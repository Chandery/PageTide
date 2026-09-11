# Self-review: first application slice (Python core + local UI + AI triage)

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review; this is a first working slice, not a release.

## What was built

- `app/db.py`: SQLite schema for papers, batches, exposures, feedback (undoable), immutable profile versions, PDFs and settings; cross-thread safe with a lock.
- `app/ranking.py`: TF-IDF cosine, Rocchio profile, MMR diversification.
- `app/sources.py`: OpenAlex discovery (the DATA-01 validated recipe) and seed resolution, with an on-disk response cache and bounded retries that degrade instead of hanging on HTTP 429.
- `app/gateway.py`: the single budgeted model gateway — reserve, then send, then record reconciled usage; refuses over-ceiling calls; no silent fallback.
- `app/service.py`: daily 5-card loop, feedback semantics (`busy`/`confused`/`later` never change interest), visible/editable profile, PDF download, optional AI triage.
- `app/server.py` + `app/static/index.html`: loopback-only single-threaded server and a working UI.
- `app/cli.py`: the same flows headless.
- 18 new tests (core + HTTP smoke) plus a harness test fix.

## Verified

- 82 tests pass; `harness.py check` and `budget.py --check` pass.
- End-to-end offline: imported 754 frozen candidates, produced 5 cards with reasons and URLs, recorded feedback, rendered the profile.
- One real AI triage call succeeded (1469 tokens, $0.0010608) and was written to the ledger; dry-run reserves without calling.
- The UI serves `GET /` 200 and `/api/state` with 5 cards, 1 positive and 1 negative feedback.
- A bug was found and fixed during self-testing: ThreadingHTTPServer + SQLite cross-thread failure, and the server smoke test now guards it.

## Honest limits

- Recommendation quality is still unproven; `E-RANKING`/`E-FEEDBACK-VALUE`/`E-LLM-LABEL-VALIDITY` remain `not_run`.
- No Tauri shell, packaging or signing yet; the UI is a browser page on loopback.
- The labelling prompt's seed-title bias is unfixed, so evaluation numbers are not product evidence.
- No Zotero import, notes/highlights, follow-up QA or export UI yet.
- OpenAlex 429s make `refresh` unreliable during heavy use; the app degrades but may fetch nothing.
- The runtime budget gateway has not been exercised near its ceilings or through a restart with unknown usage.
