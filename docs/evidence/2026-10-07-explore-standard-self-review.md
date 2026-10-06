# Self-review: exploration standard and repeating path papers (2026-10-07)

Implementing agent, not independent.

- Old behaviour: any unseen paper outside the frontier could be exploration, ranked by similarity to the reader's interests, so a paper of an already understood concept (3D Gaussian Splatting) came first. A batch also lost every path label when the readable concepts had no unseen papers left, and there was an early return with no cards at all when every paper had been shown.
- New rules in `App._route_pick` / `build_batch`: exploration = never shown before AND matches no concept of the map (understood or locked); a paper of a concept the reader can read now stays a candidate until the reader answers it (saved, not interested, too hard, understood), the least shown first, so it is shown again after the unseen ones. A batch that is short says why; an ordinary batch is used only when the path has no papers and no exploration candidate at all. The "off path" label added earlier is removed.
- No model call, no token, no migration. Repetition changes what a reader sees more than once: a paper they never answer comes back; answering any way stops it.
- Not measured: how this feels on the owner's real library; whether an exploration pool of "matches nothing on the map" is large enough (it can be empty, then the batch has no exploration slot and the panel says so).
