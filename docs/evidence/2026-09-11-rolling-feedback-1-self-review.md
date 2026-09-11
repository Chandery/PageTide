# Self-review: rolling feedback experiment (10 batches)

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review; no product-quality claim.

## What was built

- `tools/eval_probe.py`: monthly-window freeze (`--months`) for a 12-month time-spread pool, stratified labelling (`--sample-field` / `--sample-distractor`), an `equal_batches` helper and a `rolling` command that locks predictions before releasing each batch's feedback.
- 3 new tests (equal_batches) plus the earlier profile/metric tests; 17 in the file, 65 overall.
- Labelled 233 new items (268 total) across 12 months at batch size 10.

## Result

Rolling sequence over 9 evaluated batches: mean AUC rolling 0.910 vs frozen 0.891 (delta +0.018), wins 4 / ties 3 / losses 2. Recency 0.512. The earlier single-split +0.05 was an overestimate.

## Verified

- 65 tests pass; `harness.py check` and `budget.py --check` pass.
- IDF is fit only on seeds + strictly earlier batches; predictions are locked before feedback is applied.
- Labels persist incrementally, so the two relay 404s only required resuming, not re-spending.
- No runtime-provider call; only the evaluation annotator was used.

## Critical limitation found

The labelling prompt contains the 10 seed titles, so the annotator rates seed-similar papers as useful by construction. That inflates both the frozen and rolling AUC and compresses their difference. Ranking and feedback numbers are therefore not trustworthy until the prompt is changed and labels are regenerated. This is recorded, not hidden.

## Other limits

- Proxy labels from a single annotator for both feedback and evaluation.
- Single run, single parameter set; no seed/split robustness check.
- Batch 10 scored 0.39 for both profiles, so that batch is uninformative.
- `E-RANKING` and `E-FEEDBACK-VALUE` stay `not_run`.
