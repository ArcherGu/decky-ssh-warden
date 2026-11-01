import os

from . import DECK_USER
from .proc import run

AUTHORIZED_KEYS = f"/home/{DECK_USER}/.ssh/authorized_keys"
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def authorized_key_count() -> int:
    try:
        with open(AUTHORIZED_KEYS, encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.strip() and not line.lstrip().startswith("#"))
    except FileNotFoundError:
        return 0


def has_authorized_keys() -> bool:
    return os.path.exists(AUTHORIZED_KEYS) and authorized_key_count() > 0


def change_password(new_password: str) -> None:
    """Set the deck user's password (also the sudo password)."""
    if not MIN_PASSWORD_LENGTH <= len(new_password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(f"密码长度需在 {MIN_PASSWORD_LENGTH} 到 {MAX_PASSWORD_LENGTH} 个字符之间")
    if any(ord(c) < 32 or ord(c) == 127 for c in new_password):
        raise ValueError("密码不能包含换行等控制字符")
    # Passed on stdin so it never shows up in the process list or logs.
    run(["chpasswd"], input=f"{DECK_USER}:{new_password}\n")
