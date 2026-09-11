# Self-review: UI round 3 (collection semantics, auto triage, hover preview, warm palette)

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review.

## Owner feedback and what changed

| Feedback | Change |
|---|---|
| 点详情没用 | The old page bound the detail handler on `document` twice, and the small card buttons swallowed the click. Detail is now a dedicated **page** opened by clicking the card; buttons stop propagation |
| 颜色太丑（蓝色） | Palette replaced with warm amber / dusty rose / sage / terracotta; gradients and glass re-tuned for light and dark |
| 收藏语义错了 | `有用` now writes to a new `library` table (idempotent) and the card **stays visible** marked 已收藏; added a 论文库 tab plus `/api/library` and `/api/unsave`. Neutral actions still never change interest |
| 生成五篇要秒出 | Cards render immediately from the batch response, before any AI work |
| AI 速览自动执行 | After generation the page calls a real triage automatically (toggleable); each card shows a spinner, then 速览 text and an 「AI 已速览」 badge |
| 底下按钮太丑 | Buttons are now small pills with icons (`☆ 收藏`, `不感兴趣`, …), grouped and restyled |
| 详情要悬停出框、点击进页 | Hover 0.5s shows a preview popover near the card; leaving hides it; clicking the card opens the full detail page |

## Verified

- 86 tests pass, including new ones: collect saves to library and the card remains visible, saving twice is idempotent, unsave removes it, and feedback never removes a card from the current batch.
- Live smoke: `GET /` 200; `/api/home` exposes `saved` on each card; collecting card 0 returned `saved:true`, `/api/library` listed 1 item, and a follow-up `/api/home` still returned all 5 cards with `saved:true`.
- `harness.py check` and `budget.py --check` pass.

## Honest limits

- Auto triage spends DeepSeek tokens on every generation; it goes through the gateway and degrades to local mode if the ceiling is hit or there is no key, but there is no "already summarised" skip yet.
- The palette and animations are subjective; no accessibility audit beyond reduced-motion support.
- Recommendation quality is still unproven; quality gates remain `not_run`.
- Library export, notes, Zotero import and Tauri packaging are still missing.
