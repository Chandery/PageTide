# Self-review: full-page PDF reader, selection translate/ask, floating assistant

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Constraint discovered first

The browser's built-in PDF viewer is a plugin: JavaScript cannot read the user's
selection inside it, so 划词 is impossible with an `<iframe src="...pdf">`. The
only way to support selection is to render the PDF ourselves. pdf.js was vendored
(Apache-2.0, pinned 4.6.82, 330 KB + 1.36 MB, no runtime CDN) and recorded in
`sources.json`.

## Owner requests and what changed

| Request | Change |
|---|---|
| PDF 预览太小，要一键全屏 | The small inline preview was removed. Detail now has **全屏阅读 PDF**; cards have **阅读 PDF**. The reader is a full-viewport overlay with a slim toolbar (back / title / page count / 对这篇提问) |
| 追问助手缩成小的类似宠物的东西 | A floating 🐾 orb bottom-right toggles a compact chat panel; it holds the current paper context and bounded per-paper history |
| 可以划词翻译 | Selecting text in the reader (or the detail abstract) raises a small popover with 翻译 / 追问 |
| 可以选中段落进行追问 | 追问 attaches the selection to the question and sends it with the paper context |
| 历史要记录 | New `qa_history` table stores user/assistant turns per paper; `GET /api/qa?key=` returns them |

## Implementation notes

- The reader renders each page to a canvas and builds a transparent, selectable
  text layer from `getTextContent()`; if pdf.js fails to load it falls back to the
  native viewer and says so.
- New endpoints: `POST /api/qa`, `POST /api/translate`, `GET /api/qa?key=`.
  Both model calls go through the single budget gateway (`paper_qa`,
  `selection_translate`) and degrade to a visible message when refused.

## Verified before committing

- 95 tests pass, including: dry-run reservations for both new endpoints record no
  history; the history endpoint returns user+assistant turns; `/api/pdf/view`
  serves stored bytes; the vendored pdf.js files are served.
- Live on a fresh server: pdf.js (329,881 B) and its worker (1,362,587 B) served;
  a real `paper_qa` call answered about the paper and wrote 2 history rows; a real
  `selection_translate` call returned Chinese with English terms preserved; the
  ledger recorded `paper_qa` ($0.000166) and `selection_translate` ($0.000030).

## Honest limits

- Selection only works in our own text layer; the fallback viewer cannot select.
- Only the abstract is sent as context (plus the selection) — no full-text upload,
  by design; answers are therefore bounded by the abstract.
- The reader renders pages eagerly, which is fine for a paper but not optimised
  for very large PDFs.
- The assistant's visual design and the reader's typography are unverified by me
  (no rendered-page access).
- Recommendation quality remains unproven; quality gates stay `not_run`.
