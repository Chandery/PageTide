"""Full-Map growth proposal contracts; every provider result is a local fixture."""
import json
import subprocess
import sys
import unittest
from unittest import mock
from pipe_helpers import read_line
from test_route_growth import Fixture, reply, new
from app.organization import Conflict


class GrowthProposalTests(Fixture):
    def large_map(self, intro=''):
        graph = self.app.route_get(self.pid)['graph']
        graph['concepts'] = [{'id': f'private-node-{i}', 'name': f'N{i}', 'terms': [f't{i}'],
                              'hint': 2, 'state': 'active', 'origin': 'user', 'side': False,
                              **({'intro': intro, 'intro_by': 'user'} if intro else {})} for i in range(40)]
        graph['prereqs'] = [{'from': f'private-node-{i-1}', 'to': f'private-node-{i}',
                             'state': 'active', 'origin': 'user', 'support': None} for i in range(1, 40)]
        graph['targets'] = ['private-node-39']
        self.app.route_save(self.pid, graph=graph)

    def propose(self, kind='new_task', **fields):
        if kind == 'missing_prerequisite':
            graph = self.app.route_get(self.pid)['graph']
            for ref in fields.get('required_by', ['c2']):
                if isinstance(ref, str) and ref.startswith('c') and ref[1:].isdigit():
                    node = graph['concepts'][int(ref[1:]) - 1]
                    node['intro'] = f"Strain relaxation is required before {node['name']}."
            self.app.route_save(self.pid, graph=graph)
        self.say(('s1', 'useful'))
        self.gateway(reply([{**new(['p1']), 'verdict': kind,
                             'parent': 'c2' if kind == 'new_task' else '',
                             'required_by': ['c2'] if kind == 'missing_prerequisite' else [],
                             'needs': [], **fields}]))
        return self.app.route_direction_judge(self.pid)

    def test_path_useful_can_propose_a_nearby_new_task(self):
        self.shown('s1', kind='route')
        out = self.propose()
        self.assertTrue(out['ok'])
        candidate = self.app.route_candidates(self.pid)['candidates'][0]
        self.assertEqual(candidate['proposal_type'], 'new_task')
        self.assertTrue(candidate['can_accept'])

    def test_missing_prerequisite_is_previewed_before_the_existing_node(self):
        self.propose('missing_prerequisite')
        candidate = self.app.route_candidates(self.pid)['candidates'][0]
        self.assertEqual(len(candidate['topology']['required_by']), 1)
        out = self.app.route_candidate_accept(self.pid, candidate['id'])
        added = next(c['id'] for c in out['graph']['concepts'] if c.get('candidate') == candidate['id'])
        dependent = candidate['topology']['required_by'][0]['id']
        self.assertIn((added, dependent), [(e['from'], e['to']) for e in out['graph']['prereqs']])

    def test_all_map_nodes_and_edges_are_sent_under_ephemeral_aliases(self):
        plan = {'concepts': [{'id': f'private-{i}', 'name': f'Topic {i}', 'terms': [f'term{i}'],
                            'hint': 2, 'needs': [f'private-{i-1}'] if i else []} for i in range(12)],
                'targets': ['private-11']}
        self.app.route_save(self.pid, plan=plan)
        self.say(('s1', 'useful'))
        calls = self.gateway(reply([]))
        self.app.route_direction_judge(self.pid)
        self.assertEqual(calls[0][0], 'route_growth_judge')
        body = json.loads(calls[0][1][1]['content'])
        self.assertEqual(len(body['map']['concepts']), 12)
        self.assertEqual(len(body['map']['prereqs']), 11)
        self.assertNotIn('private-', calls[0][1][1]['content'])

    def test_changed_map_marks_proposal_stale_and_prevents_accept(self):
        self.propose()
        candidate = self.app.route_candidates(self.pid)['candidates'][0]
        graph = self.app.route_get(self.pid)['graph']
        graph['concepts'][0]['name'] = 'Different foundation'
        self.app.route_save(self.pid, graph=graph)
        stale = self.app.route_candidates(self.pid)['candidates'][0]
        self.assertTrue(stale['stale'])
        self.assertFalse(stale['can_accept'])
        with self.assertRaises((ValueError, Conflict)):
            self.app.route_candidate_accept(self.pid, candidate['id'])

    def test_undo_useful_makes_proposal_stale_without_another_model_call(self):
        self.propose()
        self.app.undo_feedback(self.app.latest_feedback(self.pid)['s1']['id'])
        c = self.app.route_candidates(self.pid)['candidates'][0]
        self.assertTrue(c['stale'])
        self.assertEqual(c['positive'], 0)

    def test_graph_changes_during_model_call_do_not_store_stale_results(self):
        self.say(('s1', 'useful'))
        def changed():
            graph = self.app.route_get(self.pid)['graph']
            graph['targets'] = [graph['concepts'][0]['id']]
            self.app.route_save(self.pid, graph=graph)
            return reply([{**new(['p1']), 'verdict': 'new_branch'}])
        self.gateway(changed)
        with self.assertRaises(Conflict):
            self.app.route_direction_judge(self.pid)
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'], [])

    def test_valid_json_from_a_truncated_reply_is_not_applied(self):
        self.say(('s1', 'useful'))
        self.gateway({**reply([{**new(['p1']), 'verdict': 'new_branch'}]), 'finish_reason': 'length'})
        out = self.app.route_direction_judge(self.pid)
        self.assertFalse(out['ok'])
        self.assertEqual(out['mode'], 'ai')
        self.assertIn('未保存', out['reason'])
        self.assertNotIn('本地整理', out['reason'])
        self.assertEqual(out['judges_left'], 9)
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'], [])

    def test_new_scope_is_unapproved_and_cannot_borrow_the_old_grant(self):
        self.app.gateway.config['operations']['route_growth_judge']['owner_approved'] = False
        self.say(('s1', 'useful'))
        with mock.patch('urllib.request.urlopen') as network:
            out = self.app.route_direction_judge(self.pid)
        self.assertFalse(out['ok'])
        self.assertEqual(out['reason_code'], 'not_approved')
        network.assert_not_called()

    def test_invalid_parent_reference_cannot_be_silently_dropped(self):
        out = self.propose(parent='nonexistent')
        self.assertFalse(out['ok'])
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'], [])

    def test_short_complete_forty_node_map_is_not_cut_to_ten(self):
        self.large_map()
        self.say(('s1', 'useful'))
        calls = self.gateway(reply([]))
        self.app.route_direction_judge(self.pid)
        body = json.loads(calls[0][1][1]['content'])
        self.assertEqual(len(body['map']['concepts']), 40)
        self.assertEqual(len(body['map']['prereqs']), 39)
        self.assertEqual(body['map']['targets'], ['c40'])

    def test_oversized_complete_message_is_refused_without_sending_or_cutting(self):
        self.large_map('说明' * 70)
        self.say(('s1', 'useful'))
        calls = self.gateway(reply([]))
        with self.assertRaisesRegex(ValueError, '没有截断Map'):
            self.app.route_direction_judge(self.pid)
        self.assertEqual(calls, [])
        self.assertEqual(len(self.app.route_get(self.pid)['graph']['concepts']), 40)

    def test_layout_change_preserves_a_current_proposal(self):
        self.propose()
        c = self.app.route_candidates(self.pid)['candidates'][0]
        org = self.app._route_org(self.pid)
        org.action({'action': 'positions', 'positions': {'paper:s1': {'x': 10, 'y': 20}}})
        self.assertFalse(self.app.route_candidates(self.pid)['candidates'][0]['stale'])
        self.assertTrue(self.app.route_candidate_accept(self.pid, c['id'])['graph'])

    def test_new_useful_paper_does_not_expire_an_unrelated_proposal(self):
        self.propose()
        self.say(('s2', 'useful'))
        self.assertFalse(self.app.route_candidates(self.pid)['candidates'][0]['stale'])
        self.assertEqual({p['key'] for p in self.app._pending_growth(self.pid)}, {'s2'})

    def test_old_unversioned_direction_is_visible_stale_and_never_steers(self):
        self.say(('s1', 'useful'))
        self.app.store.set_setting(f'route_directions_{self.pid}', {
            'directions': [{'id': 'old', 'name': 'Old direction', 'terms': ['strain'],
                            'papers': ['s1'], 'needs': []}], 'judged': {'s1': {'verdict': 'new'}}})
        out = self.app.route_candidates(self.pid)
        self.assertTrue(out['candidates'][0]['stale'])
        self.assertTrue(out['judgements'][0]['stale'])
        self.assertEqual(self.app._visible_directions(self.pid, self.app.route_get(self.pid)), [])

    def test_undo_between_preview_and_transaction_rejects_the_whole_save(self):
        self.propose()
        c = self.app.route_candidates(self.pid)['candidates'][0]
        before = self.app.route_get(self.pid)['graph']
        original = self.app._route_apply
        def revoked(*args, **kwargs):
            self.app.undo_feedback(self.app.latest_feedback(self.pid)['s1']['id'])
            return original(*args, **kwargs)
        with mock.patch.object(self.app, '_route_apply', side_effect=revoked):
            with self.assertRaises(Conflict):
                self.app.route_candidate_accept(self.pid, c['id'])
        self.assertEqual(self.app.route_get(self.pid)['graph'], before)

    def test_a_prerequisite_that_would_cycle_is_not_an_actionable_proposal(self):
        out = self.propose('missing_prerequisite', needs=['c3'], required_by=['c1'])
        self.assertFalse(out['ok'])
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'], [])

    def test_fresh_proposal_is_not_hidden_by_five_stronger_stale_proposals(self):
        self.say(('s1', 'useful'), ('s2', 'useful'), ('s3', 'useful'))
        self.app.store.set_setting(f'route_directions_{self.pid}', {'directions': [
            {'id': f'old{i}', 'name': f'Old {i}', 'terms': ['strain relaxation'],
             'papers': ['s1', 's2', 's3'], 'needs': [], 'context': 'obsolete'} for i in range(5)]})
        self.say(('s4', 'useful'))
        self.gateway(reply([{**new(['p1'], name='Fresh task'), 'verdict': 'new_branch'}]))
        out = self.app.route_direction_judge(self.pid)
        fresh_id = out['results'][0]['direction']
        shown = self.app.route_candidates(self.pid)['candidates']
        self.assertEqual(shown[0]['id'], fresh_id)
        self.assertTrue(self.app.route_candidate_accept(self.pid, fresh_id)['graph'])

    def test_accept_does_not_use_the_five_row_display_limit_as_existence(self):
        self.say(('s1', 'useful'))
        context = self.app._growth_context(self.pid, ['s1'])
        self.app.store.set_setting(f'route_directions_{self.pid}', {'directions': [
            {'id': f'fresh{i}', 'name': f'Fresh {i}', 'terms': ['strain relaxation'],
             'papers': ['s1'], 'needs': [], 'context': context, 'proposal_type': 'new_branch'} for i in range(6)]})
        self.assertNotIn('fresh5', [c['id'] for c in self.app.route_candidates(self.pid)['candidates']])
        self.assertTrue(self.app.route_candidate_accept(self.pid, 'fresh5')['graph'])

    def test_undo_rejection_expires_the_judgement_that_depended_on_it(self):
        self.say(('s1', 'useful'), ('s2', 'useful'), ('s3', 'useful'))
        self.gateway(lambda: reply([new(['p1', 'p2', 'p3'])]) if len(self.app._pending_growth(self.pid)) > 1 else reply([new(['p1'])]))
        self.app.route_direction_judge(self.pid)
        c = self.app.route_candidates(self.pid)['candidates'][0]
        self.app.route_candidate_reject(self.pid, c['id'])
        self.say(('s4', 'useful'))
        self.assertEqual(self.app.route_direction_judge(self.pid)['results'][0]['verdict'], 'declined')
        self.assertEqual(self.app._pending_growth(self.pid), [])
        self.app.route_undo(self.pid)
        self.assertEqual([p['key'] for p in self.app._pending_growth(self.pid)], ['s4'])
        self.assertTrue(self.app.route_candidates(self.pid)['judgements'][0]['stale'])

    def test_goal_preview_ignores_a_proposed_link_into_the_goal(self):
        graph = self.app.route_get(self.pid)['graph']
        graph['prereqs'][0]['state'] = 'proposed'
        self.app.route_save(self.pid, graph=graph)
        self.propose('missing_prerequisite', required_by=['c1'])
        c = self.app.route_candidates(self.pid)['candidates'][0]
        before = self.app.route_get(self.pid)['goal_scope']
        self.assertEqual(c['goal_impact'], 'targets_unchanged')
        self.assertEqual(self.app.route_candidate_accept(self.pid, c['id'])['goal_scope'], before)

    def test_another_process_cannot_make_a_second_call_and_crash_releases_claim(self):
        self.say(('s1', 'useful'))
        code = """import sys
from app.service import App
app=App(root=sys.argv[1], data_dir=sys.argv[2])
def fake(*args, **kwargs):
    print('CALL_STARTED', flush=True)
    sys.stdin.readline()
    return {'ok':False,'reason':'timeout'}
app.gateway.call=fake
app.route_direction_judge(sys.argv[3])
"""
        child = subprocess.Popen([sys.executable, '-c', code, str(self.root), str(self.app.data), self.pid],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual((read_line(child.stdout, 20) or '').strip(), 'CALL_STARTED')
            calls = self.gateway(reply([new(['p1'])]))
            with self.assertRaisesRegex(ValueError, '正在判断'):
                self.app.route_direction_judge(self.pid)
            self.assertEqual(calls, [])
            self.assertEqual(self.app.store.get_setting(f'direction_judge_{self.pid}')['attempts'], 1)
            child.terminate(); child.wait(timeout=10)
            self.assertTrue(self.app.route_direction_judge(self.pid)['ok'])
            self.assertEqual(len(calls), 1)
        finally:
            if child.poll() is None:
                child.kill(); child.wait(timeout=10)
            child.stdin.close(); child.stdout.close(); child.stderr.close()

    def test_bad_verdict_and_join_types_degrade_without_crashing(self):
        self.say(('s1', 'useful'))
        calls = self.gateway(lambda: reply([{'papers': ['p1'], 'verdict': []}]))
        self.assertFalse(self.app.route_direction_judge(self.pid)['ok'])
        calls.clear()
        self.app.gateway.call.side_effect = lambda *args, **kw: reply([{'papers': ['p1'], 'verdict': 'join', 'direction': []}])
        self.assertFalse(self.app.route_direction_judge(self.pid)['ok'])
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'], [])

    def test_reference_that_does_not_apply_to_verdict_is_not_silently_ignored(self):
        self.assertFalse(self.propose('new_branch', nearest='nonexistent')['ok'])
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'], [])

    def test_new_judgment_keeps_original_proposal_for_undo_accept_and_reject(self):
        self.say(('s1', 'useful'), ('s2', 'useful'), ('s3', 'useful'))
        self.gateway(reply([new(['p1', 'p2', 'p3'])]))
        self.app.route_direction_judge(self.pid)
        original=self.app._directions_store(self.pid)['directions'][0]
        for action in ('accept', 'reject'):
            method = self.app.route_candidate_accept if action == 'accept' else self.app.route_candidate_reject
            method(self.pid, original['id'])
            self.say(('s4', 'useful'))
            self.app.gateway.call.side_effect = lambda *args, **kwargs: reply([new(['p1'], name='Different new task', terms=['another direction'])])
            self.app.route_direction_judge(self.pid)
            self.app.route_undo(self.pid)
            shown=self.app.route_candidates(self.pid)['candidates']
            self.assertIn(original['id'], [c['id'] for c in shown if not c['stale']])
            self.app.undo_feedback(self.app.latest_feedback(self.pid)['s4']['id'])

    def test_unknown_server_failure_keeps_the_growth_attempt(self):
        self.say(('s1', 'useful'))
        self.gateway({'ok':False,'reason':'HTTPError: 503','usage_unknown':True,'http_status':503})
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual(out['reason_code'], 'http')
        self.assertIn('503', out['reason'])
        self.assertEqual(out['judges_left'], 9)
        self.assertEqual(self.app.store.get_setting(f'direction_judge_{self.pid}')['attempts'],1)
        self.assertIn('未知',out['reason'])
        self.assertNotIn('本地整理',out['reason'])

    def test_released_client_rejection_refunds_the_growth_attempt(self):
        self.say(('s1', 'useful'))
        self.gateway({'ok':False,'reason':'HTTPError: 400','usage_unknown':False,'http_status':400})
        out=self.app.route_direction_judge(self.pid)
        self.assertEqual(out['reason_code'],'http')
        self.assertEqual(out['judges_left'],10)
        self.assertEqual(self.app.store.get_setting(f'direction_judge_{self.pid}')['attempts'],0)
