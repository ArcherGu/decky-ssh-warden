"""Undo everything the plugin changed on the system, and put the user's settings back after an update.

Decky runs a plugin's _uninstall before every update or reinstall, not only when it is removed,
so an update looks like uninstall + install. The plugin's settings directory survives both:
uninstall() notes the user's SSH settings there before reverting them, and the next load
re-applies them with restore_after_update() if it comes within REINSTALL_WINDOW.
"""
import math
import os
import time

from . import net, port, settings, sshd, trust

REINSTALL_WINDOW = 10 * 60
NOTE = "before_uninstall"


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
    revert_all()


def restore_after_update() -> dict | None:
    """Re-apply what uninstall() noted if the plugin is back within REINSTALL_WINDOW.

    Returns {"restored": [...], "failed": {step: error}} for the log, or None when there was
    nothing to restore. Each step runs on its own, so one failure does not keep the others
    reverted.
    """
    data = settings.load()
    note = data.pop(NOTE, None)
    if note is None:
        return None
    settings.save(data)
    if time.time() - note["at"] > REINSTALL_WINDOW:
        return None

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
