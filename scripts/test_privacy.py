#!/usr/bin/env python3
"""Regression checks for public source and rootfs filtering."""
import io
from pathlib import Path
import tarfile
import unittest
from public_sources import audit
from sanitize_rootfs import allowed, transform


class PrivacyTests(unittest.TestCase):
    def test_personal_state_is_excluded(self):
        for path in ['home/phablet/.ssh/authorized_keys', 'etc/wireguard/profile.conf',
                     'etc/NetworkManager/system-connections/private-network',
                     'userdata/user-data/phablet/Documents/vault.txt',
                     'var/lib/bluetooth/AA:BB:CC:DD:EE:FF/info', 'var/log/journal/log',
                     'etc/ssh/ssh_host_ed25519_key', 'root/.bash_history',
                     'var/lib/a50-panel/backups/old.conf',
                     'etc/systemd/system/multi-user.target.wants/a50-mullvad.service']:
            with self.subTest(path=path):
                self.assertFalse(allowed(path, tarfile.TarInfo(path)))

    def test_shadow_passwords_are_locked(self):
        self.assertEqual(transform('etc/shadow', b'root:private-hash:1:0:99999:7:::\n'),
                         b'root:!:1:0:99999:7:::\n')

    def test_machine_identity_and_adb_defaults(self):
        self.assertEqual(transform('etc/machine-id', b'private-identity'), b'')
        self.assertIn(b'ADBD_SECURE=1', transform('etc/default/adbd', b'ADBD_SECURE=0\n'))

    def test_workstation_credentials_fail_source_audit(self):
        # Assemble a synthetic key header; no real private key is stored here.
        class FakeFile:
            suffix = '.txt'
            def read_bytes(self): return b'-----BEGIN ' + b'PRIVATE KEY-----\n'
        with self.assertRaisesRegex(ValueError, 'private key'):
            audit([(FakeFile(), Path('synthetic.txt'))])

    def test_system_account_paths_are_allowed(self):
        class FakeFile:
            suffix = '.sh'
            def read_bytes(self): return b'cd /home/' + b'phablet/Documents\n'
        audit([(FakeFile(), Path('synthetic.sh'))])


if __name__ == '__main__':
    unittest.main(verbosity=2)
