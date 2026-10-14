import dataclasses
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import zapret_manager as manager


class SettingsTests(unittest.TestCase):
    def test_reject_bad_values(self):
        for fields in ({'game': 'bad'}, {'ipset': 'bad'}, {'strategy': 'bad'},
                       {'excluded_uids': [-1]}, {'excluded_uids': [True]},
                       {'excluded_ips': ['1.2.3.4/33']}, {'excluded_domains': ['a; rm -rf /']}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                manager.Settings(**fields).validate()

    def test_save_and_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'settings.json'
            settings = manager.Settings(game='udp', ipset='loaded', excluded_ips=['2001:db8::/32'])
            manager.atomic_save(settings, path)
            self.assertEqual(manager.load_settings(path), settings)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                manager.atomic_save(manager.Settings(game='oops'), path)
            self.assertEqual(path.read_bytes(), before)

    def test_rules_do_not_touch_other_firewalls(self):
        rules = manager.nft_rules(manager.Settings(excluded_uids=[1000]))
        self.assertIn('table inet zapret2_manager', rules)
        self.assertNotIn('flush', rules)
        self.assertNotIn('oifname', rules)
        self.assertIn('queue num 200 bypass', rules)
        self.assertIn('meta mark & 0x40000000 != 0 return', rules)
        self.assertIn('meta skuid { 1000 }', rules)
        self.assertIn('ct mark & 0x20000000 != 0 return', rules)

    def test_https_probe_classifies_content(self):
        responses = []
        for status, body in ((200, b'ytInitialData'), (204, b''), (200, b'{"url":"wss://gateway.discord.gg"}'), (403, b'Forbidden')):
            response = unittest.mock.MagicMock()
            response.__enter__.return_value = response
            response.status = status
            response.read.return_value = body
            responses.append(response)
        opener = unittest.mock.Mock()
        opener.open.side_effect = responses
        with patch('urllib.request.build_opener', return_value=opener):
            result = manager.network_probes()
        self.assertEqual([x['success'] for x in result['probes']], [True, True, True, False])
        self.assertIn('Anti-Cheat', result['note'])

    def test_systemd_notified_only_explicitly(self):
        import socket
        with tempfile.TemporaryDirectory() as temp, socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
            path = str(Path(temp) / 'notify')
            server.bind(path)
            server.settimeout(1)
            with patch.dict(manager.os.environ, {'NOTIFY_SOCKET': path}):
                manager.notify_ready()
            self.assertEqual(server.recv(1024), b'READY=1')

    def test_detect_queue_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'queues'
            self.assertIsNone(manager.queue_owner(path))
            path.write_text(' 199 42 0 2\n 200 1234 0 2\n')
            self.assertEqual(manager.queue_owner(path), 1234)

    def test_refuse_foreign_table(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({'nftables': [{'table': {'name': manager.TABLE}}]}), '')
        with patch.object(manager.subprocess, 'run', return_value=result), patch.object(manager, 'checked') as checked:
            with self.assertRaises(RuntimeError):
                manager.remove_table()
            checked.assert_not_called()

    def test_cleanup_after_nft_failure(self):
        child = unittest.mock.Mock(pid=1234)
        child.poll.return_value = None
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(manager, 'require_root'), \
                patch.object(manager, 'validate_engine'), \
                patch.object(manager, 'engine', return_value=Path('/fake/nfqws2')), \
                patch.object(manager, 'build_args', return_value=[]), \
                patch.object(manager.shutil, 'which', return_value='/sbin/nft'), \
                patch.object(manager.Path, 'mkdir'), \
                patch('builtins.open', return_value=open(Path(temp) / 'lock', 'w')), \
                patch.object(manager, 'queue_owner', side_effect=[None, 1234]), \
                patch.object(manager, 'remove_table') as cleanup, \
                patch.object(manager.subprocess, 'Popen', return_value=child), \
                patch.object(manager, 'checked', side_effect=RuntimeError('nft failed')):
            with self.assertRaisesRegex(RuntimeError, 'nft failed'):
                manager.supervise(manager.Settings())
            self.assertEqual(cleanup.call_count, 2)
            child.terminate.assert_called_once()
            child.wait.assert_called_once()


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not manager.RUNTIME.exists():
            raise unittest.SkipTest('Run tests from the packaged release for real engine checks')

    def test_all_profiles_real_engine(self):
        for game in ('off', 'tcp', 'udp', 'all'):
            for ipset in ('none', 'loaded', 'any'):
                for strategy in ('current', 'split', 'disorder'):
                    with self.subTest(game=game, ipset=ipset, strategy=strategy):
                        manager.validate_engine(manager.Settings(game=game, ipset=ipset, strategy=strategy,
                            excluded_ips=['192.0.2.0/24', '2001:db8::/32'], excluded_domains=['example.org']))

    def test_paths_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='zapret path with spaces ') as temp:
            link = Path(temp) / 'runtime'
            link.symlink_to(manager.RUNTIME.resolve(), target_is_directory=True)
            manager.validate_engine(manager.Settings(game='all', ipset='loaded'), link)

    def test_no_windows_args(self):
        args = manager.build_args(manager.Settings(game='all', ipset='any'))
        self.assertFalse(any(x.startswith('--wf-') or '%ROOT%' in x for x in args))
        self.assertIn('--filter-tcp=1024-65535', args)
        self.assertIn('--filter-udp=1024-65535', args)
        # Unknown game UDP intentionally has IP filters only, not domain filters.
        section = args[args.index('--filter-udp=1024-65535'):]
        self.assertFalse(any(x.startswith('--hostlist=') for x in section))


if __name__ == '__main__':
    unittest.main()
