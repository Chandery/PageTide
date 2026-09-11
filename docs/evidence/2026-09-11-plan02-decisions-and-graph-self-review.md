# Self-review: owner decisions + hybrid LLM ranking + knowledge-graph research

Date: 2026-09-11 (UTC). Reviewer: implementing agent. Scope: registry/doc/budget changes for the owner's decisions, ADR 0003, and the paper-graph research. **Not** an independent review; no runtime or quality claim.

## Decisions recorded

- AI ceilings accepted by owner, **including the raised ceilings that cover `llm_rerank`** → `budget.json` `approved_by_owner=true`, `pending_approval=[]`.
- `llm_rerank` remains **default-off** until `EVAL-01` shows a gain over the sparse baseline (ADR 0003).
- No private seed/profile IDs to external recommender services (public metadata queries only).
- PDF storage defaults to a local folder; Zotero attachment writing deferred.
- New paper graph/clustering feature: `R-GRAPH`, `E-GRAPH`, `GRAPH-01`, stage `graph`, research in `docs/KNOWLEDGE-GRAPH.md`.

## What was checked

- `budget.py --write` then `--check`: raised ceilings (bg 26k / interactive 35k / total 55k per day, 1.5M per month, $0.15/day, $1.50/month) make the `hybrid_llm_rerank` cap scenario fit while the retry-stress scenario still violates as intended. Generated heading now derives the approval state instead of hardcoding "pending".
- `harness.py check`: prompt registry matches, requirements/gates traceable, links resolve.
- `tests`: owner-approval + `pending_approval` assertions updated; 40 pass.
- Licence claims spot-verified from raw LICENSE files: scikit-learn HDBSCAN source, python-louvain, VOSviewer-Online (MIT), Kuzu (MIT), litstudy (Apache-2.0).

## Honest limits

- No candidate installed/run; graph stack is a proposal, not selected. Resource figures are estimates.
- Seed papers still not resolved to canonical IDs; no explicit negatives.
- `llm_rerank` has no gain evidence yet; it must stay off until measured.
- All evaluations remain `not_run`; release still blocked by missing implementation approval, gates, gateway enforcement and tokenizer parity.
- Licences not listed above rest on the research agent's fetches, not re-verified by me.
