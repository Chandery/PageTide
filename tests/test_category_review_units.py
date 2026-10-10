"""An AI category-review plan is shown as separately selectable units.

Order is the owner's priority: first file the unclassified papers, then adjust
the existing categories, then move papers that were already classified. A
selection is closed over what it needs (deleting a category re-homes its papers,
deleting a parent handles its children) so a chosen subset is always applicable.
"""
import unittest

from app import category_review_units as units


def directions():
    return [{'id': 'wm', 'name': '世界模型', 'parent_id': None},
            {'id': 'wm-dup', 'name': 'World Models', 'parent_id': None},
            {'id': 'junk', 'name': 'Model for Embodied', 'parent_id': None},
            {'id': 'junk-child', 'name': '残片子类', 'parent_id': 'junk'},
            {'id': 'robot', 'name': '机器人', 'parent_id': None}]


MEMBERSHIPS = {'held-dup': ['wm-dup'], 'held-junk': ['junk'], 'held-child': ['junk-child'],
               'kept': ['robot'], 'moved': ['robot']}


def plan(**overrides):
    value = {
        'categories': [
            {'id': 'wm', 'action': 'keep', 'reason': '研究方向合理'},
            {'id': 'wm-dup', 'action': 'merge', 'target': 'wm', 'reason': '中英文完全同义'},
            {'id': 'junk', 'action': 'delete', 'reason': '标题残片'},
            {'id': 'junk-child', 'action': 'delete', 'reason': '残片子类'},
            {'id': 'robot', 'action': 'rename', 'name': '机器人学', 'reason': '统一名称'}],
        'new_categories': [{'id': 'ai-cat-a', 'name': '视频世界模型', 'parent_id': 'wm', 'reason': '视频预测证据'},
                           {'id': 'ai-cat-unused', 'name': '没人用的新类', 'parent_id': None, 'reason': '不会被选'}],
        'papers': [
            {'key': 'fresh-1', 'categories': ['ai-cat-a'], 'reason': '视频预测'},
            {'key': 'fresh-2', 'categories': ['robot'], 'reason': '机器人控制'},
            {'key': 'fresh-3', 'categories': ['ai-cat-other'], 'reason': '依据不足，暂放「其他」', 'fallback': True},
            {'key': 'held-dup', 'categories': ['wm'], 'reason': '合并后归入'},
            {'key': 'held-junk', 'categories': ['wm'], 'reason': '重新归类'},
            {'key': 'held-child', 'categories': ['ai-cat-a'], 'reason': '重新归类'},
            {'key': 'kept', 'categories': ['robot'], 'reason': '不变'},
            {'key': 'moved', 'categories': ['wm'], 'reason': '方向更准'}]}
    value['new_categories'].append({'id': 'ai-cat-other', 'name': '其他', 'parent_id': None, 'reason': '依据不足的论文暂放'})
    value.update(overrides)
    return value


def memberships():
    return {**MEMBERSHIPS}


class BuildUnitsTests(unittest.TestCase):
    def setUp(self):
        self.units = units.build_units(plan(), directions(), memberships())
        self.by_id = {u['id']: u for u in self.units}

    def test_unclassified_papers_come_first_then_category_adjustments_then_moves(self):
        sections = [u['section'] for u in self.units]
        self.assertEqual(sections, sorted(sections, key=['classify', 'adjust', 'rehome'].index))
        self.assertEqual([u['key'] for u in self.units if u['section'] == 'classify'], ['fresh-1', 'fresh-2', 'fresh-3'])

    def test_fallback_placement_is_marked_and_reasoned(self):
        unit = self.by_id['p:fresh-3']
        self.assertTrue(unit['fallback'])
        self.assertFalse(self.by_id['p:fresh-1']['fallback'])

    def test_unchanged_and_merge_derived_papers_have_no_unit_of_their_own(self):
        self.assertNotIn('p:kept', self.by_id)
        self.assertNotIn('p:held-dup', self.by_id, 'a merge already moves these papers')
        self.assertEqual(self.by_id['c:wm-dup']['papers'], 1)

    def test_holders_of_a_deleted_category_belong_to_the_delete_not_to_a_separate_move(self):
        self.assertNotIn('p:held-junk', self.by_id)
        self.assertNotIn('p:held-child', self.by_id)
        delete = self.by_id['c:junk']
        self.assertEqual(delete['rehome'], [{'key': 'held-junk', 'to': ['wm']}])
        self.assertEqual(self.by_id['c:junk-child']['rehome'], [{'key': 'held-child', 'to': ['ai-cat-a']}])

    def test_classified_paper_moved_for_no_structural_reason_is_a_rehome_unit(self):
        unit = self.by_id['p:moved']
        self.assertEqual((unit['section'], unit['from'], unit['to']), ('rehome', ['robot'], ['wm']))

    def test_rename_merge_delete_units_carry_their_details(self):
        self.assertEqual(self.by_id['c:robot']['name'], '机器人学')
        self.assertEqual(self.by_id['c:wm-dup']['target'], 'wm')
        self.assertNotIn('c:wm', self.by_id, 'keep is not a change')

    def test_deleting_a_parent_requires_the_units_that_handle_its_children(self):
        self.assertEqual(self.by_id['c:junk']['requires'], ['c:junk-child'])
        self.assertEqual(self.by_id['c:junk-child']['requires'], [])

    def test_a_plan_without_changes_has_no_units(self):
        keep = {'categories': [{'id': 'wm', 'action': 'keep', 'reason': 'r'}], 'new_categories': [],
                'papers': [{'key': 'kept', 'categories': ['wm'], 'reason': 'r'}]}
        self.assertEqual(units.build_units(keep, directions(), {'kept': ['wm']}), [])


class SelectPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan()
        self.units = units.build_units(self.plan, directions(), memberships())

    def select(self, *ids):
        return units.select_plan(self.plan, self.units, ids, memberships())

    @staticmethod
    def ops(sub):
        return {op['id']: op['action'] for op in sub['categories']}

    @staticmethod
    def papers(sub):
        return {p['key']: p['categories'] for p in sub['papers']}

    def test_selecting_everything_reproduces_the_whole_plan(self):
        sub = self.select(*[u['id'] for u in self.units])
        self.assertEqual(self.ops(sub), {'wm': 'keep', 'wm-dup': 'merge', 'junk': 'delete',
                                         'junk-child': 'delete', 'robot': 'rename'})
        self.assertEqual(self.papers(sub), {p['key']: p['categories'] for p in self.plan['papers']})

    def test_selecting_nothing_changes_nothing(self):
        sub = self.select()
        self.assertEqual(set(self.ops(sub).values()), {'keep'})
        self.assertEqual(self.papers(sub), {k: v for k, v in memberships().items()} | {'fresh-1': [], 'fresh-2': [], 'fresh-3': []})
        self.assertEqual(sub['new_categories'], [])

    def test_only_selected_unclassified_papers_are_filed_and_only_their_new_categories_exist(self):
        sub = self.select('p:fresh-1')
        self.assertEqual(self.papers(sub)['fresh-1'], ['ai-cat-a'])
        self.assertEqual(self.papers(sub)['fresh-2'], [])
        self.assertEqual([c['id'] for c in sub['new_categories']], ['ai-cat-a'])
        self.assertEqual(set(self.ops(sub).values()), {'keep'})

    def test_a_new_child_pulls_in_its_new_parent_but_not_unrelated_new_categories(self):
        self.plan['new_categories'][0]['parent_id'] = 'ai-cat-unused'
        self.units = units.build_units(self.plan, directions(), memberships())
        sub = self.select('p:fresh-1')
        self.assertEqual([c['id'] for c in sub['new_categories']], ['ai-cat-unused', 'ai-cat-a'])

    def test_deleting_a_category_brings_the_rehoming_of_its_papers(self):
        sub = self.select('c:junk-child')
        self.assertEqual(self.ops(sub)['junk-child'], 'delete')
        self.assertEqual(self.papers(sub)['held-child'], ['ai-cat-a'])
        self.assertEqual(self.papers(sub)['held-junk'], ['junk'], 'the other category and its papers stay')
        self.assertEqual([c['id'] for c in sub['new_categories']], ['ai-cat-a'])

    def test_deleting_a_parent_selects_the_handling_of_its_children_too(self):
        sub = self.select('c:junk')
        self.assertEqual({k: v for k, v in self.ops(sub).items() if v != 'keep'}, {'junk': 'delete', 'junk-child': 'delete'})
        self.assertEqual(self.papers(sub)['held-junk'], ['wm'])
        self.assertEqual(self.papers(sub)['held-child'], ['ai-cat-a'])

    def test_an_unselected_merge_leaves_its_papers_where_they_are(self):
        sub = self.select('p:moved')
        self.assertEqual(self.ops(sub)['wm-dup'], 'keep')
        self.assertEqual(self.papers(sub)['held-dup'], ['wm-dup'])
        self.assertEqual(self.papers(sub)['moved'], ['wm'])

    def test_a_selected_merge_moves_its_papers_through_the_merge_itself(self):
        sub = self.select('c:wm-dup')
        self.assertEqual(self.ops(sub)['wm-dup'], 'merge')
        self.assertEqual(self.papers(sub)['held-dup'], ['wm'])

    def test_unknown_unit_is_refused(self):
        with self.assertRaisesRegex(ValueError, '选择'):
            self.select('p:nobody')
        with self.assertRaisesRegex(ValueError, '选择'):
            units.select_plan(self.plan, self.units, 'p:fresh-1', memberships())

    def test_closure_reports_what_a_choice_requires(self):
        self.assertEqual(units.closure(self.units, ['c:junk']), {'c:junk', 'c:junk-child'})
        self.assertEqual(units.closure(self.units, ['p:fresh-1']), {'p:fresh-1'})


if __name__ == '__main__':
    unittest.main()
