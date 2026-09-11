# Self-review: assistant UX round (page jump, dynamic follow-ups, title, citations, translation, selection)

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Owner feedback and fixes

| Complaint | Cause | Fix |
|---|---|---|
| 点推荐问题会回到首页（第一页） | `setPetOpen` called `layoutPages()` to re-fit the width, and that rebuilt every page shell and reset the scroll to the top | `layoutPages()` now records `R.current` and restores that page after rebuilding, so docking the panel no longer jumps |
| 推荐问题不更新 | The chips were a fixed list | The QA prompt now returns JSON with `answer` plus three `followups`, the server parses them, and the panel re-renders the chips after every answer. If the model ignores the JSON contract the raw answer is used and the default chips stay |
| 标题不醒目 | The paper title was small grey text in the context box | A prominent `<div id="petPaper">` shows the paper title in bold with a small subtitle |
| 引用太丑，应像 Cursor 那样在输入框上 | The selection was pasted into the context text area | The selection is now a removable chip above the input (`#petRef`) with an ✕; it is cleared after the question is sent |
| 翻译不该在阅读助手里 | Translation wrote into the assistant log | Translation has its own popover near the selection with copy/close, and no longer touches the assistant |
| 划词不准 / 选中的不能取消 | I used my own `.txt` class and CSS instead of the contract pdf.js expects, so span geometry drifted | Switched the container to `textLayer` and copied the official `.textLayer` rules from `pdf_viewer.css`; added an ✕ in the selection bar and Escape clears the selection |

## Verified

- 98 tests pass, including four new ones: QA parses `answer`+`followups` (capped at three), falls back to raw text without JSON, dry run records no history.
- Live on a fresh server: two consecutive questions both returned `followups` of length 3, and the follow-ups were specific to the paper (world-model data sources, RGBD fusion, CoT supervision) rather than the static list.
- Both inline scripts pass `node --check`; served page contains the docking, reference-chip, translation-popover and `textLayer` markers; `GET /` 200; `server_version 0.4`.

## Honest limits

- Selection accuracy is now based on pdf.js's own layout contract, but I still cannot verify it visually; it is the standard setup rather than a measured fix.
- Follow-up questions depend on the model returning the requested JSON; when it does not, the previous chips are kept.
- The translation popover is not draggable and is closed by ✕/Escape.
- Recommendation quality remains unproven; quality gates stay `not_run`.
