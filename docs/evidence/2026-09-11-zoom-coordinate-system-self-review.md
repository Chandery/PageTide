# Self-review: one coordinate system for reader positioning

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## The symptom

Pinching to zoom out moved the view up by a fixed chunk **the instant the gesture
started**, and it stayed there after release. So it was not an end-of-gesture
mismatch (the previous fix addressed that) but a constant error applied at the
first event.

## The cause

`#readerPages` is the scroll container, but a `.pgwrap`'s `offsetTop` is measured
against its **nearest positioned ancestor** — `.reader`, which is `position:fixed`
— so it includes the toolbar height and the container's padding. The code mixed
that with `box.scrollTop`, which is the scroll offset *inside* `#readerPages`.

Mixing the two produced a constant error (toolbar + padding), applied the first
time an anchored formula ran. Because the visual phase and the crisp phase used the
same wrong formula, the view moved once and then stayed put — exactly what was
reported. The same error is why 适宽 also jumped.

## Fix

A single helper, used everywhere positioning happens:

```js
function contentTopOf(wrap, box = $('#readerPages')) {
  const boxRect = box.getBoundingClientRect();
  const wrapRect = wrap.getBoundingClientRect();
  return wrapRect.top - boxRect.top + box.scrollTop;
}
```

`getBoundingClientRect()` differences plus `scrollTop` give the true offset inside
the scroll content, whatever the offsetParent is and including padding. It now
feeds `currentAnchor`, the visual-phase anchor, the crisp-phase anchor and the
fractional restore used by re-layouts and by 适宽.

There are **no raw `.offsetTop` reads left** in the file.

## Verified

- 110 tests pass; `harness.py check` and `budget.py --check` pass; both inline
  scripts pass `node --check`; `grep .offsetTop` returns nothing.

## Honest limits

- Not verified with a real trackpad pinch here. The change removes a genuine
  coordinate-system inconsistency and the constant it introduced, which is the
  mechanism behind "moves a chunk and stays".
- If a residual shift remains it would now have a different cause (for example the
  container padding interacting with the pointer offset), and the direction and
  magnitude would identify it.
- Recommendation quality remains unproven; quality gates stay `not_run`.
