"""Command-line entry for testing the backend on the Deck without the UI.

    sudo PYTHONPATH=/home/deck/homebrew/plugins/decky-ssh-warden/py_modules python3 -m sshwarden status
"""
import json
import sys

from . import port, sshd, status


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
    }
    if not argv or argv[0] not in commands:
        print(f"usage: python3 -m sshwarden {{{'|'.join(commands)}}} [args...]", file=sys.stderr)
        return 2
    print(json.dumps(commands[argv[0]](*argv[1:]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
