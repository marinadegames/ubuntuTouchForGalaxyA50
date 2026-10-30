#!/bin/sh
# Run on the phone with the patched ChrootContainer.py in the staging folder.
set -eu
STAGE=${1:?Pass the staging directory}
TARGET=/usr/lib/python3/dist-packages/libertine/ChrootContainer.py
BACKUP=/var/lib/a50-libertine
[ "$(id -u)" = 0 ]
expected='1.7.2+ubports+0~20260901180603.153+ubports26.04.1~1.gbpab6bbc'
[ "$(dpkg-query -W -f='${Version}' python3-libertine-chroot)" = "$expected" ] || {
    echo 'Libertine version changed; review the patch before applying.' >&2
    exit 1
}
python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$STAGE/ChrootContainer.py"
grep -q "extractall(path=self.root_path, filter='tar')" "$STAGE/ChrootContainer.py"
readonly_root=0
case ",$(findmnt -n -o OPTIONS /)," in *,ro,*) readonly_root=1; mount -o remount,rw / ;; esac
finish() { if [ "$readonly_root" = 1 ]; then mount -o remount,ro /; fi; }
trap finish EXIT
mkdir -p "$BACKUP"
if [ ! -f "$BACKUP/ChrootContainer.py.original" ]; then
    cp -a "$TARGET" "$BACKUP/ChrootContainer.py.original"
    dpkg-query -W -f='${Version}' python3-libertine-chroot > "$BACKUP/package-version"
fi
install -o root -g root -m 644 "$STAGE/ChrootContainer.py" "$TARGET"
