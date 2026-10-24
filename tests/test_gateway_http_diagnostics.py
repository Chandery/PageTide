"""Bounded provider error classification with synthetic transport and ledgers."""
import io
import http.client
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from app.gateway import Gateway


ROOT = Path(__file__).resolve().parents[1]
JSON_ERROR = ('\'messages\' must contain the word \'json\' in some form, '
              'to use \'response_format\' of type \'json_object\'.')


class ErrorStream(io.BytesIO):
    def __init__(self, body, read_error=None):
        super().__init__(body)
        self.read_sizes = []
        self.read_error = read_error

    def read(self, size=-1):
        self.read_sizes.append(size)
        if self.read_error is not None:
            raise self.read_error
        return super().read(size)


def error_payload(message=JSON_ERROR, **extra):
    return json.dumps({'error': {'message': message, **extra}}).encode()


class GatewayHTTPDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        env = mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'synthetic-secret-key', 'PAGETIDE_DEV': '0'})
        env.start(); self.addCleanup(env.stop)
        self.gateway = Gateway(root=ROOT, data_dir=self.data, dev=False)

    def request_error(self, body, status=400, connection=False, read_error=None):
        stream = ErrorStream(body, read_error)
        error = urllib.error.HTTPError('https://example.invalid/synthetic-secret', status,
                                      'synthetic-exception-secret', {}, stream)
        with mock.patch('app.gateway.urllib.request.urlopen', side_effect=error) as sent:
            result = (self.gateway.test_connection('synthetic-secret-key') if connection else
                      self.gateway.call('project_guidance', [{'role': 'user', 'content': 'Synthetic direction'}]))
        self.assertEqual(sent.call_count, 1)
        return result, stream

    def assert_released(self, result):
        self.assertFalse(result['ok']); self.assertEqual(result['http_status'], 400)
        self.assertFalse(result['usage_unknown']); self.assertFalse(result['usage_reserved'])
        self.assertIsNone(result['reservation'])
        self.assertEqual(self.gateway.usage_today()['pending_reservations'], 0)
        self.assertEqual(self.gateway.usage_today()['tokens'], 0)

    def test_explicit_json_instruction_error_is_classified_without_retry_and_released(self):
        out, stream = self.request_error(error_payload())
        self.assert_released(out)
        self.assertEqual(out.get('provider_error'), 'json_instruction_missing')
        self.assertEqual(out['reason'], 'HTTPError: 400')
        self.assertEqual(stream.read_sizes, [8193]); self.assertTrue(stream.closed)

    def test_recognized_message_and_other_provider_fields_never_echo_secrets(self):
        out, stream = self.request_error(error_payload(JSON_ERROR + ' synthetic-secret-key synthetic-private-prompt',
                                                       code='synthetic-code-secret', param='synthetic-param-secret'))
        self.assert_released(out); self.assertTrue(stream.closed)
        self.assertEqual(out.get('provider_error'), 'json_instruction_missing')
        for secret in ('synthetic-secret-key', 'synthetic-private-prompt', 'synthetic-code-secret',
                       'synthetic-param-secret', 'synthetic-exception-secret'):
            self.assertNotIn(secret, json.dumps(out))
            self.assertNotIn(secret, self.gateway.ledger.read_text())
        self.assertFalse({'message', 'code', 'param', 'body'} & out.keys())

    def test_malformed_or_unrecognized_400_stays_generic_and_closes(self):
        bodies = [b'not JSON', b'\xff', b'{"error":', error_payload({'message': JSON_ERROR}),
                  json.dumps({'message': JSON_ERROR}).encode(), error_payload('Invalid API key'),
                  error_payload('messages and json_object response_format are invalid'),
                  error_payload('messages must contain word json to use response_format'),
                  b'{"error":{"message":' + json.dumps(JSON_ERROR).encode() + b'},"invalid":NaN}']
        for body in bodies:
            with self.subTest(body_kind=type(body).__name__, length=len(body)):
                out, stream = self.request_error(body)
                self.assert_released(out); self.assertNotIn('provider_error', out)
                self.assertEqual(stream.read_sizes, [8193]); self.assertTrue(stream.closed)

    def test_oversized_error_is_not_classified_or_read_past_the_bound(self):
        out, stream = self.request_error(error_payload() + b' ' * 8193)
        self.assert_released(out); self.assertNotIn('provider_error', out)
        self.assertEqual(stream.read_sizes, [8193]); self.assertTrue(stream.closed)

    def test_exact_8k_error_boundary_can_be_classified(self):
        body = error_payload(); body += b' ' * (8192 - len(body))
        self.assertEqual(len(body), 8192)
        out, stream = self.request_error(body)
        self.assert_released(out); self.assertEqual(out.get('provider_error'), 'json_instruction_missing')
        self.assertEqual(stream.read_sizes, [8193]); self.assertTrue(stream.closed)

    def test_error_body_read_failure_does_not_change_known_http_rejection(self):
        for error in (OSError('synthetic-private-path'), http.client.IncompleteRead(b'synthetic-private-path', 4)):
            with self.subTest(error_type=type(error).__name__):
                out, stream = self.request_error(error_payload(), read_error=error)
                self.assert_released(out); self.assertNotIn('provider_error', out)
                self.assertTrue(stream.closed); self.assertNotIn('synthetic-private-path', json.dumps(out))

    def test_5xx_preserves_unknown_reservation_and_does_not_parse_error_body(self):
        out, stream = self.request_error(error_payload(), status=503)
        self.assertFalse(out['ok']); self.assertEqual(out['http_status'], 503)
        self.assertTrue(out['usage_unknown']); self.assertTrue(out['usage_reserved'])
        self.assertEqual(out['reservation']['input'], self.gateway.config['operations']['project_guidance']['cap']['input'])   # the registered estimate
        self.assertNotIn('provider_error', out)
        self.assertEqual(stream.read_sizes, []); self.assertTrue(stream.closed)
        self.assertEqual(self.gateway.usage_today()['pending_reservations'], 1)

    def test_explicit_connection_test_also_exposes_no_raw_error_body(self):
        out, stream = self.request_error(error_payload(JSON_ERROR + ' synthetic-secret-key'), connection=True)
        self.assert_released(out); self.assertTrue(stream.closed)
        self.assertNotIn('synthetic-secret-key', json.dumps(out))
        self.assertNotIn('synthetic-exception-secret', json.dumps(out))
        self.assertFalse({'content', 'message', 'code', 'param', 'body'} & out.keys())

    def test_connection_release_write_failure_preserves_diagnostic_and_reservation(self):
        record = self.gateway._record
        def fail_release(*args):
            if args[-1] == 'released':
                raise PermissionError('synthetic-private-path')
            return record(*args)
        with mock.patch.object(self.gateway, '_record', side_effect=fail_release):
            out, stream = self.request_error(error_payload(), connection=True)
        self.assertEqual(out.get('provider_error'), 'json_instruction_missing')
        self.assertEqual(out['http_status'], 400); self.assertTrue(out['tracking_failed'])
        self.assertTrue(out['usage_unknown']); self.assertTrue(out['usage_reserved'])
        self.assertEqual(out['reservation']['input'], 768)
        self.assertEqual(self.gateway.usage_today()['pending_reservations'], 1)
        self.assertTrue(stream.closed); self.assertNotIn('synthetic-private-path', json.dumps(out))


if __name__ == '__main__':
    unittest.main()
