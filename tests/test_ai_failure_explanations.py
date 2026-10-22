"""Failure causes remain actionable even when provider billing is unresolved."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from app import creation, growthproposal
from app.service import App


class FailureExplanationTests(unittest.TestCase):
    def test_http_status_survives_unknown_billing(self):
        for status, marker in [(401, '密钥'), (402, '余额'), (429, '频率'), (503, '服务')]:
            for english in (False, True):
                result = {'ok': False, 'http_status': status, 'reason': f'HTTPError: {status}',
                          'usage_unknown': status == 503, 'usage_reserved': status == 503}
                code, text = creation.degrade_reason(result, english)
                self.assertEqual(code, 'http')
                self.assertIn(str(status), text)
                if not english:
                    self.assertIn(marker, text)
                    if status == 503:
                        self.assertIn('未知', text)
                else:
                    self.assertNotRegex(text, '[㐀-鿿]')

    def test_input_beyond_the_model_window_is_not_misreported_as_bad_text(self):
        code, text = creation.degrade_reason({'invalid_input': True, 'input_too_large': True})
        self.assertEqual(code, 'invalid_input')
        self.assertIn('最大长度', text)
        self.assertIn('新会话', text)
        self.assertIn('未发送', text)
        self.assertNotIn('输入上限', text)   # no budget ceiling is blamed any more
        code, text = creation.degrade_reason({'invalid_input': True, 'input_too_large': True}, english=True)
        self.assertIn('longer than the model can read at once', text)
        self.assertIn('Nothing was sent', text)

    def test_bad_reply_is_not_misreported_as_network_failure(self):
        code, text = creation.degrade_reason({'bad_reply': True, 'finish_reason': 'length',
                                             'usage_unknown': True})
        self.assertEqual(code, 'bad_reply')
        self.assertIn('截断', text)
        self.assertIn('未知', text)
        self.assertNotIn('本地整理', text)

    def test_budget_period_and_resource_are_visible(self):
        for period, pword in [('daily', '每日'), ('monthly', '每月')]:
            for resource, rword in [('token', 'token'), ('USD', '金额')]:
                code, text = creation.degrade_reason({'reason': f'{period} {resource} ceiling (1/2 used)'})
                self.assertEqual(code, 'budget')
                self.assertIn(pword, text)
                self.assertIn(rword, text)

    def test_growth_keeps_the_cause_and_saved_progress(self):
        code, text = growthproposal.degrade_reason({'http_status': 503, 'usage_unknown': True}, saved=3)
        self.assertEqual(code, 'http')
        self.assertIn('503', text)
        self.assertIn('3', text)
        self.assertIn('待判断', text)


class FailureApiTests(unittest.TestCase):
    def test_reader_translation_and_triage_return_same_actionable_cause(self):
        with tempfile.TemporaryDirectory() as folder:
            app = App(root=Path(__file__).resolve().parents[1], data_dir=Path(folder))
            self.addCleanup(app.store.close)
            pid = app.create_project('Failure test')['project_id']
            app.store.upsert_papers([{'key': 'public', 'title': 'World model planning',
                                     'abstract': 'Public planning abstract', 'published': '2026-09-01'}], project_id=pid)
            result = {'ok': False, 'http_status': 402, 'reason': 'HTTPError: 402'}
            with patch.object(app.gateway, 'call', return_value=result):
                failures = [app.translate('public phrase'), app.triage(app.store.papers(), keys=['public'], project_id=pid),
                            app.qa('public', 'What is the approach?', project_id=pid)]
            for failure in failures:
                self.assertEqual(failure['reason_code'], 'http')
                self.assertIn('余额', failure['reason'])
                self.assertIn('402', failure['reason'])
