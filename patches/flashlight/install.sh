#!/bin/sh
set -eu
STAGE=${1:?Pass the staging directory}
BASE=/var/lib/a50-panel
[ "$(id -u)" = 0 ]
[ -f "$BASE/custom/Panel/A50QuickSettings.qml" ]
readonly_root=0
case ",$(findmnt -n -o OPTIONS /)," in *,ro,*) readonly_root=1; mount -o remount,rw / ;; esac
finish() { if [ "$readonly_root" = 1 ]; then mount -o remount,ro /; fi; }
trap finish EXIT
mkdir -p "$BASE/flashlight-backup"
for item in /etc/deviceinfo/devices/a50.yaml "$BASE/custom/Panel/A50QuickSettings.qml"; do
    backup="$BASE/flashlight-backup/$(basename "$item")"
    [ -e "$backup" ] || cp -p "$item" "$backup"
done
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/deviceinfo/devices/a50.yaml')
s=p.read_text()
keys={
 'FlashlightSysfsPath':'/sys/class/camera/flash/rear_flash',
 'FlashlightSimpleEnableValue':'1',
 'FlashlightSimpleDisableValue':'0',
}
lines=s.splitlines()
for key,value in keys.items():
    prefix='  '+key+':'
    lines=[line for line in lines if not line.startswith(prefix)]
    lines.append(prefix+' "'+value+'"')
p.write_text('\n'.join(lines)+'\n')
PY
install -o root -g root -m 755 "$STAGE/a50-flashlight-permissions.sh" /usr/local/bin/a50-flashlight-permissions.sh
install -o root -g root -m 644 "$STAGE/a50-flashlight-permissions.service" /etc/systemd/system/a50-flashlight-permissions.service
install -o root -g root -m 644 "$STAGE/A50QuickSettings.qml" "$BASE/custom/Panel/A50QuickSettings.qml"
finish
trap - EXIT
systemctl daemon-reload
systemctl enable --now a50-flashlight-permissions.service
ls -l /sys/class/camera/flash/rear_flash
