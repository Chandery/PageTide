# Self-review: ranking experiment 2 (distractors + graded relevance)

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review; no recommendation-quality claim.

## What changed

- `tools/eval_probe.py`: mixed candidate pool (field + 5 adjacent distractors), graded 0-3 relevance rubric, union + random-sample labelling, graded metrics, and a `spotcheck` command that writes a blind sheet plus a private answer key.
- `tests/test_eval_probe.py`: updated to the graded metrics; 7 tests.
- Experiment 2 report, HANDOFF update, `CORE-01` evidence refreshed.

## Verified result

- Frozen 1126 candidates (318 field / 808 distractor, hash `5c27c2aa8bfbf91c`), abstracts complete.
- Labels (45, 9 annotator calls, ~50k tokens): `{1: 18, 2: 5, 3: 22}`.
- Strict threshold discriminates the trivial baseline: recency P@5>=3 = 0.40 vs 1.00 for both profile systems; mean relevance 2.40 vs 3.00.
- keyword+date and TF-IDF-seed-centroid remain tied at the top-5 ceiling, so no method ranking is claimed.
- 55 unit tests pass; `harness.py check` and `budget.py --check` pass.

## Honest limits

- n=45 with only 5 top-5 slots; differences are not statistically meaningful.
- Distractor relevance is partly by construction (they were chosen as off-field), so the field/distractor separation is expected, not an independent finding.
- Within-field annotator variance is still low (22/26 field papers scored 3).
- Annotator labels are an unvalidated proxy; the blind spot-check sheet is prepared but not yet filled by the owner.
- `E-RANKING` stays `not_run`; `REUSE-01` upstream probe is still outstanding.
