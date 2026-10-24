"""Check the real guidance wire against DeepSeek's documented JSON-mode gate.

No live request: temporary App/Gateway state uses a protocol-aware fake transport.
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from app import guidance_contract
from app.gateway import input_bound, request_envelope
from app.service import App

ROOT = Path(__file__).resolve().parents[1]


def json_instruction(body):
    return any('json' in message['content'].casefold()
               for message in body['messages'] if message['role'] in {'system', 'user'})


def provider_reply(request, timeout):
    body = json.loads(request.data)
    if body.get('response_format') == {'type': 'json_object'} and not json_instruction(body):
        raise urllib.error.HTTPError(request.full_url, 400, 'Bad Request', {}, io.BytesIO(
            b'{"error":{"message":"messages must contain the word json for json_object"}}'))
    payload = {'choices': [{'message': {'content': json.dumps({
        'r': 'Choose one application first.',
        'd': {'k': ['world model'], 'q': ['world model planning'], 'a': 'Which application?',
              'c': ['Simulation', 'Robot planning'], 's': 'World model focus', 'ready': False}})},
        'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 80, 'completion_tokens': 40, 'total_tokens': 120}}
    return io.BytesIO(json.dumps(payload).encode())


class GuidanceJSONProtocolTests(unittest.TestCase):
    def test_actual_guidance_messages_always_instruct_json_in_every_creation_mode(self):
        for english in (False, True):
            for quick in (False, True):
                for long in (False, True):
                    with self.subTest(english=english, quick=quick, long=long):
                        goal = ('World model research' if english else '我想研究世界模型')
                        message = ('Simulation only' if english else '只做仿真，不研究机械结构')
                        if long:
                            goal, message = '中' * 4000, '答' * 2000
                        wire = request_envelope('project_guidance', 'deepseek-flash', 500,
                            guidance_contract.messages(goal, ['world model'], message, english,
                                turn=6, quick=quick, last_question='Which focus?', summary='Simulation only'))
                        self.assertEqual(wire['response_format'], {'type': 'json_object'})
                        self.assertTrue(json_instruction(wire), 'JSON-mode request lacks its required prompt instruction')
                        self.assertIn('Return JSON', wire['messages'][0]['content'])
                        self.assertEqual(wire['max_tokens'], 500)
                        self.assertEqual(wire['thinking'], {'type': 'disabled'})
                        body = json.loads(wire['messages'][-1]['content'])   # long text is sent whole, never an excerpt
                        self.assertEqual((body['goal'], body['message']), (goal, message))
                        self.assertEqual((body['last_question'], body['summary']), ('Which focus?', 'Simulation only'))

    def test_worst_unicode_and_memory_are_all_sent_whole_beside_the_current_answer(self):
        for english in (False, True):
            for quick in (False, True):
                with self.subTest(english=english, quick=quick):
                    args = ('中' * 4000, ['词' * 120] * 20, '答' * 2000, english)
                    plain = guidance_contract.messages(*args, quick=quick)
                    memory = guidance_contract.messages(*args, quick=quick, turn=6,
                        last_question='问' * 500, summary='记' * 500)
                    plain_body, memory_body = [json.loads(messages[-1]['content']) for messages in (plain, memory)]
                    for field in ('goal', 'message', 'keywords'):
                        self.assertEqual(memory_body[field], plain_body[field])
                    self.assertEqual((plain_body['goal'], plain_body['message'], plain_body['keywords']),
                                     ('中' * 4000, '答' * 2000, ['词' * 120] * 20))
                    self.assertNotIn('last_question', plain_body); self.assertNotIn('summary', plain_body)
                    self.assertEqual((memory_body['last_question'], memory_body['summary']), ('问' * 500, '记' * 500))
                    for messages in (plain, memory):
                        wire = request_envelope('project_guidance', 'deepseek-flash', 500, messages)
                        self.assertTrue(json_instruction(wire))
                        self.assertGreater(input_bound(wire), 1200)   # the old estimate no longer shrinks the request
                        self.assertEqual(wire['max_tokens'], 500)

    def test_short_explicit_constraints_remain_in_the_actual_user_message(self):
        goal, message = '世界模型用于机器人规划', '只做仿真，不研究机械结构，每周三小时'
        built = guidance_contract.messages(goal, ['world model'], message,
            last_question='从哪里开始？', summary='不研究机械结构')
        body = json.loads(built[-1]['content'])
        self.assertEqual(body['goal'], goal)
        self.assertEqual(body['message'], message)
        self.assertEqual(body['keywords'], ['world model'])
        self.assertTrue(json_instruction(request_envelope('project_guidance', 'deepseek-flash', 500, built)))

    def test_guidance_prompt_names_its_fields_marks_the_map_as_beta_only_and_forbids_placeholder_copy(self):
        system = guidance_contract.SYSTEM
        self.assertIn('"queries":[]', system)
        self.assertIn('never questions or sentences addressed to the user', system)
        self.assertIn('no placeholders', system)
        self.assertNotIn('graph', system)   # the map is asked for only while the beta map is on (MAP_HINT)
        self.assertIn('graph?concrete goals only', guidance_contract.MAP_HINT)
        self.assertNotIn('"id","name"', system)
        self.assertLessEqual(len(system.encode('utf-8')), 1300)

    def test_overproduction_is_bounded_and_a_question_in_queries_is_not_kept(self):
        # This test used to expect q:['one?','two?'] to be accepted as queries: the bug the owner reported.
        payload = {'r': '先选一个方向。', 'd': {
            'k': ['one', 'two', 'three', 'four'], 'q': ['one?', 'two?'], 'a': '',
            'c': ['A'], 's': '', 'ready': False}}
        parsed = guidance_contract.parse(json.dumps(payload))
        self.assertEqual(parsed['draft']['keywords'], ['one', 'two', 'three', 'four'])
        self.assertEqual(parsed['draft']['search_queries'], ['one two three four'])
        bad = {'r': '先选一个方向。', 'd': {
            'k': [{'name': 'one'}], 'q': [], 'a': '', 'c': ['A'], 's': '', 'ready': False}}
        with self.assertRaises(ValueError):
            guidance_contract.parse(json.dumps(bad))

    def test_long_string_choices_are_bounded_but_wrong_choice_types_fail(self):
        payload = {'r': '先选一个方向。', 'd': {
            'k': [], 'q': [], 'a': '', 'c': ['x' * 80], 's': '', 'ready': False}}
        parsed = guidance_contract.parse(json.dumps(payload))
        self.assertEqual(len(parsed['draft']['choices'][0]), 60)
        payload['d']['c'] = [{'label': 'x'}]
        with self.assertRaises(ValueError):
            guidance_contract.parse(json.dumps(payload))

    def test_protocol_control_rejects_a_json_sample_without_the_json_instruction(self):
        missing = request_envelope('project_guidance', 'deepseek-flash', 500,
            [{'role': 'system', 'content': '{"r":"","d":{}}'},
             {'role': 'user', 'content': '我想研究世界模型'}])
        request = urllib.request.Request('https://api.deepseek.com/chat/completions',
            data=json.dumps(missing).encode())
        with self.assertRaises(urllib.error.HTTPError) as raised:
            provider_reply(request, 90)
        self.assertEqual(raised.exception.code, 400)

    def test_app_to_gateway_real_request_passes_protocol_once_without_local_fallback(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ,
                {'DEEPSEEK_API_KEY': 'synthetic-guidance-key', 'PAGETIDE_DEV': '0'}):
            app = App(root=ROOT, data_dir=Path(directory))
            self.addCleanup(app.store.close)
            for english in (False, True):
                (app.data / 'settings.json').write_text(json.dumps(
                    {'language': 'en-US' if english else 'zh-CN'}))
                for mode in ('quick', 'ai_guided'):
                    with self.subTest(english=english, mode=mode):
                        goal = 'World model planning' if english else '我想研究世界模型'
                        session = app.create_guidance_session('Synthetic project', goal, mode)
                        with mock.patch('app.gateway.urllib.request.urlopen', side_effect=provider_reply) as sent:
                            result = app.guidance_turn(session['id'], goal)
                        self.assertEqual(sent.call_count, 1)
                        self.assertEqual(result['mode'], 'ai')
                        wire = json.loads(sent.call_args.args[0].data)
                        self.assertTrue(json_instruction(wire))
                        self.assertEqual(wire['max_tokens'], 384000)   # a conversation asks for the model's longest answer
                        self.assertIsNone(result['reason_code'])
                        self.assertEqual(result['session']['turn_count'], 1)
                        self.assertEqual(result['tokens'], 120)
                        self.assertFalse(result['usage_unknown'])
                        self.assertFalse(result['usage_reserved'])
            entries = app.gateway._entries()
            self.assertEqual(len(entries), 4)
            self.assertTrue(all(entry['status'] == 'reconciled' for entry in entries))

    def test_legacy_app_request_is_rejected_once_and_explicit_retry_uses_the_fixed_instruction(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ,
                {'DEEPSEEK_API_KEY': 'synthetic-guidance-key', 'PAGETIDE_DEV': '0'}):
            app = App(root=ROOT, data_dir=Path(directory))
            self.addCleanup(app.store.close)
            session = app.create_guidance_session('Synthetic project', '我想研究世界模型')
            legacy = guidance_contract.SYSTEM.removeprefix('Return JSON ')
            with mock.patch.object(guidance_contract, 'SYSTEM', legacy), \
                    mock.patch('app.gateway.urllib.request.urlopen', side_effect=provider_reply) as refused:
                failure = app.guidance_turn(session['id'], session['draft']['goal'])
            self.assertEqual(refused.call_count, 1)
            self.assertEqual(failure['mode'], 'local')
            self.assertEqual(failure['session']['turn_count'], 0)
            self.assertFalse(failure['usage_unknown'])
            self.assertFalse(failure['usage_reserved'])
            self.assertEqual(app.gateway._entries()[0]['status'], 'released')
            with mock.patch('app.gateway.urllib.request.urlopen', side_effect=provider_reply) as accepted:
                success = app.guidance_turn(session['id'], '', retry=True)
            self.assertEqual(accepted.call_count, 1)
            self.assertEqual(success['mode'], 'ai')
            self.assertEqual(success['session']['turn_count'], 1)
            self.assertEqual(success['tokens'], 120)

    def test_long_app_goal_and_answer_keep_originals_and_are_sent_whole_without_excerpt_notice(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ,
                {'DEEPSEEK_API_KEY': 'synthetic-guidance-key', 'PAGETIDE_DEV': '0'}):
            app = App(root=ROOT, data_dir=Path(directory))
            self.addCleanup(app.store.close)
            (app.data / 'settings.json').write_text(json.dumps({'language': 'en-US'}))
            goal, answer = '中' * 4000, '答' * 2000
            session = app.create_guidance_session('Synthetic project', goal)
            with mock.patch('app.gateway.urllib.request.urlopen', side_effect=provider_reply) as sent:
                app.guidance_turn(session['id'], goal)
                result = app.guidance_turn(session['id'], answer)
            self.assertEqual(sent.call_count, 2)  # Exactly the two explicit turns above.
            self.assertEqual(result['mode'], 'ai')
            self.assertEqual(result['session']['draft']['goal'], goal)
            self.assertEqual(result['session']['transcript'][-2]['content'], answer)
            self.assertNotIn('context_limits', result)   # nothing is shortened, so there is nothing to report
            self.assertNotIn('scope_notice', result)
            wire = json.loads(sent.call_args.args[0].data)
            self.assertTrue(json_instruction(wire))
            body = json.loads(wire['messages'][-1]['content'])
            self.assertEqual((body['goal'], body['message']), (goal, answer))
            self.assertGreater(input_bound(wire), 1200)   # the old estimate is not an admission limit
            self.assertEqual(wire['max_tokens'], 384000)

    def test_registered_system_text_matches_the_actual_model_instruction(self):
        registered = (ROOT / 'prompts/project-guidance.md').read_text()
        self.assertIn(guidance_contract.SYSTEM, registered)
        self.assertIn('Return JSON', guidance_contract.SYSTEM)


if __name__ == '__main__':
    unittest.main()
