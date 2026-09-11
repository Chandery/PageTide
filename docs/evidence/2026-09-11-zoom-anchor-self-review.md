# Self-review: zoom anchor and smoothness

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Why it jumped (my arithmetic bug)

```js
box.scrollTop = target.offsetTop + anchor.within + anchor.top - prevTop;
```
`anchor.within = prevTop - anchor.top`, so the expression is identically
`target.offsetTop` — every re-layout snapped to **the top of the current page**
and discarded the position inside it. Zooming and 适宽 therefore both jumped, and
the cursor-anchored correction afterwards measured from the wrong place.

## Why it was not smooth

Every pinch event eventually re-rendered canvases. The debounce meant a gesture
only redrew once, but the gesture still felt like it "settled" rather than scaled.

## Fixes

- `currentAnchor()` now also records the page height; the restore keeps the
  **fraction of the page** (`target.offsetTop + fraction * target.offsetHeight`),
  so a re-layout no longer moves the reading position.
- Cursor anchoring is now measured against the scroll position at the **start of
  the gesture sequence** (`R.zoomBase`) and the scale the DOM was last **rendered**
  at, so the content under the pointer stays put and a burst of events accumulates
  instead of overwriting each other.
- **Instant feedback**: `applyVisualScale(k)` scales the already-rendered pages
  with a CSS transform and resizes their wrappers (so the scroll extents are
  correct) — no canvas work at all during the gesture. The debounced re-render
  then replaces it with a crisp bitmap at the final scale.
- 适宽 (and the −/+ buttons) clear any pending pinch correction first, so a zoom
  that is still settling cannot yank the view afterwards.

## Verified

- 110 tests pass; `harness.py check` and `budget.py --check` pass; both inline
  scripts pass `node --check`; the served page contains `applyVisualScale`,
  `zoomBase`, the wrapper base sizes and `transform-origin:0 0`.
- The old, provably-redundant restore expression is gone from the file.

## Honest limits

- I still cannot perform a real pinch here, so the feel is unverified; the
  arithmetic and the event handling are, however, now straightforwardly correct
  and the counterexample that caused the jump is removed.
- During the gesture the image is a scaled bitmap (slightly soft at high zoom)
  until the 180ms idle re-render.
- Recommendation quality remains unproven; quality gates stay `not_run`.
