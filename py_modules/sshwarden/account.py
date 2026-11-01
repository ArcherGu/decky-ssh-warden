from . import DECK_USER
from .errors import UserError
from .proc import run

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def change_password(new_password: str) -> None:
    """Set the deck user's password (also the sudo password)."""
    if not MIN_PASSWORD_LENGTH <= len(new_password) <= MAX_PASSWORD_LENGTH:
        raise UserError(
            "password_length",
            "The password must be {min} to {max} characters long",
            min=MIN_PASSWORD_LENGTH,
            max=MAX_PASSWORD_LENGTH,
        )
    if any(ord(c) < 32 or ord(c) == 127 for c in new_password):
        raise UserError("password_control_chars", "The password must not contain control characters such as line breaks")
    # Passed on stdin so it never shows up in the process list or logs.
    run(["chpasswd"], input=f"{DECK_USER}:{new_password}\n")
