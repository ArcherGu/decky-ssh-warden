"""Small JSON store for what the plugin itself changed (e.g. firewall rules it added).

It lives in Decky's settings directory, which belongs to the deck user, so it is read and
written through safefile (no symlinks followed).
"""
import json
import os

from . import safefile

DEFAULT_DIR = "/home/deck/homebrew/settings/decky-ssh-warden"
NAME = "settings.json"
MAX_BYTES = 1024 * 1024

_dir = DEFAULT_DIR


def init(directory: str) -> None:
    global _dir
    _dir = directory


def load() -> dict:
    """The stored settings; empty when missing, corrupt or not a plain file."""
    try:
        dir_fd = safefile.open_dir(_dir)
    except OSError:
        return {}
    try:
        data = safefile.read(dir_fd, NAME, MAX_BYTES)
        return json.loads(data) if data else {}
    except (OSError, ValueError):
        return {}
    finally:
        os.close(dir_fd)


def save(data: dict) -> None:
    dir_fd = safefile.open_dir(_dir, create_mode=0o755)
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        safefile.write(dir_fd, NAME, text.encode(), 0o644)
    finally:
        os.close(dir_fd)
