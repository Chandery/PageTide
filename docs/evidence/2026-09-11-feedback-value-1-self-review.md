# Self-review: feedback-value experiment 1

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review; no product-quality claim.

## What was built

- `tools/eval_probe.py`: `feedback` command with a chronological split, Rocchio-style profile variants (frozen seed / +positives / +positives−negatives), time-safe IDF (seeds+batch A only), and full-label metrics (AUC, mean rank of useful, mean relevance@10).
- 4 new unit tests for the Rocchio profile, the chronological split and the AUC/mean-rank helpers; 16 tests in the file.
- Experiment-3 report; `PROFILE-01` and `EVAL-01` moved to `in_progress` with evidence.

## Result

recency AUC 0.52; frozen seed 0.94; +positives 0.96; +positives−negatives 0.99. The ordering is consistent and monotone across negative weights (0, 0.25, 0.5, 1.0). This is a directional signal that explicit feedback, including dislikes, improves ranking.

## Verified

- All 64 tests pass overall (58 before + 6 new); `harness.py check` and `budget.py --check` pass.
- IDF is fit only on seeds + batch A; batch-B labels are used only for scoring.
- Re-running is deterministic; no new network or model calls in this unit.

## Honest limits

- Batch B has 23 items; AUC deltas of 0.94→0.99 are not statistically meaningful at this size.
- Single chronological split, not the >=10-batch rolling sequence the roadmap requires.
- The same annotator produced both the feedback labels and the evaluation labels, so the apparent gain may partly reflect the annotator's own biases. The owner's 95% binary spot-check mitigates but does not remove this.
- P@5 is saturated, so only AUC and mean rank carry signal.
- `E-FEEDBACK-VALUE` stays `not_run`.
