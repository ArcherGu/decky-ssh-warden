"""proc (running commands) and lock (one change at a time)."""
import threading
import time
import unittest

from helpers import TempDirTest
from sshwarden import lock, proc
from sshwarden.proc import CommandError


class ProcTest(unittest.TestCase):
    def test_failure_carries_the_command_and_its_message(self):
        with self.assertRaises(CommandError) as e:
            proc.run(["sh", "-c", "echo oops >&2; exit 3"])
        self.assertEqual((e.exception.code, e.exception.params["detail"]), ("command_failed", "oops"))
        self.assertEqual(proc.run(["sh", "-c", "exit 3"], check=False), "")

    def test_binary_output_does_not_break_decoding(self):
        self.assertIn("�", proc.run(["printf", "\\377key"]))

    def test_input_is_passed_exactly_or_not_at_all(self):
        self.assertEqual(proc.run(["cat"], input="pässwörd\n"), "pässwörd\n")
        for call in (proc.run, proc.succeeds):
            with self.subTest(call.__name__), self.assertRaises(UnicodeEncodeError):
                call(["cat"], input="pass\ud800word")

    def test_failure_keeps_the_exit_status(self):
        with self.assertRaises(CommandError) as e:
            proc.run(["sh", "-c", "exit 124"])
        self.assertEqual((e.exception.returncode, e.exception.params["detail"]), (124, "exit status 124"))

    def test_succeeds_with_input(self):
        self.assertTrue(proc.succeeds(["grep", "-q", "secret"], input="the secret\n"))
        self.assertFalse(proc.succeeds(["grep", "-q", "secret"], input="nothing\n"))
        self.assertFalse(proc.succeeds(["/nonexistent/command"]))

    def test_split_terse_honours_escapes(self):
        self.assertEqual(proc.split_terse(r"Café\: 5G:uuid:802-11-wireless:wlan0"), ["Café: 5G", "uuid", "802-11-wireless", "wlan0"])
        self.assertEqual(proc.split_terse(r"a\\b:c"), ["a\\b", "c"])


class LockTest(TempDirTest):
    def test_changes_run_one_at_a_time(self):
        events = []

        def second():
            with lock.changes():
                events.append("second")

        with lock.changes():
            thread = threading.Thread(target=second)
            thread.start()
            time.sleep(0.2)
            events.append("first done")
        thread.join(5)
        self.assertEqual(events, ["first done", "second"])

    def test_unless_busy_never_waits(self):
        with lock.unless_busy() as idle:
            self.assertTrue(idle)
        with lock.changes(), lock.unless_busy() as idle:
            self.assertFalse(idle)

    def test_reads_at_the_same_time_do_not_take_each_other_for_a_change(self):
        with lock.unless_busy() as first, lock.unless_busy() as second:
            self.assertEqual((first, second), (True, True))

    def test_a_change_waits_for_a_read(self):
        events = []

        def change():
            with lock.changes():
                events.append("change")

        with lock.unless_busy():
            thread = threading.Thread(target=change)
            thread.start()
            time.sleep(0.2)
            events.append("read done")
        thread.join(5)
        self.assertEqual(events, ["read done", "change"])
