#!/usr/bin/env python3
"""Rebuild a fresh ext4 filesystem and package only an audited system archive."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile
import zipfile
from sanitize_rootfs import name

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def attrs(member):
    out = {}
    for k, v in member.pax_headers.items():
        if k.startswith('SCHILY.xattr.'):
            out[k[len('SCHILY.xattr.'):]] = v.encode('utf-8', 'surrogateescape')
        elif k.startswith('LIBARCHIVE.xattr.'):
            out[k[len('LIBARCHIVE.xattr.'):]] = base64.b64decode(v + '=' * (-len(v) % 4))
    return out


def signature(path):
    out = {}
    with tarfile.open(path) as t:
        for m in t:
            n = name(m.name)
            if n == 'lost+found': continue
            digest = None
            if m.isfile() or m.islnk():
                h = hashlib.sha256()
                with t.extractfile(m) as f:
                    for b in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(b)
                digest = h.hexdigest()
            out[n] = (m.mode, m.uid, m.gid, 'file' if m.isfile() or m.islnk() else m.type.decode(),
                      m.linkname if m.issym() else '', digest, attrs(m))
    return out


def restore_xattrs(archive, image, debugfs, stage):
    commands = []
    def quote(s):
        if '\n' in s or '\r' in s: raise ValueError('Unsupported control character')
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    with tarfile.open(archive) as t:
        for m in t:
            for key, value in attrs(m).items():
                blob = stage / f'xattr-{len(commands)}'
                blob.write_bytes(value)
                commands.append(f'ea_set -f {quote(str(blob))} {quote("/" + name(m.name))} {quote(key)}')
    if commands:
        batch = stage / 'restore-xattrs.txt'; batch.write_text('\n'.join(commands) + '\n')
        subprocess.run([debugfs, '-w', '-f', str(batch), str(image)], check=True, stdout=subprocess.DEVNULL)
    return len(commands)


def check_boot(path):
    data = path.read_bytes()
    if data[:8] != b'ANDROID!' or len(data) > 57671680:
        raise ValueError('Invalid A50 boot image')
    ks, _, rs, _, ss, _, _, page, version, _ = struct.unpack_from('<10I', data, 8)
    if page != 2048 or version != 1 or ss:
        raise ValueError('Unreviewed boot layout')
    end = page + sum((n + page - 1) // page * page for n in (ks, rs, ss))
    if end > len(data): raise ValueError('Truncated boot image')
    # The captured partition contains only image sections, zero padding and an
    # inherited AVB footer. No partition slack is accepted without inspection.
    tail = data[end:]
    if tail[-64:-60] == b'AVBf': tail = tail[:-64]
    if any(tail): raise ValueError('Unexpected nonzero boot partition slack')
    ramdisk = gzip.decompress(data[page + (ks + page - 1) // page * page:][:rs])
    return data, ramdisk


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--system-tar', type=Path, required=True)
    p.add_argument('--privacy-report', type=Path, required=True)
    p.add_argument('--boot', type=Path, required=True)
    p.add_argument('--denylist', type=Path, required=True)
    p.add_argument('--tools', type=Path, required=True, help='e2fsprogs build directory')
    p.add_argument('--exporter', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = json.loads(args.privacy_report.read_text())
    if not report.get('passed') or report.get('archive_sha256') != sha(args.system_tar):
        raise ValueError('The supplied archive has no matching successful privacy audit')
    boot, ramdisk = check_boot(args.boot)
    needles = [s.encode().lower() for s in json.loads(args.denylist.read_text()) if s]
    if any(n in boot.lower() or n in ramdisk.lower() for n in needles):
        raise ValueError('Known personal identifier in boot image')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists(): raise ValueError('Refusing to overwrite an existing installer')
    work = ROOT / 'work'; work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='public-build-', dir=work) as temp:
        stage = Path(temp).resolve(); image = stage / 'rootfs.img'
        with image.open('xb') as f: f.truncate(6442450944)
        image.chmod(0o600)
        mke2fs = str(args.tools / 'misc/mke2fs')
        subprocess.run([mke2fs, '-q', '-t', 'ext4', '-F', '-b', '4096', '-I', '256',
                        '-L', 'ubuntu-touch', '-U', 'random', '-O', '^orphan_file,^metadata_csum_seed',
                        '-E', 'lazy_itable_init=0,lazy_journal_init=0,nodiscard',
                        '-d', str(args.system_tar.resolve()), str(image)], check=True)
        xattr_count = restore_xattrs(args.system_tar, image, str(args.tools / 'debugfs/debugfs'), stage)
        subprocess.run([str(args.tools / 'e2fsck/e2fsck'), '-fn', str(image)], check=True)
        exported = stage / 'verified.tar'
        subprocess.run([str(args.exporter.resolve()), str(image), str(exported)], check=True)
        expected, actual = signature(args.system_tar), signature(exported)
        if expected != actual:
            different = sorted(n for n in expected.keys() | actual.keys() if expected.get(n) != actual.get(n))
            raise ValueError('Filesystem reconstruction mismatch: ' + ', '.join(different[:30]))
        print(f'Filesystem verified: {len(actual)} entries; {xattr_count} extended attributes.', flush=True)
        root_hash = sha(image)
        compressed = stage / 'rootfs.img.gz'
        with image.open('rb') as src, compressed.open('wb') as target:
            with gzip.GzipFile(filename='', mode='wb', fileobj=target, compresslevel=1, mtime=0) as gz:
                shutil.copyfileobj(src, gz, 8 * 1024 * 1024)
        manifest = ('device=a50\nmodel=SM-A505F\nrelease=26.04-1.x\nversion=2026-10-30-public-test\n'
                    'variant=public-test\nrootfs_bytes=6442450944\n'
                    f'boot_bytes={len(boot)}\nprivacy=system-only-fresh-filesystem\nhardware_clean_install_test=pending\n')
        sums = f'{hashlib.sha256(boot).hexdigest()}  boot.img\n{root_hash}  rootfs.img\n'
        report.update({'filesystem_check': 'e2fsck -fn passed', 'reconstruction_check': f'{len(actual)} entries matched: contents, permissions, owners, links and extended attributes',
                       'rootfs_sha256': root_hash, 'boot_sha256': hashlib.sha256(boot).hexdigest(),
                       'boot_personal_identifier_check': 'passed', 'filesystem_created_fresh': True})
        release_notes = ('Ubuntu Touch for Samsung Galaxy A50 SM-A505F\n\n'
                         'Test build: first clean-install hardware test is pending.\n'
                         'Requires the matching Android 11 vendor firmware and unlocked bootloader.\n'
                         'Back up privately. TWRP Format Data erases phone data; the installer requires clean Data.\n'
                         'Install this ZIP through TWRP, reboot and complete the first-boot wizard.\n'
                         'Choose your own PIN; no password or authorized computer is preconfigured.\n'
                         'Personal home directories, accounts, VPN profiles and host keys are excluded.\n')
        with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            def put(n, data, executable=False):
                info = zipfile.ZipInfo(n, (2026, 10, 30, 0, 0, 0)); info.create_system = 3
                info.external_attr = (0o100755 if executable else 0o100644) << 16
                z.writestr(info, data)
            for file in sorted((ROOT / 'installer').rglob('*')):
                if file.is_file():
                    n = file.relative_to(ROOT / 'installer').as_posix()
                    put(n, file.read_bytes(), n.endswith(('update-binary', '.sh')))
            put('install/boot.img', boot)
            # zipfile.write does not include UID/GID or filesystem extended attributes.
            # Stream the large payload and set fixed ZIP metadata explicitly.
            info = zipfile.ZipInfo('install/rootfs.img.gz', (2026, 10, 30, 0, 0, 0))
            info.create_system = 3; info.external_attr = 0o100644 << 16
            info.file_size = compressed.stat().st_size
            if info.file_size + len(boot) > 2_000_000_000:
                raise ValueError('Installer exceeds the chosen 2 GB asset budget')
            with compressed.open('rb') as src, z.open(info, 'w') as target:
                shutil.copyfileobj(src, target, 8 * 1024 * 1024)
            put('install/manifest.txt', manifest)
            put('install/SHA256SUMS', sums)
            put('PRIVACY-REPORT.json', json.dumps(report, indent=2) + '\n')
            put('README.txt', release_notes)
        with zipfile.ZipFile(args.output) as z:
            if z.testzip() is not None: raise ValueError('ZIP integrity verification failed')
        sidecar = args.output.with_name('IMAGE-PRIVACY-REPORT.json')
        sidecar.write_text(json.dumps(report, indent=2) + '\n')
        args.output.with_name('IMAGE-SHA256SUMS').write_text(f'{sha(args.output)}  {args.output.name}\n')
        print('Created and verified ' + args.output.name, flush=True)


if __name__ == '__main__':
    main()
