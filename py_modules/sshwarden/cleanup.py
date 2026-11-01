"""Undo everything the plugin changed on the system, and put the user's settings back after an update.

Decky runs a plugin's _uninstall before every update or reinstall, not only when it is removed,
so an update looks like uninstall + install. The plugin's settings directory survives both:
uninstall() notes the user's SSH settings there before reverting them, and the next load
re-applies them with restore_after_update() if it comes within REINSTALL_WINDOW.

Decky also SIGKILLs the plugin process 5 s after asking it to stop and then deletes the plugin
directory, while turning trusted mode off alone takes about that long. So _uninstall only calls
start_uninstall(), which copies this package to RUN_DIR and runs uninstall() from there in a
transient systemd service that outlives the plugin.
"""
import math
import os
import shutil
import time

from . import lock, net, port, settings, sshd, trust
from .proc import run

REINSTALL_WINDOW = 10 * 60
NOTE = "before_uninstall"
UNINSTALL_UNIT = "ssh-warden-uninstall"
RUN_DIR = "/run/ssh-warden-uninstall"  # /run is writable by root only


def revert_all() -> None:
    sshd.cancel_autooff()
    data = settings.load()
    if net.firewall_running():
        if trust.is_enabled(data):
            trust.set_enabled(False)
            data = settings.load()
        # Remove any remaining rules we added (e.g. a port opened for a custom SSH port).
        data["trusted_mode"] = False
        net.sync_ssh_firewall(set(), data)
        settings.save(data)
    # Back to the system's sshd defaults (port 22, password login allowed).
    if os.path.exists(sshd.DROPIN):
        sshd.update_config({key: None for key in sshd.MANAGED_KEYS})


def uninstall() -> None:
    """Note the user's settings, then revert_all()."""
    with lock.changes():
        _note_settings()
        revert_all()


def _note_settings() -> None:
    data = settings.load()
    managed = sshd.read_managed()
    data[NOTE] = {
        "at": time.time(),
        "port": managed.get("Port"),
        "password_auth": managed.get("PasswordAuthentication") != "no",
        "trusted_mode": trust.is_enabled(data),
        "autooff_at": sshd.autooff_deadline(),
    }
    settings.save(data)


def start_uninstall(settings_dir: str) -> None:
    """Run uninstall() in the background, independent of the plugin process and its files."""
    shutil.rmtree(RUN_DIR, ignore_errors=True)
    os.makedirs(RUN_DIR, 0o700)
    package = os.path.dirname(os.path.abspath(__file__))
    shutil.copytree(package, os.path.join(RUN_DIR, "sshwarden"), ignore=shutil.ignore_patterns("__pycache__"))
    run(["systemctl", "reset-failed", f"{UNINSTALL_UNIT}.service"], check=False)
    run([
        "systemd-run",
        f"--unit={UNINSTALL_UNIT}",
        "--collect",
        "--description=SSH Warden: undo the plugin's system changes",
        f"--setenv=PYTHONPATH={RUN_DIR}",
        f"--setenv=SSH_WARDEN_SETTINGS_DIR={settings_dir}",
        f"--property=ExecStopPost=/usr/bin/rm -rf {RUN_DIR}",
        "/usr/bin/python3", "-B", "-m", "sshwarden", "uninstall",
    ])


def _wait_for_uninstall(timeout: float = 120) -> None:
    """Wait until a background uninstall (see start_uninstall()) has finished."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = run(["systemctl", "is-active", f"{UNINSTALL_UNIT}.service"], check=False).strip()
        if state not in ("active", "activating", "deactivating"):
            return
        time.sleep(0.5)


def restore_after_update() -> dict | None:
    """Re-apply what uninstall() noted if the plugin is back within REINSTALL_WINDOW.

    Returns {"restored": [...], "failed": {step: error}} for the log, or None when there was
    nothing to restore. Each step runs on its own, so one failure does not keep the others
    reverted. Decky starts a freshly installed plugin twice and stops the first process within
    seconds, so the note is only dropped once every step has run; the steps are idempotent and
    the next process simply repeats them.
    """
    # After an update the old version's uninstall may still be running (it holds the lock too,
    # but might not have taken it yet).
    _wait_for_uninstall()
    with lock.changes():
        note = settings.load().get(NOTE)
        if note is None:
            return None
        result = None
        if time.time() - note["at"] <= REINSTALL_WINDOW:
            result = _restore(note)
        data = settings.load()
        data.pop(NOTE, None)
        settings.save(data)
        return result


def _restore(note: dict) -> dict:
    steps = []
    if note["port"]:
        steps.append(("port", lambda: port.set_port(int(note["port"]))))
    if note["trusted_mode"]:
        steps.append(("trusted_mode", lambda: trust.set_enabled(True)))
    if not note["password_auth"]:
        steps.append(("password_auth", lambda: sshd.set_password_auth(False)))
    if note["autooff_at"] and note["autooff_at"] > time.time():
        minutes = math.ceil((note["autooff_at"] - time.time()) / 60)
        steps.append(("autooff", lambda: sshd.schedule_autooff(minutes)))

    result: dict = {"restored": [], "failed": {}}
    for name, step in steps:
        try:
            step()
            result["restored"].append(name)
        except Exception as e:
            result["failed"][name] = str(e)
    return result
