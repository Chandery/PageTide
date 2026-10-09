"""Owner policy changes use isolated ledgers and synthetic provider responses."""
import datetime
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from app.gateway import AI_DISABLED_MARKER, DEV_POLICY, Gateway, input_bound

ROOT = Path(__file__).resolve().parents[1]
TEST_OPERATION = 'ai_connection_test'
TEST_MESSAGES = [{'role': 'user', 'content': 'Reply only OK.'}]


def reply(usage=True):
    payload = {'choices': [{'message': {'content': 'OK'}, 'finish_reason': 'stop'}]}
    if usage:
        payload['usage'] = {'prompt_tokens': 80, 'completion_tokens': 2, 'total_tokens': 82}
    return io.BytesIO(json.dumps(payload).encode())


class GatewayPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'synthetic-saved-key', 'PDH_DEV': '0'})
        env.start(); self.addCleanup(env.stop)
        self.gateway = Gateway(root=ROOT, data_dir=self.data, dev=False)

    def unlimited(self):
        self.gateway.config['policy']['aggregate_limits_enabled'] = False
        for field in ('daily_total_tokens', 'monthly_total_tokens'):
            self.gateway.config['policy'][field] = 0
        for field in ('daily_usd', 'monthly_usd'):
            self.gateway.config['policy'][field] = '0'

    def test_current_runtime_disables_aggregate_caps_and_dev_retains_its_own_caps(self):
        self.assertIs(self.gateway.limits().get('aggregate_limits_enabled', True), False)
        overview = self.gateway.usage_today()
        self.assertIsNone(overview['ceiling'])
        self.assertIs(overview['aggregate_limits_enabled'], False)
        dev = Gateway(root=ROOT, data_dir=self.data, dev=True)
        self.assertIs(dev.limits()['aggregate_limits_enabled'], True)
        self.assertEqual(dev.usage_today()['ceiling'], DEV_POLICY['daily_total_tokens'])
        self.assertNotEqual(dev.ledger, self.gateway.ledger)

    def test_disabled_aggregate_ignores_old_token_and_usd_fields_without_resetting_usage(self):
        self.unlimited()
        day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        self.gateway._append({'date': day, 'input': 2_000_000, 'output': 0, 'usd': '100'})
        with mock.patch('app.gateway.urllib.request.urlopen', return_value=reply()) as sent:
            result = self.gateway.call('daily_triage', [{'role': 'user', 'content': 'Synthetic data'}])
        self.assertTrue(result['ok']); self.assertEqual(sent.call_count, 1)
        self.assertEqual(self.gateway.usage_today()['tokens'], 2_000_082)
        self.assertGreater(float(self.gateway.usage_today()['usd']), 100)
        self.assertIsNone(self.gateway.usage_today()['ceiling'])

    def test_unknown_reservations_survive_restart_without_becoming_measured_or_double_counted(self):
        self.unlimited()
        with mock.patch('app.gateway.urllib.request.urlopen', side_effect=TimeoutError('synthetic timeout')) as sent:
            first = self.gateway.call('daily_triage', [])
        self.assertTrue(first['usage_unknown']); self.assertEqual(sent.call_count, 1)
        restarted = Gateway(root=ROOT, data_dir=self.data, dev=False)
        restarted.config['policy']['aggregate_limits_enabled'] = False
        cap = self.gateway.config['operations']['daily_triage']['cap']
        total = cap['input'] + cap['output']
        overview = restarted.usage_today()
        self.assertEqual(overview['tokens'], total)
        self.assertFalse(overview['tokens_known'])
        self.assertEqual(overview['reserved_tokens'], total)
        self.assertEqual(overview['pending_reservations'], 1)
        rid = restarted._entries()[0]['id']
        for _ in range(2):
            restarted._record(datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                              'daily_triage', {'prompt_tokens': 80, 'completion_tokens': 2}, '0.0000264',
                              'deepseek-flash', rid, 'reconciled')
        overview = restarted.usage_today()
        self.assertEqual(overview['tokens'], 82)
        self.assertTrue(overview['tokens_known'])
        self.assertEqual(overview['pending_reservations'], 0)

    def test_explicit_enabled_aggregate_and_single_request_approval_guards_still_work(self):
        self.gateway.config['policy'].update(aggregate_limits_enabled=True, daily_total_tokens=0)
        with mock.patch('app.gateway.urllib.request.urlopen') as sent:
            refused = self.gateway.call('daily_triage', [])
        sent.assert_not_called(); self.assertIn('daily token ceiling', refused['reason'])
        self.unlimited()
        self.gateway.config['operations']['project_guidance']['owner_approved'] = False
        with mock.patch('app.gateway.urllib.request.urlopen') as sent:
            approval = self.gateway.call('project_guidance', [])
            oversized = self.gateway.call('daily_triage', [{'role': 'user', 'content': 'x' * 9000}])
        sent.assert_not_called(); self.assertIn('owner approval', approval['reason'])
        self.assertTrue(oversized['input_too_large']); self.assertFalse(self.gateway.ledger.exists())

    def test_connection_test_uses_only_fixed_bounded_data_and_ephemeral_key_without_enabling_ai(self):
        self.gateway.set_enabled(False)
        marker = (self.data / AI_DISABLED_MARKER).read_bytes()
        seen = []
        def provider(request, timeout):
            seen.append(request)
            self.assertEqual(timeout, 30)
            return reply()
        with mock.patch('app.gateway.urllib.request.urlopen', side_effect=provider) as sent:
            out = self.gateway.test_connection('synthetic-unsaved-secret')
        self.assertTrue(out['ok']); self.assertEqual(sent.call_count, 1)
        body = json.loads(seen[0].data)
        self.assertEqual(body['messages'], TEST_MESSAGES)
        self.assertEqual(body['max_tokens'], 16); self.assertLessEqual(input_bound(body), 768)
        self.assertEqual(seen[0].get_header('Authorization'), 'Bearer synthetic-unsaved-secret')
        self.assertNotIn('content', out)
        self.assertEqual((self.data / AI_DISABLED_MARKER).read_bytes(), marker)
        self.assertFalse(self.gateway.key_file().exists())
        self.assertNotIn('synthetic-unsaved-secret', self.gateway.ledger.read_text())
        self.assertNotIn('synthetic-unsaved-secret', json.dumps(out))
        with mock.patch('app.gateway.urllib.request.urlopen') as sent:
            ordinary = self.gateway.call('daily_triage', [])
        self.assertTrue(ordinary['disabled']); sent.assert_not_called()

    def test_connection_key_none_uses_existing_key_and_blank_or_bad_values_never_send(self):
        with mock.patch('app.gateway.urllib.request.urlopen', return_value=reply()) as sent:
            out = self.gateway.test_connection()
        self.assertTrue(out['ok'])
        self.assertEqual(sent.call_args.args[0].get_header('Authorization'), 'Bearer synthetic-saved-key')
        for key in ('', ' ', 1, 'a\nb', 'a\tb', 'x' * 513):
            with self.subTest(key_type=type(key).__name__), mock.patch('app.gateway.urllib.request.urlopen') as sent:
                invalid = self.gateway.test_connection(key)
            sent.assert_not_called(); self.assertTrue(invalid['invalid_input'])
            self.assertFalse(invalid['usage_unknown'])

    def test_ephemeral_key_and_switch_bypass_cannot_be_used_for_other_operations_or_messages(self):
        with mock.patch('app.gateway.urllib.request.urlopen') as sent:
            ordinary = self.gateway.call('daily_triage', [], connection_test_key='synthetic-key')
            wrong_message = self.gateway.call(TEST_OPERATION, [{'role': 'user', 'content': 'Private note'}])
        sent.assert_not_called(); self.assertTrue(ordinary['invalid_input'])
        self.assertTrue(wrong_message['invalid_input']); self.assertFalse(self.gateway.ledger.exists())

    def test_connection_failure_sanitizes_diagnostics_and_retains_unknown_usage(self):
        secret = 'synthetic-unsaved-secret'
        with mock.patch('app.gateway.urllib.request.urlopen', side_effect=urllib.error.URLError(secret)) as sent:
            out = self.gateway.test_connection(secret)
        self.assertEqual(sent.call_count, 1); self.assertTrue(out['usage_unknown']); self.assertTrue(out['usage_reserved'])
        self.assertNotIn(secret, json.dumps(out)); self.assertNotIn(secret, self.gateway.ledger.read_text())
        self.assertEqual(self.gateway.usage_today()['pending_reservations'], 1)
        error = urllib.error.HTTPError('https://example.invalid', 401, secret, {}, io.BytesIO(secret.encode()))
        with mock.patch('app.gateway.urllib.request.urlopen', side_effect=error) as sent:
            out = self.gateway.test_connection(secret)
        self.assertEqual(sent.call_count, 1); self.assertEqual(out['http_status'], 401)
        self.assertFalse(out['usage_unknown']); self.assertNotIn(secret, json.dumps(out))
        self.assertEqual(self.gateway.usage_today()['pending_reservations'], 1)

    def test_connection_initial_tracking_write_failure_stops_before_transport(self):
        secret = 'synthetic-private-error-detail'
        with mock.patch.object(self.gateway, '_record', side_effect=PermissionError(secret)), \
                mock.patch('app.gateway.urllib.request.urlopen') as sent:
            out = self.gateway.test_connection('synthetic-test-key')
        sent.assert_not_called()
        self.assertFalse(self.gateway.ledger.exists())
        self.assertFalse(out['ok']); self.assertTrue(out['tracking_failed'])
        self.assertFalse(out['usage_unknown']); self.assertFalse(out['usage_reserved'])
        self.assertIsNone(out.get('reservation'))
        self.assertIn('nothing sent', out['reason'])
        self.assertNotIn(secret, json.dumps(out))

    def test_connection_post_send_reconcile_failure_keeps_durable_reservation(self):
        record = self.gateway._record
        def fail_reconcile(*args):
            if args[-1] == 'reconciled':
                raise PermissionError('synthetic-private-error-detail')
            return record(*args)
        with mock.patch.object(self.gateway, '_record', side_effect=fail_reconcile), \
                mock.patch('app.gateway.urllib.request.urlopen', return_value=reply()) as sent:
            out = self.gateway.test_connection('synthetic-test-key')
        self.assertEqual(sent.call_count, 1)
        self.assertFalse(out['ok']); self.assertTrue(out['tracking_failed'])
        self.assertTrue(out['usage_unknown']); self.assertTrue(out['usage_reserved'])
        self.assertEqual(out['reservation']['input'], 768)
        self.assertNotIn('synthetic-private-error-detail', json.dumps(out))
        restarted = Gateway(root=ROOT, data_dir=self.data, dev=False)
        self.assertEqual(restarted.usage_today()['pending_reservations'], 1)
        self.assertEqual(restarted.usage_today()['tokens'], 784)
        self.assertFalse(restarted.usage_today()['tokens_known'])

    def test_regular_operation_tracking_write_errors_retain_existing_exception_behavior(self):
        with mock.patch.object(self.gateway, '_record', side_effect=PermissionError('synthetic error')), \
                mock.patch('app.gateway.urllib.request.urlopen') as sent:
            with self.assertRaises(PermissionError):
                self.gateway.call('daily_triage', [])
        sent.assert_not_called()

    def test_connection_pre_send_ledger_read_or_lock_failure_does_not_claim_a_charge(self):
        for method in ('admit', '_ledger_serial'):
            with self.subTest(method=method):
                with mock.patch.object(self.gateway, method, side_effect=PermissionError('synthetic-private-path')), \
                        mock.patch('app.gateway.urllib.request.urlopen') as sent:
                    out = self.gateway.test_connection('synthetic-test-key')
                sent.assert_not_called(); self.assertFalse(self.gateway.ledger.exists())
                self.assertTrue(out['tracking_failed']); self.assertFalse(out['usage_unknown'])
                self.assertFalse(out['usage_reserved']); self.assertIsNone(out.get('reservation'))
                self.assertNotIn('synthetic-private-path', json.dumps(out))

    def test_connection_post_send_unknown_or_release_write_failure_keeps_pending_accounting(self):
        for stage in ('unknown', 'released'):
            with self.subTest(stage=stage):
                record = self.gateway._record
                def fail_record(*args):
                    if args[-1] == stage:
                        raise PermissionError('synthetic-private-path')
                    return record(*args)
                transport = (mock.patch('app.gateway.urllib.request.urlopen', return_value=reply(usage=False))
                             if stage == 'unknown' else mock.patch('app.gateway.urllib.request.urlopen',
                                 side_effect=urllib.error.HTTPError('https://example.invalid', 401,
                                     'synthetic-private-path', {}, io.BytesIO(b'synthetic body'))))
                with mock.patch.object(self.gateway, '_record', side_effect=fail_record), transport as sent:
                    out = self.gateway.test_connection('synthetic-test-key')
                self.assertEqual(sent.call_count, 1)
                self.assertFalse(out['ok']); self.assertTrue(out['tracking_failed'])
                self.assertTrue(out['usage_unknown']); self.assertTrue(out['usage_reserved'])
                self.assertEqual(out['reservation']['input'], 768)
                self.assertNotIn('synthetic-private-path', json.dumps(out))
                if stage == 'released':
                    self.assertEqual(out['http_status'], 401)
        self.assertEqual(self.gateway.usage_today()['pending_reservations'], 2)


if __name__ == '__main__':
    unittest.main()
