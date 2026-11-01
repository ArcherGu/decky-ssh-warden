import re

from .proc import run

UNIT = "sshd.service"


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
