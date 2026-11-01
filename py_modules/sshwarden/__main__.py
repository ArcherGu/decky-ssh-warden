"""Command-line entry for testing the backend on the Deck without the UI.

    sudo PYTHONPATH=/home/deck/homebrew/plugins/decky-ssh-warden/py_modules python3 -m sshwarden status
"""
import json
import sys

from . import status


def main(argv: list[str]) -> int:
    commands = {
        "status": lambda: status.collect(),
    }
    if not argv or argv[0] not in commands:
        print(f"usage: python3 -m sshwarden {{{'|'.join(commands)}}} [args...]", file=sys.stderr)
        return 2
    print(json.dumps(commands[argv[0]](*argv[1:]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
