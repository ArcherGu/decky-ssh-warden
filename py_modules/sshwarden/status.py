from . import DECK_USER, account, keys, lock, net, settings, sshd
from .errors import UserError
from .proc import CommandError


def collect() -> dict:
    try:
        config, config_error = sshd.effective_config(), None
    except CommandError as e:
        # A broken sshd config must not hide the rest of the status.
        config, config_error = {}, e.params["detail"]
    listen_ports = sshd.ports(config)
    try:
        key_list, keys_unsafe = keys.list_keys(), False
    except UserError:
        # ~/.ssh or authorized_keys is a symlink or not a plain file: say so instead of "no keys".
        key_list, keys_unsafe = [], True

    fw = net.firewall_running()
    # A change records each rule just before adding it, so only compare the records with the
    # firewall while no change runs; this read never waits for one.
    with lock.unless_busy() as idle:
        zones = net.zones_snapshot() if fw else {}
        data = settings.load()
    unsynced = net.out_of_sync(data, zones) if fw and idle else []
    default_zone = next((name for name, z in zones.items() if z["default"]), None)
    zone_of_device = {dev: name for name, z in zones.items() for dev in z["interfaces"]}

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
        "password_set": account.password_set(),
        "keys": key_list,
        "keys_unsafe": keys_unsafe,
        # Whether those keys alone can log in, i.e. password login may be turned off.
        "key_login": bool(key_list) and sshd.accepts_keys(config),
        "sessions": sshd.sessions(listen_ports),
        "logins": sshd.login_history(),
        "firewall": fw,
        # Where the firewall differs from the saved mode; the panel offers to repair it.
        "firewall_out_of_sync": len(unsynced),
        "networks": networks,
        # The saved mode, which trust.repair_firewall() applies: the panel decides from this
        # whether a repair needs confirming. A missing zone shows up in firewall_out_of_sync.
        "trusted_mode": fw and bool(data.get("trusted_mode")),
        "saved_networks": [{**n, "trusted": n["uuid"] in trusted_ids} for n in net.saved_networks()],
    }
