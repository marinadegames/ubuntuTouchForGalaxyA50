#!/usr/bin/env python3
"""Check exactly the staged Git blobs; run automatically before local commits."""
import fnmatch
import getpass
from pathlib import Path
import socket
import subprocess
import sys
from public_sources import TOP, TREES, DENIED_NAMES, audit


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    root = Path(git('rev-parse', '--show-toplevel').decode().strip())
    names = git('ls-files', '-z').decode().split('\0')
    forbidden = {'known_hosts', 'authorized_keys', '.DS_Store', '.env', 'adbkey',
                 'auth.json', '.netrc', '.npmrc', '.pypirc'} | DENIED_NAMES
    patterns = ('*.pem', '*.key', '*.p12', '*.pfx', '*.ovpn', '*.keystore', '*.jks',
                '*.img*', '*.zip', '*.tar*', '*.gz', '*.xz', '*.db', '*.sqlite*',
                '*.log', '*.pyc', '*.so', '*.dylib', '.env*', 'id_rsa*', 'id_ed25519*',
                'id_ecdsa*', 'adbkey*', 'credentials*.json', '*service-account*.json')
    blocked_parts = {'.git', '.ssh', '.gnupg', '.aws', '.codex', '.config',
                     '__pycache__', 'node_modules', 'backups', 'private', 'build'}
    identities = set()
    username = getpass.getuser()
    if len(username) >= 8:
        identities.add(username)
        if len(username.split('.')[0]) >= 8: identities.add(username.split('.')[0])
    host = socket.gethostname().removesuffix('.local')
    if len(host) >= 8 and host != 'localhost': identities.add(host)
    for field in ('user.name', 'user.email'):
        r = subprocess.run(['git', 'config', '--global', '--get', field], capture_output=True)
        value = r.stdout.decode().strip()
        if len(value) >= 8: identities.add(value)
    needles = [x.lower().encode() for x in identities]
    items = []
    errors = []
    for n in filter(None, names):
        p = Path(n)
        if p.parts[0] not in TREES and n not in TOP:
            errors.append(f'{n}: outside public source allowlist'); continue
        if (any(x in blocked_parts for x in p.parts) or p.name in forbidden or
                any(fnmatch.fnmatch(p.name, pattern) for pattern in patterns)):
            errors.append(f'{n}: private/generated filename'); continue
        entry = git('ls-files', '-s', '--', n).decode().strip()
        if not entry.startswith('100644 ') and not entry.startswith('100755 '):
            errors.append(f'{n}: symlinks/submodules are not allowed'); continue
        data = git('show', ':' + n)
        if any(v in n.encode().lower() or v in data.lower() for v in needles):
            errors.append(f'{n}: local personal identity detected'); continue
        class Blob:
            suffix = p.suffix
            def __init__(self, content): self.content = content
            def read_bytes(self): return self.content
        items.append((Blob(data), p))
    try: audit(items)
    except ValueError as error: errors.append(str(error))
    if errors:
        print('Git privacy check FAILED. Commit blocked.', file=sys.stderr)
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'Git privacy check passed: {len(items)} staged files, exact index contents.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
