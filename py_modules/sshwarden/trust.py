"""Trusted networks: allow SSH only on networks the user marked as trusted."""
from . import net, settings, sshd
from .errors import UserError
from .net import TRUSTED_ZONE


def _ssh_ports() -> set[int]:
    return set(sshd.ports(sshd.effective_config()))


def _require_firewall() -> None:
    if not net.firewall_running():
        raise UserError("firewall_not_running", "The firewall (firewalld) is not running, so SSH cannot be limited by network")


def is_enabled(data: dict) -> bool:
    return bool(data.get("trusted_mode")) and net.firewall_running() and net.zone_exists(TRUSTED_ZONE)


def set_enabled(on: bool) -> None:
    _require_firewall()
    _switch(on, _ssh_ports())


def remove_all() -> None:
    """Switch trusted mode off and remove every firewall rule the plugin added (for uninstall).

    No SSH port is wanted, so this needs no sshd and works with a config sshd -T rejects.
    """
    _require_firewall()
    _switch(False, set())


def _switch(on: bool, ports: set[int]) -> None:
    data = settings.load()
    known = {n["uuid"] for n in net.saved_networks()}
    if on:
        if not (data.get("trusted_mode") and net.zone_exists(TRUSTED_ZONE)):
            net.create_trusted_zone(data)
        for uuid in data.get("trusted", []):
            if uuid in known:
                net.set_connection_zone(uuid, TRUSTED_ZONE)
        data["trusted_mode"] = True
        net.sync_ssh_firewall(ports, data)
    else:
        # Saved before anything changes, so a repair after an interruption finishes switching
        # off, as the user asked, instead of switching back on (net.out_of_sync() spots it).
        data["trusted_mode"] = False
        settings.save(data)
        net.sync_ssh_firewall(ports, data)
        for uuid in known:
            if net.connection_zone(uuid) == TRUSTED_ZONE:
                net.set_connection_zone(uuid, "")
        net.delete_trusted_zone(data)
    settings.save(data)


def repair_firewall() -> None:
    """Make the firewall match the saved mode again (see net.out_of_sync()).

    Applying that mode again does it: sync_ssh_firewall() adds every recorded rule that is
    still wanted and removes the others, turning trusted mode on recreates a missing zone, and
    turning it off removes a leftover one. The panel shows the same saved mode
    (status.collect()), so it can warn before this blocks SSH on the current network.
    """
    set_enabled(bool(settings.load().get("trusted_mode")))


def set_network_trusted(uuid: str, on: bool) -> None:
    data = settings.load()
    trusted = [u for u in data.get("trusted", []) if u != uuid]
    if on:
        trusted.append(uuid)
    data["trusted"] = trusted
    if is_enabled(data):
        net.set_connection_zone(uuid, TRUSTED_ZONE if on else "")
        # The set of untrusted zones may have changed; re-apply the block rules.
        net.sync_ssh_firewall(_ssh_ports(), data)
    settings.save(data)
