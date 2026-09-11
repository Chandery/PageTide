# Self-review: DATA-01 read-only arXiv/OpenAlex coverage probe

Date: 2026-09-11 (UTC). Reviewer: implementing agent. Scope: a new stdlib probe tool, its tests, seeds file, and the DATA-01 findings. **Not** an independent review; no recommendation-quality claim.

## What was added

- `tools/data_probe.py`: read-only, zero-model-token probe. Resolves the owner's seeds via OpenAlex, optionally arXiv, snapshots raw responses for replay, and measures pool coverage. Snapshot caching avoids re-spending OpenAlex quota.
- `harness/seeds.json`: the 10 owner-declared seed titles in machine-readable form.
- `tests/test_data_probe.py`: 7 unit tests over pure parsers (arXiv XML, OpenAlex inverted abstract, ID extraction, title matching).
- `docs/evidence/2026-09-11-data01-openalex-report.md` and a RESEARCH/HANDOFF summary.
- `DATA-01` set to `in_progress` with evidence.

## Findings recorded honestly

- Seeds resolved 8/10; the two failures are recent 2026 preprints (one matched an unrelated paper, one not found).
- Free-text keyword search is not a field filter (3.28M hits; medical/repository noise even with a CS filter).
- OpenAlex reference edges are largely absent for arXiv preprints (1/8 seeds had any).
- Future-dated metadata appears unless `to_publication_date` is set (117/200 before the fix, 0 after).
- Observed metering: OpenAlex $0.001/search, 10 credits, 1000 credits and $0.10/day; bursts cause HTTP 429.
- arXiv legacy API returned persistent HTTP 429 for this IP during the probe.

## What was verified

- `harness.py check`, `budget.py --check`, and 48 unit tests pass (41 before + 7 new).
- Snapshot replay is deterministic: the second run reproduced the same 8/10 seed resolutions from cache.
- No private seed IDs were sent to any recommender; only public titles to public metadata search.

## Honest limits

- This is a data-source probe, not a candidate set and not a quality measurement; `DATA-01` stays `in_progress`.
- Recall of known-relevant papers was not measured (no confirmed relevant set yet).
- OpenAlex quota is a shared account limit; the ~$0.011 spent is recorded but not a recurring budget line.
- The pool is deliberately kept as a documented negative result (keyword pool unusable).
- arXiv could not be exercised; its coverage remains unverified for this field.
