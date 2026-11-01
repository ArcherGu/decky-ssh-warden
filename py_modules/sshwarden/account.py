import time

from . import DECK_USER
from .errors import UserError
from .proc import run, succeeds

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
WRONG_PASSWORD_DELAY = 2
SHADOW = "/etc/shadow"


def _password_hash() -> str:
    with open(SHADOW, encoding="utf-8") as f:
        for line in f:
            user, _, rest = line.partition(":")
            if user == DECK_USER:
                return rest.split(":", 1)[0]
    return ""


def _locked(hashed: str) -> bool:
    return hashed.startswith(("!", "*"))


def password_set() -> bool:
    """Whether changing the password needs the current one: anything but an empty hash.

    An empty hash means no password (as on a new Deck). A locked account ("!" or "*") counts
    as set: change_password() refuses it, like passwd does.
    """
    return bool(_password_hash())


def _password_matches(password: str) -> bool:
    # pam_unix's own helper; it reads one NUL-terminated password from stdin.
    return succeeds(["unix_chkpwd", DECK_USER, "nullok"], input=f"{password}\0")


def change_password(current_password: str, new_password: str) -> None:
    """Set the deck user's password (also the sudo password).

    Any local process can obtain Decky's auth token and call plugin methods, so without
    this check any program running as deck could set a password and then use sudo. Like
    passwd, the current password is required once one is set.
    """
    if not MIN_PASSWORD_LENGTH <= len(new_password) <= MAX_PASSWORD_LENGTH:
        raise UserError(
            "password_length",
            "The password must be {min} to {max} characters long",
            min=MIN_PASSWORD_LENGTH,
            max=MAX_PASSWORD_LENGTH,
        )
    if any(ord(c) < 32 or ord(c) == 127 for c in new_password):
        raise UserError("password_control_chars", "The password must not contain control characters such as line breaks")
    hashed = _password_hash()
    if _locked(hashed):
        # Setting a password here would also unlock the account.
        raise UserError("account_locked", "The deck account is locked; its password cannot be changed here")
    if hashed and not _password_matches(current_password):
        time.sleep(WRONG_PASSWORD_DELAY)  # slows down guessing through the plugin
        raise UserError("wrong_password", "The current password is wrong")
    # Passed on stdin so it never shows up in the process list or logs.
    run(["chpasswd"], input=f"{DECK_USER}:{new_password}\n")
