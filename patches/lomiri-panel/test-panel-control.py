#!/usr/bin/env python3
"""Exercise the real shell helper against simulated mounts and systemd."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


def fake_command():
    root = Path(os.environ['PANEL_TEST_ROOT'])
    state_file = root / 'state.json'
    state = json.loads(state_file.read_text())
    command, args = Path(sys.argv[0]).name, sys.argv[1:]
    with (root / 'calls.jsonl').open('a') as log:
        log.write(json.dumps([command, *args]) + '\n')
    result = 0
    if command == 'id':
        print('32011' if 'phablet' in args else '0')
    elif command == 'dpkg-query':
        print(state.get('version', '1'), end='')
    elif command == 'findmnt':
        print(state.get('source', str(root / 'a50-panel/custom/Panel'))
              if 'FSROOT' in args else 'ro' if state['readonly'] else 'rw')
    elif command == 'mountpoint':
        result = 0 if state['mounted'] else 1
    elif command == 'mount':
        if '--bind' in args:
            shutil.rmtree(root / 'Panel')
            shutil.copytree(root / 'a50-panel/custom/Panel', root / 'Panel')
            state['mounted'] = True
        elif args[-1] == '/':
            state['readonly'] = args[-2] == 'remount,ro'
    elif command == 'umount':
        if '-l' not in args and state.get('busy', False):
            print('umount: target is busy', file=sys.stderr)
            result = 32
        else:
            shutil.rmtree(root / 'Panel')
            shutil.copytree(root / 'a50-panel/stock/Panel', root / 'Panel')
            state['mounted'] = False
    elif command == 'systemctl':
        if args[0] == 'enable':
            state['enabled'] = True
        elif args[0] == 'disable':
            # A failed/inactive oneshot does not run ExecStop.
            state['enabled'] = False
        elif args[0] == 'is-failed':
            result = 0 if state.get('failed', False) else 1
        elif args[0] == 'reset-failed':
            # systemd may unload a successfully stopped, disabled oneshot.
            result = 0 if state.get('failed', False) else 1
            state['failed'] = False
    elif command == 'runuser':
        if 'is-active' in args and not state.get('session', True):
            result = 3
    elif command == 'systemd-run':
        state['restart_scheduled'] = True
    elif command == 'sha256sum':
        for line in Path(args[-1]).read_text().splitlines():
            digest, name = line.split('  ', 1)
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                result = 1
    else:
        raise AssertionError(command)
    state_file.write_text(json.dumps(state))
    return result


class PanelControlTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        base = self.root / 'a50-panel'
        for mode in ('stock', 'custom'):
            panel = base / mode / 'Panel'
            panel.mkdir(parents=True)
            (panel / 'Panel.qml').write_text(mode)
        (base / 'custom/Panel/A50QuickSettings.qml').touch()
        (base / 'lomiri-version').write_text('1')
        (base / 'stock.sha256').write_text(
            hashlib.sha256(b'stock').hexdigest() + '  Panel/Panel.qml\n')
        shutil.copytree(base / 'custom/Panel', self.root / 'Panel')
        self.state = dict(mounted=True, enabled=False, busy=True, readonly=True, failed=True)
        source = Path(__file__).with_name('a50-panel-control').read_text()
        source = source.replace('BASE=/var/lib/a50-panel', f'BASE={base}')
        source = source.replace('TARGET=/usr/share/lomiri/Panel', f'TARGET={self.root / "Panel"}')
        self.helper = self.root / 'control'
        self.helper.write_text(source)
        self.helper.chmod(0o755)
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        for name in ('id', 'dpkg-query', 'findmnt', 'mountpoint', 'mount',
                     'umount', 'systemctl', 'runuser', 'systemd-run', 'sha256sum'):
            executable = bin_dir / name
            executable.write_text(f'#!{sys.executable}\n' + Path(__file__).read_text())
            executable.chmod(0o755)
        self.env = dict(os.environ, PANEL_TEST_ROOT=str(self.root),
                        PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])

    def run_helper(self, *args):
        (self.root / 'state.json').write_text(json.dumps(self.state))
        result = subprocess.run([str(self.helper), *args], env=self.env,
                                capture_output=True, text=True)
        self.state = json.loads((self.root / 'state.json').read_text())
        return result

    def calls(self):
        return [json.loads(line) for line in
                (self.root / 'calls.jsonl').read_text().splitlines()]

    def test_stock_detaches_busy_mount_left_by_failed_service(self):
        result = self.run_helper('stock', '--restart')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.state['mounted'])
        self.assertFalse(self.state['enabled'])
        self.assertFalse(self.state['failed'])
        self.assertTrue(self.state['readonly'])
        self.assertTrue(self.state['restart_scheduled'])
        self.assertIn(['umount', '-l', str(self.root / 'Panel')], self.calls())
        self.assertEqual((self.root / 'Panel/Panel.qml').read_text(), 'stock')

    def test_custom_repairs_mount_even_if_service_was_already_enabled(self):
        self.assertEqual(self.run_helper('stock').returncode, 0)
        self.state['enabled'] = True
        result = self.run_helper('custom', '--restart')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.state['mounted'])
        self.assertTrue(self.state['enabled'])
        self.assertTrue(self.state['readonly'])
        self.assertEqual((self.root / 'Panel/Panel.qml').read_text(), 'custom')

    def test_stock_is_repeatable(self):
        for _ in range(2):
            result = self.run_helper('stock')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.state.get('restart_scheduled', False))

    def test_refuses_unrelated_mount(self):
        self.state['source'] = '/another/installation'
        result = self.run_helper('stock', '--restart')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state['mounted'])
        self.assertTrue(self.state['readonly'])
        self.assertFalse(self.state.get('restart_scheduled', False))
        self.assertFalse(any(call[0] == 'umount' for call in self.calls()))

    def test_custom_rejects_package_version_mismatch(self):
        self.state['version'] = '2'
        result = self.run_helper('custom', '--restart')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.state['enabled'])
        self.assertFalse(self.state.get('restart_scheduled', False))

    def test_failed_stock_verification_does_not_claim_success(self):
        (self.root / 'a50-panel/stock/Panel/Panel.qml').write_text('corrupted')
        result = self.run_helper('stock', '--restart')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('restored and verified', result.stdout)
        self.assertFalse(self.state.get('restart_scheduled', False))
        self.assertTrue(self.state['readonly'])

    def test_missing_session_fails_before_changing_panel(self):
        self.state['session'] = False
        result = self.run_helper('stock', '--restart')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state['mounted'])
        self.assertFalse(any(call[0] == 'systemctl' for call in self.calls()))


if __name__ == '__main__':
    if 'PANEL_TEST_ROOT' in os.environ:
        sys.exit(fake_command())
    unittest.main()
