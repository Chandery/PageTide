"""The review organizes what the left directory shows, files unclassified papers first, and leaves none behind.

No network and no model: a scripted gateway answers, a fake organization holds the frozen state.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import category_review as cr
from app.category_review_service import _stable_id, run_review
from app.organization_terms import category_identity
from tests.test_category_review_service import FakeGateway, FakeOrganization


class ScopedOrganization(FakeOrganization):
    """Papers of project `mine` are in scope; every paper is saved somewhere."""

    def __init__(self, papers, mine, directions=None, memberships=None):
        super().__init__(papers, directions, memberships)
        self.mine = set(mine)

    def _corpus(self, scope=None):
        return copy.deepcopy([p for p in self.papers if not scope or p['key'] in self.mine])


def paper(key, title='World model planning'):
    return {'key': key, 'title': title, 'abstract': 'A study of video world models.'}


def direction(identifier, name, parent=None):
    return {'id': identifier, 'name': name, 'parent_id': parent}


class Base(unittest.TestCase):
    def build(self, papers, mine, directions, memberships):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.app = SimpleNamespace(data=Path(tmp.name), store=object(), gateway=FakeGateway())
        self.org = ScopedOrganization(papers, mine, directions, memberships)
        self.addCleanup(patch.stopall)
        patch('app.category_review_service.Organization', return_value=self.org).start()

    def review(self, scope='project-one', **kwargs):
        return run_review(self.app, scope, {}, **kwargs)

    def wire(self, call=0):
        return json.loads(self.app.gateway.calls[call][1][-1]['content'])


class ScopeTests(Base):
    def setUp(self):
        papers = [paper('mine-1'), paper('mine-2'), paper('theirs-1')]
        directions = [direction('A', '机器人'), direction('B', '自动驾驶'), direction('C', '空的类别'),
                      direction('D', '端到端驾驶', 'B'), direction('S', '共用类别'), direction('T', '只有我的', None)]
        memberships = {'mine-1': ['A', 'S'], 'theirs-1': ['B', 'D', 'S'], 'mine-2': ['T'],}
        self.build(papers, ['mine-1', 'mine-2'], directions, memberships)

    def test_a_project_review_sends_only_the_categories_its_directory_shows(self):
        result = self.review()
        names = [c['name'] for c in self.wire()['categories']]
        self.assertEqual(names, ['机器人', '空的类别', '共用类别', '只有我的'])
        self.assertEqual(result['ai_review']['status'], 'complete')
        plan = self.org.stored[0]
        self.assertEqual(plan['category_scope'], ['A', 'C', 'S', 'T'])
        self.assertTrue(plan['scoped'])
        self.assertEqual([op['id'] for op in plan['categories']], ['A', 'C', 'S', 'T'])

    def test_all_projects_review_sends_the_whole_directory(self):
        self.review(scope=None)
        self.assertEqual(len(self.wire()['categories']), 6)
        plan = self.org.stored[0]
        self.assertFalse(plan['scoped'])
        self.assertEqual(plan['category_scope'], ['A', 'B', 'C', 'D', 'S', 'T'])

    def test_a_category_other_projects_also_use_is_read_only_on_the_wire(self):
        self.review()
        wire = {c['name']: c for c in self.wire()['categories']}
        self.assertEqual(wire['共用类别'].get('lock'), 1)
        self.assertNotIn('lock', wire['机器人'])
        self.assertNotIn('lock', wire['空的类别'])

    def test_a_reply_that_changes_a_read_only_category_is_ignored_for_that_category(self):
        # The model is told not to; if it does anyway the proposal for that category is dropped, not the whole plan.
        def rename_shared(index, request, value):
            shared = next(c for c in request['categories'] if c['name'] == '共用类别')
            op = next(o for o in value['categories'] if o['id'] == shared['id'])
            op.update(action='rename', name='改名了')
            mine = next(c for c in request['categories'] if c['name'] == '机器人')
            next(o for o in value['categories'] if o['id'] == mine['id']).update(action='rename', name='机器人学')
        self.app.gateway.response = rename_shared
        result = self.review()
        self.assertEqual(result['ai_review']['status'], 'complete')
        ops = {op['id']: op for op in self.org.stored[0]['categories']}
        self.assertEqual(ops['S']['action'], 'keep', 'shared: the rename is dropped')
        self.assertEqual((ops['A']['action'], ops['A'].get('name')), ('rename', '机器人学'), 'only this project: kept')

    def test_a_rename_that_repeats_a_name_outside_the_directory_stays_as_it_was(self):
        # Project two's directory has a top-level 世界模型; renaming this project's "World Models" to it would be a duplicate.
        self.org.papers.append(paper('theirs-2')); self.org.data['directions'] += [direction('W1', 'World Models'), direction('W2', '世界模型')]
        self.org.mine.add('mine-2')
        self.org.data['memberships'].update({'mine-2': ['W1'], 'theirs-2': ['W2']})
        def to_chinese(index, request, value):
            wm = next(c for c in request['categories'] if c['name'] == 'World Models')
            next(o for o in value['categories'] if o['id'] == wm['id']).update(action='rename', name='世界模型')
        self.app.gateway.response = to_chinese
        result = self.review()
        self.assertEqual(result['ai_review']['status'], 'complete')
        self.assertEqual({op['id']: op['action'] for op in self.org.stored[0]['categories']}['W1'], 'keep')
        self.assertEqual(result['ai_review']['kept_by_scope'], 1)

    def test_a_merge_whose_children_would_repeat_a_hidden_child_s_name_is_dropped(self):
        # Beta's child "Planning" would land beside Alpha's "Planning", which only project two uses.
        self.org.papers.append(paper('theirs-2'))
        self.org.data['directions'] += [direction('AL', 'Alpha'), direction('BE', 'Beta'), direction('BP', 'Planning', 'BE'),
                                        direction('AP', 'Planning', 'AL')]
        self.org.data['memberships'].update({'mine-1': ['BP'], 'mine-2': ['AL'], 'theirs-2': ['AP']})
        def merge_beta(index, request, value):
            ids = {(c['name'], c['parent']): c['id'] for c in request['categories']}
            alpha, beta = ids[('Alpha', None)], ids[('Beta', None)]
            next(o for o in value['categories'] if o['id'] == beta).update(action='merge', target=alpha)
        self.app.gateway.response = merge_beta
        result = self.review()
        self.assertEqual(result['ai_review']['status'], 'complete')
        self.assertEqual({op['id']: op['action'] for op in self.org.stored[0]['categories']}['BE'], 'keep')
        self.assertEqual(result['ai_review']['kept_by_scope'], 1)

    def test_new_categories_reuse_outside_ones_whatever_order_the_reply_lists_them(self):
        self.org.data['directions'] += [direction('H1', '自动驾驶'), direction('H2', '端到端驾驶', 'H1')]
        self.org.papers.append(paper('theirs-2')); self.org.data['memberships']['theirs-2'] = ['H2']
        def child_first(index, request, value):
            value['new_categories'] = [{'id': 'n2', 'name': '端到端驾驶', 'parent': 'n1', 'reason': '子方向'},
                                       {'id': 'n1', 'name': '自动驾驶', 'reason': '研究方向'}]
            for item in value['papers']:
                item['categories'] = ['n2']
        self.app.gateway.response = child_first
        self.review()
        plan = self.org.stored[0]
        self.assertEqual(plan['new_categories'], [])
        self.assertTrue(all(p['categories'] == ['H2'] for p in plan['papers']))

    def test_a_new_category_that_repeats_one_outside_the_directory_reuses_that_one(self):
        def create_driving(index, request, value):
            value['new_categories'] = [{'id': 'n1', 'name': 'Autonomous Driving', 'reason': '论文研究自动驾驶'}]
            for item in value['papers']:
                item['categories'] = ['n1']
        self.app.gateway.response = create_driving
        self.review()
        plan = self.org.stored[0]
        self.assertEqual(plan['new_categories'], [])
        self.assertTrue(all(p['categories'] == ['B'] for p in plan['papers']))


class PriorityTests(Base):
    def setUp(self):
        papers = [paper('a-classified'), paper('b-new'), paper('c-classified'), paper('d-new')]
        self.build(papers, [p['key'] for p in papers], [direction('W', '世界模型')],
                   {'a-classified': ['W'], 'c-classified': ['W']})

    def test_unclassified_papers_are_reviewed_first(self):
        self.review(scope=None)
        first = [p['categories'] for p in self.wire()['papers']]
        self.assertEqual(first, [[], [], ['c1'], ['c1']], 'unclassified first, classified after, input order kept')

    def test_the_prompt_puts_filing_unclassified_papers_first_and_forbids_leaving_them_empty(self):
        self.assertIn('第一优先', cr.SYSTEM)
        self.assertIn('未分类', cr.SYSTEM)
        self.assertIn('不得为空', cr.SYSTEM)
        self.assertNotIn('保留为未分类', cr.SYSTEM)
        self.assertIn('"lock":1', cr.SYSTEM)

    def test_a_paper_the_model_leaves_without_a_category_is_filed_under_other_and_marked(self):
        result = self.review(scope=None)
        plan = self.org.stored[0]
        self.assertEqual(result['ai_review']['status'], 'complete')
        self.assertTrue(all(p['categories'] for p in plan['papers']), 'nothing is left unclassified')
        other = [c for c in plan['new_categories'] if c['name'] == '其他']
        self.assertEqual(len(other), 1)
        self.assertIsNone(other[0]['parent_id'])
        filed = {p['key']: p for p in plan['papers']}
        for key in ('b-new', 'd-new'):
            self.assertEqual(filed[key]['categories'], [other[0]['id']])
            self.assertTrue(filed[key]['fallback'])
            self.assertIn('其他', filed[key]['reason'])
        self.assertFalse(filed['a-classified'].get('fallback'))
        self.assertEqual(result['ai_review']['fallback_papers'], 2)
        self.assertEqual(result['ai_review']['unclassified_papers'], 2)

    def test_papers_the_model_does_classify_are_not_touched_by_the_fallback(self):
        def classify(index, request, value):
            for item in value['papers']:
                if not item['categories']:
                    item['categories'] = ['c1']
        self.app.gateway.response = classify
        result = self.review(scope=None)
        plan = self.org.stored[0]
        self.assertEqual(plan['new_categories'], [])
        self.assertTrue(all(p['categories'] == ['W'] and not p.get('fallback') for p in plan['papers']))
        self.assertEqual(result['ai_review']['fallback_papers'], 0)

    def test_the_fallback_follows_the_interface_language(self):
        run_review(self.app, None, {'language': 'en-US'})
        plan = self.org.stored[0]
        self.assertEqual([c['name'] for c in plan['new_categories']], ['Other'])
        self.assertTrue(all('Not enough evidence' in p['reason'] for p in plan['papers'] if p.get('fallback')))

    def test_an_existing_other_category_is_reused(self):
        self.org.data['directions'].append(direction('O', '其他'))
        self.review(scope=None)
        plan = self.org.stored[0]
        self.assertEqual(plan['new_categories'], [])
        self.assertEqual({p['key']: p['categories'] for p in plan['papers']}['b-new'], ['O'])

    def empty_everything(self, index, request, value):
        for item in value['papers']:
            item['categories'] = []

    def test_a_classified_paper_the_model_leaves_empty_keeps_its_own_categories(self):
        self.org.data['directions'].append(direction('R', '机器人'))
        self.org.data['memberships']['a-classified'] = ['W', 'R']
        self.app.gateway.response = self.empty_everything
        self.review(scope=None)
        filed = {p['key']: p for p in self.org.stored[0]['papers']}
        self.assertEqual(filed['a-classified']['categories'], ['W', 'R'])
        self.assertEqual(filed['c-classified']['categories'], ['W'])
        self.assertFalse(filed['a-classified'].get('fallback'))
        self.assertTrue(filed['b-new'].get('fallback'), 'only the papers that had nothing go to 其他')

    def test_deleting_a_category_leaves_a_paper_its_other_categories(self):
        self.org.data['directions'].append(direction('R', '机器人'))
        self.org.data['memberships'].update({'a-classified': ['W', 'R'], 'c-classified': ['R']})
        def delete_robot(index, request, value):
            robot = next(c for c in request['categories'] if c['name'] == '机器人')
            next(o for o in value['categories'] if o['id'] == robot['id']).update(action='delete')
            self.empty_everything(index, request, value)
        self.app.gateway.response = delete_robot
        self.review(scope=None)
        filed = {p['key']: p for p in self.org.stored[0]['papers']}
        self.assertEqual(filed['a-classified']['categories'], ['W'], 'the deleted category goes, the other stays')
        self.assertTrue(filed['c-classified']['fallback'], 'nothing left, so 其他')

    def test_a_merged_category_maps_the_current_membership_when_the_model_returns_nothing(self):
        self.org.data['directions'].append(direction('S', 'World Models'))
        self.org.data['memberships']['a-classified'] = ['S']
        def merge_s(index, request, value):
            s = next(c for c in request['categories'] if c['name'] == 'World Models')
            w = next(c for c in request['categories'] if c['name'] == '世界模型')
            next(o for o in value['categories'] if o['id'] == s['id']).update(action='merge', target=w['id'])
            self.empty_everything(index, request, value)
        self.app.gateway.response = merge_s
        self.review(scope=None)
        self.assertEqual({p['key']: p['categories'] for p in self.org.stored[0]['papers']}['a-classified'], ['W'])

    def test_a_later_review_can_create_other_again_after_the_first_one_was_renamed(self):
        taken = _stable_id((category_identity('其他'),))
        self.org.data['directions'].append(direction(taken, '杂项'))   # the earlier 其他, renamed by its owner
        self.review(scope=None)
        created = [c for c in self.org.stored[0]['new_categories'] if c['name'] == '其他']
        self.assertEqual(len(created), 1)
        self.assertNotEqual(created[0]['id'], taken)

    def test_a_merged_away_other_category_does_not_block_a_new_one(self):
        taken = _stable_id((category_identity('其他'),))
        self.org.data['directions'].append(direction(taken, '其他'))
        def merge_other(index, request, value):
            other = next(c for c in request['categories'] if c['name'] == '其他')
            world = next(c for c in request['categories'] if c['name'] == '世界模型')
            next(o for o in value['categories'] if o['id'] == other['id']).update(action='merge', target=world['id'])
        self.app.gateway.response = merge_other
        result = self.review(scope=None)
        self.assertEqual(result['ai_review']['status'], 'complete')
        created = [c for c in self.org.stored[0]['new_categories'] if c['name'] == '其他']
        self.assertEqual(len(created), 1)
        self.assertNotEqual(created[0]['id'], taken)

    def test_papers_placed_in_the_category_that_owns_a_derived_id_stay_there_while_the_new_one_gets_a_fresh_id(self):
        # An earlier review made "Foo", its owner renamed it "Bar"; now the model proposes a NEW "Foo" and files
        # some papers in the existing "Bar" and others in the new "Foo". Both must keep their own papers.
        taken = _stable_id((category_identity('视频世界模型'),))
        self.org.data['directions'].append(direction(taken, '手工改名的类别'))
        def split(index, request, value):
            value['new_categories'] = [{'id': 'n1', 'name': '视频世界模型', 'reason': '视频预测证据'}]
            existing = next(c for c in request['categories'] if c['name'] == '手工改名的类别')['id']
            for number, item in enumerate(value['papers']):
                item['categories'] = [existing] if number % 2 == 0 else ['n1']
        self.app.gateway.response = split
        result = self.review(scope=None)
        self.assertEqual(result['ai_review']['status'], 'complete')
        plan = self.org.stored[0]
        fresh = plan['new_categories'][0]['id']
        self.assertNotEqual(fresh, taken)
        placed = [p['categories'] for p in plan['papers']]
        self.assertEqual(sorted(set(map(tuple, placed))), sorted([(taken,), (fresh,)]), 'two groups, one in each category')
        self.assertEqual(sum(1 for c in placed if c == [taken]), 2, 'the papers the model put in the existing category stay in it')

    def test_an_ai_category_whose_derived_id_is_already_taken_gets_a_fresh_id(self):
        taken = _stable_id((category_identity('视频世界模型'),))
        self.org.data['directions'].append(direction(taken, '手工改名的类别'))
        def create_video(index, request, value):
            value['new_categories'] = [{'id': 'n1', 'name': '视频世界模型', 'reason': '视频预测证据'}]
            for item in value['papers']:
                item['categories'] = ['n1']
        self.app.gateway.response = create_video
        result = self.review(scope=None)
        self.assertEqual(result['ai_review']['status'], 'complete')
        plan = self.org.stored[0]
        created = plan['new_categories'][0]
        self.assertNotEqual(created['id'], taken)
        self.assertTrue(all(p['categories'] == [created['id']] for p in plan['papers']))

    def test_a_delete_that_leaves_papers_empty_also_ends_in_other_not_unclassified(self):
        def delete_world(index, request, value):
            value['categories'][0]['action'] = 'delete'
            for item in value['papers']:
                item['categories'] = []
        self.app.gateway.response = delete_world
        self.review(scope=None)
        plan = self.org.stored[0]
        self.assertTrue(all(p['categories'] for p in plan['papers']))
        self.assertEqual(plan['categories'][0]['action'], 'delete')


if __name__ == '__main__':
    unittest.main()
