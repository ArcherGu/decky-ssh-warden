import json

from .proc import run, split_terse, succeeds

LAN_TYPES = {"802-11-wireless": "wifi", "802-3-ethernet": "ethernet"}
# firewalld zone for trusted networks: a copy of the default zone that also allows SSH.
TRUSTED_ZONE = "sshwarden"


def active_networks() -> list[dict]:
    """Active Wi-Fi/Ethernet connections with their device and IPv4 addresses."""
    networks = []
    out = run(["nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show", "--active"], check=False)
    for line in out.splitlines():
        name, uuid, ctype, device = split_terse(line)
        if ctype not in LAN_TYPES or not device:
            continue
        networks.append({
            "name": name,
            "uuid": uuid,
            "type": LAN_TYPES[ctype],
            "device": device,
            "addresses": _ipv4_addresses(device),
        })
    return networks


def saved_networks() -> list[dict]:
    """All saved Wi-Fi/Ethernet connections, marking the active ones."""
    active = {n["uuid"] for n in active_networks()}
    networks = []
    for line in run(["nmcli", "-t", "-f", "NAME,UUID,TYPE", "connection", "show"], check=False).splitlines():
        name, uuid, ctype = split_terse(line)
        if ctype in LAN_TYPES:
            networks.append({"name": name, "uuid": uuid, "type": LAN_TYPES[ctype], "active": uuid in active})
    return networks


def connection_zone(uuid: str) -> str:
    return run(["nmcli", "-g", "connection.zone", "connection", "show", uuid], check=False).strip()


def set_connection_zone(uuid: str, zone: str) -> None:
    """Persist the connection's zone ("" = default) and move its live device right away."""
    run(["nmcli", "connection", "modify", uuid, "connection.zone", zone])
    for n in active_networks():
        if n["uuid"] == uuid:
            run(["firewall-cmd", f"--zone={zone or default_zone()}", f"--change-interface={n['device']}"])


def _ipv4_addresses(device: str) -> list[str]:
    try:
        links = json.loads(run(["ip", "-j", "-4", "addr", "show", "dev", device], check=False) or "[]")
    except json.JSONDecodeError:
        return []
    return [a["local"] for link in links for a in link.get("addr_info", []) if a.get("scope") == "global"]


def firewall_running() -> bool:
    return run(["firewall-cmd", "--state"], check=False).strip() == "running"


def default_zone() -> str:
    return run(["firewall-cmd", "--get-default-zone"], check=False).strip()


def zone_of(device: str) -> str:
    return run(["firewall-cmd", f"--get-zone-of-interface={device}"], check=False).strip() or default_zone()


def zone_exists(zone: str) -> bool:
    return zone in run(["firewall-cmd", "--permanent", "--get-zones"], check=False).split()


def _block_rule(port: int) -> str:
    # drop rather than reject: on an untrusted network the port should look like nothing is there.
    return f'rule port port="{port}" protocol="tcp" drop'


def _rule_blocks(rule: str, port: int) -> bool:
    return f'port="{port}"' in rule and 'protocol="tcp"' in rule and (" drop" in rule or " reject" in rule)


def _blocked(zone: str, port: int) -> bool:
    rules = run(["firewall-cmd", f"--zone={zone}", "--list-rich-rules"], check=False).splitlines()
    return any(_rule_blocks(r, port) for r in rules)


def zones_snapshot() -> dict[str, dict]:
    """Runtime state of every zone from one `firewall-cmd --list-all-zones` call.

    Each firewall-cmd run costs ~0.3s on the Deck, so the frequently polled status
    reads everything at once instead of querying zone by zone.
    """
    zones: dict[str, dict] = {}
    zone: dict | None = None
    for line in run(["firewall-cmd", "--list-all-zones"], check=False).splitlines():
        if not line.strip():
            continue
        if line.startswith("\t"):  # continuation lines under "rich rules:"
            if zone is not None:
                zone["rich_rules"].append(line.strip())
        elif not line.startswith(" "):  # "public (default, active)"
            name, _, flags = line.partition(" ")
            zone = zones[name] = {
                "default": "default" in flags,
                "interfaces": [],
                "services": [],
                "ports": [],
                "rich_rules": [],
            }
        elif zone is not None:
            key, _, value = line.strip().partition(":")
            if key in ("interfaces", "services", "ports"):
                zone[key] = value.split()
    return zones


def zone_admits(zone: dict, port: int) -> bool:
    """port_open_in_zone() computed from a zones_snapshot() entry."""
    if any(_rule_blocks(r, port) for r in zone["rich_rules"]):
        return False
    if port == 22 and "ssh" in zone["services"]:
        return True
    for spec in zone["ports"]:
        span, _, proto = spec.partition("/")
        low, _, high = span.partition("-")
        if proto == "tcp" and int(low) <= port <= int(high or low):
            return True
    return False


def _port_allowed(zone: str, port: int) -> bool:
    """Whether a service/port rule of `zone` admits `port` (block rules not considered)."""
    if port == 22 and succeeds(["firewall-cmd", f"--zone={zone}", "--query-service=ssh"]):
        return True
    # --query-port also matches port ranges such as SteamOS's 1024-65535/tcp.
    return succeeds(["firewall-cmd", f"--zone={zone}", f"--query-port={port}/tcp"])


def port_open_in_zone(zone: str, port: int) -> bool:
    """Whether firewalld lets new TCP connections to `port` in through `zone`."""
    return not _blocked(zone, port) and _port_allowed(zone, port)


def _firewall(zone: str, arg: str, check: bool = True) -> None:
    """Apply a zone change both now (runtime) and across reboots (permanent)."""
    run(["firewall-cmd", f"--zone={zone}", arg], check=check)
    run(["firewall-cmd", "--permanent", f"--zone={zone}", arg], check=check)


def lan_zones() -> set[str]:
    """The default zone plus the zones of all active Wi-Fi/Ethernet devices."""
    return {default_zone()} | {zone_of(n["device"]) for n in active_networks()}


def reload_firewall() -> None:
    run(["firewall-cmd", "--reload"])
    # Put Wi-Fi/Ethernet devices back in the zone their connection asks for. Other
    # devices (loopback, VPN/proxy tun interfaces) are deliberately left alone.
    for n in active_networks():
        zone = connection_zone(n["uuid"]) or default_zone()
        run(["firewall-cmd", f"--zone={zone}", f"--change-interface={n['device']}"], check=False)


def create_trusted_zone(data: dict) -> None:
    """Create TRUSTED_ZONE as a copy of the default zone's services and ports.

    Ports the plugin itself opened in the default zone are not copied; sync_ssh_firewall()
    adds (and records) whatever the trusted zone needs for SSH. A zone left over from an
    interrupted attempt is replaced, and a failed attempt removes its half-made zone, since
    zone_exists() could not tell it from a finished one.
    """
    delete_trusted_zone(data)
    base = default_zone()
    ours = {f"{e['port']}/tcp" for e in data.get("firewall", []) if e["zone"] == base and e["kind"] == "port"}
    run(["firewall-cmd", "--permanent", f"--new-zone={TRUSTED_ZONE}"])
    try:
        for service in run(["firewall-cmd", "--permanent", f"--zone={base}", "--list-services"]).split():
            run(["firewall-cmd", "--permanent", f"--zone={TRUSTED_ZONE}", f"--add-service={service}"])
        for port in run(["firewall-cmd", "--permanent", f"--zone={base}", "--list-ports"]).split():
            if port not in ours:
                run(["firewall-cmd", "--permanent", f"--zone={TRUSTED_ZONE}", f"--add-port={port}"])
        reload_firewall()
    except Exception:
        run(["firewall-cmd", "--permanent", f"--delete-zone={TRUSTED_ZONE}"], check=False)
        run(["firewall-cmd", "--reload"], check=False)
        raise


def delete_trusted_zone(data: dict) -> None:
    """Delete TRUSTED_ZONE if it exists, and forget the rules recorded for it.

    Those rules went away with the zone. Keeping their records would make a new zone look
    as if it already had them, so SSH on a custom port would stay closed there.
    """
    if zone_exists(TRUSTED_ZONE):
        run(["firewall-cmd", "--permanent", f"--delete-zone={TRUSTED_ZONE}"])
        reload_firewall()
    data["firewall"] = [e for e in data.get("firewall", []) if e["zone"] != TRUSTED_ZONE]


def _apply(entry: dict, add: bool) -> None:
    verb = "add" if add else "remove"
    if entry["kind"] == "port":
        arg = f"--{verb}-port={entry['port']}/tcp"
    else:
        arg = f"--{verb}-rich-rule={_block_rule(entry['port'])}"
    _firewall(entry["zone"], arg, check=add)


def sync_ssh_firewall(ports: set[int], data: dict) -> None:
    """Make firewalld match what SSH on `ports` needs.

    Normal mode: open the ports in every LAN zone that would block them.
    Trusted mode: open them in TRUSTED_ZONE and drop them in every other LAN zone.
    Every rule we add is recorded in data["firewall"] so it can be removed later.
    """
    if not firewall_running():
        return
    recorded: list[dict] = data.setdefault("firewall", [])
    trusted_mode = data.get("trusted_mode", False)
    zones = lan_zones()

    wanted: list[dict] = []
    for zone in ({TRUSTED_ZONE} if trusted_mode else zones):
        for port in ports:
            entry = {"zone": zone, "kind": "port", "port": port}
            if entry in recorded or not _port_allowed(zone, port):
                wanted.append(entry)
    if trusted_mode:
        wanted += [{"zone": z, "kind": "block", "port": p} for z in zones - {TRUSTED_ZONE} for p in ports]

    # Add before removing, so SSH is never closed where it is meant to stay open.
    for entry in wanted:
        if entry not in recorded:
            _apply(entry, add=True)
            recorded.append(entry)
    for entry in list(recorded):
        if entry not in wanted:
            _apply(entry, add=False)
            recorded.remove(entry)
