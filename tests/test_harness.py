import datetime as dt
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import harness


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for source in harness.files(harness.ROOT):
            relative = source.relative_to(harness.ROOT)
            if relative.parts[0] in ('scripts', 'changes'):
                continue
            if relative.parts[0] == 'tests' and relative.as_posix() != 'tests/test_route_full_flow.py':
                continue
            dest = self.root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)

    def mutate(self, path, fn):
        p = self.root / path
        data = json.loads(p.read_text())
        fn(data)
        p.write_text(json.dumps(data))

    def test_classification_consequence_not_size(self):
        self.assertEqual(harness.classify(['README.md']), 'docs')
        for path in ['AGENTS.md', 'prompts/paper-qa.md', 'harness/budget.json',
                     'src/main/storage/migrations/001.sql', 'src/main/ipc/files.ts',
                     'docs/HARNESS.md', 'tests/test_budget.py', 'tests/test_harness.py']:
            self.assertEqual(harness.classify([path]), 'critical')
        self.assertEqual(harness.classify(['src/ui/button.tsx']), 'standard')

    def test_declared_stages_are_not_tied_to_legacy_abcd(self):
        def update(data):
            data['stages'] = ['research']
            for task in data['tasks']:
                task['stage'] = 'research'
        self.mutate('harness/tasks.json', update)
        self.assertEqual(harness.check_tasks(self.root), [])

    def test_stage_registry_must_be_nonempty_unique_names(self):
        for value in [[], ['research', 'research'], [''], [True], 'research']:
            self.mutate('harness/tasks.json', lambda d: d.update(stages=value))
            self.assertTrue(any('stage registry' in e for e in harness.check_tasks(self.root)))

    def test_undeclared_stage_is_rejected(self):
        self.mutate('harness/tasks.json', lambda d: d['tasks'][0].update(stage='unregistered-stage'))
        self.assertTrue(any('unknown stage' in e for e in harness.check_tasks(self.root)))

    def test_task_cycle_detected(self):
        self.mutate('harness/tasks.json', lambda d: d['tasks'][0]['depends_on'].append(d['tasks'][0]['id']))
        self.assertTrue(any('cycle' in e for e in harness.check_tasks(self.root)))

    def test_multi_node_task_cycle_detected(self):
        def update(data):
            first, second, third = data['tasks'][:3]
            first['depends_on'] = [third['id']]
            second['depends_on'] = [first['id']]
            third['depends_on'] = [second['id']]
        self.mutate('harness/tasks.json', update)
        self.assertTrue(any('cycle' in e for e in harness.check_tasks(self.root)))

    def test_done_without_evidence_rejected(self):
        self.mutate('harness/tasks.json', lambda d: d['tasks'][0].update(status='done', evidence=[]))
        self.assertTrue(any('done without evidence' in e for e in harness.check_tasks(self.root)))

    def test_unknown_requirement_detected(self):
        self.mutate('harness/tasks.json', lambda d: d['tasks'][0]['requirements'].append('R-FAKE'))
        self.assertTrue(any('unknown requirement' in e for e in harness.check_tasks(self.root)))

    def test_passed_eval_requires_evidence(self):
        self.mutate('harness/evaluations.json', lambda d: d['evaluations'][0].update(status='passed', evidence=[]))
        self.assertTrue(any('passed without evidence' in e for e in harness.check_tasks(self.root)))

    def test_orphan_evaluation_not_referenced_by_requirement(self):
        def update(data):
            for req in data['requirements']:
                req['gates'] = [g for g in req['gates'] if g != 'E-REUSE']
        self.mutate('harness/requirements.json', update)
        self.assertTrue(any('not referenced by any requirement' in e for e in harness.check_tasks(self.root)))

    def test_unregistered_prompt_detected(self):
        (self.root / 'prompts').mkdir(exist_ok=True)
        (self.root / 'prompts/unbudgeted.md').write_text('operation: secret')
        self.assertTrue(any('prompt registry mismatch' in e for e in harness.check_prompts_and_skills(self.root)))

    def test_local_broken_link_detected(self):
        (self.root / 'docs/broken.md').write_text('[broken](does-not-exist.md)')
        self.assertTrue(any('missing file link' in e for e in harness.check_links(self.root)))

    def test_evidence_cannot_escape_repository(self):
        self.assertFalse(harness.local_file(self.root, '../outside.txt'))
        self.assertFalse(harness.local_file(self.root, 'docs'))

    def test_stale_sources_detected_without_network(self):
        errors, stale = harness.check_sources(self.root, dt.date(2027, 10, 1))
        self.assertFalse(errors)
        self.assertIn('ARXIV-SANITY-X', stale)

    def test_release_still_blocked_by_unrun_gates(self):
        errors = harness.check_release(self.root)
        self.assertTrue(any('E-PERFORMANCE' in e for e in errors))
        self.assertTrue(any('enforcement is not implemented' in e for e in errors))
        self.assertTrue(any('E-RANKING' in e for e in errors))
        # Owner approval is recorded, so it must not appear as a blocker any more.
        self.assertFalse(any('implementation approval missing' in e for e in errors))

    def test_record_cannot_downgrade_or_omit_changed_files(self):
        record = {'schema_version': 1, 'class': 'docs', 'summary': 'test', 'files': [],
                  'tasks': [harness.read_json(self.root, 'harness/tasks.json')['tasks'][0]['id']], 'budget_impact': {'rationale': 'test'}, 'checks': [], 'reviews': []}
        errors = harness.check_record(self.root, record, ['harness/budget.json'])
        self.assertTrue(any('below path-based' in e for e in errors))
        self.assertTrue(any('exact current changed paths' in e for e in errors))

    def test_nested_unregistered_prompt_detected(self):
        directory = self.root / 'prompts/nested'
        directory.mkdir(parents=True)
        (directory / 'unbudgeted.md').write_text('operation: hidden')
        self.assertTrue(any('prompt registry mismatch' in e for e in harness.check_prompts_and_skills(self.root)))

    def test_future_provider_verification_rejected(self):
        self.mutate('harness/budget.json', lambda d: d.update(provider={
            'verified_on': '2099-01-01', 'recheck_after_days': 30, 'price_source': 'TEST-PRICE'}))
        errors, _ = harness.check_sources(self.root, dt.date(2026, 9, 10))
        self.assertTrue(any('budget.provider' in e and 'future' in e for e in errors))

    def test_invalid_source_interval_rejected(self):
        for value in [0, -1, True, '30']:
            self.mutate('harness/sources.json', lambda d: d['sources'][0].update(recheck_after_days=value))
            errors, _ = harness.check_sources(self.root, dt.date(2026, 9, 10))
            self.assertTrue(any('positive integer' in e for e in errors))

    def test_string_false_cannot_pass_release_approval(self):
        self.mutate('harness/budget.json', lambda d: d.update(approved_by_owner='false'))
        self.mutate('harness/tasks.json', lambda d: d.update(approved_for_implementation='false'))
        self.assertTrue(any('owner budget approval missing' in e for e in harness.check_release(self.root)))
        self.assertTrue(any('implementation approval missing' in e for e in harness.check_release(self.root)))
        self.assertTrue(any('JSON boolean' in e for e in harness.check_tasks(self.root)))

    def record_fixture(self):
        evidence = self.root / 'docs/evidence/test-fixture.txt'
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text('Synthetic record-validation fixture, not execution evidence.')
        return {'schema_version': 1, 'id': 'test-fixture', 'class': 'critical',
                'summary': 'Fixture', 'files': ['scripts/budget.py'], 'tasks': [harness.read_json(self.root, 'harness/tasks.json')['tasks'][0]['id']],
                'budget_impact': {'runtime': 'not_applicable', 'rationale': 'Fixture only',
                                  'before': 'unchanged', 'after': 'unchanged'},
                'checks': [{'category': key, 'command': command, 'exit_code': 0,
                            'evidence': 'docs/evidence/test-fixture.txt'}
                           for key, command in harness.CHECK_COMMANDS.items()],
                'reviews': [{'kind': kind, 'result': 'passed', 'reviewer': 'synthetic reviewer',
                             'evidence': 'docs/evidence/test-fixture.txt'}
                            for kind in ('self', 'independent')], 'owner_approved': True}

    def test_record_categories_and_impact_required(self):
        record = self.record_fixture()
        self.assertEqual(harness.check_record(self.root, record, record['files'], True), [])
        record['checks'] = [{'category': 'tests', 'command': 'true', 'exit_code': 0, 'evidence': 'README.md'}]
        record['budget_impact'] = {'rationale': 'insufficient'}
        del record['id']
        errors = harness.check_record(self.root, record, record['files'], True)
        self.assertTrue(any('record id' in e for e in errors))
        self.assertTrue(any('runtime impact' in e for e in errors))
        self.assertTrue(any('required check categories' in e for e in errors))
        self.assertTrue(any('registered command' in e for e in errors))

    def test_record_approval_requires_true_boolean(self):
        record = self.record_fixture()
        record['owner_approved'] = 'false'
        errors = harness.check_record(self.root, record, record['files'], True)
        self.assertTrue(any('release approval missing' in e for e in errors))

    def test_changed_impact_requires_quantities(self):
        record = self.record_fixture()
        record['budget_impact']['runtime'] = 'changed'
        errors = harness.check_record(self.root, record, record['files'])
        self.assertTrue(any('quantified' in e for e in errors))

    def test_generated_budget_drift_detected(self):
        (self.root / 'docs/BUDGET.generated.md').write_text('not the budget')
        errors = harness.run_check(self.root, today=dt.date(2026, 9, 10))
        self.assertTrue(any('generated budget differs' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
