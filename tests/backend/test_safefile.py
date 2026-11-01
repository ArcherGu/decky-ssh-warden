"""safefile and settings: nothing planted in a directory the deck user owns may redirect root."""
import json
import os
import stat

from helpers import TempDirTest
from sshwarden import safefile, settings


class SafefileTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.dir = self.path("home")
        os.mkdir(self.dir)
        self.target = self.path("target")  # stands in for /etc/shadow
        with open(self.target, "w") as f:
            f.write("secret\n")

    def open(self, path=None, **kw):
        fd = safefile.open_dir(path or self.dir, **kw)
        self.addCleanup(os.close, fd)
        return fd

    def test_open_dir_refuses_a_symlinked_component(self):
        os.symlink(self.dir, self.path("link"))
        os.mkdir(os.path.join(self.dir, "sub"))
        with self.assertRaises(OSError):
            safefile.open_dir(self.path("link", "sub"))

    def test_open_dir_creates_the_last_component_on_request(self):
        fd = self.open(os.path.join(self.dir, "new"), create_mode=0o700)
        self.assertTrue(stat.S_ISDIR(os.fstat(fd).st_mode))
        with self.assertRaises(FileNotFoundError):
            safefile.open_dir(os.path.join(self.dir, "missing"))

    def test_read(self):
        fd = self.open()
        self.assertIsNone(safefile.read(fd, "missing", 100))
        with open(os.path.join(self.dir, "file"), "w") as f:
            f.write("hello")
        self.assertEqual(safefile.read(fd, "file", 100), b"hello")
        with self.assertRaises(OSError):
            safefile.read(fd, "file", 3)  # over the limit

    def test_read_refuses_symlinks_fifos_and_directories(self):
        fd = self.open()
        os.symlink(self.target, os.path.join(self.dir, "link"))
        os.mkfifo(os.path.join(self.dir, "fifo"))  # would block forever without O_NONBLOCK
        os.mkdir(os.path.join(self.dir, "dir"))
        for name in ("link", "fifo", "dir"):
            with self.subTest(name), self.assertRaises(OSError):
                safefile.read(fd, name, 100)

    def test_write_replaces_a_planted_symlink_instead_of_following_it(self):
        fd = self.open()
        os.symlink(self.target, os.path.join(self.dir, "authorized_keys"))
        safefile.write(fd, "authorized_keys", b"new\n", 0o600, (os.getuid(), os.getgid()))
        with open(self.target) as f:
            self.assertEqual(f.read(), "secret\n")
        written = os.path.join(self.dir, "authorized_keys")
        self.assertFalse(os.path.islink(written))
        self.assertEqual(stat.S_IMODE(os.stat(written).st_mode), 0o600)
        with open(written) as f:
            self.assertEqual(f.read(), "new\n")
        self.assertEqual(os.listdir(self.dir), ["authorized_keys"])  # no temporary file left


class SettingsTest(TempDirTest):
    def test_round_trip_and_missing_file(self):
        self.assertEqual(settings.load(), {})
        settings.save({"trusted": ["a"], "firewall": []})
        self.assertEqual(settings.load(), {"trusted": ["a"], "firewall": []})

    def test_corrupt_file_reads_as_empty(self):
        with open(os.path.join(settings._dir, settings.NAME), "w") as f:
            f.write("{not json")
        self.assertEqual(settings.load(), {})

    def test_symlinked_settings_are_neither_read_nor_followed(self):
        target = self.path("target")
        with open(target, "w") as f:
            json.dump({"trusted": ["planted"]}, f)
        os.symlink(target, os.path.join(settings._dir, settings.NAME))
        self.assertEqual(settings.load(), {})
        settings.save({"trusted": []})
        with open(target) as f:
            self.assertEqual(json.load(f), {"trusted": ["planted"]})
        self.assertEqual(settings.load(), {"trusted": []})
