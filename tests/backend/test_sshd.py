"""sshd: config handling and rollback, the key-login check, login history."""
import json

from helpers import TempDirTest
from sshwarden import sshd
from sshwarden.errors import UserError
from sshwarden.proc import CommandError


class FakeSshd:
    """Records commands; sshd -t/-T and ss answer as configured."""

    def __init__(self, test_ok=True, port=22, journal=""):
        self.calls, self.test_ok, self.port, self.journal = [], test_ok, port, journal

    def run(self, args, *, input=None, check=True, timeout=30):
        self.calls.append(" ".join(args))
        if args[:2] == ["sshd", "-t"] and not self.test_ok:
            raise CommandError("sshd -t", "line 3: Bad configuration option")
        if args[:2] == ["sshd", "-T"]:
            return f"port {self.port}\npasswordauthentication yes\n"
        if args[0] == "ss":
            return "LISTEN 0 128 0.0.0.0:22\n"
        if args[0] == "journalctl":
            return self.journal
        return ""


class UpdateConfigTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.patch(sshd, "DROPIN", self.path("05-ssh-warden.conf"))
        self.patch(sshd, "service_state", lambda: {"running": True, "autostart": True})
        with open(sshd.DROPIN, "w") as f:
            f.write("Port 2222\n")

    def test_applies_and_restarts(self):
        fake = FakeSshd(port=2223)
        self.patch(sshd, "run", fake.run)
        sshd.update_config({"Port": "2223", "PasswordAuthentication": "no"})
        with open(sshd.DROPIN) as f:
            self.assertEqual(f.read().splitlines()[1:], ["Port 2223", "PasswordAuthentication no"])
        self.assertIn("systemctl restart sshd.service", fake.calls)

    def test_invalid_config_restores_the_previous_drop_in(self):
        fake = FakeSshd(test_ok=False)
        self.patch(sshd, "run", fake.run)
        with self.assertRaises(CommandError):
            sshd.update_config({"Port": "2223"})
        with open(sshd.DROPIN) as f:
            self.assertEqual(f.read(), "Port 2222\n")
        self.assertIn("systemctl restart sshd.service", fake.calls)

    def test_dropping_every_setting_removes_the_drop_in(self):
        self.patch(sshd, "run", FakeSshd().run)
        sshd.update_config({"Port": None})
        self.assertFalse(sshd.read_managed())


class HostKeysTest(TempDirTest):
    def test_missing_host_keys_are_created_and_sshd_asked_again(self):
        calls, first = [], [True]

        def run(args, **kw):
            calls.append(" ".join(args))
            if args[0] == "sshd" and first[0]:
                first[0] = False
                raise CommandError("sshd -T", "sshd: no hostkeys available -- exiting.")
            return "port 22\n"

        self.patch(sshd, "run", run)
        self.assertEqual(sshd.ports(sshd.effective_config()), [22])
        self.assertEqual(calls, ["sshd -T", "ssh-keygen -A", "sshd -T"])

    def test_other_errors_are_not_retried(self):
        def run(args, **kw):
            raise CommandError("sshd -T", "line 3: Bad configuration option")

        self.patch(sshd, "run", run)
        with self.assertRaises(CommandError):
            sshd.effective_config()


class PasswordAuthTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.applied = []
        self.patch(sshd, "update_config", self.applied.append)
        self.config = {"pubkeyauthentication": ["yes"], "authorizedkeysfile": [".ssh/authorized_keys"]}
        self.patch(sshd, "effective_config", lambda: self.config)
        self.has_keys = True
        self.patch(sshd, "has_authorized_keys", lambda: self.has_keys)

    def test_off_needs_keys(self):
        self.has_keys = False
        with self.assertRaises(UserError) as e:
            sshd.set_password_auth(False)
        self.assertEqual(e.exception.code, "no_authorized_keys")

    def test_off_needs_sshd_to_accept_the_keys(self):
        self.config["pubkeyauthentication"] = ["no"]
        with self.assertRaises(UserError) as e:
            sshd.set_password_auth(False)
        self.assertEqual(e.exception.code, "keys_not_accepted")
        self.assertEqual(self.applied, [])

    def test_off_and_on(self):
        sshd.set_password_auth(False)
        sshd.set_password_auth(True)
        self.assertEqual(self.applied, [{"PasswordAuthentication": "no"}, {"PasswordAuthentication": None}])

    def test_accepts_keys(self):
        ok = {"authorizedkeysfile": [".ssh/authorized_keys .ssh/authorized_keys2"]}
        self.assertTrue(sshd.accepts_keys(ok))
        self.assertTrue(sshd.accepts_keys({**ok, "pubkeyauthentication": ["host-bound"]}))
        self.assertFalse(sshd.accepts_keys({**ok, "pubkeyauthentication": ["no"]}))
        self.assertFalse(sshd.accepts_keys({"authorizedkeysfile": ["/etc/ssh/keys/%u"]}))
        self.assertFalse(sshd.accepts_keys({**ok, "authenticationmethods": ["publickey,password"]}))
        self.assertTrue(sshd.accepts_keys({**ok, "authenticationmethods": ["publickey,password publickey"]}))


class LoginHistoryTest(TempDirTest):
    def test_each_failed_connection_counts_once(self):
        journal = "\n".join([
            "1700000000.0 sshd-session[1]: Invalid user admin from 1.2.3.4 port 5555",
            "1700000000.1 sshd-session[1]: Failed none for invalid user admin from 1.2.3.4 port 5555 ssh2",
            "1700000000.2 sshd-session[1]: Failed password for invalid user admin from 1.2.3.4 port 5555 ssh2",
            "1700000000.3 sshd-session[1]: Failed password for invalid user admin from 1.2.3.4 port 5555 ssh2",
            "1700000001.0 sshd-session[2]: Failed password for deck from 5.6.7.8 port 6000 ssh2",
            "1700000001.5 sshd-session[2]: Accepted password for deck from 5.6.7.8 port 6000 ssh2",
            "1700000002.0 sshd-session[3]: Invalid user  from 9.9.9.9 port 7000",
            "1700000003.0 sshd-session[4]: Accepted publickey for deck from 5.6.7.8 port 6001 ssh2: ED25519 SHA256:x",
        ])
        self.patch(sshd, "run", FakeSshd(journal=journal).run)
        history = sshd.login_history()
        self.assertEqual(history["failed"], 2)
        self.assertEqual([(r["method"], r["from"]) for r in history["recent"]], [("publickey", "5.6.7.8"), ("password", "5.6.7.8")])


class AutooffTest(TempDirTest):
    def test_deadline_from_systemd(self):
        timers = [{"unit": "ssh-warden-autooff.timer", "next": 1_700_000_000_000_000}]
        self.patch(sshd, "run", lambda args, **kw: json.dumps(timers))
        self.assertEqual(sshd.autooff_deadline(), 1_700_000_000)
        self.patch(sshd, "run", lambda args, **kw: "[]")
        self.assertIsNone(sshd.autooff_deadline())

    def test_out_of_range(self):
        for minutes in (0, sshd.MAX_AUTOOFF_MINUTES + 1):
            with self.assertRaises(UserError):
                sshd.schedule_autooff(minutes)
