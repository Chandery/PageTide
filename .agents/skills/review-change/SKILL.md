---
name: review-change
description: Review any PageTide work unit, from a documentation fix to a critical migration or prompt edit, with proportional records and reproducible evidence.
---
# Review a change

1. Run `git status --short` and `python3 scripts/harness.py impact`. Inspect the actual diff, including untracked files and deleted paths. The tool gives a minimum class, not semantic approval.
2. Create/update one `changes/<id>.json` using `harness/templates/change.json`. One coherent work unit can contain many edits; a typo needs only a short record, not a new ADR.
3. Follow docs/HARNESS.md's class matrix. A one-line prompt, model parameter, migration, IPC or checker change remains critical.
4. Specification pass: does it fulfill the requirement and handle skipped reading, missing evidence, privacy scope and local-first behavior? Identify changed contracts and real callers.
5. Quality pass: tests, data recovery, failure paths, input validation, resources, usage accounting and maintainability. Do not ask an LLM judge to replace deterministic tests.
6. Run the applicable exact commands; record exit codes and sanitized evidence. Never report planned commands as executed. Inspect changed snapshots and generated-budget deltas.
7. For feature/critical work, obtain an independent reviewer before release. The reviewer must not be told to rubber-stamp. Record found defects and fixes; rerun after changes. Two self-reviews do not count as independent.
8. Refresh the exact change file list and run `python3 scripts/harness.py review changes/<id>.json`. This verifies records, not code correctness. If unrelated work exists, isolate or explicitly include it; never delete the owner's work.

Stop if a required check fails, review evidence is stale, the budget is unknown, or required authorization is missing. Record the blocker rather than claiming completion.
