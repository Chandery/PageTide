"""Offline contract for five-field requirements and full-Map revision patches."""
import copy
import json
import unittest
from app import route_revision as rr
from app import pathgraph


def graph(count=3):
    return {'concepts': [{'id': f'private-{i}', 'name': f'Concept {i}',
                          'terms': [f'topic {i}'], 'hint': 2, 'origin': 'user',
                          'state': 'active', 'intro': 'My explanation', 'intro_by': 'user'}
                         for i in range(count)],
            'prereqs': [{'from': f'private-{i}', 'to': f'private-{i+1}'} for i in range(count-1)],
            'targets': [f'private-{count-1}']}


def patch(*ops):
    return {'operations': list(ops)}


class BriefTests(unittest.TestCase):
    def test_only_goal_required_and_empty_basics_unknown(self):
        self.assertEqual(rr.validate_brief({'goal': ' 学会世界模型 '}),
                         {'goal': '学会世界模型', 'known': '', 'include': '', 'exclude': '', 'structure': ''})

    def test_each_boundary_rejected_without_silent_truncation(self):
        for field, cap in rr.BRIEF_LIMITS.items():
            value = {'goal': '目标', field: '中' * cap}
            self.assertEqual(len(rr.validate_brief(value)[field]), cap)
            value[field] += '中'
            with self.assertRaises(ValueError): rr.validate_brief(value)

    def test_no_coercion_unknown_fields_or_empty_goal(self):
        for value in [None, [], {}, {'goal': ' '}, {'goal': 1}, {'goal': 'g', 'known': None},
                      {'goal': 'g', 'language': 'English'}]:
            with self.assertRaises(ValueError): rr.validate_brief(value)

    def test_teacher_text_remains_data_and_is_not_evaluated(self):
        teacher = '<script>fetch("secret")</script>\n# 先学概率，再学模型'
        self.assertEqual(rr.validate_brief({'goal': 'g', 'structure': teacher})['structure'], teacher)

    def test_invalid_unicode_rejected_in_every_brief_field(self):
        for field in rr.BRIEF_LIMITS:
            with self.assertRaises(ValueError): rr.validate_brief({'goal': 'g', field: '\ud800text'})


class PatchTests(unittest.TestCase):
    def test_complete_context_has_no_private_ids_or_progress(self):
        source = graph(40)
        source['concepts'][0]['progress_since_feedback_id'] = 99
        view = rr.graph_context(source)
        encoded = json.dumps(view)
        self.assertNotIn('private-', encoded)
        self.assertNotIn('progress_since', encoded)
        self.assertEqual(len(view['concepts']), 40)
        self.assertEqual(view['targets'], ['c40'])
        self.assertEqual(len(view['prereqs']), 39)

    def test_empty_patch_preserves_40_nodes_and_legacy_cutoff(self):
        source = graph(40)
        source['concepts'][0]['progress_since_feedback_id'] = 5
        result = rr.apply_patch(source, patch(), through_feedback_id=99)
        self.assertEqual(len(result['graph']['concepts']), 40)
        self.assertEqual(result['reset'], [])
        self.assertFalse(result['changed'])
        self.assertEqual(result['graph']['concepts'][0]['progress_since_feedback_id'], 5)

    def test_new_nodes_have_fresh_identity_and_cutoff_with_forward_references(self):
        source = graph()
        before = copy.deepcopy(source)
        result = rr.apply_patch(source, patch(
            {'op': 'add_edge', 'from': 'n1', 'to': 'c3'},
            {'op': 'add_node', 'ref': 'n1', 'node': {'name': '潜变量', 'terms': ['潜变量'], 'hint': 3}},
            {'op': 'add_edge', 'from': 'c2', 'to': 'n1'}), through_feedback_id=23)
        self.assertEqual(source, before)
        added = next(c for c in result['graph']['concepts'] if c['name'] == '潜变量')
        self.assertNotIn(added['id'], [c['id'] for c in source['concepts']])
        self.assertEqual(added['progress_since_feedback_id'], 23)
        self.assertIn(added['id'], result['reset'])
        self.assertEqual(len(result['graph']['prereqs']), 4)
        self.assertTrue(result['warnings'])  # hint inversion is warning, not failure

    def test_semantic_change_resets_only_changed_node_and_preserves_human_intro(self):
        result = rr.apply_patch(graph(), patch({'op': 'update_node', 'ref': 'c2',
            'changes': {'terms': ['another task']}}), through_feedback_id=44)
        self.assertEqual(result['reset'], ['private-1'])
        self.assertEqual(result['graph']['concepts'][1]['intro'], 'My explanation')
        self.assertEqual(result['graph']['concepts'][1]['intro_by'], 'user')
        self.assertEqual(result['graph']['concepts'][1]['progress_since_feedback_id'], 44)
        self.assertNotIn('progress_since_feedback_id', result['graph']['concepts'][0])

    def test_hint_change_and_reordered_terms_do_not_reset_mastery(self):
        source = graph()
        source['concepts'][0]['terms'] = ['first', 'second']
        result = rr.apply_patch(source, patch({'op': 'update_node', 'ref': 'c1',
            'changes': {'hint': 4, 'terms': ['second', 'first']}}), through_feedback_id=44)
        self.assertEqual(result['reset'], [])
        self.assertTrue(result['warnings'])

    def test_artificial_intro_overwrite_rejected_not_silently_saved(self):
        with self.assertRaises(ValueError):
            rr.apply_patch(graph(), patch({'op': 'update_node', 'ref': 'c1', 'changes': {'intro': 'AI rewrite'}}))

    def test_delete_target_requires_explicit_valid_replacement(self):
        deletion = {'op': 'remove_node', 'ref': 'c3'}
        for extra in [[], [{'op': 'set_targets', 'refs': []}],
                      [{'op': 'set_targets', 'refs': ['c3']}]]:
            with self.assertRaises(ValueError): rr.apply_patch(graph(), patch(deletion, *extra))
        result = rr.apply_patch(graph(), patch(deletion, {'op': 'set_targets', 'refs': ['c2']}))
        self.assertEqual(result['graph']['targets'], ['private-1'])
        self.assertEqual(result['removed'], ['private-2'])

    def test_split_does_not_reuse_removed_identity(self):
        result = rr.apply_patch(graph(), patch({'op': 'remove_node', 'ref': 'c3'},
            {'op': 'add_node', 'ref': 'n1', 'node': {'name': 'Subtask', 'terms': ['subtask']}},
            {'op': 'set_targets', 'refs': ['n1']}), through_feedback_id=50)
        target = result['graph']['targets'][0]
        self.assertNotEqual(target, 'private-2')
        self.assertEqual(result['reset'], [target])

    def test_explicit_redundant_edges_are_preserved(self):
        result = rr.apply_patch(graph(), patch({'op': 'add_edge', 'from': 'c1', 'to': 'c3'}))
        self.assertEqual(len(result['graph']['prereqs']), 3)

    def test_invalid_and_conflicting_operations_leave_original_unchanged(self):
        cases = [
            [{'op': 'unknown'}], [{'op': 'remove_node', 'ref': 'private-0'}],
            [{'op': 'update_node', 'ref': 'c1', 'changes': {'manual': 'mastered'}}],
            [{'op': 'update_node', 'ref': 'c1', 'changes': {'progress_since_feedback_id': 0}}],
            [{'op': 'update_node', 'ref': 'c1', 'changes': {}}],
            [{'op': 'remove_node', 'ref': 'c1'}, {'op': 'update_node', 'ref': 'c1', 'changes': {'hint': 3}}],
            [{'op': 'remove_node', 'ref': 'c1'}, {'op': 'remove_node', 'ref': 'c1'}],
            [{'op': 'add_edge', 'from': 'c1', 'to': 'c2'}],
            [{'op': 'remove_edge', 'from': 'c1', 'to': 'c3'}],
            [{'op': 'add_edge', 'from': 'c3', 'to': 'c1'}],
            [{'op': 'set_targets', 'refs': ['c2', 'c2']}],
            [{'op': 'set_targets', 'refs': ['c2']}, {'op': 'set_targets', 'refs': ['c3']}],
            [{'op': 'add_node', 'ref': 'c1', 'node': {'name': 'New', 'terms': ['new']}}],
            [{'op': 'add_node', 'ref': 'n1', 'node': {'name': 'x'*61, 'terms': ['new']}}],
            [{'op': 'add_node', 'ref': 'n1', 'node': {'name': 'New', 'terms': ['new'], 'hint': True}}],
        ]
        for operations in cases:
            with self.subTest(operations=operations):
                source = graph(); before = copy.deepcopy(source)
                with self.assertRaises(ValueError): rr.apply_patch(source, patch(*operations))
                self.assertEqual(source, before)

    def test_limits_and_bad_feedback_cutoff(self):
        with self.assertRaises(ValueError):
            rr.apply_patch(graph(40), patch({'op': 'add_node', 'ref': 'n1', 'node': {'name': 'More', 'terms': ['more']}}))
        source = graph(5)
        source['prereqs'] = []
        with self.assertRaises(ValueError):
            rr.apply_patch(source, patch(*[{'op': 'add_edge', 'from': f'c{i}', 'to': 'c5'} for i in range(1,5)]))
        for value in [True, -1, '4', 2**64]:
            with self.assertRaises(ValueError): rr.apply_patch(graph(), patch(), through_feedback_id=value)

    def test_existing_cutoff_never_moves_backwards(self):
        source = graph(); source['concepts'][0]['progress_since_feedback_id'] = 99
        result = rr.apply_patch(source, patch({'op': 'update_node', 'ref': 'c1', 'changes': {'name': 'Another'}}), through_feedback_id=2)
        self.assertEqual(result['graph']['concepts'][0]['progress_since_feedback_id'], 99)

    def test_parse_is_strict_and_length_is_always_rejected(self):
        valid = '{"operations":[]}'
        self.assertEqual(rr.parse(valid), patch())
        for value in [valid, '{"operations":[{"op":"remove_node","ref":"c1"}]}']:
            with self.assertRaises(ValueError): rr.parse(value, finish_reason='length')
        for value in ['```json\n'+valid+'\n```', '{}', '{"operations":[],"operations":[]}',
                      '{"operations":[],"other":1}', '{"operations":null}', '[]', valid+' ignored']:
            with self.assertRaises(ValueError): rr.parse(value)

    def test_parser_and_operations_have_resource_bounds(self):
        with self.assertRaises(ValueError): rr.parse(' ' * (rr.MAX_RESPONSE_BYTES + 1))
        with self.assertRaises(ValueError): rr.parse('中' * (rr.MAX_RESPONSE_BYTES // 3 + 1))
        with self.assertRaises(ValueError): rr.apply_patch(graph(), patch(*([{}] * 401)))

    def test_full_graph_at_fan_in_bound_keeps_every_edge(self):
        source = graph(40)
        source['prereqs'] = [{'from': f'private-{j}', 'to': f'private-{i}'}
                             for i in range(1, 40) for j in range(max(0, i-3), i)]
        result = rr.apply_patch(source, patch())
        self.assertEqual(len(result['graph']['prereqs']), 114)
        self.assertEqual(len(rr.graph_context(source)['prereqs']), 114)

    def test_root_and_nested_duplicate_json_keys_and_constants_are_refused(self):
        for text in ['{"operations":[{"op":"remove_node","ref":"c1","ref":"c2"}]}',
                     '{"operations":[{"op":"update_node","ref":"c1","changes":{"hint":NaN}}]}',
                     '{"operations":[{"op":"update_node","ref":"c1","changes":{"hint":Infinity}}]}']:
            with self.assertRaises(ValueError): rr.parse(text)

    def test_split_new_identity_has_no_old_human_metadata(self):
        source = graph()
        result = rr.apply_patch(source, patch({'op': 'remove_node', 'ref': 'c3'},
            {'op': 'add_node', 'ref': 'n1', 'node': {'name': 'First subtask', 'terms': ['first'], 'intro': 'AI draft'}},
            {'op': 'add_node', 'ref': 'n2', 'node': {'name': 'Second subtask', 'terms': ['second']}},
            {'op': 'set_targets', 'refs': ['n1', 'n2']}), through_feedback_id=50)
        added = [c for c in result['graph']['concepts'] if c['id'] in result['added']]
        self.assertEqual(len(added), 2)
        self.assertEqual(added[0]['intro_by'], 'ai')
        self.assertNotIn('intro', added[1])
        self.assertTrue(all(c['progress_since_feedback_id'] == 50 for c in added))

    def test_merge_requires_new_identity_instead_of_overwriting_old_task(self):
        source = graph()
        result = rr.apply_patch(source, patch({'op': 'remove_node', 'ref': 'c2'},
            {'op': 'remove_node', 'ref': 'c3'},
            {'op': 'add_node', 'ref': 'n1', 'node': {'name': 'Combined task', 'terms': ['combined']}},
            {'op': 'add_edge', 'from': 'c1', 'to': 'n1'},
            {'op': 'set_targets', 'refs': ['n1']}), through_feedback_id=75)
        self.assertEqual(len(result['graph']['concepts']), 2)
        self.assertEqual(result['reset'], result['added'])
        self.assertEqual(set(result['removed']), {'private-1', 'private-2'})

    def test_legacy_save_does_not_accept_client_authored_cutoff(self):
        source = graph(); source['concepts'][0]['progress_since_feedback_id'] = 99
        self.assertNotIn('progress_since_feedback_id', pathgraph.validate(source)['concepts'][0])
        self.assertEqual(pathgraph.validate(source, explicit=True)['concepts'][0]['progress_since_feedback_id'], 99)

    def test_existing_cutoff_is_strictly_bounded(self):
        for value in [True, -1, '4', 2**64]:
            source = graph(); source['concepts'][0]['progress_since_feedback_id'] = value
            with self.assertRaises(ValueError): rr.apply_patch(source, patch())

    def test_legacy_needs_review_target_can_be_repaired_explicitly(self):
        source = graph(); source['concepts'][-1]['state'] = 'archived'
        self.assertEqual(rr.graph_context(source)['targets'], ['c3'])
        result = rr.apply_patch(source, patch({'op': 'set_targets', 'refs': ['c2']}))
        self.assertEqual(result['graph']['targets'], ['private-1'])
        source['targets'] = []
        result = rr.apply_patch(source, patch({'op': 'set_targets', 'refs': ['c1']}))
        self.assertEqual(result['graph']['targets'], ['private-0'])
        with self.assertRaises(ValueError): rr.apply_patch(source, patch())

    def test_invalid_source_shape_always_reports_value_error(self):
        for value in [None, [], {}, {'concepts': None}, {'concepts': 3}, {'concepts': {}, 'prereqs': []}]:
            with self.assertRaises(ValueError): rr.graph_context(value)
            with self.assertRaises(ValueError): rr.apply_patch(value, patch())

    def test_deeply_nested_untrusted_node_field_is_not_copied(self):
        text = '{"operations":[{"op":"update_node","ref":"c1","changes":{"name":' + '['*500 + '0' + ']'*500 + '}}]}'
        payload = rr.parse(text)
        source = graph(); before = copy.deepcopy(source)
        with self.assertRaises(ValueError): rr.apply_patch(source, payload)
        self.assertEqual(source, before)

    def test_invalid_unicode_node_fields_never_reach_http_serialization(self):
        for field in ['name', 'intro', 'why', 'terms']:
            changes = {field: ['\ud800text'] if field == 'terms' else '\ud800text'}
            source = graph(); source['concepts'][0]['intro_by'] = 'ai'
            payload = rr.parse(json.dumps(patch({'op': 'update_node', 'ref': 'c1', 'changes': changes})))
            with self.assertRaises(ValueError): rr.apply_patch(source, payload)
        source = graph(); source['concepts'][0]['name'] = '\ud800text'
        with self.assertRaises(ValueError): rr.graph_context(source)

    def test_inactive_target_and_unknown_edges_are_rejected(self):
        source = graph(); source['concepts'][-1]['state'] = 'archived'
        with self.assertRaises(ValueError): rr.apply_patch(source, patch())
        source = graph(); source['prereqs'].append({'from': 'missing', 'to': 'private-1'})
        with self.assertRaises(ValueError): rr.graph_context(source)


if __name__ == '__main__': unittest.main()
