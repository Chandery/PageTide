# Self-review: docked assistant, always-visible orb, markdown rendering

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Owner feedback and fixes

| Complaint | Cause | Fix |
|---|---|---|
| 还是没有悬浮球 | The previous round added `body.reader-open .pet { display:none }`, and the `reader-open` class survives if the reader is closed by any path other than the back button (e.g. Escape/navigation), so the orb could stay hidden | The rule is gone. The orb is always rendered; while reading it just sits closer to the corner at 62% opacity and returns to full opacity on hover |
| 点「对这篇提问」右边出现黑框、挡住 PDF、不会自动缩放、关不掉 | The panel was `position:fixed` overlaying the full-screen reader, and the reflow relied on a `margin-right` hack that did not actually shrink the page and never re-fit | The assistant is now **docked as a real column inside the reader's flex row** (`.petpanel.docked`, moved into `.rbody` on open, moved back to `body` on close). The pages area is a flex sibling, so it shrinks automatically, `layoutPages()` re-fits the page width when the panel opens/closes, and a `resize` listener re-fits on window changes. The panel has its own header with ✕ |
| 摘要、助手不能渲染 markdown | Everything was inserted as plain text | A small renderer (`md`/`mdInline`) with HTML escaped first, supporting headings, bold/italic, inline code, fenced code blocks, bullet lists and links; applied to the abstract, the AI summary and assistant answers |
| 助手面板打开时是空的 | Only messages appeared, and there were none at first | A welcome hint is shown plus the six suggestion chips |

## Extra

`server_version` bumped to **0.4**, shown in the page footer, so it is obvious
whether the running process is the current code (a recurring source of
confusion in earlier rounds).

## Verified

- 95 tests pass; `harness.py check` and `budget.py --check` pass.
- Both inline scripts pass `node --check`.
- Served page contains `petpanel.docked`, `function dockPanel(`, `function md(`,
  the resize listener and the new orb rule; `GET /` → 200; `/api/home` reports
  `server_version: 0.4`.

## Honest limits

- I cannot see the rendered page; the dock width (380px) and markdown spacing are
  judged from CSS. A docking layout is, however, structurally incapable of
  covering the pages, unlike the previous fixed overlay.
- The markdown renderer is intentionally minimal (no tables, no nested lists).
- Recommendation quality remains unproven; quality gates stay `not_run`.
