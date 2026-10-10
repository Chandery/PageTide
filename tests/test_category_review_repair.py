"""A plan the library cannot take as it stands is repaired locally by dropping label changes, not by failing a paid review.

The model's merge or rename can depend on another proposal that was dropped for scope reasons (it would repeat a name
only another project's directory has). No model call is repeated: the repair is local and read-only until storing.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.category_review_service import _repair, run_review
from app.db import Store
from app.organization import Organization
from app.project import ProjectManager
from tests.test_category_review_service import FakeGateway


class FakeLibrary:
    """plan_error() says a plan is fine only when none of `need_kept` is still changed."""

    def __init__(self, need_kept):
        self.need_kept = set(need_kept)
        self.asked = 0

    def plan_error(self, plan):
        self.asked += 1
        changed = {op['id'] for op in plan['categories'] if op['action'] != 'keep'}
        return None if not changed & self.need_kept else '审阅方案仍有同级同义类别'


def plan_of(*ops):
    return {'categories': [{'id': i, 'action': a, 'reason': 'r', **({'name': 'N'} if a == 'rename' else {}),
                            **({'target': 'x'} if a == 'merge' else {})} for i, a in ops], 'papers': [], 'new_categories': []}


class RepairUnitTests(unittest.TestCase):
    def test_a_plan_that_applies_is_left_alone(self):
        library = FakeLibrary([])
        plan = plan_of(('a', 'rename'), ('b', 'merge'))
        self.assertEqual(_repair(library, plan), (plan, 0))
        self.assertEqual(library.asked, 1)

    def test_the_one_proposal_whose_removal_makes_the_rest_apply_is_dropped_and_the_others_stay(self):
        plan = plan_of(('a', 'rename'), ('b', 'merge'), ('c', 'delete'))
        repaired, dropped = _repair(FakeLibrary(['b']), plan)
        self.assertEqual(dropped, 1)
        self.assertEqual({op['id']: op['action'] for op in repaired['categories']}, {'a': 'rename', 'b': 'keep', 'c': 'delete'})

    def test_two_independent_problems_drop_only_the_proposals_that_cannot_stand(self):
        # Neither 'a' nor 'b' can be applied; 'c' is unrelated and valid, so it stays.
        plan = plan_of(('a', 'rename'), ('b', 'merge'), ('c', 'delete'))
        repaired, dropped = _repair(FakeLibrary(['a', 'b']), plan)
        self.assertEqual(dropped, 2)
        self.assertEqual({op['id']: op['action'] for op in repaired['categories']}, {'a': 'keep', 'b': 'keep', 'c': 'delete'})

    def test_proposals_that_cannot_be_applied_together_keep_the_first_and_drop_the_second(self):
        class Exclusive(FakeLibrary):
            def plan_error(self, plan):
                self.asked += 1
                changed = {op['id'] for op in plan['categories'] if op['action'] != 'keep'}
                return '审阅方案仍有同级同义类别' if {'a', 'b'} <= changed else None
        plan = plan_of(('a', 'rename'), ('b', 'merge'), ('c', 'delete'))
        repaired, dropped = _repair(Exclusive([]), plan)
        self.assertEqual(dropped, 1)
        self.assertEqual({op['id']: op['action'] for op in repaired['categories']}, {'a': 'rename', 'b': 'keep', 'c': 'delete'})

    def test_when_even_no_label_change_applies_it_is_left_for_the_store_to_report(self):
        plan = plan_of(('a', 'rename'), ('b', 'merge'))
        class Hopeless(FakeLibrary):
            def plan_error(self, plan):
                return '无法修复'
        self.assertEqual(_repair(Hopeless([]), plan), (plan, 0))

    def test_what_cannot_be_repaired_is_left_for_the_store_to_report(self):
        class Broken(FakeLibrary):
            def plan_error(self, plan):
                return '无法修复'
        plan = plan_of(('a', 'rename'))
        self.assertEqual(_repair(Broken([]), plan), (plan, 0))

    def test_a_library_without_a_probe_is_not_asked(self):
        plan = plan_of(('a', 'rename'))
        self.assertEqual(_repair(object(), plan), (plan, 0))


class RepairPipelineTests(unittest.TestCase):
    def test_a_merge_that_relied_on_a_dropped_rename_is_dropped_too_and_the_review_completes(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = Store(Path(tmp.name) / 't.sqlite'); store.init(); self.addCleanup(store.close)
        manager = ProjectManager(store)
        one, two = manager.create_project('One'), manager.create_project('Two')
        store.upsert_papers([{'key': k, 'title': 'Paper ' + k, 'abstract': 'About robots.'} for k in ('o1', 'o2', 'x1')])
        for key, project in (('o1', one), ('o2', one), ('x1', two)):
            store.add_project_paper(project, key); store.save_to_library(key, project_id=project)
        org = Organization(store)
        for name in ('机器人', '具身智能', '机器人'):                    # the third one is project two's own
            org.action({'action': 'direction-save', 'name': name, 'color': '#123456'})
        ids = [d['id'] for d in org.snapshot()['directions']]
        for key, category in (('o1', ids[0]), ('o2', ids[1]), ('x1', ids[2])):
            org.action({'action': 'membership', 'keys': [key], 'add': [category]})

        def respond(index, request, value):
            wire = {c['name']: c['id'] for c in request['categories']}
            robot, embodied = wire['机器人'], wire['具身智能']
            for op in value['categories']:
                if op['id'] == embodied:
                    op.update(action='rename', name='Robotics', reason='统一为标准名')      # = 机器人: another project's name
                if op['id'] == robot:
                    op.update(action='merge', target=embodied, reason='同义')
            for paper in value['papers']:
                paper['categories'] = [embodied if c == robot else c for c in paper['categories']]
        gateway = FakeGateway(respond)
        app = SimpleNamespace(data=Path(tmp.name), store=store, gateway=gateway)
        result = run_review(app, one, {})
        self.assertEqual(result['ai_review']['status'], 'complete', result['ai_review'].get('error'))
        self.assertEqual(result['ai_review']['kept_by_scope'], 1, 'the rename was dropped: it would repeat project two\'s name')
        self.assertEqual(result['ai_review']['demoted_for_validity'], 1, 'and the merge that relied on it')
        plan = result['suggestions']['ai_plan']
        self.assertEqual({op['id']: op['action'] for op in plan['categories']}, {ids[0]: 'keep', ids[1]: 'keep'})
        self.assertEqual(len(gateway.calls), 1, 'repairing is local; no model call is repeated')


if __name__ == '__main__':
    unittest.main()
