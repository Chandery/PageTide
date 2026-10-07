import copy
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import budget


def configured_fixture():
    """Synthetic accounting contract, not a selected provider or approved operation."""
    config = copy.deepcopy(budget.load())
    config['provider'] = {
        'name': 'synthetic', 'model': 'fixture', 'thinking': 'disabled',
        'price_source': 'TEST-PRICE', 'verified_on': '2026-01-01',
        'recheck_after_days': 30,
        'usd_per_million': {'input_miss': '0.30', 'input_hit': '0.006', 'output': '1.20'},
    }
    config['operations'] = {
        'batch': {'prompt': 'prompts/batch.md', 'trigger': 'background',
                  'reference': {'input': 100, 'output': 20},
                  'cap': {'input': 200, 'output': 40},
                  'input_cap_components': {'instructions': 50, 'data': 150}},
        'periodic': {'prompt': 'prompts/periodic.md', 'trigger': 'interactive',
                     'reference': {'input': 200, 'output': 40},
                     'cap': {'input': 400, 'output': 80},
                     'input_cap_components': {'instructions': 100, 'data': 300}},
    }
    config['scenarios'] = [{'id': 'fixture', 'label': 'Synthetic only', 'days': 30,
                            'weekly_runs': 5, 'daily_calls': {'batch': 1},
                            'weekly_calls': {'periodic': 1}, 'one_off_calls': {}}]
    config['policy'].update(daily_background_tokens=500, daily_interactive_tokens=500,
                            daily_total_tokens=800, monthly_total_tokens=10000,
                            daily_usd='0.01', monthly_usd='0.10', max_retries_per_operation=1)
    return config


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.config = configured_fixture()

    def test_current_plan_is_owner_approved_but_not_enforced(self):
        config = budget.load()
        budget.validate(config)
        # Ceilings are owner-approved including the raised hybrid-rerank scope, but the runtime
        # enforcement release evidence and tokenizer parity remain unverified; llm_rerank stays default-off.
        self.assertIsNotNone(config['provider'])
        self.assertTrue(config['operations'])
        self.assertIs(config['approved_by_owner'], True)
        self.assertEqual(config['pending_approval'], [])
        for name in ('route_growth_judge','route_map_create','route_map_revision'):
            self.assertTrue(config['operations'][name]['owner_approved'])
            self.assertIn('授权啊，全都授权',config['operations'][name]['approval_note'])
            self.assertFalse(config['operations'][name]['enabled_by_default'])
        self.assertIn('llm_rerank', config['operations'])
        self.assertIs(config['operations']['llm_rerank']['enabled_by_default'], False)
        self.assertIs(config['policy']['runtime_enforcement_implemented'], False)
        self.assertIs(config['policy']['tokenizer_parity_verified'], False)
        zero = next(s for s in config['scenarios'] if s['id'] == 'core_zero_token')
        self.assertEqual(budget.scenario_totals(config, zero, 'cap')['tokens'], 0)
        self.assertEqual(budget.scenario_totals(config, zero, 'reference')['usd'], Decimal(0))
        self.assertEqual(budget.cost(config, 0, 0), 0)
        self.assertGreater(budget.cost(config, 1, 0), 0)

    def test_registered_proposal_daily_minimum_and_stress(self):
        config = budget.load()
        starter = next(s for s in config['scenarios'] if s['id'] == 'daily_triage_starter')
        day = budget.peak_day(config, starter, 'reference')
        self.assertGreater(day['tokens'], 0)
        self.assertLess(day['tokens'], config['policy']['daily_total_tokens'])
        self.assertEqual(budget.violations(config, starter, 'cap'), [])
        heavy = next(s for s in config['scenarios'] if s['id'] == 'heavy_retry_stress')
        self.assertIn('daily_total_tokens', budget.violations(config, heavy, 'cap'))
        hybrid = next(s for s in config['scenarios'] if s['id'] == 'hybrid_llm_rerank')
        self.assertEqual(budget.violations(config, hybrid, 'cap'), [])

    def test_evaluation_annotator_is_separate_and_token_only(self):
        config = budget.load()
        budget.validate(config)
        evaluation = config['evaluation']
        # The judge is a different provider and is never a runtime operation.
        self.assertIs(evaluation['provider']['price_verifiable'], False)
        self.assertNotIn('judge_relevance', config['operations'])
        self.assertTrue(evaluation['operations'])
        rendered = budget.render(config)
        self.assertIn('离线评估标注', rendered)
        self.assertIn(f"{evaluation['provider']['observed_hidden_input_tokens']:,}", rendered)
        # Claiming verifiable annotator prices must fail until a public source exists.
        bad = copy.deepcopy(config)
        bad['evaluation']['provider']['price_verifiable'] = True
        with self.assertRaises(ValueError):
            budget.validate(bad)
        # Hidden prefix is charged to every evaluation call.
        bad = copy.deepcopy(config)
        bad['evaluation']['scenarios'][0]['calls'] = {'judge_relevance': 10}
        prefix = evaluation['provider']['observed_hidden_input_tokens']
        cap_in = evaluation['operations']['judge_relevance']['cap']['input']
        self.assertIn(f"{10 * (cap_in + prefix):,}", budget.render(bad))
        # Unregistered evaluation operations are rejected.
        bad = copy.deepcopy(config)
        bad['evaluation']['scenarios'][0]['calls'] = {'hidden': 1}
        with self.assertRaises(ValueError):
            budget.validate(bad)

    def test_provider_absent_cannot_hide_calls_or_limits(self):
        honest = budget.load()
        honest['provider'] = None
        honest['operations'] = {}
        honest['scenarios'] = [{'id': 'none', 'label': 'none', 'days': 30, 'weekly_runs': 0,
                                'daily_calls': {}, 'weekly_calls': {}, 'one_off_calls': {}}]
        honest['policy'].update(daily_background_tokens=0, daily_interactive_tokens=0,
                                daily_total_tokens=0, monthly_total_tokens=0,
                                daily_usd='0', monthly_usd='0', max_retries_per_operation=0)
        budget.validate(honest)
        mutations = [lambda c: c.update(operations=self.config['operations']),
                     lambda c: c['policy'].update(daily_total_tokens=1),
                     lambda c: c['policy'].update(monthly_usd='0.01'),
                     lambda c: c['policy'].update(max_retries_per_operation=1),
                     lambda c: c['policy'].update(tokenizer_parity_verified=True),
                     lambda c: c['policy'].update(runtime_enforcement_implemented=True)]
        for mutate in mutations:
            config = copy.deepcopy(honest)
            mutate(config)
            with self.subTest(config=config), self.assertRaises(ValueError):
                budget.validate(config)

    def test_configured_contract_valid(self):
        budget.validate(self.config)

    def test_calendar_and_peak_are_not_prorated(self):
        scenario = self.config['scenarios'][0]
        total = budget.scenario_totals(self.config, scenario, 'reference')
        self.assertEqual((total['input'], total['output'], total['tokens']), (4000, 800, 4800))
        self.assertEqual(total['usd'], Decimal('0.00216'))
        self.assertEqual(budget.peak_day(self.config, scenario, 'cap')['tokens'], 720)
        scenario['one_off_calls'] = {'batch': 1}
        self.assertEqual(budget.peak_day(self.config, scenario, 'cap')['tokens'], 960)
        self.assertIn('daily_total_tokens', budget.violations(self.config, scenario, 'cap'))

    def test_retry_and_monthly_demand_not_authorization(self):
        scenario = self.config['scenarios'][0]
        scenario['daily_calls']['batch'] = 3
        errors = budget.violations(self.config, scenario, 'cap')
        self.assertIn('daily_background_tokens', errors)
        self.assertIn('daily_total_tokens', errors)
        self.assertIn('monthly_total_tokens', errors)
        self.config['policy'].update(daily_usd='0', monthly_usd='0')
        errors = budget.violations(self.config, scenario, 'cap')
        self.assertIn('daily_usd', errors)
        self.assertIn('monthly_usd', errors)

    def test_unregistered_calls_and_empty_configured_operations_rejected(self):
        self.config['scenarios'][0]['daily_calls']['hidden'] = 1
        with self.assertRaises(ValueError):
            budget.validate(self.config)
        self.config['operations'] = {}
        with self.assertRaises(ValueError):
            budget.validate(self.config)

    def test_envelope_reference_and_duplicate_prompt_rejected(self):
        for change in [lambda c: c['operations']['batch']['input_cap_components'].update(data=151),
                       lambda c: c['operations']['batch']['reference'].update(output=41),
                       lambda c: c['operations']['periodic'].update(prompt='prompts/batch.md')]:
            config = copy.deepcopy(self.config)
            change(config)
            with self.assertRaises(ValueError):
                budget.validate(config)

    def test_reasoning_fallback_and_cache_discount_not_default(self):
        for change in [lambda c: c['provider'].update(thinking='enabled'),
                       lambda c: c['policy'].update(automatic_model_fallback=True),
                       lambda c: c['policy'].update(cache_savings_assumed=True)]:
            config = copy.deepcopy(self.config)
            change(config)
            with self.assertRaises(ValueError):
                budget.validate(config)

    def test_invalid_money_and_counts(self):
        for value in ['NaN', 'Infinity', '-0.1']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                budget.money(value, 'price')
        for value in [True, -1, 1.5]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                budget.integer(value, 'tokens')

    def test_cache_cost_not_zero(self):
        cold = budget.cost(self.config, 1000, 100)
        hit = budget.cost(self.config, 1000, 100, 1000)
        self.assertGreater(hit, 0)
        self.assertLess(hit, cold)
        with self.assertRaises(ValueError):
            budget.cost(self.config, 100, 10, 101)

    def test_reasoning_not_double_counted_and_inconsistent_usage_rejected(self):
        usage = {'prompt_tokens': 1000, 'completion_tokens': 200, 'total_tokens': 1200,
                 'prompt_cache_hit_tokens': 400, 'prompt_cache_miss_tokens': 600,
                 'prompt_tokens_details': {'cached_tokens': 400},
                 'completion_tokens_details': {'reasoning_tokens': 50}}
        result = budget.reconcile_usage(self.config, usage)
        self.assertEqual(result['tokens'], 1200)
        self.assertEqual(result['usd'], budget.cost(self.config, 1000, 200, 400))
        for key in ['total_tokens', 'prompt_cache_miss_tokens']:
            bad = copy.deepcopy(usage)
            bad[key] += 1
            with self.assertRaises(ValueError):
                budget.reconcile_usage(self.config, bad)
        for details in [{'prompt_tokens_details': {'cached_tokens': 401}},
                        {'completion_tokens_details': {'reasoning_tokens': 201}}]:
            with self.assertRaises(ValueError):
                budget.reconcile_usage(self.config, dict(usage, **details))
        with self.assertRaises(KeyError):
            budget.reconcile_usage(self.config, {})

    def test_pending_reservations_count_in_arithmetic(self):
        self.assertTrue(budget.can_admit(100, [200], 200, 500))
        self.assertFalse(budget.can_admit(100, [200], 201, 500))

    def test_approval_and_enforcement_require_json_booleans(self):
        for field in ['approved_by_owner', 'runtime_enforcement_implemented', 'tokenizer_parity_verified']:
            config = copy.deepcopy(self.config)
            target = config if field == 'approved_by_owner' else config['policy']
            target[field] = 'false'
            with self.subTest(field=field), self.assertRaises(ValueError):
                budget.validate(config)

    def test_changed_calendar_and_price_render_dynamically(self):
        self.config['scenarios'][0].update(days=28, weekly_runs=4)
        before = budget.render(self.config)
        self.assertIn('28天/4次周任务', before)
        self.config['provider']['usd_per_million']['output'] = '2.40'
        self.assertNotEqual(before, budget.render(self.config))

    def test_invalid_calendar_rejected(self):
        for values in [dict(days=60), dict(weekly_runs=6)]:
            config = copy.deepcopy(self.config)
            config['scenarios'][0].update(**values)
            with self.assertRaises(ValueError):
                budget.validate(config)


if __name__ == '__main__':
    unittest.main()
