# Self-review: UI round 4 (detail actually opens, un-save, theme presets)

Date: 2026-09-11 (UTC). Reviewer: implementing agent. **Not** an independent review.

## Root cause of the broken detail page

Paper keys are URLs (e.g. `https://doi.org/10.48550/arxiv.2510.16240`). The browser sent them percent-encoded, but the server read the raw, still-encoded path segment and looked it up in SQLite, so every detail request returned 404 and the front end swallowed the error. Fixes:

- `/api/paper` now takes `?key=...` (query parameters are decoded by `parse_qs`), and the path form is `unquote()`d for compatibility.
- A regression test uses a real URL-shaped key through both forms.

## Other owner feedback

| Feedback | Change |
|---|---|
| 收藏的论文页点不开 | Same root cause; library items now open the detail page through the fixed endpoint |
| 不能取消收藏 | Cards show `✓ 已收藏（点击取消）`, library rows have a 取消收藏 button, and the detail page toggles 收藏/取消收藏; `/api/unsave` already existed and is now wired |
| 颜色还是太丑，找好看的模板 | Replaced the single palette with four selectable presets (mint / rose / sand / ink) built on neutral zinc surfaces with one accent each; switcher in the header, choice persisted in localStorage, no blue by default |
| 点击不进详情（再次） | Detail clicks now work; the previous broken `{once:true}` handler was removed and detail actions are delegated once on `#detail` |

## Verified

- 86 tests pass, including the URL-key detail regression test.
- Live: `/api/paper?key=<url-encoded>` → 200 with a 1339-char abstract; collect → library grows; `/api/unsave` → library shrinks.
- `harness.py check` and `budget.py --check` pass.

## Honest limits

- Theme choice is subjective; I cannot see the rendered page, so this is a tasteful default set rather than a verified visual match to any specific template.
- No visual regression/screenshot test exists.
- Recommendation quality is still unproven; quality gates remain `not_run`.
- Export, notes, Zotero import and Tauri packaging are still missing.
