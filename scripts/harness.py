#!/usr/bin/env python3
"""Repository traceability checks. These do not certify application behavior."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

import budget

ROOT = Path(__file__).resolve().parents[1]
LEVELS = {'docs': 0, 'standard': 1, 'feature': 2, 'critical': 3}
CRITICAL = ('AGENTS.md', '.agents/', 'harness/', 'scripts/', 'prompts/',
            'src/main/ipc/', 'src/main/model-gateway/', 'src/main/security/',
            'src/main/storage/migrations/', 'src/main/backup/', 'docs/BUDGET',
            '.githooks/', '.github/', 'docs/HARNESS.md', 'docs/ARCHITECTURE.md',
            'tests/test_budget.py', 'tests/test_harness.py')
CHECK_COMMANDS = {
    'budget': 'python3 scripts/budget.py --check',
    'repository': 'python3 scripts/harness.py check',
    'tests': 'python3 -m unittest discover -s tests -v',
    'app-tests': 'npm run test:app',
}
EXCLUDED = {'.git', '.local', 'node_modules', '__pycache__', 'data', 'dist', 'out'}


def read_json(root, path):
    return json.loads((root / path).read_text())


def local_file(root, path):
    target = (root / path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return False
    return target.is_file()


def files(root):
    return [p for p in root.rglob('*') if p.is_file() and not EXCLUDED.intersection(p.relative_to(root).parts)]


def classify(paths):
    if any(p.startswith(CRITICAL) for p in paths):
        return 'critical'
    if paths and all(p.endswith('.md') or p.startswith(('changes/', 'docs/evidence/')) for p in paths):
        return 'docs'
    return 'standard'


def changed_paths(root=ROOT):
    def git(*args):
        result = subprocess.run(['git', *args], cwd=root, capture_output=True, check=True)
        return {s.decode('utf-8') for s in result.stdout.split(b'\0') if s}
    # --no-renames includes both sides so a protected path cannot disappear unnoticed.
    return sorted(git('diff', '--no-renames', '--name-only', '-z') |
                  git('diff', '--cached', '--no-renames', '--name-only', '-z') |
                  git('ls-files', '--others', '--exclude-standard', '-z'))


def check_links(root):
    errors = []
    for path in files(root):
        if path.suffix != '.md':
            continue
        text = path.read_text()
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            url = link.split('#', 1)[0]
            if not url or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', url):
                continue
            if not (path.parent / unquote(url)).is_file():
                errors.append(f'{path.relative_to(root)}: missing file link {link}')
    return errors


def check_tasks(root):
    errors = []
    task_data = read_json(root, 'harness/tasks.json')
    tasks = task_data['tasks']
    if type(task_data['approved_for_implementation']) is not bool:
        errors.append('implementation approval must be a JSON boolean')
    reqs = read_json(root, 'harness/requirements.json')['requirements']
    evals = read_json(root, 'harness/evaluations.json')['evaluations']
    stages = task_data.get('stages')
    if (not isinstance(stages, list) or not stages
            or not all(isinstance(stage, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', stage) for stage in stages)
            or len(set(stages)) != len(stages)):
        errors.append('invalid stage registry: declare nonempty unique stage names')
        stages = []
    mapping = {t['id']: t for t in tasks}
    req_ids, eval_ids = {r['id'] for r in reqs}, {e['id'] for e in evals}
    if len(mapping) != len(tasks) or len(req_ids) != len(reqs) or len(eval_ids) != len(evals):
        errors.append('duplicate task/requirement/evaluation ID')
    covered = set()
    referenced_gates = set()
    for task in tasks:
        tid = task['id']
        if task['status'] not in ('planned', 'in_progress', 'blocked', 'review', 'done'):
            errors.append(f'{tid}: invalid status')
        if not task['acceptance'] or not task['requirements']:
            errors.append(f'{tid}: missing acceptance or requirement')
        if task['stage'] not in stages:
            errors.append(f'{tid}: unknown stage')
        covered.update(task['requirements'])
        if set(task['requirements']) - req_ids:
            errors.append(f'{tid}: unknown requirement')
        if task['status'] == 'blocked' and not task.get('blocked_reason'):
            errors.append(f'{tid}: blocked without reason')
        if task['status'] == 'done' and not task['evidence']:
            errors.append(f'{tid}: done without evidence')
        for evidence in task['evidence']:
            if not local_file(root, evidence):
                errors.append(f'{tid}: missing evidence {evidence}')
        for dep in task['depends_on']:
            if dep not in mapping:
                errors.append(f'{tid}: unknown dependency {dep}')
            elif task['status'] == 'done' and mapping[dep]['status'] != 'done':
                errors.append(f'{tid}: completed ahead of prerequisite {dep}')
    visiting, done = set(), set()
    def visit(tid):
        if tid in visiting:
            errors.append(f'task dependency cycle at {tid}')
            return
        if tid in done or tid not in mapping:
            return
        visiting.add(tid)
        for dep in mapping[tid]['depends_on']:
            visit(dep)
        visiting.remove(tid)
        done.add(tid)
    for tid in mapping:
        visit(tid)
    for req in reqs:
        if req['id'] not in covered or not req['gates'] or set(req['gates']) - eval_ids:
            errors.append(f"{req['id']}: incomplete task/evaluation traceability")
        referenced_gates.update(req['gates'])
    for ev in evals:
        if ev['id'] not in referenced_gates:
            errors.append(f"{ev['id']}: evaluation is not referenced by any requirement")
        if type(ev['blocks_release']) is not bool:
            errors.append(f"{ev['id']}: blocking flag must be a JSON boolean")
        if ev['status'] not in ('not_run', 'passed', 'failed', 'blocked'):
            errors.append(f"{ev['id']}: invalid evaluation status")
        if ev['status'] == 'passed' and not ev['evidence']:
            errors.append(f"{ev['id']}: passed without evidence")
        for path in ev['evidence']:
            if not local_file(root, path):
                errors.append(f"{ev['id']}: missing evidence {path}")
    return errors


def check_sources(root, today):
    errors, stale = [], []
    sources = read_json(root, 'harness/sources.json')['sources']
    ids = {s['id'] for s in sources}
    if len(ids) != len(sources):
        errors.append('duplicate source ID')
    provider = budget.load(root)['provider']
    dated = sources + ([dict(provider, id='budget.provider')] if provider is not None else [])
    for source in dated:
        verified = dt.date.fromisoformat(source['verified_on'])
        interval = source['recheck_after_days']
        if verified > today:
            errors.append(f"{source['id']}: verification date is in the future")
        if type(interval) is not int or interval <= 0:
            errors.append(f"{source['id']}: recheck interval must be a positive integer")
        elif (today - verified).days > interval:
            stale.append(source['id'])
    for source in sources:
        if not source['url'].startswith('https://') or not source['verification']:
            errors.append(f"{source['id']}: invalid source evidence")
    if provider is not None and provider['price_source'] not in ids:
        errors.append('budget references unknown price source')
    return errors, stale


def check_prompts_and_skills(root):
    errors = []
    config = budget.load(root)
    evaluation = config.get('evaluation') or {}
    declared = {op['prompt'] for op in config['operations'].values()}
    declared |= {op['prompt'] for op in evaluation.get('operations', {}).values()}
    actual_files = [p for p in (root / 'prompts').rglob('*') if p.is_file()]
    actual = {p.relative_to(root).as_posix() for p in actual_files if p.suffix == '.md'}
    if any(p.suffix != '.md' for p in actual_files):
        errors.append('unsupported prompt file type; register Markdown contracts only')
    if declared != actual:
        errors.append(f'prompt registry mismatch: {sorted(declared ^ actual)}')
    all_ops = dict(config['operations'])
    all_ops.update(evaluation.get('operations', {}))
    for op_id, op in all_ops.items():
        if local_file(root, op['prompt']) and f'operation: {op_id}' not in (root / op['prompt']).read_text():
            errors.append(f'{op_id}: prompt operation header mismatch')
    skills = list((root / '.agents/skills').glob('*/SKILL.md'))
    if len(skills) != 4:
        errors.append('expected four project workflow skills')
    for skill in skills:
        text = skill.read_text()
        if not text.startswith('---\n') or f'name: {skill.parent.name}\n' not in text:
            errors.append(f'{skill}: invalid skill name/frontmatter')
        if not re.search(r'^description: .+', text, re.M):
            errors.append(f'{skill}: missing skill trigger description')
        description = re.search(r'^description: (.+)$', text, re.M)
        if description and len(description.group(1)) > 1024:
            errors.append(f'{skill}: description exceeds the 1024-character skill budget')
    return errors


def check_release(root):
    errors = []
    config = budget.load(root)
    task_data = read_json(root, 'harness/tasks.json')
    if config['approved_by_owner'] is not True:
        errors.append('release: owner budget approval missing')
    if task_data['approved_for_implementation'] is not True:
        errors.append('release: implementation approval missing')
    for ev in read_json(root, 'harness/evaluations.json')['evaluations']:
        if type(ev['blocks_release']) is not bool:
            errors.append(f"release: {ev['id']} blocking flag must be a JSON boolean")
        elif ev['blocks_release'] and ev['status'] != 'passed':
            errors.append(f"release: {ev['id']} is {ev['status']}")
    if config['policy']['runtime_enforcement_implemented'] is not True:
        errors.append('release: application budget enforcement is not implemented')
    if config['policy']['tokenizer_parity_verified'] is not True:
        errors.append('release: provider counting/usage calibration missing')
    return errors


def check_record(root, record, paths, release=False):
    errors = []
    if type(record.get('schema_version')) is not int or record['schema_version'] != 1 or record.get('class') not in LEVELS:
        return ['invalid change record schema/class']
    if not isinstance(record.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', record['id']):
        errors.append('missing or invalid record id')
    if type(record.get('owner_approved')) is not bool:
        errors.append('owner approval must be a JSON boolean')
    if LEVELS[record['class']] < LEVELS[classify(paths)]:
        errors.append('change class below path-based minimum')
    recorded_files = record.get('files', [])
    if not isinstance(recorded_files, list) or not all(isinstance(p, str) for p in recorded_files):
        errors.append('files must be a list of paths')
    elif len(set(recorded_files)) != len(recorded_files) or set(recorded_files) != set(paths):
        errors.append('change record must cover exact current changed paths; refresh after edits')
    impact = record.get('budget_impact', {})
    if not isinstance(impact, dict):
        return errors + ['budget impact must be an object']
    if not record.get('summary') or not impact.get('rationale'):
        errors.append('missing summary or budget impact rationale')
    if impact.get('runtime') not in ('zero', 'changed', 'not_applicable'):
        errors.append('missing or invalid runtime impact classification')
    if record['class'] != 'docs' and (not impact.get('before') or not impact.get('after')):
        errors.append('before/after budget impact is required for non-doc changes')
    if impact.get('runtime') == 'changed':
        quantified = impact.get('quantified', {})
        try:
            if not quantified['period']:
                raise ValueError('missing period')
            for side in ('before', 'after'):
                budget.integer(quantified[side]['input_tokens'], side)
                budget.integer(quantified[side]['output_tokens'], side)
                budget.money(quantified[side]['usd'], side)
        except (KeyError, TypeError, ValueError):
            errors.append('changed runtime requires quantified before/after input/output/USD and period')
    task_ids = {t['id'] for t in read_json(root, 'harness/tasks.json')['tasks']}
    if not record.get('tasks') or set(record['tasks']) - task_ids:
        errors.append('missing or unknown change task')
    checks = record.get('checks', [])
    required = {'repository'}
    if record['class'] != 'docs':
        required.add('tests')
    if record['class'] in ('feature', 'critical'):
        required.add('budget')
    categories = set()
    for check in checks:
        category = check.get('category')
        categories.add(category)
        if category not in CHECK_COMMANDS or check.get('command') != CHECK_COMMANDS.get(category):
            errors.append('check category requires its registered command, not arbitrary success text')
        evidence = check.get('evidence', '')
        if (type(check.get('exit_code')) is not int or not isinstance(evidence, str)
                or not evidence.startswith('docs/evidence/') or not local_file(root, evidence)
                or (root / evidence).stat().st_size == 0):
            errors.append('invalid command evidence; use a nonempty sanitized evidence artifact')
        elif check['exit_code'] != 0:
            errors.append('a recorded check failed')
    if required - categories:
        errors.append('missing required check categories: ' + ', '.join(sorted(required - categories)))
    reviews = record.get('reviews', [])
    def reviewed(kind):
        return any(r.get('kind') == kind and r.get('result') == 'passed'
                   and r.get('reviewer') and r.get('evidence')
                   and local_file(root, r['evidence']) for r in reviews)
    if not reviewed('self'):
        errors.append('self-review evidence missing')
    if release and record['class'] in ('feature', 'critical') and not reviewed('independent'):
        errors.append('release requires independent review evidence')
    if release and record.get('owner_approved') is not True:
        errors.append('release approval missing')
    return errors


def run_check(root=ROOT, strict=False, release=False, today=None):
    errors = []
    today = today or dt.datetime.now(dt.timezone.utc).date()
    required = ['AGENTS.md', 'README.md', 'docs/HANDOFF.md', 'docs/FEASIBILITY.md', 'docs/HARNESS.md']
    errors += [f'missing required file: {p}' for p in required if not local_file(root, p)]
    if local_file(root, 'AGENTS.md') and len((root / 'AGENTS.md').read_text().splitlines()) > 110:
        errors.append('AGENTS.md exceeds 110-line navigation budget')
    config = budget.load(root)
    budget.validate(config)
    generated = root / 'docs/BUDGET.generated.md'
    if not generated.exists() or generated.read_text() != budget.render(config):
        errors.append('generated budget differs from machine-readable baseline')
    errors += check_links(root) + check_tasks(root) + check_prompts_and_skills(root)
    source_errors, stale = check_sources(root, today)
    errors += source_errors
    if stale:
        if strict or release:
            errors.append('external sources need recheck: ' + ', '.join(stale))
        else:
            print('WARN external sources need recheck: ' + ', '.join(stale))
    if release:
        errors += check_release(root)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check')
    check.add_argument('--strict-freshness', action='store_true')
    check.add_argument('--release', action='store_true')
    sub.add_parser('impact')
    review = sub.add_parser('review')
    review.add_argument('record')
    review.add_argument('--release', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'check':
            errors = run_check(strict=args.strict_freshness, release=args.release)
        elif args.command == 'impact':
            paths = changed_paths()
            print(json.dumps({'minimum_class': classify(paths), 'files': paths,
                              'note': 'Semantic risks may require a higher class; this does not inspect code behavior.'}, indent=2))
            return 0
        else:
            record = read_json(ROOT, args.record)
            errors = check_record(ROOT, record, changed_paths(), args.release)
        if errors:
            for error in errors:
                print('FAIL ' + error, file=sys.stderr)
            return 1
        print('PASS repository checks only; app gates/real billing are not implied')
        return 0
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('FAIL harness: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
