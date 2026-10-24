"""The package verifier preserves HOME while blocking host provider-key fallback."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app.gateway import Gateway
from scripts.verify_packaged_route import launch


ROOT = Path(__file__).resolve().parents[1]


class PackagedRouteIsolationTests(unittest.TestCase):
    def test_launch_removes_host_key_overrides_before_starting_backend(self):
        class StopBeforeSpawn(Exception):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / 'home'; home.mkdir()
            data = root / 'data'; data.mkdir()
            (data / 'harness').mkdir()
            config = json.loads((ROOT / 'harness/budget.json').read_text())
            (data / 'harness/budget.json').write_text(json.dumps(config))
            fake_key = root / 'fake-host.env'
            fake_key.write_text('DEEPSEEK_API_KEY=synthetic-host-key\n')
            host_home = root / 'host-home'; host_home.mkdir()
            inherited = {'HOME': str(host_home), 'PAGETIDE_KEY_FILE': str(fake_key), 'DEEPSEEK_API_KEY': ''}
            with mock.patch.dict(os.environ, inherited, clear=True):
                self.assertEqual(Gateway(root=data, data_dir=data)._load_key()[0], 'synthetic-host-key')
                with mock.patch('scripts.verify_packaged_route.subprocess.Popen', side_effect=StopBeforeSpawn) as spawn:
                    with self.assertRaises(StopBeforeSpawn):
                        launch(root / 'never-started-backend', data, home, lambda _: None)
                env = spawn.call_args.kwargs['env']
            self.assertEqual(env['PAGETIDE_KEY_FILE'], str(home / 'missing-key.env'))
            self.assertFalse(Path(env['PAGETIDE_KEY_FILE']).exists())
            self.assertNotEqual(env['PAGETIDE_KEY_FILE'], str(fake_key))
            self.assertEqual(env['DEEPSEEK_API_KEY'], '')
            self.assertEqual(env['HOME'], inherited['HOME'])
            self.assertEqual(env['PAGETIDE_DATA'], str(data))
            self.assertEqual(env['https_proxy'], 'http://127.0.0.1:9')
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(Gateway(root=data, data_dir=data)._load_key(), (None, None))
