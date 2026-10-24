"""Explicit, secret-safe connectivity check; disposable roots and mocked provider."""
import json
import http.client
from contextlib import contextmanager
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.service import App
from app import operation_lock
from app.organization import Conflict
from tests import test_app_server, test_provider_settings

ROOT = Path(__file__).resolve().parents[1]


class AIConnectionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'root'; (root / 'harness').mkdir(parents=True)
        (root / 'harness/budget.json').write_bytes((ROOT / 'harness/budget.json').read_bytes())
        self.app = App(root=root, data_dir=Path(tmp.name) / 'data')
        self.addCleanup(self.app.store.close)
        self.app.gateway.set_enabled(False)
        self.call = mock.Mock(return_value={'ok': True, 'content': 'secret-should-not-echo',
            'model': 'secret-should-not-echo', 'usage': {'prompt_tokens': 10, 'completion_tokens': 2,
            'total_tokens': 12, 'secret': 'secret-should-not-echo'}, 'usd': '0.0000054'})
        self.app.gateway.test_connection = self.call

    def test_temporary_key_is_tested_once_without_saving_switch_or_content(self):
        result = self.app.test_ai_connection('sk-temporary-test')
        self.call.assert_called_once_with(test_key='sk-temporary-test')
        self.assertTrue(result['ok'])
        self.assertEqual(result['model'], self.app.gateway.config['provider']['model'])
        self.assertEqual(result['provider'], 'DeepSeek')
        self.assertEqual(result['usage']['total_tokens'], 12)
        self.assertNotIn('secret-should-not-echo', json.dumps(result))
        self.assertNotIn('sk-temporary-test', json.dumps(result))
        self.assertFalse(self.app.gateway.enabled())
        self.assertFalse(self.app.gateway.key_file().exists())
        self.assertIsInstance(result['elapsed_ms'], int)

    def test_saved_key_path_uses_none_and_does_not_enable_ai(self):
        self.assertTrue(self.app.test_ai_connection()['ok'])
        self.call.assert_called_once_with(test_key=None)
        self.assertFalse(self.app.gateway.enabled())

    def test_invalid_temporary_credentials_are_rejected_before_gateway(self):
        for value in ('', ' ', 'sk-a\nsk-b', 'sk-a\rsk-b', 'a' * 501, 3, {}, True):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ValueError): self.app.test_ai_connection(value)
        self.call.assert_not_called()

    def test_authentication_cause_is_specific_without_raw_secret(self):
        self.call.return_value = {'ok': False, 'http_status': 401,
                                 'reason': 'HTTPError: 401 secret-should-not-echo'}
        result = self.app.test_ai_connection()
        self.assertFalse(result['ok']); self.assertEqual(result['reason_code'], 'http')
        self.assertIn('401', result['reason']); self.assertIn('密钥', result['reason'])
        self.assertNotIn('secret-should-not-echo', json.dumps(result))

    def test_unknown_usage_is_not_returned_as_measured_usage(self):
        self.call.return_value = {'ok': True, 'content': 'OK', 'usage_unknown': True,
            'usage_reserved': True, 'usage': {'total_tokens': 784}, 'usd': '0.0002496',
            'reservation': {'input': 768, 'output': 16, 'usd': '0.0002496'}}
        result = self.app.test_ai_connection()
        self.assertTrue(result['ok']); self.assertIsNone(result['usage']); self.assertIsNone(result['usd'])
        self.assertTrue(result['usage_unknown']); self.assertTrue(result['usage_reserved'])
        self.assertEqual(result['reservation']['input'], 768)
        self.assertIn('未确认', result['reason'])

    def test_network_cause_retains_accounting_uncertainty(self):
        self.call.return_value = {'ok': False, 'reason': 'URLError: secret-should-not-echo',
                                 'usage_unknown': True, 'usage_reserved': True}
        result = self.app.test_ai_connection()
        self.assertFalse(result['ok']); self.assertEqual(result['reason_code'], 'network')
        self.assertTrue(result['usage_unknown']); self.assertTrue(result['usage_reserved'])
        self.assertNotIn('secret-should-not-echo', json.dumps(result))

    def test_presend_accounting_failure_is_known_unused_without_reservation(self):
        self.call.return_value = {'ok': False, 'tracking_failed': True, 'nothing_sent': True,
                                  'usage_unknown': False, 'usage_reserved': False,
                                  'reason': 'PermissionError secret-should-not-echo'}
        result = self.app.test_ai_connection()
        self.assertFalse(result['ok']); self.assertEqual(result['reason_code'], 'accounting_failed')
        self.assertFalse(result['usage_unknown']); self.assertFalse(result['usage_reserved'])
        self.assertIsNone(result['reservation']); self.assertIn('未发送', result['reason'])
        self.assertNotIn('secret-should-not-echo', json.dumps(result))

    def test_unexpected_failure_does_not_invent_a_preserved_reservation(self):
        self.call.side_effect = RuntimeError('secret-should-not-echo')
        result = self.app.test_ai_connection()
        self.assertFalse(result['ok']); self.assertEqual(result['reason_code'], 'accounting_failed')
        self.assertTrue(result['usage_unknown']); self.assertFalse(result['usage_reserved'])
        self.assertIsNone(result['reservation']); self.assertIsNone(result['usage'])
        self.assertIn('未确认', result['reason']); self.assertNotIn('secret-should-not-echo', json.dumps(result))

    def test_postsend_accounting_failure_keeps_recorded_reservation_unknown(self):
        self.call.return_value = {'ok': False, 'tracking_failed': True,
            'usage_unknown': True, 'usage_reserved': True,
            'reservation': {'input': 768, 'output': 16, 'usd': '0.0002496'},
            'reason': 'PermissionError secret-should-not-echo'}
        result = self.app.test_ai_connection()
        self.assertFalse(result['ok']); self.assertEqual(result['reason_code'], 'accounting_failed')
        self.assertTrue(result['usage_unknown']); self.assertTrue(result['usage_reserved'])
        self.assertIsNone(result['usage']); self.assertIsNone(result['usd'])
        self.assertEqual(result['reservation']['input'], 768)
        self.assertIn('保留', result['reason']); self.assertNotIn('secret-should-not-echo', json.dumps(result))

    def test_rejected_request_with_release_failure_explains_both_causes(self):
        self.call.return_value = {'ok': False, 'tracking_failed': True, 'http_status': 401,
                                 'usage_unknown': True, 'usage_reserved': True,
                                 'reservation': {'input': 768, 'output': 16, 'usd': '0.0002496'}}
        result = self.app.test_ai_connection()
        self.assertFalse(result['ok']); self.assertEqual(result['reason_code'], 'accounting_failed')
        self.assertIn('401', result['reason']); self.assertIn('密钥', result['reason'])
        self.assertIn('记录', result['reason']); self.assertTrue(result['usage_reserved'])

    def test_an_existing_test_claim_prevents_a_second_provider_call(self):
        with operation_lock.claim(self.app.data, 'ai-connection-test'):
            with self.assertRaises(Conflict): self.app.test_ai_connection()
        self.call.assert_not_called()

    def test_claim_creation_failure_is_known_unsent(self):
        with mock.patch('app.service.operation_lock.claim', side_effect=PermissionError('secret-should-not-echo')):
            result = self.app.test_ai_connection()
        self.call.assert_not_called()
        self.assertFalse(result['ok']); self.assertEqual(result['reason_code'], 'accounting_failed')
        self.assertFalse(result['usage_unknown']); self.assertFalse(result['usage_reserved'])
        self.assertIsNone(result['reservation']); self.assertIn('未发送', result['reason'])
        self.assertNotIn('secret-should-not-echo', json.dumps(result))

    def test_claim_release_failure_preserves_the_known_gateway_receipt(self):
        @contextmanager
        def release_failure(*args):
            yield
            raise PermissionError('secret-should-not-echo')
        with mock.patch('app.service.operation_lock.claim', side_effect=release_failure):
            result = self.app.test_ai_connection()
        self.call.assert_called_once_with(test_key=None)
        self.assertFalse(result['ok']); self.assertEqual(result['reason_code'], 'local_lock_failed')
        self.assertFalse(result['usage_unknown']); self.assertFalse(result['usage_reserved'])
        self.assertEqual(result['usage']['total_tokens'], 12); self.assertEqual(result['usd'], '0.0000054')
        self.assertIn('释放', result['reason']); self.assertNotIn('未发送', result['reason'])
        self.assertNotIn('secret-should-not-echo', json.dumps(result))


class AIConnectionHTTPTests(unittest.TestCase):
    def setUp(self):
        test_app_server.ServerSmokeTests.setUp(self)
        self._request = test_provider_settings.SettingsHTTPTests._request.__get__(self)

    def test_post_invokes_one_explicit_test_and_does_not_store_key(self):
        response = {'ok': True, 'reason': '测试成功', 'elapsed_ms': 1}
        with mock.patch('app.service.App.test_ai_connection', create=True, return_value=response) as call:
            status, raw = self._request('POST', '/api/ai-test', {'api_key': 'sk-transient'})
        self.assertEqual(status, 200); self.assertEqual(json.loads(raw), response)
        call.assert_called_once_with('sk-transient')
        self.assertFalse((self.root / '.local/app/deepseek.env').exists())

    def test_body_and_origin_guards_prevent_a_call(self):
        with mock.patch('app.service.App.test_ai_connection', create=True) as call:
            for body in ({'api_key': None}, {'api_key': 3}, {'model': 'other'}):
                status, _ = self._request('POST', '/api/ai-test', body)
                self.assertIn(status, (400, 413))
            status, _ = self._request('POST', '/api/ai-test', {}, origin='http://evil.example')
            self.assertEqual(status, 403)
            status, _ = self._request('GET', '/api/ai-test')
            self.assertEqual(status, 404)
            # An oversized Content-Length is rejected before body reads. Avoid
            # sending unread bytes that can reset the rejected socket on macOS.
            connection = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=5)
            self.addCleanup(connection.close)
            connection.request('POST', '/api/ai-test', headers={'Content-Length': '9000'})
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            response.read()
        call.assert_not_called()

    def test_settings_report_no_runtime_ceiling_and_preserve_usage(self):
        with mock.patch.dict(os.environ, {'PAGETIDE_DEV': '0'}):
            status, raw = self._request('GET', '/api/settings')
        self.assertEqual(status, 200); value = json.loads(raw)
        self.assertFalse(value['aggregate_limits_enabled'])
        self.assertIsNone(value['limits']['daily_total_tokens'])
        self.assertIn('tokens', value['usage'])

    def test_test_in_progress_returns_conflict_without_another_attempt(self):
        with mock.patch('app.service.App.test_ai_connection', side_effect=Conflict('AI 连接测试正在进行')):
            status, raw = self._request('POST', '/api/ai-test', {})
        self.assertEqual(status, 409)
        self.assertIn('正在进行', json.loads(raw)['error'])

    def test_claim_io_failure_returns_specific_json_without_transport(self):
        with mock.patch('app.service.operation_lock.claim', side_effect=PermissionError('secret-should-not-echo')), \
                mock.patch('app.gateway.Gateway.test_connection') as sent:
            status, raw = self._request('POST', '/api/ai-test', {})
        sent.assert_not_called()
        self.assertEqual(status, 200); result = json.loads(raw)
        self.assertEqual(result['reason_code'], 'accounting_failed')
        self.assertFalse(result['usage_unknown']); self.assertFalse(result['usage_reserved'])
        self.assertNotIn('secret-should-not-echo', raw.decode())


if __name__ == '__main__': unittest.main()
