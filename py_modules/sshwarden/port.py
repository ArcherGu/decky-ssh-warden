from . import net, settings, sshd


def set_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("端口需在 1 到 65535 之间")
    owner = sshd.port_owner(port)
    if owner:
        raise ValueError(f"端口 {port} 已被 {owner} 占用")
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
