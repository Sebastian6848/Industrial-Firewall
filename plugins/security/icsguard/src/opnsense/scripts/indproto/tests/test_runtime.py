import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import generate_rules
import runtime


def configuration(enabled):
    return ET.fromstring(
        "<IndProto><general><enabled>%d</enabled><default_action>block</default_action></general>"
        "<rules/></IndProto>" % enabled
    )


class ApplyManagerTest(unittest.TestCase):
    def test_dnp3_fragment_registers_detection_port(self):
        fragment = runtime.ApplyManager().fragment({'dnp3'})
        self.assertIn('dp: "[20000]"', fragment)

    def test_mqtt_fragment_includes_custom_nclink_port(self):
        node = ET.fromstring('<IndProto><rules><rule><protocol>nclink</protocol><dst_port>1884</dst_port></rule></rules></IndProto>')
        fragment = runtime.ApplyManager().fragment({'nclink'}, node)
        self.assertIn('dp: "[1883,1884]"', fragment)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.fragment = root / "conf.d" / "indproto.yaml"
        self.rules = root / "indproto" / "indproto.rules"
        self.cron = root / "indproto.cron"
        self.path_patches = [
            patch.object(runtime, "FRAGMENT_PATH", self.fragment),
            patch.object(generate_rules, "RULES_PATH", self.rules),
            patch.object(generate_rules, "CRON_PATH", self.cron),
        ]
        for item in self.path_patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.path_patches):
            item.stop()
        self.temporary.cleanup()

    def manager(self, running, native_enabled=True):
        manager = runtime.ApplyManager()
        manager.ids = MagicMock()
        manager.ids.enabled.return_value = native_enabled
        manager.service = MagicMock()
        manager.service.is_running.return_value = running
        manager.service.start.return_value = runtime.ok({"transition": "start"})
        manager.service.stop.return_value = runtime.ok({"transition": "stop"})
        manager.service.restart.return_value = runtime.ok({"transition": "restart"})
        manager.service.signal_reload.return_value = runtime.ok({"transition": "reload"})
        manager.validate = MagicMock()
        return manager

    def test_rule_only_change_uses_one_reload(self):
        manager = self.manager(running=True)
        fragment = manager.fragment({"dnp3"})
        runtime.atomic_write(self.fragment, fragment)

        with patch.object(generate_rules, "load_config", return_value=configuration(True)), \
                patch.object(generate_rules, "render_rules", return_value=(["rule"], {"dnp3"}, False)), \
                patch.object(generate_rules, "validate_unique_sids"):
            result = manager.apply()

        self.assertEqual(result["status"], "ok")
        manager.service.signal_reload.assert_called_once_with()
        manager.service.start.assert_not_called()
        manager.service.restart.assert_not_called()
        manager.service.stop.assert_not_called()

    def test_disabling_preserves_native_ids_service(self):
        manager = self.manager(running=True, native_enabled=True)
        runtime.atomic_write(self.fragment, manager.fragment({"dnp3"}))

        with patch.object(generate_rules, "load_config", return_value=configuration(False)):
            result = manager.apply()

        self.assertEqual(result["status"], "ok")
        manager.service.restart.assert_called_once_with()
        manager.service.stop.assert_not_called()

    def test_disabling_stops_non_native_service(self):
        manager = self.manager(running=True, native_enabled=False)
        runtime.atomic_write(self.fragment, manager.fragment({"dnp3"}))

        with patch.object(generate_rules, "load_config", return_value=configuration(False)):
            result = manager.apply()

        self.assertEqual(result["status"], "ok")
        manager.service.stop.assert_called_once_with()
        manager.service.restart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
