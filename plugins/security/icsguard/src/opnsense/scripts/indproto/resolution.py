import ipaddress
import socket
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


class PolicyValueResolver:
    def __init__(self, config_path):
        self.root = None
        self.interfaces = {}
        self.aliases = {}
        path = Path(config_path) if config_path is not None else None
        if path is not None and path.exists():
            self.root = ET.parse(path).getroot()
            self.load_interfaces()
            self.load_aliases()

    def load_interfaces(self):
        interfaces = self.root.find("./interfaces")
        if interfaces is None:
            return
        for node in interfaces:
            self.interfaces[node.tag] = node

    def load_aliases(self):
        for node in self.root.findall(".//aliases/alias"):
            name = self.text(node, "name")
            alias_type = self.text(node, "type")
            if name and alias_type:
                self.aliases[name] = {
                    "type": alias_type,
                    "content": self.text(node, "content").split(),
                }

    def text(self, node, name, default=""):
        found = node.find(name)
        return default if found is None or found.text is None else found.text.strip()

    def interface_values(self, name, address_only=False):
        node = self.interfaces.get(name)
        if node is None:
            raise ValueError("unknown interface network %r" % name)
        values = []
        for family in ("", "v6"):
            address = self.text(node, "ipaddr%s" % family)
            prefix = self.text(node, "subnet%s" % family)
            if not address or address.lower() in ("dhcp", "dhcp6", "track6"):
                continue
            try:
                interface = ipaddress.ip_interface("%s/%s" % (address, prefix)) if prefix else ipaddress.ip_interface(address)
            except ValueError as exc:
                raise ValueError("invalid address configured on interface %s" % name) from exc
            values.append(str(interface.ip if address_only else interface.network))
        if not values:
            physical = self.text(node, "if")
            if physical:
                values = self.runtime_interface_values(physical, address_only)
        if not values:
            raise ValueError("interface %s has no resolvable address or network" % name)
        return values

    def runtime_interface_values(self, interface, address_only):
        try:
            result = subprocess.run(
                ["/sbin/ifconfig", "-f", "inet:cidr", interface],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return []
        if result.returncode != 0:
            return []
        values = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 2 or fields[0] not in ("inet", "inet6"):
                continue
            try:
                configured = ipaddress.ip_interface(fields[1])
            except ValueError:
                continue
            if configured.ip.is_link_local:
                continue
            values.append(str(configured.ip if address_only else configured.network))
        return values

    def address_items(self, value, stack=None):
        value = (value or "").strip()
        if value in ("", "any", "*", "0.0.0.0/0", "::/0"):
            return ["any"]
        if value == "(self)":
            result = []
            for name in self.interfaces:
                try:
                    result.extend(self.interface_values(name, address_only=True))
                except ValueError:
                    continue
            if not result:
                raise ValueError("unable to resolve This Firewall to an address")
            return result
        if value.endswith("ip") and value[:-2] in self.interfaces:
            return self.interface_values(value[:-2], address_only=True)
        if value in self.interfaces:
            return self.interface_values(value)
        if value in self.aliases:
            alias = self.aliases[value]
            if alias["type"] not in ("host", "network"):
                raise ValueError("alias %s is not a host or network alias" % value)
            stack = set() if stack is None else set(stack)
            if value in stack:
                raise ValueError("recursive address alias %s" % value)
            stack.add(value)
            result = []
            for item in alias["content"]:
                result.extend(self.address_items(item, stack))
            if not result:
                raise ValueError("address alias %s is empty" % value)
            return result
        try:
            return [str(ipaddress.ip_network(value, strict=False) if "/" in value else ipaddress.ip_address(value))]
        except ValueError as exc:
            raise ValueError("unable to resolve address or alias %r" % value) from exc

    def address(self, value):
        items = list(dict.fromkeys(self.address_items(value)))
        if "any" in items:
            return "any"
        return items[0] if len(items) == 1 else "[%s]" % ",".join(items)

    def port(self, value, stack=None):
        value = (value or "").strip()
        normalized = value.lower()
        if normalized in ("", "any", "*"):
            return "any"
        if value in self.aliases:
            alias = self.aliases[value]
            if alias["type"] != "port":
                raise ValueError("alias %s is not a port alias" % value)
            stack = set() if stack is None else set(stack)
            if value in stack:
                raise ValueError("recursive port alias %s" % value)
            stack.add(value)
            ports = [self.port(item, stack) for item in alias["content"]]
            if not ports:
                raise ValueError("port alias %s is empty" % value)
            return ports[0] if len(ports) == 1 else "[%s]" % ",".join(ports)
        if "-" in normalized:
            parts = value.split("-", 1)
            if len(parts) != 2 or not all(item.isdigit() for item in parts):
                raise ValueError("invalid port range %r" % value)
            start, end = (int(item) for item in parts)
            if not (1 <= start < end <= 65535):
                raise ValueError("invalid port range %r" % value)
            return "%d:%d" % (start, end)
        if normalized.isdigit():
            port = int(normalized)
            if 1 <= port <= 65535:
                return str(port)
            raise ValueError("port out of range: %d" % port)
        try:
            return str(socket.getservbyname(normalized, "tcp"))
        except OSError as exc:
            raise ValueError("unable to resolve port or alias %r" % value) from exc
