#!/bin/sh
set -eu

ANDROID_USB=/sys/class/android_usb/android0

if [ -d "$ANDROID_USB" ]; then
    echo 0 > "$ANDROID_USB/enable"
    echo 04e8 > "$ANDROID_USB/idVendor"
    echo 6860 > "$ANDROID_USB/idProduct"
    echo "Samsung" > "$ANDROID_USB/iManufacturer"
    echo "Galaxy A50 Linux Console" > "$ANDROID_USB/iProduct"
    echo "A50LINUX" > "$ANDROID_USB/iSerial"
    echo acm > "$ANDROID_USB/functions"
    echo 1 > "$ANDROID_USB/enable"
else
    mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config
    G=/sys/kernel/config/usb_gadget/a50-console
    mkdir -p "$G/strings/0x409" "$G/configs/c.1/strings/0x409"
    echo 0x04e8 > "$G/idVendor"
    echo 0x6860 > "$G/idProduct"
    echo "A50LINUX" > "$G/strings/0x409/serialnumber"
    echo "Samsung" > "$G/strings/0x409/manufacturer"
    echo "Galaxy A50 Linux Console" > "$G/strings/0x409/product"
    echo "ACM console" > "$G/configs/c.1/strings/0x409/configuration"
    mkdir -p "$G/functions/acm.usb0"
    ln -sf "$G/functions/acm.usb0" "$G/configs/c.1/acm.usb0"
    ls /sys/class/udc | head -n 1 > "$G/UDC"
fi

for n in 1 2 3 4 5; do
    [ -c /dev/ttyGS0 ] && exit 0
    sleep 1
done

echo "ttyGS0 was not created" >&2
exit 1
