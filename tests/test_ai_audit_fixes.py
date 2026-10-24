"""Audit identity, budget, response and missing-evidence regressions. No network."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import ai_evidence, category_review, guidance_contract, growthproposal, route_revision
from app.gateway import Gateway, input_bound, request_envelope
from app.service import App

ROOT = Path(__file__).resolve().parents[1]


class ReplyGateway:
    def __init__(self, content, effect=None):
        self.content, self.effect = content, effect
    def call(self, op, messages, **kw):
        if self.effect:
            self.effect()
        return {'ok': True, 'content': self.content, 'usage': {'total_tokens': 10}, 'usd': '0.0001', 'model': 'fake'}


class AuditFixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name))
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project('Public regression')['project_id']
        self.rows = [{'key': key, 'title': 'Public world model planning ' + key, 'abstract': 'Public test abstract',
                      'published': '2026-09-01'} for key in ('a', 'b')]
        self.app.store.upsert_papers(self.rows, project_id=self.pid)

    def triage_item(self, key):
        return dict(paper_id=key, one_liner='Public summary', why_relevant='Explicit task', caution='Unknown full text')

    def test_unknown_billing_receipt_survives_success_and_bad_reply(self):
        reserved = {'input': 4200, 'output': 1200, 'usd': '0.0027'}
        def response(content, ok=True):
            return {'ok': ok, 'content': content, 'usage': {'total_tokens': 5400},
                    'usd': reserved['usd'], 'usage_unknown': True, 'reservation': reserved,
                    'model': 'fake', 'reason': 'controlled bad reply'}
        good_qa = json.dumps({'answer': 'Supported answer', 'followups': []})
        for invoke, content, expected in [
                (lambda: self.app.qa('a', 'Question', project_id=self.pid), good_qa, True),
                (lambda: self.app.qa('a', 'Question', project_id=self.pid), '["invalid"]', False),
                (lambda: self.app.translate('Public sentence'), '公开句子', True),
                (lambda: self.app.triage(self.rows, project_id=self.pid),
                 json.dumps([self.triage_item('a'), self.triage_item('b')]), True),
                (lambda: self.app.triage(self.rows, project_id=self.pid), '[]', False)]:
            with mock.patch.object(self.app.gateway, 'call', return_value=response(content)):
                result = invoke()
            self.assertEqual(result['ok'], expected)
            self.assertTrue(result['usage_unknown']); self.assertTrue(result['usage_reserved'])
            self.assertEqual(result['reservation'], reserved)
            self.assertEqual(result['usage'], {'total_tokens': 5400})
        for invoke in (lambda: self.app.qa('a', 'Question', project_id=self.pid),
                       lambda: self.app.translate('Public sentence'),
                       lambda: self.app.triage(self.rows, project_id=self.pid)):
            with mock.patch.object(self.app.gateway, 'call', return_value=response(None, False)):
                result = invoke()
            self.assertFalse(result['ok']); self.assertTrue(result['usage_reserved'])
            self.assertEqual(result['reservation'], reserved)

    def test_legacy_ai_map_needs_stay_optional_at_both_compatibility_entries(self):
        session = self.app.create_guidance_session('Legacy test', 'Representation before Planning is optional.')['id']
        graph = {'concepts': [
            {'id': 'a', 'name': 'Representation', 'terms': ['representation'], 'hint': 1, 'needs': []},
            {'id': 'b', 'name': 'Planning', 'terms': ['planning'], 'hint': 2, 'needs': ['a']}], 'targets': ['b']}
        self.app.gateway = ReplyGateway(json.dumps(graph))
        for invoke in (lambda: self.app.route_plan(session),
                       lambda: self.app.route_plan_project(self.pid, 'Representation before Planning is optional.')):
            result = invoke()
            self.assertTrue(result['ok']); self.assertEqual(result['graph']['prereqs'], [])
            self.assertEqual(len(result['report']['prerequisite_review']), 1)
            self.assertEqual(result['report']['prerequisite_review'][0]['from'], 'Representation')
            self.assertEqual(result['report']['prerequisite_review'][0]['to'], 'Planning')

    def test_old_unconfirmed_ai_cache_is_optional_in_views_and_original_is_preserved(self):
        session = self.app.create_guidance_session('Old cache', 'Representation before Planning is optional.')['id']
        cached = {'graph': {'concepts': [
            {'id': 'a', 'name': 'Representation', 'terms': ['representation'], 'hint': 1},
            {'id': 'b', 'name': 'Planning', 'terms': ['planning'], 'hint': 2}],
            'prereqs': [{'from': 'a', 'to': 'b'}], 'targets': ['b']}, 'report': {}, 'tokens': 10}
        key = 'route_plan_' + session
        stored = {'plan': cached, 'attempts': 1}; self.app.store.set_setting(key, stored)
        with mock.patch.object(self.app.gateway, 'call') as call:
            out = self.app.route_plan(session)
        call.assert_not_called(); self.assertEqual(out['mode'], 'kept')
        self.assertEqual(out['graph']['prereqs'], []); self.assertTrue(out['report']['warnings'])
        self.assertEqual(self.app.guidance_session_view(session)['draft']['route_plan']['graph']['prereqs'], [])
        self.assertEqual(self.app.store.get_setting(key), stored)
        # An operation name alone is no proof for old unconfirmed drafts.
        new = {**cached, 'operation': 'route_map_create'}
        self.assertEqual(self.app._legacy_plan_view(new)['graph']['prereqs'], [])

    def test_current_grounded_and_old_brief_cache_at_quick_and_guided_entries(self):
        quote = 'Representation is required before Planning.'
        brief = dict(goal='Learn planning', known='', include='', exclude='', structure=quote)
        payload = {'concepts': [
            {'id': 'c1', 'name': 'Representation', 'terms': ['representation'], 'why': ''},
            {'id': 'c2', 'name': 'Planning', 'terms': ['planning'], 'why': 'Required in the brief'}],
            'prereqs': {'c2': {'required': ['c1'], 'quote': quote}}, 'targets': ['c2']}
        for mode in ('quick', 'ai_guided'):
            session = self.app.create_guidance_session('Grounded cache', 'Learn planning', creation_mode=mode)['id']
            parsed = route_revision.parse_creation(json.dumps(payload), brief=brief)
            plan = {**parsed, 'brief': brief, 'operation': 'route_map_create'}
            key = 'route_plan_' + session
            for grounded in (True, False):
                stored = {'plan': plan if grounded else {k: v for k, v in plan.items() if k != 'grounding'}, 'attempts': 1}
                self.app.store.set_setting(key, stored)
                with mock.patch.object(self.app.gateway, 'call') as call:
                    out = self.app.route_brief_plan(brief, session_id=session)
                call.assert_not_called(); self.assertEqual(out['mode'], 'kept')
                self.assertEqual(len(out['graph']['prereqs']), int(grounded))
                self.assertEqual(len(self.app.guidance_session_view(session)['draft']['route_plan']['graph']['prereqs']), int(grounded))
                self.assertEqual(self.app.store.get_setting(key), stored)

    def test_b02_b19_exact_keys_types_duplicate_and_missing_refuse_all_writes(self):
        invalid = [[self.triage_item('foreign')], [self.triage_item('a')],
                   [self.triage_item('a'), self.triage_item('a')],
                   [self.triage_item('a'), {**self.triage_item('b'), 'one_liner': 123}]]
        for items in invalid:
            self.app.gateway = ReplyGateway(json.dumps(items))
            out = self.app.triage(self.rows, project_id=self.pid)
            self.assertFalse(out['ok']); self.assertEqual(self.app.store.summaries(), {})

    def test_b02_source_or_membership_changed_during_call_refuses_atomically(self):
        for effect in [lambda: self.app.store.conn.execute("UPDATE papers SET title='Changed' WHERE key='b'"),
                       lambda: self.app.store.conn.execute('DELETE FROM project_papers WHERE project_id=? AND paper_key=?', (self.pid, 'b'))]:
            self.app.store.upsert_papers(self.rows, project_id=self.pid)
            self.app.store.conn.execute('UPDATE papers SET title=? WHERE key=?', (self.rows[1]['title'], 'b'))
            self.app.store.conn.commit()
            def mutate():
                effect(); self.app.store.conn.commit()
            self.app.gateway = ReplyGateway(json.dumps([self.triage_item('a'), self.triage_item('b')]), mutate)
            out = self.app.triage(self.rows, project_id=self.pid)
            self.assertFalse(out['ok']); self.assertEqual(self.app.store.summaries(), {})

    def test_b02_storage_fault_cannot_leave_first_summary_committed(self):
        self.app.gateway = ReplyGateway(json.dumps([self.triage_item('a'), self.triage_item('b')]))
        original = self.app.store.save_summary
        def fail_second(key, *args, **kwargs):
            if key == 'b': raise ValueError('controlled write failure')
            return original(key, *args, **kwargs)
        with mock.patch.object(self.app.store, 'save_summary', side_effect=fail_second):
            out = self.app.triage(self.rows, project_id=self.pid)
        self.assertFalse(out['ok']); self.assertEqual(self.app.store.summaries(), {})

    def test_b03_request_beyond_the_model_window_stops_before_transport_and_ledger(self):
        # Only the model's own window refuses a request (owner 2026-10-22); shrink it so the cases stay small.
        self.app.gateway.config['provider']['context_tokens'] = 20000
        with mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-key', 'PAGETIDE_DEV': '0'}), \
             mock.patch('app.gateway.urllib.request.urlopen') as opened:
            for kwargs in [dict(question='x' * 150000), dict(question='q', selection='中' * 10000)]:
                out = self.app.qa('a', project_id=self.pid, **kwargs)
                self.assertFalse(out['ok']); self.assertIn('最大长度', out['reason'])
                self.assertIn('未发送', out['reason']); self.assertEqual(out['reason_code'], 'invalid_input')
            self.app.store.add_qa('a', 'assistant', 'old' * 10000, project_id=self.pid)
            out = self.app.qa('a', 'short', project_id=self.pid)
            self.assertFalse(out['ok']); self.assertEqual(out['reason_code'], 'invalid_input')
        opened.assert_not_called(); self.assertFalse(self.app.gateway.ledger.exists())

    def test_b03_long_question_selection_and_history_inside_the_window_are_sent_whole(self):
        payload = {'choices': [{'message': {'content': json.dumps({'answer': 'Whole input seen', 'followups': []})}}],
                   'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}
        response = mock.MagicMock(); response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        question, selection, old = 'LONG_QUESTION ' + 'x' * 20000, 'LONG_SELECTION ' + '中' * 3000, 'OLD_TURN ' + 'old ' * 3000
        self.app.store.add_qa('a', 'assistant', old, project_id=self.pid)
        with mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-key', 'PAGETIDE_DEV': '0'}), \
             mock.patch('app.gateway.urllib.request.urlopen', return_value=response) as opened:
            out = self.app.qa('a', question, selection=selection, project_id=self.pid)
        self.assertTrue(out['ok'])
        envelope = json.loads(opened.call_args.args[0].data)
        self.assertGreater(input_bound(envelope), 4200)   # the old estimate is not an admission limit
        self.assertIn(question, envelope['messages'][-1]['content']); self.assertIn(selection, envelope['messages'][-1]['content'])
        self.assertIn(old, json.dumps(envelope['messages'], ensure_ascii=False))
        self.assertEqual(envelope['max_tokens'], 384000)

    def test_b04_bad_json_types_return_stable_failure_without_history(self):
        for answer, followups in [(123, []), ('answer', 'next'), ('answer', 123), ('answer', [123]), ('answer', {})]:
            self.app.gateway = ReplyGateway(json.dumps(dict(answer=answer, followups=followups)))
            out = self.app.qa('a', 'question', project_id=self.pid)
            self.assertFalse(out['ok']); self.assertTrue(out['bad_reply'])
            self.assertEqual(self.app.qa_history('a', self.pid), [])

    def test_b04_json_arrays_scalars_or_broken_wrappers_are_not_plain_prose(self):
        invalid = ['["unsupported"]', '"answer"', '123', 'true', 'null',
                   '[{"answer":"hidden object","followups":[]}]',
                   '{broken', 'prefix {"answer":"embedded","followups":[]}']
        for content in invalid:
            self.app.gateway = ReplyGateway(content)
            out = self.app.qa('a', 'question', project_id=self.pid)
            self.assertFalse(out['ok'], content); self.assertTrue(out['bad_reply'])
            self.assertEqual(self.app.qa_history('a', self.pid), [])

    def test_b03_pdf_retrieval_sends_every_passage_and_the_whole_abstract(self):
        self.app.save_fulltext('a', [{'page': i, 'text': 'world model planning evidence. ' * 80} for i in range(1, 12)])
        abstract = 'ABSTRACT_START ' + 'Public test abstract. ' * 100 + 'ABSTRACT_END'
        self.app.store.conn.execute("UPDATE papers SET abstract=? WHERE key='a'", (abstract,)); self.app.store.conn.commit()
        payload = {'choices': [{'message': {'content': json.dumps({'answer': 'Full excerpts', 'followups': []})}}],
                   'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}
        response = mock.MagicMock(); response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-key', 'PAGETIDE_DEV': '0'}), \
             mock.patch('app.gateway.urllib.request.urlopen', return_value=response) as opened:
            out = self.app.qa('a', 'KEEP_QUESTION world model', selection='KEEP_SELECTION', project_id=self.pid)
        self.assertTrue(out['ok']); self.assertNotIn('context_limits', out)
        envelope = json.loads(opened.call_args.args[0].data)
        self.assertGreater(input_bound(envelope), 4200)   # nothing is dropped to fit the old estimate
        text = envelope['messages'][-1]['content']
        self.assertIn('KEEP_QUESTION world model', text); self.assertIn('KEEP_SELECTION', text)
        self.assertIn(abstract, text); self.assertNotIn('摘要节选', text); self.assertNotIn('预算未发送', text)
        self.assertTrue(out['pages'])
        for page in out['pages']:
            self.assertIn(f'[第 {page} 页]', text)
        retrieved = self.app.passages('a', 'KEEP_QUESTION world model', k=8)
        self.assertGreater(len(retrieved), 1)
        for hit in retrieved:   # every retrieved excerpt is in the request, none dropped for budget
            self.assertIn(hit['text'], text)

    def test_gateway_malformed_choice_and_usage_types_are_stable_and_never_free(self):
        gateway = self.app.gateway
        payloads = [dict(choices=[123], usage={'prompt_tokens': 10, 'completion_tokens': 1}),
                    dict(choices=[{'message': {'content': 123}}], usage={'prompt_tokens': 10, 'completion_tokens': 1}),
                    dict(choices=[], usage={'prompt_tokens': 'bad', 'completion_tokens': 1})]
        with mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-key', 'PAGETIDE_DEV': '0'}):
            for payload in payloads:
                response = mock.MagicMock(); response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
                with mock.patch('app.gateway.urllib.request.urlopen', return_value=response):
                    out = gateway.call('paper_qa', [{'role': 'user', 'content': 'Question'}])
                self.assertTrue(out.get('bad_reply') or out.get('usage_unknown'))
        self.assertGreater(len(gateway._entries()), 0)

    def test_b04_unknown_usage_bad_empty_or_truncated_text_retains_reservation(self):
        for content, finish in [(123, 'stop'), (['text'], 'stop'), ('', 'stop'), (' ', 'stop'), ('cut', 'length')]:
            payload = dict(choices=[{'message': {'content': content}, 'finish_reason': finish}])
            response = mock.MagicMock(); response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
            with mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-key', 'PAGETIDE_DEV': '0'}), \
                 mock.patch('app.gateway.urllib.request.urlopen', return_value=response):
                out = self.app.gateway.call('selection_translate', [{'role': 'user', 'content': 'Public phrase'}])
            self.assertFalse(out['ok']); self.assertTrue(out['bad_reply']); self.assertTrue(out['usage_unknown'])
            self.assertGreater(float(out['usd']), 0)
        entries = self.app.gateway._entries()
        self.assertEqual(len(entries), 5); self.assertTrue(all(e['status'] == 'reserved' for e in entries))
        self.assertTrue(all(e['input'] > 0 and e['output'] > 0 and float(e['usd']) > 0 for e in entries))

    def test_b10_compact_chinese_english_drafts_send_goal_message_and_keywords_whole_and_reject_length(self):
        goal, message = '硫化物全固态锂电池界面稳定性' * 30, '关注正极而非锂金属负极' * 20
        keywords = ['Li6PS5Cl', '界面反应', 'k3', 'k4', 'k5']
        for english in [False, True]:
            messages = guidance_contract.messages(goal, keywords, message, english,
                                                  last_question='上一个问题' * 40, summary='目前确认' * 60)
            body = json.loads(messages[-1]['content'])
            self.assertEqual((body['goal'], body['message'], body['keywords']), (goal, message, keywords))
            self.assertEqual((body['last_question'], body['summary']), ('上一个问题' * 40, '目前确认' * 60))
            # The registered 1200 input is an estimate now; the compact request is simply larger than it.
            self.assertGreater(input_bound(request_envelope('project_guidance', 'deepseek-flash', 500, messages)), 1200)
        with self.assertRaises(ValueError): guidance_contract.parse('{}', 'length')

    def test_b11_frozen_category_actions_are_aliased_and_full_directory_stays(self):
        ds = [{'id': 'private-cat', 'name': 'Interfaces', 'parent_id': None}]
        ps = [{'key': 'private-paper', 'title': 'Public cathode interface', 'abstract': 'Public metadata', 'categories': ['private-cat']}]
        prepared = category_review.prepare(ds, ps, fixed_actions=[{'id': 'private-cat', 'action': 'keep', 'reason': 'Supported'}])
        wire = json.dumps(prepared['messages'])
        self.assertNotIn('private-', wire)
        body = json.loads(prepared['messages'][-1]['content'])
        self.assertEqual(body['fixed_actions'], {})
        self.assertEqual(len(body['categories']), 1)

    def test_b20_incomplete_title_missing_abstract_becomes_unclear_but_invalid_reply_still_rejected(self):
        graph = {'concepts': [{'id': 'concept', 'name': 'Cathode interface', 'terms': ['cathode'], 'hint': 2}], 'prereqs': [], 'targets': ['concept']}
        paper = {'key': 'public', 'title': 'Liquid L', 'abstract': None}
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Assumed liquid lithium'}
        result, error = growthproposal.validate_result(item, [paper], graph, [])
        self.assertIsNone(error); self.assertEqual(result['proposal_type'], 'unclear'); self.assertIsNone(result['nearest'])
        rejected, _ = growthproposal.validate_result({**item, 'nearest': 'c99'}, [paper], graph, [])
        self.assertIsNone(rejected)
        body = json.loads(growthproposal.messages([paper], graph, [])[1]['content'])
        self.assertTrue(body['papers']['p1']['abstract_missing'])
        title = 'Stable Interface between Sulfide Solid Electrolyte and Room-Temperature Liquid Lithium Anode'
        fragmentary = {'key': 'public', 'title': title, 'abstract': 'Sulfide solid electrolytes have high conductivity.'}
        result, error = growthproposal.validate_result(item, [fragmentary], graph, [])
        self.assertIsNone(error); self.assertEqual(result['proposal_type'], 'unclear')

    def test_b21_dependency_need_is_reviewable_and_optional_methods_not_required(self):
        self.assertIn('Optional', route_revision.REVISION_SYSTEM)
        self.assertIn('necessity', route_revision.CREATE_SYSTEM)
        value = {'concepts': [{'id': 'c1', 'name': 'Representation', 'terms': ['representation']},
                              {'id': 'c2', 'name': 'Planning', 'terms': ['planning']}],
                 'prereqs': [['c1', 'c2']], 'targets': ['c2']}
        warnings = route_revision.parse_creation(json.dumps(value))['report']['warnings']
        self.assertTrue(any('必要依据' in text for text in warnings))

    def test_b20_decisive_coverage_needs_literal_visible_object_and_treatment(self):
        graph = {'concepts': [{'id': 'axis', 'name': 'PD1 axis', 'terms': ['PD-1']},
                              {'id': 'resistance', 'name': 'Tumor resistance', 'terms': ['resistance']}],
                 'prereqs': [], 'targets': ['resistance']}
        for title, treatment in [('Dual inhibition in platinum-resistant NSCLC', 'platinum'),
                                 ('Resistance to KRASG12C inhibitors in NSCLC', 'KRASG12C')]:
            source = {'key': 'paper', 'title': title, 'abstract': 'A visible background only.'}
            item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c2', 'reason': 'Same topic',
                    'evidence': [{'paper': 'p1', 'quote': title, 'object': 'NSCLC', 'treatment': treatment, 'type': 'unknown'}]}
            result, error = growthproposal.validate_result(item, [source], graph, [])
            self.assertIsNone(error); self.assertEqual(result['proposal_type'], 'unclear')
            item['evidence'][0]['paper'] = 'p99'
            self.assertEqual(growthproposal.validate_result(item, [source], graph, [])[1], 'invalid_evidence')
        title = 'PD-1 resistance in NSCLC cell line xenografts'
        source = {'key': 'paper', 'title': title, 'abstract': ''}
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c2', 'reason': 'Clinically proven benefit',
                'evidence': [{'paper': 'p1', 'quote': title, 'object': 'NSCLC', 'treatment': 'PD-1', 'type': 'basic'}]}
        result, _ = growthproposal.validate_result(item, [source], graph, [])
        self.assertEqual(result['proposal_type'], 'unclear')
        item['reason'] = 'Study PD-1 resistance in cell line models.'
        result, _ = growthproposal.validate_result(item, [source], graph, [])
        self.assertEqual(result['proposal_type'], 'covered'); self.assertEqual(result['source_evidence'][0]['type'], 'basic')
        item['evidence'][0]['quote'] = 'A hidden result with PD-1 resistance and NSCLC'
        self.assertEqual(growthproposal.validate_result(item, [source], graph, [])[0]['proposal_type'], 'unclear')
        quote = 'NSCLC PD-1 therapy improved survival in mice; no clinical trial.'
        source.update(title=quote)
        item.update(reason='Clinical benefit improves survival', nearest='c1')
        item['evidence'] = [{'paper': 'p1', 'quote': quote, 'object': 'NSCLC', 'treatment': 'PD-1', 'type': 'trial'}]
        self.assertEqual(growthproposal.validate_result(item, [source], graph, [])[0]['proposal_type'], 'unclear')

    def test_b21_new_hard_relation_without_literal_necessity_stays_optional(self):
        graph = {'concepts': [{'id': 'base', 'name': 'Representation', 'terms': ['representation'],
                              'intro': 'Planning requires Representation.'}], 'prereqs': [], 'targets': ['base']}
        title = 'Visual planning from image representations'
        source = {'key': 'paper', 'title': title, 'abstract': 'Planning public evidence.'}
        item = {'papers': ['p1'], 'verdict': 'new_task', 'name': 'Planning', 'terms': ['planning'],
                'intro': 'Study visual planning', 'barrier': '', 'reason': 'A distinct planning task', 'parent': 'c1', 'needs': [],
                'evidence': [{'paper': 'p1', 'quote': title, 'object': 'planning', 'treatment': '', 'type': 'unknown'}]}
        result, _ = growthproposal.validate_result(item, [source], graph, [])
        self.assertEqual(result['proposal_type'], 'new_branch'); self.assertEqual(result['needs'], [])
        item['necessity'] = [{'node': 'c1', 'quote': 'Planning requires Representation.'}]
        result, _ = growthproposal.validate_result(item, [source], graph, [])
        self.assertEqual(result['proposal_type'], 'new_task')
        graph['concepts'][0]['intro'] = 'Planning does not require Representation.'
        item['necessity'][0]['quote'] = graph['concepts'][0]['intro']
        result, _ = growthproposal.validate_result(item, [source], graph, [])
        self.assertEqual(result['proposal_type'], 'new_branch')

    def test_b20_literal_quote_still_cannot_override_explicit_object_conflict(self):
        cases = [
            ('NSCLC PD-1 resistance', ['PD-1'], 'PD-1 resistant melanoma cells were studied in vitro.', 'melanoma', 'PD-1', 'basic'),
            ('Cathode sulfide interface', ['sulfide'], 'Sulfide electrolyte bulk ionic conductivity was measured using impedance.', 'Sulfide', '', 'unknown')]
        for name, terms, quote, obj, treatment, kind in cases:
            graph = {'concepts': [{'id': 'scope', 'name': name, 'terms': terms}], 'prereqs': [], 'targets': ['scope']}
            source = {'key': 'paper', 'title': quote, 'abstract': ''}
            item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Same keyword',
                    'evidence': [{'paper': 'p1', 'quote': quote, 'object': obj, 'treatment': treatment, 'type': kind}]}
            result, error = growthproposal.validate_result(item, [source], graph, [])
            self.assertIsNone(error); self.assertEqual(result['proposal_type'], 'unclear')

    def test_explicit_pd1_mechanism_is_not_vetoed_by_adjacent_kras_keyword(self):
        quote = 'NSCLC PD-1 resistance was induced by KRAS mutation in vitro.'
        graph = {'concepts': [{'id': 'scope', 'name': 'PD-1 resistance', 'terms': ['PD-1 resistance']}],
                 'prereqs': [], 'targets': ['scope']}
        source = {'key': 'paper', 'title': quote, 'abstract': ''}
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Basic mechanism',
                'evidence': [{'paper': 'p1', 'quote': quote, 'object': 'NSCLC', 'treatment': 'PD-1', 'type': 'basic'}]}
        result, error = growthproposal.validate_result(item, [source], graph, [], fixed_scope='NSCLC PD-1 resistance')
        self.assertIsNone(error); self.assertEqual(result['proposal_type'], 'covered')
        # This synthetic control tests scope admission, not a medical truth claim.
        source['title'] = quote.replace('PD-1 resistance', 'Resistance'); item['evidence'][0]['quote'] = source['title']
        item['evidence'][0]['treatment'] = ''
        result, error = growthproposal.validate_result(item, [source], graph, [], fixed_scope='NSCLC PD-1 resistance')
        self.assertIsNone(error); self.assertEqual(result['proposal_type'], 'unclear')

    def test_manual_map_growth_respects_explicit_project_scope_and_changes_stale_it(self):
        pid = self.app.create_project('Fixed scope', keywords=['NSCLC', 'PD-1 resistance'])['project_id']
        graph = {'concepts': [{'id': 'tme', 'name': 'Tumor microenvironment',
                  'terms': ['microenvironment'], 'hint': 2}], 'prereqs': [], 'targets': ['tme']}
        self.app.route_save(pid, graph=graph)
        quote = 'PD-1 resistant melanoma cells in microenvironment were studied in vitro.'
        self.app.store.upsert_papers([{'key': 'melanoma', 'title': quote, 'abstract': '', 'published': '2026-09-01'}], project_id=pid)
        self.app.record_feedback('melanoma', 'useful', project_id=pid)
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Microenvironment overlap',
                'evidence': [{'paper': 'p1', 'quote': quote, 'object': 'melanoma', 'treatment': 'PD-1', 'type': 'basic'}]}
        def reply(op, messages, **kwargs):
            sent = json.loads(messages[1]['content'])['papers']['p1']
            item['evidence'] = {'p1':{'type':'basic',
                'snippet':next(sid for sid, option in sent['snippets'].items() if quote == option['text'])}}
            return {'ok':True, 'content':json.dumps({'results':[item]}),
                    'usage':{'total_tokens':10}, 'usd':'0.0001', 'model':'fake'}
        with mock.patch.object(self.app.gateway, 'call', side_effect=reply):
            out = self.app.route_direction_judge(pid)
        self.assertEqual(out['results'][0]['verdict'], 'unclear')
        before = self.app._growth_context(pid)
        self.app.projects.update_project(pid, keywords=['melanoma', 'PD-1 resistance'])
        self.assertNotEqual(before, self.app._growth_context(pid))

    def test_first_growth_batch_selects_same_fixed_scope_fragment_as_validator(self):
        pid = self.app.create_project('Public manual scope', keywords=['NSCLC', 'PD-1 resistance'])['project_id']
        graph = {'concepts': [{'id': 'tme', 'name': 'Microenvironment',
                              'terms': ['microenvironment'], 'hint': 2}], 'prereqs': [], 'targets': ['tme']}
        self.app.route_save(pid, graph=graph)
        quote = 'NSCLC PD-1 resistance alters microenvironment in vitro'
        source = {'key': 'scoped', 'title': 'Public experimental mechanism',
                  'abstract': 'Microenvironment introduction. ' * 20 + quote, 'published': '2026-09-01'}
        self.app.store.upsert_papers([source], project_id=pid)
        self.app.record_feedback('scoped', 'useful', project_id=pid)
        def reply(op, messages, **kwargs):
            body = json.loads(messages[1]['content'])
            self.assertIn(quote, body['papers']['p1']['abstract'])
            item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Visible mechanism',
                    'evidence': [{'paper': 'p1', 'quote': quote, 'object': 'NSCLC', 'treatment': 'PD-1', 'type': 'basic'}]}
            item['evidence'] = {'p1':{'type':'basic',
                'snippet':next(sid for sid, option in body['papers']['p1']['snippets'].items() if quote == option['text'])}}
            return {'ok': True, 'content': json.dumps({'results': [item]}), 'usage': {'total_tokens': 10}}
        with mock.patch.object(self.app.gateway, 'call', side_effect=reply) as call:
            out = self.app.route_direction_judge(pid)
        self.assertEqual(call.call_count, 1); self.assertTrue(out['complete'])
        self.assertEqual(out['results'][0]['verdict'], 'covered')
        evidence = out['results'][0]['source_evidence'][0]
        self.assertEqual(source[evidence['field']][evidence['start']:evidence['end']], quote)

    def test_removing_sulfide_map_node_does_not_remove_fixed_electrolyte_scope(self):
        pid = self.app.create_project('Fixed electrolyte')['project_id']
        metal = {'id':'metal','name':'锂金属界面反应','terms':['lithium metal interface'],'hint':2}
        foundation = {'id':'sulfide','name':'Sulfide electrolyte','terms':['sulfide electrolyte'],'hint':2}
        brief = {'goal':'Study lithium metal interface with sulfide electrolyte.',
                 'known':'Basic electrochemistry','include':'Interface evidence','exclude':'','structure':''}
        self.app.route_save(pid,graph={'concepts':[foundation,metal],'prereqs':[],'targets':['metal']},brief=brief)
        self.app.route_save(pid,graph={'concepts':[metal],'prereqs':[],'targets':['metal']})
        scope = self.app._learning_scope(pid)
        self.assertTrue(any(c['kind']=='sulfide_electrolyte' for c in scope['constraints']))
        titles = {'coating':'The lithium metal interface used a sulfide coating.',
                  'electrolyte':'The lithium metal interface used a sulfide electrolyte.'}
        for key,title in titles.items():
            self.app.store.upsert_papers([{'key':key,'title':title,'abstract':'','published':'2026-09-01'}],project_id=pid)
            self.app.record_feedback(key,'useful',project_id=pid)
        def reply(op,messages,**kwargs):
            body = json.loads(messages[-1]['content'])
            groups = [{'papers':[alias],'verdict':'covered','nearest':'c1','reason':'Literal interface',
                'evidence':{alias:{'snippet':next(iter(record['snippets'])),'type':'unknown'}}}
                for alias,record in body['papers'].items()]
            return {'ok':True,'content':json.dumps({'results':groups}),'usage':{'total_tokens':10}}
        with mock.patch.object(self.app.gateway,'call',side_effect=reply):
            out = self.app.route_direction_judge(pid)
        self.assertTrue(out['complete']); self.assertEqual(out['processed'],2)
        by_title = {row['titles'][0]:row['verdict'] for row in out['results']}
        self.assertEqual(by_title[titles['coating']],'unclear')
        self.assertEqual(by_title[titles['electrolyte']],'covered')

    def test_growth_reply_cannot_redefine_a_frozen_snippet_after_call(self):
        pid = self.app.create_project('Frozen public snippets')['project_id']
        graph = {'concepts':[{'id':'action','name':'动作条件动力学','terms':['world model'],'hint':2}],
                 'prereqs':[], 'targets':['action']}
        self.app.route_save(pid, graph=graph)
        quote = 'The model predicts future video conditioned on actions.'
        self.app.store.upsert_papers([{'key':'frozen','title':'Action prediction study','abstract':quote,
                                      'published':'2026-09-01'}], project_id=pid)
        self.app.record_feedback('frozen','useful',project_id=pid)
        def reply(op, messages, **kwargs):
            body = json.loads(messages[-1]['content'])
            body['papers']['p1']['snippets']['p1.a99'] = {'field':'abstract','start':0,'end':len(quote),'text':quote}
            messages[-1]['content'] = json.dumps(body)
            item = {'papers':['p1'],'verdict':'covered','nearest':'c1','reason':'Changed table',
                    'evidence':{'p1':{'snippet':'p1.a99','type':'unknown'}}}
            return {'ok':True,'content':json.dumps({'results':[item]}),'usage':{'total_tokens':10}}
        with mock.patch.object(self.app.gateway,'call',side_effect=reply):
            out = self.app.route_direction_judge(pid)
        self.assertFalse(out['complete']); self.assertEqual(out['processed'],0)
        self.assertEqual(out['results'][0]['error_code'],'invalid_snippet_reference')
        self.assertEqual(len(self.app._pending_growth(pid)),1)

    def test_bounded_public_window_recovers_positive_and_keeps_literal_provenance(self):
        for name, terms, quote, obj, treatment, scope in [
                ('Interface resistance', ['interfacial resistance'],
                 'Interfacial resistance at lithium metal/sulfide interface is measured',
                 'lithium metal', '', 'sulfide lithium metal interface'),
                ('PD-1 resistance', ['PD-1 resistance'],
                 'NSCLC PD-1 resistance was studied in vitro', 'NSCLC', 'PD-1', 'NSCLC PD-1 resistance')]:
            graph = {'concepts': [{'id': 'task', 'name': name, 'terms': terms}], 'prereqs': [], 'targets': ['task']}
            source = {'key': 'positive', 'title': 'Public paper with a long generic background title ' * 3,
                      'abstract': 'General introduction. ' * 25 + quote + '. More background.'}
            selected = ai_evidence.fragments(source, graph, scope)
            self.assertLessEqual(len(selected['title']), 80); self.assertLessEqual(len(selected['abstract']), 180)
            self.assertIn(quote, selected['abstract']); self.assertGreater(selected['abstract_start'], 180)
            item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Explicit visible task',
                    'evidence': [{'paper': 'p1', 'quote': quote, 'object': obj, 'treatment': treatment, 'type': 'unknown'}]}
            out, error = growthproposal.validate_result(item, [source], graph, [], fixed_scope=scope)
            self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'covered')
            evidence = out['source_evidence'][0]
            self.assertEqual(source[evidence['field']][evidence['start']:evidence['end']], quote)
        self.assertTrue(ai_evidence.term_match('lithium metal interface', 'Interface between Lithium Metal and sulfide'))
        self.assertFalse(ai_evidence.term_match('lithium metal interface', 'Lithium metal is present. Interface is elsewhere.'))
        self.assertFalse(ai_evidence.term_match('lithium metal interface', 'Liquid lithium interface'))
        self.assertFalse(ai_evidence.term_match('lithium metal interface', 'lithium\n\nmetal interface'))
        self.assertFalse(ai_evidence.term_match('lithium metal interface', 'lithium. Metal interface'))
        self.assertFalse(ai_evidence.term_match('lithium metal interface', 'lithium' + ' ' * 90 + 'metal interface'))
        self.assertTrue(ai_evidence.term_match('lithium metal interface', 'lithium\nmetal interface'))
        graph = {'concepts': [{'id': 'p', 'name': 'PD-1 resistance', 'terms': ['PD-1']}], 'prereqs': [], 'targets': ['p']}
        source = {'title': 'NSCLC\n\nPD-1 resistance', 'abstract': ''}
        citation = {'paper': 'p1', 'quote': source['title'], 'object': 'NSCLC', 'treatment': 'PD-1', 'type': 'unknown'}
        self.assertIsNone(ai_evidence.source_evidence([citation], ['p1'], [source], graph, 'NSCLC PD-1'))
        for boundary in ('\r\n\r\n', '\f', '\u2029', '\u2028\u2028'):
            text = 'NSCLC' + boundary + 'PD-1 resistance'
            self.assertFalse(ai_evidence.term_match('NSCLC PD-1 resistance', text))
            source = {'title': text, 'abstract': ''}
            citation['quote'] = text
            self.assertIsNone(ai_evidence.source_evidence([citation], ['p1'], [source], graph, 'NSCLC PD-1'))
            self.assertFalse(ai_evidence.PARAGRAPH.search(ai_evidence.fragments(source, graph, 'NSCLC PD-1')['title']))
        source = {'title': '', 'abstract': ('Background.\n\n' * 129) + 'NSCLC\n\nPD-1 resistance'}
        self.assertNotIn('PD-1', ai_evidence.fragments(source, graph, 'NSCLC PD-1')['abstract'])

    def test_growth_contract_excludes_join_without_pending_directions(self):
        graph = {'concepts': [{'id': 'public-task', 'name': 'Planning', 'terms': ['planning']}],
                 'prereqs': [], 'targets': ['public-task']}
        paper = {'key': 'public-paper', 'title': 'Planning method', 'abstract': 'Planning evidence.'}
        for directions, joins in [([], False), ([{'id': 'pending', 'name': 'Other planning', 'intro': ''}], True)]:
            messages = growthproposal.messages([paper], graph, directions)
            body = json.loads(messages[1]['content'])
            self.assertEqual('join' in body['available_verdicts'], joins)
            self.assertIn('covered必须写nearest为活动c', messages[0]['content'])
            self.assertIn('join仅合已有directions的d，不能用c或同批p', messages[0]['content'])
            self.assertIn('directions为空严禁join', messages[0]['content'])
            invalid = {'papers': ['p1'], 'verdict': 'join', 'direction': 'c1', 'reason': 'Existing task'}
            self.assertEqual(growthproposal.validate_result(invalid, [paper], graph, directions)[1], 'invalid_direction')

    def test_literal_interfacial_adjective_keeps_material_object_relation(self):
        graph = {'concepts': [{'id': 'interface', 'name': 'Lithium metal interface',
                              'terms': ['lithium metal interface', 'interphase']}], 'prereqs': [], 'targets': ['interface']}
        quote = 'high interfacial resistance with Li metal anode'
        source = {'key': 'public', 'title': 'Origin of lithium metal interface resistance', 'abstract': quote}
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Literal interface object',
                'evidence': [{'paper': 'p1', 'quote': quote, 'object': 'interfacial resistance', 'treatment': '', 'type': 'unknown'}]}
        out, error = growthproposal.validate_result(item, [source], graph, [], fixed_scope='sulfide lithium metal interface')
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'covered')
        self.assertTrue(ai_evidence.term_match('lithium metal interface', quote))
        self.assertFalse(ai_evidence.term_match('lithium metal interface', 'interfacial resistance with liquid lithium anode'))
        self.assertFalse(ai_evidence.term_match('lithium metal interface', 'lithium metal bulk conductivity'))
        self.assertFalse(ai_evidence.term_match('lithium metal interface', 'lithium metal. Interfacial resistance'))

    def test_complete_long_literal_relation_fits_existing_fragment_and_output_budget(self):
        quote = 'We studied PD-1 resistance in a cohort of NSCLC patients using molecular and immune evidence from their pretreatment specimens.'
        self.assertGreater(len(quote), 80); self.assertLessEqual(len(quote), 160)
        graph = {'concepts': [{'id': 'scope', 'name': 'PD-1 resistance', 'terms': ['PD-1 resistance']}],
                 'prereqs': [], 'targets': ['scope']}
        source = {'key': 'public', 'title': 'Public cohort', 'abstract': quote}
        item = {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c1', 'reason': 'Observed mechanism',
                'evidence': [{'paper': 'p1', 'quote': quote, 'object': 'NSCLC patients', 'treatment': 'PD-1', 'type': 'observational'}]}
        out, error = growthproposal.validate_result(item, [source], graph, [], fixed_scope='NSCLC PD-1 resistance')
        self.assertIsNone(error); self.assertEqual(out['proposal_type'], 'covered')
        self.assertEqual(out['source_evidence'][0]['quote'], quote)
        self.assertEqual(growthproposal.INPUT_CAP, 8000); self.assertEqual(growthproposal.OUTPUT_CAP, 1000)

    def test_b10_long_guidance_goal_is_sent_whole_without_excerpt_notice_and_original_survives(self):
        goal = 'Learn world model planning. ' * 25 + 'Exclude surgical applications.'
        session = self.app.create_guidance_session('Public draft', goal)
        self.app.gateway = ReplyGateway(json.dumps({'reply': 'Review scope', 'draft': {
            'keywords': ['world model'], 'search_queries': ['world model planning'], 'learning_path': [], 'next_question': ''}}))
        sent = []
        real_call = self.app.gateway.call
        self.app.gateway.call = lambda op, messages, **kw: (sent.append(messages), real_call(op, messages, **kw))[1]
        result = self.app.guidance_turn(session['id'], goal)
        self.assertEqual(result['mode'], 'ai')
        self.assertNotIn('context_limits', result); self.assertNotIn('scope_notice', result)   # nothing is shortened, so nothing is reported
        self.assertEqual(result['session']['draft']['goal'], goal)
        self.assertEqual(json.loads(sent[0][-1]['content'])['goal'], goal)   # the whole goal, including its last sentence, was sent

    def test_guided_session_has_no_message_length_or_turn_limit_but_quick_creation_is_one_call(self):
        response = json.dumps({'reply': 'Review the whole goal', 'draft': {
            'keywords': ['world model'], 'search_queries': ['world model planning'],
            'learning_path': [], 'next_question': ''}})
        reply = {'ok': True, 'content': response, 'usage': {'total_tokens': 10}, 'usd': '0.0001', 'model': 'fake'}
        for mode in ('quick', 'ai_guided'):
            goal = ('Public goal ' * 360)[:4000].strip()   # the longest goal a project holds; far above the old 1200 estimate
            session = self.app.create_guidance_session('Long goal', goal, creation_mode=mode)
            with mock.patch.object(self.app.gateway, 'call', return_value=reply) as call:
                out = self.app.guidance_turn(session['id'], goal)
            self.assertEqual(out['mode'], 'ai'); self.assertNotIn('scope_notice', out)
            self.assertNotIn('context_limits', out)
            self.assertEqual(out['session']['draft']['goal'], goal)
            self.assertEqual(json.loads(call.call_args.args[1][-1]['content'])['goal'], goal)
            if mode == 'ai_guided':
                long_message = 'x' * 5000   # beyond the former 2000-character later-message limit
                with mock.patch.object(self.app.gateway, 'call', return_value=reply) as call:
                    out = self.app.guidance_turn(session['id'], long_message)
                self.assertEqual(out['mode'], 'ai')
                self.assertEqual(json.loads(call.call_args.args[1][-1]['content'])['message'], long_message)
                with mock.patch.object(self.app.gateway, 'call') as call:   # only an empty message is refused
                    with self.assertRaises(ValueError): self.app.guidance_turn(session['id'], '   ')
                call.assert_not_called()
            else:
                with mock.patch.object(self.app.gateway, 'call') as call:
                    with self.assertRaises(ValueError): self.app.guidance_turn(session['id'], 'one more')
                call.assert_not_called()
        self.assertTrue(self.app.create_guidance_session('Long goal', 'x' * 8000)['id'])   # no goal length cap
        with self.assertRaises(ValueError): self.app.create_guidance_session('Invalid', '   ')

    def test_b21_creation_and_revision_keep_only_positive_ordered_brief_quotes(self):
        nodes = [{'id': 'c1', 'name': 'Representation', 'terms': ['representation'], 'why': 'Useful skill'},
                 {'id': 'c2', 'name': 'Planning', 'terms': ['planning'], 'why': 'Dependency from the brief'}]
        for quote, expected in [('Representation is required before Planning.', 1),
                                ('Representation is not required before Planning.', 0),
                                ('Representation before Planning is optional.', 0),
                                ("Representation isn't required before Planning.", 0),
                                ('Representation is never required before Planning.', 0),
                                ('Representation is no prerequisite for Planning.', 0),
                                ('Representation cannot be required before Planning.', 0),
                                ('Planning is required before Representation.', 0),
                                ('Representation before Planning.', 0)]:
            brief = dict(goal='Learn planning', known='', include='', exclude='', structure=quote)
            value = {'concepts': nodes, 'prereqs': {'c2': {'required': ['c1'], 'quote': quote}}, 'targets': ['c2']}
            result = route_revision.parse_creation(json.dumps(value), brief=brief)
            self.assertEqual(len(result['graph']['prereqs']), expected, quote)
            graph = {'concepts': [{'id': n['id'], 'name': n['name'], 'terms': n['terms']} for n in nodes], 'prereqs': [], 'targets': ['c2']}
            reply = {'operations': [{'op': 'add_edge', 'from': 'c1', 'to': 'c2'}],
                     'evidence': [{'from': 'c1', 'to': 'c2', 'quote': quote}]}
            patch, warnings = route_revision.parse_model(json.dumps(reply), brief, graph)
            self.assertEqual(len(patch['operations']), expected, quote)
            self.assertEqual(bool(warnings), expected == 0)
        value['prereqs']['c2']['required'] = ['c99']
        with self.assertRaises(ValueError): route_revision.parse_creation(json.dumps(value), brief=brief)

    def test_optional_unproved_edge_does_not_require_hard_edge_why(self):
        nodes = [{'id': 'c1', 'name': 'Representation', 'terms': ['representation'], 'why': ''},
                 {'id': 'c2', 'name': 'Planning', 'terms': ['planning'], 'why': ''}]
        optional = 'Representation before Planning is optional.'
        brief = dict(goal='Learn planning', known='', include='', exclude='', structure=optional)
        value = {'concepts': nodes, 'prereqs': {'c2': {'required': ['c1'], 'quote': optional}}, 'targets': ['c2']}
        result = route_revision.parse_creation(json.dumps(value), brief=brief)
        self.assertEqual(result['graph']['prereqs'], [])
        self.assertTrue(result['report']['warnings'])
        proved = 'Representation is required before Planning.'
        brief['structure'] = proved; value['prereqs']['c2']['quote'] = proved
        with self.assertRaises(ValueError): route_revision.parse_creation(json.dumps(value), brief=brief)
        # Original strict graph/reference/topology checks still run first.
        value['prereqs']['c1'] = {'required': ['c2'], 'quote': proved}
        with self.assertRaises(ValueError): route_revision.parse_creation(json.dumps(value), brief=brief)


if __name__ == '__main__': unittest.main()
