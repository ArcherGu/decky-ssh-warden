"""Undo everything the plugin changed on the system (used when it is uninstalled)."""
import os

from . import net, settings, sshd, trust


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
