# Stage07 local revision contract review

Scope: app/route_revision.py, explicit pathgraph validation and regression tests; base4937ad1. This is a foundation work unit, not a completed stage07 or release.

Independent reviewer `/root/route_logic` inspected the actual untracked/tracked implementation and ran `PYTHONPATH=tests python3 -m unittest test_route_revision test_pathgraph test_route_goal test_pathgrowth -q`:184 passed, exit0. Reviewer additionally reported506 malformed-operation probes (504 rejects/2 legitimate accepts), all original graphs unchanged; budget/harness/diff checks exit0. Probe results were delivered as tool-output review evidence, not a preserved standalone probe script/log; do not claim they are reproducible from this file alone.

Findings and verified fixes:

- P2: archived legacy target was refused before explicit set_targets could repair it. Source validation now permits archived/empty targets with no inference; merged graph still requires active explicit targets. Added repair and no-replacement failure regressions.
- Bad source concepts=None/int leaked TypeError. Source shape checked before iteration; ValueError regressions.
- P2:500-level nested name reached deepcopy and leaked RecursionError. Scalar/list field validation now precedes copying. Added1071-byte parsed payload regression and original-copy check.
- P2:lone surrogate in brief or node text reached a result that could not encode into HTTP UTF8. All relevant text and clean source require UTF8 encoding, never replacement; escaped-surrogate regressions across all fields.

Reviewer reran original probes and final184 related tests; reported no remaining P1/P2. No provider/network/private-library access. Self review verified operations schema, bounded copy, fresh identity, protected user intros, explicit edges, target repair, cutoff monotonicity and unchanged legacy save behavior.

Integration reminder: repeated patch calculation creates new UUIDs. A future saved preview must freeze alias→UUID identities and verify graph/effective-feedback snapshots separately; do not compare two independently randomized result graphs as CAS. Services/API/UI, authoritative cutoff persistence, re-understood events, atomic graph+brief+cutoffs/undo, full message budgeting and phase08 are unfinished. E07 stays not_run.
