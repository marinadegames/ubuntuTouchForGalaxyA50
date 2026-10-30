#!/bin/sh
# Run as root on the phone; argument is the prepared staging directory.
set -eu
STAGE=${1:?Pass the staging directory}
BASE=/var/lib/a50-panel
[ "$(id -u)" = 0 ] || exit 1
[ -f "$STAGE/Panel/A50QuickSettings.qml" ]
[ ! -e "$BASE" ] || { echo 'An installation already exists; inspect it before replacing.' >&2; exit 1; }
was_readonly=0
case ",$(findmnt -n -o OPTIONS /)," in *,ro,*) was_readonly=1; mount -o remount,rw / ;; esac
restore_mount() { if [ "$was_readonly" = 1 ]; then mount -o remount,ro /; fi; }
trap restore_mount EXIT
mkdir -p "$BASE/stock" "$BASE/custom"
runuser -u phablet -- env XDG_RUNTIME_DIR=/run/user/32011 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/32011/bus gsettings get com.lomiri.Shell enable-blur > "$BASE/stock-enable-blur"
cp -a /usr/share/lomiri/Panel "$BASE/stock/"
cp -a "$STAGE/Panel" "$BASE/custom/"
dpkg-query -W -f='${Version}' lomiri-common > "$BASE/lomiri-version"
chown -R root:root "$BASE"
chmod -R go-w "$BASE"
(cd "$BASE/stock" && find Panel -type f -exec sha256sum {} +) > "$BASE/stock.sha256"
install -o root -g root -m 755 "$STAGE/a50-panel-control" /usr/local/sbin/a50-panel-control
install -o root -g root -m 644 "$STAGE/a50-custom-panel.service" /etc/systemd/system/a50-custom-panel.service
restore_mount
trap - EXIT
mkdir -p /home/phablet/.local/bin
install -o phablet -g phablet -m 755 "$STAGE/restore-stock-panel" /home/phablet/.local/bin/restore-stock-panel
install -o phablet -g phablet -m 755 "$STAGE/use-custom-panel" /home/phablet/.local/bin/use-custom-panel
systemctl daemon-reload
# The installation falls back to the stock panel unless verification cancels this timer.
systemd-run --unit=a50-panel-safety-rollback --on-active=5m /usr/local/sbin/a50-panel-control recover
/usr/local/sbin/a50-panel-control custom
/usr/local/sbin/a50-panel-control status
