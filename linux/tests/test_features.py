import base64
from contextlib import ExitStack
import dataclasses
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import zapret_manager as zm
import zaper_state as state
import zaper_maintenance as maintenance
import zaper_preferences as preferences


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target, name, value in ((state, 'STATE', self.root / 'state'), (zm, 'CONFIG', self.root / 'config/settings.json'),
                                    (state, 'IP_OVERLAY', self.root / 'config/ipset-all.txt')):
            self.stack.enter_context(patch.object(target, name, value))
        self.stack.enter_context(patch.object(zm, 'validate_engine', return_value='valid'))

    def test_settings_history_restore_includes_exclusions(self):
        before = zm.Settings(game='udp', ipset='loaded', excluded_domains=['example.org'], excluded_uids=[1234])
        state.save_settings(before)
        identity = state.save_settings(zm.Settings(game='off'))
        self.assertEqual(len(state.history()), 2)
        state.restore(identity)
        self.assertEqual(zm.load_settings(), before)
        self.assertEqual(len(state.history()), 3)

    def test_restore_valid_history_when_current_settings_are_corrupt(self):
        identity = state.save_settings(zm.Settings(game='tcp', ipset='any'))
        original = state.save_settings(zm.Settings())
        zm.CONFIG.write_text('corrupt json')
        state.restore(original)
        self.assertEqual(zm.load_settings().game, 'tcp')
        self.assertTrue(any('raw_settings_base64' in x.read_text() for x in (state.STATE / 'history').glob('*.json')))

    def test_partial_settings_change_reads_current_state_under_lock(self):
        state.save_settings(zm.Settings(excluded_domains=['preserve.example.org']))
        def changed(current):
            current.game = 'udp'
            return current
        state.save_settings(changed)
        self.assertEqual(zm.load_settings().excluded_domains, ['preserve.example.org'])
        self.assertEqual(zm.load_settings().game, 'udp')

    def test_invalid_history_identity_cannot_escape_directory(self):
        for identity in ('../../etc/passwd', '/etc/hosts', 'x.json'):
            with self.assertRaises(ValueError): state.restore(identity)

    def test_failed_write_keeps_settings_and_backup(self):
        original = zm.Settings(game='tcp', ipset='any')
        state.save_settings(original)
        with patch.object(zm, 'atomic_save', side_effect=OSError('read only')):
            with self.assertRaises(OSError): state.save_settings(zm.Settings())
        self.assertEqual(zm.load_settings(), original)
        self.assertEqual(len(state.history()), 2)

    def test_invalid_profile_does_not_write_or_create_history(self):
        value = state.profile(zm.Settings())
        value['settings']['game'] = 'invalid'
        with self.assertRaises(ValueError): state.import_profile(value)
        self.assertFalse(zm.CONFIG.exists())
        self.assertFalse(state.history())

    def test_linux_and_windows_profile_import(self):
        settings = zm.Settings(game='all', ipset='loaded', excluded_ips=['2001:db8::/32'])
        imported, skipped = state.import_profile(state.profile(settings, 'Fixture'))
        self.assertEqual(imported, settings)
        self.assertFalse(skipped)
        windows = {'Name': 'Игры', 'Settings': {'Game': 'udp', 'IPSet': 'loaded', 'StrategyId': 'host-seq', 'GameUdpPreset': 'alt12-exp'},
                   'Applications': [r'C:\Users\Alice\game.exe']}
        imported, skipped = state.import_profile(windows)
        self.assertEqual((imported.strategy, imported.game_udp_preset), ('host-seq', 'alt12-exp'))
        self.assertEqual(skipped, ['game.exe'])

    def test_foreign_profile_schema_rejected(self):
        for profile in (None, [], {}, {'schema': 999, 'application': 'Zaper', 'platform': 'linux'}, {'Settings': []}):
            with self.assertRaises((ValueError, TypeError, KeyError)): state.import_profile(profile)

    def test_operation_lock_prevents_overlapping_writes(self):
        with state.operation():
            with self.assertRaisesRegex(RuntimeError, 'операции'): state.save_settings(zm.Settings())
        self.assertFalse(zm.CONFIG.exists())

    def test_launch_preferences_autostart_is_idempotent_and_separate(self):
        prefs = preferences.Preferences(start_in_tray=True, panel_autostart=True, notify_errors=False)
        preferences.save(prefs, self.root)
        self.assertEqual(preferences.load(self.root), prefs)
        launch = self.root / 'autostart/zaper.desktop'
        self.assertIn('zapret2-manager-gui --tray', launch.read_text())
        with patch.object(zm, 'service') as service:
            preferences.save(preferences.Preferences(), self.root)
            preferences.save(preferences.Preferences(), self.root)
            service.assert_not_called()
        self.assertFalse(launch.exists())

    def test_launch_preferences_roll_back_autostart_if_save_fails(self):
        prefs = preferences.Preferences(panel_autostart=True)
        preferences.save(prefs, self.root)
        launch = (self.root / 'autostart/zaper.desktop').read_bytes()
        real = state.atomic_bytes
        def fail(path, content, mode=0o644):
            if path.name == 'preferences.json': raise OSError('read only')
            real(path, content, mode)
        with patch.object(state, 'atomic_bytes', side_effect=fail):
            with self.assertRaises(OSError): preferences.save(preferences.Preferences(), self.root)
        self.assertEqual((self.root / 'autostart/zaper.desktop').read_bytes(), launch)
        self.assertEqual(preferences.load(self.root), prefs)

    def test_hosts_save_detects_conflict_and_keeps_backup(self):
        path = self.root / 'hosts'
        original = b'127.0.0.1 localhost\n::1 localhost\n# Keep comment\n'
        path.write_bytes(original)
        expected = hashlib.sha256(original).hexdigest()
        updated = original.decode() + '192.0.2.1 example.org\n'
        backup = maintenance.save_hosts(updated, expected, path)
        self.assertEqual(Path(backup).read_bytes(), original)
        self.assertEqual(path.read_text(), updated)
        with self.assertRaisesRegex(RuntimeError, 'другой программой'):
            maintenance.save_hosts('127.0.0.1 localhost\n', expected, path)
        self.assertEqual(path.read_text(), updated)

    def test_hosts_merge_preserves_unrelated_mappings_and_comments(self):
        original = '127.0.0.1 localhost\n1.2.3.4 old.example keep.example # retain\n'
        result = maintenance.merge_hosts(original, '8.8.8.8 old.example\n')
        self.assertIn('127.0.0.1 localhost', result)
        self.assertIn('1.2.3.4\tkeep.example # retain', result)
        self.assertIn('8.8.8.8 old.example', result)
        with self.assertRaises(ValueError): maintenance.validate_hosts('not-ip invalid\n')

    def test_ip_update_fallback_and_overlay_without_runtime_mutation(self):
        payload = json.dumps({'content': base64.b64encode(b'192.0.2.0/24\n2001:db8::/32\n').decode()})
        with patch.object(maintenance, 'download', side_effect=['<!doctype html>', payload]), \
             patch.object(maintenance, 'service_active', return_value=False), patch.object(zm, 'queue_owner', return_value=None):
            result = maintenance.update_ips()
        self.assertEqual(result['networks'], 2)
        self.assertIn('2001:db8::/32', state.IP_OVERLAY.read_text())

    def test_failed_ip_validation_restores_existing_file(self):
        state.IP_OVERLAY.parent.mkdir(parents=True)
        state.IP_OVERLAY.write_text('198.51.100.0/24\n')
        with patch.object(maintenance, 'download', return_value='192.0.2.0/24\n'), \
             patch.object(maintenance, 'service_active', return_value=False), patch.object(zm, 'queue_owner', return_value=None), \
             patch.object(zm, 'validate_engine', side_effect=RuntimeError('rejected')):
            with self.assertRaises(RuntimeError): maintenance.update_ips()
        self.assertEqual(state.IP_OVERLAY.read_text(), '198.51.100.0/24\n')

    def test_unavailable_ip_sources_leave_current_file_unchanged(self):
        state.IP_OVERLAY.parent.mkdir(parents=True)
        state.IP_OVERLAY.write_text('192.0.2.0/24\n')
        with patch.object(maintenance, 'download', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError): maintenance.update_ips()
        self.assertEqual(state.IP_OVERLAY.read_text(), '192.0.2.0/24\n')

    def test_diagnostics_redacts_secrets_and_home_paths(self):
        text = 'secret=privateValue\npassword=privatePassword\nAuthorization: Bearer privateToken\n{"token":"jsonSecret"}\n/home/Alice/folder\n'
        result = state.redact(text)
        for secret in ('privateValue', 'privatePassword', 'privateToken', 'jsonSecret', 'Alice'):
            self.assertNotIn(secret, result)
        with patch.object(zm, 'diagnostics', return_value={'path': '/home/Alice/code'}), patch.object(maintenance.shutil, 'which', return_value=None):
            archive = maintenance.diagnostics_zip()
        with zipfile.ZipFile(io.BytesIO(archive)) as content:
            self.assertEqual(set(content.namelist()), {'summary.json', 'settings.json'})
            self.assertNotIn('Alice', content.read('summary.json').decode())


class PackagedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not zm.RUNTIME.exists(): raise unittest.SkipTest('Run from packaged release')

    def test_all_nine_strategies_and_both_game_presets(self):
        for strategy in zm.STRATEGIES:
            for preset in ('native', 'alt12-exp'):
                for game in ('off', 'tcp', 'udp', 'all'):
                    for ipset in ('none', 'loaded', 'any'):
                        with self.subTest(strategy=strategy, preset=preset, game=game, ipset=ipset):
                            zm.validate_engine(zm.Settings(strategy=strategy, game_udp_preset=preset, game=game, ipset=ipset))

    def test_runtime_backup_restores_corrupt_file_without_losing_user_lists(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'installed'
            home.mkdir()
            for name in ('runtime-repair.tar.gz', 'runtime-repair.sha256'):
                shutil.copy2(zm.HOME / name, home / name)
            shutil.copytree(zm.RUNTIME, home / 'runtime')
            (home / 'runtime/lua/zapret-lib.lua').write_text('corrupt')
            user = home / 'runtime/lists/list-general-user.txt'
            user.write_text('custom.example.org\n')
            with patch.object(zm, 'HOME', home), patch.object(zm, 'RUNTIME', home / 'runtime'), \
                 patch.object(zm, 'validate_engine', return_value='valid'), patch.object(zm, 'queue_owner', return_value=None), \
                 patch.object(maintenance, 'service_active', return_value=False), patch.object(state, 'STATE', home / 'state'):
                result = maintenance.repair()
                self.assertTrue(result['repaired'])
                self.assertNotEqual((home / 'runtime/lua/zapret-lib.lua').read_text(), 'corrupt')
                self.assertEqual(user.read_text(), 'custom.example.org\n')

    def test_corrupt_repair_archive_is_rejected_before_mutation(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'runtime-repair.tar.gz').write_bytes(b'corrupt')
            (home / 'runtime-repair.sha256').write_text('0' * 64)
            with patch.object(zm, 'HOME', home), self.assertRaises(ValueError): maintenance.repair()


if __name__ == '__main__':
    unittest.main()

class DownloadTests(unittest.TestCase):
    def test_real_curl_https_direct_route_and_trusted_certificate(self):
        import http.server
        import shutil
        import ssl
        import threading
        if not shutil.which('openssl') or not shutil.which('curl'):
            self.skipTest('curl/openssl are required for real HTTPS download fixture')
        with tempfile.TemporaryDirectory() as temp:
            cert, key = Path(temp) / 'cert.pem', Path(temp) / 'key.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-days', '1', '-nodes',
                            '-keyout', str(key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
                            '-addext', 'subjectAltName=IP:127.0.0.1'], capture_output=True, check=True)
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    body = b'192.0.2.0/24\n2001:db8::/32\n'
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                def log_message(self, *args): pass
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with patch.dict(os.environ, {'CURL_CA_BUNDLE': str(cert), 'HTTPS_PROXY': 'http://127.0.0.1:9'}):
                    text = maintenance.download(f'https://127.0.0.1:{server.server_port}/list')
                self.assertEqual(maintenance.validate_ipset(text), 2)
            finally:
                server.shutdown(); server.server_close(); worker.join(timeout=3)
