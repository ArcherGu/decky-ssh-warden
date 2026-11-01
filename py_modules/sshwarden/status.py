from . import DECK_USER, account, net, settings, sshd
from .proc import CommandError


def collect() -> dict:
    try:
        config, config_error = sshd.effective_config(), None
    except CommandError as e:
        # A broken sshd config must not hide the rest of the status.
        config, config_error = {}, e.params["detail"]
    listen_ports = sshd.ports(config)

    fw = net.firewall_running()
    zones = net.zones_snapshot() if fw else {}
    default_zone = next((name for name, z in zones.items() if z["default"]), None)
    zone_of_device = {dev: name for name, z in zones.items() for dev in z["interfaces"]}

    data = settings.load()
    trusted_ids = set(data.get("trusted", []))
    networks = net.active_networks()
    for n in networks:
        zone = zone_of_device.get(n["device"], default_zone)
        n["zone"] = zone
        n["trusted"] = n["uuid"] in trusted_ids
        # Reachable from this network unless firewalld blocks every SSH port on it.
        n["ssh_allowed"] = (not fw) or (zone in zones and any(net.zone_admits(zones[zone], p) for p in listen_ports))

    return {
        "user": DECK_USER,
        **sshd.service_state(),
        "autooff_at": sshd.autooff_deadline(),
        "ports": listen_ports,
        "config_error": config_error,
        "password_auth": config.get("passwordauthentication", ["yes"])[0] == "yes",
        "key_count": account.authorized_key_count(),
        "sessions": sshd.sessions(listen_ports),
        "logins": sshd.login_history(),
        "firewall": fw,
        "networks": networks,
        # Same rule as trust.is_enabled(), from the snapshot instead of extra firewall-cmd calls.
        "trusted_mode": bool(data.get("trusted_mode")) and net.TRUSTED_ZONE in zones,
        "saved_networks": [{**n, "trusted": n["uuid"] in trusted_ids} for n in net.saved_networks()],
    }
