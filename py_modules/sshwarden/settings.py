"""Small JSON store for what the plugin itself changed (e.g. firewall rules it added)."""
import json
import os

DEFAULT_DIR = "/home/deck/homebrew/settings/decky-ssh-warden"

_path = os.path.join(DEFAULT_DIR, "settings.json")


def init(directory: str) -> None:
    global _path
    _path = os.path.join(directory, "settings.json")


def load() -> dict:
    try:
        with open(_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(data: dict) -> None:
    os.makedirs(os.path.dirname(_path), exist_ok=True)
    tmp = f"{_path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _path)
