#!/bin/sh
set -eu
NODE=/sys/class/camera/flash/rear_flash
# Android init sets its own owner/mode during startup; apply host access after it.
n=0
while [ "$n" -lt 30 ]; do
    if [ -e "$NODE" ] && [ "$(lxc-attach -n android -- /system/bin/getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; then
        break
    fi
    n=$((n + 1))
    sleep 1
done
[ -e "$NODE" ] || exit 1
chgrp video "$NODE"
chmod 0660 "$NODE"
