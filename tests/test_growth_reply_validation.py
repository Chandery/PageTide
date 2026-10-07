"""Sanitized real reply shapes; no live provider or user data in fixtures."""
import json
from test_route_growth import Fixture, reply, new
from app import growthproposal


class GrowthReplyValidationTests(Fixture):
    def queue(self, count=6):
        for i in range(count):
            self.add(f'b{i}', f'Synthetic paper {i}', 'Public synthetic abstract', 'synthetic')
            self.say((f'b{i}', 'useful'))

    def topic_groups(self, number):
        return [
            {**new(['p1'], name=f'Task {number}'), 'verdict': 'new_task', 'parent': 'c2',
             'needs': ['c1', 'c2'], 'direction': '具身智能'},
            {'papers': ['p2'], 'verdict': 'covered', 'nearest': 'c2'},
            {**new(['p3'], name=f'Branch {number}'), 'verdict': 'new_branch', 'direction': '具身智能'},
        ]

    def test_real_shape_display_labels_preserve_all_six_and_continue_second_batch(self):
        self.queue()
        calls = []
        def respond(operation, messages, dry_run=False):
            calls.append(messages)
            return reply(self.topic_groups(len(calls)))
        self.app.gateway.call = respond
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['complete'], out['judges_left']), (6, 0, True, 9))
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(self.app._directions_store(self.pid)['directions']), 4)
        self.assertTrue(all(d['proposal_type'] in ('new_task', 'new_branch')
                            for d in self.app._directions_store(self.pid)['directions']))

    def test_six_supplementary_papers_can_all_cover_without_any_new_direction(self):
        self.queue()
        before = self.app.route_get(self.pid)['graph']
        calls = []
        def respond(operation, messages, dry_run=False):
            calls.append(messages)
            return reply([{'papers': ['p1', 'p2', 'p3'], 'verdict': 'covered', 'nearest': 'c2',
                           'reason': 'Different methods supplement the same learning objective.'}])
        self.app.gateway.call = respond
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['complete']), (6, 0, True))
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.app._directions_store(self.pid)['directions'], [])
        self.assertEqual(self.app.route_get(self.pid)['graph'], before)

    def test_six_papers_for_one_learning_task_share_one_proposal_across_batches(self):
        self.queue()
        before = self.app.route_get(self.pid)['graph']
        calls = []
        def respond(operation, messages, dry_run=False):
            body = json.loads(messages[1]['content'])
            calls.append(body)
            if len(calls) == 1:
                return reply([new(['p1', 'p2', 'p3'], name='Reusable learning capability')])
            self.assertEqual(list(body['directions']), ['d1'])
            return reply([{'papers': ['p1', 'p2', 'p3'], 'verdict': 'join', 'direction': 'd1',
                           'reason': 'Additional evidence for the same learning objective.'}])
        self.app.gateway.call = respond
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['complete']), (6, 0, True))
        stored = self.app._directions_store(self.pid)['directions']
        self.assertEqual(len(stored), 1)
        self.assertEqual(len(stored[0]['papers']), 6)
        self.assertEqual(self.app.route_get(self.pid)['graph'], before)

    def test_display_label_does_not_choose_join_target_or_alter_topology(self):
        graph = self.app.route_get(self.pid)['graph']
        plain = self.topic_groups(1)[0]
        decorated = growthproposal.validate(plain, [{'key': 'synthetic-private'}], graph, [])
        del plain['direction']
        clean = growthproposal.validate(plain, [{'key': 'synthetic-private'}], graph, [])
        self.assertEqual(decorated, clean)
        self.assertNotIn('direction', decorated)

    def test_new_direction_aliases_local_ids_and_containers_remain_invalid(self):
        graph = self.app.route_get(self.pid)['graph']
        batch = [{'key': 'private-paper-123'}]
        directions = [{'id': 'private-direction-123'}]
        for value in ['d1', 'd999', 'c1', 'p1', '概念c1', 'uses d999 here',
                      batch[0]['key'], graph['concepts'][0]['id'], directions[0]['id'],
                      'prefix private-paper-123', [], {}, None, 0, True, 'x' * 41, '\ud800']:
            with self.subTest(value=repr(value)):
                _, error = growthproposal.validate_result({**new(['p1']), 'direction': value}, batch, graph, directions)
                self.assertEqual(error, 'invalid_direction')

    def test_join_still_requires_this_requests_d_alias(self):
        graph = self.app.route_get(self.pid)['graph']
        for value in ['具身智能', 'd2', 'private-direction-123']:
            _, error = growthproposal.validate_result({'papers': ['p1'], 'verdict': 'join', 'direction': value},
                [{'key': 'private-paper-123'}], graph, [{'id': 'private-direction-123'}])
            self.assertEqual(error, 'invalid_direction')

    def test_partial_invalid_reference_retains_valid_two_and_reports_the_field(self):
        self.queue(6)
        self.gateway(reply([{'papers': ['p1', 'p2'], 'verdict': 'covered', 'nearest': 'c2'},
                            {**new(['p3']), 'direction': 'd999'}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['model_calls']), (2, 4, 1))
        self.assertEqual(out['reply_error_code'], 'invalid_direction')
        self.assertIn('direction', out['reason'])
        bad = out['results'][-1]
        self.assertEqual(len(bad['titles']), 1)
        self.assertEqual(bad['error_code'], 'invalid_direction')

    def test_distinct_json_length_missing_and_duplicate_causes_are_reported(self):
        self.queue(3)
        examples = [
            ({'ok': True, 'content': 'not json'}, 'invalid_json'),
            (reply([]), 'empty_results'),
            ({**reply([]), 'finish_reason': 'length'}, 'truncated_reply'),
            (reply([{'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c2'}]), 'missing_papers'),
            (reply([{'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c2'},
                    {'papers': ['p1'], 'verdict': 'covered', 'nearest': 'c2'}]), 'duplicate_papers'),
        ]
        for response, expected in examples:
            with self.subTest(expected=expected):
                self.app.store.set_setting(f'route_directions_{self.pid}', {})
                self.gateway(response)
                out = self.app.route_direction_judge(self.pid)
                self.assertEqual(out['reply_error_code'], expected)
                self.assertTrue(out['reason'].startswith(growthproposal.reply_reason(expected)))

    def test_cycle_is_not_fixed_by_dropping_display_labels(self):
        self.queue(3)
        self.gateway(reply([{**new(['p1', 'p2', 'p3']), 'verdict': 'missing_prerequisite',
                             'needs': ['c2'], 'required_by': ['c2'], 'direction': '具身智能'}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['reply_error_code']), (0, 3, 'invalid_topology'))
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'], [])

    def test_nullable_prose_remains_invalid_with_specific_reason(self):
        self.queue(3)
        self.gateway(reply([{'papers': ['p1', 'p2', 'p3'], 'verdict': 'covered', 'nearest': 'c2', 'intro': None}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual(out['reply_error_code'], 'invalid_intro')
        self.assertIn('简介', out['reason'])

    def test_uncertain_real_reply_with_valid_nearby_context_is_not_coverage(self):
        self.queue()
        before = self.app.route_get(self.pid)['graph']
        calls = []
        def respond(operation, messages, dry_run=False):
            calls.append(messages)
            return reply([{'papers': ['p1', 'p2'], 'verdict': 'covered', 'nearest': 'c2'},
                          {'papers': ['p3'], 'verdict': 'unclear', 'nearest': 'c1',
                           'reason': 'There is insufficient evidence to identify a matching learning capability.'}])
        self.app.gateway.call = respond
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['complete'], len(calls)), (6, 0, True, 2))
        uncertain = [r for r in out['results'] if r['verdict'] == 'unclear']
        self.assertEqual(len(uncertain), 2)
        self.assertTrue(all(not r.get('nearest') and not r.get('direction') for r in uncertain))
        self.assertEqual(self.app.route_get(self.pid)['graph'], before)
        self.assertEqual(self.app._directions_store(self.pid)['directions'], [])

    def test_uncertain_context_does_not_admit_unknown_or_malformed_references(self):
        graph = self.app.route_get(self.pid)['graph']
        for value in ['c999', 'd1', 'p1', 'Unknown node', None, [], {}, 0, '\ud800']:
            with self.subTest(value=repr(value)):
                _, error = growthproposal.validate_result(
                    {'papers': ['p1'], 'verdict': 'unclear', 'nearest': value}, [{'key': 'safe'}], graph, [])
                self.assertEqual(error, 'invalid_nearest')

    def test_real_empty_note_decorations_do_not_stop_complete_batches(self):
        self.queue()
        calls = []
        def respond(operation, messages, dry_run=False):
            calls.append(messages)
            return reply([{**new(['p1', 'p2'], name=f'Independent capability {len(calls)}'),
                           'reason_note': '', 'reason_detail': ''},
                          {'papers': ['p3'], 'verdict': 'unclear', 'nearest': 'c1',
                           'reason': 'Insufficient evidence.'}])
        self.app.gateway.call = respond
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['complete'], len(calls)), (6, 0, True, 2))
        for candidate in self.app._directions_store(self.pid)['directions']:
            self.assertNotIn('reason_note', candidate)
            self.assertNotIn('reason_detail', candidate)
        for item in out['results']:
            self.assertNotIn('reason_note', item)
            self.assertNotIn('reason_detail', item)

    def test_note_compatibility_is_only_two_known_literal_empty_strings(self):
        graph = self.app.route_get(self.pid)['graph']
        for key in ['reason_note', 'reason_detail', 'unknown', 'tool_call']:
            for value in ['c1', 'd1', 'p1', 'explanation', ' ', '\n', None, [], {}, 0, False, '\ud800']:
                with self.subTest(key=key, value=repr(value)):
                    _, error = growthproposal.validate_result({**new(['p1']), key: value}, [{'key': 'safe'}], graph, [])
                    self.assertEqual(error, 'unexpected_fields')
        for key in ['unknown', 'tool_call']:
            _, error = growthproposal.validate_result({**new(['p1']), key: ''}, [{'key': 'safe'}], graph, [])
            self.assertEqual(error, 'unexpected_fields')

    def test_nonempty_note_still_stops_spend_and_keeps_valid_two(self):
        self.queue()
        self.gateway(reply([{'papers': ['p1', 'p2'], 'verdict': 'covered', 'nearest': 'c2'},
                            {**new(['p3']), 'reason_note': 'd1'}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['model_calls']), (2, 4, 1))
        self.assertEqual(out['reply_error_code'], 'unexpected_fields')

    def test_twelve_existing_proposals_do_not_stop_new_distinct_batches(self):
        self.queue(6)
        self.app.store.set_setting(f'route_directions_{self.pid}', {'directions': [
            {'id': f'd-{i}', 'name': f'Existing {i}', 'terms': ['old topic'], 'needs': [], 'papers': [],
             'context': self.app._growth_context(self.pid, []), 'proposal_type': 'new_branch'} for i in range(12)]})
        self.gateway(reply(self.topic_groups(1)))
        # Different names in the second batch ensure this really stores >12.
        count = []
        def response(*args, **kwargs):
            count.append(1)
            return reply(self.topic_groups(len(count)))
        self.app.gateway.call = response
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['complete'], out['model_calls']), (6, 0, True, 2))
        self.assertEqual(len(self.app._directions_store(self.pid)['directions']), 16)
        self.assertLessEqual(len(self.app.route_candidates(self.pid)['candidates']), 5)

    def test_thirteen_originals_and_six_new_proposals_preserve_history_and_hidden_accept(self):
        self.queue(6)
        originals = [
            {'id': f'd-{i}', 'name': f'Existing {i}', 'terms': ['old topic'], 'needs': [], 'papers': [],
             'context': self.app._growth_context(self.pid, []), 'proposal_type': 'new_branch'} for i in range(13)]
        self.app.store.set_setting(f'route_directions_{self.pid}', {'directions': originals})
        calls = []
        def response(operation, messages, **kwargs):
            body = json.loads(messages[1]['content'])
            self.assertLessEqual(len(body['directions']), 3)
            calls.append(messages)
            return reply([new([p], name=f'Proposal {len(calls)}-{i}') for i, p in enumerate(body['papers'])])
        self.app.gateway.call = response
        before = self.app.route_get(self.pid)['graph']
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['complete'], out['model_calls']), (6, 0, True, 2))
        stored = self.app._directions_store(self.pid)['directions']
        self.assertEqual(stored[:13], originals)
        self.assertEqual(len(stored), 19)
        self.assertEqual(self.app.route_get(self.pid)['graph'], before)
        target = stored[-1]['id']
        self.assertNotIn(target, [d['id'] for d in self.app.route_candidates(self.pid)['candidates']])
        accepted = self.app.route_candidate_accept(self.pid, target)
        self.assertTrue(any(c.get('candidate') == target for c in accepted['graph']['concepts']))
        self.app.route_undo(self.pid)
        self.assertEqual(self.app.route_get(self.pid)['graph'], before)
        self.assertEqual(self.app._directions_store(self.pid)['directions'], stored)

    def test_repeated_json_keys_cannot_override_real_references(self):
        for content in [
            '{"results":[{"papers":["p1"],"verdict":"new_branch","direction":"d1","direction":"具身智能"}]}',
            '{"results":[{"papers":["p1"],"verdict":"covered","nearest":"c999","nearest":"c1"}]}',
            '{"results":[],"results":[]}',
        ]:
            with self.subTest(content=content):
                self.assertEqual(growthproposal.parse_result(content), ([], 'invalid_json'))

    def test_invalid_utf8_all_prose_and_terms_are_field_errors(self):
        graph = self.app.route_get(self.pid)['graph']
        for field in ['name', 'intro', 'barrier', 'reason', 'terms']:
            with self.subTest(field=field):
                value = ['bad\ud800term'] if field == 'terms' else '\ud800'
                _, error = growthproposal.validate_result({**new(['p1']), field: value}, [{'key': 'safe'}], graph, [])
                self.assertEqual(error, 'invalid_' + field)

    def test_invalid_utf8_group_keeps_two_valid_saves_without_unicode_crash(self):
        self.queue(6)
        self.gateway(reply([{'papers': ['p1', 'p2'], 'verdict': 'covered', 'nearest': 'c2'},
                            {**new(['p3']), 'reason': '\ud800'}]))
        out = self.app.route_direction_judge(self.pid)
        self.assertEqual((out['processed'], out['pending'], out['model_calls']), (2, 4, 1))
        self.assertEqual(out['reply_error_code'], 'invalid_reason')
        self.assertIn('理由', out['reason'])

    def test_prompt_explains_direction_as_join_reference_and_name_for_new(self):
        self.assertIn('direction仅属于join', growthproposal.SYSTEM)
        self.assertIn('绝不填写direction或nearest', growthproposal.SYSTEM)
        self.assertIn('covered必须写nearest为活动c', growthproposal.SYSTEM)
