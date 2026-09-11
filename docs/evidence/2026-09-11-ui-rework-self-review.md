# Self-review: UI/UX rework (home, frosted glass, detail view, background jobs)

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review.

## Owner-reported problems and fixes

| Reported | Root cause found | Fix |
|---|---|---|
| 没有主页 | UI was a single card list | New `/api/home` + hero dashboard with stats chips, primary actions and job progress |
| 抓取很慢 | 6 OpenAlex queries with long retries, synchronous | Refresh is now a **background job** polled by the page; default is one field query; retries bounded to ~10s and capped |
| 点击 AI 速览显示降级为离线 | UI defaulted to dry-run and rendered `ok:false` as "degraded" | Dry-run now shows the reservation explicitly; degraded only on real failures; mode toggle is labelled |
| 生成今日五篇超级慢 | **Not computation** (`build_batch` = 73ms). The single-threaded server was blocked by the in-flight refresh | Server is now threaded with a per-request App/SQLite connection; measured `/api/home` = 3.6ms during a running refresh |
| 摘要不全 | Stored abstracts are full (median 1437 chars); the card CSS clamped them | Card keeps a 4-line clamp but cards are clickable and the detail panel shows the full abstract |
| UI 丑、要磨砂玻璃、要动画 | — | Frosted glass (backdrop-filter), pointer glow, card hover lift, entry animations, modal pop, toasts, progress bar, reduced-motion support |
| 可交互性差、没有详情 | Cards were static | Cards and a 详情 button open a detail sheet with full abstract, metadata, feedback actions, PDF and 原文 links |

## Verified

- 83 tests pass (added a detail-endpoint test and made the HTTP helper handle 404s).
- `harness.py check` and `budget.py --check` pass.
- Live smoke: `GET /` 200; `/api/home` shows 811 papers / 5 cards; `/api/paper/<key>` returns 1315-char abstract; triage dry-run reserves 4200 in / 1300 out / $0.00282; concurrent refresh does not block the API.

## Honest limits

- This is visual/interaction work; it does not improve recommendation quality, which is still unproven.
- AI summaries are only persisted after a real (non-dry-run) triage; the detail panel shows one only if it exists.
- Optional AI follow-up questions, notes/highlights and Zotero import remain unimplemented.
- No Tauri packaging yet; the page runs in a browser on loopback.
- The refresh job's OpenAlex 429 handling still yields zero new papers when the shared API is hot.
