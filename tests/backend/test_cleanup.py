"""Uninstall notes the user's settings; the next load after an update puts them back."""
import time

from helpers import TempDirTest
from sshwarden import cleanup, port, settings, sshd, trust


class RestoreTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.patch(cleanup, "_wait_for_uninstall", lambda: None)
        self.steps = []
        self.patch(port, "set_port", lambda p: self.steps.append(("port", p)))
        self.patch(trust, "set_enabled", lambda on: self.steps.append(("trusted_mode", on)))
        self.patch(sshd, "set_password_auth", lambda on: self.steps.append(("password_auth", on)))
        self.patch(sshd, "schedule_autooff", lambda m: self.steps.append(("autooff", m)))

    def note(self, **values):
        note = {"at": time.time(), "port": "2222", "password_auth": False, "trusted_mode": True,
                "autooff_at": time.time() + 30 * 60, **values}
        settings.save({"trusted": ["uuid"], cleanup.NOTE: note})

    def test_nothing_noted(self):
        self.assertIsNone(cleanup.restore_after_update())
        self.assertEqual(self.steps, [])

    def test_restores_in_order_and_drops_the_note(self):
        self.note()
        result = cleanup.restore_after_update()
        self.assertEqual(self.steps, [("port", 2222), ("trusted_mode", True), ("password_auth", False), ("autooff", 30)])
        self.assertEqual(result, {"restored": ["port", "trusted_mode", "password_auth", "autooff"], "failed": {}})
        self.assertEqual(settings.load(), {"trusted": ["uuid"]})

    def test_defaults_need_no_steps(self):
        self.note(port=None, password_auth=True, trusted_mode=False, autooff_at=None)
        self.assertEqual(cleanup.restore_after_update(), {"restored": [], "failed": {}})
        self.assertEqual(self.steps, [])

    def test_an_old_note_is_dropped_without_restoring(self):
        self.note(at=time.time() - cleanup.REINSTALL_WINDOW - 1)
        self.assertIsNone(cleanup.restore_after_update())
        self.assertEqual(self.steps, [])
        self.assertNotIn(cleanup.NOTE, settings.load())

    def test_a_failing_step_does_not_stop_the_others(self):
        def broken(p):
            raise RuntimeError("port in use")
        self.patch(port, "set_port", broken)
        self.note()
        result = cleanup.restore_after_update()
        self.assertEqual(result["failed"], {"port": "port in use"})
        self.assertEqual(result["restored"], ["trusted_mode", "password_auth", "autooff"])

    def test_the_note_survives_an_interrupted_restore(self):
        # Decky kills the first process of a fresh install; the next one must find the note.
        def killed(on):
            raise KeyboardInterrupt
        self.patch(trust, "set_enabled", killed)
        self.note()
        with self.assertRaises(KeyboardInterrupt):
            cleanup.restore_after_update()
        self.assertIn(cleanup.NOTE, settings.load())


class UninstallTest(TempDirTest):
    def test_notes_the_settings_before_reverting(self):
        self.patch(sshd, "read_managed", lambda: {"Port": "2222", "PasswordAuthentication": "no"})
        self.patch(trust, "is_enabled", lambda data: True)
        self.patch(sshd, "autooff_deadline", lambda: 1234.0)
        seen = []
        self.patch(cleanup, "revert_all", lambda: seen.append(settings.load()[cleanup.NOTE]))
        cleanup.uninstall()
        note = seen[0]
        self.assertEqual((note["port"], note["password_auth"], note["trusted_mode"], note["autooff_at"]), ("2222", False, True, 1234.0))
