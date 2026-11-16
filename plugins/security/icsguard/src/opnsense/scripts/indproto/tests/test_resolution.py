import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from resolution import PolicyValueResolver


CONFIG = """<opnsense>
  <interfaces>
    <lan><if>igc0</if><ipaddr>192.168.10.1</ipaddr><subnet>24</subnet></lan>
    <wan><if>igc1</if><ipaddr>dhcp</ipaddr></wan>
  </interfaces>
  <OPNsense><Firewall><Alias><aliases>
    <alias><name>plc_hosts</name><type>host</type><content>192.168.10.20\n192.168.10.21</content></alias>
    <alias><name>industrial_ports</name><type>port</type><content>502\n20000-20010</content></alias>
  </aliases></Alias></Firewall></OPNsense>
</opnsense>"""


class PolicyValueResolverTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.config = Path(self.temporary.name) / "config.xml"
        self.config.write_text(CONFIG)
        self.resolver = PolicyValueResolver(self.config)

    def tearDown(self):
        self.temporary.cleanup()

    def test_interface_network_and_address(self):
        self.assertEqual(self.resolver.address("lan"), "192.168.10.0/24")
        self.assertEqual(self.resolver.address("lanip"), "192.168.10.1")

    def test_address_alias_expands_for_suricata(self):
        self.assertEqual(self.resolver.address("plc_hosts"), "[192.168.10.20,192.168.10.21]")

    def test_port_values_and_alias(self):
        self.assertEqual(self.resolver.port(""), "any")
        self.assertEqual(self.resolver.port("1000-2000"), "1000:2000")
        self.assertEqual(self.resolver.port("industrial_ports"), "[502,20000:20010]")

    @patch("resolution.subprocess.run")
    def test_dynamic_interface_uses_live_network(self, run):
        run.return_value = MagicMock(
            returncode=0,
            stdout="igc1: flags=...\n\tinet 203.0.113.9/24 broadcast 203.0.113.255\n",
        )
        self.assertEqual(self.resolver.address("wan"), "203.0.113.0/24")
        self.assertEqual(self.resolver.address("wanip"), "203.0.113.9")


if __name__ == "__main__":
    unittest.main()
