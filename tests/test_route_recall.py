"""Bounded local recall plans; public metadata fixtures, no network/model."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
import urllib.error
from unittest import mock

from app import cli, route_recall, sources
from app.service import App
from app.organization import Organization
from test_route_runtime import Fixture
from test_openalex_discovery import Router


def route():
    return {"revision": 1, "goal_status": "learning", "goal_targets": ["target"],
            "goal_scope": ["a", "b", "target"], "frontier": ["a", "b"],
            "watched_satisfied": ["known"], "graph": {"concepts": [
                {"id": "a", "state": "active", "terms": ["alpha foundations"]},
                {"id": "b", "state": "active", "terms": ["beta foundations"]},
                {"id": "target", "state": "active", "terms": ["target technique", "adjacent technique"]},
                {"id": "known", "state": "active", "terms": ["known technique"]}], "targets": ["target"], "prereqs": []}}


class PlannerTests(unittest.TestCase):
    def plan(self, r=None, state=None, keywords=None, interest=None):
        return route_recall.plan(r or route(), keywords or ["broad field"], interest or [], state=state or {},
                                 language_revision=1, basic_since="2016-10-07", recent_since="2021-10-07", to_date="2026-10-07")

    def test_three_roles_share_three_themes_and_keep_distinct_order_and_windows(self):
        p = self.plan()
        self.assertEqual([q["kind"] for q in p["queries"]], ["path", "explore", "watch"])
        self.assertEqual([(q["order"], q["from_date"]) for q in p["queries"]],
                         [("relevance", "2016-10-07"), ("recent", "2021-10-07"), ("recent", "2021-10-07")])

    def test_rotation_survives_repeated_plans_without_starving_later_frontier(self):
        p = self.plan(); state = route_recall.record(p, {}, [], observed_at=100)
        next_ = self.plan(state=state)
        self.assertEqual(p["queries"][0]["query"], "alpha foundations")
        self.assertEqual(next_["queries"][0]["query"], "beta foundations")

    def test_completed_goal_has_only_discovery_roles_and_not_ordinary_fallback(self):
        r = route(); r.update(goal_status="completed", frontier=[])
        self.assertEqual(set(k for q in self.plan(r)["queries"] for k in q["kinds"]), {"explore", "watch"})

    def test_empty_frontier_and_bad_target_do_not_invent_world_model_query(self):
        r = route(); r.update(goal_status="needs_review", frontier=[], goal_targets=[], goal_scope=[], watched_satisfied=[])
        r["graph"]["concepts"] = []
        p = route_recall.plan(r, [], [], basic_since="2016-10-07", recent_since="2021-10-07", to_date="2026-10-07")
        self.assertEqual(p["queries"], [])

    def test_shared_phrase_keeps_distinct_relevance_paged_recent_paged_and_latest(self):
        r = route(); r["graph"]["concepts"][-1]["terms"] = ["alpha foundations"]
        p = self.plan(r, keywords=["alpha foundations"])
        queries = [(q["query"], q["order"], q["page_mode"]) for q in p["queries"]]
        self.assertEqual(len(queries), len(set(queries)))
        self.assertEqual(queries, [('alpha foundations', 'relevance', 'paged'),
                                  ('alpha foundations', 'recent', 'paged'),
                                  ('alpha foundations', 'recent', 'latest')])
        state = route_recall.record(p, {}, [(q, [{'key':str(i)} for i in range(50)]) for q in p['queries']], 100)
        state['cursors'] = dict.fromkeys(route_recall.KINDS, 0)
        again = self.plan(r, state=state, keywords=['alpha foundations'])
        self.assertEqual([q['page'] for q in again['queries']], [2,2,1])
        self.assertEqual(len(state['sources']['0']), 3)

    def test_graph_or_language_change_invalidates_source_and_rotation_state(self):
        p = self.plan(); state = route_recall.record(p, {}, [(p["queries"][0], [{"key": "x"}])], observed_at=100)
        changed = route(); changed['graph']['concepts'][0]['terms'] = ['new foundation']
        newer = self.plan(changed, state=state)
        self.assertNotEqual(newer["signature"], p["signature"])
        self.assertEqual(route_recall.live_sources(state, newer["signature"], 101), {})
        self.assertEqual(route_recall.live_sources(state, p["signature"], 100 + route_recall.SOURCE_TTL + 1), {})
        self.assertEqual(route_recall.live_sources(state, p["signature"], 99), {})

    def test_organization_revision_alone_does_not_expire_recall(self):
        p = self.plan(); state = route_recall.record(p, {}, [(p['queries'][0], [{'key':'x'}])], 100)
        changed = route(); changed['revision'] = 99
        newer = self.plan(changed, state=state)
        self.assertEqual(newer['signature'], p['signature'])
        self.assertIn('x', route_recall.live_sources(state, newer['signature'], 101))

    def test_actual_graph_dependency_change_expires_sources_even_if_queries_match(self):
        p = self.plan(); changed = route()
        changed['graph']['prereqs'] = [{'from':'a','to':'b','state':'active'}]
        self.assertNotEqual(self.plan(changed)['signature'], p['signature'])

    def test_sources_and_pages_are_bounded_across_many_refreshes(self):
        state = {}
        for n in range(8):
            p = self.plan(state=state)
            results = [(q, [{"key": f"{n}-{i}"} for i in range(50)]) for q in p["queries"]]
            state = route_recall.record(p, state, results, observed_at=100+n)
        self.assertLessEqual(len(state["sources"]), route_recall.MAX_SOURCE_PAPERS)
        self.assertTrue(all(len(v) <= route_recall.MAX_PAPER_SOURCES for v in state["sources"].values()))
        self.assertLessEqual(len(state["pages"]), route_recall.MAX_PAGE_KEYS)

    def test_many_frontiers_rotate_instead_of_repeating_first_three(self):
        r = route(); r.update(frontier=[f'p{i}' for i in range(6)], watched_satisfied=[])
        r['graph']['concepts'] += [{'id': i, 'terms':[f'{i} theory']} for i in r['frontier']]
        state, seen = {}, set()
        for _ in range(3):
            p = self.plan(r, state=state)
            seen.update(c for q in p['queries'] if q['kind']=='path' for c in q['concepts'])
            state = route_recall.record(p, state, [], observed_at=100)
        self.assertTrue(set(r['frontier']) <= seen)

    def test_page_size_and_explicit_window_changes_invalidate_provenance_and_pages(self):
        r = route(); options=dict(basic_since='2016-10-07',recent_since='2021-10-07',to_date='2026-10-07')
        p = route_recall.plan(r, ['broad field'], [], per_page=2, **options)
        state = route_recall.record(p, {}, [(p['queries'][0], [{'key':'a'},{'key':'b'}])], observed_at=100)
        for altered in ({**options,'recent_since':'2025-01-01'}, options):
            newer = route_recall.plan(r, ['broad field'], [], state=state, per_page=3, **altered)
            self.assertNotEqual(newer['signature'],p['signature'])
            self.assertEqual(newer['queries'][0]['page'],1)
            self.assertEqual(route_recall.live_sources(state,newer['signature'],101),{})

    def test_shared_phrase_keeps_path_page_two_and_watch_recent_page_one(self):
        r = route(); r['graph']['concepts'][-1]['terms']=['alpha foundations']
        p = self.plan(r)
        q = next(q for q in p['queries'] if q['kind']=='path')
        state = route_recall.record(p, {}, [(q,[{'key':str(i)} for i in range(50)])], observed_at=100)
        # Return to the first frontier while keeping the actual persisted page.
        state['cursors']['path']=0
        p = self.plan(r,state=state)
        self.assertEqual(next(q for q in p['queries'] if q['order']=='relevance')['page'],2)
        self.assertEqual(next(q for q in p['queries'] if 'watch' in q['kinds'])['page'],1)

    def test_paging_cap_wraps_to_first_page_instead_of_locking_forever(self):
        p=self.plan(); q=p['queries'][0];q['page']=route_recall.MAX_SOURCE_PAGE
        state=route_recall.record(p, {}, [(q,[{'key':str(i)} for i in range(50)])], observed_at=100)
        self.assertEqual(state['pages'][q['page_key']],1)

    def test_relative_window_rollover_keeps_pagination_but_actual_dates_are_recorded(self):
        r=route(); policy={'basic_years':10,'recent_years':5}
        p=route_recall.plan(r,[],[],basic_since='2016-10-07',recent_since='2021-10-07',to_date='2026-10-07',window_policy=policy)
        q=p['queries'][0]
        state=route_recall.record(p,{},[(q,[{'key':str(i)} for i in range(50)])],observed_at=100)
        state['cursors']['path']=0
        next_=route_recall.plan(r,[],[],state=state,basic_since='2016-10-08',recent_since='2021-10-08',to_date='2026-10-08',window_policy=policy)
        self.assertEqual(next_['signature'],p['signature'])
        self.assertEqual(next_['queries'][0]['page'],2)
        self.assertEqual(state['sources']['0'][0]['to_date'],'2026-10-07')

    def test_maximum_saved_graph_does_not_evict_exploration_pages_before_next_turn(self):
        ids=[f'n{i}' for i in range(40)]
        r=route();r.update(frontier=ids,goal_targets=ids,goal_scope=ids,watched_satisfied=[])
        r['graph']={'concepts':[{'id':i,'terms':[i+' basics',i+' methods']} for i in ids],
                    'targets':ids,'prereqs':[]}
        state={};previous={};revisited=set()
        for _ in range(220):
            planned=self.plan(r,state=state,keywords=['public field one','public field two','public field three'],
                              interest=[f'interest {i}' for i in range(6)])
            for q in planned['queries']:
                if q['kind']=='explore':
                    key=q['page_key']
                    if key in previous:
                        self.assertGreater(q['page'],previous[key])
                        revisited.add(key)
                    previous[key]=q['page']
            state=route_recall.record(planned,state,[(q,[{'key':str(i)} for i in range(50)]) for q in planned['queries']],100)
        self.assertEqual(len(revisited),89)

    def test_new_interest_expires_explanation_but_keeps_unchanged_path_page(self):
        p=self.plan();q=p['queries'][0]
        state=route_recall.record(p,{},[(q,[{'key':str(i)} for i in range(50)])],100)
        state['cursors']['path']=0
        changed=self.plan(state=state,interest=['new public interest'])
        self.assertNotEqual(changed['signature'],p['signature'])
        self.assertEqual(changed['queries'][0]['page'],2)
        self.assertEqual(route_recall.live_sources(state,changed['signature'],101),{})


class RefreshTests(Fixture):
    def get(self, **kwargs):
        calls = []
        def topic(query, **options):
            calls.append((query, options))
            return [{"key": "shared", "title": "Public paper", "abstract": "A useful abstract", "language": "en"}]
        with mock.patch.object(self.app.source, "discover_topic", side_effect=topic), mock.patch.object(self.app.source, "discover", side_effect=AssertionError("no ordinary fallback")):
            result = self.app.refresh_candidates(project_id=self.pid, **kwargs)
        return calls, result

    def test_refresh_has_bounded_multisource_provenance_and_keeps_seed_relation(self):
        self.enable(); self.paper("shared", "Public paper", "A useful abstract")
        self.app.store.add_project_paper(self.pid, "shared", "seed")
        calls, result = self.get()
        self.assertLessEqual(len(calls), 3)
        self.assertEqual((result["fetched"], result["field"]), (1, 1))
        origins = self.app.route_recall_sources(self.pid)["shared"]
        self.assertGreaterEqual(len(origins), 2)
        relation = self.app.store.conn.execute("SELECT relation_kind FROM project_papers WHERE project_id=? AND paper_key='shared'", (self.pid,)).fetchone()[0]
        self.assertEqual(relation, "seed")

    def test_query_rotation_survives_restart_and_has_no_private_ids_in_requests(self):
        self.enable(mastered=["Crystal basics"])
        self.app.route_watch(self.pid, self.cid["Crystal basics"], True)
        first, _ = self.get()
        again = App(root=str(self.root), data_dir=str(self.app.data)); self.addCleanup(again.store.close)
        with mock.patch.object(again.source, "discover_topic", return_value=[]) as topic:
            again.refresh_candidates(project_id=self.pid)
        self.assertNotEqual(topic.call_args_list[0].args[0], first[0][0])
        for call in topic.call_args_list:
            payload = json.dumps([call.args, call.kwargs])
            self.assertNotIn(self.pid, payload)
            self.assertNotIn("profile", payload)

    def test_hot_failure_stops_without_extra_application_retries(self):
        self.enable(mastered=["Crystal basics"])
        with mock.patch.object(self.app.source, "discover_topic", side_effect=sources.SourceError("busy", "unavailable")) as topic:
            out = self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual(topic.call_count, 1)
        self.assertEqual(out["fetched"], 0)
        self.assertEqual(out["errors"][0]["kind"], "unavailable")

    def test_graph_change_during_fetch_does_not_save_old_context_provenance(self):
        self.enable()
        def fetch(query, **options):
            self.app.route_mode(self.pid, "off")
            return [{"key": "stale", "title": "Public paper", "abstract": "Useful"}]
        with mock.patch.object(self.app.source, "discover_topic", side_effect=fetch):
            out = self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual(out["reason_code"], "route_recall_changed")
        self.assertFalse(self.app.store.paper("stale"))
        self.assertEqual(self.app.route_recall_sources(self.pid), {})

    def test_distractors_cannot_bypass_three_theme_route_limit(self):
        self.enable()
        with mock.patch.object(self.app.source, "discover_topic") as topic, mock.patch.object(self.app.source, "distractors") as extra:
            with self.assertRaises(ValueError): self.app.refresh_candidates(project_id=self.pid, include_distractors=True)
        self.assertEqual((topic.call_count, extra.call_count), (0, 0))

    def test_project_delete_removes_recall_state(self):
        self.enable(); self.get()
        self.app.projects.delete_project(self.pid)
        self.assertIsNone(self.app.store.get_setting("route_recall_"+self.pid))

    def test_only_useful_and_chosen_seeds_supply_interest_not_understood_or_imports(self):
        self.enable()
        self.paper("plain", "Public photonics calibration", "photonic calibration")
        self.app.store.save_to_library("plain", project_id=self.pid)
        self.app.record_feedback("plain", "understood", project_id=self.pid)
        self.assertEqual(self.app._route_recall_interest(self.pid), [])
        self.app.record_feedback("plain", "useful", project_id=self.pid)
        self.assertTrue(self.app._route_recall_interest(self.pid))
        feedback = self.app.latest_feedback(self.pid)["plain"]["id"]
        self.app.undo_feedback(feedback, project_id=self.pid)
        self.assertEqual(self.app._route_recall_interest(self.pid), [])

    def test_layout_edits_preserve_sources_and_paging_but_route_edits_expire_them(self):
        self.enable()
        def full(query, **options):
            return [{'key':str(i), 'title':'Public study '+str(i)} for i in range(options['per_page'])]
        with mock.patch.object(self.app.source, 'discover_topic', side_effect=full):
            self.app.refresh_candidates(project_id=self.pid, per_page=2)
        before = self.app.store.get_setting('route_recall_'+self.pid)
        revision = self.app.route_get(self.pid)['revision']
        self.app.store.save_to_library('0', project_id=self.pid)
        Organization(self.app.store, self.pid).action({'action':'positions', 'positions':{'paper:0':{'x':30,'y':40}}})
        self.assertGreater(self.app.route_get(self.pid)['revision'], revision)
        self.assertEqual(set(self.app.route_recall_sources(self.pid)), {'0','1'})
        current = self.app._route_recall_plan(self.pid, self.app.route_get(self.pid), before, per_page=2)
        self.assertEqual(current['signature'], before['signature'])
        self.assertEqual(next(q['page'] for q in current['queries'] if q['kind']=='path'), 2)
        self.app.route_manual(self.pid, self.cid['Crystal basics'], 'mastered')
        self.assertEqual(self.app.route_recall_sources(self.pid), {})

    def test_cross_process_refresh_cannot_overwrite_committed_sources_or_facts(self):
        self.enable()
        child_code = '''
import json,sys
from app.service import App
app=App(root=sys.argv[1],data_dir=sys.argv[2])
app.gateway.call=lambda *a,**k: (_ for _ in ()).throw(AssertionError('no model'))
app.source.discover_topic=lambda *a,**k:[{'key':'child','title':'Child public study'}]
result=app.refresh_candidates(project_id=sys.argv[3])
assert result['fetched']==1,result
app.store.close()
'''
        started = False
        def fetch(*args, **kwargs):
            nonlocal started
            if not started:
                started = True
                subprocess.run([sys.executable, '-c', child_code, str(self.root), str(self.app.data), self.pid],
                               check=True, capture_output=True, text=True, timeout=30)
            return [{'key':'parent','title':'Parent stale study'}]
        with mock.patch.object(self.app.source, 'discover_topic', side_effect=fetch):
            result = self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual(result['reason_code'], 'route_recall_changed')
        self.assertIsNone(self.app.store.paper('parent'))
        self.assertIsNotNone(self.app.store.paper('child'))
        self.assertEqual(set(self.app.route_recall_sources(self.pid)), {'child'})
        self.assertFalse(self.app.store.conn.in_transaction)

    def test_atomic_failure_rolls_back_facts_and_provenance_and_allows_next_refresh(self):
        self.enable()
        with mock.patch.object(route_recall, 'record', side_effect=OSError('fixture disk full')):
            with self.assertRaises(OSError): self.get()
        self.assertIsNone(self.app.store.paper('shared'))
        self.assertIsNone(self.app.store.get_setting('route_recall_'+self.pid))
        self.assertFalse(self.app.store.conn.in_transaction)
        self.assertEqual(self.get()[1]['fetched'], 1)

    def test_delete_during_fetch_does_not_resurrect_project_facts_or_state(self):
        self.enable()
        def fetch(*args, **kwargs):
            self.app.projects.delete_project(self.pid)
            return [{'key':'deleted','title':'Deleted project fixture'}]
        with mock.patch.object(self.app.source, 'discover_topic', side_effect=fetch):
            result = self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual(result['reason_code'], 'route_recall_changed')
        self.assertIsNone(self.app.store.paper('deleted'))
        self.assertIsNone(self.app.store.get_setting('route_recall_'+self.pid))

    def test_two_app_instances_in_same_process_do_not_stack_source_requests(self):
        self.enable()
        again=App(root=str(self.root),data_dir=str(self.app.data));self.addCleanup(again.store.close)
        results=[]
        def fetch(*args, **kwargs):
            results.append(again.refresh_candidates(project_id=self.pid))
            return []
        with mock.patch.object(self.app.source,'discover_topic',side_effect=fetch), mock.patch.object(again.source,'discover_topic') as duplicate:
            self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual(duplicate.call_count,0)
        self.assertTrue(all(r['reason_code']=='refresh_running' for r in results))

    def test_cli_default_refresh_works_in_route_without_distractors_or_fixed_date(self):
        self.enable()
        output=io.StringIO()
        with mock.patch.object(cli,'App',return_value=self.app), mock.patch.object(self.app,'get_default_project_id',return_value=self.pid), contextlib.redirect_stdout(output), mock.patch.object(self.app.source,'discover_topic',return_value=[]) as topic, mock.patch.object(self.app.source,'distractors') as distractors:
            self.assertEqual(cli.main(['refresh']),0)
        result=json.loads(output.getvalue())
        self.assertEqual(len(result['query_plan']),3)
        self.assertEqual(topic.call_count,3)
        self.assertEqual(distractors.call_count,0)
        self.assertIsNone(self.app.store.get_setting('route_recall_'+self.pid)['configuration']['from_date'])

    def test_actual_source_has_at_most_six_requests_and_no_added_retry_loop(self):
        self.enable()
        router=Router([])
        with mock.patch.object(sources.urllib.request,'urlopen',router), mock.patch.object(sources.time,'sleep'):
            result=self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual((len(result['query_plan']),len(router.urls)),(3,6))
        self.assertEqual(result['errors'],[])
        # A new query policy avoids the just-populated success cache.
        with mock.patch.object(sources.urllib.request,'urlopen',side_effect=urllib.error.URLError('fixture outage')) as fetch, mock.patch.object(sources.time,'sleep'):
            result=self.app.refresh_candidates(project_id=self.pid,from_date='2025-01-01')
        self.assertEqual(fetch.call_count,2)  # the source's existing two-attempt bound
        self.assertEqual(result['errors'][0]['kind'],'network_error')
        self.assertTrue(all(e['kind']=='skipped' for e in result['errors'][1:]))

    def test_policy_change_expires_live_sources(self):
        self.enable();self.get()
        self.app.projects.set_language_policy(self.pid,'humanities',['zh'])
        self.assertEqual(self.app.route_recall_sources(self.pid),{})


if __name__ == "__main__": unittest.main()
