# Stage07 backend preview independent review

2026-10-07; baseline d78d589; critical local backend/API work. Stage07 remains in_progress/E07 not_run; UI/model/create/phase08 are outside this completed backend slice.

Independent reviewer: /root/route_logic, separate agent required by review-change skill. Review covered actual dirty code and supported callers, not a second self-rating. No real library, sources or provider calls.

Findings fixed and reprobed:

1. Frozen feedback boundary uses global IDs; project-local max could precede another project's ID and wrongly ignore fresh familiarity. Added max(project max,frozen boundary), preserving prior cutoff; independent cross-project freeze/reset/re-understood repro passed.
2. Repeated too_hard after a semantic reset was deduplicated against isolated old evidence. Both familiarity actions now allow one fresh record; double clicks remain idempotent and interest stays unchanged.
3. Shared Store connection feedback undo could commit a partially saved revision before a late marker error. Undo, freeze/unfreeze and restore-default hold the same Store lock and reject reentrant active transactions. Independent actual two-thread late-marker failure probes and same-thread probes now preserve graph/event; supported separate connections serialize under SQLite.
4. Raw HTTP ordinary json.loads discarded duplicate keys before strict patch validation. /api/route now uses strict JSON at raw boundary, refusing nested/root duplicates and nonfinite values. New operations require explicit project ID and known request fields.
5. Old editor c# allocation reused a deleted highest identity and transferred watch to an unrelated new task. New-node allocation uses fresh identities; rename still preserves watch. Delete/add and reloaded-draft Node regressions passed.
6. Full-suite diagnosis found five weekly-report fixture setups with uncommitted direct SQL date changes before feedback. Fixture preparation now commits before the service starts its transaction; idle guard and business assertions remain. Independent26 weekly tests passed.

Independent final combination:228 Python tests,75 Node editor/i18n tests, budget/harness/diff checks, all exit0. Actual commands:

- PYTHONPATH=tests python3 -m unittest test_route_revision_service test_route_revision_http test_route_revision test_route_goal test_route_store test_route_batches test_growth_evidence test_growth_proposals test_profile_redesign test_profile_core_chain -q
- node --test tests/test_route_editor.cjs tests/test_i18n.cjs
- PYTHONPATH=tests python3 -m unittest test_weekly_detail -q

Reviewer explicitly reported no remaining P1/P2 for this backend slice. Packaged verification extension was statically reviewed; the implementer must still execute it against a fresh bundle. Full release gates, real model quality/usage, native-window flow and reference-machine resources remain unmeasured. New budgets/operations are not approved by this review.

Implementer final evidence:1418 full Python,242 full Node, fresh backend/Tauri build and actual newly bundled backend isolation flow all exit0; see checks.txt. No claim of native window or complete stage07 acceptance.
