"""Firewall bookkeeping and trusted mode, against FakeNetwork."""
from helpers import FakeNetwork, TempDirTest
from sshwarden import cleanup, net, settings, sshd, trust
from sshwarden.proc import CommandError

DROP_222 = 'rule port port="222" protocol="tcp" drop'


class NetTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.fw = FakeNetwork()
        self.patch(net, "run", self.fw.run)
        self.patch(net, "succeeds", self.fw.succeeds)
        self.ports = {22}
        self.patch(trust, "_ssh_ports", lambda: set(self.ports))

    def records(self):
        return settings.load().get("firewall", [])

    def sync(self, ports):
        data = settings.load()
        net.sync_ssh_firewall(ports, data)
        settings.save(data)


class NormalModeTest(NetTest):
    def test_port_in_the_default_range_needs_no_rule(self):
        self.sync({2222})
        self.assertEqual(self.records(), [])

    def test_custom_port_is_opened_recorded_and_removed_again(self):
        self.sync({22, 222})
        self.assertTrue(self.fw.has("public", "ports", "222/tcp"))
        self.assertIn({"zone": "public", "kind": "port", "port": 222}, self.records())
        self.sync({22})
        self.assertFalse(self.fw.has("public", "ports", "222/tcp", permanent=True))
        self.assertFalse(self.fw.has("public", "ports", "222/tcp", permanent=False))
        self.assertEqual(self.records(), [])

    def test_a_recorded_rule_that_went_missing_is_added_again(self):
        self.sync({222})
        for config in (self.fw.permanent, self.fw.runtime):
            config["public"]["ports"].discard("222/tcp")
        self.sync({222})
        self.assertTrue(self.fw.has("public", "ports", "222/tcp"))

    def test_a_rule_is_recorded_before_it_is_added(self):
        # If the process dies while adding, the record must already be on disk.
        def failing_apply(entry, add):
            raise CommandError("firewall-cmd", "killed")
        self.patch(net, "_apply", failing_apply)
        with self.assertRaises(CommandError):
            self.sync({222})
        self.assertIn({"zone": "public", "kind": "port", "port": 222}, self.records())


class TrustedModeTest(NetTest):
    def setUp(self):
        super().setUp()
        trust.set_network_trusted("uuid-home", True)

    def test_on_moves_trusted_networks_and_drops_ssh_elsewhere(self):
        trust.set_enabled(True)
        self.assertEqual(self.fw.connections["uuid-home"]["zone"], net.TRUSTED_ZONE)
        self.assertEqual(self.fw.zone_of("wlan0"), net.TRUSTED_ZONE)
        self.assertEqual(self.fw.permanent[net.TRUSTED_ZONE]["services"], self.fw.permanent["public"]["services"])
        self.assertTrue(self.fw.has("public", "rich", 'rule port port="22" protocol="tcp" drop'))
        # "home" is not in use by any device, so it is left alone.
        self.assertEqual(self.fw.permanent["home"]["rich"], set())
        # VPN devices are not Wi-Fi/Ethernet and stay where they were.
        self.assertNotIn("tun0", self.fw.bindings)

    def test_off_restores_everything(self):
        trust.set_enabled(True)
        trust.set_enabled(False)
        self.assertNotIn(net.TRUSTED_ZONE, self.fw.permanent)
        self.assertEqual(self.fw.connections["uuid-home"]["zone"], "")
        self.assertEqual(self.fw.permanent["public"]["rich"], set())
        self.assertEqual(self.records(), [])

    def test_custom_port_stays_open_after_off_and_on_again(self):
        # Regression: the record of the port opened in the trusted zone survived the zone.
        self.ports = {222}
        self.sync({222})
        trust.set_enabled(True)
        self.assertTrue(self.fw.has(net.TRUSTED_ZONE, "ports", "222/tcp"))
        trust.set_enabled(False)
        trust.set_enabled(True)
        self.assertTrue(self.fw.has(net.TRUSTED_ZONE, "ports", "222/tcp"))
        self.assertTrue(self.fw.has("public", "rich", DROP_222))
        self.assertTrue(all(e["zone"] in self.fw.permanent for e in self.records()))

    def test_stale_records_of_the_trusted_zone_are_dropped_when_it_is_recreated(self):
        self.ports = {222}
        data = settings.load()
        data["firewall"] = [{"zone": net.TRUSTED_ZONE, "kind": "port", "port": 222}]  # left by the old bug
        settings.save(data)
        trust.set_enabled(True)
        self.assertTrue(self.fw.has(net.TRUSTED_ZONE, "ports", "222/tcp"))

    def test_a_half_made_trusted_zone_is_removed(self):
        self.fw.fail_on.add("--add-service=ssh")
        with self.assertRaises(CommandError):
            trust.set_enabled(True)
        self.assertNotIn(net.TRUSTED_ZONE, self.fw.permanent)

    def test_untrusting_the_current_network_moves_it_back(self):
        trust.set_enabled(True)
        trust.set_network_trusted("uuid-home", False)
        self.assertEqual(self.fw.zone_of("wlan0"), "public")
        self.assertEqual(self.fw.connections["uuid-home"]["zone"], "")


class MissingRulesTest(NetTest):
    """Recorded rules firewalld lacks, e.g. the plugin was killed between recording and adding."""

    def missing(self):
        return net.missing_rules(self.records(), net.zones_snapshot())

    def setUp(self):
        super().setUp()
        self.ports = {222}
        trust.set_network_trusted("uuid-home", True)

    def test_a_lost_open_port_is_found_and_repaired(self):
        self.sync({222})
        self.assertEqual(self.missing(), [])
        self.fw.runtime["public"]["ports"].discard("222/tcp")
        self.assertEqual(self.missing(), [{"zone": "public", "kind": "port", "port": 222}])
        trust.repair_firewall()
        self.assertTrue(self.fw.has("public", "ports", "222/tcp"))
        self.assertEqual(self.missing(), [])
        self.assertNotIn(net.TRUSTED_ZONE, self.fw.permanent)

    def test_a_lost_drop_rule_is_found_and_repaired(self):
        trust.set_enabled(True)
        self.assertEqual(self.missing(), [])
        self.fw.runtime["public"]["rich"].discard(DROP_222)
        self.assertEqual(self.missing(), [{"zone": "public", "kind": "block", "port": 222}])
        trust.repair_firewall()
        self.assertTrue(self.fw.has("public", "rich", DROP_222))
        self.assertEqual(self.missing(), [])

    def test_a_lost_trusted_zone_is_recreated(self):
        trust.set_enabled(True)
        for config in (self.fw.permanent, self.fw.runtime):
            del config[net.TRUSTED_ZONE]
        self.assertIn({"zone": net.TRUSTED_ZONE, "kind": "port", "port": 222}, self.missing())
        trust.repair_firewall()
        self.assertTrue(self.fw.has(net.TRUSTED_ZONE, "ports", "222/tcp"))
        self.assertEqual(self.fw.zone_of("wlan0"), net.TRUSTED_ZONE)
        self.assertEqual(self.missing(), [])


class RevertAllTest(NetTest):
    def test_removes_every_rule_zone_and_record(self):
        self.patch(sshd, "cancel_autooff", lambda: None)
        self.patch(sshd, "DROPIN", self.path("no-dropin"))
        self.ports = {222}
        self.sync({222})
        trust.set_network_trusted("uuid-home", True)
        trust.set_enabled(True)
        cleanup.revert_all()
        self.assertNotIn(net.TRUSTED_ZONE, self.fw.permanent)
        for config in (self.fw.permanent, self.fw.runtime):
            self.assertNotIn("222/tcp", config["public"]["ports"])
            self.assertEqual(config["public"]["rich"], set())
        self.assertEqual(self.records(), [])
        self.assertFalse(settings.load()["trusted_mode"])
