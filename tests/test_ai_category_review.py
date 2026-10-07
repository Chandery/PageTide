"""Offline, synthetic category-review privacy, schema and failure regressions."""
import copy
import json
import unittest
from pathlib import Path

from app import category_review as cr


def directories():
    return [{'id': 'private-world', 'name': 'World Models', 'parent_id': None},
            {'id': 'private-video', 'name': '视频世界模型', 'parent_id': 'private-world'},
            {'id': 'private-robot', 'name': '机器人', 'parent_id': None}]


def papers():
    return [{'key': 'private-paper', 'title': 'Video world models for robot control',
             'abstract': 'A video world model predicts future observations.',
             'categories': ['private-world', 'private-video']}]


def keep(context):
    categories = context['categories']
    aliases = {item['id']: 'c' + str(i + 1) for i, item in enumerate(categories)}
    return {'categories': [{'id': 'c' + str(i + 1), 'action': 'keep', 'reason': '研究方向合理'}
                           for i in range(len(categories))],
            'papers': [{'id': 'p' + str(i + 1), 'categories': [aliases[c] for c in item['categories']],
                        'reason': '标题摘要支持该方向'} for i, item in enumerate(context['papers'])],
            'new_categories': []}


def encoded(value):
    return json.dumps(value, ensure_ascii=False)


class PreparationTests(unittest.TestCase):
    def test_only_public_bounded_fragments_and_request_local_aliases_sent(self):
        ds, ps = directories(), papers()
        ds[0].update(note='secret category note', owner='secret-owner', color='secret-color')
        ps[0].update(note='secret note', feedback='private feedback', pdf_path='/secret/path',
                     protected=True, source_id='secret-source')
        before = copy.deepcopy((ds, ps))
        result = cr.prepare(ds, ps)
        wire = encoded(result['messages'])
        for private in ['private-', 'secret', 'feedback', 'pdf_path', 'protected', 'source_id']:
            self.assertNotIn(private, wire)
        body = json.loads(result['messages'][1]['content'])
        self.assertEqual(body['categories'][1]['parent'], 'c1')
        self.assertEqual(body['papers'][0]['categories'], ['c1', 'c2'])
        self.assertEqual((ds, ps), before)

    def test_full_existing_labels_and_explicit_title_abstract_fragment_flags(self):
        ds, ps = directories(), papers()
        ds[0]['name'] = '旧类别' * 40
        ps[0]['title'] = 'T' * 81
        ps[0]['abstract'] = 'A' * 161
        result = cr.prepare(ds, ps)
        body = json.loads(result['messages'][1]['content'])
        self.assertEqual(body['categories'][0]['name'], ds[0]['name'])
        self.assertEqual(body['papers'][0]['title'], 'T' * 80)
        self.assertEqual(body['papers'][0]['abstract'], 'A' * 160)
        self.assertTrue(body['papers'][0]['title_truncated'])
        self.assertTrue(body['papers'][0]['abstract_truncated'])

    def test_exact_fragment_boundaries_and_none_abstract(self):
        ps = papers()
        ps[0].update(title='T' * 80, abstract='A' * 160)
        body = json.loads(cr.prepare(directories(), ps)['messages'][1]['content'])
        self.assertFalse(body['papers'][0]['title_truncated'])
        self.assertFalse(body['papers'][0]['abstract_truncated'])
        ps[0]['abstract'] = None
        self.assertEqual(json.loads(cr.prepare(directories(), ps)['messages'][1]['content'])['papers'][0]['abstract'], '')

    def test_public_unsent_tail_changes_local_fingerprint(self):
        ps = papers()
        ps[0]['abstract'] = 'A' * 160 + 'tail1'
        before = cr.prepare(directories(), ps)
        ps[0]['abstract'] = 'A' * 160 + 'tail2'
        after = cr.prepare(directories(), ps)
        self.assertEqual(before['messages'], after['messages'])
        self.assertNotEqual(before['context']['fingerprint'], after['context']['fingerprint'])

    def test_complete_wire_accounting_matches_gateway_with_framing(self):
        result = cr.prepare(directories(), papers())
        envelope = {'model': 'deepseek-flash', 'thinking': {'type': 'disabled'},
                    'max_tokens': 2000, 'messages': result['messages']}
        self.assertEqual(cr.message_estimate(result['messages']),
                         len(json.dumps(envelope, ensure_ascii=False).encode('utf-8')) + 256)
        self.assertLessEqual(cr.message_estimate(result['messages']), 8000)

    def test_complete_oversize_directory_fails_without_cutting_any_categories(self):
        ds = [{'id': 'private-' + str(i), 'name': str(i) + '中' * 110, 'parent_id': None} for i in range(60)]
        with self.assertRaisesRegex(ValueError, '输入预算'):
            cr.prepare(ds, [])
        self.assertEqual(len(ds), 60)

    def test_count_limits_no_silent_drop_and_exact_sixty_twelve_supported(self):
        ds = [{'id': 'private-' + str(i), 'name': str(i), 'parent_id': None} for i in range(60)]
        ps = [{'key': 'paper-' + str(i), 'title': '', 'abstract': '', 'categories': []} for i in range(12)]
        result = cr.prepare(ds, ps)
        body = json.loads(result['messages'][1]['content'])
        self.assertEqual((len(body['categories']), len(body['papers'])), (60, 12))
        with self.assertRaises(ValueError): cr.prepare(ds + [{'id': 'extra', 'name': 'Extra'}], ps)
        with self.assertRaises(ValueError): cr.prepare(ds, ps + [{'key': 'extra'}])

    def test_nonempty_profile_never_transmitted(self):
        for value in [{'name': 'private-project'}, {'goal': 'private-goal'}, {'language': 'en-US'}, [], 'secret']:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): cr.prepare(directories(), papers(), value)
        self.assertEqual(cr.prepare([], [], {})['messages'], cr.prepare([], [])['messages'])

    def test_unknown_duplicate_memberships_and_duplicate_papers_fail(self):
        for memberships in [['unknown'], ['private-world', 'private-world'], [None], 'private-world']:
            ps = papers(); ps[0]['categories'] = memberships
            with self.subTest(memberships=memberships):
                with self.assertRaises(ValueError): cr.prepare(directories(), ps)
        with self.assertRaises(ValueError): cr.prepare(directories(), papers() * 2)

    def test_unknown_parent_cycles_duplicate_ids_and_invalid_labels_fail(self):
        bads = [directories() + [dict(directories()[0])],
                [{'id': 'a', 'name': 'A', 'parent_id': 'missing'}],
                [{'id': 'a', 'name': 'A', 'parent_id': 'a'}],
                [{'id': 'a', 'name': 'A', 'parent_id': 'b'}, {'id': 'b', 'name': 'B', 'parent_id': 'a'}],
                [{'id': 'a', 'name': '中' * 121}], [{'id': 'a', 'name': ' '}]]
        for ds in bads:
            with self.subTest(ds=ds):
                with self.assertRaises(ValueError): cr.prepare(ds, [])

    def test_invalid_unicode_fails_before_any_budget_or_model_call(self):
        for field in ['id', 'name', 'parent_id']:
            ds = directories(); ds[0][field] = '\ud800'
            with self.subTest(field=field):
                with self.assertRaises(ValueError): cr.prepare(ds, papers())
        for field in ['key', 'title', 'abstract']:
            ps = papers(); ps[0][field] = 'safe' * 100 + '\ud800'
            with self.subTest(field=field):
                with self.assertRaises(ValueError): cr.prepare(directories(), ps)

    def test_public_metadata_values_are_not_silently_coerced_to_empty_text(self):
        for field in ['title', 'abstract']:
            for value in [0, False, [], {}]:
                ps = papers(); ps[0][field] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError): cr.prepare(directories(), ps)


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.prepared = cr.prepare(directories(), papers())
        self.context = self.prepared['context']
        self.reply = keep(self.context)

    def parse(self, value=None, context=None, **kwargs):
        return cr.parse(encoded(self.reply if value is None else value), context or self.context, **kwargs)

    def test_complete_keep_reply_returns_private_ids_locally_and_preserves_inputs(self):
        original = copy.deepcopy((self.context, self.reply))
        plan = self.parse()
        self.assertEqual(plan['categories'][0]['id'], 'private-world')
        self.assertEqual(plan['papers'][0]['key'], 'private-paper')
        self.assertEqual(plan['papers'][0]['categories'], ['private-world', 'private-video'])
        self.assertEqual(plan['fingerprint'], self.context['fingerprint'])
        self.assertEqual((self.context, self.reply), original)

    def test_exact_bilingual_synonyms_merge_and_retained_children_redirect(self):
        ds = directories() + [{'id': 'private-duplicate', 'name': '世界模型', 'parent_id': None},
                               {'id': 'private-child', 'name': 'Other child', 'parent_id': 'private-duplicate'}]
        context = cr.prepare(ds, papers())['context']
        reply = keep(context)
        reply['categories'][3] = {'id': 'c4', 'action': 'merge', 'target': 'c1', 'reason': '中英文完全同义'}
        plan = self.parse(reply, context)
        self.assertEqual(plan['categories'][3]['target'], 'private-world')
        self.assertEqual(plan['categories'][4]['action'], 'keep')

    def test_distinct_related_directions_are_not_collapsed_deterministically(self):
        ds = [{'id': 'private-a', 'name': '具身智能'}, {'id': 'private-b', 'name': '机器人'}]
        context = cr.prepare(ds, [])['context']
        plan = self.parse(keep(context), context)
        self.assertEqual([c['action'] for c in plan['categories']], ['keep', 'keep'])

    def test_merge_different_known_research_concepts_rejects_relatedness_as_synonym(self):
        for source, target in [('机器人', '具身智能'), ('机器人', '世界模型'),
                               ('视频世界模型', '世界模型')]:
            context = cr.prepare([{'id': 'a', 'name': source}, {'id': 'b', 'name': target}],
                                 [{'key': 'p', 'title': 'Public paper', 'categories': ['a']}])['context']
            reply = keep(context)
            reply['categories'][0] = {'id': 'c1', 'action': 'merge', 'target': 'c2', 'reason': '关联方向'}
            reply['papers'][0]['categories'] = ['c2']
            with self.subTest(source=source, target=target):
                with self.assertRaisesRegex(ValueError, '不同研究概念'): self.parse(reply, context)

    def test_known_merge_compares_final_renamed_target_identity(self):
        context = cr.prepare([{'id': 'a', 'name': '机器人'}, {'id': 'b', 'name': '具身智能'}], [])['context']
        reply = keep(context)
        reply['categories'][0] = {'id': 'c1', 'action': 'merge', 'target': 'c2', 'reason': '统一名称'}
        reply['categories'][1] = {'id': 'c2', 'action': 'rename', 'name': 'Robotics', 'reason': '标准名称'}
        self.assertEqual(self.parse(reply, context)['categories'][0]['target'], 'b')
        reply['categories'][1]['name'] = 'World Models'
        with self.assertRaisesRegex(ValueError, '不同研究概念'): self.parse(reply, context)

    def test_delete_invalid_category_and_explicitly_leave_its_paper_unclassified(self):
        context = cr.prepare([{'id': 'old', 'name': 'Model for Embodied'}],
                             [{'key': 'paper', 'title': 'Unknown topic', 'categories': ['old']}])['context']
        reply = {'categories': [{'id': 'c1', 'action': 'delete', 'reason': '标题残片不能作为方向'}],
                 'papers': [{'id': 'p1', 'categories': [], 'reason': '片段不足，保留论文为未分类'}], 'new_categories': []}
        plan = self.parse(reply, context)
        self.assertEqual(plan['papers'], [{'key': 'paper', 'categories': [], 'reason': '片段不足，保留论文为未分类'}])

    def test_rename_and_add_supported_child_use_canonical_chinese_labels(self):
        self.reply['categories'][0] = {'id': 'c1', 'action': 'rename', 'name': 'World Models', 'reason': '统一名称'}
        self.reply['new_categories'] = [{'id': 'n1', 'name': 'JEPA', 'parent': 'c1', 'reason': '世界模型方法分支'}]
        self.reply['papers'][0]['categories'] = ['n1']
        plan = self.parse()
        self.assertEqual(plan['categories'][0]['name'], '世界模型')
        self.assertEqual(plan['new_categories'][0]['parent_id'], 'private-world')
        self.assertEqual(plan['papers'][0]['categories'], ['n1'])

    def test_new_parent_supported_by_assigned_new_descendant(self):
        self.reply['new_categories'] = [{'id': 'n1', 'name': '新研究方向', 'reason': '研究方向'},
                                        {'id': 'n2', 'name': '子方向', 'parent': 'n1', 'reason': '子方向'}]
        self.reply['papers'][0]['categories'] = ['n2']
        self.assertEqual(len(self.parse()['new_categories']), 2)

    def test_complete_empty_taxonomy_and_unclassified_paper_works(self):
        context = cr.prepare([], [{'key': 'p', 'title': 'Unknown'}])['context']
        reply = keep(context)
        self.assertEqual(self.parse(reply, context)['papers'][0]['categories'], [])

    def test_bad_json_duplicate_fields_nonfinite_and_fenced_response_reject(self):
        invalid = ['{', '```json\n' + encoded(self.reply) + '\n```',
                   '{"categories":[],"categories":[],"papers":[],"new_categories":[]}',
                   encoded(self.reply).replace('"reason": "研究方向合理"', '"reason": NaN', 1),
                   encoded(self.reply).replace('"reason": "研究方向合理"', '"reason": Infinity', 1)]
        for content in invalid:
            with self.subTest(content=content[:40]):
                with self.assertRaises(ValueError): cr.parse(content, self.context)

    def test_length_and_size_and_invalid_content_reject_without_partial_plan(self):
        with self.assertRaisesRegex(ValueError, '截断'): self.parse(finish_reason='length')
        for content in [None, [], {}, '\ud800', ' ' * (cr.MAX_RESPONSE_BYTES + 1)]:
            with self.subTest(kind=type(content)):
                with self.assertRaises(ValueError): cr.parse(content, self.context)

    def test_missing_and_unknown_top_fields_reject(self):
        for field in self.reply:
            value = copy.deepcopy(self.reply); del value[field]
            with self.subTest(field=field):
                with self.assertRaises(ValueError): self.parse(value)
        value = copy.deepcopy(self.reply); value['tool_call'] = 'secret'
        with self.assertRaises(ValueError): self.parse(value)

    def test_every_current_category_and_paper_must_be_reviewed_exactly_once(self):
        for field in ['categories', 'papers']:
            value = copy.deepcopy(self.reply); value[field].pop()
            with self.subTest(field=field):
                with self.assertRaises(ValueError): self.parse(value)
            value = copy.deepcopy(self.reply); value[field].append(value[field][0])
            with self.assertRaises(ValueError): self.parse(value)
            value = copy.deepcopy(self.reply); value[field][0]['id'] = 'unknown'
            with self.assertRaises(ValueError): self.parse(value)

    def test_action_field_allowlist_prevents_tool_and_conflicting_mutations(self):
        for action in [{'id': 'c1', 'action': 'keep', 'reason': 'R', 'name': 'Unexpected'},
                       {'id': 'c1', 'action': 'delete', 'reason': 'R', 'target': 'c3'},
                       {'id': 'c1', 'action': 'rename', 'reason': 'R'},
                       {'id': 'c1', 'action': 'merge', 'reason': 'R'},
                       {'id': 'c1', 'action': 'execute', 'reason': 'R'},
                       {'id': 'c1', 'action': [], 'reason': 'R'}]:
            value = copy.deepcopy(self.reply); value['categories'][0] = action
            with self.subTest(action=action):
                with self.assertRaises(ValueError): self.parse(value)

    def test_unknown_merge_target_self_merge_chains_and_delete_target_reject(self):
        for target in ['c1', 'missing', None]:
            value = copy.deepcopy(self.reply)
            value['categories'][0] = {'id': 'c1', 'action': 'merge', 'target': target, 'reason': 'R'}
            with self.subTest(target=target):
                with self.assertRaises(ValueError): self.parse(value)
        for second in [{'id': 'c3', 'action': 'delete', 'reason': 'R'},
                       {'id': 'c3', 'action': 'merge', 'target': 'c2', 'reason': 'R'}]:
            value = copy.deepcopy(self.reply)
            value['categories'][0] = {'id': 'c1', 'action': 'merge', 'target': 'c3', 'reason': 'R'}
            value['categories'][2] = second
            with self.assertRaises(ValueError): self.parse(value)

    def test_delete_parent_with_surviving_child_and_merge_parent_into_child_reject(self):
        for action in [{'id': 'c1', 'action': 'delete', 'reason': 'R'},
                       {'id': 'c1', 'action': 'merge', 'target': 'c2', 'reason': 'R'}]:
            value = copy.deepcopy(self.reply); value['categories'][0] = action
            with self.subTest(action=action):
                with self.assertRaises(ValueError): self.parse(value)

    def test_new_unknown_parent_cycles_and_orphans_reject(self):
        for parent in ['unknown', 'n1', 2, []]:
            value = copy.deepcopy(self.reply)
            value['new_categories'] = [{'id': 'n1', 'name': '新方向', 'parent': parent, 'reason': 'R'}]
            value['papers'][0]['categories'] = ['n1']
            with self.subTest(parent=parent):
                with self.assertRaises(ValueError): self.parse(value)
        value = copy.deepcopy(self.reply)
        value['new_categories'] = [{'id': 'n1', 'name': 'A', 'parent': 'n2', 'reason': 'R'},
                                    {'id': 'n2', 'name': 'B', 'parent': 'n1', 'reason': 'R'}]
        value['papers'][0]['categories'] = ['n1']
        with self.assertRaises(ValueError): self.parse(value)

    def test_new_categories_need_batch_evidence_and_unique_ids(self):
        value = copy.deepcopy(self.reply)
        value['new_categories'] = [{'id': 'n1', 'name': '没有证据的方向', 'reason': 'R'}]
        with self.assertRaisesRegex(ValueError, '归属证据'): self.parse(value)
        value['new_categories'] *= 2
        with self.assertRaises(ValueError): self.parse(value)

    def test_new_method_at_root_reject_but_relevant_child_allowed(self):
        value = copy.deepcopy(self.reply)
        value['new_categories'] = [{'id': 'n1', 'name': 'Vision Transformers', 'reason': 'R'}]
        value['papers'][0]['categories'] = ['n1']
        with self.assertRaisesRegex(ValueError, '父类'): self.parse(value)
        value['new_categories'][0]['parent'] = 'c1'
        self.assertEqual(self.parse(value)['new_categories'][0]['name'], '视觉 Transformer')

    def test_existing_method_may_keep_unknown_until_sufficient_paper_evidence(self):
        context = cr.prepare([{'id': 'old-method', 'name': 'Vision Transformers'}], [])['context']
        reply = keep(context)
        reply['categories'][0]['reason'] = '片段不足，未知，暂时保留现有类别'
        self.assertEqual(self.parse(reply, context)['categories'][0]['action'], 'keep')

    def test_merge_to_new_category_reject_even_with_assigned_paper_support(self):
        value = copy.deepcopy(self.reply)
        value['categories'][1] = {'id': 'c2', 'action': 'merge', 'target': 'n1', 'reason': 'R'}
        value['new_categories'] = [{'id': 'n1', 'name': 'New subdirection', 'parent': 'c1', 'reason': 'R'}]
        value['papers'][0]['categories'] = ['n1']
        with self.assertRaisesRegex(ValueError, '合并目标'): self.parse(value)

    def test_duplicate_bilingual_aliases_with_same_parent_reject(self):
        value = copy.deepcopy(self.reply)
        value['new_categories'] = [{'id': 'n1', 'name': '世界模型', 'reason': 'R'}]
        value['papers'][0]['categories'] = ['n1']
        with self.assertRaisesRegex(ValueError, '完全同义'): self.parse(value)
        value = copy.deepcopy(self.reply)
        value['categories'][2] = {'id': 'c3', 'action': 'rename', 'name': '世界模型', 'reason': 'R'}
        with self.assertRaises(ValueError): self.parse(value)

    def test_final_paper_categories_unknown_removed_duplicate_or_nonlist_reject(self):
        alias_directions = directories()
        alias_directions[1]['name'] = '世界模型'
        alias_context = cr.prepare(alias_directions, papers())['context']
        alias_reply = keep(alias_context)
        for assigned in [['unknown'], ['c1', 'c1'], [None], 'c1']:
            value = copy.deepcopy(alias_reply); value['papers'][0]['categories'] = assigned
            with self.subTest(assigned=assigned):
                with self.assertRaisesRegex(ValueError, '论文归属'): self.parse(value, alias_context)
        value = copy.deepcopy(alias_reply)
        value['categories'][1] = {'id': 'c2', 'action': 'delete', 'reason': 'R'}
        with self.assertRaisesRegex(ValueError, '论文归属'): self.parse(value, alias_context)
        value['categories'][1] = {'id': 'c2', 'action': 'merge', 'target': 'c1', 'reason': 'R'}
        with self.assertRaisesRegex(ValueError, '论文归属'): self.parse(value, alias_context)
        value['papers'][0]['categories'] = ['c1']
        self.assertEqual(self.parse(value, alias_context)['papers'][0]['categories'], ['private-world'])

    def test_reason_and_new_name_limits_and_unicode_are_strict(self):
        for field, text in [('reason', '中' * 101), ('reason', '\ud800'), ('reason', '')]:
            value = copy.deepcopy(self.reply); value['papers'][0][field] = text
            with self.subTest(text=text[:5]):
                with self.assertRaises(ValueError): self.parse(value)
        for name in ['中' * 31, '', '\ud800']:
            value = copy.deepcopy(self.reply)
            value['categories'][0] = {'id': 'c1', 'action': 'rename', 'name': name, 'reason': 'R'}
            with self.subTest(name=name[:5]):
                with self.assertRaises(ValueError): self.parse(value)


class RegistryParityTests(unittest.TestCase):
    def test_registered_prompt_and_gateway_caps_match_contract(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / 'harness/budget.json').read_text(encoding='utf-8'))
        operation = registry['operations'][cr.OPERATION]
        self.assertEqual(operation['cap'], {'input': cr.INPUT_CAP, 'output': cr.OUTPUT_CAP})
        prompt = (root / operation['prompt']).read_text(encoding='utf-8')
        actual = prompt.split('## System\n\n', 1)[1].split('\n\n## Contract', 1)[0]
        self.assertEqual(actual, cr.SYSTEM)
        self.assertFalse(operation['enabled_by_default'])


if __name__ == '__main__':
    unittest.main()
