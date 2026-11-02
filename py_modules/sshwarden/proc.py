import os
import subprocess

from .errors import UserError

SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin"


class CommandError(UserError):
    def __init__(self, command: str, detail: str):
        super().__init__("command_failed", "{command} failed: {detail}", command=command, detail=detail)


def _system_env() -> dict[str, str]:
    env = dict(os.environ)
    # Decky's loader is a PyInstaller bundle that points LD_LIBRARY_PATH at its own
    # libraries; system tools (sshd, bash, nmcli...) can fail to start with those.
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    env["PATH"] = SYSTEM_PATH
    # Parse untranslated output regardless of the system language.
    env["LC_ALL"] = "C"
    return env


def _encode(input: str | None) -> bytes | None:
    # Strict on purpose: input may be a password, which must reach the command exactly.
    # Text that cannot be encoded (a lone surrogate) raises UnicodeEncodeError instead.
    return input.encode() if input is not None else None


def run(args: list[str], *, input: str | None = None, check: bool = True, timeout: float = 30) -> str:
    """Run a command and return its stdout. Raises CommandError on failure when check is set."""
    try:
        proc = subprocess.run(args, input=_encode(input), capture_output=True, env=_system_env(), timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        if check:
            raise CommandError(args[0], str(e)) from e
        return ""
    # Output is decoded leniently: it may be a file the user picked, or a log line.
    stdout = proc.stdout.decode(errors="replace")
    if check and proc.returncode != 0:
        detail = (proc.stderr.decode(errors="replace") or stdout).strip() or f"exit status {proc.returncode}"
        raise CommandError(" ".join(args), detail)
    return stdout


def succeeds(args: list[str], *, input: str | None = None, timeout: float = 30) -> bool:
    try:
        return subprocess.run(
            args, input=_encode(input), capture_output=True, env=_system_env(), timeout=timeout
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def split_terse(line: str) -> list[str]:
    """Split one line of `nmcli -t` output, honouring its \\: and \\\\ escapes."""
    fields, current, escaped = [], [], False
    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))
    return fields
