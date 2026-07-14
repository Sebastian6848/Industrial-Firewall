# Offline plugin workflow

This core tree disables every remote system and plugin package channel. No HTTP/HTTPS package repository, repository signing key, or package catalogue is required.

## Plugin source repository

The maintained source repository is checked out at `/home/sebastian/plugins`:

```text
origin    https://gitee.com/xwy6848/plugins.git
upstream  https://github.com/opnsense/plugins.git
```

`origin` is writable. Push access to `upstream` is disabled locally.

To merge future official source changes:

```sh
cd /home/sebastian/plugins
git fetch upstream
git checkout master
git merge upstream/master
git push origin master
```

## Recommended: install a local package file

On a compatible FreeBSD/OPNsense build machine, build the selected plugin:

```sh
cd /home/sebastian/plugins/<category>/<plugin>
make package
```

Copy the resulting `os-*.pkg` file to the firewall by SCP, USB storage, or another local transfer method. Install it without contacting a repository:

```sh
pkg add /root/packages/os-example.pkg
```

To replace an installed plugin with a newer local build:

```sh
pkg add -f /root/packages/os-example.pkg
```

The package must be built for the same FreeBSD and OPNsense ABI as the target firewall. All dependencies must already be installed or copied as local package files and installed explicitly with `pkg add`.

## Direct source installation

The plugin framework also supports an `install` target:

```sh
cd /path/to/plugins/<category>/<plugin>
make install
```

This is useful during development, but `make package` followed by local `pkg add` is preferred because the installed files remain tracked by the package database. Direct source installation does not bypass missing build tools or dependencies and must be performed on a compatible OPNsense system.

## Offline policy

The generated `OPNsense`, `OPNsense-aux`, and FreeBSD pkg repositories are disabled. Web API and configd actions for remote install, reinstall, sync, repository queries, update, and upgrade are disabled. The Firmware page only lists locally installed `os-*` plugins and can remove them.

An administrator with root access can still deliberately rewrite pkg repository configuration. The product's normal Web, console, API, and background update paths do not enable or use a remote download channel.
