# Self-review: project creation flow (2026-10-02)

Self-review by the implementing agent. This is not an independent review.

## What was reviewed
- Backend: `app/creation.py` (seed parsing, lookup, name search, PDF import, degrade reasons), the guidance changes in
  `app/service.py` (turn counting, retry, edits, per-query search), routes in `app/server.py`.
- Page: `project_creation.html`, `project-creation.js`, `project-creation.css`, `creation-pdf.js`; the Tauri window flag.

## Data, privacy and budget
- Only an identifier, a user-typed title, or a title/id recognised in a dropped PDF is sent to OpenAlex. The page says so.
  The PDF stays on disk (`imports/` -> `pdfs/`), original bytes, never uploaded. This deliberately relaxes the earlier
  "free text is never looked up" rule for explicit name search and for PDF-derived titles (ADR 0010); PDF-derived titles
  are searched without a per-search confirmation.
- No new model operation and no budget change. Quick creation is capped server-side at 1 AI turn, guided at 6; a turn that
  did not get a model answer is free, but each retry is one explicit request (no automatic loop, no model fallback).
  The transcript is capped at 40 messages so no-AI turns cannot grow it forever.
- Upload route: same-origin check, 60 MB cap, `%PDF` signature check, content-addressed name, uploads older than 24 h removed.
  `pdf_id` is validated as 64 hex characters before touching the filesystem.
- Candidates are never pre-selected and the model never picks papers (unchanged boundary).

## Failure paths checked
- No key / AI off / not approved / budget / HTTP error / network / bad reply each map to a named reason (unit tests).
- OpenAlex unavailable or offline: seed rows show a reason with retry; candidate search keeps earlier results and says why.
- Expired or missing upload at project creation: the seed is still created, `pdf_attached=false` with the reason.
- A failed turn request keeps the typed message and re-renders from the server's transcript.

## Bugs found while reviewing and fixed
- Quick/guided mode switch ran its reset after an `await`, so a fast follow-up could be reset (found in the browser).
- Seed search hit button text squeezed titles to one word per line on narrow widths.
- A module-level seed cache leaked between tests; the old seed test now clears it.

## Verified in a browser (static server, fetch mocked)
- Manual: identifier, name search with add/undo, three dropped PDFs (arXiv stamp, title only, unreadable), help row.
- Quick and guided: activity line with timer, local-mode reason with retry/settings link, retry success, failed request,
  progressive candidate cards with expandable abstracts, narrow layout, wide two-column layout in dark mode.
- Not verified: drag-and-drop inside the WKWebView of the built app, real OpenAlex name search / PDF matching quality,
  real DeepSeek turns, English-mode rendering by eye (the pack is complete per `i18n_extract.py`).

## Not done / open
- Independent review not run. Candidate retrieval is still the arXiv / since-2024 / date-sorted title search.
