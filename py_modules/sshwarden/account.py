import os

from . import DECK_USER

AUTHORIZED_KEYS = f"/home/{DECK_USER}/.ssh/authorized_keys"


def authorized_key_count() -> int:
    try:
        with open(AUTHORIZED_KEYS, encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.strip() and not line.lstrip().startswith("#"))
    except FileNotFoundError:
        return 0


def has_authorized_keys() -> bool:
    return os.path.exists(AUTHORIZED_KEYS) and authorized_key_count() > 0
