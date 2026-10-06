# Independent review: direction loop (2026-10-06)

Reviewer: one separate read-only code-review agent (same model family, not a human). It read the full diff, ran the unit suite, the budget and harness checks, and probes and five mutation checks on a copy in $TMPDIR. It did not run the node tests or the browser flow, did not rebuild the app, made no real model call, and could not verify the owner's approval quote against the conversation (the owner should confirm it).

No data leak beyond the agreed fields, no XSS, reserve/refund/lock match `route_concept_intro`, a direction is only added through the accept click with all gates, silence and turned-down papers are not evidence.

| # | Finding | Result |
|---|---|---|
| 1 | The "让 AI 写简介" tooltip (and its English entry and a test) still said only name/terms/goal are sent, but papers' titles and abstract excerpts are sent too | Fixed: tooltip, i18n and test now name the matching papers; "一句话" wording changed to "一段话". |
| 2 | A direction turned down ("不再提示") still steered exploration, was told to the model, and could absorb papers via join/twin | Fixed with one helper `_visible_directions` used by the list, the exploration targets and the judge call; a new with the rejected words is answered "declined". Tests added. Steering also drops papers the reader turned down since. |
| 3 | `parse_intro` kept only the first line, losing the barrier | Fixed: lines are joined; tests added. |
| 4 | Wrong JSON types (terms as a string, intro as a list) were stored as garbage | Fixed: types checked, terms need >= 3 characters, otherwise the item is unusable; tests added. |
| 5 | Items failing validation were recorded as permanently judged | Fixed: they are reported as unusable and the papers stay pending; only the model's own "unclear"/"covered" are recorded. Tests added. |
| 6 | The model saw the first 10 concepts / first 3 directions in storage order; stored directions unbounded | Fixed: the nearest concepts and directions to the papers (local cosine) are sent; at most 12 open directions, then new ones wait ("full"). Limitation (weak T_NEAR for concepts with few papers) written into docs/BUDGET.md. Test added. |
| 7 | The panel showed "novelty 100%" as a measurement | Fixed: the part is removed (it was a constant); the text says the difference from the map is the model's judgement. |
| minor | `WHERE key IN (...)` without chunking | Fixed (chunks of 400). |
| minor | `unsave` kept the judge prompt on the card | Fixed. |
| minor | the paper just collected might not be in the batch of three | Fixed: pending sorted by the order of the clicks (feedback id). Test added. |
| minor | Chinese-only ValueError messages; HANDOFF older entries still describe the removed flow | Not changed (same as earlier operations; historical entries). |

The fixes were not re-read by a reviewer.
