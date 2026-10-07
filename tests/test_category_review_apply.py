"""Actual temporary SQLite apply/undo/CAS tests, never an owner's library."""
import tempfile
import unittest
from pathlib import Path
from app.db import Store
from app.organization import Organization, Conflict
from app.organization_facets import structure_hash
from app.clustering import corpus_fingerprint


class ApplyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / 'test.sqlite'); self.store.init(); self.addCleanup(self.store.close)
        self.store.upsert_papers([{'key': 'a', 'title': 'World models with JEPA'}, {'key': 'b', 'title': 'Video world model'}])
        for key in ('a', 'b'): self.store.save_to_library(key)
        self.org = Organization(self.store)
        self.org.action({'action':'direction-save','name':'World States','color':'#123456'})
        self.old = self.org.snapshot()['directions'][0]['id']
        self.org.action({'action':'membership','keys':['a','b'],'add':[self.old]})
        self.org.action({'action':'note','key':'a','text':'Owner note','version':0})

    def plan(self):
        return {'categories':[{'id':self.old,'action':'delete','reason':'标题残片'}],
                'new_categories':[{'id':'new-world','name':'世界模型','parent_id':None,'reason':'明确方向'}],
                'papers':[{'key':k,'categories':['new-world'],'reason':'标题依据'} for k in ('a','b')]}

    def preview(self, plan=None):
        rev, data = self.org._load(); scope = None
        return self.org.store_ai_review(plan or self.plan(),rev,corpus_fingerprint(self.org._corpus(scope)),
                                       structure_hash(data['directions'],data['memberships']),scope)

    def apply(self, snapshot):
        p = snapshot['suggestions']
        return self.org.action({'action':'apply-ai-review','ai_token':p['ai_token'],'fingerprint':p['fingerprint']})

    def test_preview_changes_nothing_apply_deletes_bad_label_keeps_notes_and_undo_restores(self):
        before = self.org.snapshot()
        preview = self.preview()
        self.assertEqual(preview['directions'], before['directions'])
        after = self.apply(preview)
        self.assertEqual([d['name'] for d in after['directions']], ['世界模型'])
        self.assertEqual(after['apply_result']['deleted_categories'], 1)
        self.assertEqual([(p['key'],p['note']) for p in after['items']],[(p['key'],p['note']) for p in before['items']])
        events = self.store.conn.execute('SELECT COUNT(*) FROM org_events').fetchone()[0]
        self.assertEqual(self.apply(preview)['apply_result']['changed_papers'], 0)
        self.assertEqual(self.store.conn.execute('SELECT COUNT(*) FROM org_events').fetchone()[0], events)
        undo = self.org.action({'action':'undo'})
        self.assertEqual(undo['directions'], before['directions'])
        self.assertEqual([p['directions'] for p in undo['items']], [p['directions'] for p in before['items']])

    def test_changed_metadata_rejects_old_preview(self):
        preview = self.preview()
        self.store.conn.execute("UPDATE papers SET abstract='new evidence' WHERE key='a'"); self.store.conn.commit()
        with self.assertRaises(Conflict): self.apply(preview)
        self.assertEqual(self.org.snapshot()['directions'][0]['id'], self.old)

    def test_incomplete_review_cannot_be_installed(self):
        plan = self.plan(); plan['papers'].pop()
        with self.assertRaises(ValueError): self.preview(plan)
        self.assertNotIn('suggestions',self.org.snapshot())

    def test_archived_holder_blocks_delete_without_any_partial_edit(self):
        self.store.conn.execute("DELETE FROM library WHERE paper_key='b'"); self.store.conn.commit()
        plan=self.plan(); plan['papers']=plan['papers'][:1]
        before=self.org.snapshot()
        with self.assertRaises(ValueError): self.preview(plan)
        self.assertEqual(self.org.snapshot(),before)

    def test_final_write_boundary_rejects_method_root_and_unsupported_new_label(self):
        plan = self.plan(); plan['new_categories'][0]['name'] = 'JEPA'
        with self.assertRaisesRegex(ValueError, '方法类别'): self.preview(plan)
        plan = self.plan(); plan['new_categories'].append({'id':'unused','name':'表征学习','parent_id':None})
        with self.assertRaisesRegex(ValueError, '证据支持'): self.preview(plan)
