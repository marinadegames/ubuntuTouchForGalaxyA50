#!/usr/bin/env python3
"""Create a reviewed system-only tar from a phone export and pristine templates.

Input archives stay private. This creates a new archive; it never edits the phone.
Review the inventory and audit the result before turning it into a filesystem.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import tarfile

RESET = ('home', 'root', 'etc/ssh', 'etc/writable', 'var/lib/extrausers',
         'etc/hosts', 'etc/timezone', 'etc/localtime', 'android', 'nix')
CLEAR = ('userdata', 'tmp', 'run', 'proc', 'sys', 'dev', 'media', 'mnt',
         'var/log', 'var/tmp', 'var/cache', 'var/backups', 'var/crash', 'var/spool',
         'var/lib/android-data', 'var/lib/AccountsService', 'var/lib/NetworkManager',
         'var/lib/bluetooth', 'var/lib/ofono', 'var/lib/lightdm', 'var/lib/lightdm-data',
         'var/lib/biometryd-meizu-fp-reader', 'var/lib/aethercast', 'var/lib/upower',
         'var/lib/usermetrics', 'var/lib/usb-moded', 'var/lib/rfkill', 'var/lib/urfkill',
         'var/lib/lomiri-location-service', 'var/lib/waydroid', 'var/lib/connman',
         'var/lib/sudo', 'var/lib/private', 'var/lib/tailscale', 'var/lib/caddy',
         'var/lib/dhcp', 'var/lib/ureadahead', 'var/lib/apport', 'var/lib/a50-vpn',
         'etc/NetworkManager/system-connections', 'usr/lib/NetworkManager/system-connections',
         'etc/netplan', 'etc/wireguard', 'etc/openvpn', 'etc/caddy', 'etc/letsencrypt',
         'etc/ssl/private', 'var/lib/lxc/android/rootfs', 'var/lib/lxc/android/overrides')
DROP_PARTS = {'.ssh', '.gnupg', '.codex', '.config.private', '__pycache__'}
PRIVATE_SERVICE = re.compile(r'(?:obsidian|caddy|tailscale|rclone)', re.I)
DROP_FILES = {'etc/ssh/sshd_config.d/99-a50-devel.conf', 'root/.wget-hsts',
              'etc/ssl/certs/ssl-cert-snakeoil.pem', 'var/lib/systemd/random-seed',
              'var/lib/urandom/random-seed', 'etc/adjtime',
              'etc/systemd/system/NetworkManager.service.d/a50-vendor.conf',
              'etc/systemd/system/a50-vendor.service'}


def name(s):
    if s.startswith('/') or '..' in PurePosixPath(s).parts:
        raise ValueError('Unsafe tar path')
    return str(PurePosixPath(s))


def under(n, prefix):
    return n == prefix or n.startswith(prefix + '/')


def index(t):
    out = {}
    for m in t:
        n = name(m.name)
        if n in out:
            raise ValueError('Duplicate archive member: ' + n)
        out[n] = (t, m)
    return out


def members(base, current, synced):
    entries = index(current)
    entries.update(index(synced))
    pristine = index(base)
    for n in list(entries):
        if any(under(n, p) for p in RESET):
            del entries[n]
    for n, pair in pristine.items():
        if any(under(n, p) for p in RESET):
            entries[n] = pair
    return entries


def allowed(n, m):
    if re.search(r'(?:a50-vpn|a50-mullvad|mullvad|a50-capture|a50-screencast)', n, re.I):
        return False
    if n == 'etc/apparmor.d/local/wg-quick':
        return False
    if n == 'lost+found' or n in DROP_FILES:
        return False
    if any(p in DROP_PARTS for p in PurePosixPath(n).parts):
        return False
    if any(under(n, p) for p in CLEAR):
        return m.isdir()
    if '/backups/' in '/' + n + '/' and n.startswith('var/lib/a50-'):
        return False
    if any(part in n for part in ('/flashlight-backup/', '/flashlight-backup')):
        return False
    if n.startswith(('etc/systemd/', 'etc/init/', 'etc/sudoers.d/', 'usr/local/')) and PRIVATE_SERVICE.search(n):
        return False
    if n.startswith('etc/systemd/system/') and n.endswith('/a50-screen-off.service'):
        return False  # Display power belongs to repowerd in an interactive installation.
    if n.startswith('etc/systemd/system/') and n.endswith('/a50-vendor.service'):
        return False  # The container mount hooks own vendor mounting.
    if n.startswith('etc/systemd/system/a50-vendor.service.d'):
        return False
    if n.endswith(('/authorized_keys', '/known_hosts', '/adbkey', '/adbkey.pub')):
        return False
    if re.search(r'/ssh_host_.*_key(?:\.pub)?$', n):
        return False
    if n.endswith(('/.bash_history', '/.zsh_history', '/.python_history')):
        return False
    if n.endswith(('.dpkg-old', '.dpkg-dist', '.a50-original', '.bad', '.disabled', '.removed', '~')):
        return False
    if '.before-' in n or '.before.' in n:
        return False
    return True


def transform(n, data):
    if n == 'var/lib/a50-panel/stock-enable-blur':
        return b'true\n'
    if n in ('etc/machine-id', 'var/lib/dbus/machine-id'):
        return b''
    if n == 'etc/hostname':
        return b'ubuntu-phablet\n'
    if n == 'etc/default/adbd':
        return b'# Require each computer to be authorized on the phone.\nADBD_SECURE=1\n'
    if n == 'etc/resolvconf/resolv.conf.d/base':
        return b'# Local NetworkManager DNS forwarder; no saved network resolver.\nnameserver 127.0.0.1\n'
    if n in ('etc/shadow', 'etc/shadow-'):
        lines = []
        for line in data.decode().splitlines():
            row = line.split(':')
            if len(row) != 9:
                raise ValueError('Unexpected shadow format')
            row[1] = '!'
            lines.append(':'.join(row))
        return ('\n'.join(lines) + '\n').encode()
    if n == 'etc/gshadow' or n.endswith('/gshadow-'):
        lines = []
        for line in data.decode().splitlines():
            row = line.split(':'); row[1] = '!'; lines.append(':'.join(row))
        return ('\n'.join(lines) + '\n').encode()
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', required=True)
    p.add_argument('--current', required=True)
    p.add_argument('--synced', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--inventory', required=True)
    args = p.parse_args()
    inventory = []
    with tarfile.open(args.base) as base, tarfile.open(args.current) as current, tarfile.open(args.synced) as synced:
        entries = members(base, current, synced)
        with tarfile.open(args.output, 'w', format=tarfile.PAX_FORMAT) as out:
            def order(pair):
                n, (_, m) = pair
                return (0 if m.isdir() else 2 if m.islnk() else 1, len(PurePosixPath(n).parts) if m.isdir() else 0, n)
            for n, (src, original) in sorted(entries.items(), key=order):
                if not allowed(n, original):
                    continue
                m = copy.copy(original)
                m.name = n
                m.uname = m.gname = ''
                m.pax_headers = {k: v for k, v in original.pax_headers.items()
                                 if k.startswith(('SCHILY.xattr.security.', 'LIBARCHIVE.xattr.security.',
                                                  'SCHILY.xattr.system.posix_acl_', 'LIBARCHIVE.xattr.system.posix_acl_'))}
                # Preserve Linux filename bytes when libarchive runs on macOS;
                # its default UTF-8 handling decomposes accented filenames.
                m.pax_headers['hdrcharset'] = 'BINARY'
                # Retain permissions/capabilities; remove owner names and device timestamps.
                m.mtime = min(int(m.mtime), 1793318400)
                if m.islnk():
                    target = name(m.linkname)
                    if target not in entries or not allowed(target, entries[target][1]):
                        raise ValueError('Hardlink points to excluded data: ' + n)
                    m.linkname = target
                digest = None
                if m.isfile():
                    with src.extractfile(original) as f:
                        if n in {'etc/machine-id', 'var/lib/dbus/machine-id', 'etc/hostname', 'etc/shadow', 'etc/shadow-', 'etc/gshadow', 'etc/default/adbd', 'etc/resolvconf/resolv.conf.d/base', 'var/lib/a50-panel/stock-enable-blur'} or n.endswith('/gshadow-'):
                            data = transform(n, f.read()); m.size = len(data)
                            digest = hashlib.sha256(data).hexdigest(); out.addfile(m, io.BytesIO(data))
                        else:
                            # tarfile copies in bounded chunks; do not load large images into RAM.
                            class Reader:
                                def __init__(self): self.hash = hashlib.sha256()
                                def read(self, size):
                                    data = f.read(size); self.hash.update(data); return data
                            reader = Reader(); out.addfile(m, reader); digest = reader.hash.hexdigest()
                else:
                    out.addfile(m)
                inventory.append({'path': n, 'mode': m.mode, 'uid': m.uid, 'gid': m.gid,
                                  'type': m.type.decode(), 'size': m.size, 'sha256': digest})
    with open(args.inventory, 'w') as f:
        json.dump(inventory, f, indent=2); f.write('\n')
    print(f'Created system-only archive: {len(inventory)} entries. Image audit still required.')


if __name__ == '__main__':
    main()
