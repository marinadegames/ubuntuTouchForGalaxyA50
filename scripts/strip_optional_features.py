#!/usr/bin/env python3
"""Remove optional VPN and USB capture additions from a clean system tar."""
import argparse
import copy
import io
import json
from pathlib import PurePosixPath
import re
import tarfile
from sanitize_rootfs import name

PACKAGES = {'wireguard-tools', 'wireguard-go', 'mullvad-vpn'}
CUSTOM = re.compile(r'(?:a50-vpn|a50-mullvad|mullvad|a50-capture|a50-screencast|phone-h264-stream|mirror-h264)', re.I)


def unwanted(n):
    return bool(CUSTOM.search(n) or n == 'etc/apparmor.d/local/wg-quick' or
                n == 'etc/wireguard' or n.startswith('etc/wireguard/'))


def prune_packages(data):
    paragraphs = data.decode().split('\n\n')
    return ('\n\n'.join(p for p in paragraphs if p.strip() and
            not any(re.search(r'(?m)^Package: ' + re.escape(pkg) + r'$', p) for pkg in PACKAGES)) + '\n\n').encode()


def strip(input_path, output_path):
    removed = set()
    with tarfile.open(input_path) as src:
        entries = {name(m.name): m for m in src}
        package_files = set()
        other_files = set()
        info_paths = set()
        for n, m in entries.items():
            if not n.startswith('var/lib/dpkg/info/'):
                continue
            package = PurePosixPath(n).name.split('.', 1)[0].split(':', 1)[0]
            if package in PACKAGES: info_paths.add(n)
            if n.endswith('.list') and m.isfile():
                paths = {line.lstrip('/') for line in src.extractfile(m).read().decode().splitlines()}
                (package_files if package in PACKAGES else other_files).update(paths)
        for n, m in entries.items():
            if n in package_files and not m.isdir():
                if n in other_files: raise ValueError('Refusing to remove a shared package file: ' + n)
                removed.add(n)
            if n in info_paths or unwanted(n): removed.add(n)
            if any('/' + pkg + '/' in '/' + n + '/' for pkg in PACKAGES): removed.add(n)
        with tarfile.open(output_path, 'w', format=tarfile.PAX_FORMAT) as dst:
            for n, original in entries.items():
                if n in removed: continue
                m = copy.copy(original); m.name = n
                m.pax_headers = dict(original.pax_headers)
                m.pax_headers['hdrcharset'] = 'BINARY'
                if m.islnk() and name(m.linkname) in removed:
                    raise ValueError('Remaining hardlink points to removed file: ' + n)
                data = None
                if n in {'var/lib/dpkg/status', 'var/lib/dpkg/status-old', 'var/lib/dpkg/available', 'var/lib/apt/extended_states'} and m.isfile():
                    data = prune_packages(src.extractfile(original).read())
                elif n == 'etc/resolvconf/interface-order' and m.isfile():
                    data = b''.join(line for line in src.extractfile(original).read().splitlines(keepends=True)
                                    if b'mullvad' not in line.lower())
                if data is not None:
                    m.size = len(data); dst.addfile(m, io.BytesIO(data))
                elif m.isfile():
                    with src.extractfile(original) as f: dst.addfile(m, f)
                else: dst.addfile(m)
    return {'removed_paths': sorted(removed), 'removed_package_names': sorted(PACKAGES),
            'network_dns_configuration': 'Retained resolvconf and its generic boot fix; removed VPN interface preference.'}


def check(path):
    with tarfile.open(path) as src:
        for m in src:
            n = name(m.name)
            if unwanted(n): raise ValueError('Optional feature remains: ' + n)
            if n == 'var/lib/dpkg/status':
                data = src.extractfile(m).read().decode()
                if any(re.search(r'(?m)^Package: ' + re.escape(pkg) + r'$', data) for pkg in PACKAGES):
                    raise ValueError('Optional VPN package remains installed')
            if n == 'etc/resolvconf/interface-order' and b'mullvad' in src.extractfile(m).read().lower():
                raise ValueError('VPN DNS preference remains')
    print('Feature exclusion check passed: VPN additions and custom USB capture helpers are absent.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output')
    p.add_argument('--report')
    args = p.parse_args()
    if args.output:
        report = strip(args.input, args.output)
        if args.report:
            with open(args.report, 'w') as f: json.dump(report, f, indent=2); f.write('\n')
        print('Removed', len(report['removed_paths']), 'optional feature files/directories.')
    check(args.output or args.input)


if __name__ == '__main__':
    main()
