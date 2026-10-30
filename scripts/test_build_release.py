#!/usr/bin/env python3
"""Check the release pipeline using small fixtures; never assemble a phone image."""
import gzip
import hashlib
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from build_release import check, fetch, source_archive, make_boot, apply_patches
from strip_optional_features import strip, check as check_features


class ReleaseBuildTests(unittest.TestCase):
    def test_build_plan_and_version(self):
        check('0.0.1')
        for version in ['latest', '0.0.1\nvariant=devel', '../release']:
            with self.assertRaises(ValueError): check(version)

    def test_hash_checked_download(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);source=p/'source';source.write_bytes(b'public input')
            target=p/'download';expected=hashlib.sha256(source.read_bytes()).hexdigest()
            fetch(source.as_uri(),expected,target)
            self.assertEqual(target.read_bytes(),b'public input')
            target.write_bytes(b'corrupted')
            with self.assertRaises(ValueError):fetch(source.as_uri(),expected,target)
            target.unlink()
            with self.assertRaises(ValueError):fetch(source.as_uri(),'0'*64,target)
            self.assertFalse(target.exists());self.assertFalse((p/'download.part').exists())

    def test_source_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with tarfile.open(p/'source.tar','w') as t:
                m=tarfile.TarInfo('project/../outside');m.size=4;t.addfile(m,io.BytesIO(b'data'))
            with self.assertRaises(ValueError):source_archive(p/'source.tar',p/'extracted')
            self.assertFalse((p/'outside').exists())

    def test_source_overlay_link_preserved_without_following(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with tarfile.open(p/'source.tar','w') as t:
                m=tarfile.TarInfo('project/overlay/system/etc/resolv.conf')
                m.type=tarfile.SYMTYPE;m.linkname='/run/resolvconf/resolv.conf';t.addfile(m)
            source_archive(p/'source.tar',p/'extracted')
            self.assertEqual(str((p/'extracted/overlay/system/etc/resolv.conf').readlink()),'/run/resolvconf/resolv.conf')

    def test_boot_repack_uses_only_declared_sections(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);old=b'old kernel';new=b'public replacement kernel'
            ramdisk=gzip.compress(b'public ramdisk');header=bytearray(2048);header[:8]=b'ANDROID!'
            struct.pack_into('<I',header,8,len(old));struct.pack_into('<I',header,16,len(ramdisk))
            struct.pack_into('<I',header,36,2048);struct.pack_into('<I',header,40,1)
            pad=lambda b:b+bytes((-len(b))%2048)
            (p/'donor').write_bytes(header+pad(old)+pad(ramdisk)+b'unused old partition slack')
            with tarfile.open(p/'kernel.tar','w') as t:
                m=tarfile.TarInfo('out/Image');m.size=len(new);t.addfile(m,io.BytesIO(new))
            make_boot(p/'donor',p/'kernel.tar',p/'boot')
            data=(p/'boot').read_bytes()
            self.assertEqual(struct.unpack_from('<I',data,8)[0],len(new))
            self.assertEqual(data[2048:2048+len(new)],new)
            self.assertNotIn(b'unused old partition slack',data)

    def test_offline_installer_refuses_live_root(self):
        with self.assertRaises(ValueError):apply_patches(Path('/'))

    def test_vpn_files_and_package_records_removed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            entries={
                'var/lib/dpkg/status':b'Package: wireguard-tools\nStatus: install ok installed\n\nPackage: core\nStatus: install ok installed\n\n',
                'var/lib/dpkg/info/wireguard-tools.list':b'/usr/bin/wg\n',
                'usr/bin/wg':b'vpn executable',
                'usr/local/bin/a50-vpn-toggle':b'vpn helper',
                'etc/resolvconf/interface-order':b'tun.mullvad\nlo.*\n',
                'usr/bin/core':b'essential',
            }
            with tarfile.open(p/'input.tar','w') as t:
                for n,data in entries.items():
                    m=tarfile.TarInfo(n);m.size=len(data);t.addfile(m,io.BytesIO(data))
            strip(p/'input.tar',p/'output.tar');check_features(p/'output.tar')
            with tarfile.open(p/'output.tar') as t:
                names=t.getnames();self.assertNotIn('usr/bin/wg',names)
                self.assertNotIn('usr/local/bin/a50-vpn-toggle',names)
                self.assertEqual(t.extractfile('usr/bin/core').read(),b'essential')
                self.assertNotIn(b'wireguard-tools',t.extractfile('var/lib/dpkg/status').read())


if __name__ == '__main__':
    unittest.main(verbosity=2)
