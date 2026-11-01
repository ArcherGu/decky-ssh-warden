from . import net, settings, sshd
from .errors import UserError


def set_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise UserError("port_range", "The port must be between 1 and 65535")
    owner = sshd.port_owner(port)
    if owner:
        raise UserError("port_in_use", "Port {port} is already used by {owner}", port=port, owner=owner)
    old_ports = set(sshd.ports(sshd.effective_config()))

    data = settings.load()
    # Prepare the firewall for both ports first, so the new one is never blocked while sshd moves.
    net.sync_ssh_firewall(old_ports | {port}, data)
    settings.save(data)
    try:
        sshd.update_config({"Port": None if port == sshd.DEFAULT_PORT else str(port)})
    except Exception:
        net.sync_ssh_firewall(old_ports, data)
        settings.save(data)
        raise
    net.sync_ssh_firewall({port}, data)
    settings.save(data)
