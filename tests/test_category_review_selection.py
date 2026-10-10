"""Applying only the chosen part of an AI category-review plan, inside the left directory's scope.

Real temporary SQLite; no model call. Project One shows the categories its papers use, project Two's
private category is not in that directory, and a category both projects use is shared.
"""
import tempfile
import unittest
from pathlib import Path

from app.clustering import corpus_fingerprint
from app.db import Store
from app.organization import Conflict, Organization
from app.organization_facets import structure_hash
from app.project import ProjectManager


class SelectionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / 'test.sqlite'); self.store.init(); self.addCleanup(self.store.close)
        manager = ProjectManager(self.store)
        self.one, self.two = manager.create_project('One'), manager.create_project('Two')
        papers = {'new-a': self.one, 'new-b': self.one, 'junk-held': self.one, 'dup-held': self.one,
                  'shared-paper': self.one, 'two-only': self.two}
        self.store.upsert_papers([{'key': key, 'title': f'Paper {key}', 'abstract': 'About world models.'} for key in papers])
        for key, project in papers.items():
            self.store.add_project_paper(project, key)
            self.store.save_to_library(key, project_id=project)
        self.store.add_project_paper(self.two, 'shared-paper')
        self.store.save_to_library('shared-paper', project_id=self.two)
        self.org = Organization(self.store)
        for name in ('世界模型', 'World Models', 'Model for Embodied', '机器人'):
            self.org.action({'action': 'direction-save', 'name': name, 'color': '#123456'})
        ids = {d['name']: d['id'] for d in self.org.snapshot()['directions']}
        self.wm, self.dup, self.junk, self.robot = ids['世界模型'], ids['World Models'], ids['Model for Embodied'], ids['机器人']
        for keys, add in ((['shared-paper'], self.wm), (['dup-held'], self.dup), (['junk-held'], self.junk),
                          (['two-only'], self.robot), (['shared-paper'], self.robot), (['two-only'], self.wm)):
            self.org.action({'action': 'membership', 'keys': keys, 'add': [add]})
        self.org.action({'action': 'note', 'key': 'new-a', 'text': 'Owner note', 'version': 0})

    def memberships(self):
        return {item['key']: sorted(item['directions']) for item in self.org.snapshot()['items']}

    def names(self):
        return {d['id']: d['name'] for d in self.org.snapshot()['directions']}

    def plan(self):
        """What the review service would store for project One: Two-only category is not in its directory."""
        return {'scoped': True, 'scope_project': self.one, 'category_scope': [self.wm, self.dup, self.junk, self.robot],
                'categories': [{'id': self.wm, 'action': 'keep', 'reason': '合理'},
                               {'id': self.dup, 'action': 'merge', 'target': self.wm, 'reason': '中英文同义'},
                               {'id': self.junk, 'action': 'delete', 'reason': '标题残片'},
                               {'id': self.robot, 'action': 'keep', 'reason': '合理'}],
                'new_categories': [{'id': 'ai-cat-video', 'name': '视频世界模型', 'parent_id': self.wm, 'reason': '视频预测'},
                                   {'id': 'ai-cat-other', 'name': '其他', 'parent_id': None, 'reason': '依据不足的论文暂放'}],
                'papers': [{'key': 'new-a', 'categories': ['ai-cat-video'], 'reason': '视频预测'},
                           {'key': 'new-b', 'categories': ['ai-cat-other'], 'reason': '依据不足，暂放「其他」', 'fallback': True},
                           {'key': 'junk-held', 'categories': [self.wm], 'reason': '重新归类'},
                           {'key': 'dup-held', 'categories': [self.wm], 'reason': '合并后归入'},
                           {'key': 'shared-paper', 'categories': [self.wm, self.robot], 'reason': '不变'}]}

    def preview(self, plan=None, scope=None):
        scope = scope or self.one
        revision, data = self.org._load()
        return self.org.store_ai_review(plan or self.plan(), revision, corpus_fingerprint(self.org._corpus(scope)),
                                        structure_hash(data['directions'], data['memberships']), scope)['suggestions']

    def apply(self, preview, **extra):
        return self.org.action({'action': 'apply-ai-review', 'ai_token': preview['ai_token'],
                                'fingerprint': preview['fingerprint'], **extra})

    def test_preview_carries_the_selectable_units_in_priority_order(self):
        units = self.preview()['ai_units']
        self.assertEqual([u['section'] for u in units], ['classify', 'classify', 'adjust', 'adjust'])
        self.assertEqual([u['id'] for u in units], ['p:new-a', 'p:new-b', 'c:' + self.dup, 'c:' + self.junk])
        self.assertTrue(next(u for u in units if u['id'] == 'p:new-b')['fallback'])

    def test_no_selection_applies_the_whole_plan_as_before(self):
        result = self.apply(self.preview())
        self.assertEqual(result['apply_result']['still_unclassified'], 0)
        after, names = self.memberships(), self.names()
        self.assertEqual({names[i] for i in after['new-a']}, {'视频世界模型'})
        self.assertEqual({names[i] for i in after['new-b']}, {'其他'})
        self.assertEqual(after['dup-held'], [self.wm])
        self.assertNotIn(self.junk, names)
        self.assertNotIn(self.dup, names)

    def test_only_the_chosen_units_are_applied_and_the_rest_is_left_exactly_as_it_was(self):
        before_names = dict(self.names())
        result = self.apply(self.preview(), selection={'units': ['p:new-a']})
        after, names = self.memberships(), self.names()
        self.assertEqual({names[i] for i in after['new-a']}, {'视频世界模型'})
        self.assertEqual(after['new-b'], [], 'not chosen, so still unclassified')
        self.assertEqual(result['apply_result']['still_unclassified'], 1)
        self.assertEqual(after['dup-held'], [self.dup])
        self.assertEqual(after['junk-held'], [self.junk])
        self.assertEqual({k: v for k, v in names.items() if k in before_names}, before_names)
        self.assertNotIn('其他', names.values(), 'a new category nobody was filed under is not created')
        self.assertEqual(next(i['note'] for i in self.org.snapshot()['items'] if i['key'] == 'new-a'), 'Owner note')

    def test_choosing_a_delete_also_moves_the_papers_it_empties(self):
        self.apply(self.preview(), selection={'units': ['c:' + self.junk]})
        after, names = self.memberships(), self.names()
        self.assertNotIn(self.junk, names)
        self.assertEqual(after['junk-held'], [self.wm])
        self.assertEqual(after['new-a'], [])

    def test_choosing_a_merge_moves_its_papers_through_the_merge(self):
        self.apply(self.preview(), selection={'units': ['c:' + self.dup]})
        self.assertEqual(self.memberships()['dup-held'], [self.wm])
        self.assertNotIn(self.dup, self.names())
        self.assertIn(self.junk, self.names())

    def test_the_partial_application_is_one_undo_step(self):
        before = self.memberships(), self.names()
        self.apply(self.preview(), selection={'units': ['p:new-a', 'c:' + self.junk]})
        self.org.action({'action': 'undo'})
        self.assertEqual((self.memberships(), self.names()), before)

    def test_an_empty_or_unknown_selection_is_refused_without_touching_anything(self):
        preview = self.preview(); before = self.memberships(), self.names()
        for selection in ({'units': []}, {'units': ['p:nobody']}, {'units': 'p:new-a'}, {}):
            with self.subTest(selection=selection):
                with self.assertRaises(ValueError):
                    self.apply(preview, selection=selection)
        self.assertEqual((self.memberships(), self.names()), before)
        self.apply(preview, selection={'units': ['p:new-a']})   # the preview is still usable

    def test_categories_outside_the_directory_are_not_part_of_the_plan_and_stay_untouched(self):
        # A category only project Two uses is not in project One's directory:
        self.org.action({'action': 'direction-save', 'name': '只在二号项目', 'color': '#123456'})
        private = next(d['id'] for d in self.org.snapshot()['directions'] if d['name'] == '只在二号项目')
        self.org.action({'action': 'membership', 'keys': ['two-only'], 'add': [private]})
        self.apply(self.preview())
        self.assertIn(private, self.names())
        self.assertEqual(self.memberships()['two-only'], sorted([self.robot, self.wm, private]))

    def test_a_plan_that_forgets_a_category_of_the_directory_is_still_rejected(self):
        plan = self.plan(); plan['categories'].pop()
        with self.assertRaises(ValueError):
            self.preview(plan)

    def test_a_shared_category_cannot_be_renamed_merged_or_deleted_from_a_project_scope(self):
        for action in ({'action': 'rename', 'name': '改名了'}, {'action': 'delete'}):
            plan = self.plan(); plan['categories'][0] = {'id': self.wm, 'reason': 'x', **action}
            with self.subTest(action=action['action']):
                with self.assertRaisesRegex(ValueError, '共用'):
                    self.preview(plan)

    def test_merging_the_ancestor_of_a_shared_category_is_refused(self):
        # "子类" is used by both projects; merging its parent away would move it in project Two's tree too.
        self.org.action({'action': 'direction-save', 'name': '上级', 'color': '#123456'})
        up = next(d['id'] for d in self.org.snapshot()['directions'] if d['name'] == '上级')
        self.org.action({'action': 'direction-save', 'name': '子类', 'color': '#123456', 'parent_id': up})
        child = next(d['id'] for d in self.org.snapshot()['directions'] if d['name'] == '子类')
        self.org.action({'action': 'membership', 'keys': ['new-a', 'two-only'], 'add': [child]})
        plan = self.plan()
        plan['category_scope'] += [up, child]
        plan['categories'] += [{'id': up, 'action': 'merge', 'target': self.wm, 'reason': '重复上级'},
                               {'id': child, 'action': 'keep', 'reason': '合理'}]
        plan['new_categories'] = [plan['new_categories'][1]]
        plan['papers'][0] = {'key': 'new-a', 'categories': [child], 'reason': '不变'}
        with self.assertRaisesRegex(ValueError, '共用'):
            self.preview(plan)

    def test_a_paper_another_project_also_saved_makes_its_category_shared(self):
        self.store.add_project_paper(self.two, 'dup-held')
        self.store.save_to_library('dup-held', project_id=self.two)
        with self.assertRaisesRegex(ValueError, '共用'):
            self.preview()   # the plan merges "World Models", which dup-held (also project Two's) holds

    def test_an_old_duplicate_the_plan_does_not_touch_does_not_block_the_application(self):
        # "World Models" and "世界模型" are the same category; this plan leaves both alone.
        plan = self.plan()
        plan['categories'][1] = {'id': self.dup, 'action': 'keep', 'reason': '本次不处理'}
        plan['papers'][3] = {'key': 'dup-held', 'categories': [self.dup], 'reason': '不变'}
        self.apply(self.preview(plan))
        self.assertIn(self.dup, self.names())

    def test_label_changes_of_a_category_only_this_project_uses_stand_alone_in_a_project_scope(self):
        # "Solo" is held by a paper the plan does not change; that paper still counts as this project's, so Solo is
        # not shared and its rename needs nothing else.
        self.org.action({'action': 'direction-save', 'name': 'Solo', 'color': '#123456'})
        solo = next(d['id'] for d in self.org.snapshot()['directions'] if d['name'] == 'Solo')
        self.org.action({'action': 'membership', 'keys': ['new-a'], 'add': [solo]})
        plan = self.plan()
        plan['category_scope'].append(solo)
        plan['categories'].append({'id': solo, 'action': 'rename', 'name': 'Solo2', 'reason': '统一名称'})
        plan['new_categories'] = [plan['new_categories'][1]]
        plan['papers'][0] = {'key': 'new-a', 'categories': [solo], 'reason': '不变'}
        units = {u['id']: u for u in self.preview(plan)['ai_units']}
        self.assertEqual(units['c:' + solo]['requires'], [])
        self.assertEqual(units['c:' + self.dup]['requires'], [])

    def test_a_new_category_that_repeats_an_existing_name_is_still_refused(self):
        plan = self.plan(); plan['new_categories'][1]['name'] = 'World Models'
        with self.assertRaises(ValueError):
            self.preview(plan)

    def test_stale_structure_is_still_refused(self):
        preview = self.preview()
        self.org.action({'action': 'direction-save', 'name': '手工新增', 'color': '#123456'})
        with self.assertRaises(Conflict):
            self.apply(preview, selection={'units': ['p:new-a']})


if __name__ == '__main__':
    unittest.main()
