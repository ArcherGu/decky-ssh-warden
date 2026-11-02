"""Firewall bookkeeping and trusted mode, against FakeNetwork."""
from unittest import mock

from helpers import FakeNetwork, TempDirTest
from sshwarden import account, cleanup, keys, net, settings, sshd, status, trust
from sshwarden.proc import CommandError

DROP_22 = 'rule port port="22" protocol="tcp" drop'
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


class OutOfSyncTest(NetTest):
    """Recorded rules firewalld lacks, e.g. the plugin was killed between recording and adding."""

    def missing(self):
        return net.out_of_sync(settings.load(), net.zones_snapshot())

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
        self.assertEqual(self.missing(), [{"zone": net.TRUSTED_ZONE, "kind": "zone"},
                                          {"zone": net.TRUSTED_ZONE, "kind": "port", "port": 222}])
        trust.repair_firewall()
        self.assertTrue(self.fw.has(net.TRUSTED_ZONE, "ports", "222/tcp"))
        self.assertEqual(self.fw.zone_of("wlan0"), net.TRUSTED_ZONE)
        self.assertEqual(self.missing(), [])


def killed_in(name, after=False):
    """Patch net.<name> to stop the plugin there, as Decky's SIGKILL would (before or after it runs)."""
    real = getattr(net, name)

    def killed(*args):
        if after:
            real(*args)
        raise KeyboardInterrupt

    return mock.patch.object(net, name, killed)


class InterruptedSwitchTest(NetTest):
    """The plugin is killed while switching trusted mode. Only "Cafe" is trusted; the Deck is on "Home"."""

    def setUp(self):
        super().setUp()
        trust.set_network_trusted("uuid-cafe", True)
        trust.set_enabled(True)
        self.assertTrue(self.fw.has("public", "rich", DROP_22))

    def switch(self, on, killed):
        with killed, self.assertRaises(KeyboardInterrupt):
            trust.set_enabled(on)

    def unsynced(self):
        return net.out_of_sync(settings.load(), net.zones_snapshot())

    def panel(self):
        self.patch(sshd, "effective_config", lambda: {})
        self.patch(sshd, "service_state", lambda: {"running": True, "autostart": True})
        self.patch(sshd, "autooff_deadline", lambda: None)
        self.patch(sshd, "sessions", lambda ports: [])
        self.patch(sshd, "login_history", lambda: {"recent": [], "failed": 0})
        self.patch(sshd, "accepts_keys", lambda config: False)
        self.patch(keys, "list_keys", lambda: [])
        self.patch(account, "password_set", lambda: True)
        result = status.collect()
        home = next(n for n in result["networks"] if n["uuid"] == "uuid-home")
        return result["trusted_mode"], result["firewall_out_of_sync"], home["trusted"], home["ssh_allowed"]

    def assert_off(self):
        self.assertFalse(self.fw.has("public", "rich", DROP_22))
        self.assertNotIn(net.TRUSTED_ZONE, self.fw.permanent)
        self.assertEqual(self.fw.connections["uuid-cafe"]["zone"], "")
        self.assertEqual(self.records(), [])
        self.assertEqual(self.unsynced(), [])

    def test_off_killed_before_its_last_save_is_finished_not_undone(self):
        self.switch(False, killed_in("delete_trusted_zone", after=True))
        self.assertFalse(self.fw.has("public", "rich", DROP_22))
        # The panel shows trusted mode off and offers a repair, which needs no confirmation...
        self.assertEqual(self.panel(), (False, 1, False, True))
        self.assertEqual(self.unsynced(), [{"zone": "public", "kind": "block", "port": 22}])
        # ...because it finishes switching off instead of blocking SSH on Home again.
        trust.repair_firewall()
        self.assert_off()

    def test_off_killed_before_anything_changed_is_noticed(self):
        self.switch(False, killed_in("sync_ssh_firewall"))
        self.assertTrue(self.fw.has("public", "rich", DROP_22))
        self.assertFalse(settings.load()["trusted_mode"])
        # No recorded rule is missing, yet the zone and the drop rule should not be there.
        self.assertEqual(self.unsynced(), [{"zone": net.TRUSTED_ZONE, "kind": "zone"},
                                           {"zone": "public", "kind": "block", "port": 22}])
        trust.repair_firewall()
        self.assert_off()

    def test_on_killed_before_it_was_saved_is_undone(self):
        trust.set_enabled(False)
        self.switch(True, killed_in("sync_ssh_firewall"))
        self.assertIn(net.TRUSTED_ZONE, self.fw.permanent)
        self.assertEqual(self.unsynced(), [{"zone": net.TRUSTED_ZONE, "kind": "zone"}])
        trust.repair_firewall()
        self.assert_off()

    def test_the_panel_confirms_when_the_repair_blocks_the_current_network(self):
        self.fw.runtime["public"]["rich"].discard(DROP_22)
        # Trusted mode is on, Home is untrusted and open: StatusSection asks before repairing.
        self.assertEqual(self.panel(), (True, 1, False, True))
        trust.repair_firewall()
        self.assertTrue(self.fw.has("public", "rich", DROP_22))
        self.assertEqual(self.panel(), (True, 0, False, False))

    def test_a_lost_zone_is_shown_with_the_saved_mode(self):
        for config in (self.fw.permanent, self.fw.runtime):
            del config[net.TRUSTED_ZONE]
        # Still on, as the user left it; the repair recreates the zone.
        self.assertEqual(self.panel()[:2], (True, 1))
        trust.repair_firewall()
        self.assertEqual(self.fw.connections["uuid-cafe"]["zone"], net.TRUSTED_ZONE)
        self.assertEqual(self.unsynced(), [])


class RevertAllTest(NetTest):
    def setUp(self):
        super().setUp()
        self.patch(sshd, "cancel_autooff", lambda: None)
        self.patch(sshd, "DROPIN", self.path("no-dropin"))

    def test_removes_the_zone_an_interrupted_switch_off_left(self):
        trust.set_network_trusted("uuid-cafe", True)
        trust.set_enabled(True)
        with killed_in("sync_ssh_firewall"), self.assertRaises(KeyboardInterrupt):
            trust.set_enabled(False)
        cleanup.revert_all()
        self.assertNotIn(net.TRUSTED_ZONE, self.fw.permanent)
        self.assertEqual(self.fw.connections["uuid-cafe"]["zone"], "")
        for config in (self.fw.permanent, self.fw.runtime):
            self.assertEqual(config["public"]["rich"], set())
        self.assertEqual(self.records(), [])

    def test_needs_no_sshd(self):
        # E.g. the user broke sshd_config: sshd -T fails, yet every rule must still go.
        self.ports = {222}
        self.sync({222})
        trust.set_network_trusted("uuid-cafe", True)
        trust.set_enabled(True)

        def broken():
            raise CommandError("sshd -T", "/etc/ssh/sshd_config line 3: Bad configuration option")

        self.patch(trust, "_ssh_ports", broken)
        cleanup.revert_all()
        self.assertNotIn(net.TRUSTED_ZONE, self.fw.permanent)
        for config in (self.fw.permanent, self.fw.runtime):
            self.assertNotIn("222/tcp", config["public"]["ports"])
            self.assertEqual(config["public"]["rich"], set())
        self.assertEqual(self.records(), [])

    def test_removes_every_rule_zone_and_record(self):
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
