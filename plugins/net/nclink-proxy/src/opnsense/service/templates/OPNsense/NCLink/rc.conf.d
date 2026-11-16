{% if not helpers.empty('OPNsense.NCLink.general.enabled') %}
nclink_proxy_enable="YES"
nclink_proxy_pidfile="/var/run/nclink_proxy.pid"
nclink_proxy_flags="--listen-host '{{OPNsense.NCLink.general.listen_host}}' --listen-port '{{OPNsense.NCLink.general.listen_port}}' --target-host '{{OPNsense.NCLink.general.target_host}}' --target-port '{{OPNsense.NCLink.general.target_port}}' --log-file '{{OPNsense.NCLink.general.log_file}}'"
{% else %}
nclink_proxy_enable="NO"
{% endif %}
