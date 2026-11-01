"""Changing the deck password: the current one is required once a password is set."""
from helpers import TempDirTest
from sshwarden import account
from sshwarden.errors import UserError


class ChangePasswordTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.patch(account, "SHADOW", self.path("shadow"))
        self.patch(account, "WRONG_PASSWORD_DELAY", 0)
        self.chpasswd = []
        self.patch(account, "run", lambda args, input=None, **kw: self.chpasswd.append((args, input)))
        self.current = "old-password"
        self.patch(account, "_password_matches", lambda password: password == self.current)

    def set_hash(self, hashed: str):
        with open(account.SHADOW, "w") as f:
            f.write(f"root:!*:19000::::::\ndeck:{hashed}:19000:0:99999:7:::\n")

    def assertRefused(self, code, current="old-password", new="new-password"):
        with self.assertRaises(UserError) as e:
            account.change_password(current, new)
        self.assertEqual(e.exception.code, code)
        self.assertEqual(self.chpasswd, [])

    def test_no_password_yet_needs_no_current_one(self):
        self.set_hash("")
        self.assertFalse(account.password_set())
        account.change_password("", "new-password")
        self.assertEqual(self.chpasswd, [(["chpasswd"], "deck:new-password\n")])

    def test_set_password_needs_the_current_one(self):
        self.set_hash("$y$j9T$salt$hash")
        self.assertTrue(account.password_set())
        self.assertRefused("wrong_password", current="guess")
        account.change_password("old-password", "new-password")
        self.assertEqual(self.chpasswd, [(["chpasswd"], "deck:new-password\n")])

    def test_locked_account_is_refused_not_unlocked(self):
        for hashed in ("!$y$j9T$salt$hash", "!", "*"):
            with self.subTest(hashed):
                self.set_hash(hashed)
                self.assertTrue(account.password_set())
                self.assertRefused("account_locked")

    def test_new_password_is_validated_first(self):
        self.set_hash("")
        self.assertRefused("password_length", new="short")
        self.assertRefused("password_control_chars", new="new-password\nroot::0:0")
