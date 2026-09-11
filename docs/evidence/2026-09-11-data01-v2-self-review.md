# Self-review: DATA-01 v2 — canonical seed IDs and arXiv-source discovery

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review; no recommendation-quality claim.

## What changed

- `harness/seeds.json` now carries canonical identifiers (`arxiv_id` / `openalex_id` / `doi`); the two seeds the owner supplied (arXiv `2607.06401`, `2607.26037`) resolve by explicit ID.
- `tools/data_probe.py` resolves explicit IDs via the OpenAlex single-work endpoint and verifies the returned title (records `+title_mismatch` instead of silently accepting).
- Candidate discovery switched to `primary_location.source.id:S4306400194` + `title.search` + date bounds.
- Report/RESEARCH/HANDOFF/DOMAIN updated to the v2 findings.

## Verified

- Seeds: **10/10 resolved, 0 title mismatches**; the same result reproduces from cached snapshots with no network.
- Pool: 3,226 reported, 200 returned, **200/200 from arXiv, 0 missing abstracts**; references and related-works edges **200/200 missing**.
- 48 unit tests pass; `harness.py check` and `budget.py --check` pass.
- No private seed IDs were sent to any recommender; only public identifiers/titles to public metadata lookups.

## Honest limits

- The pool is one ~1-month slice; time splitting and a known-relevant recall set are still missing, so `DATA-01` stays `in_progress`.
- OpenAlex edge coverage for recent arXiv is effectively zero; the graph feature cannot use it.
- arXiv API remained HTTP 429 throughout; its coverage is still unverified.
- OpenAlex quota spent this session (~$0.0235) is recorded but is not a runtime budget line.
