"""Safe provider contract failures must explain the guidance failure in place."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import creation
from app.service import App


class GuidanceErrorDiagnosticsTests(unittest.TestCase):
    def test_known_json_400_identifies_app_request_format_in_both_languages(self):
        result = {'ok': False, 'http_status': 400, 'reason': 'HTTPError: 400',
                  'provider_error': 'json_instruction_missing'}
        for english in (False, True):
            with self.subTest(english=english):
                code, text = creation.degrade_reason(result, english)
                self.assertEqual(code, 'request_format')
                self.assertIn('HTTP 400', text)
                self.assertIn('JSON', text)
                self.assertNotIn('shorten', text)
                self.assertNotIn('缩短', text)

    def test_unrecognized_status_or_provider_classification_stays_generic(self):
        for status, diagnostic in ((401, 'json_instruction_missing'),
                                   (400, 'synthetic-private-provider-message'),
                                   (400, None)):
            result = {'http_status': status, 'reason': f'HTTPError: {status}',
                      'provider_error': diagnostic}
            code, text = creation.degrade_reason(result)
            self.assertEqual(code, 'http')
            self.assertNotIn('synthetic-private', text)
            if status == 401:
                self.assertIn('密钥', text)

    def test_guidance_result_retains_draft_and_shows_the_safe_format_cause(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app = App(root=Path(__file__).resolve().parents[1], data_dir=Path(temp.name))
        self.addCleanup(app.store.close)
        session = app.create_guidance_session('Project', 'world model planning')
        with mock.patch.object(app.gateway, 'call', return_value={
                'ok': False, 'degraded': True, 'http_status': 400,
                'reason': 'HTTPError: 400', 'provider_error': 'json_instruction_missing'}):
            out = app.guidance_turn(session['id'], 'world model planning')
        self.assertEqual(out['mode'], 'local')
        entry = out['session']['transcript'][-1]
        self.assertEqual(out['reason_code'], 'request_format')
        self.assertEqual(entry['reason'], 'request_format')
        self.assertIn('JSON', entry['reason_text'])
        self.assertIn('HTTP 400', entry['reason_text'])
        self.assertTrue(out['session']['draft']['route_draft']['graph']['concepts'])
        self.assertEqual(out['session']['draft']['goal'], session['draft']['goal'])
        self.assertNotIn('provider_error', json.dumps(entry))
