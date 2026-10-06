import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.db import Store
from app.organization import Organization
from app.clustering import corpus_fingerprint

class SelectedSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.sqlite');self.store.init();self.addCleanup(self.store.close)
        self.papers=[dict(key=k,title='Robot control') for k in ('a','b')]
        self.store.upsert_papers(self.papers)
        for p in self.papers:self.store.save_to_library(p['key'],'keep note')
        self.org=Organization(self.store)
        snap=self.org.action(dict(action='direction-save',name='My folder',color='#123456'))
        self.original=snap['directions'][0]['id']
        self.org.action(dict(action='membership',keys=['a','b'],add=[self.original]))
    def preview(self):
        preview=dict(fingerprint=corpus_fingerprint(self.papers),groups=[dict(id='cluster-new',name='机器人',color='#64748b',keys=['a','b'])])
        with patch('app.organization.review_papers',return_value=preview): self.org.action(dict(action='suggest'))
        return preview
    def apply(self,preview):
        return self.org.action(dict(action='apply-suggestions',apply_mode='add',fingerprint=preview['fingerprint'],suggestions=preview['groups']))
    def test_explicit_add_applies_to_classified_protected_papers_and_undo(self):
        before=self.org.snapshot();result=self.apply(self.preview())
        for p in result['items']:
            self.assertIn(self.original,p['directions']);self.assertEqual(len(p['directions']),2)
            self.assertEqual(p['note'],'keep note')
        self.assertEqual(result['apply_result']['added_memberships'],2)
        self.assertEqual(result['apply_result']['changed_papers'],2)
        undone=self.org.action(dict(action='undo'))
        self.assertEqual(undone['items'],before['items']);self.assertEqual(undone['directions'],before['directions'])
    def test_repeat_is_idempotent_and_reports_already_present(self):
        first=self.apply(self.preview());preview=self.preview();before=self.org.snapshot()
        result=self.apply(preview)
        self.assertEqual(result['directions'],first['directions'])
        self.assertEqual(result['apply_result']['added_memberships'],0)
        self.assertEqual(result['apply_result']['already_present'],2)
        self.assertEqual(result['revision'],before['revision'])
    def test_renamed_manual_target_is_not_overwritten(self):
        first=self.apply(self.preview());target=next(d for d in first['directions'] if d['id']!=self.original)
        self.org.action(dict(action='direction-save',id=target['id'],name='User renamed',color='#123456'))
        second=self.apply(self.preview())
        self.assertEqual(next(d for d in second['directions'] if d['id']==target['id'])['name'],'User renamed')
        self.assertEqual(len(second['items'][0]['directions']),3)
    def test_explicit_add_rejects_empty_selection(self):
        preview=self.preview()
        for selection in ([], None):
            body=dict(action='apply-suggestions',apply_mode='add',fingerprint=preview['fingerprint'])
            if selection is not None:body['suggestions']=selection
            with self.assertRaises(ValueError):self.org.action(body)

    def test_explicit_add_rejects_empty_group_without_mutation(self):
        preview=self.preview();before=self.org.snapshot()
        selection=[dict(preview['groups'][0],keys=[])]
        with self.assertRaises(ValueError):
            self.org.action(dict(action='apply-suggestions',apply_mode='add',
                                 fingerprint=preview['fingerprint'],suggestions=selection))
        self.assertEqual(self.org.snapshot(),before)
