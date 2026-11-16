# Industrial Firewall installer

This is the project's installer fork, kept with core and plugins in the same
repository. It is based on the scripts from the verified
opnsense-installer-25.1_2 package; its package hash is pinned in
tools/release/upstream-inputs.sha256. The additional firewall-keymap script
comes from the matching signed FreeBSD base set.

Changes apply the appliance name and release to installer dialogs, keyboard
selection, UFS/ZFS setup and completion. Internal command names, partition
types, installation logic, original copyright and BSD licenses are retained.
The core branding configuration is /usr/local/opnsense/version/branding.conf.

build-package.py generates opnsense-installer-25.1_3.pkg for the ISO build.
The installer package remains separate from core so files have a single
package owner and the official signed vendor package is not rewritten.
