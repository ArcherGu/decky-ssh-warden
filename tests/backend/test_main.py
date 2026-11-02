"""The entry points: main.py (every panel call goes through _call()) and the command-line tool."""
import asyncio
import contextlib
import fcntl
import io
import logging
import os
import re
import sys
import types
from unittest import mock

from helpers import TempDirTest
from sshwarden import __main__ as cli, cleanup, lock, sshd, status
from sshwarden.errors import UserError
from sshwarden.proc import CommandError

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# main.py imports Decky's own module, which only exists inside the loader.
decky = types.ModuleType("decky")
decky.logger = logging.getLogger("decky")
decky.DECKY_PLUGIN_SETTINGS_DIR = "/nonexistent"
sys.modules.setdefault("decky", decky)
sys.path.insert(0, REPO)
import main  # noqa: E402


def lock_held() -> bool:
    """Whether someone holds lock.changes(), asked from outside like another process would."""
    fd = os.open(lock.PATH, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


class CallTest(TempDirTest):
    def call(self, fn, *args, **kw):
        return asyncio.run(main._call(fn, *args, **kw))

    def test_result_is_wrapped(self):
        self.assertEqual(self.call(lambda a, b: a + b, 2, 3), {"ok": True, "data": 5})

    def test_user_errors_carry_code_and_params_for_the_panel(self):
        def fail():
            raise UserError("port_in_use", "Port {port} is already used by {owner}", port=1337, owner="Decky Loader")

        with self.assertLogs("decky", "ERROR"):
            result = self.call(fail)
        self.assertEqual(result, {
            "ok": False,
            "error": "Port 1337 is already used by Decky Loader",
            "code": "port_in_use",
            "params": {"port": 1337, "owner": "Decky Loader"},
        })

    def test_command_errors_are_user_errors_too(self):
        def fail():
            raise CommandError("sshd -t", "line 3: Bad configuration option")

        with self.assertLogs("decky", "ERROR"):
            result = self.call(fail)
        self.assertEqual((result["code"], result["params"]["detail"]), ("command_failed", "line 3: Bad configuration option"))

    def test_other_exceptions_only_give_their_message(self):
        def fail():
            raise RuntimeError("boom")

        with self.assertLogs("decky", "ERROR"):
            self.assertEqual(self.call(fail), {"ok": False, "error": "boom"})

    def test_changes_hold_the_lock_reads_do_not(self):
        self.assertEqual(self.call(lock_held), {"ok": True, "data": True})
        self.assertEqual(self.call(lock_held, exclusive=False), {"ok": True, "data": False})
        self.assertFalse(lock_held())


class PluginTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.plugin = main.Plugin()
        self.calls = []

    def record(self, name, result=None):
        def fn(*args):
            self.calls.append((name, args, lock_held()))
            return result
        return fn

    def test_status_is_read_without_the_lock(self):
        self.patch(status, "collect", self.record("collect", {"running": True}))
        self.assertEqual(asyncio.run(self.plugin.get_status()), {"ok": True, "data": {"running": True}})
        self.assertEqual(self.calls, [("collect", (), False)])

    def test_arguments_are_coerced_and_changes_locked(self):
        self.patch(sshd, "schedule_autooff", self.record("schedule"))
        self.patch(sshd, "cancel_autooff", self.record("cancel"))
        asyncio.run(self.plugin.set_autooff("30"))
        asyncio.run(self.plugin.set_autooff(0))
        self.assertEqual(self.calls, [("schedule", (30,), True), ("cancel", (), True)])

    def test_uninstall_falls_back_when_the_background_service_cannot_start(self):
        def start(settings_dir):
            raise CommandError("systemd-run", "Failed to start transient service unit")

        self.patch(cleanup, "start_uninstall", start)
        self.patch(cleanup, "uninstall", self.record("uninstall"))
        with self.assertLogs("decky", "ERROR"):
            asyncio.run(self.plugin._uninstall())
        self.assertEqual(self.calls, [("uninstall", (), False)])  # uninstall() takes the lock itself

    def test_every_method_the_panel_calls_exists(self):
        with open(os.path.join(REPO, "src", "api.ts"), encoding="utf-8") as f:
            names = re.findall(r'callable<.*?>\("(\w+)"\)', f.read())
        self.assertGreater(len(names), 5)
        for name in names:
            self.assertTrue(callable(getattr(main.Plugin, name, None)), f"main.Plugin has no {name}()")


class CommandLineTest(TempDirTest):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"SSH_WARDEN_SETTINGS_DIR": self.path("settings")}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_usage(self):
        code, _, err = self.run_cli("nonsense")
        self.assertEqual(code, 2)
        self.assertIn("usage:", err)

    def test_reads_print_json_without_the_lock(self):
        self.patch(status, "collect", lambda: {"locked": lock_held()})
        self.assertEqual(self.run_cli("status")[:2], (0, '{\n  "locked": false\n}\n'))

    def test_changes_take_the_lock(self):
        seen = []
        self.patch(sshd, "set_running", lambda on: seen.append((on, lock_held())))
        self.assertEqual(self.run_cli("service", "off")[0], 0)
        self.assertEqual(seen, [(False, True)])
        with self.assertRaises(SystemExit):
            self.run_cli("service", "maybe")

    def test_passwd_reads_both_passwords_from_stdin(self):
        from sshwarden import account

        seen = []
        self.patch(account, "change_password", lambda current, new: seen.append((current, new)))
        with mock.patch("sys.stdin", io.StringIO("old password\nnew password\n")):
            self.assertEqual(self.run_cli("passwd")[0], 0)
        self.assertEqual(seen, [("old password", "new password")])
