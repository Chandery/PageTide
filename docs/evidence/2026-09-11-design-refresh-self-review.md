# Self-review: design refresh, inline follow-ups, Cursor-style citations, translation dismissal

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Owner feedback and fixes

| Complaint | Fix |
|---|---|
| 推荐问题挡住回答 | The fixed suggestion block was removed from the panel. Follow-ups are now rendered **inside the conversation log, immediately below the answer** (`followupRow`), and only the newest row is kept |
| 翻译点了别处应关闭 | A `mousedown` listener dismisses `#transPop` when the click is outside it and outside the selection bar |
| 样式太单一，块与块没有分别 | Layered surface scale added (`--surface-1/2/3` + three shadow levels) and applied to panels, cards, chips, buttons and messages; cards get an accent rail and a stronger hover elevation; tabs/buttons/messages now have distinct surfaces; animations added for messages and follow-up rows |
| 引用太丑，参考 Cursor 侧边栏 | Selections became a **reference card** (`refCard`): a PDF icon, an uppercase "引用 · 论文片段" label, a two-line truncated snippet and an ✕. It appears above the input and is also attached to the user's message inside the conversation, which is how Cursor shows quoted context |

## Verified

- 98 tests pass; `harness.py check` and `budget.py --check` pass.
- Both inline scripts pass `node --check`.
- The served page (59,488 bytes) contains `followupRow`, `refcard`, `rlabel`,
  `surface-1`, the design-refresh block and the outside-click `mousedown`
  listener; `GET /` 200; `server_version 0.4`.

## Honest limits

- **I could not view the Dribbble reference** (no image/browser rendering here),
  so the refresh follows general modern-SaaS layering rules rather than that
  specific shot. If it is still off, describing the concrete difference (e.g.
  "cards need bigger radius", "more contrast between page and cards", "less
  colour") will converge faster than another link.
- The follow-up chips appear under the answer in the conversation; they are
  removed when the next question is asked, so older suggestions are not kept.
- Reference cards are not clickable to jump back into the PDF yet.
- Recommendation quality remains unproven; quality gates stay `not_run`.
