"""Independent quota regressions: display causes never decide whether a call was paid.

Every app uses temporary data and a replaced gateway. These cases never send a
request, access the owner's library, or alter real usage/reservations.
"""
from unittest import mock

from tests import test_concept_intro as intro_tests
from tests import test_project_manage as project_tests
from tests import test_route_growth as growth_tests
from tests import test_route_map_model as map_tests
from tests import test_route_plan as plan_tests


def provider_failure(status=503, *, unknown=True, reserved=True):
    return {'ok': False, 'http_status': status, 'reason': f'HTTPError: {status}',
            'usage_unknown': unknown, 'usage_reserved': reserved}


class IntroQuotaTests(intro_tests.Fixture):
    def test_http_unknown_preserves_attempt_and_cause_but_confirmed_4xx_refunds(self):
        with mock.patch.object(self.app.gateway, 'call', return_value=provider_failure(401, unknown=False, reserved=False)) as call:
            refusal = self.app.route_concept_intro(self.pid, self.cid['Epitaxy'])
        self.assertEqual(refusal['attempts_left'], self.app.CONCEPT_INTROS_PER_DAY)
        self.assertEqual(call.call_count, 1)
        with mock.patch.object(self.app.gateway, 'call', return_value=provider_failure()) as call:
            unknown = self.app.route_concept_intro(self.pid, self.cid['Epitaxy'])
        self.assertEqual(unknown['reason_code'], 'http')
        self.assertIn('503', unknown['reason'])
        self.assertEqual(unknown['attempts_left'], self.app.CONCEPT_INTROS_PER_DAY - 1)
        self.assertEqual(self.app.store.get_setting('concept_intro_' + self.pid)['attempts'], 1)
        self.assertEqual(call.call_count, 1)

    def test_reserved_only_flag_cannot_refund_an_http_attempt(self):
        with mock.patch.object(self.app.gateway, 'call', return_value=provider_failure(503, unknown=False)):
            result = self.app.route_concept_intro(self.pid, self.cid['Epitaxy'])
        self.assertEqual(result['attempts_left'], self.app.CONCEPT_INTROS_PER_DAY - 1)


class GrowthQuotaTests(growth_tests.Fixture):
    def test_http_server_failure_keeps_attempt_and_queue_without_an_automatic_retry(self):
        self.say(('s1', 'useful'))
        calls = self.gateway(provider_failure())
        result = self.app.route_direction_judge(self.pid)
        self.assertEqual(result['reason_code'], 'http')
        self.assertIn('503', result['reason'])
        self.assertEqual(result['judges_left'], self.app.DIRECTION_JUDGES_PER_DAY - 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.app.route_candidates(self.pid)['candidates'], [])


class RevisionQuotaTests(map_tests.store_tests.Fixture):
    def test_revision_unknown_http_keeps_attempt_cause_and_existing_map(self):
        self.app.route_save(self.pid, plan=map_tests.store_tests.PLAN)
        before = self.app.route_get(self.pid)
        with mock.patch.object(self.app.gateway, 'call', return_value=provider_failure()) as call:
            result = self.app.route_revision_generate(self.pid, map_tests.BRIEF)
        self.assertEqual(result['reason_code'], 'http')
        self.assertIn('503', result['reason'])
        self.assertEqual(result['attempts_left'], 1)
        self.assertEqual(self.app.store.get_setting('route_revision_attempt_' + self.pid)['attempts'], 1)
        self.assertEqual(self.app.route_get(self.pid), before)
        self.assertEqual(call.call_count, 1)


class LegacySessionQuotaTests(plan_tests.Fixture):
    def test_session_plan_unknown_http_keeps_the_shared_attempt_count(self):
        calls = self.gateway(provider_failure())
        result = self.app.route_plan(self.session)
        self.assertEqual(result['reason_code'], 'http')
        self.assertIn('503', result['reason'])
        self.assertEqual(self.app.route_plan_state(self.session)['attempts'], 1)
        self.assertIsNone(self.app.route_plan_state(self.session)['plan'])
        self.assertEqual(len(calls), 1)


class LegacyProjectQuotaTests(project_tests.Fixture):
    def test_existing_project_plan_unknown_http_keeps_attempt_and_existing_map(self):
        self.app.route_save(self.pid, plan=project_tests.BRANCHED)
        before = self.app.route_get(self.pid)
        calls = self.gateway(provider_failure())
        result = self.app.route_plan_project(self.pid, '学习外延与半导体生长')
        self.assertEqual(result['reason_code'], 'http')
        self.assertIn('503', result['reason'])
        self.assertEqual(result['attempts_left'], self.app.PROJECT_PLANS_PER_DAY - 1)
        self.assertEqual(self.app.store.get_setting('route_plan_project_' + self.pid)['attempts'], 1)
        self.assertEqual(self.app.route_get(self.pid), before)
        self.assertEqual(len(calls), 1)
