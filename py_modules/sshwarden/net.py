import json

from .proc import run, split_terse, succeeds

LAN_TYPES = {"802-11-wireless": "wifi", "802-3-ethernet": "ethernet"}


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


def _ipv4_addresses(device: str) -> list[str]:
    try:
        links = json.loads(run(["ip", "-j", "-4", "addr", "show", "dev", device], check=False) or "[]")
    except json.JSONDecodeError:
        return []
    return [a["local"] for link in links for a in link.get("addr_info", []) if a.get("scope") == "global"]


def firewall_running() -> bool:
    return run(["firewall-cmd", "--state"], check=False).strip() == "running"


def zone_of(device: str) -> str:
    zone = run(["firewall-cmd", f"--get-zone-of-interface={device}"], check=False).strip()
    return zone or run(["firewall-cmd", "--get-default-zone"], check=False).strip()


def port_open_in_zone(zone: str, port: int) -> bool:
    """Whether firewalld lets new TCP connections to `port` in through `zone`."""
    if any(_blocks_port(rule, port) for rule in run(["firewall-cmd", f"--zone={zone}", "--list-rich-rules"], check=False).splitlines()):
        return False
    if port == 22 and succeeds(["firewall-cmd", f"--zone={zone}", "--query-service=ssh"]):
        return True
    # --query-port also matches port ranges such as SteamOS's 1024-65535/tcp.
    return succeeds(["firewall-cmd", f"--zone={zone}", f"--query-port={port}/tcp"])


def _blocks_port(rule: str, port: int) -> bool:
    return f'port="{port}"' in rule and 'protocol="tcp"' in rule and (" drop" in rule or " reject" in rule)
