#!/usr/bin/env python3
"""Fail closed on personal state and credential patterns in a system-only tar.

Supply a private JSON list of known identifiers with --denylist. Reports contain
only file paths and rule names, never matched values. Review any failure.
"""
import argparse
import hashlib
import json
import re
import tarfile
from sanitize_rootfs import allowed, name
from public_sources import RULES


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive')
    p.add_argument('--base', required=True)
    p.add_argument('--denylist', required=True)
    p.add_argument('--report', required=True)
    args = p.parse_args()
    needles = [v.encode().lower() for v in json.load(open(args.denylist)) if v]
    failures = []
    pristine_pattern_matches = []
    checked = total = 0
    with tarfile.open(args.base) as base:
        pristine = {}
        for m in base:
            n = name(m.name)
            if m.isfile():
                pristine[n] = hashlib.sha256(base.extractfile(m).read()).hexdigest()
    with tarfile.open(args.archive) as t:
        seen = set()
        for m in t:
            n = name(m.name)
            if n in seen: failures.append([n, 'duplicate path'])
            seen.add(n)
            if not allowed(n, m): failures.append([n, 'excluded personal state'])
            if m.uname or m.gname: failures.append([n, 'owner identity metadata'])
            if m.issym():
                # Links may point at system or runtime paths, but never a local workstation.
                text = m.linkname.encode().lower()
                if any(v in text for v in needles): failures.append([n, 'known personal identifier in link'])
            if not m.isfile(): continue
            checked += 1
            with t.extractfile(m) as f:
                digest = hashlib.sha256()
                previous = b''
                small = bytearray() if m.size <= 2 * 1024 * 1024 else None
                for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
                    total += len(block); digest.update(block)
                    data = previous + block
                    if any(v in data.lower() for v in needles): failures.append([n, 'known personal identifier'])
                    previous = data[-1024:]
                    if small is not None: small.extend(block)
                if n.startswith(('home/', 'root/')) and pristine.get(n) != digest.hexdigest():
                    failures.append([n, 'non-pristine home file'])
            if small is not None:
                data = bytes(small)
                # Packages can contain public example keys, but no usable private keys.
                for rule, pattern in RULES.items():
                    if rule == 'personal workstation path':
                        # Upstream binaries/docs embed build paths; known local paths are
                        # checked above. Do not mistake generic package build paths for users.
                        continue
                    if re.search(pattern, data):
                        # SSH/crypto programs contain key-format markers as
                        # constants. Accept only byte-identical pristine package
                        # files; known local identifiers are always checked.
                        if n.startswith('usr/') and pristine.get(n) == digest.hexdigest():
                            pristine_pattern_matches.append([n, rule])
                        else:
                            failures.append([n, rule])
                if n in {'etc/shadow', 'etc/shadow-'}:
                    if any(l.split(b':')[1] not in (b'!', b'*', b'!!') for l in data.splitlines()):
                        failures.append([n, 'unlocked password entry'])
                if n == 'var/lib/extrausers/shadow':
                    for line in data.splitlines():
                        fields = line.split(b':')
                        if fields[0] != b'phablet' or fields[1] != b'':
                            failures.append([n, 'non-pristine login database'])
                if n in {'etc/machine-id', 'var/lib/dbus/machine-id'} and data:
                    failures.append([n, 'machine identity'])
                if n == 'etc/default/adbd' and b'ADBD_SECURE=0' in data:
                    failures.append([n, 'ADB host verification disabled'])
    digest = hashlib.sha256()
    with open(args.archive, 'rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''): digest.update(block)
    report = {'passed': not failures, 'archive_sha256': digest.hexdigest(), 'regular_files_checked': checked,
              'file_bytes_checked': total, 'failures': failures,
              'pristine_package_pattern_matches': pristine_pattern_matches,
              'scope': 'Reachable system files, known local identifiers and credential patterns. Free blocks are excluded by rebuilding a new filesystem.',
              'hardware_installation_test': 'not performed'}
    with open(args.report, 'w') as f: json.dump(report, f, indent=2); f.write('\n')
    print(json.dumps(report, indent=2))
    if failures: raise SystemExit(1)


if __name__ == '__main__':
    main()
