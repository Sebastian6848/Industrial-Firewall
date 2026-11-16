#!/bin/sh
# Assemble a fresh DVD root from verified upstream sets and local packages.
set -eu

usage() {
    echo "Usage: $0 /absolute/verified-inputs /absolute/output /absolute/fresh-work-dir" >&2
    exit 1
}
[ "$#" = 3 ] || usage
for directory in "$@"; do
    case "$directory" in /*) ;; *) usage ;; esac
done
[ "$(uname -s):$(uname -m):$(id -u)" = 'FreeBSD:amd64:0' ] || usage

inputs=$1
output=$2
work=$3
repo=$(cd "$(dirname "$0")/../.." && pwd -P)
version=26.1.11
revision=11
media=industrial-firewall-2026.11.16-amd64
commit=$(git -C "$repo" rev-parse HEAD)
[ -z "$(git -C "$repo" status --porcelain --untracked-files=no)" ] || {
    echo "Build from a committed source tree" >&2
    exit 1
}
mkdir -p "$output"
mkdir "$work"
work=$(cd "$work" && pwd -P)
stage=$work/root
custom=$work/custom
mkdir "$stage" "$custom"
mounted=no
cleanup() {
    if [ "$mounted" = yes ]; then
        umount "$stage/dev"
    fi
    rm -f "$output/.${media}.iso.incomplete"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

(
    cd "$inputs"
    while read -r digest file; do
        sha256 -q -c "$digest" "$file" > /dev/null || {
            echo "Checksum mismatch: $file" >&2; exit 1
        }
    done < "$repo/tools/release/upstream-inputs.sha256"
)
for set in base kernel; do
    opnsense-verify -q "$inputs/sets/$set-$version-amd64.txz"
    tar -xpf "$inputs/sets/$set-$version-amd64.txz" -C "$stage"
done
install -d -m 0755 "$stage/dev" "$stage/conf" "$stage/home" "$stage/mnt"
install -d -m 1777 "$stage/tmp"
mkdir -m 700 "$stage/tmp/iso-packages"
printf 'configd_enable="NO"\n' > "$stage/etc/rc.conf.local"
mount -t devfs devfs "$stage/dev"
mounted=yes

# No host package changes: the wrapper resolves and checks dependencies in
# the image only, while package creation uses the host's pkg binary.
pkg=$(command -v pkg)
cat > "$work/image-pkg" <<EOF
#!/bin/sh
case "\$1" in
    info|query) exec "$pkg" -c "$stage" "\$@" ;;
    create) exec "$pkg" "\$@" ;;
    *) echo "Unsupported image build package action: \$1" >&2; exit 1 ;;
esac
EOF
chmod 0755 "$work/image-pkg"

for file in "$inputs"/vendor/All/*.pkg; do
    case "${file##*/}" in
        opnsense-[0-9]*|os-clamav-[0-9]*|os-squid-[0-9]*) continue ;;
    esac
    cp -p "$file" "$stage/tmp/iso-packages/"
done
# Pass the entire signed dependency set at once to resolve dependencies
# locally, including the pkg bootstrap and the language pack.
set --
for file in "$stage"/tmp/iso-packages/*.pkg; do
    set -- "$@" "/tmp/iso-packages/${file##*/}"
done
"$pkg" -c "$stage" add "$@"

add_custom() {
    cp -p "$custom/$1.pkg" "$stage/tmp/iso-packages/"
    "$pkg" -c "$stage" add "/tmp/iso-packages/$1.pkg"
}
make -C "$repo" package CORE_VERSION="$version" CORE_REVISION="$revision" \
    CORE_HASH="$commit" PKG="$work/image-pkg" PLUGINCTL=/usr/bin/true \
    WRKDIR="$work/core" PKGDIR="$custom"
add_custom "opnsense-${version}_${revision}"

for dir in www/squid security/clamav net/app-identification security/icsguard security/industrial-suite; do
    plugin=$repo/plugins/$dir
    make -C "$plugin" package PLUGIN_DEVEL= PKG="$work/image-pkg" \
        WRKDIR="$work/${dir##*/}" PKGDIR="$custom"
    name=$(make -C "$plugin" -V NAME PLUGIN_DEVEL=)
    set -- "$custom/$name"-[0-9]*.pkg
    [ "$#" = 1 ] && [ -f "$1" ]
    name=${1##*/}
    add_custom "${name%.pkg}"
done

"$pkg" -c "$stage" check -d -a
"$pkg" -c "$stage" lock -y opnsense
"$pkg" -c "$stage" query '%n %v %o' | LC_ALL=C sort > "$output/$media.packages.txt"
cp "$output/$media.packages.txt" "$stage/usr/local/opnsense/version/pkgs"
rm -rf "$stage/tmp/iso-packages" "$stage/var/cache/pkg"
rm "$stage/etc/rc.conf.local"
umount "$stage/dev"
mounted=no

# Replace only the factory sample. No live configuration or secrets enter the image.
python3 "$repo/tools/release/factory-config.py" "$work/config.xml"
install -m 0600 "$work/config.xml" "$stage/usr/local/etc/config.xml"
install -m 0600 "$work/config.xml" "$stage/conf/config.xml"
chroot "$stage" /usr/local/etc/rc.loader
if [ -f "$stage/boot/loader.conf.local" ]; then
    sed -i '' '/# ZFS standard/,/zfs_load="YES"/d' "$stage/boot/loader.conf.local"
fi
cat >> "$stage/boot/loader.conf.local" <<'EOF'
kern.cam.boot_delay="10000"
console="vidconsole,comconsole"
boot_multicons="YES"
boot_serial="YES"
comconsole_speed="115200"
EOF
printf '/dev/iso9660/OPNSENSE_INSTALL\t/\tcd9660\tro\t0\t0\ntmpfs\t/tmp\ttmpfs\trw,mode=01777\t0\t0\n' > "$stage/etc/fstab"

printf './dev\n./tmp\n' > "$work/mtree.exclude"
mtree -c -k uid,gid,mode,size,sha256digest -p "$stage" -X "$work/mtree.exclude" > "$work/installed_filesystem.mtree"
install -m 0600 "$work/installed_filesystem.mtree" "$stage/etc/installed_filesystem.mtree"
for entropy in entropy boot/entropy; do
    dd if=/dev/random of="$stage/$entropy" bs=4096 count=1 2>/dev/null
    chmod 0600 "$stage/$entropy"
done

mkdir -p "$work/efi/efi/boot"
cp "$stage/boot/loader.efi" "$work/efi/efi/boot/bootx64.efi"
makefs -t msdos -o fat_type=12 -o sectors_per_cluster=1 -o volume_label=EFISYS \
    -s 2048k "$work/efiboot.img" "$work/efi"
makefs -t cd9660 -o "bootimage=i386;$stage/boot/cdboot" -o no-emul-boot \
    -o "bootimage=i386;$work/efiboot.img" -o label=OPNSENSE_INSTALL -o rockridge \
    "$output/.$media.iso.incomplete" "$stage"
mv "$output/.$media.iso.incomplete" "$output/$media.iso"
printf '%s\n' "$commit" > "$output/$media.source-commit.txt"
(cd "$output" && sha256 -r "$media.iso" > "$media.iso.sha256")
