# Self-review: annotator label validation 1 (and experiment-2 correction)

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review; the validation is the owner's own blind judgement, and this review only checks the plumbing.

## What was done

- Added `spotcheck-score` (plus `parse_spotcheck_sheet` and `spotcheck_agreement`) to `tools/eval_probe.py`, and 3 unit tests for them.
- Parsed the owner's filled 15-item blind sheet and compared it with the annotator labels.
- Recorded the result and **corrected the experiment-2 conclusion** in HANDOFF.
- Prepared a second blind sheet for the 5 annotator level-2 items whose meaning is unresolved.

## Result and why it matters

- Binary agreement (useful >=2) is 15/15; exact agreement is only 40%.
- The annotator never emits 0 and shifts the owner's 0->1 and 2->3, so the graded scale is not comparable and graded means must not be reported as measurement.
- Under the validated binary rule, experiment 2's three systems all score P@5 = 1.00, i.e. **no discrimination**, so the earlier "profile ranking beats recency" claim is withdrawn.

## Verified

- 58 unit tests pass; `harness.py check` and `budget.py --check` pass.
- The agreement script is deterministic and re-runnable from the saved sheet and cached labels.
- The sheet shown to the owner was blind: it contained no annotator verdicts.

## Honest limits

- n=15, and the useful threshold was discussed after seeing results rather than pre-registered.
- The sample came from the 45 already-labelled items, not a random draw from the whole pool.
- The annotator level-2 meaning is unresolved; a second small sheet is pending.
- Findings apply only to this annotator, model and prompt version.
