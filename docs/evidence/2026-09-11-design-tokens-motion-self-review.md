# Self-review: contrast-fixed design tokens, real motion, and the missing divider variable

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## I could not see the Dribbble reference

Every route to `dribbble.com/shots/26548228` is blocked by AWS WAF / Cloudflare
(HTTP 202 with a CAPTCHA shell); a reader proxy is blocked too. I *can* read
image files, so the reliable path is for the owner to save the shot as a file
and give me the path — then I can match it properly instead of guessing.

## What the measurements found (the owner's complaints were measurable)

I parsed the real token definitions and computed WCAG contrast:

| Pair | Before | Verdict |
|---|---:|---|
| `--muted` on light surfaces | 3.1–3.6 | FAIL |
| `--good` / `--bad` as text | 3.2 / 3.8 | FAIL |
| `--accent` as text | 4.34 | FAIL |
| `--accent-ink` | **undefined** | buttons inherited their text colour — the "dark text on dark buttons" report |
| `--line` | **undefined** | all 11 `1px solid var(--line)` borders fell back to the text colour — why blocks had no separation |

## Fixes

- Re-derived the palette **against the worst-case surface** of each mode (darkest
  light surface, lightest dark surface) instead of the best case, and applied the
  computed values.
- Split the accent into three roles: `--accent` (fill, kept vivid),
  `--accent-text` (AA-safe text/links) and `--accent-ink` (text *on* the fill),
  defined explicitly for all five accents in both modes. The primary button is now
  a flat accent fill so the verified ink contrast actually applies.
- Defined `--line` / `--line-strong` for both modes.
- Motion pass: shared spring/out easings, card lift+scale, staggered follow-up
  chips, toast slide-in, preview pop, tab pop, button press, all inside
  `prefers-reduced-motion`.

## New regression tests (the reason these bugs can't come back)

- `tests/test_ui_contrast.py` resolves every (mode × accent) palette from the real
  stylesheet and asserts ≥4.5:1 for text/muted/accent-text/good/bad/ai-text on
  base, surface-1/2/3, plus accent-ink on the accent fill.
- It also asserts **every CSS variable used without a fallback is defined** —
  which is exactly how the undefined `--accent-ink` and `--line` slipped through.

## Verified

- 110 tests pass; `harness.py check`, `budget.py --check` pass; `GET /` 200;
  `server_version 0.5`, dev mode on.

## Honest limits

- Visual polish in the sense the owner means (layout, spacing, illustration style,
  the specific Dribbble look) is **not** verified and cannot be without the image.
- The motion values are design choices, not measured against a reference.
- Recommendation quality remains unproven; quality gates stay `not_run`.
