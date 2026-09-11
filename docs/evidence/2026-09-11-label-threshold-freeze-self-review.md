# Self-review: freeze the useful threshold and correct the experiment-2 reading

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review; the labels are the owner's, the plumbing is mine.

## What was done

- Filled the second blind sheet with the owner's 5 annotations (1,2,2,2,3) and extended `spotcheck-score` to merge multiple sheets and sweep thresholds.
- Combined agreement over 20 items: exact 45%, within-1 100%, binary 95%.
- Froze `useful = annotator relevance >= 2` (95% agreement; 1 false positive, 0 false negatives) versus `>=3` (80%, 4 false negatives).
- Re-ran scoring and recorded the corrected experiment-2 reading: P@5 saturated, P@10 recency 0.60 vs 1.00 for both profile systems.
- Wrote the threshold into `docs/EVALUATION.md` and added a note + evidence to `E-LLM-LABEL-VALIDITY`.

## Verified

- 58 unit tests pass; `harness.py check` and `budget.py --check` pass.
- The sweep is deterministic from the saved sheets and cached labels.
- No new model calls in this unit.

## Honest limits

- n=20 and the threshold was chosen after seeing the labels, so it only pre-registers for future candidate sets.
- The sample was drawn from the 45 already-labelled items, and the graded scale remains unusable (annotator never emits 0).
- The P@10 comparison uses 10 labelled items per system; far too few for a statistical claim.
- `E-LLM-LABEL-VALIDITY` is deliberately left `not_run`; a fresh >=40-item validation is required before release.
