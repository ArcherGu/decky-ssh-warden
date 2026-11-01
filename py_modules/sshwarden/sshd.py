import json
import os
import re
import time

from .account import has_authorized_keys
from .proc import CommandError, run

UNIT = "sshd.service"
AUTOOFF_UNIT = "ssh-warden-autooff"
MAX_AUTOOFF_MINUTES = 24 * 60

# Our drop-in sorts before SteamOS's own (20-*, 99-*); sshd keeps the first value it reads.
DROPIN = "/etc/ssh/sshd_config.d/05-ssh-warden.conf"
MANAGED_KEYS = ("Port", "PasswordAuthentication")
DEFAULT_PORT = 22


def effective_config() -> dict[str, list[str]]:
    """The configuration sshd would actually use (`sshd -T`), keys lower-cased."""
    config: dict[str, list[str]] = {}
    for line in run(["sshd", "-T"]).splitlines():
        key, _, value = line.partition(" ")
        config.setdefault(key.lower(), []).append(value)
    return config


def ports(config: dict[str, list[str]]) -> list[int]:
    return sorted({int(p) for p in config.get("port", ["22"])})


def read_managed() -> dict[str, str]:
    """Settings currently written in our drop-in, e.g. {"Port": "2222"}."""
    values: dict[str, str] = {}
    try:
        with open(DROPIN, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return values
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition(" ")
            values[key] = value.strip()
    return values


def _write_dropin(values: dict[str, str]) -> None:
    lines = [f"{k} {values[k]}" for k in MANAGED_KEYS if k in values]
    if not lines:
        if os.path.exists(DROPIN):
            os.remove(DROPIN)
        return
    tmp = f"{DROPIN}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("# Managed by SSH Warden (Decky plugin). Change these in the plugin.\n")
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, DROPIN)


def _listening(port: int) -> bool:
    return bool(run(["ss", "-Hltn", f"sport = :{port}"], check=False).strip())


def update_config(changes: dict[str, str | None]) -> None:
    """Change managed sshd settings (None removes one), validate and apply them.

    Any failure (invalid config, sshd not coming back on the expected port) restores
    the previous drop-in and restarts sshd with it, so a bad value cannot lock us out.
    """
    try:
        with open(DROPIN, encoding="utf-8") as f:
            previous: str | None = f.read()
    except FileNotFoundError:
        previous = None
    values = read_managed()
    for key, value in changes.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = value
    was_running = service_state()["running"]
    _write_dropin(values)
    try:
        run(["sshd", "-t"])
        if was_running:
            run(["systemctl", "restart", UNIT])
            expected = ports(effective_config())
            deadline = time.monotonic() + 5
            while not all(_listening(p) for p in expected):
                if time.monotonic() > deadline:
                    raise CommandError(f"sshd 没有在端口 {expected} 上启动")
                time.sleep(0.2)
    except Exception:
        if previous is None:
            if os.path.exists(DROPIN):
                os.remove(DROPIN)
        else:
            with open(DROPIN, "w", encoding="utf-8") as f:
                f.write(previous)
        if was_running:
            run(["systemctl", "restart", UNIT], check=False)
        raise


def set_password_auth(on: bool) -> None:
    if not on and not has_authorized_keys():
        raise ValueError("还没有配置 SSH 公钥，关闭密码登录后将无法再通过 SSH 登录")
    # "yes" is sshd's default, so turning it back on just drops our override.
    update_config({"PasswordAuthentication": None if on else "no"})


def port_owner(port: int) -> str | None:
    """Name of a non-sshd process already listening on `port`, if any."""
    out = run(["ss", "-Hltnp", f"sport = :{port}"], check=False)
    for m in re.finditer(r'users:\(\("([^"]+)"', out):
        if m.group(1) != "sshd":
            return m.group(1)
    return None


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
