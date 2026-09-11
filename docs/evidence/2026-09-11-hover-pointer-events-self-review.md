# Self-review: hover preview was swallowing its own events (right column dead)

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## The real cause

`#preview` was hidden only with `opacity:0`. It kept its box, its `z-index:70`
and — because an earlier round made it scrollable — `pointer-events:auto`. So an
**invisible panel stayed where it last appeared**, and for a left-column card that
position is exactly to the right of the card, i.e. **on top of the right column**.
Hovering the right column therefore hit the invisible preview instead of the card,
the card's `mouseover` never fired, and no preview appeared.

That also explains why it was *only* the right column and only after any hover had
happened once: before the first hover the box sat at the top-left corner, and after
it, it sat over the right column.

## Fix

- `#preview` is now `visibility:hidden` + `pointer-events:none` by default, and
  `#preview.show` re-enables both. A hidden preview can no longer intercept
  anything.
- `hidePreview()` also parks it back at (0,0), belt and braces.
- Removed the contradictory `pointer-events:auto` from the base rule.

## Verified

- 105 tests pass; `harness.py check` and `budget.py --check` pass; both inline
  scripts pass `node --check`.
- The fix is a CSS pointer-events/visibility correction. I cannot observe the
  rendered hover, but the mechanism is deterministic: a hidden element with
  `visibility:hidden` and `pointer-events:none` cannot receive events.

## Honest limits

- Not visually confirmed by me; the owner should check the right column now.
- If a preview ever appeared over the card you are moving to, the `mouseenter`
  grace period keeps it open; that is intended.
- Recommendation quality remains unproven; quality gates stay `not_run`.
