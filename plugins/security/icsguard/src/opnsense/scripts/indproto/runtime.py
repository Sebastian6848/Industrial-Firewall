import os
import shutil
import signal
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import generate_rules


CONFIG_XML = Path("/conf/config.xml")
SURICATA_BINARY = Path("/usr/local/bin/suricata")
SURICATA_RC = Path("/usr/local/etc/rc.d/suricata")
FRAGMENT_PATH = Path(os.environ.get(
    "INDPROTO_SURICATA_FRAGMENT",
    "/usr/local/etc/suricata/conf.d/indproto.yaml",
))
SURICATA_YAML = Path(os.environ.get(
    "INDPROTO_SURICATA_YAML",
    "/usr/local/etc/suricata/suricata.yaml",
))


def ok(data=None, message="ok"):
    payload = {"status": "ok", "message": message}
    if data:
        payload.update(data)
    return payload


def error(message, data=None):
    payload = {"status": "error", "message": message}
    if data:
        payload.update(data)
    return payload


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_text(content)
    temporary.replace(path)


class CapabilityProbe:
    def probe(self):
        available = {
            "suricata_binary": shutil.which("suricata") is not None or SURICATA_BINARY.exists(),
            "suricata_rc": SURICATA_RC.exists(),
            "configctl": shutil.which("configctl") is not None or Path("/usr/local/sbin/configctl").exists(),
            "rules_dir_writable": self.dir_writable(generate_rules.RULES_PATH.parent),
            "fragment_dir_writable": self.dir_writable(FRAGMENT_PATH.parent),
            "suricata_yaml": SURICATA_YAML.exists(),
        }
        return {
            "available": available,
            "missing": [name for name, value in available.items() if not value],
        }

    def dir_writable(self, path):
        path = Path(path)
        if path.exists():
            return os.access(path, os.W_OK)
        return os.access(path.parent, os.W_OK)


class NativeIDS:
    def enabled(self):
        if not CONFIG_XML.exists():
            return False
        try:
            root = ET.parse(CONFIG_XML).getroot()
            node = root.find("./OPNsense/IDS/general/enabled")
            return node is not None and (node.text or "").strip().lower() in ("1", "true", "yes", "on")
        except (OSError, ET.ParseError):
            return False

    def reload_template(self):
        return self.run(["/usr/local/sbin/configctl", "template", "reload", "OPNsense/IDS"])

    def install_rules(self):
        return self.run(["/usr/local/sbin/configctl", "ids", "install", "rules"])

    def run(self, command):
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "command failed").strip())
        return (result.stdout or "").strip()


class ServiceManager:
    def pids(self):
        result = subprocess.run(["/bin/pgrep", "-x", "suricata"], capture_output=True, text=True)
        return [int(item) for item in result.stdout.split() if item.isdigit()]

    def is_running(self):
        return bool(self.pids())

    def signal_reload(self):
        pids = self.pids()
        if not pids:
            return self.start()
        for pid in pids:
            os.kill(pid, signal.SIGUSR2)
        return ok({"transition": "reload"}, "Suricata rules reloaded")

    def start(self):
        return self.run_service("onestart", "start")

    def stop(self):
        return self.run_service("onestop", "stop")

    def restart(self):
        return self.run_service("onerestart", "restart")

    def run_service(self, action, transition):
        result = subprocess.run(["/usr/sbin/service", "suricata", action], capture_output=True, text=True)
        if result.returncode != 0:
            return error((result.stderr or result.stdout or "Suricata service command failed").strip())
        return ok({"transition": transition}, "Suricata %sed" % transition)

    def status(self):
        state = "running" if self.is_running() else "stopped"
        return ok({
            "components": {"suricata": state},
            "capabilities": CapabilityProbe().probe(),
        }, "Suricata %s" % state)


class ApplyManager:
    def __init__(self):
        self.ids = NativeIDS()
        self.service = ServiceManager()

    def fragment(self, protocols, indproto=None):
        # Detection ports must be scalar strings: a YAML sequence silently
        # disables probing in Suricata. DNP3 has no built-in port fallback.
        app_protocols = [protocol for protocol in ('modbus', 'dnp3', 'mqtt', 'enip')
                         if protocol in protocols or (protocol == 'mqtt' and 'nclink' in protocols)]
        if not app_protocols:
            return ""
        lines = ["%YAML 1.1", "---", "app-layer:", "  protocols:"]
        for protocol in app_protocols:
            ports = {'modbus': {'502'}, 'dnp3': {'20000'}, 'mqtt': {'1883'}, 'enip': {'44818'}}[protocol]
            if indproto is not None:
                resolver = generate_rules.PolicyValueResolver(generate_rules.CONFIG_PATH or generate_rules.DEFAULT_CONFIG_PATH)
                for node in indproto.findall('./rules/rule'):
                    if generate_rules.text(node, 'protocol') not in ({'mqtt', 'nclink'} if protocol == 'mqtt' else {protocol}):
                        continue
                    port = resolver.port(generate_rules.text(node, 'dst_port')).strip('[] ')
                    if port and port not in ('any', '*'):
                        ports.update(part.strip() for part in port.split(',') if part.strip())
            lines.extend(["    %s:" % protocol, "      enabled: yes", '      detection-ports:',
                          '        dp: "[%s]"' % ','.join(sorted(ports))])
        return "\n".join(lines) + "\n"

    def validate(self):
        binary = shutil.which("suricata") or str(SURICATA_BINARY)
        result = subprocess.run([binary, "--init-errors-fatal", "-T", "-c", str(SURICATA_YAML)], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Suricata validation failed").strip())

    def snapshot(self, path):
        return path.read_bytes() if path.exists() else None

    def restore(self, path, content):
        if content is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(".%s.rollback" % path.name)
            temporary.write_bytes(content)
            temporary.replace(path)

    def apply(self):
        old_fragment = self.snapshot(FRAGMENT_PATH)
        old_rules = self.snapshot(generate_rules.RULES_PATH)
        old_cron = self.snapshot(generate_rules.CRON_PATH)
        template_touched = False
        try:
            indproto = generate_rules.load_config(generate_rules.CONFIG_PATH)
            general = indproto.find("general")
            if general is None:
                raise ValueError("missing <general> configuration node")
            enabled = generate_rules.is_enabled(generate_rules.text(general, "enabled", "0"))
            was_running = self.service.is_running()
            if enabled:
                rules, protocols, time_rules = generate_rules.render_rules(indproto)
                generate_rules.write_rules(rules)
                new_fragment = self.fragment(protocols, indproto)
                fragment_changed = old_fragment != new_fragment.encode()
                if new_fragment:
                    atomic_write(FRAGMENT_PATH, new_fragment)
                elif FRAGMENT_PATH.exists():
                    FRAGMENT_PATH.unlink()
                generate_rules.update_cron(time_rules)
            else:
                generate_rules.write_rules([])
                generate_rules.update_cron(False)
                fragment_changed = FRAGMENT_PATH.exists()
                if fragment_changed:
                    FRAGMENT_PATH.unlink()

            template_touched = True
            self.ids.reload_template()
            self.ids.install_rules()
            if enabled:
                self.validate()

            if enabled and not was_running:
                service_result = self.service.start()
            elif enabled and fragment_changed:
                service_result = self.service.restart()
            elif enabled:
                service_result = self.service.signal_reload()
            elif was_running and not self.ids.enabled():
                service_result = self.service.stop()
            elif was_running and fragment_changed:
                service_result = self.service.restart()
            else:
                service_result = ok({"transition": "none"}, "No service transition required")

            if service_result["status"] == "error":
                raise RuntimeError(service_result.get('message', 'Suricata service transition failed'))
            return ok({
                "enabled": enabled,
                "service": service_result,
                "fragment_changed": fragment_changed,
            }, "industrial protocol policy applied")
        except Exception as exc:
            self.restore(FRAGMENT_PATH, old_fragment)
            self.restore(generate_rules.RULES_PATH, old_rules)
            self.restore(generate_rules.CRON_PATH, old_cron)
            if template_touched:
                try:
                    self.ids.reload_template()
                    self.ids.install_rules()
                except Exception:
                    pass
            return error("industrial protocol apply failed: %s" % exc)
