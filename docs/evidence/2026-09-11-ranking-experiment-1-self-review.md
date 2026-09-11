# Self-review: ranking experiment 1 (measurement harness)

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review; no recommendation-quality claim.

## What was built

- `tools/eval_probe.py`: freeze / rank / label / score subcommands. Freeze+rank+score are zero-token and replayable; `label` calls the evaluation annotator (taomu) and caches labels to `.local/`.
- `tests/test_eval_probe.py`: 6 tests over the pure TF-IDF, centroid, cosine and precision-at-k functions.
- Frozen candidate set (318 papers, hash `0c06666429815cc8`) and three ranking systems.
- `docs/evidence/2026-09-11-ranking-experiment-1.md`; `CORE-01` moved to `in_progress` with evidence.

## Result recorded

Recency P@5=0.80; keyword+date and TF-IDF-seed-centroid both P@5=1.00. The annotator labelled 25/26 items useful (96%). The metric therefore **cannot discriminate the systems** and no quality claim is made; `E-RANKING` stays `not_run`.

## What was verified

- 48 + 6 unit tests pass; `harness.py check` and `budget.py --check` pass.
- Labels are cached; re-running `label`/`score` spends nothing and reproduces the same result.
- No rank/score information was included in the annotation request (blind judging).
- Only the evaluation annotator was called; the runtime provider was never invoked.

## Honest limits

- Single exploratory slice; pool pre-filtered to `title.search:world model`, so positives dominate.
- Proxy labels, not the owner's judgement; no `E-LLM-LABEL-VALIDITY` spot-check yet.
- Only the union of each system's top-10 was labelled; no low-rank or random negatives.
- taomu is a flaky third-party relay; it required a common User-Agent and still injects a hidden ~4.2k-token prefix.
- This is the fixed-baseline harness, not the upstream-reuse probe (`REUSE-01`), which is still outstanding.
