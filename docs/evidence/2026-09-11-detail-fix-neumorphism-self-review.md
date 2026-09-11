# Self-review: detail lookup hardened + Neumorphism UI

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Why the detail page still 404'd for the owner

My previous fix worked on a **freshly started** server, but the owner's browser was almost certainly talking to a **still-running old Python process** — refreshing the page reloads HTML/JS but does not restart the server. I could not verify this from here, so instead of assuming, I made the failure impossible to miss and the request impossible to break:

- `POST /api/detail` with `{"key": ...}` in the body. A JSON body has no URL encoding at all, so URL-shaped keys cannot be mangled. The UI now uses this endpoint.
- `/api/paper?key=` and the `unquote()`d path form remain as fallbacks.
- The server now prints `[404] paper key=...` for failed lookups, so a failure is visible in the terminal.
- `/api/home` returns `server_version`, and the page footer shows it, so a stale process is obvious at a glance.

## Neumorphism redesign (per the owner's reference)

Reference: `claudekit.github.io/frontend-design-pro-demo/02-neumorphism.html`.

- One surface colour; depth comes from paired light/dark shadows, **no borders**.
- Raised panels for cards/hero/header, inset wells for tab bar, inputs, badges and the AI summary.
- Press states use inset shadows (buttons physically "push in").
- Replaced the accent-only theme picker with **5 accent colours** (violet default, mint, coral, rose, amber) plus a **light/dark** toggle; both persisted in localStorage.

## Verified before committing

- 88 tests pass, including new ones: POST-body detail, the `?key=`/path forms with a URL-shaped key, and the home version field.
- End-to-end on a freshly started server, using the exact request the browser makes: `POST /api/detail` → **200**, correct title, 1339-character abstract.
- Server stderr was empty of `[404]` lines during the run.
- `harness.py check` and `budget.py --check` pass.

## Honest limits

- I still cannot see the rendered page; the Neumorphism implementation follows the reference's principles but its visual quality is unverified by me.
- No screenshot/visual regression test exists.
- Recommendation quality remains unproven; quality gates stay `not_run`.
- Export, notes, Zotero import and Tauri packaging are still missing.
