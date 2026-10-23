"""What is IN each field of a guidance reply, not only that a reply parsed.

A real conversation put the assistant's question into the search-query box and its advice into the question slot,
because the wire said only `q` and `a`. These tests check the contract names every field, the parser keeps a question
out of keywords and queries, and the service never fills a query from the user's own prose. No model is called.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import guidance_contract, project_brainstorm
from app.gateway import input_bound, request_envelope
from app.service import App

QUESTION_MARKS = ('?', '？')


def norm(text):
    return ' '.join(str(text).casefold().split())


def named(reply='先看这个方向。', **draft):
    base = {'keywords': ['world model', 'robot planning'], 'queries': ['world model robot planning'],
            'ask': '你想先读论文还是复现？', 'choices': ['读论文', '复现'], 'summary': '机器人规划里的世界模型',
            'ready': False}
    base.update(draft)
    return json.dumps({'reply': reply, 'draft': base}, ensure_ascii=False)


def compact(reply='先看这个方向。', **draft):
    base = {'k': ['world model'], 'q': ['world model planning'], 'a': '你想先读论文还是复现？',
            'c': ['读论文', '复现'], 's': '机器人规划', 'ready': False}
    base.update(draft)
    return json.dumps({'r': reply, 'd': base}, ensure_ascii=False)


def ok(content):
    return {'ok': True, 'content': content, 'finish_reason': 'stop', 'usage': {'total_tokens': 10}}


class WireContractTests(unittest.TestCase):
    def test_prompt_spells_out_every_field_and_says_what_it_holds(self):
        system = guidance_contract.SYSTEM
        self.assertIn('Return JSON', system)
        self.assertIn(project_brainstorm.RULES, system)
        self.assertIn('{"reply":"","draft":{"keywords":[],"queries":[],"ask":"","choices":[],"summary":"","ready":false}}',
                      system)
        for meaning in ('reply=your chat message to the user', 'ask=the one next question for the user',
                        'queries=', 'never questions or sentences addressed to the user', 'keywords=', 'summary=',
                        'choices=', 'ready='):
            self.assertIn(meaning, system)
        for cryptic in ('"r":', '"d":{', '"q":[', '"a":""', 'k/q/c', 'r/a/s'):
            self.assertNotIn(cryptic, system)

    def test_prompt_mentions_the_map_only_when_the_beta_map_is_on(self):
        off = guidance_contract.messages('goal', [], 'goal')[0]['content']
        on = guidance_contract.messages('goal', [], 'goal', graph=True)[0]['content']
        self.assertNotIn('graph', off.casefold())
        self.assertNotIn('node', off.casefold())
        self.assertIn('"nodes"', on)
        self.assertIn('graph', on)
        self.assertTrue(on.startswith(off.split(' Text in ')[0]))

    def test_turn_body_carries_the_current_queries_and_the_language_choice(self):
        body = json.loads(guidance_contract.messages('目标', ['a', 'b'], '目标', queries=['my own query'],
                                                     languages=['zh', 'en'])[-1]['content'])
        self.assertEqual(body['queries'], ['my own query'])
        self.assertEqual(body['languages'], ['zh', 'en'])
        plain = json.loads(guidance_contract.messages('目标', ['a'], '目标')[-1]['content'])
        self.assertNotIn('queries', plain)
        self.assertNotIn('languages', plain)

    def test_the_prompt_says_a_ticked_chinese_box_allows_one_chinese_query(self):
        system = guidance_contract.SYSTEM
        self.assertIn('languages', system)
        self.assertIn('zh', system)
        self.assertIn('Chinese', system)

    def test_prompt_is_still_small_and_nothing_is_cut_from_the_user_input(self):
        self.assertLessEqual(len(guidance_contract.SYSTEM.encode('utf-8')), 1250)
        built = guidance_contract.messages('中' * 4000, ['词'] * 20, '答' * 2000, queries=['q' * 100] * 3,
                                           languages=['zh', 'en'], last_question='问' * 500, summary='记' * 500)
        body = json.loads(built[-1]['content'])
        self.assertEqual((body['goal'], body['message']), ('中' * 4000, '答' * 2000))
        self.assertEqual(body['queries'], ['q' * 100] * 3)
        self.assertGreater(input_bound(request_envelope('project_guidance', 'deepseek-flash', 500, built)), 1200)


class ParseTests(unittest.TestCase):
    def test_named_reply_lands_in_the_right_fields(self):
        draft = guidance_contract.parse(named())['draft']
        self.assertEqual(draft['keywords'], ['world model', 'robot planning'])
        self.assertEqual(draft['search_queries'], ['world model robot planning'])
        self.assertEqual(draft['next_question'], '你想先读论文还是复现？')
        self.assertEqual(draft['choices'], ['读论文', '复现'])
        self.assertEqual(draft['summary'], '机器人规划里的世界模型')

    def test_every_older_spelling_still_parses_into_the_same_fields(self):
        expected = {'keywords': ['world model'], 'search_queries': ['world model planning'],
                    'next_question': '你想先读论文还是复现？', 'choices': ['读论文', '复现']}
        forms = {
            'one-letter': compact(),
            'kw': json.dumps({'reply': 'x', 'draft': {'kw': ['world model'], 'queries': ['world model planning'],
                              'ask': '你想先读论文还是复现？', 'choices': ['读论文', '复现'], 'summary': '', 'ready': False}},
                             ensure_ascii=False),
            'long': json.dumps({'reply': 'x', 'draft': {'keywords': ['world model'], 'search_queries': ['world model planning'],
                                'learning_path': [], 'next_question': '你想先读论文还是复现？',
                                'choices': ['读论文', '复现'], 'summary': '', 'ready': False}}, ensure_ascii=False),
            'named': named(keywords=['world model'], queries=['world model planning']),
        }
        for label, content in forms.items():
            with self.subTest(form=label):
                draft = guidance_contract.parse(content)['draft']
                for key, value in expected.items():
                    self.assertEqual(draft[key], value, key)

    def test_a_question_in_the_query_slot_is_dropped_and_a_query_comes_from_the_keywords(self):
        # Reproduces the owner's report: the model read q as "question" and put its question there.
        for content in (compact(q=['你想先理解哪个方向？'], k=['world model', 'robot planning']),
                        named(queries=['Which application first?']),
                        named(queries=['要先看哪个应用？', 'What is your goal?'])):
            with self.subTest(content=content):
                draft = guidance_contract.parse(content)['draft']
                self.assertFalse(any(q.endswith(QUESTION_MARKS) for q in draft['search_queries']), draft['search_queries'])
                self.assertEqual(draft['search_queries'], ['world model robot planning'])

    def test_a_query_that_repeats_the_question_or_the_reply_is_dropped(self):
        draft = guidance_contract.parse(named(reply='Pick one focus first', ask='Which focus first',
                                              queries=['which focus first', 'PICK ONE FOCUS FIRST']))['draft']
        self.assertEqual(draft['search_queries'], ['world model robot planning'])
        draft = guidance_contract.parse(named(keywords=['Which focus first', 'world model'], ask='Which focus first',
                                              queries=[]))['draft']
        self.assertEqual(draft['keywords'], ['world model'])

    def test_a_good_query_is_kept_and_a_chinese_query_is_not_treated_as_prose(self):
        draft = guidance_contract.parse(named(queries=['world model planning', '世界模型 规划']))['draft']
        self.assertEqual(draft['search_queries'], ['world model planning', '世界模型 规划'])

    def test_with_no_usable_query_one_is_built_from_at_most_four_keywords(self):
        draft = guidance_contract.parse(named(keywords=['a b', 'c', 'd', 'e', 'f'], queries=[]))['draft']
        self.assertEqual(draft['search_queries'], [' '.join(['a b', 'c', 'd', 'e'])])
        self.assertEqual(guidance_contract.parse(named(keywords=[], queries=[]))['draft']['search_queries'], [])

    def test_overproduction_is_trimmed_instead_of_refusing_the_reply(self):
        # The parser keeps what the model offers (up to a sanity bound); the per-turn limit of 5 keywords and 2
        # phrases is applied by the service after the person's own lists (see RoundTwo).
        draft = guidance_contract.parse(named(
            keywords=['k%d' % i for i in range(9)], queries=['q one', 'q two', 'q three'],
            choices=['A', 'B', 'C', 'D', 'E'], summary='长' * 400))['draft']
        self.assertEqual(len(draft['keywords']), 9)
        self.assertEqual(len(guidance_contract.parse(named(keywords=['k%d' % i for i in range(40)]))['draft']['keywords']),
                         guidance_contract.MAX_LISTED)
        self.assertEqual(draft['choices'], ['A', 'B', 'C'])
        self.assertEqual(draft['summary'], '长' * 160)
        self.assertEqual(guidance_contract.parse(named(choices=['x' * 90]))['draft']['choices'], ['x' * 60])

    def test_a_single_string_is_one_item_not_a_refused_reply(self):
        draft = guidance_contract.parse(named(queries='world model planning', keywords='world model'))['draft']
        self.assertEqual(draft['search_queries'], ['world model planning'])
        self.assertEqual(draft['keywords'], ['world model'])

    def test_wrong_types_and_unknown_keys_are_still_refused(self):
        for bad in (named(keywords=[{'name': 'x'}]), named(queries=[3]), named(choices=[{'label': 'x'}]),
                    named(summary=['x']), named(ready=1), named(ask=['x']),
                    json.dumps({'reply': 'x', 'draft': {'keywords': [], 'queries': [], 'ask': '', 'extra': 1}}),
                    json.dumps({'reply': 'x', 'draft': {'keywords': [], 'queries': [], 'search_queries': [], 'ask': ''}}),
                    json.dumps({'reply': 'x', 'draft': {'keywords': []}}), '{}', 'not json'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                guidance_contract.parse(bad)
        with self.assertRaises(ValueError):
            guidance_contract.parse(named(), 'length')

    def test_a_bad_map_is_dropped_but_the_rest_of_the_reply_is_kept(self):
        invalid = {'nodes': [['a', 'World model', ['world model'], 'x']], 'edges': [['a', 'a']], 'targets': ['a']}
        valid = {'nodes': [['a', 'World model', ['world model'], '预测环境状态']], 'edges': [], 'targets': ['a']}
        for graph in (invalid, {'nodes': 'x'}, 'not a graph', {'nodes': [['a', 'https://example.org/p', ['t'], 'x']],
                                                                  'edges': [], 'targets': ['a']}):
            with self.subTest(graph=graph):
                draft = guidance_contract.parse(named(graph=graph))['draft']
                self.assertNotIn('learning_graph', draft)
                self.assertNotIn('learning_path', draft)
                self.assertEqual(draft['next_question'], '你想先读论文还是复现？')
                self.assertEqual(draft['search_queries'], ['world model robot planning'])
        kept = guidance_contract.parse(named(graph=valid))['draft']
        self.assertEqual([c['id'] for c in kept['learning_graph']['concepts']], ['a'])
        self.assertEqual(kept['learning_path'][0]['title'], 'World model')

    def test_the_map_is_ignored_entirely_when_the_beta_map_is_off(self):
        valid = {'nodes': [['a', 'World model', ['world model'], '预测环境状态']], 'edges': [], 'targets': ['a']}
        draft = guidance_contract.parse(named(graph=valid), graph=False)['draft']
        self.assertNotIn('learning_graph', draft)
        self.assertNotIn('learning_path', draft)
        self.assertEqual(draft['keywords'], ['world model', 'robot planning'])


class ServiceFieldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(root='.', data_dir=Path(self.temp.name))
        self.addCleanup(self.app.store.close)
        patch = mock.patch('app.gateway.urllib.request.urlopen', side_effect=AssertionError('offline test'))
        patch.start()
        self.addCleanup(patch.stop)

    def turn(self, goal, message, result, mode='ai_guided', **kwargs):
        session = kwargs.pop('session', None) or self.app.create_guidance_session('Project', goal, mode)
        with mock.patch.object(self.app.gateway, 'call', return_value=result) as call:
            out = self.app.guidance_turn(session['id'], message, **kwargs)
        self.last_call = call
        return out

    def draft_of(self, out):
        return out['session']['draft']

    def test_a_new_session_holds_no_query_and_never_the_goal_as_one(self):
        for goal in ('我想了解世界模型在机器人规划里的应用', 'I want to understand how world models are used for robot planning',
                     '世界模型 world model'):
            for mode in ('quick', 'ai_guided'):
                with self.subTest(goal=goal, mode=mode):
                    draft = self.app.create_guidance_session('Project', goal, mode)['draft']
                    self.assertEqual(draft['search_queries'], [])

    def test_question_and_advice_land_in_their_own_fields(self):
        goal = '我想了解世界模型在机器人规划里的应用'
        out = self.turn(goal, goal, ok(named(reply='建议先从概览读起。')))
        draft = self.draft_of(out)
        self.assertEqual(draft['search_queries'], ['world model robot planning'])
        self.assertEqual(draft['next_question'], '你想先读论文还是复现？')
        self.assertEqual(draft['choices'], ['读论文', '复现'])
        self.assertEqual(draft['summary'], '机器人规划里的世界模型')
        self.assertEqual(out['reply'], '建议先从概览读起。')
        self.assertEqual(out['session']['transcript'][-1]['content'], '建议先从概览读起。')

    def test_the_old_cryptic_reply_that_caused_the_bug_no_longer_fills_the_search_box(self):
        goal = '我想了解世界模型在机器人规划里的应用'
        out = self.turn(goal, goal, ok(compact(k=['world model'], q=['你更想了解哪个应用方向？'], a='可以先读综述。')))
        draft = self.draft_of(out)
        self.assertEqual(draft['search_queries'], ['world model'])
        self.assertFalse(any(q.endswith(QUESTION_MARKS) for q in draft['search_queries']))
        self.assertEqual(out['mode'], 'ai')

    def test_a_query_equal_to_the_goal_the_message_or_the_reply_never_survives(self):
        goal = '我想了解世界模型在机器人规划里的应用'
        for echoed in (goal, '只做仿真，不研究机械结构', '先看概览再决定。'):
            with self.subTest(echoed=echoed):
                out = self.turn(goal, '只做仿真，不研究机械结构',
                                ok(named(reply='先看概览再决定。', queries=[echoed, echoed.upper()])))
                queries = self.draft_of(out)['search_queries']
                self.assertEqual(queries, ['world model robot planning'])

    def test_no_session_ends_with_prose_as_its_query(self):
        goals = ['我想了解世界模型在机器人规划里的应用', 'I want to understand how world models are used for robot planning',
                 '研究 diffusion policy 在灵巧操作里的作用，主要看真实机器人实验']
        message = '只做仿真，不研究机械结构，每周三小时'
        replies = {
            'valid': lambda goal, said: ok(named()),
            'echo-goal': lambda goal, said: ok(named(queries=[goal])),
            'echo-message': lambda goal, said: ok(named(queries=[said])),
            'question': lambda goal, said: ok(compact(q=['你想先理解哪个方向？'])),
            'string-q': lambda goal, said: ok(compact(q='你想先理解哪个方向？')),
            'bad-reply': lambda goal, said: ok('not json'),
            'gateway-off': lambda goal, said: {'ok': False, 'reason': 'no API key'},
        }
        for goal in goals:
            for label, make in replies.items():
                for mode in ('quick', 'ai_guided'):
                    with self.subTest(goal=goal[:12], reply=label, mode=mode):
                        said = goal if mode == 'quick' else message
                        out = self.turn(goal, said, make(goal, said), mode=mode)
                        draft, reply = self.draft_of(out), out['reply']
                        prose = {norm(goal), norm(said), norm(reply), norm(draft['next_question'])}
                        for query in draft['search_queries']:
                            self.assertNotIn(norm(query), prose)
                            self.assertFalse(query.endswith(QUESTION_MARKS))

    def test_the_local_fallback_never_turns_chinese_input_into_a_query(self):
        goal = '我想了解世界模型在机器人规划里的应用'
        out = self.turn(goal, goal, {'ok': False, 'reason': 'no API key'})
        draft = self.draft_of(out)
        self.assertEqual(out['mode'], 'local')
        self.assertEqual(draft['search_queries'], [])
        self.assertEqual(draft['keywords'], [])
        out = self.turn(goal, '只做仿真，不研究机械结构', {'ok': False, 'reason': 'no API key'}, session=out['session'])
        self.assertEqual(self.draft_of(out)['search_queries'], [])

    def test_the_local_fallback_builds_its_query_from_keywords_only(self):
        goal = 'robotic manipulation with diffusion policies and tactile feedback'
        draft = self.draft_of(self.turn(goal, goal, {'ok': False, 'reason': 'no API key'}))
        self.assertTrue(draft['keywords'])
        self.assertEqual(draft['search_queries'], [' '.join(draft['keywords'][:4])])

    def test_the_local_fallback_keeps_the_queries_the_person_edited(self):
        goal = '我想了解世界模型在机器人规划里的应用'
        out = self.turn(goal, goal, {'ok': False, 'reason': 'no API key'},
                        draft_edits={'keywords': ['world model'], 'search_queries': ['my own query', 'second query']})
        draft = self.draft_of(out)
        self.assertEqual(draft['search_queries'], ['my own query', 'second query'])
        self.assertEqual(draft['keywords'], ['world model'])

    def test_an_empty_list_from_the_model_never_wipes_what_the_person_has(self):
        goal = '机器人规划'
        out = self.turn(goal, goal, ok(named(keywords=['planning'], queries=['robot planning'])))
        out = self.turn(goal, '继续', ok(named(keywords=[], queries=[])), session=out['session'],
                        draft_edits={'keywords': ['planning', 'my term'], 'search_queries': ['my query']})
        draft = self.draft_of(out)
        self.assertEqual(draft['keywords'], ['planning', 'my term'])
        self.assertEqual(draft['search_queries'], ['my query'])

    def test_the_model_sees_the_current_queries_and_the_language_choice(self):
        goal = '机器人规划'
        self.turn(goal, goal, ok(named()), draft_edits={'keywords': ['planning'], 'search_queries': ['my query']},
                  languages=['zh', 'en'])
        body = json.loads(self.last_call.call_args.args[1][-1]['content'])
        self.assertEqual(body['user_queries'], ['my query'])
        self.assertEqual(body['user_keywords'], ['planning'])
        self.assertEqual(body['languages'], ['zh', 'en'])

    def test_an_unknown_language_code_is_not_forwarded(self):
        self.turn('机器人规划', '机器人规划', ok(named()), languages=['zh', 'xx', 3, 'zh'])
        self.assertEqual(json.loads(self.last_call.call_args.args[1][-1]['content'])['languages'], ['zh'])

    def test_the_beta_switch_decides_whether_the_model_is_asked_for_a_map(self):
        goal = 'world model planning'
        self.turn(goal, goal, ok(named()))
        self.assertNotIn('graph', self.last_call.call_args.args[1][0]['content'].casefold())
        (Path(self.temp.name) / 'settings.json').write_text(json.dumps({'routeBeta': True}))
        self.turn(goal, goal, ok(named()))
        self.assertIn('"nodes"', self.last_call.call_args.args[1][0]['content'])

    def test_a_map_proposed_with_beta_off_is_ignored_and_a_bad_one_with_beta_on_keeps_the_reply(self):
        graph = {'nodes': [['a', 'World model', ['world model'], '预测环境状态']], 'edges': [], 'targets': ['a']}
        goal = 'world model planning'
        off = self.draft_of(self.turn(goal, goal, ok(named(graph=graph))))
        self.assertEqual(off['route_draft']['source'], 'local_goal')
        (Path(self.temp.name) / 'settings.json').write_text(json.dumps({'routeBeta': True}))
        bad = dict(graph, edges=[['a', 'a']])
        out = self.turn(goal, goal, ok(named(graph=bad)))
        self.assertEqual(out['mode'], 'ai')
        self.assertEqual(self.draft_of(out)['next_question'], '你想先读论文还是复现？')
        self.assertEqual(self.draft_of(out)['route_draft']['source'], 'local_goal')
        good = self.draft_of(self.turn(goal, goal, ok(named(graph=graph))))
        self.assertEqual(good['route_draft']['source'], 'ai_guidance')

    def test_wording_does_not_mention_hidden_map_parts_when_the_beta_map_is_off(self):
        goal = '机器人规划'
        out = self.turn(goal, goal, ok(named(reply='')))
        self.assertNotIn('学习路径', out['reply'])
        self.assertNotIn('学习图', out['reply'])
        for english in (False, True):
            for phase in ('review', 'confirm'):
                text = json.dumps(project_brainstorm.local_followup({'brainstorm_phase': phase}, 'x', english, graph=False),
                                  ensure_ascii=False).casefold()
                self.assertNotIn('学习图', text)
                self.assertNotIn('learning map', text)
        on = project_brainstorm.local_followup({'brainstorm_phase': 'review'}, 'x', False, graph=True)
        self.assertIn('学习图', json.dumps(on, ensure_ascii=False))

    def test_the_agreed_summary_is_saved_with_the_project(self):
        goal = '机器人规划'
        out = self.turn(goal, goal, ok(named(summary='机器人规划里的世界模型，先读综述')))
        pid = self.app.finalize_guidance(out['session']['id'], skip_route=True)['project_id']
        self.assertEqual(self.app.projects.get_project(pid)['goal_confirmation'], '机器人规划里的世界模型，先读综述')
        self.assertEqual([p['goal_confirmation'] for p in self.app.projects.list_projects() if p['id'] == pid],
                         ['机器人规划里的世界模型，先读综述'])
        other = self.app.create_guidance_session('Other', goal)
        pid2 = self.app.finalize_guidance(other['id'], skip_route=True)['project_id']
        self.assertEqual(self.app.projects.get_project(pid2)['goal_confirmation'], '')

    def test_deleting_a_project_removes_its_saved_summary(self):
        out = self.turn('机器人规划', '机器人规划', ok(named(summary='机器人规划')))
        pid = self.app.finalize_guidance(out['session']['id'], skip_route=True)['project_id']
        self.app.delete_project(pid)
        self.assertEqual(self.app.store.get_setting('project_goal_' + pid, ''), '')

    def test_a_resumed_session_never_shows_the_goal_as_its_query(self):
        session = self.app.create_guidance_session('Project', '机器人规划')
        stored = self.app.store.guidance_session(session['id'])
        # A session saved before this fix started with the goal as its only query and no AI turn.
        self.app.store.update_guidance_session(session['id'], draft={**stored['draft'], 'search_queries': ['机器人规划']})
        self.assertEqual(self.app.guidance_session_view(session['id'])['draft']['search_queries'], [])

    def test_turn_does_not_report_truncation_state_that_no_longer_exists(self):
        out = self.turn('机器人规划', '机器人规划', ok(named()))
        self.assertNotIn('context_limits', out)
        self.assertNotIn('scope_notice', out)
        self.assertNotIn('scope_notice', out['session']['transcript'][-1])


class RoundTwo(unittest.TestCase):
    """Second round (independent review + real-model run): the person's lists survive, the reply does not repeat the
    question, goal/message prose stays out of keywords, language rules, and the smaller fixes."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(root='.', data_dir=Path(self.temp.name))
        self.addCleanup(self.app.store.close)
        patch = mock.patch('app.gateway.urllib.request.urlopen', side_effect=AssertionError('offline test'))
        patch.start()
        self.addCleanup(patch.stop)

    turn = ServiceFieldTests.turn
    draft_of = ServiceFieldTests.draft_of

    # ---- R1: what the person has is kept; the model only adds
    def test_the_persons_own_queries_and_keywords_are_kept_in_order_and_the_model_adds_after_them(self):
        goal = '机器人规划'
        mine_q = ['my first query', 'my second query', 'my third query']
        mine_k = ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta']
        out = self.turn(goal, goal, ok(named(keywords=['planning', 'Alpha', ' beta '], queries=['world model planning', 'MY FIRST QUERY'])),
                        draft_edits={'keywords': mine_k, 'search_queries': mine_q})
        draft = self.draft_of(out)
        self.assertEqual(draft['search_queries'], mine_q + ['world model planning'])
        self.assertEqual(draft['keywords'], mine_k + ['planning'])

    def test_what_the_model_adds_is_limited_to_five_keywords_and_two_queries(self):
        goal = '机器人规划'
        out = self.turn(goal, goal, ok(named(keywords=['n%d' % i for i in range(9)], queries=['q one', 'q two', 'q three'])),
                        draft_edits={'keywords': ['mine'], 'search_queries': ['my query']})
        draft = self.draft_of(out)
        self.assertEqual(draft['keywords'], ['mine'] + ['n%d' % i for i in range(5)])
        self.assertEqual(draft['search_queries'], ['my query', 'q one', 'q two'])

    def test_earlier_model_phrases_are_replaced_by_the_current_ones(self):
        goal = '机器人规划'
        out = self.turn(goal, goal, ok(named(keywords=['a1', 'a2'], queries=['first phrase'])))
        out = self.turn(goal, '继续', ok(named(keywords=['a3'], queries=['second phrase'])), session=out['session'],
                        draft_edits={'keywords': self.draft_of(out)['keywords'], 'search_queries': self.draft_of(out)['search_queries']})
        draft = self.draft_of(out)
        self.assertEqual(draft['keywords'], ['a3'])   # round three: the model's current suggestions replace its earlier ones
        self.assertEqual(draft['search_queries'], ['second phrase'])

    # ---- R2: the reply does not repeat the question
    def test_the_prompt_says_the_reply_never_asks_the_question(self):
        self.assertIn('never a question', guidance_contract.SYSTEM)

    def test_a_closing_question_in_the_reply_is_dropped_when_ask_carries_it(self):
        parsed = guidance_contract.parse(named(reply='先看概览。你想先读论文还是复现？', ask='你想先读论文还是复现？'))
        self.assertEqual(parsed['reply'], '先看概览。')
        parsed = guidance_contract.parse(named(reply='Good start. Which focus first?', ask='Which application do you mean'))
        self.assertEqual(parsed['reply'], 'Good start.')
        parsed = guidance_contract.parse(named(reply='先看概览。你想先读论文还是复现', ask='你想先读论文还是复现？'))
        self.assertEqual(parsed['reply'], '先看概览。')

    def test_the_reply_is_kept_whole_when_there_is_no_ask(self):
        self.assertEqual(guidance_contract.parse(named(reply='先看概览。你想先读论文？', ask=''))['reply'], '先看概览。你想先读论文？')
        self.assertEqual(guidance_contract.parse(named(reply='你想先读论文？', ask='你想先读论文还是复现？'))['reply'], '')   # round four: neutral text is used instead
        self.assertEqual(guidance_contract.parse(named(reply='先看概览。', ask='你想先读论文还是复现？'))['reply'], '先看概览。')
        self.assertEqual(guidance_contract.parse(named(reply='版本 1.5 更好。要不要试试？', ask='试哪个？'))['reply'], '版本 1.5 更好。')

    def test_the_shown_and_stored_reply_has_no_second_copy_of_the_question(self):
        goal = '机器人规划'
        out = self.turn(goal, goal, ok(named(reply='先看概览。你想先读论文还是复现？')))
        self.assertEqual(out['reply'], '先看概览。')
        self.assertEqual(out['session']['transcript'][-1]['content'], '先看概览。')
        self.assertEqual(self.draft_of(out)['next_question'], '你想先读论文还是复现？')

    # ---- S1: the person's sentences stay out of keywords and of keyword-built queries
    def test_the_goal_or_message_echoed_into_keywords_and_queries_ends_up_nowhere(self):
        goal, said = '我想了解世界模型在机器人规划里的应用', '只做仿真，不研究机械结构'
        for echoed in (goal, said, goal.upper()):
            with self.subTest(echoed=echoed):
                out = self.turn(goal, said, ok(named(keywords=[echoed], queries=[echoed])))
                draft = self.draft_of(out)
                self.assertEqual((draft['keywords'], draft['search_queries']), ([], []))

    def test_parse_drops_keywords_equal_to_the_avoid_list(self):
        parsed = guidance_contract.parse(named(keywords=['整句 目标', 'world model']), avoid=['整句 目标'])
        self.assertEqual(parsed['draft']['keywords'], ['world model'])
        self.assertEqual(parsed['draft']['search_queries'], ['world model robot planning'])

    # ---- S2: a resumed old quick draft
    def test_a_resumed_legacy_session_does_not_search_with_the_goal_on_its_next_turn(self):
        goal = '我想了解世界模型在机器人规划里的应用'
        session = self.app.create_guidance_session('Project', goal, 'quick')
        stored = self.app.store.guidance_session(session['id'])
        self.app.store.update_guidance_session(session['id'], draft={**stored['draft'], 'search_queries': [goal]})
        out = self.turn(goal, goal, {'ok': False, 'reason': 'no API key'}, session=session)
        self.assertEqual(self.draft_of(out)['search_queries'], [])
        self.assertNotIn('queries', json.loads(self.last_call.call_args.args[1][-1]['content']))

    def test_the_legacy_goal_query_is_not_sent_to_the_model_either(self):
        goal = '我想了解世界模型在机器人规划里的应用'
        session = self.app.create_guidance_session('Project', goal, 'quick')
        stored = self.app.store.guidance_session(session['id'])
        self.app.store.update_guidance_session(session['id'], draft={**stored['draft'], 'search_queries': [goal]})
        out = self.turn(goal, goal, ok(named(keywords=['world model'], queries=[])), session=session)
        self.assertNotIn('queries', json.loads(self.last_call.call_args.args[1][-1]['content']))
        self.assertEqual(self.draft_of(out)['search_queries'], ['world model'])

    # ---- S3: languages is input, not an output field
    def test_the_prompt_describes_languages_as_input(self):
        system = guidance_contract.SYSTEM
        self.assertNotIn('languages=', system)
        self.assertIn('input also has languages', system)

    def test_input_keys_echoed_in_the_draft_are_ignored_not_refused(self):
        content = named(languages=['zh'], goal='x', turn=1, message='y', last_question='z')
        draft = guidance_contract.parse(content)['draft']
        for key in ('languages', 'goal', 'turn', 'message', 'last_question'):
            self.assertNotIn(key, draft)
        self.assertEqual(draft['next_question'], '你想先读论文还是复现？')
        out = self.turn('机器人规划', '机器人规划', ok(content))
        self.assertEqual(out['mode'], 'ai')

    # ---- S5: language rules for phrases the model adds
    def test_a_chinese_phrase_from_the_model_needs_zh_ticked_and_at_most_one_is_kept_beside_english(self):
        goal = '机器人规划'
        reply = ok(named(queries=['世界模型 规划', '机器人 规划']))
        for languages, expected in ((['en'], []), ([], []), (['zh', 'en'], ['世界模型 规划']), (['zh'], ['世界模型 规划', '机器人 规划'])):   # 中文 alone: both (2026-10-23)
            with self.subTest(languages=languages):
                out = self.turn(goal, goal, reply, languages=languages)
                chinese = [q for q in self.draft_of(out)['search_queries'] if any('\u3400' <= c <= '\u9fff' for c in q)]
                self.assertEqual(chinese, expected)
        out = self.turn(goal, goal, ok(named(queries=['world model planning', '世界模型 规划'])), languages=['en'])
        self.assertEqual(self.draft_of(out)['search_queries'], ['world model planning'])

    def test_a_chinese_phrase_the_person_wrote_is_never_dropped(self):
        goal = '机器人规划'
        out = self.turn(goal, goal, ok(named(queries=['english phrase'])), languages=['en'],
                        draft_edits={'keywords': ['planning'], 'search_queries': ['我自己的检索式', '另一条中文检索式']})
        self.assertEqual(self.draft_of(out)['search_queries'], ['我自己的检索式', '另一条中文检索式', 'english phrase'])

    def test_the_interface_language_suffix_no_longer_contradicts_the_chinese_phrase_rule(self):
        system = guidance_contract.messages('目标', [], '目标', False, languages=['zh'])[0]['content']
        self.assertNotIn('query in English', system)
        self.assertTrue(system.endswith('Text in Chinese.'))
        self.assertTrue(guidance_contract.messages('goal', [], 'goal', True)[0]['content'].endswith('Text in English.'))

    # ---- smaller fixes
    def test_a_non_text_language_entry_is_ignored_instead_of_crashing(self):
        body = json.loads(guidance_contract.messages('g', [], 'g', languages=[{'x': 1}, ['zh'], 'zh', 'zh', 3, None])[-1]['content'])
        self.assertEqual(body['languages'], ['zh'])
        out = self.turn('机器人规划', '机器人规划', ok(named()), languages=[{'x': 1}, 'zh'])
        self.assertEqual(json.loads(self.last_call.call_args.args[1][-1]['content'])['languages'], ['zh'])
        self.assertEqual(out['mode'], 'ai')

    def test_the_streaming_preview_never_searches_with_the_goal(self):
        session = self.app.create_guidance_session('Project', '我想了解世界模型')
        with mock.patch.object(self.app.source, 'discover_topic', side_effect=AssertionError('no search without a phrase')):
            out = self.app.guidance_preview(session['id'])
        self.assertEqual((out['items'], out['errors']), ([], []))

    def test_a_learning_path_is_ignored_with_the_beta_map_off_and_cannot_drop_a_reviewed_graph(self):
        long_form = lambda **extra: json.dumps({'reply': 'x', 'draft': {
            'keywords': ['world model'], 'search_queries': ['world model planning'], 'next_question': '', **extra}})
        steps = [{'title': 'Intro', 'purpose': 'start'}]
        self.assertNotIn('learning_path', guidance_contract.parse(long_form(learning_path=steps), graph=False)['draft'])
        self.assertIn('learning_path', guidance_contract.parse(long_form(learning_path=steps))['draft'])
        invalid = {'nodes': [['a', 'World model', ['world model'], 'x']], 'edges': [['a', 'a']], 'targets': ['a']}
        self.assertNotIn('learning_path', guidance_contract.parse(long_form(learning_path=steps, learning_graph=invalid))['draft'])
        (Path(self.temp.name) / 'settings.json').write_text(json.dumps({'routeBeta': True}))
        goal = 'world model planning'
        good = {'nodes': [['a', 'World model', ['world model'], '预测环境状态']], 'edges': [], 'targets': ['a']}
        first = self.turn(goal, goal, ok(named(graph=good)))
        reviewed = self.draft_of(first)['route_draft']
        self.assertEqual(reviewed['source'], 'ai_guidance')
        second = self.turn(goal, '继续', ok(long_form(learning_path=steps, learning_graph=invalid)), session=first['session'])
        self.assertEqual(second['mode'], 'ai')
        self.assertEqual(self.draft_of(second)['route_draft'], reviewed)

    def test_the_local_fallback_filters_english_filler_words(self):
        goal = 'I want to understand how world models are used for robot planning'
        session = self.app.create_guidance_session('Project', goal)
        for filler in ('want', 'understand', 'how'):
            self.assertNotIn(filler, session['draft']['keywords'])
        draft = self.draft_of(self.turn(goal, goal, {'ok': False, 'reason': 'no API key'}, session=session))
        for filler in ('want', 'understand', 'how'):
            self.assertNotIn(filler, draft['keywords'])
            self.assertFalse(any(filler in q.split() for q in draft['search_queries']))
        self.assertIn('robot', draft['keywords'])
        self.assertEqual(draft['search_queries'], [' '.join(draft['keywords'][:4])])

    def test_the_registered_approval_note_describes_the_current_scope_without_changing_approval(self):
        root = Path(__file__).resolve().parents[1]
        entry = json.loads((root / 'harness/budget.json').read_text())['operations']['project_guidance']
        self.assertIs(entry['owner_approved'], True)
        note = entry['approval_note']
        for fact in ('2026-10-01', 'ADR 0037', 'ADR 0038', 'search phrases', 'paper-language'):
            self.assertIn(fact, note)
        self.assertNotIn('最多 6 轮', note)
        self.assertIn("owner's attention", note)


class RoundThree(unittest.TestCase):
    """Third round: who wrote each keyword/query is tracked. The person's items stay, the model's current suggestions
    replace its earlier ones (no pile-up), what the person deleted is not brought back, and an empty or unusable
    model list never empties the page."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(root='.', data_dir=Path(self.temp.name))
        self.addCleanup(self.app.store.close)
        patch = mock.patch('app.gateway.urllib.request.urlopen', side_effect=AssertionError('offline test'))
        patch.start()
        self.addCleanup(patch.stop)
        self.session = self.app.create_guidance_session('Project', '机器人规划')

    def turn(self, message='继续', result=None, edits=None, **kwargs):
        """One turn the way the page makes it: the draft it sends is the lists it shows (`edits` changes them first)."""
        shown = self.page()
        if edits:
            shown = edits(shown)
        with mock.patch.object(self.app.gateway, 'call', return_value=result or {'ok': False, 'reason': 'no API key'}) as call:
            out = self.app.guidance_turn(self.session['id'], message, draft_edits=shown, **kwargs)
        self.sent = json.loads(call.call_args.args[1][-1]['content']) if call.call_args else None
        return out

    def page(self):
        draft = self.app.guidance_session_view(self.session['id'])['draft']
        return {'keywords': list(draft['keywords']), 'search_queries': list(draft['search_queries'])}

    def model(self, keywords=(), queries=()):
        return ok(named(keywords=list(keywords), queries=list(queries)))

    def origins(self):
        draft = self.app.store.guidance_session(self.session['id'])['draft']
        return {key: draft.get(key) for key in ('user_keywords', 'user_queries', 'removed_keywords', 'removed_queries')}

    def test_the_models_suggestions_replace_its_earlier_ones_instead_of_piling_up(self):
        self.turn(result=self.model(['k a1', 'k a2'], ['q a1', 'q a2']))
        self.turn(result=self.model(['k b1'], ['q b1']))
        self.assertEqual(self.page(), {'keywords': ['k b1'], 'search_queries': ['q b1']})
        self.turn(result=self.model(['k c1', 'k c2', 'k c3', 'k c4', 'k c5', 'k c6'], ['q c1', 'q c2', 'q c3']))
        self.assertEqual(self.page(), {'keywords': ['k c1', 'k c2', 'k c3', 'k c4', 'k c5'], 'search_queries': ['q c1', 'q c2']})

    def test_what_the_person_typed_survives_every_turn_even_when_the_model_leaves_it_out(self):
        self.turn(result=self.model(['k a1'], ['q a1']))
        self.turn(result=self.model(['k b1'], ['q b1']),
                  edits=lambda p: {'keywords': p['keywords'] + ['my term'], 'search_queries': p['search_queries'] + ['my query']})
        for index in range(2, 5):
            self.turn(result=self.model(['k b%d' % index], ['q b%d' % index]))
        self.assertEqual(self.page(), {'keywords': ['my term', 'k b4'], 'search_queries': ['my query', 'q b4']})
        self.assertEqual(self.origins()['user_queries'], ['my query'])

    def test_a_user_item_the_person_later_deletes_is_gone_and_stays_gone(self):
        self.turn(result=self.model([], ['q a1']), edits=lambda p: {**p, 'search_queries': p['search_queries'] + ['my query']})
        self.turn(result=self.model([], ['q a1']), edits=lambda p: {**p, 'search_queries': [q for q in p['search_queries'] if q != 'my query']})
        self.assertEqual(self.page()['search_queries'], ['q a1'])
        self.assertEqual(self.origins()['user_queries'], [])
        self.assertEqual(self.origins()['removed_queries'], ['my query'])   # round four: a person's deleted item is not brought back either

    def test_an_ai_item_the_person_deleted_is_not_added_back_when_the_model_repeats_it(self):
        self.turn(result=self.model(['k a1', 'k a2'], ['q a1', 'q a2']))
        for _ in range(3):
            self.turn(result=self.model(['K  A1', 'k a2'], ['Q a1', 'q a2']),
                      edits=lambda p: {'keywords': [k for k in p['keywords'] if k != 'k a1'],
                                       'search_queries': [q for q in p['search_queries'] if q.lower() != 'q a1']})
        self.assertEqual(self.page(), {'keywords': ['k a2'], 'search_queries': ['q a2']})
        self.assertEqual(self.origins()['removed_queries'], ['q a1'])
        # typing it again is the person's own choice and makes it a user item
        self.turn(result=self.model(['k a2'], ['q a2']), edits=lambda p: {**p, 'search_queries': p['search_queries'] + ['q a1']})
        self.assertIn('q a1', self.page()['search_queries'])
        self.assertEqual(self.origins()['removed_queries'], [])
        self.assertIn('q a1', self.origins()['user_queries'])

    def test_an_empty_or_unusable_model_list_keeps_the_previous_suggestions(self):
        self.turn(result=self.model(['k a1', 'k a2'], ['q a1', 'q a2']))
        before = self.page()
        self.turn(result=self.model([], []))
        self.assertEqual(self.page(), before)
        self.turn(result=self.model(['你想先读什么？'], ['Which one first?', 'q a1']), message='x')   # questions are dropped; q a1 repeats
        self.assertEqual(self.page()['keywords'], before['keywords'])
        self.assertEqual(self.page()['search_queries'], ['q a1'])   # the one valid phrase is the model's current list
        self.turn(result=self.model(['k a1'], []))               # only a repeat of the person's item adds nothing new
        self.assertEqual(self.page()['search_queries'], ['q a1'])

    def test_a_local_answer_changes_no_list_and_never_brings_back_a_removed_item(self):
        goal = 'robotic manipulation with diffusion policies'
        self.session = self.app.create_guidance_session('English', goal)
        self.turn(result=self.model(['diffusion', 'k a1'], ['q a1']),
                  edits=lambda p: {'keywords': p['keywords'] + ['mine'], 'search_queries': p['search_queries'] + ['my query']})
        full = self.page()
        self.assertEqual(full, {'keywords': ['mine', 'diffusion', 'k a1'], 'search_queries': ['my query', 'q a1']})
        self.turn(edits=lambda p: {**p, 'keywords': [k for k in p['keywords'] if k != 'diffusion']})   # local answer, one deletion
        after = self.page()
        self.assertEqual(after, {'keywords': ['mine', 'k a1'], 'search_queries': full['search_queries']})
        origins = self.origins()
        self.turn(message='只做仿真，不研究机械结构')                                                  # local answer, Chinese
        self.assertEqual(self.page(), after)
        self.assertEqual(self.origins(), origins)
        self.turn(goal)                                                                              # the goal again: its terms are not re-seeded
        self.assertEqual(self.page(), after)
        self.turn(message='I really want diffusion')                                                 # mentions the deleted term again
        self.assertNotIn('diffusion', self.page()['keywords'])
        self.assertEqual(self.page()['search_queries'], full['search_queries'])
        self.turn(message='tactile feedback sensors')                                                # a new English term is added, as an AI item
        self.assertEqual(self.page()['keywords'][:2], ['mine', 'k a1'])
        self.assertIn('tactile', self.page()['keywords'])
        self.assertNotIn('tactile', self.origins()['user_keywords'])

    def test_a_session_saved_before_origins_were_tracked_counts_everything_on_the_page_as_the_persons(self):
        stored = self.app.store.guidance_session(self.session['id'])
        legacy = {key: value for key, value in stored['draft'].items()
                  if key not in ('user_keywords', 'user_queries', 'removed_keywords', 'removed_queries')}
        legacy.update(keywords=['old a', 'old b'], search_queries=['old query'])
        self.app.store.update_guidance_session(self.session['id'], draft=legacy)
        self.turn(result=self.model(['k m1'], ['q m1']), edits=lambda p: {**p, 'keywords': p['keywords'] + ['new c']})
        self.assertEqual(self.page(), {'keywords': ['old a', 'old b', 'new c', 'k m1'], 'search_queries': ['old query', 'q m1']})
        self.turn(result=self.model(['k m2'], ['q m2']))
        self.assertEqual(self.page(), {'keywords': ['old a', 'old b', 'new c', 'k m2'], 'search_queries': ['old query', 'q m2']})

    def test_a_legacy_session_without_edits_is_also_left_whole(self):
        stored = self.app.store.guidance_session(self.session['id'])
        legacy = {key: value for key, value in stored['draft'].items() if not key.startswith(('user_', 'removed_'))}
        legacy.update(keywords=['old a'], search_queries=['old query'])
        self.app.store.update_guidance_session(self.session['id'], draft=legacy)
        with mock.patch.object(self.app.gateway, 'call', return_value=self.model(['k m1'], ['q m1'])):
            out = self.app.guidance_turn(self.session['id'], '继续')
        self.assertEqual(out['session']['draft']['keywords'], ['old a', 'k m1'])
        self.assertEqual(out['session']['draft']['search_queries'], ['old query', 'q m1'])

    def test_the_model_is_sent_the_current_lists_and_the_origin_sets_stay_internal(self):
        self.turn(result=self.model(['k a1'], ['q a1']))
        out = self.turn(result=self.model(['k b1'], ['q b1']), edits=lambda p: {**p, 'search_queries': p['search_queries'] + ['my query']})
        self.assertEqual((self.sent['your_queries'], self.sent['user_queries']), (['q a1'], ['my query']))
        self.assertEqual(self.sent['your_keywords'], ['k a1'])
        for key in ('user_keywords', 'user_queries', 'removed_keywords', 'removed_queries', 'replaced_keywords', 'replaced_queries'):
            self.assertNotIn(key, out['session']['draft'])
            self.assertNotIn(key, self.app.guidance_session_view(self.session['id'])['draft'])
        for key in ('removed_keywords', 'removed_queries', 'replaced_keywords', 'replaced_queries'):
            self.assertNotIn(key, self.sent)

    def test_a_new_session_starts_with_no_user_items_so_the_local_goal_terms_are_replaceable(self):
        session = self.app.create_guidance_session('English', 'world models for robot planning')
        stored = self.app.store.guidance_session(session['id'])['draft']
        self.assertEqual((stored['user_keywords'], stored['user_queries'], stored['removed_keywords'], stored['removed_queries']), ([], [], [], []))
        self.session = session
        self.turn('world models for robot planning', result=self.model(['world model', 'robot planning'], ['world model robot planning']))
        self.assertEqual(self.page()['keywords'], ['world model', 'robot planning'])

    def test_the_preview_records_who_wrote_what_and_finalize_ignores_origin_sets_sent_by_a_client(self):
        with mock.patch.object(self.app.source, 'discover_topic', return_value=[]):
            self.app.guidance_preview(self.session['id'], {'keywords': ['mine'], 'search_queries': ['my query']})
        self.assertEqual(self.origins()['user_queries'], ['my query'])
        self.assertEqual(self.origins()['user_keywords'], ['mine'])
        self.turn(result=self.model(['k m'], ['q m']))
        self.assertEqual(self.page(), {'keywords': ['mine', 'k m'], 'search_queries': ['my query', 'q m']})
        self.app.finalize_guidance(self.session['id'], {'keywords': ['mine'], 'user_keywords': ['injected'], 'removed_keywords': ['x']}, skip_route=True)
        draft = self.app.store.guidance_session(self.session['id'])['draft']
        self.assertNotIn('injected', draft['user_keywords'])
        self.assertNotIn('x', draft['removed_keywords'])

    def test_the_prompt_says_the_suggestions_replace_the_earlier_ones_and_the_persons_items_stay(self):
        system = guidance_contract.SYSTEM
        self.assertIn('replace your earlier', system)
        self.assertIn('the user\'s own, kept anyway', system)
        self.assertNotIn('NEW', system)
        self.assertLessEqual(len(system.encode('utf-8')), 1250)


class RoundFour(unittest.TestCase):
    """Fourth round (second independent review): a deleted keyword-built query stays deleted, short goals are not
    treated as prose, the reply splitter keeps abbreviations and quotes intact, the model sees its own items apart
    from the person's, deleted person items and case-only edits are tracked, a stale page cannot flip authorship, and
    Chinese keywords need 中文."""

    setUp = RoundThree.setUp
    turn = RoundThree.turn
    page = RoundThree.page
    model = RoundThree.model
    origins = RoundThree.origins

    def full_origins(self):
        draft = self.app.store.guidance_session(self.session['id'])['draft']
        return {key: draft.get(key) for key in ('user_keywords', 'user_queries', 'removed_keywords', 'removed_queries',
                                                'replaced_keywords', 'replaced_queries', 'revision')}

    # ---- F1
    def test_a_keyword_built_query_the_person_deleted_does_not_come_back(self):
        self.assertEqual(guidance_contract.clean_queries([], ['robot planning', 'world model'], ['robot planning world model']), [])
        self.assertEqual(guidance_contract.clean_queries([], ['a b'], ['A  B?']), [])
        self.turn(result=self.model(['robot planning', 'world model'], []))
        self.assertEqual(self.page()['search_queries'], ['robot planning world model'])
        self.turn(result=self.model(['robot planning', 'world model'], []), edits=lambda p: {**p, 'search_queries': []})
        self.assertEqual(self.page()['search_queries'], [])
        self.turn(result=self.model(['robot planning', 'world model'], []))
        self.assertEqual(self.page()['search_queries'], [])
        self.turn()                                                          # a local answer as well
        self.assertEqual(self.page()['search_queries'], [])

    def test_the_local_fallback_does_not_rebuild_a_deleted_query_either(self):
        goal = 'robotic manipulation with diffusion policies'
        self.session = self.app.create_guidance_session('English', goal)
        self.turn(goal)
        built = self.page()['search_queries']
        self.assertEqual(len(built), 1)
        self.turn(goal, edits=lambda p: {**p, 'search_queries': []})
        self.assertEqual(self.page()['search_queries'], [])

    # ---- F2
    def test_only_sentence_like_goals_and_messages_count_as_prose(self):
        sentence = guidance_contract.sentence_avoid
        self.assertEqual(sentence('quantum computing', 'Robot manipulation', '世界模型', 'a, b'), ['a, b'])
        self.assertEqual(sentence('I want to understand world models', '我想了解世界模型在机器人规划里的应用', '只做仿真。', 'Is it ok?'),
                         ['I want to understand world models', '我想了解世界模型在机器人规划里的应用', '只做仿真。', 'Is it ok?'])
        self.assertEqual(sentence(None, 3, ''), [])

    def test_a_short_goal_or_a_clicked_choice_does_not_remove_the_models_matching_keyword(self):
        goal = 'quantum computing'
        self.session = self.app.create_guidance_session('Short', goal)
        draft = self.turn(goal, result=ok(named(keywords=['quantum computing'], queries=['quantum computing'])))['session']['draft']
        self.assertEqual((draft['keywords'], draft['search_queries']), (['quantum computing'], ['quantum computing']))
        out = self.turn('Robot manipulation', result=ok(named(keywords=['robot manipulation'], queries=['robot manipulation'])))
        draft = out['session']['draft']
        self.assertIn('robot manipulation', draft['keywords'])
        self.assertEqual(draft['search_queries'], ['robot manipulation'])
        parsed = guidance_contract.parse(named(keywords=['robot manipulation']), avoid=guidance_contract.sentence_avoid('Robot manipulation'))
        self.assertEqual(parsed['draft']['keywords'], ['robot manipulation'])

    # ---- F3
    def test_the_reply_splitter_keeps_abbreviations_quotes_and_decimals(self):
        cut = guidance_contract.drop_repeated_question
        ask = '先读哪个？'
        cases = {
            'Try e.g. Dreamer first. Which one?': 'Try e.g. Dreamer first.',
            'Compare A vs. B. Which first?': 'Compare A vs. B.',
            'Ask Dr. Smith about it. Ready?': 'Ask Dr. Smith about it.',
            'See Fig. 3 and Wu et al. Which first?': 'See Fig. 3 and Wu et al.',
            'Models, i.e. world models, help. Which?': 'Models, i.e. world models, help.',
            'He said "really?" and left. Which one now?': 'He said "really?" and left.',
            '他说“真的吗？”然后离开。你想先读哪个？': '他说“真的吗？”然后离开。',
            '先看概览。A 还是 B？还是都要？': '先看概览。',
            'Good start. A or B? Or both?': 'Good start.',
            '版本 1.5 更好。要不要试试？': '版本 1.5 更好。',
        }
        for reply, expected in cases.items():
            with self.subTest(reply=reply):
                self.assertEqual(cut(reply, ask), expected)
        for reply in ('Say "which one?"', 'Use e.g. Dreamer.', '先看概览。', 'Try e.g. Dreamer first. Which one?'):
            self.assertEqual(cut(reply, ''), reply, 'without an ask nothing is removed')
        self.assertEqual(cut('Say "which one?"', ask), 'Say "which one?"')
        self.assertEqual(cut('Use e.g. Dreamer.', ask), 'Use e.g. Dreamer.')

    def test_a_reply_that_is_only_the_question_falls_back_to_the_neutral_text(self):
        self.assertEqual(guidance_contract.drop_repeated_question('你想先读论文还是复现？', '你想先读论文还是复现？'), '')
        self.assertEqual(guidance_contract.drop_repeated_question('A 还是 B？还是都要？', '先读哪个？'), '')
        goal = '机器人规划'
        self.turn(goal, result=ok(named(reply='你想先读论文？', ask='你想先读论文还是复现？')))
        entry = self.app.store.guidance_session(self.session['id'])['transcript'][-1]
        self.assertEqual(entry['content'], '已更新项目草稿，请检查关键词和检索式。')

    # ---- prompt consistency
    def test_the_model_is_sent_its_own_items_apart_from_the_persons(self):
        self.turn(result=self.model(['k a1'], ['q a1']))
        self.turn(result=self.model(['k b1'], ['q b1']), edits=lambda p: {'keywords': p['keywords'] + ['my term'], 'search_queries': p['search_queries'] + ['my query']})
        self.turn(result=self.model(['k b1'], ['q b1']))
        self.assertEqual(self.sent['your_keywords'], ['k b1'])
        self.assertEqual(self.sent['your_queries'], ['q b1'])
        self.assertEqual(self.sent['user_keywords'], ['my term'])
        self.assertEqual(self.sent['user_queries'], ['my query'])
        for key in ('keywords', 'queries', 'removed_keywords', 'removed_queries', 'replaced_queries'):
            self.assertNotIn(key, self.sent)

    def test_empty_groups_are_left_out_and_direct_callers_keep_the_plain_lists(self):
        self.turn(result=self.model([], []))
        self.assertNotIn('user_queries', self.sent)
        self.assertNotIn('your_queries', self.sent)
        plain = json.loads(guidance_contract.messages('g', ['a'], 'g', queries=['q'])[-1]['content'])
        self.assertEqual((plain['keywords'], plain['queries']), (['a'], ['q']))
        both = json.loads(guidance_contract.messages('g', [], 'g', your_keywords=['a'], user_keywords=['b'],
                                                     your_queries=['c'], user_queries=['d'])[-1]['content'])
        self.assertEqual((both['your_keywords'], both['user_keywords'], both['your_queries'], both['user_queries']), (['a'], ['b'], ['c'], ['d']))
        self.assertNotIn('keywords', both)

    def test_the_prompt_names_the_two_groups_and_still_matches_the_registered_text(self):
        system = guidance_contract.SYSTEM
        for token in ('your_keywords', 'your_queries', 'user_keywords', 'user_queries', 'repeat'):
            self.assertIn(token, system)
        self.assertLessEqual(len(system.encode('utf-8')), 1250)
        self.assertIn(system, (Path(__file__).resolve().parents[1] / 'prompts/project-guidance.md').read_text())

    # ---- N1 / N2
    def test_a_person_item_that_was_deleted_is_not_brought_back_by_the_model(self):
        self.turn(result=self.model([], ['q a1']), edits=lambda p: {**p, 'search_queries': p['search_queries'] + ['my query']})
        self.turn(result=self.model([], ['MY query', 'q a1']), edits=lambda p: {**p, 'search_queries': ['q a1']})
        self.assertEqual(self.page()['search_queries'], ['q a1'])
        self.assertEqual(self.origins()['user_queries'], [])
        self.assertEqual(self.origins()['removed_queries'], ['my query'])

    def test_editing_only_the_case_or_spacing_of_a_model_item_adopts_it_with_the_persons_spelling(self):
        self.turn(result=self.model(['dreamer', 'world model'], ['q a1']))
        self.turn(result=self.model(['dreamer', 'world model'], ['q a2']),
                  edits=lambda p: {**p, 'keywords': ['Dreamer', 'World  Model']})
        self.assertEqual(self.origins()['user_keywords'], ['Dreamer', 'World  Model'])
        self.turn(result=self.model(['dreamer', 'other'], ['q a3']))
        self.assertEqual(self.page()['keywords'], ['Dreamer', 'World  Model', 'other'])
        self.assertEqual(self.origins()['removed_keywords'], [])

    # ---- N3
    def test_a_page_that_missed_a_turn_cannot_flip_authorship(self):
        self.assertEqual(self.full_origins()['revision'], 0)
        self.turn(result=self.model(['k a1'], ['q a1']), base=0)
        self.assertEqual(self.full_origins()['revision'], 1)
        self.turn(result=self.model(['k b1'], ['q b1']), base=1)
        self.assertEqual(self.full_origins()['revision'], 2)
        # the page never received the second answer: it still shows the first lists, and the person typed one more
        self.turn(result=self.model(['k c1'], ['q c1']), base=1,
                  edits=lambda p: {'keywords': ['k a1', 'typed'], 'search_queries': ['q a1', 'typed query']})
        origins = self.full_origins()
        self.assertEqual(origins['user_queries'], ['typed query'])
        self.assertEqual(origins['user_keywords'], ['typed'])
        self.assertEqual(origins['removed_queries'], [])
        self.assertEqual(self.page(), {'keywords': ['typed', 'k c1'], 'search_queries': ['typed query', 'q c1']})
        self.assertEqual(origins['revision'], 3)

    def test_a_stale_page_deletes_nothing_and_a_matching_or_missing_base_works_as_before(self):
        self.turn(result=self.model(['k a1'], ['q a1', 'q a2']), base=0)
        self.turn(base=0, edits=lambda p: {**p, 'search_queries': ['q a1']})          # stale: the deletion is not trusted
        self.assertEqual(self.page()['search_queries'], ['q a1', 'q a2'])
        self.assertEqual(self.origins()['removed_queries'], [])
        self.turn(base=2, edits=lambda p: {**p, 'search_queries': ['q a1']})          # current: the deletion counts
        self.assertEqual(self.page()['search_queries'], ['q a1'])
        self.assertEqual(self.origins()['removed_queries'], ['q a2'])
        self.turn(edits=lambda p: {**p, 'search_queries': []})                        # no base (older caller): as before
        self.assertEqual(self.origins()['removed_queries'], ['q a2', 'q a1'])
        for bad in ('1', True, 1.5, [], {}):
            self.turn(base=bad)                                                       # not a number: ignored, not an error

    def test_the_revision_is_part_of_the_session_the_page_receives_and_survives_finalize(self):
        out = self.turn(result=self.model(['k a1'], ['q a1']), base=0)
        self.assertEqual(out['session']['draft']['revision'], 1)
        self.assertEqual(self.app.guidance_session_view(self.session['id'])['draft']['revision'], 1)
        self.assertEqual(self.app.create_guidance_session('Other', '机器人规划')['draft']['revision'], 0)
        self.app.finalize_guidance(self.session['id'], {'revision': 99}, skip_route=True)
        self.assertEqual(self.app.store.guidance_session(self.session['id'])['draft']['revision'], 1)

    # ---- N4
    def test_chinese_keywords_from_the_model_need_zh_but_the_persons_own_are_kept(self):
        reply = ok(named(keywords=['机器人', 'robot planning'], queries=['robot planning']))
        self.turn(result=reply, languages=['en'], edits=lambda p: {**p, 'keywords': ['我的词']})
        self.assertEqual(self.page()['keywords'], ['我的词', 'robot planning'])
        self.turn(result=reply, languages=['zh', 'en'])
        self.assertEqual(self.page()['keywords'], ['我的词', '机器人', 'robot planning'])
        self.turn(result=reply, languages=[])
        self.assertEqual(self.page()['keywords'], ['我的词', 'robot planning'])

    # ---- N5 / N6 / N7
    def test_the_preview_without_a_draft_does_not_search_the_legacy_goal_query(self):
        goal = '我想了解世界模型在机器人规划里的应用'
        stored = self.app.store.guidance_session(self.session['id'])
        self.app.store.update_guidance_session(self.session['id'], draft={**stored['draft'], 'search_queries': [goal], 'goal': goal})
        with mock.patch.object(self.app.source, 'discover_topic', side_effect=AssertionError('no search with the goal')):
            out = self.app.guidance_preview(self.session['id'])
        self.assertEqual(out['items'], [])
        self.assertEqual(self.app.store.guidance_session(self.session['id'])['draft']['search_queries'], [])

    def test_up_to_two_hundred_removed_items_are_remembered_newest_last(self):
        draft = self.app.store.guidance_session(self.session['id'])['draft']
        draft = self.app._bounded_guidance_draft({**draft, 'removed_keywords': ['w%d' % i for i in range(250)],
                                                  'removed_queries': ['q%d' % i for i in range(250)]})
        self.assertEqual(len(draft['removed_keywords']), 200)
        self.assertEqual(draft['removed_keywords'][-1], 'w249')
        self.assertEqual(draft['removed_queries'][0], 'q50')
        keywords = ['k%d' % i for i in range(20)]
        self.turn(result=self.model(keywords, []), edits=lambda p: {**p, 'keywords': keywords})
        for round_ in range(11):
            self.turn(edits=lambda p: {**p, 'keywords': []} if round_ % 2 == 0 else {**p, 'keywords': keywords})
        self.assertLessEqual(len(self.origins()['removed_keywords']), 200)

    def test_the_approval_note_uses_the_possessive(self):
        root = Path(__file__).resolve().parents[1]
        note = json.loads((root / 'harness/budget.json').read_text())['operations']['project_guidance']['approval_note']
        self.assertIn("owner's attention", note)
        self.assertNotIn('owner attention', note)


if __name__ == '__main__':
    unittest.main()
