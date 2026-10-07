"""AI review jobs are bounded, unretried, all-or-nothing proposal generation."""
import copy
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import operation_lock
from app.category_review_service import run_review
from app.organization import Conflict
from app.organization_facets import structure_hash


class FakeOrganization:
    def __init__(self, papers, directions=None, memberships=None):
        self.papers = papers
        self.revision = 4
        self.data = {'directions': directions or [], 'memberships': memberships or {}, 'reviewed': {}}
        self.stored = []

    def _transaction(self, write=True):
        return nullcontext()

    def _load(self):
        return self.revision, copy.deepcopy(self.data)

    def _corpus(self, scope=None):
        return copy.deepcopy(self.papers)

    def _snapshot(self):
        return {'revision': self.revision, 'directions': copy.deepcopy(self.data['directions']),
                'items': [{**p, 'directions': self.data['memberships'].get(p['key'], []),
                           'note': 'PRIVATE_NOTE_SENTINEL'} for p in self.papers]}

    def snapshot(self):
        return self._snapshot()

    def store_ai_review(self, plan, revision, corpusfp, structure, scope):
        if revision != self.revision or structure != structure_hash(self.data['directions'], self.data['memberships']):
            raise Conflict('stale plan')
        self.stored.append(copy.deepcopy(plan))
        return {**self._snapshot(), 'suggestions': {'source': 'ai', 'ai_plan': plan,
                                                   'review_stats': plan['stats'], 'fingerprint': corpusfp}}


class FakeGateway:
    config = {'provider': {'model': 'deepseek-flash'}}

    def __init__(self, response=None):
        self.calls = []
        self.response = response

    def call(self, operation, messages, dry_run=False):
        self.calls.append((operation, copy.deepcopy(messages), dry_run))
        if dry_run:
            return {'ok': True, 'dry_run': True, 'reservation': {'input': 8000, 'output': 2000, 'usd': '0.0048'}}
        request = json.loads(messages[-1]['content'])
        value = {'categories': [{'id': c['id'], 'action': 'keep', 'reason': '保留现有研究方向'}
                                for c in request['categories']],
                 'papers': [{'id': p['id'], 'categories': p['categories'], 'reason': '核验标题摘要'}
                            for p in request['papers']], 'new_categories': []}
        if self.response:
            custom = self.response(len(self.calls), request, value)
            if custom is not None:
                return custom
        return {'ok': True, 'content': json.dumps(value, ensure_ascii=False), 'finish_reason': 'stop',
                'usage': {'total_tokens': 100}, 'usd': '0.000048'}


class CategoryReviewServiceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = SimpleNamespace(data=Path(tmp.name), store=object(), gateway=FakeGateway())
        self.profile = {'pinned': ['PRIVATE_PROFILE_SENTINEL'], 'project': 'PRIVATE_PROJECT_SENTINEL'}
        self.papers = [{'key': f'private-paper-{i:02}', 'title': f'World model video paper {i}',
                        'abstract': 'Video world model planning.', 'note': 'PRIVATE_NOTE_SENTINEL'}
                       for i in range(25)]
        self.org = FakeOrganization(self.papers, [{'id': 'private-world-id', 'name': '世界模型', 'parent_id': None}])
        self.addCleanup(patch.stopall)
        patch('app.category_review_service.Organization', return_value=self.org).start()

    def review(self, **kwargs):
        return run_review(self.app, 'private-project-id', self.profile, **kwargs)

    def test_all_placed_and_unplaced_papers_are_reviewed_in_unretried_bounded_batches(self):
        self.org.data['memberships'][self.papers[0]['key']] = ['private-world-id']
        result = self.review()
        self.assertEqual(len(self.app.gateway.calls), 3)
        sizes = [len(json.loads(messages[-1]['content'])['papers']) for _, messages, _ in self.app.gateway.calls]
        self.assertEqual(sizes, [12, 12, 1])
        self.assertEqual([op for op, _, _ in self.app.gateway.calls], ['category_review'] * 3)
        plan = self.org.stored[0]
        self.assertEqual({p['key'] for p in plan['papers']}, {p['key'] for p in self.papers})
        self.assertEqual(result['ai_review']['processed_papers'], 25)
        self.assertEqual(result['ai_review']['remaining_papers'], 0)
        self.assertEqual(result['ai_review']['total_tokens'], 300)
        self.assertEqual(self.org.data['memberships'][self.papers[0]['key']], ['private-world-id'])

    def test_public_metadata_and_local_aliases_only_enter_the_wire(self):
        self.review()
        wire = json.dumps(self.app.gateway.calls, ensure_ascii=False)
        for private in ('PRIVATE_NOTE_SENTINEL', 'PRIVATE_PROFILE_SENTINEL', 'PRIVATE_PROJECT_SENTINEL',
                        'private-project-id', 'private-world-id', 'private-paper-00'):
            self.assertNotIn(private, wire)

    def test_every_batch_carries_the_complete_category_directory(self):
        self.org.data['directions'] = [{'id': f'private-cat-{i}', 'name': f'方向{i}', 'parent_id': None} for i in range(60)]
        result = self.review()
        self.assertEqual(result['ai_review']['status'], 'complete')
        self.assertTrue(all(len(json.loads(m[-1]['content'])['categories']) == 60 for _, m, _ in self.app.gateway.calls))

    def test_new_aliases_are_stable_across_batches_and_identical_categories_are_unified(self):
        def add_new(index, request, value):
            ref = f'n{index}'
            value['new_categories'] = [{'id': ref, 'name': '视频世界模型', 'parent': 'c1', 'reason': '视频预测证据'}]
            for p in value['papers']:
                p['categories'] = [ref]
        self.app.gateway.response = add_new
        self.review()
        plan = self.org.stored[0]
        self.assertEqual(len(plan['new_categories']), 1)
        identifier = plan['new_categories'][0]['id']
        self.assertTrue(all(p['categories'] == [identifier] for p in plan['papers']))
        self.assertNotEqual(identifier, 'n1')

    def test_budget_refusal_after_one_batch_stops_without_saving_a_partial_plan(self):
        self.app.gateway.response = lambda i, req, out: {'ok': False, 'reason': 'daily budget exceeded'} if i == 2 else None
        result = self.review()
        self.assertEqual(len(self.app.gateway.calls), 2)
        self.assertEqual(self.org.stored, [])
        self.assertEqual((result['ai_review']['processed_papers'], result['ai_review']['remaining_papers']), (12, 13))
        self.assertEqual(result['suggestions']['source'], 'local')
        self.assertFalse(result['suggestions']['stored'])
        self.assertIn('daily budget', result['ai_review']['error'])
        self.assertEqual(self.org.data['reviewed'], {})

    def test_category_action_conflicts_across_batches_reject_the_entire_plan(self):
        def conflict(index, request, value):
            if index == 2:
                value['categories'][0].update(action='rename', name='研究路线')
        self.app.gateway.response = conflict
        result = self.review()
        self.assertEqual(result['ai_review']['status'], 'failed')
        self.assertEqual(len(self.app.gateway.calls), 2)
        self.assertEqual(self.org.stored, [])
        self.assertIn('冲突', result['ai_review']['error'])

    def test_delete_with_an_archived_or_out_of_scope_member_is_rejected(self):
        self.org.data['memberships'] = {'archived-paper-key': ['private-world-id']}
        def delete(index, request, value):
            value['categories'][0]['action'] = 'delete'
        self.app.gateway.response = delete
        result = self.review()
        self.assertEqual(result['ai_review']['status'], 'failed')
        self.assertEqual(self.org.stored, [])
        self.assertIn('归档', result['ai_review']['error'])

    def test_delete_reassigns_all_reviewed_papers_explicitly_before_preview_storage(self):
        self.org.data['memberships'] = {p['key']: ['private-world-id'] for p in self.papers}
        def delete(index, request, value):
            value['categories'][0]['action'] = 'delete'
            for p in value['papers']:
                p['categories'] = []
        self.app.gateway.response = delete
        self.review()
        self.assertEqual(self.org.stored[0]['categories'][0]['action'], 'delete')
        self.assertTrue(all(p['categories'] == [] for p in self.org.stored[0]['papers']))

    def test_truncated_reply_is_not_applied_or_retried(self):
        self.app.gateway.response = lambda *args: {'ok': True, 'content': '{}', 'finish_reason': 'length', 'usage': {'total_tokens': 2000}}
        result = self.review()
        self.assertEqual(len(self.app.gateway.calls), 1)
        self.assertEqual(self.org.stored, [])
        self.assertIn('截断', result['ai_review']['error'])

    def test_concurrent_edit_invalidates_a_completed_reply_and_stops_more_calls(self):
        def change(index, request, value):
            self.org.revision += 1
        self.app.gateway.response = change
        result = self.review()
        self.assertEqual(len(self.app.gateway.calls), 1)
        self.assertEqual(result['ai_review']['status'], 'failed')
        self.assertEqual(self.org.stored, [])

    def test_invalid_or_excessive_category_directory_fails_before_a_provider_call(self):
        self.org.data['directions'] = [{'id': str(i), 'name': str(i), 'parent_id': None} for i in range(61)]
        result = self.review()
        self.assertEqual(self.app.gateway.calls, [])
        self.assertEqual(result['ai_review']['status'], 'failed')
        self.assertEqual(self.org.stored, [])

    def test_empty_scope_can_review_labels_but_cannot_delete_nonempty_categories(self):
        self.org.papers = []
        self.org.data['memberships'] = {'outside': ['private-world-id']}
        self.app.gateway.response = lambda i, req, out: out['categories'][0].update(action='delete')
        result = self.review()
        self.assertEqual(len(self.app.gateway.calls), 1)
        self.assertEqual(result['ai_review']['status'], 'failed')
        self.assertEqual(self.org.stored, [])

    def test_unknown_usage_stays_unknown_in_returned_job_statistics(self):
        real = self.app.gateway.call
        def without_usage(*args, **kwargs):
            result = real(*args, **kwargs)
            result.pop('usage', None)
            return result
        self.app.gateway.call = without_usage
        result = self.review()
        self.assertIsNone(result['ai_review']['total_tokens'])
        self.assertFalse(result['ai_review']['tokens_known'])

    def test_gateway_unknown_usage_success_does_not_mistake_reserved_cap_for_measurement(self):
        real = self.app.gateway.call
        def reserved_usage(*args, **kwargs):
            result = real(*args, **kwargs)
            # Gateway's exact successful-but-unreconciled result shape.
            result.update(usage_unknown=True, usage={'total_tokens': 10000})
            return result
        self.app.gateway.call = reserved_usage
        result = self.review()
        self.assertIsNone(result['ai_review']['total_tokens'])
        self.assertFalse(result['ai_review']['tokens_known'])
        self.assertEqual(result['ai_review']['status'], 'failed')
        self.assertEqual(len(self.app.gateway.calls), 1)
        self.assertEqual(self.org.stored, [])

    def test_dry_run_never_parses_a_response_or_stores_an_ai_plan(self):
        result = self.review(dry_run=True)
        self.assertEqual(result['ai_review']['status'], 'dry_run')
        self.assertEqual(result['ai_review']['processed_papers'], 0)
        self.assertEqual(self.org.stored, [])
        self.assertTrue(all(dry for _, _, dry in self.app.gateway.calls))

    def test_concurrent_duplicate_job_cannot_send_a_second_request(self):
        with operation_lock.claim(self.app.data, 'category-review:default'):
            with self.assertRaisesRegex(ValueError, '正在判断'):
                self.review()
        self.assertEqual(self.app.gateway.calls, [])

    def test_cancelled_before_start_does_not_call_gateway_or_store_a_plan(self):
        result = self.review(cancelled=lambda: True)
        self.assertEqual(result['ai_review']['status'], 'cancelled')
        self.assertEqual(self.app.gateway.calls, [])
        self.assertEqual(self.org.stored, [])

    def test_cancel_after_first_response_stops_later_batches_and_preserves_paid_usage(self):
        stopped = []
        def cancel_after_response(index, request, value):
            stopped.append(True)
        self.app.gateway.response = cancel_after_response
        result = self.review(cancelled=lambda: bool(stopped))
        self.assertEqual(result['ai_review']['status'], 'cancelled')
        self.assertEqual(len(self.app.gateway.calls), 1)
        self.assertEqual(self.org.stored, [])
        self.assertEqual(result['ai_review']['total_tokens'], 100)


if __name__ == '__main__':
    unittest.main()
