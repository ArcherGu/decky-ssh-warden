from . import net, settings, sshd


def set_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("端口需在 1 到 65535 之间")
    owner = sshd.port_owner(port)
    if owner:
        raise ValueError(f"端口 {port} 已被 {owner} 占用")
    old_ports = set(sshd.ports(sshd.effective_config()))

    data = settings.load()
    # Open the firewall first so the new port is never blocked while sshd moves over.
    net.allow_ssh_port(port, data)
    settings.save(data)
    try:
        sshd.update_config({"Port": None if port == sshd.DEFAULT_PORT else str(port)})
    except Exception:
        net.close_ssh_ports(data, keep=old_ports)
        settings.save(data)
        raise
    net.close_ssh_ports(data, keep={port})
    settings.save(data)
