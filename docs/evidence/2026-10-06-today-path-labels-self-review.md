# Self-review: Today path labels (2026-10-06)

Implementing agent, not independent.

- Cause (reproduced with the explore_new fixture, three batches in a row): when the concepts the reader can read now had no unshown papers left, `build_batch` threw away the route picks and returned an ordinary batch: no label at all, and the reason in `shortfall` was never shown by the page.
- Fix: the batch stays a path batch. The exploration papers keep their tag; the rest are filled in by the same ordinary ranking (MMR) and labelled `offroute`, with the concept they resemble when `assign` finds one; the reason is in `shortfall` and in the Today panel line. No new model call, no token, no migration (kind stored in the existing exposures columns; an old build shows no badge for an unknown kind).
- The exploration tag is a solid bold tag with a mark, and the card gets a left bar. Styling only.
- Not measured: how often it happens on the owner's data (the owner's library was not read); the Tauri window was not clicked through.
