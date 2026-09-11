# Self-review: zoom anchoring measured from the DOM, not predicted

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## The symptom and its cause

Zooming in pushed the page down-right; zooming out pushed it up-left; releasing
snapped it back.

I was **predicting** the scroll position with a formula
(`(scrollTop + localY) * k - localY`) while applying the visual scale. But scaling
also enlarges the pages *above* the anchored one, so the anchored page's real
`offsetTop` moves further down than the formula assumed. The visual phase and the
final crisp re-render therefore disagreed, and the release looked like a jump.

## The fix

Both phases now **measure** instead of predicting:

1. At the first event of a gesture, `R.zoomBase` records the cursor's anchor as
   `{page, within, localY}` — which page it is on, the offset inside that page in
   rendered pixels, and the pointer's viewport offset.
2. `applyVisualScale(k, base)` scales the rendered pages, then in a
   `requestAnimationFrame` reads the anchored page's **actual** `offsetTop` after
   the resize and sets `scrollTop = offsetTop + within * k - localY`. Because it
   reads the real geometry, pages above growing is included automatically.
3. The 180ms crisp re-render carries the same `{page, within, k, localY}` and
   applies the identical measured formula, so releasing the gesture changes
   nothing.

## Verified

- 110 tests pass; `harness.py check` and `budget.py --check` pass; both inline
  scripts pass `node --check`.
- The two predictive formulas (`baseScrollTop + localY` and `zoomBase.scrollTop`)
  are gone from the file — a grep for them returns nothing.

## Honest limits

- Still not verified by an actual trackpad pinch here; the change replaces a
  provably wrong prediction with a measurement, which is the property that was
  missing.
- The scroll adjustment runs per animation frame during the gesture; on a very
  long document this is a forced layout per frame (cheap, but not free).
- Recommendation quality remains unproven; quality gates stay `not_run`.
