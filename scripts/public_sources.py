#!/usr/bin/env python3
"""Audit and export a small explicit source allowlist, never Git history."""
import argparse
import hashlib
from pathlib import Path
import re
import stat
import zipfile

ROOT = Path(__file__).resolve().parent.parent
# Share the exact file allowlist with Git; new files need explicit review.
TOP = {line[2:] for line in (ROOT / '.gitignore').read_text().splitlines()
       if line.startswith('!/') and not line.endswith('/')}
TREES = set()
BINARY = {'.png', '.ttf'}
RULES = {
    'private key': rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',
    'access token': rb'(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-|svcacct-)[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})',
    'personal workstation path': rb'/(?:Users|home)/[^/\s]+/',
    'dynamic DNS endpoint': rb'\b[A-Za-z0-9-]+\.(?:tplinkdns\.com|duckdns\.org|ddns\.net)\b',
    'SSH identity': rb'(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256)\s+[A-Za-z0-9+/]{30,}',
    'WireGuard private key': rb'(?m)^\s*(?:PrivateKey|PresharedKey)\s*=\s*[A-Za-z0-9+/]{40,}=',
    'quoted credential assignment': rb'''(?im)^\s*["']?(?:password|passwd|pin|psk|ssid|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)["']?\s*[:=]\s*["'][^"'\r\n]{3,}["']''',
}
# These are operating-system account paths, not workstation identities.
SYSTEM_PATHS = re.compile(rb'/home/(?:phablet|root)' + rb'/')
DENIED_NAMES = {'known_hosts', 'authorized_keys', '.DS_Store', '.env', 'adbkey', 'adbkey.pub', 'auth.json', 'credentials.json'}


def files():
    for p in sorted(ROOT.rglob('*')):
        rel = p.relative_to(ROOT)
        if rel.parts[0] not in TREES and rel.as_posix() not in TOP:
            continue
        if any(x in {'.git', '__pycache__', 'build'} for x in rel.parts):
            continue
        if p.is_dir():
            continue
        if p.is_symlink():
            raise ValueError(f'Symlink not allowed: {rel}')
        if p.name in DENIED_NAMES or p.suffix in {'.pyc', '.log', '.img', '.zip', '.so', '.key', '.pem'}:
            raise ValueError(f'Private/generated file in public tree: {rel}')
        yield p, rel


def audit(items):
    failures = []
    for p, rel in items:
        data = p.read_bytes()
        if p.suffix in BINARY:
            # Only explicitly reviewed static assets; no screenshots or binaries.
            if rel.parts[:3] != ('patches', 'lomiri-panel', 'fonts'):
                failures.append(f'{rel}: unreviewed binary asset')
            continue
        if b'\x00' in data:
            failures.append(f'{rel}: unexpected binary')
            continue
        data = SYSTEM_PATHS.sub(b'/SYSTEM_ACCOUNT/', data)
        for name, pattern in RULES.items():
            for match in re.finditer(pattern, data):
                line = data.count(b'\n', 0, match.start()) + 1
                failures.append(f'{rel}:{line}: {name}')
    if failures:
        raise ValueError('\n'.join(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--version', default='0.0.1')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', args.version):
        parser.error('--version must be a version such as 0.0.1')
    items = list(files())
    audit(items)
    print(f'Privacy source audit passed: {len(items)} files.')
    if args.export:
        target = ROOT / 'dist'
        target.mkdir(exist_ok=True)
        out = target / f'LinuxGalaxyA50-{args.version}-source.zip'
        with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p, rel in items:
                info = zipfile.ZipInfo('LinuxGalaxyA50/' + rel.as_posix(), (2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                mode = 0o755 if p.stat().st_mode & stat.S_IXUSR else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, p.read_bytes())
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        (target / 'SOURCE-SHA256SUMS').write_text(f'{digest}  {out.name}\n')
        print('Created dist/' + out.name + ' without Git history or host metadata.')


if __name__ == '__main__':
    main()
