from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from app import migrations
from app.db import Store
from app.service import App
from app.sources import slim
from app.paper_language import policy_from_row


class ProjectLanguageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(data_dir=self.tmp.name)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project('世界模型')['project_id']

    def test_project_language_is_not_inferred_from_name_or_keywords(self):
        for project in self.app.projects.list_projects():
            self.assertEqual(project['language_policy']['status'], 'pending')
            self.assertEqual(project['language_policy']['allowed_languages'], [])

    def test_stem_requires_english_and_invalid_changes_are_atomic(self):
        out = self.app.set_project_language(self.pid, 'stem', ['en'])
        self.assertEqual(out['language_policy']['allowed_languages'], ['en'])
        for discipline, allowed in [('stem', ['zh']), ('unknown', ['en']), ('humanities', []),
                                    ('humanities', 'zh'), ('humanities', ['xx']), ('humanities', [None])]:
            with self.assertRaises(ValueError):
                self.app.set_project_language(self.pid, discipline, allowed)
            self.assertEqual(self.app.projects.get_project(self.pid), out)

    def test_humanities_multiple_languages_are_project_scoped_and_persist(self):
        other = self.app.create_project('历史')['project_id']
        self.app.set_project_language(self.pid, 'stem', ['en'])
        out = self.app.set_project_language(other, 'humanities', ['zh', 'en', 'zh', 'la'])
        self.assertEqual(out['language_policy']['allowed_languages'], ['zh', 'en', 'la'])
        self.assertEqual(self.app.projects.get_project(self.pid)['language_policy']['discipline'], 'stem')
        reopened = App(data_dir=self.tmp.name)
        try:
            self.assertEqual(reopened.projects.get_project(other)['language_policy'], out['language_policy'])
        finally:
            reopened.store.close()

    def test_policy_revision_changes_only_for_changed_policy_and_keeps_history(self):
        self.app.store.upsert_papers([{'key': 'one', 'title': 'History', 'abstract': 'text'}], self.pid)
        bid = self.app.store.create_batch('2026-10-01', ['one'], project_id=self.pid)
        first = self.app.set_project_language(self.pid, 'humanities', ['zh'])['language_policy']
        same = self.app.set_project_language(self.pid, 'humanities', ['zh'])['language_policy']
        changed = self.app.set_project_language(self.pid, 'humanities', ['en'])['language_policy']
        self.assertEqual(first['revision'], same['revision'])
        self.assertEqual(changed['revision'], first['revision'] + 1)
        self.assertEqual(self.app.cards(bid, self.pid)[0]['key'], 'one')

    def test_missing_project_does_not_change_default(self):
        before = self.app.projects.list_projects()
        for bad in ('', None, 'missing'):
            with self.assertRaises(ValueError):
                self.app.set_project_language(bad, 'stem', ['en'])
        self.assertEqual(self.app.projects.list_projects(), before)

    def test_metadata_language_is_preserved_without_inferring_from_english_title(self):
        paper = slim({'id': 'https://openalex.org/W1', 'title': 'An English title', 'language': 'zh'})
        self.assertEqual(paper['metadata_language'], 'zh')
        self.app.store.upsert_papers([paper], self.pid)
        saved = self.app.store.paper(paper['key'])
        self.assertEqual(saved['metadata_language'], 'zh')
        self.assertEqual(saved['metadata_language_source'], 'OpenAlex')
        self.app.store.upsert_papers([{'key': paper['key'], 'title': 'English again'}], self.pid)
        self.assertEqual(self.app.store.paper(paper['key'])['metadata_language'], 'zh')
        self.assertIsNone(slim({'id': 'https://openalex.org/W2', 'title': 'English'})['metadata_language'])

    def test_fulltext_language_evidence_is_bound_to_current_pdf_hash(self):
        store = self.app.store
        store.upsert_papers([{'key': 'pdf', 'title': 'English title', 'language': 'en'}], self.pid)
        self.assertEqual(store.paper_language('pdf')['fulltext_status'], 'unverified')
        old = 'a' * 64; new = 'b' * 64
        store.record_pdf('pdf', 'first.pdf', sha256=old)
        store.record_fulltext_language('pdf', 'zh', old, 'manual')
        self.assertEqual(store.paper_language('pdf')['fulltext_language'], 'zh')
        store.record_pdf('pdf', 'second.pdf', sha256=new)
        self.assertEqual(store.paper_language('pdf')['fulltext_status'], 'unverified')
        with self.assertRaises(ValueError):
            store.record_fulltext_language('pdf', 'en', old, 'manual')
        self.assertEqual(store.conn.execute('SELECT COUNT(*) FROM fulltext_languages').fetchone()[0], 1)
        store.record_pdf('pdf', 'first.pdf', sha256=old)
        self.assertEqual(store.paper_language('pdf')['fulltext_language'], 'zh')

    def test_legacy_migration_backs_up_and_restores_without_choosing_languages(self):
        path = Path(self.tmp.name) / 'old.sqlite'
        with mock.patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if migrations._number(m) < 9]):
            old = Store(path); old.init()
            old.upsert_papers([{'key': 'old', 'title': 'Old English title'}])
            old.close()
        upgraded = Store(path); upgraded.init()
        try:
            self.assertIsNone(upgraded.paper('old')['metadata_language'])
            self.assertIsNone(upgraded.conn.execute('SELECT discipline FROM projects LIMIT 1').fetchone()[0])
            self.assertTrue(path.with_name(path.name + '.pre-v8.bak').is_file())
            upgraded.init()
            self.assertEqual(upgraded.conn.execute('SELECT COUNT(*) FROM schema_version WHERE version=9').fetchone()[0], 1)
            backup = sqlite3.connect(str(path.with_name(path.name + '.pre-v8.bak')))
            try:
                self.assertEqual(backup.execute('SELECT title FROM papers WHERE key=?', ('old',)).fetchone()[0], 'Old English title')
                self.assertNotIn('discipline', [r[1] for r in backup.execute('PRAGMA table_info(projects)')])
            finally:
                backup.close()
        finally:
            upgraded.close()

    def test_migration_failure_rolls_back_columns_and_retries(self):
        path = Path(self.tmp.name) / 'rollback.sqlite'
        with mock.patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if migrations._number(m) < 9]):
            store = Store(path); store.init(); store.close()
        store = Store(path)
        try:
            real = migrations.set_schema_version
            def fail_version(conn, version):
                if version == 9:
                    raise sqlite3.OperationalError('simulated disk full')
                return real(conn, version)
            with mock.patch.object(migrations, 'set_schema_version', side_effect=fail_version):
                with self.assertRaises(sqlite3.OperationalError):
                    store.init()
            self.assertNotIn('discipline', [r[1] for r in store.conn.execute('PRAGMA table_info(projects)')])
            self.assertEqual(migrations.get_schema_version(store.conn), 8)
            store.init()
            self.assertEqual(migrations.get_schema_version(store.conn), 9)
        finally:
            store.close()

    def test_legacy_discipline_column_is_preserved_and_upgrade_restarts(self):
        path = Path(self.tmp.name) / 'legacy-discipline.sqlite'
        with mock.patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if migrations._number(m) < 9]):
            old = Store(path); old.init()
            old.conn.execute('ALTER TABLE projects ADD COLUMN discipline TEXT')
            old.conn.execute('UPDATE projects SET discipline=?', ('legacy research field',))
            old.upsert_papers([{'key': 'legacy', 'title': 'Preserved paper'}])
            old.close()
        upgraded = Store(path)
        try:
            upgraded.init()
            self.assertEqual(migrations.get_schema_version(upgraded.conn), 9)
            row = upgraded.conn.execute('SELECT * FROM projects LIMIT 1').fetchone()
            self.assertEqual(row['discipline'], 'legacy research field')
            self.assertEqual(row['allowed_languages'], '[]')
            self.assertEqual(row['language_policy_revision'], 0)
            self.assertEqual(policy_from_row(row)['status'], 'pending')
            self.assertEqual(upgraded.paper('legacy')['title'], 'Preserved paper')
            upgraded.init()
            self.assertEqual(upgraded.conn.execute('SELECT COUNT(*) FROM schema_version WHERE version=9').fetchone()[0], 1)
            backup = sqlite3.connect(str(path.with_name(path.name + '.pre-v8.bak')))
            try:
                self.assertEqual(backup.execute('SELECT discipline FROM projects LIMIT 1').fetchone()[0], 'legacy research field')
                self.assertNotIn('allowed_languages', [r[1] for r in backup.execute('PRAGMA table_info(projects)')])
            finally:
                backup.close()
        finally:
            upgraded.close()

    def test_legacy_discipline_upgrade_failure_rolls_back_and_retries(self):
        path = Path(self.tmp.name) / 'legacy-rollback.sqlite'
        with mock.patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if migrations._number(m) < 9]):
            old = Store(path); old.init()
            old.conn.execute('ALTER TABLE projects ADD COLUMN discipline TEXT')
            old.conn.execute("UPDATE projects SET discipline='stem'")
            old.conn.commit(); old.close()
        store = Store(path)
        try:
            real = migrations.set_schema_version
            def fail_version(conn, version):
                if version == 9:
                    raise sqlite3.OperationalError('simulated disk full')
                return real(conn, version)
            with mock.patch.object(migrations, 'set_schema_version', side_effect=fail_version):
                with self.assertRaises(sqlite3.OperationalError):
                    store.init()
            self.assertEqual(migrations.get_schema_version(store.conn), 8)
            self.assertEqual(store.conn.execute('SELECT discipline FROM projects LIMIT 1').fetchone()[0], 'stem')
            self.assertNotIn('allowed_languages', [r[1] for r in store.conn.execute('PRAGMA table_info(projects)')])
            store.init()
            self.assertEqual(policy_from_row(store.conn.execute('SELECT * FROM projects LIMIT 1').fetchone())['status'], 'pending')
        finally:
            store.close()

    def test_legacy_nonnull_discipline_supports_pending_creation_and_default_rebuild(self):
        path = Path(self.tmp.name) / 'nonnull' / 'paperdighelper.sqlite'
        with mock.patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if migrations._number(m) < 9]):
            old = Store(path); old.init()
            old.conn.execute("ALTER TABLE projects ADD COLUMN discipline TEXT NOT NULL DEFAULT 'cs_ai'")
            old.conn.commit(); old.close()
        app = App(data_dir=path.parent)
        try:
            pid = app.create_project('Legacy pending project')['project_id']
            policy = app.projects.get_project(pid)['language_policy']
            self.assertEqual(policy['discipline'], 'cs_ai')
            self.assertEqual(policy['status'], 'pending')
            self.assertEqual(policy['allowed_languages'], [])
            self.assertEqual(app.set_project_language(pid, 'stem', ['en'])['language_policy']['status'], 'ready')
            app.store.conn.execute('DELETE FROM projects'); app.store.conn.commit()
            rebuilt = app.get_default_project_id()
            self.assertEqual(app.projects.get_project(rebuilt)['language_policy']['status'], 'pending')
            self.assertEqual(app.projects.get_project(rebuilt)['language_policy']['discipline'], 'cs_ai')
        finally:
            app.store.close()

    def test_unversioned_extraction_does_not_invent_a_current_pdf_binding(self):
        store = self.app.store
        store.upsert_papers([{'key': 'body', 'title': 'Body'}], self.pid)
        store.record_pdf('body', 'new.pdf', sha256='b' * 64)
        store.save_fulltext('body', [{'page': 1, 'text': 'Maybe extracted from an older PDF.'}])
        self.assertIsNone(store.conn.execute('SELECT source_pdf_sha256 FROM fulltext WHERE paper_key=?', ('body',)).fetchone()[0])

    def test_stale_extraction_is_rejected_and_current_extraction_is_bound(self):
        store = self.app.store
        store.upsert_papers([{'key': 'body', 'title': 'Body'}], self.pid)
        old = 'a' * 64; current = 'b' * 64
        store.record_pdf('body', 'old.pdf', sha256=old)
        store.save_fulltext('body', [{'page': 1, 'text': 'Old text'}], source_pdf_sha256=old)
        store.record_pdf('body', 'new.pdf', sha256=current)
        with self.assertRaises(ValueError):
            store.save_fulltext('body', [{'page': 1, 'text': 'Late old text'}], source_pdf_sha256=old)
        self.assertEqual(store.fulltext_pages('body')[0]['text'], 'Old text')
        store.save_fulltext('body', [{'page': 1, 'text': 'Current text'}], source_pdf_sha256=current)
        self.assertEqual(store.conn.execute('SELECT source_pdf_sha256 FROM fulltext WHERE paper_key=?', ('body',)).fetchone()[0], current)
        with self.assertRaises(ValueError):
            store.save_fulltext('body', [{'page': 1, 'text': 'Partial overwrite'},
                                        {'page': 'invalid', 'text': 'Invalid page'}], source_pdf_sha256=current)
        self.assertEqual(store.fulltext_pages('body')[0]['text'], 'Current text')
