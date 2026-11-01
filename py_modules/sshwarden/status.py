from . import DECK_USER, account, net, sshd
from .proc import CommandError


def collect() -> dict:
    try:
        config, config_error = sshd.effective_config(), None
    except CommandError as e:
        # A broken sshd config must not hide the rest of the status.
        config, config_error = {}, str(e)
    listen_ports = sshd.ports(config)
    fw = net.firewall_running()
    networks = net.active_networks()
    for n in networks:
        n["zone"] = net.zone_of(n["device"]) if fw else None
        # Reachable from this network unless firewalld blocks every SSH port on it.
        n["ssh_allowed"] = (not fw) or any(net.port_open_in_zone(n["zone"], p) for p in listen_ports)
    return {
        "user": DECK_USER,
        **sshd.service_state(),
        "ports": listen_ports,
        "config_error": config_error,
        "password_auth": config.get("passwordauthentication", ["yes"])[0] == "yes",
        "key_count": account.authorized_key_count(),
        "sessions": sshd.sessions(listen_ports),
        "logins": sshd.login_history(),
        "firewall": fw,
        "networks": networks,
    }
