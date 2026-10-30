#!/usr/bin/env python3
"""Assemble the public A50 image from pinned downloads; never read a phone or home."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PORT_COMMIT = 'b4556ede53f888461321696003df29a27c464c81'
RELEASE_BASE = 'https://github.com/sadatdaniel/a50-ubuntu-touch/releases/download/inputs-20261017/'
INPUTS = {
    'port.tar.gz': ('https://codeload.github.com/sadatdaniel/a50-ubuntu-touch/tar.gz/' + PORT_COMMIT,
                    '727e5e34b61d090bf27efee388901d648088040df72b3a1c4f58ebdb2e10429d'),
    'rootfs.tar.xz': (RELEASE_BASE + 'rootfs-809e340ecb9c8043d2dff0874a7bb9a6c9adbf214c142812c47f5c3c4c139ea1.tar.xz',
                      'a213879c05908da4c643ac472538b79997052862d3d7413a1863dc56aae30db5'),
    'gsi.tar.xz': (RELEASE_BASE + 'halium_halium_arm64-1585.tar.xz',
                   'd08a92e40fa77246415d1e78acaf6f51c7cca4d5e982177d2810cb2726ed49be'),
    'donor.img': ('https://github.com/sadatdaniel/a50-ubuntu-touch/releases/download/installer-2026-09-08/boot.img',
                  '90c281f8da080f7bc1a9ec9aa822e0ae10bd19a77804717e0c3f6ea83cffd03b'),
    'kernel.tar.gz': ('https://github.com/sadatdaniel/a50-halium/releases/download/kernel-builds-20261017/out-aa13-usb-configfs.tar.gz',
                       '2220fd0896929eeef7e4cc01e33f3536fe784461a30d176fba75a0daa4a1878f'),
}
COMPAT_INPUTS = {
    'libxml2': ('https://ports.ubuntu.com/ubuntu-ports/pool/main/libx/libxml2/libxml2_2.9.14+dfsg-1.3ubuntu3_arm64.deb',
                '6045818c821a498cfa2b9c93deeac87db5d0d6bd07f160176f1073af0c2858e4', ['libxml2.so.2*']),
    'libicu74': ('https://ports.ubuntu.com/ubuntu-ports/pool/main/i/icu/libicu74_74.2-1ubuntu3_arm64.deb',
                 '041df33ab32c57287a62ba141890a82512bf092854be455259c8034ab7ae9fbc', ['libicu*.so.74*']),
}


def run(*args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def fetch(url, expected, target):
    target = Path(target)
    if target.exists():
        if digest(target) != expected: raise ValueError('Cached input checksum mismatch: ' + target.name)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.part')
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'LinuxGalaxyA50/0.0.1'})
        with urllib.request.urlopen(request, timeout=180) as src, temporary.open('wb') as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        if digest(temporary) != expected: raise ValueError('Download checksum mismatch: ' + target.name)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def source_archive(archive, destination):
    """Extract GitHub source files first, then links, without following archive links."""
    destination = Path(destination)
    destination.mkdir()
    links = []
    with tarfile.open(archive) as source:
        for member in source:
            parts = PurePosixPath(member.name).parts[1:]
            if not parts: continue
            if member.name.startswith('/') or '..' in parts: raise ValueError('Unsafe source path')
            target = destination.joinpath(*parts)
            if member.isdir(): target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as src, target.open('wb') as dst: shutil.copyfileobj(src, dst)
                target.chmod(member.mode & 0o777)
            elif member.issym(): links.append((target, member.linkname))
            else: raise ValueError('Unsupported source archive entry')
    for target, link in links:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(link)


def make_boot(donor_path, kernel_archive, output):
    data = Path(donor_path).read_bytes()
    if data[:8] != b'ANDROID!': raise ValueError('Invalid boot donor')
    ks, _, rs, _, ss, _, _, page, version, _ = struct.unpack_from('<10I', data, 8)
    if page != 2048 or version != 1 or ss or struct.unpack_from('<I', data, 1632)[0]:
        raise ValueError('Unsupported donor layout')
    with tarfile.open(kernel_archive) as archive:
        choices = [m for m in archive if m.isfile() and PurePosixPath(m.name).name == 'Image']
        if len(choices) != 1: raise ValueError('Kernel archive must contain exactly one Image')
        kernel = archive.extractfile(choices[0]).read()
    ramdisk_start = page + (ks + page - 1) // page * page
    ramdisk = data[ramdisk_start:ramdisk_start + rs]
    if len(ramdisk) != rs: raise ValueError('Truncated donor ramdisk')
    header = bytearray(data[:page])
    struct.pack_into('<I', header, 8, len(kernel))
    image_id = hashlib.sha1(kernel + struct.pack('<I', len(kernel)) + ramdisk +
                           struct.pack('<I', len(ramdisk)) + struct.pack('<I', 0)).digest()
    header[576:608] = image_id + bytes(12)
    pad = lambda value: value + bytes((-len(value)) % page)
    result = bytes(header) + pad(kernel) + pad(ramdisk)
    if len(result) > 57671680: raise ValueError('Boot image exceeds the A50 boot partition')
    Path(output).write_bytes(result)


def copy_file(source, target, mode=0o644):
    target = Path(target); target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target); target.chmod(mode)


def enable(root, unit):
    link = root / 'etc/systemd/system/multi-user.target.wants' / unit
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink(): link.unlink()
    link.symlink_to('/etc/systemd/system/' + unit)


def apply_patches(root):
    """Only edit an offline image; do not execute phone installers on the host."""
    root = Path(root).resolve()
    if root == Path('/') or not (root / 'var/lib/dpkg/status').is_file():
        raise ValueError('Expected an offline Ubuntu root')
    panel = root / 'usr/share/lomiri/Panel'
    base = root / 'var/lib/a50-panel'
    (base / 'stock').mkdir(parents=True)
    (base / 'custom').mkdir()
    shutil.copytree(panel, base / 'stock/Panel', symlinks=True)
    shutil.copytree(panel, base / 'custom/Panel', symlinks=True)
    with (ROOT / 'patches/lomiri-panel/panel.patch').open('rb') as patch:
        run('patch', '--batch', '--fuzz=0', '-p1', '-d', base / 'custom', stdin=patch)
    for p in (ROOT / 'patches/lomiri-panel').glob('A50*.qml'):
        copy_file(p, base / 'custom/Panel' / p.name)
    shutil.copytree(ROOT / 'patches/lomiri-panel/fonts', base / 'custom/Panel/fonts')
    version = subprocess.check_output(['dpkg-query', '--admindir=' + str(root / 'var/lib/dpkg'),
                                      '-W', '-f=${Version}', 'lomiri-common'], text=True)
    (base / 'lomiri-version').write_text(version)
    (base / 'stock-enable-blur').write_text('true\n')
    stock = base / 'stock'
    sums = [digest(p) + '  ' + p.relative_to(stock).as_posix() for p in sorted(stock.rglob('*'))
            if p.is_file() and not p.is_symlink()]
    (base / 'stock.sha256').write_text('\n'.join(sums) + '\n')
    copy_file(ROOT / 'patches/lomiri-panel/a50-panel-control', root / 'usr/local/sbin/a50-panel-control', 0o755)
    for command in ['use-custom-panel', 'restore-stock-panel']:
        copy_file(ROOT / 'patches/lomiri-panel' / command, root / 'usr/local/bin' / command, 0o755)
    for directory, unit in [('lomiri-panel', 'a50-custom-panel.service'),
                            ('flashlight', 'a50-flashlight-permissions.service')]:
        copy_file(ROOT / 'patches' / directory / unit, root / 'etc/systemd/system' / unit)
        enable(root, unit)
    copy_file(ROOT / 'patches/flashlight/a50-flashlight-permissions.sh',
              root / 'usr/local/bin/a50-flashlight-permissions.sh', 0o755)
    yaml = root / 'etc/deviceinfo/devices/a50.yaml'
    text = yaml.read_text()
    if len(re.findall(r'^a50:', text, re.M)) != 1: raise ValueError('Unexpected DeviceInfo layout')
    keys = {'FlashlightSysfsPath': '/sys/class/camera/flash/rear_flash',
            'FlashlightSimpleEnableValue': '1', 'FlashlightSimpleDisableValue': '0'}
    lines = [line for line in text.splitlines() if not any(line.startswith('  ' + k + ':') for k in keys)]
    yaml.write_text('\n'.join(lines) + '\n' + ''.join('  ' + k + ': "' + v + '"\n' for k, v in keys.items()))
    with (ROOT / 'patches/libertine/ubuntu2604-container-creation.patch').open('rb') as patch:
        run('patch', '--batch', '--fuzz=0', '-p1', '-d', root, stdin=patch)
    copy_file(ROOT / 'patches/rootfs/90-device-specific-config.ini',
              root / 'etc/usb-moded/90-device-specific-config.ini')
    override = root / 'usr/share/glib-2.0/schemas/99_a50-panel.gschema.override'
    override.write_text('[com.lomiri.Shell]\nenable-blur=false\n')
    run('chroot', root, 'glib-compile-schemas', '/usr/share/glib-2.0/schemas')


def check(version):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', version):
        raise ValueError('Expected a version such as 0.0.1')
    for filename, (url, value) in INPUTS.items():
        if not url.startswith('https://') or not re.fullmatch(r'[0-9a-f]{64}', value):
            raise ValueError('Invalid pinned input: ' + filename)
    for relative in ['installer/install/a50-install.sh', 'patches/lomiri-panel/panel.patch',
                     'patches/libertine/ubuntu2604-container-creation.patch', 'scripts/export_ext4.c']:
        if not (ROOT / relative).is_file(): raise ValueError('Missing build source: ' + relative)
    for directory in ['patches/vpn', 'patches/screencast']:
        if (ROOT / directory).exists(): raise ValueError('Excluded feature source remains')
    print('Build plan valid for ' + version + '; no downloads or image build performed.')


def build(version):
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64') or os.geteuid() != 0:
        raise ValueError('Run ./build.sh: the image build requires a privileged Linux ARM64 container')
    workspace = Path('/build'); cache = workspace / 'inputs'
    cache.mkdir(parents=True, exist_ok=True)
    output = Path('/output'); final = output / ('ubuntu-touch-a50-' + version + '.zip')
    if final.exists(): raise ValueError('Output already exists')
    files = {n: fetch(u, h, cache / n) for n, (u, h) in INPUTS.items()}
    port = workspace / 'port'; source_archive(files['port.tar.gz'], port)
    package_dir = cache / 'packages'; package_dir.mkdir()
    for line in (port / 'scripts/release/validated-packages.lock').read_text().splitlines():
        if not line or line.startswith('#'): continue
        package, package_version, arch, value, _ = line.split('\t')
        if not re.fullmatch(r'[a-z0-9+.-]+', package) or not re.fullmatch(r'[a-zA-Z0-9.+:~_-]+', package_version):
            raise ValueError('Unsafe package lock')
        filename = package + '_' + package_version + '_' + arch + '.deb'
        fetch(RELEASE_BASE + urllib.parse.quote(filename.replace('~', '.'), safe=''), value, package_dir / filename)
    # Replace the moving upstream lookup with hash-pinned compatibility libraries.
    install_compat = port / 'scripts/release/add-openstore-compat.sh'
    install_compat.write_text('#!/bin/sh\nset -eu\npython3 /repo/scripts/build_release.py --compat-root "$1"\n')
    install_compat.chmod(0o755)
    boot = workspace / 'boot.img'; make_boot(files['donor.img'], files['kernel.tar.gz'], boot)
    out = workspace / 'upstream'
    run('bash', port / 'scripts/release/build-device-tarball.sh', '--boot', boot, '--out', out)
    run('bash', port / 'scripts/release/build-rootfs-image.sh', '--device-tarball', out / 'device_a50.tar.xz',
        '--package-bundle', package_dir, '--out', out, '--cache', cache, '--size', '6G',
        '--rootfs-url', files['rootfs.tar.xz'].as_uri(), '--rootfs-sha256', INPUTS['rootfs.tar.xz'][1],
        '--gsi-tar', files['gsi.tar.xz'], '--gsi-sha256', INPUTS['gsi.tar.xz'][1])
    exporter = workspace / 'export_ext4'
    run('gcc', '-O2', ROOT / 'scripts/export_ext4.c', '-lext2fs', '-lcom_err', '-larchive', '-o', exporter)
    base_tar = workspace / 'base.tar'; current_tar = workspace / 'patched.tar'
    run(exporter, out / 'rootfs.img', base_tar)
    mounted = workspace / 'mounted'; mounted.mkdir()
    run('mount', '-o', 'loop', out / 'rootfs.img', mounted)
    try: apply_patches(mounted)
    finally: run('umount', mounted)
    run(exporter, out / 'rootfs.img', current_tar)
    # Final output is recreated in a new filesystem, so removed material leaves no slack.
    empty = workspace / 'empty.tar'
    with tarfile.open(empty, 'w'): pass
    sanitized = workspace / 'sanitized.tar'; system_tar = workspace / 'system.tar'
    run('python3', ROOT / 'scripts/sanitize_rootfs.py', '--base', base_tar, '--current', current_tar,
        '--synced', empty, '--output', sanitized, '--inventory', workspace / 'inventory.json')
    current_tar.unlink()
    (out / 'rootfs.img').unlink()
    run('python3', ROOT / 'scripts/strip_optional_features.py', '--input', sanitized, '--output', system_tar,
        '--report', workspace / 'feature-removal.json')
    sanitized.unlink()
    denylist = workspace / 'denylist.json'
    denylist.write_text(json.dumps(['/repo/scripts/', '/repo/patches/', '/tmp/a50-builder-home/']))
    audit = workspace / 'privacy.json'
    run('python3', ROOT / 'scripts/audit_rootfs.py', system_tar, '--base', base_tar,
        '--denylist', denylist, '--report', audit)
    base_tar.unlink()
    output.mkdir(exist_ok=True)
    run('python3', ROOT / 'scripts/build_public_image.py', '--system-tar', system_tar,
        '--privacy-report', audit, '--boot', boot, '--denylist', denylist,
        '--exporter', exporter, '--version', version, '--work-dir', workspace / 'final', '--output', final)
    provenance = {'version': version, 'port_commit': PORT_COMMIT, 'phone_or_personal_backup_used': False,
                  'inputs': {n: {'url': u, 'sha256': h} for n, (u, h) in INPUTS.items()},
                  'compatibility_libraries': {n: {'url': u, 'sha256': h} for n, (u, h, _) in COMPAT_INPUTS.items()},
                  'excluded': ['VPN additions', 'USB capture helpers', 'personal accounts and credentials'],
                  'hardware_installation_test': 'pending'}
    (output / 'BUILD-INPUTS.json').write_text(json.dumps(provenance, indent=2) + '\n')
    for p in output.iterdir():
        if p.name in {final.name, 'BUILD-INPUTS.json', 'IMAGE-SHA256SUMS', 'IMAGE-PRIVACY-REPORT.json'}:
            os.chown(p, int(os.environ.get('OUTPUT_UID', '0')), int(os.environ.get('OUTPUT_GID', '0')))


def compatibility(root):
    """Extract hash-pinned compatibility libraries from official Ubuntu archives."""
    root = Path(root).resolve()
    if root == Path('/') or not (root / 'usr/lib/aarch64-linux-gnu').is_dir(): raise ValueError('Invalid offline root')
    for package, (url, expected, patterns) in COMPAT_INPUTS.items():
        folder = Path('/build/compat') / package
        archive = fetch(url, expected, folder / 'package.deb')
        unpacked = folder / 'unpacked'; run('dpkg-deb', '-x', archive, unpacked)
        for pattern in patterns:
            matches = list((unpacked / 'usr/lib/aarch64-linux-gnu').glob(pattern))
            if not matches: raise ValueError('Missing compatibility library')
            for p in matches:
                target = root / 'usr/lib/aarch64-linux-gnu' / p.name
                if target.is_symlink(): target.unlink()
                if p.is_symlink(): target.symlink_to(p.readlink())
                else: copy_file(p, target, 0o644)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', default='0.0.1')
    p.add_argument('--inside', action='store_true')
    p.add_argument('--check', action='store_true')
    p.add_argument('--compat-root', type=Path)
    args = p.parse_args()
    try:
        if args.compat_root: compatibility(args.compat_root)
        else:
            check(args.version)
            if args.inside and not args.check: build(args.version)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        p.exit(1, 'Build stopped: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
