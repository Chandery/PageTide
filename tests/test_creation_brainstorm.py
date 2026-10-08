"""Creation must yield a reviewed usable map and a bounded follow-up conversation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import ai_guide, guidance_contract, pathgraph
from app.gateway import input_bound, request_envelope
from app.organization import Conflict
from app.service import App


def answer(**updates):
    draft = {'keywords': ['world model'], 'search_queries': ['world model planning'],
             'learning_path': [{'title': 'World model', 'purpose': '预测环境变化'}],
             'next_question': '先理解论文还是复现方法？', 'choices': ['理解论文', '复现方法'],
             'summary': '目标：世界模型；应用仍待确认', 'ready': False}
    draft.update(updates)
    return {'ok': True, 'content': json.dumps({'reply': '建议先理解论文，复现更需要编程基础。',
                                               'draft': draft}, ensure_ascii=False)}


def without_feedback_cutoffs(graph):
    return {**graph, 'concepts': [{key: value for key, value in node.items()
                if key != 'progress_since_feedback_id'} for node in graph['concepts']]}


class CreationBrainstormTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(root='.', data_dir=Path(self.temp.name))
        self.addCleanup(self.app.store.close)
        self.initial_projects = self.app.projects.list_projects()
        self.transport = mock.patch('app.gateway.urllib.request.urlopen', side_effect=AssertionError('offline test'))
        self.transport.start()
        self.addCleanup(self.transport.stop)

    def test_quick_and_guided_initial_drafts_show_a_local_map_and_finalize_stores_it(self):
        for mode in ('quick', 'ai_guided'):
            with self.subTest(mode=mode):
                session = self.app.create_guidance_session('Project', 'world model planning', mode)
                shown = session['draft']['route_draft']
                self.assertEqual(shown['source'], 'local_goal')
                self.assertEqual(shown['graph']['prereqs'], [])
                result = self.app.finalize_guidance(session['id'])
                stored = self.app.route_get(result['project_id'])
                self.assertEqual(without_feedback_cutoffs(stored['graph']), pathgraph.validate(shown['graph'], explicit=True))
                self.assertEqual(stored['manual'], {})
                self.assertEqual(self.app.projects.get_project(result['project_id'])['creation_mode'], mode)

    def test_learning_steps_become_independent_targets_with_terms_and_provenance(self):
        session = self.app.create_guidance_session('Project', 'world model planning')
        with mock.patch.object(self.app.gateway, 'call', return_value=answer(
                learning_path=[{'title': 'World model', 'purpose': '理解预测环境'},
                               {'title': 'Planning', 'purpose': '比较规划方法'}])) as call:
            turn = self.app.guidance_turn(session['id'], 'world model planning')
        self.assertEqual(call.call_count, 1)
        route = turn['session']['draft']['route_draft']
        self.assertEqual(route['source'], 'local_stages')
        self.assertEqual(route['stage_ids'], ['stage1', 'stage2'])
        graph = route['graph']
        self.assertEqual(graph['targets'], ['stage1', 'stage2'])
        self.assertEqual(graph['prereqs'], [])
        self.assertTrue(all(node['terms'] for node in graph['concepts']))
        self.assertTrue(all(node['intro_by'] == 'ai' for node in graph['concepts']))
        result = self.app.finalize_guidance(session['id'])
        self.assertEqual(self.app.route_get(result['project_id'])['graph']['concepts'][1]['name'], 'Planning')

    def test_next_turn_sees_its_question_summary_and_answer_without_entire_transcript(self):
        session = self.app.create_guidance_session('private-project-name', 'world model')
        with mock.patch.object(self.app.gateway, 'call', return_value=answer()) as call:
            first = self.app.guidance_turn(session['id'], 'world model')
            self.app.guidance_turn(session['id'], '理解论文')
        body = json.loads(call.call_args.args[1][-1]['content'])
        self.assertEqual(body['last_question'], first['session']['draft']['next_question'])
        self.assertEqual(body['summary'], first['session']['draft']['summary'])
        self.assertEqual(body['message'], '理解论文')
        self.assertEqual(body['turn'], 2)
        self.assertNotIn('private-project-name', json.dumps(call.call_args.args[1]))
        self.assertNotIn('transcript', body)
        self.assertNotIn('candidates', body)

    def test_optional_guidance_state_types_are_validated_and_old_reply_is_compatible(self):
        good = json.loads(answer()['content'])
        self.assertEqual(guidance_contract.parse(json.dumps(good))['draft']['choices'], ['理解论文', '复现方法'])
        for key in ('choices', 'summary', 'ready'):
            value = json.loads(answer()['content'])
            value['draft'].pop(key)
            guidance_contract.parse(json.dumps(value))
        for key, value in [('choices', 'not a list'), ('choices', [1]), ('choices', ['a'] * 4),
                           ('summary', []), ('ready', 1)]:
            bad = json.loads(answer()['content']); bad['draft'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                guidance_contract.parse(json.dumps(bad))

    def test_runtime_brainstorm_skill_covers_phases_and_skips_explicitly_known_parts(self):
        from app import project_brainstorm as skill
        self.assertEqual([skill.plan_turn(turn)['phase'] for turn in range(1, 7)],
                         ['goal', 'scope', 'start', 'output', 'review', 'confirm'])
        self.assertEqual(skill.plan_turn(1, known=['goal', 'scope'])['phase'], 'start')
        self.assertEqual(skill.plan_turn(2, ready=True)['phase'], 'confirm')
        self.assertEqual(skill.plan_turn(1, quick=True)['phase'], 'draft')
        for phrase in ['skip known', 'ready now', 'unsure:suggest', 'broad/conflict', 'keep choice', 'no inferred excludes']:
            self.assertIn(phrase, skill.RULES)
        self.assertIn(skill.RULES, guidance_contract.SYSTEM)
        system = guidance_contract.messages('world model', ['world model'], '不知道')[0]['content']
        self.assertIn(skill.RULES, system)
        self.assertNotIn('transcript', system)

    def test_local_fallback_brainstorm_skips_the_already_stated_goal(self):
        session = self.app.create_guidance_session('Project', 'world model planning')
        with mock.patch.object(self.app.gateway, 'call', return_value={'ok': False, 'reason': 'no API key'}):
            out = self.app.guidance_turn(session['id'], 'world model planning')
        self.assertEqual(out['session']['draft']['brainstorm_phase'], 'scope')
        self.assertGreaterEqual(len(out['session']['draft']['choices']), 2)
        self.assertNotIn('哪个领域', out['session']['draft']['next_question'])

    def test_wire_budget_fits_worst_unicode_and_memory_yields_before_current_answer(self):
        for english in (False, True):
            plain = guidance_contract.messages('中' * 4000, ['中' * 120] * 20, '答' * 2000, english)
            contextual = guidance_contract.messages('中' * 4000, ['中' * 120] * 20, '答' * 2000, english,
                last_question='问' * 500, summary='记' * 500, turn=6)
            plain_body, contextual_body = [json.loads(messages[-1]['content']) for messages in (plain, contextual)]
            self.assertEqual(contextual_body['message'], plain_body['message'])
            for messages in (plain, contextual):
                self.assertLessEqual(input_bound(request_envelope('project_guidance', 'deepseek-flash', 500, messages)), 1200)

    def test_explicit_abandon_keeps_project_without_a_map_and_invalid_flags_do_not_create(self):
        session = self.app.create_guidance_session('Project', 'world model')
        with self.assertRaises(ValueError): self.app.finalize_guidance(session['id'], skip_route='yes')
        self.assertEqual(self.app.projects.list_projects(), self.initial_projects)
        result = self.app.finalize_guidance(session['id'], skip_route=True)
        self.assertIsNone(self.app.route_get(result['project_id'])['graph'])

    def test_unshown_edits_cannot_implicitly_create_a_new_map(self):
        session = self.app.create_guidance_session('Project', 'world model')
        with self.assertRaises(Conflict):
            self.app.finalize_guidance(session['id'], {'learning_path': [{'title': 'Unreviewed', 'purpose': ''}]})
        self.assertEqual(self.app.projects.list_projects(), self.initial_projects)
        self.assertEqual(self.app.store.guidance_session(session['id'])['status'], 'draft')

    def test_invalid_client_draft_types_refuse_before_spend_or_creating_a_project(self):
        session = self.app.create_guidance_session('Project', 'world model')
        for field, value in [('choices', 1), ('choices', {}), ('ready', 1),
                             ('summary', []), ('keywords', 'not a list')]:
            with self.subTest(field=field, value=value):
                with mock.patch.object(self.app.gateway, 'call') as call:
                    with self.assertRaises(ValueError):
                        self.app.guidance_turn(session['id'], 'answer', draft_edits={field: value})
                call.assert_not_called()
                with self.assertRaises(ValueError):
                    self.app.finalize_guidance(session['id'], {field: value}, skip_route=True)
                self.assertEqual(self.app.projects.list_projects(), self.initial_projects)

    def test_local_builder_is_bounded_skips_paper_shapes_and_does_not_infer_dependencies(self):
        draft = {'goal': '研究 world model', 'keywords': ['world model'],
                 'learning_path': [{'title': 'https://example.org/paper', 'purpose': ''},
                                   {'title': 'Planning', 'purpose': 'Goal'}] * 20}
        route = ai_guide.local_route_draft(draft)
        self.assertLessEqual(len(route['graph']['concepts']), 8)
        self.assertEqual(route['graph']['prereqs'], [])
        self.assertFalse(any(pathgraph.paper_shaped(node) for node in route['graph']['concepts']))
        pathgraph.validate(route['graph'], explicit=True)
        self.assertEqual(ai_guide.local_route_draft(draft), route)

    def test_compact_model_graph_is_used_with_explicit_edges_terms_and_ai_provenance(self):
        payload = {'reply': '先理解状态预测，再看如何规划。', 'draft': {
            'kw': ['world model'], 'queries': ['world model planning'], 'ask': '读论文还是复现？',
            'choices': ['读论文', '复现'], 'summary': '初学者，先理解机器人世界模型', 'ready': False,
            'graph': {'nodes': [['wm', 'World model', 'world model', '预测环境状态'],
                                ['plan', 'Planning', 'model predictive control', '用预测规划动作']],
                      'prereqs': [['wm', 'plan']], 'targets': ['plan']}}}
        session = self.app.create_guidance_session('Project', 'world model planning')
        with mock.patch.object(self.app.gateway, 'call', return_value={'ok': True, 'content': json.dumps(payload)}) as call:
            out = self.app.guidance_turn(session['id'], 'world model planning')
        self.assertEqual(call.call_count, 1)
        self.assertEqual(out['mode'], 'ai')
        route = out['session']['draft']['route_draft']
        self.assertEqual(route['source'], 'ai_guidance')
        self.assertEqual(route['stage_ids'], ['wm', 'plan'])
        self.assertEqual(route['graph']['targets'], ['plan'])
        self.assertEqual([(edge['from'], edge['to']) for edge in route['graph']['prereqs']], [('wm', 'plan')])
        self.assertTrue(all(node['intro_by'] == 'ai' for node in route['graph']['concepts']))
        self.assertEqual(out['session']['draft']['learning_path'][1], {'title': 'Planning', 'purpose': '用预测规划动作'})
        result = self.app.finalize_guidance(session['id'])
        self.assertEqual(without_feedback_cutoffs(self.app.route_get(result['project_id'])['graph']), route['graph'])

    def test_invalid_ai_graph_is_refused_as_a_whole_and_keeps_the_reviewed_graph(self):
        valid = {'nodes': [['a', 'World model', 'world model', 'Predict']], 'prereqs': [], 'targets': ['a']}
        invalid = [dict(valid, targets=[]), dict(valid, targets=['unknown']),
                   dict(valid, prereqs=[['a', 'a']]), dict(valid, nodes=valid['nodes'] * 4),
                   dict(valid, nodes=[['a', 'https://example.org/paper', 'world model', '']]),
                   dict(valid, nodes=[['a', 'Topic', '', '']]),
                   dict(valid, nodes=[['a', '话题', [':'], 'Intro']]),
                   dict(valid, nodes=[['a', '话题', ['---'], 'Intro']]),
                   dict(valid, nodes=[['a', 'Topic', ['topic'], '\u0000']]),
                   dict(valid, nodes=[['a', 'Topic', 'term', '', 'unexpected']]),
                   dict(valid, extra='not allowed')]
        for graph in invalid:
            with self.subTest(graph=graph):
                payload = json.loads(answer()['content'])
                payload['draft']['learning_graph'] = graph
                with self.assertRaises(ValueError): guidance_contract.parse(json.dumps(payload))
        session = self.app.create_guidance_session('Project', 'world model')
        before = session['draft']['route_draft']
        payload = json.loads(answer()['content']); payload['draft']['learning_graph'] = invalid[0]
        with mock.patch.object(self.app.gateway, 'call', return_value={'ok': True, 'content': json.dumps(payload)}):
            out = self.app.guidance_turn(session['id'], 'world model')
        self.assertEqual(out['reason_code'], 'bad_reply')
        self.assertEqual(out['session']['draft']['route_draft'], before)

    def test_actual_minified_contract_and_empty_graph_preserve_confirmed_map(self):
        complete = {'r': '按机器人规划收敛，先读论文。', 'd': {
            'k': ['world model'], 'q': ['world model planning'], 'a': '每周大约能投入多少时间？',
            'c': ['2小时', '5小时'], 's': '机器人规划，零基础，目标读懂论文，不涉及自动驾驶。', 'ready': False,
            'graph': {'nodes': [['wm', 'World model', ['world model'], '预测环境状态']],
                      'prereqs': [], 'targets': ['wm']}}}
        parsed = guidance_contract.parse(json.dumps(complete, ensure_ascii=False))
        self.assertEqual(parsed['draft']['keywords'], ['world model'])
        session = self.app.create_guidance_session('Project', '机器人规划世界模型，不涉及自动驾驶')
        with mock.patch.object(self.app.gateway, 'call', return_value={'ok': True, 'content': json.dumps(complete)}):
            first = self.app.guidance_turn(session['id'], session['draft']['goal'])
        before = first['session']['draft']['route_draft']
        clarify = {'r': '先按每周2小时安排，随时可调整。', 'd': {
            'k': ['world model'], 'q': ['world model planning'], 'a': '确认这个方向吗？',
            'c': ['确认', '再调整'], 's': complete['d']['s'] + ' 每周2小时。', 'ready': True,
            'graph': {'nodes': [], 'prereqs': [], 'targets': []}}}
        with mock.patch.object(self.app.gateway, 'call', return_value={'ok': True, 'content': json.dumps(clarify)}):
            second = self.app.guidance_turn(session['id'], '2小时')
        self.assertEqual(second['session']['draft']['route_draft'], before)
        self.assertTrue(second['session']['draft']['ready'])
        self.assertEqual(second['session']['turn_count'], 2)

    def test_clarifying_reply_without_a_path_preserves_user_stage_authorship(self):
        session = self.app.create_guidance_session('Project', 'world model')
        user_path = [{'title': 'My stage', 'purpose': 'I wrote this'}]
        compact = {'r': '先保留你的阶段，确认投入。', 'd': {
            'k': ['world model'], 'q': ['world model'], 'a': '每周投入？', 'ready': False}}
        with mock.patch.object(self.app.gateway, 'call', return_value={'ok': True, 'content': json.dumps(compact)}):
            out = self.app.guidance_turn(session['id'], 'world model', draft_edits={'learning_path': user_path})
        self.assertEqual(out['session']['draft']['learning_path_origin'], 'user')
        self.assertEqual(out['session']['draft']['route_draft']['graph']['concepts'][0]['intro_by'], 'user')
        result = self.app.finalize_guidance(session['id'])
        self.assertEqual(self.app.route_get(result['project_id'])['graph']['concepts'][0]['intro_by'], 'user')

    def test_read_session_preserves_explicit_ai_plan_preference_and_local_map(self):
        session = self.app.create_guidance_session('Project', 'world model')
        plan = {'graph': session['draft']['route_draft']['graph'], 'brief': session['draft']['route_draft']['brief'],
                'operation': 'route_map_create'}
        self.app.store.set_setting('route_plan_' + session['id'], {'attempts': 1, 'plan': plan})
        view = self.app.guidance_session_view(session['id'])
        self.assertEqual(view['draft']['route_plan'], plan)
        self.assertEqual(view['draft']['route_draft'], session['draft']['route_draft'])
        result = self.app.finalize_guidance(session['id'])
        self.assertEqual(without_feedback_cutoffs(self.app.route_get(result['project_id'])['graph']), pathgraph.validate(plan['graph'], explicit=True))
