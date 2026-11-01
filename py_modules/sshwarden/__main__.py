"""Command-line entry for testing the backend on the Deck without the UI.

    sudo PYTHONPATH=/home/deck/homebrew/plugins/decky-ssh-warden/py_modules python3 -m sshwarden status
"""
import json
import os
import sys

from . import account, cleanup, keys, lock, port, settings, sshd, status, trust


def on_off(value: str) -> bool:
    if value not in ("on", "off"):
        raise SystemExit("expected on|off")
    return value == "on"


def main(argv: list[str]) -> int:
    commands = {
        "status": lambda: status.collect(),
        "service": lambda v: sshd.set_running(on_off(v)),
        "autostart": lambda v: sshd.set_autostart(on_off(v)),
        "autooff": lambda minutes: sshd.schedule_autooff(int(minutes)) if minutes != "cancel" else sshd.cancel_autooff(),
        "port": lambda number: port.set_port(int(number)),
        "password-auth": lambda v: sshd.set_password_auth(on_off(v)),
        # Reads the current and the new password from stdin (one per line) to keep them out of argv.
        "passwd": lambda: account.change_password(sys.stdin.readline().rstrip("\n"), sys.stdin.readline().rstrip("\n")),
        "keys": lambda: keys.list_keys(),
        "key-import": lambda path: keys.import_file(path),
        "key-remove": lambda fingerprint: keys.remove_key(fingerprint),
        "trusted-mode": lambda v: trust.set_enabled(on_off(v)),
        "trust": lambda uuid, v: trust.set_network_trusted(uuid, on_off(v)),
        "cleanup": lambda: cleanup.revert_all(),
        # What the plugin's _uninstall runs in the background: note the settings, then revert.
        "uninstall": lambda: cleanup.uninstall(),
    }
    settings.init(os.environ.get("SSH_WARDEN_SETTINGS_DIR", settings.DEFAULT_DIR))
    if not argv or argv[0] not in commands:
        print(f"usage: python3 -m sshwarden {{{'|'.join(commands)}}} [args...]", file=sys.stderr)
        return 2
    command = commands[argv[0]]
    if argv[0] in ("status", "keys", "uninstall"):  # reads, or takes the lock itself
        result = command(*argv[1:])
    else:
        with lock.changes():  # never at the same time as the plugin's own changes
            result = command(*argv[1:])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
