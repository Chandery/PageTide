"""3+1+1 and completed daily caps: disposable data, no network/model."""
import subprocess
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest import mock
from collections import Counter

from app import maintenance, route_batch
from app.service import App
from test_route_runtime import Fixture
from recommendation_fixtures import english_papers, SYNTHETIC_OA


class BatchTests(Fixture):
    def prepare(self, path=6, explore=4, watch=4, watched=True, completed=False):
        self.enable(mastered=['Crystal basics'] + (['Epitaxy','Doping','Defects'] if completed else []))
        if watched: self.app.route_watch(self.pid,self.cid['Crystal basics'],True)
        for i in range(path): self.paper('p'+str(i),'Epitaxy methods '+str(i),'epitaxy epitaxial growth methods')
        for i in range(explore): self.paper('x'+str(i),'Photonic calibration '+str(i),'photonic calibration instruments')
        if explore:
            # Exploration is a sourced, visibly matching clue, not an unmatched filler.
            patcher=mock.patch.object(self.app,'route_recall_sources',return_value={
                'x'+str(i):[{'kinds':['explore'],'query':'photonic calibration','observed_at':1}] for i in range(explore)})
            patcher.start();self.addCleanup(patcher.stop)
        for i in range(watch): self.paper('w'+str(i),'Crystal lattice update '+str(i),'crystal lattice measurement')
        english_papers(self.app,self.pid)

    def result(self, **options):
        return self.app.build_batch(project_id=self.pid,**options)

    def counts(self, result):
        return Counter(c['route']['kind'] for c in result['cards'])

    def test_full_batch_is_three_path_one_explore_one_watch(self):
        self.prepare()
        self.assertEqual(self.counts(self.result()),{'route':3,'explore':1,'watch':1})

    def test_overlapping_discovery_roles_reserve_a_distinct_watch_when_pair_exists(self):
        self.prepare(path=3,explore=1,watch=1)
        papers=[dict(p) for p in self.app.store.papers()]
        picks=route_batch.choose(self.app._route_state(self.pid),papers,
             [('w0',1.0),('x0',0.1)]+[('p'+str(i),0) for i in range(3)],5,
             sources={'w0':[{'kinds':['explore'],'query':'crystal lattice update'}],
                      'x0':[{'kinds':['explore'],'query':'photonic calibration'}]},today='2026-10-07',recent_since='2021-01-01')
        self.assertEqual(Counter(p[2] for p in picks),{'route':3,'explore':1,'watch':1})
        self.assertEqual([p[0] for p in picks if p[2]=='watch'],['w0'])

    def test_path_does_not_consume_unique_exploration_when_three_alternatives_exist(self):
        self.prepare(path=4,explore=0,watch=1)
        # Construct the dual-role public-query fixture before selection.
        self.app.store.conn.execute('UPDATE papers SET title=?,abstract=? WHERE key=?',
            ('Epitaxy methods with photonic calibration','epitaxy methods and photonic calibration','p0'))
        self.app.store.conn.commit()
        papers=[dict(p) for p in self.app.store.papers()]
        picks=route_batch.choose(self.app._route_state(self.pid),papers,
             [('p0',1.0),('p1',.8),('p2',.6),('p3',.4),('w0',.2)],5,
             sources={'p0':[{'kinds':['explore'],'query':'photonic calibration'}]},today='2026-10-07',recent_since='2021-01-01')
        self.assertEqual(Counter(p[2] for p in picks),{'route':3,'explore':1,'watch':1})
        self.assertEqual([p[0] for p in picks if p[2]=='explore'],['p0'])

    def test_each_discovery_shortage_uses_other_discovery_then_path(self):
        for explore,watch,expected in [(0,4,{'route':3,'watch':2}), (4,0,{'route':3,'explore':2}),
                                       (0,0,{'route':5})]:
            with self.subTest(explore=explore,watch=watch):
                # Use separate temporary fixture per case; no old exposures.
                case=BatchTests();case.setUp()
                try:
                    case.prepare(explore=explore,watch=watch)
                    self.assertEqual(case.counts(case.result()),expected)
                finally: case.doCleanups()

    def test_path_shortage_does_not_create_more_than_two_discoveries(self):
        self.prepare(path=1)
        result=self.result()
        self.assertEqual(self.counts(result),{'route':1,'explore':1,'watch':1})
        self.assertIsNotNone(result['shortfall'])

    def test_path_fallback_allocates_only_remaining_slots_between_branches(self):
        self.prepare(explore=0,watch=0)
        for i in range(6):self.paper('d'+str(i),'Doping methods '+str(i),'dopant doping methods')
        english_papers(self.app,self.pid)
        cards=self.result()['cards']
        self.assertEqual(Counter(c['route']['node'] for c in cards),{self.cid['Epitaxy']:3,self.cid['Doping']:2})

    def test_no_path_candidate_keeps_route_labels_and_shortage(self):
        self.prepare(path=0)
        result=self.result()
        self.assertEqual(self.counts(result),{'explore':1,'watch':1})
        self.assertIn('没凑够',result['shortfall']['reason'])

    def test_satisfied_unwatched_and_locked_routine_papers_are_not_filler(self):
        self.prepare(path=0,explore=0,watched=False)
        self.paper('locked','Dislocation defects review','dislocation defects')
        english_papers(self.app,self.pid)
        result=self.result()
        self.assertFalse(result['cards'])
        self.assertEqual(result['reason_code'],'route_no_candidates')

    def test_primary_match_and_progress_match_do_not_redirect_satisfied_papers(self):
        self.prepare(path=0,explore=0,watch=0,watched=False)
        self.paper('mixed','Crystal lattice epitaxy study','crystal lattice lattice epitaxy')
        english_papers(self.app,self.pid)
        self.assertFalse(self.result()['cards'])

    def test_explicit_novel_exploration_topic_can_deepen_an_existing_concept(self):
        self.prepare(path=0,explore=0,watched=False)
        # Same lattice concept, but from a public exploration topic absent from
        # the Map. The badge is a discovery clue, not an assertion of new skill.
        self.app.projects.update_project(self.pid,name='Crystals',keywords=['photonic calibration'])
        with mock.patch.object(self.app.source,'discover_topic',return_value=[{
            'key':'deep','title':'Crystal lattice photonic calibration','abstract':'crystal lattice photonic calibration',
            'language':'en','published':'2026-01-01','oa':SYNTHETIC_OA}]):
            self.app.refresh_candidates(project_id=self.pid)
        result=self.result()
        card=next(c for c in result['cards'] if c['key']=='deep')
        self.assertEqual(card['route']['kind'],'explore')
        self.assertIn('photonic calibration',card['route']['name'])

    def test_discoveries_never_repeat_even_when_exclude_seen_false(self):
        self.prepare()
        keys=[]
        for _ in range(5):
            keys += [c['key'] for c in self.result(exclude_seen=False)['cards'] if c['route']['kind']!='route']
        self.assertEqual(len(keys),len(set(keys)))

    def test_path_silence_rotates_and_explicit_feedback_exits(self):
        self.prepare(explore=0,watch=0)
        first=self.result();second=self.result()
        self.assertEqual(len(first['cards']),5)
        self.assertTrue(set(c['key'] for c in second['cards'])-set(c['key'] for c in first['cards']))
        key=first['cards'][0]['key'];self.app.record_feedback(key,'useful',project_id=self.pid)
        self.assertNotIn(key,{c['key'] for c in self.result()['cards']})

    def test_completed_goal_returns_one_exploration_and_same_batch_on_repeat(self):
        self.prepare(completed=True)
        first=self.result();second=self.result(run_date='2099-01-01')
        self.assertEqual(self.counts(first),{'explore':1})
        self.assertEqual(second['batch_id'],first['batch_id'])
        self.assertEqual(second['reason_code'],'completed_daily_limit')
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM batches WHERE project_id=?',(self.pid,)).fetchone()[0],1)

    def test_completed_exploration_shortage_uses_watch_and_unwatched_excludes(self):
        self.prepare(path=0,explore=0,completed=True)
        self.assertEqual(self.counts(self.result()),{'watch':1})

    def test_completed_cross_day_and_restart_preserve_daily_limit(self):
        self.prepare(completed=True)
        with mock.patch.object(self.app,'batch_day',return_value='2026-10-07'):
            first=self.result()
        again=App(root=str(self.root),data_dir=str(self.app.data));self.addCleanup(again.store.close)
        with mock.patch.object(again,'batch_day',return_value='2026-10-07'):
            same=again.build_batch(project_id=self.pid)
        self.assertEqual(same['batch_id'],first['batch_id'])
        with mock.patch.object(again,'batch_day',return_value='2026-10-08'):
            new=again.build_batch(project_id=self.pid)
        self.assertNotEqual(new['batch_id'],first['batch_id'])
        self.assertNotEqual(new['cards'][0]['key'],first['cards'][0]['key'])

    def test_source_and_feedback_changes_during_selection_do_not_write_batch(self):
        self.prepare()
        original=self.app._route_pick
        def changed(*args,**kwargs):
            result=original(*args,**kwargs)
            self.app.record_feedback(result[0][0],'irrelevant',project_id=self.pid)
            return result
        with mock.patch.object(self.app,'_route_pick',side_effect=changed):result=self.result()
        self.assertEqual(result['reason_code'],'recommendation_changed')
        self.assertFalse(self.app.store.conn.execute('SELECT 1 FROM batches WHERE project_id=?',(self.pid,)).fetchone())

    def test_route_mode_change_during_selection_does_not_save_stale_route(self):
        self.prepare();original=self.app._route_pick
        def changed(*args,**kwargs):
            result=original(*args,**kwargs);self.app.route_mode(self.pid,'off');return result
        with mock.patch.object(self.app,'_route_pick',side_effect=changed):result=self.result()
        self.assertEqual(result['reason_code'],'recommendation_changed')

    def test_cross_process_completed_selection_creates_only_one_daily_exposure(self):
        self.prepare(completed=True);original=self.app._route_pick
        child_code='''
import sys
from app.service import App
app=App(root=sys.argv[1],data_dir=sys.argv[2])
app.gateway.call=lambda *a,**k: (_ for _ in ()).throw(AssertionError('no model'))
result=app.build_batch(project_id=sys.argv[3]);assert len(result['cards'])==1,result
app.store.close()
'''
        def overlap(*args,**kwargs):
            picks=original(*args,**kwargs)
            subprocess.run([sys.executable,'-c',child_code,str(self.root),str(self.app.data),self.pid],check=True,capture_output=True,timeout=30)
            return picks
        with mock.patch.object(self.app,'_route_pick',side_effect=overlap):result=self.result()
        self.assertEqual(result['reason_code'],'completed_daily_limit')
        self.assertEqual(self.app.store.conn.execute('SELECT COUNT(*) FROM exposures e JOIN batches b ON b.id=e.batch_id WHERE b.project_id=?',(self.pid,)).fetchone()[0],1)

    def test_learning_route_all_seen_unanswered_still_available_to_maintenance(self):
        self.prepare(explore=0,watch=0)
        self.result();self.result()
        self.assertTrue(maintenance._has_unseen(self.app,self.pid))

    def test_watch_requires_recent_date_and_unseen_unanswered_paper(self):
        self.prepare(path=0,explore=0,watch=0)
        for key,day in [('old','2001-01-01'),('unknown',''),('future','2099-01-01')]:
            self.paper(key,'Crystal lattice update','crystal lattice',published=day)
        english_papers(self.app,self.pid)
        self.assertFalse(self.result()['cards'])

    def test_route_batch_maximum_five_and_small_limit_path_priority(self):
        self.prepare()
        self.assertEqual(len(self.result(limit=20)['cards']),5)
        self.assertEqual(self.counts(self.result(limit=1)),{'route':1})

    def test_watch_date_change_during_selection_rejects_stale_card(self):
        self.prepare(path=0,explore=0);original=self.app._route_pick
        def changed(*args,**kwargs):
            picks=original(*args,**kwargs)
            self.app.store.conn.execute('UPDATE papers SET published=? WHERE key=?',('2001-01-01',picks[0][0]))
            self.app.store.conn.commit()
            return picks
        with mock.patch.object(self.app,'_route_pick',side_effect=changed):result=self.result()
        self.assertEqual(result['reason_code'],'recommendation_changed')
        self.assertFalse(self.app.store.conn.execute('SELECT 1 FROM batches').fetchone())

    def test_undo_frozen_feedback_hidden_by_new_live_label_invalidates_selection(self):
        self.prepare()
        self.app.record_feedback('x0','useful',project_id=self.pid)
        old=self.app.latest_feedback(self.pid)['x0']['id']
        self.app.set_profile_frozen(True,self.pid)
        self.app.record_feedback('x0','irrelevant',project_id=self.pid)
        original=self.app._route_pick
        def changed(*args,**kwargs):
            picks=original(*args,**kwargs);self.app.undo_feedback(old,project_id=self.pid);return picks
        with mock.patch.object(self.app,'_route_pick',side_effect=changed):result=self.result()
        self.assertEqual(result['reason_code'],'recommendation_changed')

    def test_manual_then_maintenance_and_maintenance_then_manual_share_daily_cap(self):
        for manual_first in (True,False):
            with self.subTest(manual_first=manual_first):
                case=BatchTests();case.setUp()
                try:
                    case.prepare(completed=True)
                    (case.app.data/'settings.json').write_text('{"updateFrequency":"daily","routeBeta":true,"timePreference":"all"}')
                    day='2026-10-07';instant=datetime(2026,10,7,5,tzinfo=timezone.utc)
                    with mock.patch.object(case.app,'batch_day',return_value=day),mock.patch.object(maintenance,'LOCAL_TZ',timezone.utc),mock.patch.object(case.app,'refresh_candidates',return_value={'fetched':0,'added':0,'errors':[]}):
                        if manual_first:case.result()
                        ran=maintenance.run(case.app,case.pid,instant)
                        result=case.result()
                    self.assertEqual(ran['batch'],not manual_first)
                    self.assertEqual(result['reason_code'],'completed_daily_limit')
                    self.assertEqual(case.app.store.conn.execute('SELECT COUNT(*) FROM exposures').fetchone()[0],1)
                finally:case.doCleanups()

    def test_completed_day_uses_local_timezone_and_rejects_midnight_rollover(self):
        self.prepare(completed=True)
        instant=datetime(2026,10,7,18,tzinfo=timezone.utc)
        with mock.patch.object(maintenance,'LOCAL_TZ',timezone(timedelta(hours=8))),mock.patch.object(maintenance,'_now',return_value=instant):
            first=self.result(run_date='2099-01-01')
        row=self.app.store.conn.execute('SELECT run_date FROM batches WHERE id=?',(first['batch_id'],)).fetchone()
        self.assertEqual(row[0],'2026-10-08')
        clock = ['2026-10-09']
        commit = self.app._create_eligible_batch
        def midnight_before_commit(*args, **kwargs):
            clock[0] = '2026-10-10'
            return commit(*args, **kwargs)
        with mock.patch.object(self.app, 'batch_day', side_effect=lambda: clock[0]), mock.patch.object(
                self.app, '_create_eligible_batch', side_effect=midnight_before_commit):
            result = self.result()
        self.assertEqual(result['reason_code'],'recommendation_changed')

    def test_failed_atomic_exposure_write_does_not_consume_completed_cap(self):
        self.prepare(completed=True)
        self.app.store.conn.execute("CREATE TRIGGER fail_exposure BEFORE INSERT ON exposures BEGIN SELECT RAISE(ABORT,'fixture rollback'); END")
        self.app.store.conn.commit()
        with self.assertRaisesRegex(Exception,'fixture rollback'):self.result()
        self.assertFalse(self.app.store.conn.execute('SELECT 1 FROM batches').fetchone())
        self.app.store.conn.execute('DROP TRIGGER fail_exposure');self.app.store.conn.commit()
        self.assertEqual(len(self.result()['cards']),1)


if __name__=='__main__':unittest.main()
