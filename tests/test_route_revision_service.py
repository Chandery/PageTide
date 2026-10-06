"""Revision previews, authoritative progress boundaries and one atomic undo."""
import copy
import json
import threading
import unittest
from unittest import mock
from app.organization import Conflict, Organization, read_route
from app.service import App
from test_route_store import Fixture, PLAN

BRIEF = {'goal': '理解世界模型', 'known': '', 'include': '', 'exclude': '', 'structure': '补必要前置'}


def patch(*operations): return {'operations': list(operations)}


class RevisionServiceTests(Fixture):
    def setUp(self):
        super().setUp()
        self.route = self.app.route_save(self.pid, plan=PLAN)
        for i in range(2):
            key = 'p'+str(i)
            self.add(key, 'Crystal growth epitaxy review', 'Crystal growth lattice epitaxy foundational theory')
            self.app.record_feedback(key, 'useful', project_id=self.pid)
            self.app.record_feedback(key, 'understood', project_id=self.pid)

    def preview(self, value=None, brief=None):
        return self.app.route_revision_preview(self.pid, brief or BRIEF, value or patch(), revision=self.app.route_get(self.pid)['revision'])

    def confirm(self, draft): return self.app.route_revision_confirm(self.pid, draft['draft_id'])

    def semantic(self): return patch({'op': 'update_node', 'ref': 'c1', 'changes': {'name': 'Revised crystal basics'}})

    def events(self): return self.app.store.conn.execute('SELECT COUNT(*) FROM org_events WHERE project=?',(self.pid,)).fetchone()[0]

    def test_preview_does_not_change_graph_brief_progress_or_undo(self):
        before=self.app.route_get(self.pid); count=self.events()
        with mock.patch.object(self.app.gateway, 'call', side_effect=AssertionError('no AI')):
            draft=self.preview(self.semantic())
        self.assertEqual(self.app.route_get(self.pid), before)
        self.assertEqual(self.events(), count)
        self.assertEqual(draft['brief'], BRIEF)
        self.assertTrue(draft['changes']['reset'])
        self.assertNotEqual(draft['after']['progress'], before['progress'])
        self.assertEqual(self.app.route_revision_draft(self.pid)['draft_id'],draft['draft_id'])

    def test_confirm_persists_brief_graph_cutoff_and_resets_manual_in_one_event(self):
        cid=self.ids()['Crystal basics']; self.app.route_manual(self.pid,cid,'mastered'); self.app.route_watch(self.pid,cid,True)
        old=self.app.route_get(self.pid); count=self.events(); draft=self.preview(self.semantic()); saved=self.confirm(draft)
        self.assertEqual(saved['brief'], BRIEF)
        self.assertEqual(self.events(),count+1)
        self.assertNotIn(cid,saved['manual'])
        self.assertIn(cid,saved['watch'])
        node=next(c for c in saved['graph']['concepts'] if c['id']==cid)
        self.assertGreaterEqual(node['progress_since_feedback_id'],4)
        self.assertEqual(saved['progress'][cid]['understood'],0)
        self.assertEqual(saved['progress'][cid]['useful'],2)
        again=App(root=str(self.root),data_dir=str(self.root/'data')); self.addCleanup(again.store.close)
        self.assertEqual(again.route_get(self.pid)['brief'],BRIEF)
        self.assertEqual(again.route_get(self.pid)['graph'],saved['graph'])
        undone=self.app.route_undo(self.pid,event=saved['undo']['id'])
        for field in ['graph','manual','watch','brief','progress']:
            self.assertEqual(undone.get(field),old.get(field),field)

    def test_new_identity_is_identical_in_preview_and_confirmation(self):
        draft=self.preview(patch({'op':'add_node','ref':'n1','node':{'name':'New branch','terms':['new branch']}}))
        ids=draft['changes']['added']; saved=self.confirm(draft)
        self.assertEqual(ids,[c['id'] for c in saved['graph']['concepts'] if c['name']=='New branch'])
        self.assertEqual(saved['graph'],draft['after']['graph'])

    def test_double_confirm_is_idempotent_and_undo_prevents_reconfirmation(self):
        draft=self.preview(self.semantic()); first=self.confirm(draft); count=self.events()
        second=self.confirm(draft)
        self.assertTrue(second['duplicate']); self.assertEqual(self.events(),count)
        self.app.route_undo(self.pid,event=first['undo']['id'])
        with self.assertRaises(Conflict): self.confirm(draft)

    def test_changed_map_or_effective_feedback_refuses_old_preview_without_losing_it(self):
        draft=self.preview(self.semantic()); self.app.route_watch(self.pid,self.ids()['Epitaxy'],True)
        before=self.app.route_get(self.pid)
        with self.assertRaises(Conflict): self.confirm(draft)
        self.assertEqual(self.app.route_get(self.pid),before)
        self.assertTrue(self.app.route_revision_draft(self.pid)['stale'])
        fresh=self.preview(self.semantic()); last=self.app.latest_feedback(self.pid)['p1']['familiar']['id']
        largest=self.app.store.conn.execute('SELECT MAX(id) FROM feedback').fetchone()[0]
        self.app.undo_feedback(last,self.pid)
        self.assertEqual(self.app.store.conn.execute('SELECT MAX(id) FROM feedback').fetchone()[0],largest)
        with self.assertRaises(Conflict): self.confirm(fresh)
        self.assertEqual(self.app.route_revision_draft(self.pid)['draft_id'],fresh['draft_id'])

    def test_snapshot_includes_current_paper_content_and_freeze(self):
        draft=self.preview(self.semantic())
        self.app.store.conn.execute("UPDATE papers SET abstract='a different concept' WHERE key='p0'");self.app.store.conn.commit()
        with self.assertRaises(Conflict):self.confirm(draft)
        draft=self.preview(self.semantic());self.app.set_profile_frozen(True,self.pid)
        with self.assertRaises(Conflict):self.confirm(draft)

    def test_snapshot_checked_inside_write_transaction(self):
        draft=self.preview(self.semantic()); org=self.app._route_org(self.pid); original=org.action
        def interleave(body,**kw):
            self.app.undo_feedback(self.app.latest_feedback(self.pid)['p1']['familiar']['id'],self.pid)
            return original(body,**kw)
        with mock.patch.object(self.app,'_route_org',return_value=org), mock.patch.object(org,'action',side_effect=interleave):
            with self.assertRaises(Conflict):self.confirm(draft)
        self.assertEqual(self.app.route_get(self.pid)['graph'],self.route['graph'])

    def test_late_setting_failure_rolls_back_event_graph_and_brief(self):
        draft=self.preview(self.semantic()); before=self.app.route_get(self.pid);count=self.events()
        self.app.store.conn.execute("CREATE TRIGGER reject_revision_marker BEFORE UPDATE ON settings WHEN NEW.key LIKE 'route_revision_%' BEGIN SELECT RAISE(ABORT,'injected'); END");self.app.store.conn.commit()
        with self.assertRaises(Exception):self.confirm(draft)
        self.assertEqual(self.app.route_get(self.pid),before);self.assertEqual(self.events(),count)
        self.app.store.conn.execute('DROP TRIGGER reject_revision_marker');self.app.store.conn.commit()
        self.assertFalse(self.app.route_revision_draft(self.pid).get('confirmed'))
        self.confirm(draft)

    def test_newer_preview_is_not_overwritten_by_old_confirm(self):
        old=self.preview(self.semantic());new=self.preview(patch(),{**BRIEF,'goal':'另一个目标'})
        with self.assertRaises(Conflict):self.confirm(old)
        self.assertEqual(self.app.route_revision_draft(self.pid)['draft_id'],new['draft_id'])

    def test_invalid_patch_does_not_destroy_saved_draft(self):
        old=self.preview(self.semantic())
        with self.assertRaises(ValueError):self.preview(patch({'op':'remove_node','ref':'c3'}))
        self.assertEqual(self.app.route_revision_draft(self.pid)['draft_id'],old['draft_id'])

    def test_brief_only_then_identical_empty_patch_makes_no_second_event(self):
        draft=self.preview();first=self.confirm(draft); count=self.events()
        self.assertEqual(first['brief'],BRIEF)
        same=self.preview();self.confirm(same);self.assertEqual(self.events(),count)

    def test_drafts_are_project_scoped_and_deleted_with_project(self):
        draft=self.preview(self.semantic())
        with self.assertRaises(ValueError):self.app.route_revision_confirm(self.other,draft['draft_id'])
        self.assertIsNone(self.app.route_revision_draft(self.other))
        self.app.delete_project(self.pid)
        self.assertIsNone(self.app.store.get_setting('route_revision_'+self.pid))

    def test_reconfirm_understood_after_reset_is_once_and_interest_is_unchanged(self):
        draft=self.preview(self.semantic());saved=self.confirm(draft);cid=saved['graph']['concepts'][0]['id']
        prior=self.app.latest_feedback(self.pid)['p0'];new=self.app.record_feedback('p0','understood',project_id=self.pid)
        self.assertGreater(new['feedback_id'],prior['familiar']['id'])
        self.assertFalse(new.get('duplicate',False))
        duplicate=self.app.record_feedback('p0','understood',project_id=self.pid)
        self.assertTrue(duplicate['duplicate']);self.assertEqual(duplicate['feedback_id'],new['feedback_id'])
        self.assertEqual(self.app.latest_feedback(self.pid)['p0']['id'],prior['id'])
        self.assertEqual(self.app.route_get(self.pid)['progress'][cid]['understood'],1)
        self.app.undo_feedback(new['feedback_id'],self.pid)
        self.assertEqual(self.app.route_get(self.pid)['progress'][cid]['understood'],0)

    def test_fresh_too_hard_after_reset_is_recorded_once(self):
        prior=self.app.record_feedback('p0','too_hard',project_id=self.pid)
        saved=self.confirm(self.preview(self.semantic()));cid=saved['graph']['concepts'][0]['id']
        new=self.app.record_feedback('p0','too_hard',project_id=self.pid)
        self.assertGreater(new['feedback_id'],prior['feedback_id'])
        self.assertTrue(self.app.record_feedback('p0','too_hard',project_id=self.pid)['duplicate'])
        self.assertEqual(self.app.route_get(self.pid)['progress'][cid]['too_hard'],1)
        self.assertEqual(self.app.latest_feedback(self.pid)['p0']['action'],'useful')

    def test_shared_connection_undo_cannot_commit_a_failed_confirmation(self):
        draft=self.preview(self.semantic());before=self.app.route_get(self.pid);count=self.events()
        entered=threading.Event();attempted=threading.Event();finish=threading.Event();errors=[]
        feedback=self.app.latest_feedback(self.pid)['p1']['familiar']['id']
        def late_fail(pid,value):
            entered.set();self.assertTrue(attempted.wait(5));raise ValueError('injected marker failure')
        def undo():
            entered.wait(5);attempted.set()
            try:self.app.undo_feedback(feedback,self.pid)
            except BaseException as exc:errors.append(exc)
            finally:finish.set()
        worker=threading.Thread(target=undo);worker.start()
        with mock.patch.object(self.app,'_write_route_revision',side_effect=late_fail):
            with self.assertRaises(ValueError):self.confirm(draft)
        self.assertTrue(finish.wait(5));worker.join(5)
        self.assertEqual(errors,[])
        self.assertEqual(self.app.route_get(self.pid)['graph'],before['graph']);self.assertEqual(self.events(),count)
        self.assertFalse(self.app.route_revision_draft(self.pid)['confirmed'])

    def test_reentrant_undo_or_freeze_refuses_before_early_commit(self):
        draft=self.preview(self.semantic());before=self.app.route_get(self.pid);count=self.events()
        feedback=self.app.latest_feedback(self.pid)['p1']['familiar']['id']
        for write in [lambda:self.app.undo_feedback(feedback,self.pid), lambda:self.app.set_profile_frozen(True,self.pid),
                      lambda:self.app.restore_default_profile(self.pid)]:
            with mock.patch.object(self.app,'_write_route_revision',side_effect=lambda *args:write()):
                with self.assertRaises(RuntimeError):self.confirm(draft)
            self.assertEqual(self.app.route_get(self.pid),before);self.assertEqual(self.events(),count)

    def test_shared_connection_profile_restore_cannot_commit_failed_confirmation(self):
        self.app.set_profile_frozen(True,self.pid)
        draft=self.preview(self.semantic());before=self.app.route_get(self.pid);count=self.events()
        entered=threading.Event();attempted=threading.Event();finish=threading.Event();errors=[]
        def late_fail(pid,value):
            entered.set();self.assertTrue(attempted.wait(5));raise ValueError('injected marker failure')
        def restore():
            entered.wait(5);attempted.set()
            try:self.app.restore_default_profile(self.pid)
            except BaseException as exc:errors.append(exc)
            finally:finish.set()
        worker=threading.Thread(target=restore);worker.start()
        with mock.patch.object(self.app,'_write_route_revision',side_effect=late_fail):
            with self.assertRaises(ValueError):self.confirm(draft)
        self.assertTrue(finish.wait(5));worker.join(5);self.assertEqual(errors,[])
        self.assertEqual(self.app.route_get(self.pid)['graph'],before['graph']);self.assertEqual(self.events(),count)
        self.assertFalse(self.app.route_revision_draft(self.pid)['confirmed'])

    def test_frozen_profile_preserved_but_explicit_reset_can_be_reconfirmed(self):
        self.app.set_profile_frozen(True,self.pid)
        saved=self.confirm(self.preview(self.semantic()));cid=saved['graph']['concepts'][0]['id']
        before=self.app.store.get_setting('profile_freeze_'+self.pid)
        self.app.record_feedback('p0','understood',project_id=self.pid)
        self.assertEqual(self.app.route_get(self.pid)['progress'][cid]['understood'],1)
        self.assertEqual(self.app.store.get_setting('profile_freeze_'+self.pid),before)

    def test_reset_cutoff_cannot_predate_frozen_global_feedback_id(self):
        self.add('other-paper','Poetry study','poetry',pid=self.other)
        self.app.record_feedback('other-paper','useful',project_id=self.other)
        self.app.set_profile_frozen(True,self.pid)
        frozen=self.app.store.get_setting('profile_freeze_'+self.pid)['through_feedback_id']
        saved=self.confirm(self.preview(self.semantic()));node=saved['graph']['concepts'][0]
        self.assertGreaterEqual(node['progress_since_feedback_id'],frozen)
        new=self.app.record_feedback('p0','understood',project_id=self.pid)
        self.assertGreater(new['feedback_id'],frozen)
        self.assertEqual(self.app.route_get(self.pid)['progress'][node['id']]['understood'],1)

    def test_manual_save_preserves_authoritative_cutoff_and_semantic_reset(self):
        saved=self.confirm(self.preview(self.semantic()));cid=saved['graph']['concepts'][0]['id']
        graph=copy.deepcopy(saved['graph']);graph['concepts'][0]['progress_since_feedback_id']=0
        current=self.app.route_save(self.pid,graph=graph)
        self.assertEqual(current['graph']['concepts'][0]['progress_since_feedback_id'],saved['graph']['concepts'][0]['progress_since_feedback_id'])
        self.assertEqual(current['brief'],BRIEF)
        self.app.route_manual(self.pid,cid,'mastered')
        graph=copy.deepcopy(current['graph']);graph['concepts'][0]['terms']=['crystal growth','epitaxy']
        current=self.app.route_save(self.pid,graph=graph)
        self.assertNotIn(cid,current['manual'])

    def test_legacy_plan_resave_cannot_erase_cutoffs_or_human_intro(self):
        saved=self.confirm(self.preview(self.semantic()))
        source=copy.deepcopy(saved['graph'])
        source['concepts'][0]['intro']='Human note';source['concepts'][0]['intro_by']='user'
        self.app.route_save(self.pid,graph=source)
        plan=copy.deepcopy(PLAN);plan['concepts'][0]['name']='Revised crystal basics'
        before=self.app.route_get(self.pid)
        saved=self.app.route_save(self.pid,plan=plan)
        self.assertEqual(saved['graph']['concepts'][0]['id'],before['graph']['concepts'][0]['id'])
        self.assertEqual(saved['graph']['concepts'][0]['intro'],'Human note')
        self.assertEqual(saved['graph']['concepts'][0]['progress_since_feedback_id'],before['graph']['concepts'][0]['progress_since_feedback_id'])
        self.assertEqual(saved['progress'][saved['graph']['concepts'][0]['id']]['understood'],0)

    def test_legacy_plan_cannot_crop_saved_40_node_graph(self):
        graph={'concepts':[{'id':f'node{i}','name':f'Concept {i}','terms':[f'topic{i}'],'hint':2} for i in range(40)],'prereqs':[],'targets':['node39']}
        self.app.route_save(self.pid,graph=graph)
        before=self.app.route_get(self.pid)
        with self.assertRaises(ValueError):self.app.route_save(self.pid,plan=PLAN)
        self.assertEqual(self.app.route_get(self.pid),before)

    def test_confirm_from_two_connections_creates_one_event(self):
        draft=self.preview(self.semantic()); count=self.events();barrier=threading.Barrier(2);results=[];errors=[]
        def run():
            app=App(root=str(self.root),data_dir=str(self.root/'data'))
            try:
                barrier.wait();results.append(app.route_revision_confirm(self.pid,draft['draft_id']))
            except BaseException as exc:errors.append(exc)
            finally:app.store.close()
        workers=[threading.Thread(target=run) for _ in range(2)]
        for w in workers:w.start()
        for w in workers:w.join(10);self.assertFalse(w.is_alive())
        self.assertEqual(errors,[]);self.assertEqual(len(results),2);self.assertEqual(self.events(),count+1)

    def test_reconfirm_two_connections_inserts_one_new_feedback(self):
        self.confirm(self.preview(self.semantic())); count=self.app.store.conn.execute('SELECT COUNT(*) FROM feedback').fetchone()[0]
        barrier=threading.Barrier(2);results=[];errors=[]
        def run():
            app=App(root=str(self.root),data_dir=str(self.root/'data'))
            try:
                barrier.wait();results.append(app.record_feedback('p0','understood',project_id=self.pid))
            except BaseException as exc:errors.append(exc)
            finally:app.store.close()
        workers=[threading.Thread(target=run) for _ in range(2)]
        for w in workers:w.start()
        for w in workers:w.join(10);self.assertFalse(w.is_alive())
        self.assertEqual(errors,[]);self.assertEqual(results[0]['feedback_id'],results[1]['feedback_id'])
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM feedback').fetchone()[0],count+1)


if __name__=='__main__':unittest.main()
