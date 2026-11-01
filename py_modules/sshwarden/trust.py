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
    data = settings.load()
    known = {n["uuid"] for n in net.saved_networks()}
    if on:
        if not net.zone_exists(TRUSTED_ZONE):
            net.create_trusted_zone(data)
        for uuid in data.get("trusted", []):
            if uuid in known:
                net.set_connection_zone(uuid, TRUSTED_ZONE)
        data["trusted_mode"] = True
        net.sync_ssh_firewall(_ssh_ports(), data)
    else:
        data["trusted_mode"] = False
        net.sync_ssh_firewall(_ssh_ports(), data)
        for uuid in known:
            if net.connection_zone(uuid) == TRUSTED_ZONE:
                net.set_connection_zone(uuid, "")
        if net.zone_exists(TRUSTED_ZONE):
            net.delete_trusted_zone()
    settings.save(data)


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
