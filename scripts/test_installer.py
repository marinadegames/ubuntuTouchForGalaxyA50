#!/usr/bin/env python3
"""Run installer failure paths against temporary regular files, never a phone."""
import gzip
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
import zipfile

SCRIPT = (Path(__file__).resolve().parent.parent / 'installer/install/a50-install.sh').read_text()


class InstallerTests(unittest.TestCase):
    def run_install(self, *, model='SM-A505F', existing=False, bad_root=False, bad_boot=False, bad_readback=False):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary)
            data = p / 'data'; data.mkdir()
            tmp = p / 'unpack'; tmp.mkdir()
            bootdev = p / 'boot-device'; bootdev.write_bytes(b'unchanged')
            boot = b'new boot image'; root = b'clean root filesystem' * 200
            if existing: (data / 'user-data').mkdir()
            sha = lambda v: hashlib.sha256(v).hexdigest()
            payload = p / 'install.zip'
            with zipfile.ZipFile(payload, 'w') as z:
                z.writestr('install/boot.img', boot)
                z.writestr('install/rootfs.img.gz', gzip.compress(root))
                z.writestr('install/manifest.txt', f'rootfs_bytes={len(root)}\n')
                z.writestr('install/SHA256SUMS', f'{sha(boot) if not bad_boot else "0"*64}  boot.img\n{sha(root) if not bad_root else "0"*64}  rootfs.img\n')
            # Substitute only the hardware boundary and /data. The production
            # verification, write order and activation logic execute unchanged.
            body = SCRIPT[SCRIPT.index('model=$(getprop'):].replace('/data', str(data))
            q = shlex.quote
            wrappers = f'''
ZIP={q(str(payload))}
TMP={q(str(tmp))}
BOOT_BYTES=57671680
ROOTFS_TARGET={q(str(data / 'ubuntu.img'))}
STAGED_ROOTFS={q(str(data / '.a50-ubuntu.img.new'))}
getprop() {{ echo {q(model)}; }}
find_part() {{ echo {q(str(bootdev))}; }}
cat() {{ case "$1" in /sys/class/block/*/size) echo 112640 ;; *) command cat "$@" ;; esac; }}
mount() {{ return 0; }}
grep() {{ case "$*" in *'/proc/mounts'*) return 0 ;; *) command grep "$@" ;; esac; }}
df() {{ echo 'Filesystem 1K-blocks Used Available'; echo 'fixture 9999999 0 9999999'; }}
stat() {{ python3 -c 'import os,sys; print(os.stat(sys.argv[1]).st_size)' "$2"; }}
sha256sum() {{ shasum -a 256 "$@"; }}
sync() {{ return 0; }}
ui_print() {{ echo "$1"; }}
abort() {{ echo "$1" >&2; exit 1; }}
'''
            if bad_readback:
                wrappers += f'dd() {{ case "$*" in *"of={str(bootdev)}"*) printf corrupt > {q(str(bootdev))} ;; *) command dd "$@" ;; esac; }}\n'
            result = subprocess.run(['sh', '-c', wrappers + body], capture_output=True, text=True)
            return result, bootdev.read_bytes(), (data / 'ubuntu.img').read_bytes() if (data / 'ubuntu.img').exists() else None, boot, root

    def test_verified_payload_installs(self):
        r, got_boot, got_root, boot, root = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(got_boot, boot); self.assertEqual(got_root, root)

    def test_wrong_model_never_writes_boot(self):
        r, boot, root, _, _ = self.run_install(model='SM-A505FN')
        self.assertNotEqual(r.returncode, 0); self.assertEqual(boot, b'unchanged'); self.assertIsNone(root)

    def test_existing_userdata_is_rejected(self):
        r, boot, root, _, _ = self.run_install(existing=True)
        self.assertNotEqual(r.returncode, 0); self.assertEqual(boot, b'unchanged'); self.assertIsNone(root)

    def test_corrupt_rootfs_never_writes_boot(self):
        r, boot, root, _, _ = self.run_install(bad_root=True)
        self.assertNotEqual(r.returncode, 0); self.assertEqual(boot, b'unchanged'); self.assertIsNone(root)

    def test_corrupt_boot_never_activates_rootfs(self):
        r, boot, root, _, _ = self.run_install(bad_boot=True)
        self.assertNotEqual(r.returncode, 0); self.assertEqual(boot, b'unchanged'); self.assertIsNone(root)

    def test_boot_readback_failure_never_activates_rootfs(self):
        r, _, root, _, _ = self.run_install(bad_readback=True)
        self.assertNotEqual(r.returncode, 0); self.assertIsNone(root)
        self.assertIn('read-back mismatch', r.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
