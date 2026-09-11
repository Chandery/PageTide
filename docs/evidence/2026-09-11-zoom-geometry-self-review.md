# Self-review: zoom geometry made identical in both phases

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Two symptoms, one cause

1. Zooming in let the next page grow over the gap.
2. After the gesture finished, the point under the cursor had shifted (down when
   zooming in, up when zooming out).

`applyVisualScale` set the wrapper height to `pageViewportHeight * k`, but a
wrapper also contains the inner `row-gap` and the page-number line. The wrapper was
therefore **shorter than its content**, so the following page rode up over the gap,
and — more importantly — the wrappers above the anchored page were shorter than in
the crisp re-render. The anchored page's `offsetTop` differed between the two
phases, so the measured anchoring produced a different scroll position and the
release looked like a shift.

## Fix

Both phases now produce the same box:

- At build time each wrapper records the page viewport (`baseW`, `baseH`) **and the
  fixed chrome** (`chromeW`, `chromeH` = measured wrapper size minus the page).
- `applyVisualScale` sets `width = baseW * k + chromeW`,
  `height = baseH * k + chromeH` and transforms the page by `k`. The crisp layout
  at scale `baseScale * k` yields exactly `pageHeight * k + chrome` — the same
  number.
- Because the geometry matches, `offsetTop` for every page matches in both phases,
  so the cursor anchor is stable through the gesture and on release.
- An intermediate attempt scaled the gap and the page-number font as well, which
  made the visual phase *differ* from the crisp one; that is reverted.

## Verified

- 110 tests pass; `harness.py check` and `budget.py --check` pass; both inline
  scripts pass `node --check`; the wrapper records `chromeW`/`chromeH` and the
  visual phase uses `baseH * k + chromeH`.

## Honest limits

- Still not verified with a real trackpad pinch here.
- If the page-number line wraps on a very narrow window the chrome height would
  differ per page; it is measured per wrapper, so that is handled, but the layout
  shift between phases would then be per-page rather than uniform.
- Recommendation quality remains unproven; quality gates stay `not_run`.
