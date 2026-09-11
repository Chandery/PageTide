# Self-review: trackpad pinch / modifier-scroll zoom in the PDF reader

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Why it did not work

The reader only had toolbar buttons. macOS delivers trackpad zoom in two
different shapes and neither was handled:

- Chrome / Edge / Brave send a `wheel` event with `ctrlKey === true` for a pinch;
  Cmd (or Option) + scroll is the same family.
- Safari sends `gesturestart` / `gesturechange` / `gestureend` with an `event.scale`.

Nothing called `preventDefault()`, so a pinch would also zoom the whole page
instead of the document.

## What was added

- A `wheel` listener on the pages area (`{passive:false}`) that only takes over
  when a zoom modifier is present (`ctrlKey || metaKey || altKey`). Plain
  two-finger scrolling is untouched. The step is exponential
  (`exp(-deltaY * 0.0032)`) so it feels linear in perception.
- Safari `gesture*` handlers that track a base scale and apply `event.scale`.
- **Cursor-anchored zoom**: the point under the pointer stays put. The correction
  is applied after the re-layout inside the existing `requestAnimationFrame`.
- **Correct accumulation**: the anchor factor is computed against
  `R.renderedScale`, the scale the DOM was actually rendered at, so a burst of
  pinch events does not overwrite earlier deltas.
- **Debounced re-render** (140ms) so a gesture re-renders once at the final scale
  instead of on every event; the lazy renderer then only redraws visible pages.
- The toolbar buttons now go through the same `setScale` path, and the zoom bar
  has a tooltip describing the gestures.

## Verified

- Both inline scripts pass `node --check`; the served page contains the
  `gesturestart` / `gesturechange` handlers and the `pendingZoom` /
  `renderedScale` logic.
- 110 tests pass; `harness.py check` and `budget.py --check` pass.

## Honest limits

- I cannot perform a real trackpad pinch here, so the gesture behaviour itself is
  unverified; the implementation follows the documented event shapes for both
  Chromium and Safari.
- Zooming is a re-render, not a CSS transform, so a very large PDF will show a
  brief 140ms settle after the gesture.
- Pinching outside the pages area (for example over the thumbnail sidebar) is
  ignored.
- Recommendation quality remains unproven; quality gates stay `not_run`.
