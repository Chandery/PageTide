"""A rejected upload remains visible across native restarts with changing ports."""
import io
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path

from app.db import Store
from app.library_import import LibraryImport, MAX_FILES
from app.project import ProjectManager
from tests.pdf_fixture import minimal_pdf


class ImportUploadReceipts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / 'db.sqlite')
        self.store.init()
        self.addCleanup(self.store.conn.close)
        self.project = ProjectManager(self.store).create_project('public receipt test')
        self.imp = LibraryImport(self.data, self.store)
        self.batch = self.imp.create_batch(self.project, 'folder', 'papers', {'online': False})['id']

    def test_rejected_pdf_survives_new_connection_and_snapshot(self):
        bad = b'%PDF-1.7\ntruncated'
        with self.assertRaises(ValueError):
            self.imp.add_pdf(self.batch, 'papers/broken.pdf', io.BytesIO(bad), len(bad))
        self.assertEqual(self.imp.batch(self.batch)['items'], [])
        other = Store(self.data / 'db.sqlite')
        self.addCleanup(other.conn.close)
        receipt = LibraryImport(self.data, other).batch(self.batch)['upload_failures']
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt[0]['path'], 'papers/broken.pdf')
        self.assertIn('PDF', receipt[0]['message'])
        self.assertEqual(self.imp.list_batches(self.project)[0]['upload_failures'], receipt)

    def test_successful_resend_clears_only_its_failure(self):
        for path in ('papers/a.pdf', 'papers/b.pdf'):
            with self.assertRaises(ValueError):
                self.imp.add_pdf(self.batch, path, io.BytesIO(b'bad'), 3)
        good = minimal_pdf('new valid source')
        self.imp.add_pdf(self.batch, 'papers/a.pdf', io.BytesIO(good), len(good))
        receipt = self.imp.batch(self.batch)['upload_failures']
        self.assertEqual([r['path'] for r in receipt], ['papers/b.pdf'])

    def test_closed_batch_never_records_late_failure(self):
        self.imp.discard(self.batch)
        with self.assertRaises(ValueError):
            self.imp.add_pdf(self.batch, 'papers/broken.pdf', io.BytesIO(b'bad'), 3)
        self.assertEqual(self.imp.batch(self.batch)['upload_failures'], [])

    def test_concurrent_old_schema_initialization_serializes_check_and_alter(self):
        self.store.conn.execute('DROP TABLE import_upload_failures')
        self.store.conn.execute('CREATE TABLE import_upload_failures(batch_id TEXT NOT NULL, relative_path TEXT NOT NULL, '
                                'message TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(batch_id,relative_path))')
        self.store.conn.execute('INSERT INTO import_upload_failures VALUES(?,?,?,?)',
                                (self.batch, 'papers/broken.pdf', 'keep this failure', '2026-10-08T00:00:00Z'))
        self.store.conn.commit()
        first_checked, release_first, second_started, second_checked = (threading.Event() for _ in range(4))
        errors = []
        class GateConnection:
            def __init__(self, conn, first):
                self.conn, self.first = conn, first
            def __getattr__(self, name):
                return getattr(self.conn, name)
            def execute(self, sql, *args):
                result = self.conn.execute(sql, *args)
                if sql.startswith('PRAGMA table_info(import_upload_failures)'):
                    rows = list(result)  # Freeze each real SQLite view before ALTER.
                    if self.first:
                        first_checked.set()
                        if not release_first.wait(5):
                            raise RuntimeError('schema probe timed out')
                    else:
                        second_checked.set()
                    return iter(rows)
                return result
        def construct(first):
            store = Store(self.data / 'db.sqlite')
            try:
                store.conn = GateConnection(store.conn, first)
                if not first:
                    second_started.set()
                LibraryImport(self.data, store)
            except Exception as exc:
                errors.append(exc)
            finally:
                store.conn.close()
        workers = [threading.Thread(target=construct, args=(first,)) for first in (True, False)]
        try:
            workers[0].start()
            self.assertTrue(first_checked.wait(5))
            workers[1].start()
            self.assertTrue(second_started.wait(5))
            self.assertFalse(second_checked.wait(.5), 'second constructor read the old schema while the first migration was pending')
        finally:
            release_first.set()
            for worker in workers:
                if worker.ident is not None:
                    worker.join(5)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(errors, [])
        self.assertEqual(self.store.conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        row = self.store.conn.execute('SELECT * FROM import_upload_failures').fetchone()
        self.assertEqual(row['message'], 'keep this failure')
        self.assertEqual(row['attempt'], '')

    def test_receipts_are_bounded_and_replace_same_path(self):
        for n in range(MAX_FILES):
            path = f'papers/{n}.pdf'
            token = self.imp._begin_upload_attempt(self.batch, path)
            self.imp._record_upload_failure(self.batch, path, 'failure', token)
        token = self.imp._begin_upload_attempt(self.batch, 'papers/0.pdf')
        self.imp._record_upload_failure(self.batch, 'papers/0.pdf', 'new failure', token)
        token = self.imp._begin_upload_attempt(self.batch, 'papers/overflow.pdf')
        self.imp._record_upload_failure(self.batch, 'papers/overflow.pdf', 'ignored overflow', token)
        receipt = self.imp.batch(self.batch)['upload_failures']
        self.assertEqual(len(receipt), MAX_FILES)
        self.assertEqual(next(r['message'] for r in receipt if r['path'] == 'papers/0.pdf'), 'new failure')
        self.assertNotIn('papers/overflow.pdf', [r['path'] for r in receipt])

    def test_late_failed_attempt_cannot_resurrect_cleared_error(self):
        other = Store(self.data / 'db.sqlite')
        self.addCleanup(other.conn.close)
        newer = LibraryImport(self.data, other)
        good = minimal_pdf('newer public PDF')
        record = self.imp._record_upload_failure
        def older_failed(*args):
            newer.add_pdf(self.batch, 'papers/a.pdf', io.BytesIO(good), len(good))
            record(*args)
        with mock.patch.object(self.imp, '_record_upload_failure', side_effect=older_failed):
            with self.assertRaises(ValueError):
                self.imp.add_pdf(self.batch, 'papers/a.pdf', io.BytesIO(b'bad'), 3)
        self.assertEqual(self.imp.batch(self.batch)['upload_failures'], [])
        self.assertEqual(len(self.imp.batch(self.batch)['items']), 1)

    def test_recorded_failure_refreshes_active_batch_retention(self):
        token = self.imp._begin_upload_attempt(self.batch, 'papers/a.pdf')
        self.store.conn.execute("UPDATE import_batches SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (self.batch,))
        self.store.conn.commit()
        self.imp._record_upload_failure(self.batch, 'papers/a.pdf', 'new failure', token)
        self.assertEqual(len(self.imp.list_batches(self.project)), 1)

    def test_previous_receipt_schema_migrates_without_losing_failure(self):
        self.store.conn.execute('DROP TABLE import_upload_failures')
        self.store.conn.execute('CREATE TABLE import_upload_failures(batch_id TEXT NOT NULL, relative_path TEXT NOT NULL, '
                                'message TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(batch_id,relative_path))')
        self.store.conn.execute('INSERT INTO import_upload_failures VALUES(?,?,?,?)',
                                (self.batch, 'papers/a.pdf', 'old PDF failure', '2000-01-01'))
        self.store.conn.commit()
        migrated = LibraryImport(self.data, self.store)
        self.assertEqual(migrated.batch(self.batch)['upload_failures'][0]['message'], 'old PDF failure')
        self.assertEqual(self.store.conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
