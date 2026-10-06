# Independent review: growth made visible (2026-10-06)

Reviewer: one separate read-only code-review agent (same model family, not a human). It read the full diff, ran the budget, harness and i18n checks and reproduced finding 1 in memory. It did not run the test suites, the browser UI or the desktop build, did not make real model or OpenAlex calls, and did not check `route-graph.js` ghost layout or migrations beyond the existing `exposures` columns.

Found: no XSS, no gateway bypass, no private IDs sent out. Accept is refused unless ready; ghost graph is a separate copy; AI sentence never auto-saved.

| # | Finding | Result |
|---|---|---|
| 1 | With `min_members=2` the 60-phrase cap filled with alphabetically early two-paper phrases and a ready direction vanished (reproduced) | Fixed: phrases that meet the member gate come first. Regression test `test_a_display_threshold_of_two_cannot_crowd...`; it fails without the fix (checked by mutation). |
| 2 | `concept_intro` sends the project name plus first three keywords, but budget.json, prompt, tooltip and BUDGET.md said "project goal" (projects have no goal) | Fixed: wording corrected in all five places; budget.json scope text changed, **owner should confirm the corrected wording**. |
| 3 | A model re-draft overwrote a same-named concept's user-written intro | Fixed in `reuseIds` (user text kept, model text replaced); warning text mentions it; node test added. |
| 4 | concept_intro worst case 516 tokens > cap 500 by its own estimate; test passed only through +100 slack | Fixed: limits 30/80 chars (worst case 471), slack removed from the test. |
| 5 | Hard-coded 10% share on new/unsaved maps | Fixed: 0.2. |
| 6 | "Click Edit / ask AI" hint shown on the creation page, which has neither | Fixed: hint only with `canEdit` (learning-map page). |
| 7 | Exploration steered by weak two-paper directions; candidates recomputed on every batch | Cache added (`_batch_directions`, keyed by revision, paper count, latest feedback id, freeze) with a test. Steering by `watch` directions kept on purpose (they are how an early direction gathers evidence); risk listed in the change record. |
| 8 | Stale `pendingIntro` could prefill a later edit | Cleared on selection. |
| 9 | `parse_intro` offered raw JSON when `intro` was missing | Returns empty; first-line handling fixed; tests added. |
| 10 | Rounding: status used unrounded strength while gates showed rounded; plural "1 papers"; zero-progress ring drew a dot; vacuous assertion in `test_a_direction_with_two_explicit...` | All fixed with tests (status/gates consistency test, ring test, plural-safe English). Untranslated ValueError messages remain a known gap. |

Process notes from the reviewer: the owner-approval quote could not be found by a transcript search; it is the AskUserQuestion answer "起草学习图时一起写简介,新增“写这个节点的简介”操作" given on 2026-10-06. The owner still has to confirm it (`owner_approved` in the change record stays false for the change as a whole).

The fixes were not re-read by a reviewer.
