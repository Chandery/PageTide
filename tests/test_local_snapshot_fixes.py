import tempfile
import unittest
from pathlib import Path

from app.db import Store


class LocalSnapshotFixTests(unittest.TestCase):
    def test_all_tables_and_conversations_survive_consistent_copy(self):
        from app.local_snapshot import create_snapshot, restore_database
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'pagetide.sqlite'); store.init()
            try:
                store.upsert_papers([{'key': 'a', 'title': 'Paper'}])
                store.add_qa('a', 'user', 'A stored question')
                store.set_setting('route_test', {'graph': ['a'], 'revision': 2})
                store.conn.execute('CREATE TABLE future_state(id INTEGER PRIMARY KEY, value TEXT)')
                store.conn.execute('INSERT INTO future_state(value) VALUES (?)', ('future value',)); store.conn.commit()
                (root / 'settings.json').write_text('{"theme":"dark","apiKey":"SECRET"}')
                (root / 'deepseek.key').write_text('SECRET')
                before = [tuple(row) for row in store.conn.execute('SELECT * FROM future_state')]
                snap = create_snapshot(store, root)
                self.assertEqual(snap['format'], 'pagetide.local-snapshot')
                self.assertEqual(snap['version'], 1)
                self.assertIn('future_state', snap['database']['tables'])
                self.assertEqual(snap['database']['tables']['qa_history'], 1)
                self.assertNotIn('SECRET', str(snap))
                self.assertEqual(snap['local_files']['settings.json'], {'theme': 'dark'})
                restored = restore_database(snap, root / 'restored')
                import sqlite3
                with sqlite3.connect(restored) as connection:
                    self.assertEqual(connection.execute('SELECT * FROM future_state').fetchall(), before)
                    self.assertEqual(connection.execute('SELECT content FROM qa_history').fetchone()[0], 'A stored question')
                    self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                with self.assertRaises(ValueError):
                    restore_database(snap, root / 'restored')
                with self.assertRaises(ValueError):
                    restore_database({**snap, 'version': 99}, root / 'invalid')
            finally:
                store.close()

    def test_failed_write_cleans_only_new_destination_and_can_retry(self):
        from app.local_snapshot import create_snapshot, restore_database
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = Store(root/'source.sqlite');store.init()
            try:
                snap=create_snapshot(store,root); target=root/'new-restore'
                with mock.patch('app.local_snapshot.os.replace',side_effect=OSError('disk write fault')):
                    with self.assertRaises(OSError):restore_database(snap,target)
                self.assertFalse(target.exists())
                self.assertTrue(restore_database(snap,target).is_file())
                sentinel=target/'original.txt'; sentinel.write_text('preserve')
                with self.assertRaises(ValueError):restore_database(snap,target)
                self.assertEqual(sentinel.read_text(),'preserve')
            finally:store.close()
