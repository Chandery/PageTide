"""Title script is a local warning, never a replacement for body-language proof."""
import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from app import eligibility, maintenance, paper_language, ranking
from app.service import App


CHINESE_TITLE = '世界模型研究方法与视频预测'
POLICY = {'status': 'ready', 'allowed_languages': ['en']}


class TitleEvidenceTests(unittest.TestCase):
    def evidence(self, title, reported='en'):
        return paper_language.title_metadata_evidence(title, reported)

    def test_majority_scripts_are_warnings_without_guessing_body_language(self):
        for title in (CHINESE_TITLE, '世界モデルの学習と予測', '세계 모델 학습과 예측',
                      'Обучение моделей мира', 'تعلم نماذج العالم', 'Μοντέλα κόσμου'):
            with self.subTest(title=title):
                result = self.evidence(title)
                self.assertTrue(result['title_metadata_conflict'])
                self.assertEqual(result['title_warning'], 'title_metadata_conflict')
                self.assertEqual(result['title_evidence']['source'], 'title_script')
                self.assertTrue(result['title_evidence']['non_latin_majority'])
                self.assertNotIn('fulltext_language', result)
                self.assertNotIn('metadata_language', result)

    def test_small_terms_bilingual_english_and_latin_diacritics_are_allowed(self):
        for title in ('Learning 世界 models from video prediction',
                      'World models for planning 世界模型', 'Étude of world models',
                      '模型ab', '模型研究abcd', '😀 1234'):
            with self.subTest(title=title):
                self.assertFalse(self.evidence(title)['title_metadata_conflict'])
        result = self.evidence('模型研究abc')
        self.assertTrue(result['title_metadata_conflict'])
        self.assertEqual(result['title_evidence']['non_latin_chars'], 4)
        self.assertEqual(result['title_evidence']['alphabetic_chars'], 7)

    def test_unknown_reports_never_become_english_from_a_title(self):
        for reported in (None, '', 'unknown', 'zh'):
            for title in (CHINESE_TITLE, 'An entirely English title'):
                with self.subTest(reported=reported, title=title):
                    self.assertFalse(self.evidence(title, reported)['title_metadata_conflict'])
        language = {'metadata_language': None, 'metadata_source': 'source report', 'fulltext_status': 'unverified'}
        result = eligibility.evaluate(POLICY, {'title': 'An English title', 'abstract': 'Usable abstract'}, language)
        self.assertEqual(result['reason'], 'language_unknown')
        self.assertIsNone(result['language']['metadata_language'])
        self.assertEqual(result['language']['metadata_source'], 'source report')

    def test_eligibility_recomputes_warning_from_current_title(self):
        language = {'metadata_language': 'en', 'metadata_source': 'OpenAlex', 'fulltext_status': 'unverified',
                    'title_metadata_conflict': False, 'title_warning': None}
        result = eligibility.evaluate(POLICY, {'title': CHINESE_TITLE, 'abstract': 'Usable English abstract'}, language)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['reason'], 'title_language_unverified')
        self.assertTrue(result['language']['title_metadata_conflict'])
        self.assertEqual(language['title_metadata_conflict'], False)
        self.assertEqual(result['language']['metadata_language'], 'en')

    def test_verified_language_priority_and_legacy_caller_compatibility(self):
        paper = {'title': CHINESE_TITLE, 'abstract': 'Usable abstract'}
        for status in ({'fulltext_status': 'verified'}, {}):
            result = eligibility.evaluate(POLICY, paper, {'metadata_language': 'en', 'fulltext_language': 'en', **status})
            self.assertTrue(result['eligible'])
            result = eligibility.evaluate(POLICY, paper, {'metadata_language': 'en', 'fulltext_language': 'zh', **status})
            self.assertEqual(result['reason'], 'language_not_allowed')
        result = eligibility.evaluate(POLICY, paper, {'metadata_language': 'en', 'fulltext_language': 'en', 'fulltext_status': 'unverified'})
        self.assertEqual(result['reason'], 'title_language_unverified')

    def test_long_titles_are_evaluated_whole_without_half_title_guess(self):
        self.assertFalse(self.evidence('模型研究' + ' English' * 2000)['title_metadata_conflict'])
        self.assertTrue(self.evidence('English ' + '世界模型研究' * 2000)['title_metadata_conflict'])

    def test_compatibility_fonts_do_not_turn_english_into_non_latin(self):
        for title in ('𝐖𝐨𝐫𝐥𝐝 𝐌𝐨𝐝𝐞𝐥𝐬 𝐟𝐨𝐫 𝐑𝐨𝐛𝐨𝐭𝐢𝐜𝐬', '𝙒𝙤𝙧𝙡𝙙 𝙈𝙤𝙙𝙚𝙡𝙨', 'Ｗｏｒｌｄ Ｍｏｄｅｌｓ'):
            with self.subTest(title=title):
                self.assertFalse(self.evidence(title)['title_metadata_conflict'])
                self.assertEqual(self.evidence(title)['title_evidence']['non_latin_chars'], 0)
        for title in (CHINESE_TITLE, 'Μοντέλα κόσμου'):
            with self.subTest(title=title):
                self.assertTrue(self.evidence(title)['title_metadata_conflict'])


class AppTitleGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        self.app = App(data_dir=self.data); self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project('Title policy')['project_id']
        self.app.set_project_language(self.pid, 'stem', ['en'])
        patcher = mock.patch.object(self.app.gateway, 'call', side_effect=AssertionError('Title screening must not call AI'))
        patcher.start(); self.addCleanup(patcher.stop)

    def paper(self, key, title=CHINESE_TITLE, reported='en'):
        self.app.store.upsert_papers([{'key': key, 'title': title, 'abstract': 'World model learning and prediction from video.',
                                     'published': '2026-01-01', 'language': reported,
                                     'metadata_language_source': 'OpenAlex'}], self.pid)

    def pool(self, key):
        return next(p for p in self.app.recommendation_pool(self.pid) if p['key'] == key)

    def batch(self):
        return self.app.build_batch(project_id=self.pid, exclude_seen=False)

    def pdf(self, key, suffix='first'):
        path = self.data / (key + suffix + '.pdf')
        content = b'%PDF-1.4\n' + suffix.encode() + b'\n%%EOF'; path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest(); self.app.store.record_pdf(key, path, sha256=digest)
        return path, digest

    def change_title(self, key, title):
        # upsert preserves the original title; simulate a local metadata edit
        # in this isolated DB instead of pretending reinsertion changes it.
        self.app.store.conn.execute('UPDATE papers SET title=? WHERE key=?', (title, key))
        self.app.store.conn.commit()

    def test_batch_filters_suspicious_title_and_preserves_metadata(self):
        self.paper('cn'); self.paper('en', 'World models for video prediction')
        self.paper('bilingual', 'World models for planning 世界模型')
        result = self.batch()
        self.assertEqual({c['key'] for c in result['cards']}, {'en', 'bilingual'})
        self.assertEqual(result['eligibility']['excluded']['title_language_unverified'], 1)
        stored = self.app.store.paper('cn')
        self.assertEqual(stored['title'], CHINESE_TITLE)
        self.assertEqual((stored['metadata_language'], stored['metadata_language_source']), ('en', 'OpenAlex'))
        evidence = self.pool('cn')['_eligibility']['language']
        self.assertEqual(evidence['fulltext_status'], 'unverified')
        self.assertIsNone(evidence['fulltext_language'])
        self.assertTrue(evidence['title_metadata_conflict'])

    def test_humanities_allows_reported_languages_but_keeps_warning(self):
        self.paper('cn'); self.app.set_project_language(self.pid, 'humanities', ['en', 'zh'])
        cards = self.batch()['cards']
        self.assertEqual([c['key'] for c in cards], ['cn'])
        self.assertTrue(cards[0]['language']['title_metadata_conflict'])
        self.assertEqual(cards[0]['language']['title_warning'], 'title_metadata_conflict')
        self.assertEqual(cards[0]['language']['metadata_source'], 'OpenAlex')
        self.assertEqual(cards[0]['language']['fulltext_status'], 'unverified')
        self.assertTrue(self.pool('cn')['_eligibility']['language']['title_metadata_conflict'])
        self.assertEqual(self.pool('cn')['_eligibility']['language']['metadata_language'], 'en')

    def test_current_verified_english_overrides_title_but_chinese_body_does_not(self):
        self.paper('body'); _, digest = self.pdf('body')
        self.app.store.record_fulltext_language('body', 'en', digest, 'manual')
        self.assertEqual([c['key'] for c in self.batch()['cards']], ['body'])
        self.app.store.record_fulltext_language('body', 'zh', digest, 'manual')
        self.assertEqual(self.batch()['cards'], [])
        self.assertEqual(self.pool('body')['_eligibility']['reason'], 'language_not_allowed')

    def test_pdf_replacement_or_hash_mismatch_restores_title_verification_gate(self):
        self.paper('body'); path, digest = self.pdf('body')
        self.app.store.record_fulltext_language('body', 'en', digest, 'manual')
        self.assertTrue(self.pool('body')['_eligibility']['eligible'])
        path.write_bytes(b'%PDF-1.4\nchanged externally\n%%EOF')
        self.assertEqual(self.pool('body')['_eligibility']['reason'], 'title_language_unverified')
        self.pdf('body', 'replacement')
        self.assertEqual(self.pool('body')['_eligibility']['reason'], 'title_language_unverified')
        self.assertEqual(self.batch()['cards'], [])

    def test_route_and_maintenance_share_title_gate(self):
        self.paper('cn')
        self.app.route_save(self.pid, plan={'concepts': [{'id': 'world', 'name': 'World model', 'terms': ['world model'],
                                                       'hint': 1, 'needs': []}], 'targets': ['world']})
        result = self.batch(); self.assertEqual(result['cards'], [])
        self.assertEqual(result['eligibility']['excluded']['title_language_unverified'], 1)
        now = datetime.now(timezone.utc)
        self.app.store.set_setting('last_refresh_' + self.pid, now.isoformat())
        self.assertFalse(maintenance.plan(self.app, self.pid, now)['batch'])
        self.assertFalse(maintenance.run(self.app, self.pid, now)['batch'])

    def test_title_changes_recompute_evidence_without_stale_warning(self):
        self.paper('edit', 'World model research')
        self.assertTrue(self.pool('edit')['_eligibility']['eligible'])
        self.change_title('edit', CHINESE_TITLE)
        self.assertEqual(self.pool('edit')['_eligibility']['reason'], 'title_language_unverified')
        self.assertEqual(self.batch()['cards'], [])
        self.change_title('edit', 'World model research')
        self.assertTrue(self.pool('edit')['_eligibility']['eligible'])
        self.assertFalse(self.pool('edit')['_eligibility']['language']['title_metadata_conflict'])

    def test_title_changed_after_selection_cannot_enter_a_batch(self):
        self.paper('changing', 'World model research')
        real = ranking.mmr_select
        def change(*args, **kwargs):
            selected = real(*args, **kwargs)
            self.change_title('changing', CHINESE_TITLE)
            return selected
        with mock.patch.object(ranking, 'mmr_select', side_effect=change): result = self.batch()
        self.assertEqual(result['reason_code'], 'recommendation_changed')
        self.assertIsNone(result['batch_id'])
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM exposures').fetchone()[0], 0)

    def test_styled_english_titles_reach_batch_without_rewriting_title(self):
        title = '𝐖𝐨𝐫𝐥𝐝 𝐌𝐨𝐝𝐞𝐥𝐬 𝐟𝐨𝐫 𝐑𝐨𝐛𝐨𝐭𝐢𝐜𝐬'
        self.paper('styled', title); self.paper('cn')
        cards = self.batch()['cards']
        self.assertEqual([c['key'] for c in cards], ['styled'])
        self.assertEqual(cards[0]['title'], title)
        self.assertEqual(self.app.store.paper('styled')['title'], title)
