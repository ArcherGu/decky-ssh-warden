import json
import re

from .proc import run

UNIT = "sshd.service"
AUTOOFF_UNIT = "ssh-warden-autooff"
MAX_AUTOOFF_MINUTES = 24 * 60


def effective_config() -> dict[str, list[str]]:
    """The configuration sshd would actually use (`sshd -T`), keys lower-cased."""
    config: dict[str, list[str]] = {}
    for line in run(["sshd", "-T"]).splitlines():
        key, _, value = line.partition(" ")
        config.setdefault(key.lower(), []).append(value)
    return config


def ports(config: dict[str, list[str]]) -> list[int]:
    return sorted({int(p) for p in config.get("port", ["22"])})


def service_state() -> dict:
    return {
        "running": run(["systemctl", "is-active", UNIT], check=False).strip() == "active",
        "autostart": run(["systemctl", "is-enabled", UNIT], check=False).strip() == "enabled",
    }


def set_running(on: bool) -> None:
    # Stopping only closes the listener; established sessions stay connected.
    run(["systemctl", "start" if on else "stop", UNIT])
    if not on:
        cancel_autooff()


def schedule_autooff(minutes: int) -> None:
    """Stop sshd `minutes` from now with a transient systemd timer (survives Decky restarts)."""
    if not 1 <= minutes <= MAX_AUTOOFF_MINUTES:
        raise ValueError(f"自动关闭时间需在 1 到 {MAX_AUTOOFF_MINUTES} 分钟之间")
    cancel_autooff()
    run([
        "systemd-run",
        f"--unit={AUTOOFF_UNIT}",
        f"--on-active={minutes}min",
        "--timer-property=AccuracySec=1s",
        "--description=SSH Warden: stop sshd after a timeout",
        "/usr/bin/systemctl", "stop", UNIT,
    ])


def cancel_autooff() -> None:
    run(["systemctl", "stop", f"{AUTOOFF_UNIT}.timer"], check=False)
    run(["systemctl", "reset-failed", f"{AUTOOFF_UNIT}.timer", f"{AUTOOFF_UNIT}.service"], check=False)


def autooff_deadline() -> float | None:
    """Unix time at which sshd will be stopped automatically, or None."""
    out = run(["systemctl", "list-timers", "--all", "-o", "json", f"{AUTOOFF_UNIT}.timer"], check=False)
    try:
        timers = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None
    for t in timers:
        if t.get("unit") == f"{AUTOOFF_UNIT}.timer" and t.get("next"):
            return t["next"] / 1_000_000
    return None


def set_autostart(on: bool) -> None:
    run(["systemctl", "enable" if on else "disable", UNIT])


def sessions(listen_ports: list[int]) -> list[str]:
    """Remote addresses of established SSH connections."""
    peers = []
    for line in run(["ss", "-Htn", "state", "established"], check=False).splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        local, peer = cols[2], cols[3]
        try:
            local_port = int(local.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        if local_port in listen_ports:
            peers.append(peer.rsplit(":", 1)[0].strip("[]"))
    return peers


_ACCEPTED = re.compile(r"Accepted (\S+) for (\S+) from (\S+) port")
_FAILED = re.compile(r"Failed \S+ for (?:invalid user )?(\S+) from (\S+) port|Invalid user (\S*) from (\S+) port")


def login_history(hours: int = 24, recent: int = 3) -> dict:
    """Successful logins (most recent first) and failed attempts within the last `hours`."""
    out = run(
        ["journalctl", "-u", UNIT, "--since", f"-{hours}h", "--no-pager", "-o", "short-unix"],
        check=False,
    )
    accepted, failed = [], 0
    for line in out.splitlines():
        if m := _ACCEPTED.search(line):
            accepted.append({
                "time": float(line.split(" ", 1)[0]),
                "method": m.group(1),
                "user": m.group(2),
                "from": m.group(3),
            })
        elif _FAILED.search(line):
            failed += 1
    return {"recent": accepted[::-1][:recent], "failed": failed}
