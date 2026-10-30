#!/sbin/sh
# Based on https://github.com/sadatdaniel/a50-ubuntu-touch recovery installer.
# Sourced by update-binary; no partition writes occur until both payloads verify.
umask 077
BOOT_BYTES=57671680
ROOTFS_TARGET=/data/ubuntu.img
STAGED_ROOTFS=/data/.a50-ubuntu.img.new
find_part() {
    for base in /dev/block/by-name /dev/block/bootdevice/by-name \
        /dev/block/platform/*/by-name /dev/disk/by-partlabel; do
        [ -e "$base/$1" ] && { readlink -f "$base/$1"; return 0; }
    done
    return 1
}
model=$(getprop ro.product.model)
case "$model" in SM-A505F|SM-A505F/DS) ;; *) abort "Expected SM-A505F; recovery reports $model." ;; esac
BOOT_DEV=$(find_part boot) || abort 'No boot partition found.'
DATA_DEV=$(find_part userdata) || abort 'No userdata partition found.'
sectors=$(cat "/sys/class/block/$(basename "$BOOT_DEV")/size")
[ "$((sectors * 512))" -eq "$BOOT_BYTES" ] || abort 'Unexpected boot partition size.'
mount /data >/dev/null 2>&1 || true
grep -q ' /data ' /proc/mounts || abort 'Mount unencrypted Data in TWRP first.'
for path in /data/system/users /data/system/packages.xml /data/rootfs.img \
    /data/ubuntu.img /data/system-data /data/user-data /data/.force-adb /data/.force-ssh; do
    [ ! -e "$path" ] || abort 'Existing installation found. Back up privately, then use TWRP Format Data for a clean install.'
done
unzip -o "$ZIP" install/SHA256SUMS install/manifest.txt install/boot.img -d "$TMP" >/dev/null 2>&1 \
    || abort 'Cannot extract installer metadata and boot image.'
sum_of() { awk -v name="$1" '$2 == name || $2 == "*" name {print $1}' "$TMP/install/SHA256SUMS"; }
BOOT_SHA=$(sum_of boot.img)
ROOTFS_SHA=$(sum_of rootfs.img)
[ "${#BOOT_SHA}" -eq 64 ] && [ "${#ROOTFS_SHA}" -eq 64 ] || abort 'Missing payload checksums.'
rootfs_bytes=$(awk -F= '$1 == "rootfs_bytes" {print $2}' "$TMP/install/manifest.txt")
case "$rootfs_bytes" in ''|*[!0-9]*) abort 'Invalid rootfs size.' ;; esac
need_kb=$(awk -v n="$rootfs_bytes" 'BEGIN {printf "%.0f", int((n + 1023) / 1024) + 262144}')
free_kb=$(df -k /data | tail -1 | awk '{print $4}')
[ "$free_kb" -ge "$need_kb" ] || abort 'Not enough free space on Data.'
img_bytes=$(stat -c%s "$TMP/install/boot.img")
[ "$img_bytes" -gt 0 ] && [ "$img_bytes" -le "$BOOT_BYTES" ] || abort 'Invalid boot image size.'
got=$(sha256sum "$TMP/install/boot.img" | awk '{print $1}')
[ "$got" = "$BOOT_SHA" ] || abort 'Boot payload checksum mismatch.'
ui_print 'Writing and verifying the clean root filesystem (several minutes)...'
unzip -p "$ZIP" install/rootfs.img.gz | gzip -dc > "$STAGED_ROOTFS" \
    || abort 'Cannot decompress rootfs. Boot partition has not been changed.'
[ "$(stat -c%s "$STAGED_ROOTFS")" = "$rootfs_bytes" ] || abort 'Rootfs size mismatch. Boot partition has not been changed.'
got=$(sha256sum "$STAGED_ROOTFS" | awk '{print $1}')
[ "$got" = "$ROOTFS_SHA" ] || abort 'Rootfs checksum mismatch. Boot partition has not been changed.'
ui_print 'Writing the boot image...'
dd if="$TMP/install/boot.img" of="$BOOT_DEV" bs=1048576 >/dev/null 2>&1 || abort 'Boot write failed. Do not reboot; restore stock boot first.'
sync
back=$(dd if="$BOOT_DEV" bs=512 count=$(((img_bytes + 511) / 512)) 2>/dev/null \
    | head -c "$img_bytes" | sha256sum | awk '{print $1}')
[ "$back" = "$BOOT_SHA" ] || abort 'Boot read-back mismatch. Do not reboot; restore stock boot first.'
mv "$STAGED_ROOTFS" "$ROOTFS_TARGET" || abort 'Cannot activate verified rootfs. Do not reboot.'
sync
rm -rf "$TMP"
ui_print 'Installation verified. Reboot to System and complete first-boot setup.'
ui_print 'No personal accounts, VPN profile, SSH keys or preset login password are included.'
ui_print 'This build still requires a first clean-install hardware test.'
