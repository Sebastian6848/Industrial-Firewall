#!/bin/sh

# Refresh only the repository configuration and pkg catalogue used to list
# plugins. This deliberately does not run the firmware check/update workflow.

if ! /usr/local/sbin/pluginctl -c firmware_reload; then
	echo "__PLUGIN_REFRESH_ERROR__: unable to regenerate repository configuration"
	exit 1
fi

if /usr/local/sbin/pkg update -f -r OPNsense; then
	echo "__PLUGIN_REFRESH_OK__"
	exit 0
fi

echo "__PLUGIN_REFRESH_ERROR__: unable to update the package catalogue"
exit 1
