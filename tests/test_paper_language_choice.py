"""Paper language is a choice of languages (Chinese, English), not a discipline.

The owner asked twice for check boxes instead of a "理工科/文科" drop-down. A policy is its language list; projects
saved with a discipline or with other languages must still load and must not lose a language silently.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from recommendation_fixtures import SYNTHETIC_OA
from app import eligibility, migrations, paper_language
from app.db import Store
from app.service import App


class PolicyRules(unittest.TestCase):
    def test_a_policy_is_a_non_empty_list_of_supported_languages(self):
        for allowed in (['en'], ['zh'], ['en', 'zh'], ['zh', 'en', 'zh']):
            with self.subTest(allowed=allowed):
                self.assertEqual(paper_language.validate_policy(None, allowed), list(dict.fromkeys(allowed)))
        for bad in ([], None, 'zh', ['xx'], [None], ['en'] * 30):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                paper_language.validate_policy(None, bad)

    def test_a_policy_value_needs_no_discipline_and_old_values_still_validate(self):
        self.assertEqual(paper_language.validate_value({'allowed_languages': ['zh']}),
                         {'discipline': None, 'allowed_languages': ['zh']})
        self.assertEqual(paper_language.validate_value({'discipline': None, 'allowed_languages': ['en', 'zh']})['allowed_languages'],
                         ['en', 'zh'])
        self.assertEqual(paper_language.validate_value({'discipline': 'humanities', 'allowed_languages': ['zh', 'la']})
                         ['allowed_languages'], ['zh', 'la'])
        self.assertEqual(paper_language.validate_value({'discipline': 'stem', 'allowed_languages': ['en']})['discipline'], 'stem')
        self.assertIsNone(paper_language.validate_value(None))
        for bad in ({'discipline': 'stem', 'allowed_languages': ['zh']}, {'discipline': 'art', 'allowed_languages': ['en']},
                    {'allowed_languages': []}, {'allowed_languages': ['en'], 'extra': 1}, {}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                paper_language.validate_value(bad)

    def test_a_row_is_ready_once_languages_were_chosen_whatever_its_discipline_column_holds(self):
        row = lambda discipline, allowed, revision: {'discipline': discipline, 'allowed_languages': allowed,
                                                     'language_policy_revision': revision}
        self.assertEqual(paper_language.policy_from_row(row(None, '["zh"]', 1))['status'], 'ready')
        self.assertEqual(paper_language.policy_from_row(row('stem', '["en"]', 1))['status'], 'ready')
        self.assertEqual(paper_language.policy_from_row(row('cs_ai', '[]', 0))['status'], 'pending')
        self.assertEqual(paper_language.policy_from_row(row(None, '[]', 0))['status'], 'pending')
        self.assertEqual(paper_language.policy_from_row(row(None, '[]', 3))['status'], 'pending')

    def test_the_english_pack_has_no_entry_left_for_the_discipline_drop_down(self):
        import json
        pack = json.loads((Path(__file__).resolve().parents[1] / 'app/static/i18n/en-US.json').read_text())['messages']
        for key in ('学科', '项目学科', '请选择学科', '理工科', '文科', '请选择理工科或文科'):
            self.assertNotIn(key, pack)

    def test_the_message_asks_for_languages_only(self):
        for text in eligibility.REASONS['language_policy_required']:
            self.assertNotIn('学科', text)
            self.assertNotIn('iscipline', text)


class ProjectLanguages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(data_dir=self.tmp.name)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project('世界模型')['project_id']

    def policy(self, pid=None):
        return self.app.projects.get_project(pid or self.pid)['language_policy']

    def test_english_chinese_and_both_are_each_ready_without_a_discipline(self):
        for allowed in (['en'], ['zh'], ['en', 'zh']):
            with self.subTest(allowed=allowed):
                pid = self.app.create_project('P ' + '+'.join(allowed), language_policy={'allowed_languages': allowed})['project_id']
                policy = self.policy(pid)
                self.assertEqual(policy['status'], 'ready')
                self.assertEqual(policy['allowed_languages'], allowed)
                self.assertEqual(policy['revision'], 1)
        saved = self.app.set_project_language(self.pid, None, ['en', 'zh'])['language_policy']
        self.assertEqual((saved['status'], saved['allowed_languages'], saved['revision']), ('ready', ['en', 'zh'], 1))

    def test_project_creation_from_guidance_accepts_a_languages_only_policy(self):
        session = self.app.create_guidance_session('Project', 'world model')
        made = self.app.finalize_guidance(session['id'], skip_route=True, language_policy={'allowed_languages': ['zh']})
        self.assertEqual(self.policy(made['project_id'])['allowed_languages'], ['zh'])
        self.assertEqual(self.policy(made['project_id'])['status'], 'ready')

    def test_no_language_is_refused_and_leaves_the_project_pending(self):
        for bad in ([], None, ['xx']):
            with self.assertRaises(ValueError):
                self.app.set_project_language(self.pid, None, bad)
        self.assertEqual(self.policy()['status'], 'pending')
        with self.assertRaises(ValueError):
            self.app.create_project('Nope', language_policy={'allowed_languages': []})

    def test_saving_the_same_languages_is_not_a_new_policy_revision(self):
        first = self.app.set_project_language(self.pid, None, ['zh', 'en'])['language_policy']
        same = self.app.set_project_language(self.pid, None, ['en', 'zh'])['language_policy']
        changed = self.app.set_project_language(self.pid, None, ['zh'])['language_policy']
        self.assertEqual(first['revision'], same['revision'])
        self.assertEqual(changed['revision'], first['revision'] + 1)

    def test_a_legacy_stem_project_loads_and_can_be_widened_without_a_discipline(self):
        self.app.set_project_language(self.pid, 'stem', ['en'])
        self.assertEqual(self.policy()['discipline'], 'stem')
        self.assertEqual(self.policy()['status'], 'ready')
        widened = self.app.set_project_language(self.pid, None, ['en', 'zh'])['language_policy']
        self.assertEqual(widened['allowed_languages'], ['en', 'zh'])
        self.assertEqual(widened['revision'], 2)
        self.assertEqual(widened['status'], 'ready')

    def test_legacy_extra_languages_survive_a_save_that_keeps_them_ticked(self):
        self.app.set_project_language(self.pid, 'humanities', ['zh', 'la', 'ja'])
        kept = self.app.set_project_language(self.pid, None, ['zh', 'la', 'ja', 'en'])['language_policy']
        self.assertEqual(kept['allowed_languages'], ['zh', 'la', 'ja', 'en'])
        dropped = self.app.set_project_language(self.pid, None, ['zh', 'en'])['language_policy']
        self.assertEqual(dropped['allowed_languages'], ['zh', 'en'])

    def test_a_legacy_not_null_discipline_column_does_not_break_a_languages_only_project(self):
        path = Path(self.tmp.name) / 'nonnull' / 'pagetide.sqlite'
        with mock.patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if migrations._number(m) < 9]):
            old = Store(path)
            old.init()
            old.conn.execute("ALTER TABLE projects ADD COLUMN discipline TEXT NOT NULL DEFAULT 'cs_ai'")
            old.conn.commit()
            old.close()
        app = App(data_dir=path.parent)
        try:
            pid = app.create_project('Legacy', language_policy={'allowed_languages': ['en', 'zh']})['project_id']
            self.assertEqual(app.projects.get_project(pid)['language_policy']['status'], 'ready')
            pending = app.create_project('Pending')['project_id']
            self.assertEqual(app.projects.get_project(pending)['language_policy']['status'], 'pending')
            ready = app.set_project_language(pending, None, ['zh'])['language_policy']
            self.assertEqual((ready['status'], ready['allowed_languages']), ('ready', ['zh']))
            row = app.store.conn.execute('SELECT discipline FROM projects WHERE id=?', (pending,)).fetchone()
            self.assertEqual(row[0], 'cs_ai')   # the legacy value is left as it was, never read as a choice
        finally:
            app.store.close()


class EligibilityWithoutDiscipline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(data_dir=Path(self.tmp.name))
        self.addCleanup(self.app.store.close)
        patcher = mock.patch.object(self.app.gateway, 'call', side_effect=AssertionError('No model in eligibility'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def paper(self, pid, key, language):
        self.app.store.upsert_papers([{'key': key, 'title': 'An English world model title',
            'abstract': 'A usable abstract about world model learning and prediction.', 'published': '2026-01-01',
            'language': language, 'oa': SYNTHETIC_OA}], pid)

    def keys(self, pid):
        return {c['key'] for c in self.app.build_batch(project_id=pid, exclude_seen=False)['cards']}

    def test_each_language_choice_filters_new_recommendations(self):
        cases = {('en',): {'en'}, ('zh',): {'zh'}, ('en', 'zh'): {'en', 'zh'}}
        for allowed, expected in cases.items():
            with self.subTest(allowed=allowed):
                pid = self.app.create_project('P' + ''.join(allowed), language_policy={'allowed_languages': list(allowed)})['project_id']
                self.paper(pid, 'en-' + pid, 'en')
                self.paper(pid, 'zh-' + pid, 'zh')
                got = {key.split('-')[0] for key in self.keys(pid)}
                self.assertEqual(got, expected)

    def test_a_project_without_any_language_choice_still_asks_for_one(self):
        pid = self.app.create_project('None')['project_id']
        out = self.app.build_batch(project_id=pid)
        self.assertEqual(out['reason_code'], 'language_policy_required')
        self.assertNotIn('学科', out.get('reason', ''))


if __name__ == '__main__':
    unittest.main()
