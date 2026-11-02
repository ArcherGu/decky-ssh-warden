"""Shared test helpers: real temporary directories and a fake firewalld + NetworkManager."""
import copy
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from sshwarden import lock, settings
from sshwarden.proc import CommandError


class TempDirTest(unittest.TestCase):
    """Gives each test a temporary directory, its own settings.json and its own lock file."""

    def setUp(self):
        # realpath: safefile refuses symlinked path components, and on macOS /var is one.
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        settings_dir = os.path.join(self.tmp, "settings")
        os.mkdir(settings_dir)
        self.patch(settings, "_dir", settings_dir)
        self.patch(lock, "PATH", os.path.join(self.tmp, "lock"))

    def patch(self, target, attribute, value):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def path(self, *parts: str) -> str:
        return os.path.join(self.tmp, *parts)


def _covers(specs: set[str], port: int, proto: str = "tcp") -> bool:
    for spec in specs:
        span, _, p = spec.partition("/")
        low, _, high = span.partition("-")
        if p == proto and int(low) <= port <= int(high or low):
            return True
    return False


class FakeNetwork:
    """Just enough of firewall-cmd, nmcli and ip for net.py and trust.py.

    Zones are kept twice, like firewalld: `permanent` and `runtime` (rebuilt by --reload).
    `connections` are NetworkManager connections; active ones have a device.
    """

    def __init__(self):
        public = {"services": {"ssh", "dhcpv6-client"}, "ports": {"1024-65535/tcp", "1024-65535/udp"}, "rich": set()}
        self.permanent = {"public": public, "home": copy.deepcopy(public)}
        self.runtime = copy.deepcopy(self.permanent)
        self.default = "public"
        self.bindings: dict[str, str] = {}  # device -> zone (runtime)
        self.connections = {
            "uuid-home": {"name": "Home", "type": "802-11-wireless", "device": "wlan0", "zone": ""},
            "uuid-cafe": {"name": "Cafe", "type": "802-11-wireless", "device": "", "zone": ""},
            "uuid-vpn": {"name": "tun0", "type": "tun", "device": "tun0", "zone": ""},
        }
        self.fail_on: set[str] = set()  # firewall-cmd arguments that should fail

    # --- what tests look at -------------------------------------------------------------
    def zone_of(self, device: str) -> str:
        return self.bindings.get(device) or self.default

    def has(self, zone: str, kind: str, value: str, permanent: bool | None = None) -> bool:
        """Whether `zone` holds the port/rich rule in both configs (or only the one asked for)."""
        configs = [self.permanent, self.runtime] if permanent is None else [self.permanent if permanent else self.runtime]
        return all(zone in c and value in c[zone][kind] for c in configs)

    # --- the commands -------------------------------------------------------------------
    def run(self, args, *, input=None, check=True, timeout=30):
        try:
            return self._dispatch(list(args))
        except CommandError:
            if check:
                raise
            return ""

    def succeeds(self, args, *, input=None, timeout=30):
        args = list(args)
        zone = self._opt(args, "--zone") or self.default
        config = self.permanent if "--permanent" in args else self.runtime
        if zone not in config:
            return False
        if service := self._opt(args, "--query-service"):
            return service in config[zone]["services"]
        if port := self._opt(args, "--query-port"):
            number, _, proto = port.partition("/")
            return _covers(config[zone]["ports"], int(number), proto)
        raise AssertionError(f"unexpected succeeds() call: {args}")

    @staticmethod
    def _opt(args, name):
        for a in args:
            if a.startswith(name + "="):
                return a.split("=", 1)[1]
        return None

    def _fail(self, args):
        raise CommandError(" ".join(args), "fake failure")

    def _dispatch(self, args):
        tool = args[0]
        if tool == "nmcli":
            return self._nmcli(args)
        if tool == "ip":
            return json.dumps([{"addr_info": [{"local": "192.168.1.5", "scope": "global"}]}])
        if tool == "firewall-cmd":
            if any(a in self.fail_on for a in args):
                self._fail(args)
            return self._firewall(args)
        raise AssertionError(f"unexpected command: {args}")

    def _list_all_zones(self):
        """The runtime zones in firewall-cmd's --list-all-zones layout."""
        lines = []
        for name, z in sorted(self.runtime.items()):
            devices = sorted(d for d in self.bindings if self.zone_of(d) == name)
            flags = (["default"] if name == self.default else []) + (["active"] if devices else [])
            lines += [
                f"{name} ({', '.join(flags)})" if flags else name,
                "  target: default",
                f"  interfaces: {' '.join(devices)}",
                f"  services: {' '.join(sorted(z['services']))}",
                f"  ports: {' '.join(sorted(z['ports']))}",
                "  rich rules: ",
                *(f"\t{rule}" for rule in sorted(z["rich"])),
                "",
            ]
        return "\n".join(lines)

    def _nmcli(self, args):
        if args[:3] == ["nmcli", "-t", "-f"]:
            fields, active = args[3].split(","), "--active" in args
            rows = []
            for uuid, c in self.connections.items():
                if active and not c["device"]:
                    continue
                values = {"NAME": c["name"], "UUID": uuid, "TYPE": c["type"], "DEVICE": c["device"]}
                rows.append(":".join(values[f] for f in fields))
            return "\n".join(rows) + "\n"
        if args[:3] == ["nmcli", "-g", "connection.zone"]:
            return self.connections[args[-1]]["zone"] + "\n"
        if args[:3] == ["nmcli", "connection", "modify"]:
            self.connections[args[3]]["zone"] = args[5]
            return ""
        raise AssertionError(f"unexpected nmcli call: {args}")

    def _firewall(self, args):
        permanent = "--permanent" in args
        config = self.permanent if permanent else self.runtime
        zone = self._opt(args, "--zone") or self.default
        if "--state" in args:
            return "running\n"
        if "--get-default-zone" in args:
            return self.default + "\n"
        if device := self._opt(args, "--get-zone-of-interface"):
            if device not in self.bindings:
                self._fail(args)  # firewall-cmd: "no zone"
            return self.bindings[device] + "\n"
        if "--list-all-zones" in args:
            return self._list_all_zones()
        if "--get-zones" in args:
            return " ".join(sorted(config)) + "\n"
        if "--reload" in args:
            self.runtime = copy.deepcopy(self.permanent)
            self.bindings = {}  # the worst case: devices must be bound again
            return ""
        if new := self._opt(args, "--new-zone"):
            if new in self.permanent:
                self._fail(args)
            self.permanent[new] = {"services": set(), "ports": set(), "rich": set()}
            return ""
        if old := self._opt(args, "--delete-zone"):
            if old not in self.permanent:
                self._fail(args)
            del self.permanent[old]
            return ""
        if device := self._opt(args, "--change-interface"):
            if zone not in self.runtime:
                self._fail(args)
            self.bindings[device] = zone
            return ""
        if zone not in config:
            self._fail(args)
        z = config[zone]
        if "--list-rich-rules" in args:
            return "\n".join(sorted(z["rich"])) + "\n"
        if "--list-services" in args:
            return " ".join(sorted(z["services"])) + "\n"
        if "--list-ports" in args:
            return " ".join(sorted(z["ports"])) + "\n"
        for option, kind in (("port", "ports"), ("rich-rule", "rich"), ("service", "services")):
            if value := self._opt(args, f"--add-{option}"):
                z[kind].add(value)  # adding an existing rule is fine (ALREADY_ENABLED)
                return ""
            if value := self._opt(args, f"--remove-{option}"):
                z[kind].discard(value)
                return ""
        raise AssertionError(f"unexpected firewall-cmd call: {args}")
