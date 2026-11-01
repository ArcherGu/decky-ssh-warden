"""authorized_keys: parsing, fingerprints, import and removal."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

from helpers import TempDirTest
from sshwarden import keys, sshd
from sshwarden.errors import UserError
from sshwarden.proc import CommandError

ED25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJZK9sn/SHYKn/RlF2aXd5YqbQ7b4kUYxN0zCo8Ys0vX"


def generate(key_type: str, comment: str) -> tuple[str, str]:
    """A fresh public key line and its fingerprint according to ssh-keygen."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "key")
        subprocess.run(["ssh-keygen", "-q", "-t", key_type, "-N", "", "-C", comment, "-f", path], check=True)
        with open(path + ".pub") as f:
            line = f.read().strip()
        fingerprint = subprocess.run(["ssh-keygen", "-lf", path + ".pub"], capture_output=True, text=True, check=True).stdout.split()[1]
    return line, fingerprint


class ParseKeyTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ssh-keygen"), "needs ssh-keygen")
    def test_fingerprints_match_ssh_keygen(self):
        for key_type in ("ed25519", "ecdsa", "rsa"):
            with self.subTest(key_type):
                line, fingerprint = generate(key_type, f"me@{key_type}")
                key = keys.parse_key(line)
                self.assertEqual(key["fingerprint"], fingerprint)
                self.assertEqual(key["comment"], f"me@{key_type}")

    def test_options_and_comments_with_spaces(self):
        key = keys.parse_key(f'from="10.0.0.0/8",command="echo hi there" {ED25519} my laptop')
        self.assertEqual((key["type"], key["comment"]), ("ED25519", "my laptop"))

    def test_not_keys(self):
        for line in ("", "# ssh-ed25519 AAAA", "ssh-ed25519 not-base64!", "ssh-rsa " + ED25519.split()[1], "garbage"):
            with self.subTest(line):
                self.assertIsNone(keys.parse_key(line))


class KeyFileTest(TempDirTest):
    def setUp(self):
        super().setUp()
        home = self.path("home")
        os.mkdir(home)
        self.patch(keys, "HOME", home)
        self.patch(keys, "SSH_DIR", os.path.join(home, ".ssh"))
        me = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
        self.patch(keys.pwd, "getpwnam", lambda name: me)
        self.patch(keys, "run", self.fake_runuser_head)
        self.authorized_keys = os.path.join(home, ".ssh", "authorized_keys")
        self.password_auth = True
        self.patch(sshd, "password_auth_enabled", lambda: self.password_auth)

    @staticmethod
    def fake_runuser_head(args, timeout=30, **kw):
        """`runuser -u deck -- head -c N -- PATH`, run as the test user."""
        assert args[:3] == ["runuser", "-u", "deck"] and args[4] == "head", args
        try:
            with open(args[-1], "rb") as f:
                return f.read(int(args[6])).decode("utf-8", "replace")
        except OSError as e:
            raise CommandError(" ".join(args), f"head: cannot open '{args[-1]}' for reading: {e.strerror}")

    def write_file(self, name: str, text: str) -> str:
        path = self.path(name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_import_creates_ssh_dir_and_file_with_sshd_permissions(self):
        result = keys.import_file(self.write_file("a.pub", ED25519 + " a\n"))
        self.assertEqual(result, {"added": 1, "skipped": 0})
        self.assertEqual(stat.S_IMODE(os.stat(keys.SSH_DIR).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.authorized_keys).st_mode), 0o600)
        self.assertEqual([k["comment"] for k in keys.list_keys()], ["a"])

    def test_import_skips_known_keys_and_keeps_other_lines(self):
        os.mkdir(keys.SSH_DIR, 0o700)
        with open(self.authorized_keys, "w") as f:
            f.write("# my comment\n" + ED25519 + " a\n")
        other = ED25519.replace("JZK9", "JZK8")
        result = keys.import_file(self.write_file("many", f"{ED25519} again\n{other} b\nnot a key\n"))
        self.assertEqual(result, {"added": 1, "skipped": 1})
        with open(self.authorized_keys) as f:
            self.assertEqual(f.read(), f"# my comment\n{ED25519} a\n{other} b\n")

    def test_import_rejects_private_keys_and_files_without_keys(self):
        private = self.write_file("id_ed25519", "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n")
        with self.assertRaises(UserError) as e:
            keys.import_file(private)
        self.assertEqual(e.exception.code, "key_file_private")
        with self.assertRaises(UserError) as e:
            keys.import_file(self.write_file("notes.txt", "hello\n"))
        self.assertEqual(e.exception.code, "key_file_invalid")
        self.assertFalse(os.path.exists(self.authorized_keys))

    def test_import_reports_why_a_file_cannot_be_read(self):
        with self.assertRaises(UserError) as e:
            keys.import_file(self.path("missing.pub"))
        self.assertEqual(e.exception.code, "key_file_unreadable")
        self.assertEqual(e.exception.params, {"file": "missing.pub", "reason": "No such file or directory"})

    def test_remove(self):
        keys.import_file(self.write_file("a.pub", f"{ED25519} a\n"))
        fingerprint = keys.list_keys()[0]["fingerprint"]
        with self.assertRaises(UserError) as e:
            keys.remove_key("SHA256:unknown")
        self.assertEqual(e.exception.code, "key_not_found")
        keys.remove_key(fingerprint)
        self.assertEqual(keys.list_keys(), [])

    def test_last_key_stays_while_password_login_is_off(self):
        keys.import_file(self.write_file("a.pub", f"{ED25519} a\n"))
        self.password_auth = False
        with self.assertRaises(UserError) as e:
            keys.remove_key(keys.list_keys()[0]["fingerprint"])
        self.assertEqual(e.exception.code, "last_key")

    def test_a_symlinked_or_special_authorized_keys_is_left_alone(self):
        target = self.write_file("shadow", ED25519 + " root-only\n")
        os.mkdir(keys.SSH_DIR, 0o700)
        makers = {"symlink": lambda: os.symlink(target, self.authorized_keys), "fifo": lambda: os.mkfifo(self.authorized_keys)}
        for kind, make in makers.items():
            make()
            with self.subTest(kind):
                with self.assertRaises(UserError) as e:
                    keys.list_keys()
                self.assertEqual(e.exception.code, "keys_file_unsafe")
                self.assertFalse(keys.has_authorized_keys())
                with self.assertRaises(UserError):
                    keys.import_file(self.write_file("a.pub", ED25519 + " a\n"))
            os.unlink(self.authorized_keys)
        with open(target) as f:
            self.assertEqual(f.read(), ED25519 + " root-only\n")

    def test_a_symlinked_ssh_dir_is_left_alone(self):
        elsewhere = self.path("elsewhere")
        os.mkdir(elsewhere)
        os.symlink(elsewhere, keys.SSH_DIR)
        with self.assertRaises(UserError):
            keys.import_file(self.write_file("a.pub", ED25519 + " a\n"))
        self.assertEqual(os.listdir(elsewhere), [])
