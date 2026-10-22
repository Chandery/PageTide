"""Owner 2026-10-22: the budget estimates, it never limits the user. Only the model's own window bounds a request;
conversations ask for the model's longest answer; background structured tasks keep their output guard. Synthetic
provider replies, isolated ledgers, no network."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.gateway import Gateway, input_bound
from app.service import App

ROOT = Path(__file__).resolve().parents[1]


def provider_reply(content, prompt=100, completion=20):
    payload = {'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}],
               'usage': {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion}}
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response


class GatewayNoCapsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'synthetic-key', 'PDH_DEV': '0'})
        env.start(); self.addCleanup(env.stop)
        self.gateway = Gateway(root=ROOT, data_dir=Path(self.tmp.name), dev=False)
        self.provider = self.gateway.config['provider']

    def sent(self, operation, messages):
        with mock.patch('app.gateway.urllib.request.urlopen', return_value=provider_reply('{"ok": true}')) as opened:
            out = self.gateway.call(operation, messages)
        return out, opened

    def test_the_model_window_and_output_are_recorded_from_the_provider_docs(self):
        self.assertEqual(self.provider['context_tokens'], 1_000_000)
        self.assertEqual(self.provider['max_output_tokens'], 384_000)
        self.assertEqual(self.gateway.config['policy']['per_call_caps'], 'estimate')

    def test_input_over_the_estimate_is_sent(self):
        estimate = self.gateway.config['operations']['daily_triage']['cap']['input']
        out, opened = self.sent('daily_triage', [{'role': 'user', 'content': 'x' * (estimate * 3)}])
        self.assertTrue(out['ok'], out); opened.assert_called_once()

    def test_conversations_ask_for_the_longest_answer_and_background_keeps_its_guard(self):
        for operation in ('paper_qa', 'selection_translate', 'project_guidance'):
            self.assertTrue(self.gateway.config['operations'][operation].get('conversation'), operation)
            _, opened = self.sent(operation, [{'role': 'user', 'content': 'json question'}])
            self.assertEqual(json.loads(opened.call_args.args[0].data)['max_tokens'], 384_000, operation)
        guard = self.gateway.config['operations']['daily_triage']['cap']['output']
        _, opened = self.sent('daily_triage', [{'role': 'user', 'content': 'json'}])
        self.assertEqual(json.loads(opened.call_args.args[0].data)['max_tokens'], guard)

    def test_a_long_conversation_shrinks_the_answer_room_to_fit_the_window(self):
        self.provider['context_tokens'] = 50_000
        out, opened = self.sent('paper_qa', [{'role': 'user', 'content': 'y' * 30_000}])
        body = json.loads(opened.call_args.args[0].data)
        self.assertTrue(out['ok']); self.assertLessEqual(input_bound(body) + body['max_tokens'], 50_000)

    def test_only_a_request_beyond_the_model_window_is_refused(self):
        self.provider['context_tokens'] = 20_000
        with mock.patch('app.gateway.urllib.request.urlopen') as opened:
            out = self.gateway.call('paper_qa', [{'role': 'user', 'content': 'z' * 25_000}])
        opened.assert_not_called(); self.assertFalse(self.gateway.ledger.exists())
        self.assertTrue(out['input_too_large']); self.assertIn('模型', out['reason'])

    def test_the_reservation_covers_what_is_actually_sent(self):
        estimate = self.gateway.config['operations']['paper_qa']['cap']['input']
        out = self.gateway.call('paper_qa', [{'role': 'user', 'content': 'w' * (estimate * 2)}], dry_run=True)
        self.assertGreater(out['reservation']['input'], estimate)
        self.assertEqual(out['reservation']['output'], 384_000)


class ReaderAndChatNoCapsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'synthetic-key', 'PDH_DEV': '0'})
        env.start(); self.addCleanup(env.stop)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name)); self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project('Public regression')['project_id']
        self.abstract = 'World models predict. ' * 60 + 'END_OF_ABSTRACT'
        self.app.store.upsert_papers([{'key': 'a', 'title': 'Public world model', 'abstract': self.abstract,
                                       'published': '2026-09-01'}], project_id=self.pid)

    def ask(self, **kwargs):
        answer = json.dumps({'answer': 'ok', 'followups': []})
        with mock.patch('app.gateway.urllib.request.urlopen', return_value=provider_reply(answer)) as opened:
            out = self.app.qa('a', project_id=self.pid, **kwargs)
        self.assertTrue(out['ok'], out)
        return json.loads(opened.call_args.args[0].data)

    def test_the_whole_abstract_and_every_retrieved_passage_are_sent(self):
        self.app.save_fulltext('a', [{'page': i, 'text': ' '.join(f'IFP future chunk prediction p{i}s{j}.' for j in range(60))}
                                     for i in range(1, 12)])
        body = self.ask(question='What is IFP future chunk prediction?', selection='中' * 5000)
        text = body['messages'][-1]['content']
        self.assertIn('END_OF_ABSTRACT', text)
        self.assertNotIn('预算', text)
        self.assertEqual(text.count('[第 '), 8)

    def test_the_whole_conversation_history_is_sent(self):
        for i in range(12):
            self.app.store.add_qa('a', 'user' if i % 2 == 0 else 'assistant', f'TURN_{i}', project_id=self.pid)
        body = self.ask(question='next')
        sent = ' '.join(m['content'] for m in body['messages'] if isinstance(m['content'], str))
        for i in range(12):
            self.assertIn(f'TURN_{i}', sent)

    def test_a_long_selection_is_translated(self):
        with mock.patch('app.gateway.urllib.request.urlopen', return_value=provider_reply('译文')) as opened:
            out = self.app.translate('long sentence. ' * 400)
        self.assertTrue(out['ok'], out); opened.assert_called_once()

    def test_project_chat_sends_the_full_goal_and_message(self):
        from app import guidance_contract
        goal, message = 'GOAL ' + '目标' * 400 + ' GOAL_END', 'MSG ' + '消息' * 600 + ' MSG_END'
        body = json.loads(guidance_contract.messages(goal, ['a', 'b'], message, last_question='Q' * 300,
                                                     summary='S' * 400)[-1]['content'])
        self.assertEqual(body['goal'], goal); self.assertEqual(body['message'], message)
        self.assertEqual(body['last_question'], 'Q' * 300); self.assertEqual(body['summary'], 'S' * 400)


if __name__ == '__main__':
    unittest.main()
