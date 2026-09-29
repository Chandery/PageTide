import tempfile
import unittest
from pathlib import Path
from app.db import Store
from app.organization import Organization


class CategoryTreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite'
        self.store = Store(self.path)
        self.store.init()
        self.addCleanup(self.store.close)
        self.store.upsert_papers([dict(key='p', title='One paper')])
        self.store.save_to_library('p', 'Keep note')
        self.org = Organization(self.store)

    def create(self, name, parent=None):
        snap = self.org.action(dict(action='direction-save', name=name, color='#123456', parent_id=parent))
        return snap['directions'][-1]['id']

    def test_nested_categories_persist_and_papers_have_multiple_memberships(self):
        root = self.create('机器学习')
        child = self.create('世界模型', root)
        leaf = self.create('机器人', child)
        other = self.create('医学')
        self.org.action(dict(action='membership', keys=['p'], add=[leaf, other]))
        self.assertEqual({d['id']: d['parent_id'] for d in self.org.snapshot()['directions']},
                         {root: None, child: root, leaf: child, other: None})
        second = Store(self.path)
        try:
            snap = Organization(second).snapshot()
            self.assertEqual(set(snap['items'][0]['directions']), {leaf, other})
            self.assertEqual(snap['directions'][2]['parent_id'], child)
        finally:
            second.close()
        self.org.action(dict(action='membership', keys=['p'], add=[child], remove=[leaf]))
        self.assertEqual(set(self.org.snapshot()['items'][0]['directions']), {child, other})
        self.assertEqual(self.org.snapshot()['items'][0]['note'], 'Keep note')

    def test_cycles_unknown_parent_and_invalid_parent_rejected_atomically(self):
        root = self.create('Root')
        child = self.create('Child', root)
        leaf = self.create('Leaf', child)
        before = self.org.snapshot()
        for parent in (root, child, leaf, 'missing', 2, []):
            with self.subTest(parent=parent), self.assertRaises(ValueError):
                self.org.action(dict(action='direction-save', id=root, name='Root', color='#123456', parent_id=parent))
            self.assertEqual(self.org.snapshot(), before)

    def test_delete_only_category_promotes_children_preserves_papers_and_undo(self):
        root = self.create('Root')
        child = self.create('Child', root)
        leaf = self.create('Leaf', child)
        self.org.action(dict(action='membership', keys=['p'], add=[child, leaf]))
        before = self.org.snapshot()
        deleted = self.org.action(dict(action='direction-delete', id=child))
        self.assertEqual(next(d for d in deleted['directions'] if d['id']==leaf)['parent_id'], root)
        self.assertEqual(deleted['items'][0]['directions'], [leaf])
        restored = self.org.action(dict(action='undo'))
        self.assertEqual(restored['directions'], before['directions'])
        self.assertEqual(restored['items'], before['items'])
        deleted = self.org.action(dict(action='direction-delete', id=root))
        self.assertIsNone(next(d for d in deleted['directions'] if d['id']==child)['parent_id'])

    def test_legacy_flat_data_gets_root_without_migration(self):
        root = self.create('Legacy')
        self.store.conn.execute("UPDATE org_projects SET data=json_remove(data,'$.directions[0].parent_id')")
        self.store.conn.commit()
        self.assertIsNone(self.org.snapshot()['directions'][0]['parent_id'])
        self.org.action(dict(action='direction-save', id=root, name='Renamed', color='#234567'))
        self.assertIsNone(self.org.snapshot()['directions'][0]['parent_id'])

    def test_reparent_preserves_descendants_and_memberships(self):
        a = self.create('A')
        b = self.create('B')
        leaf = self.create('Leaf', a)
        self.org.action(dict(action='membership', keys=['p'], add=[leaf]))
        moved = self.org.action(dict(action='direction-save', id=a, name='A renamed', color='#123456', parent_id=b))
        self.assertEqual(next(d for d in moved['directions'] if d['id']==leaf)['parent_id'], a)
        self.assertEqual(moved['items'][0]['directions'], [leaf])
