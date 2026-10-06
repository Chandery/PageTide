# Independent review: 2026-10-06-route-layers

Reviewer: one separate read-only code-review agent (same model family as the implementer, not a human). It read the full diff and ran three throwaway scripts in $TMPDIR.

Found nothing in: feedback semantics consumers, XSS, boundary validation / what reaches the model, budget file consistency, `rejected` persistence across the other route ops.

Found and fixed afterwards (each with a regression test; the fixes were not re-read by a reviewer):
1. Medium - a paper marked not-interested and then understood still counted as growth evidence (service._route_candidates).
2. Medium - "don't suggest again" keyed on a hash of the paper set, so it stopped working when the cluster changed. Now keyed on the normalised phrases; directions already on the map are recognised the same way.
3. Medium - the undo button could undo a different step than the one shown. The page now names the step; the server refuses when anything newer exists; the offer disappears when the revision moves on.
4. Low-medium - undo was not locked while edits were unsaved.
5. Medium - a slow read of the second view could draw over the paper graph after switching back / changing project tab. Every render now invalidates the read in flight and the continuation re-checks view, scope and mode (mutation-checked: removing the guard fails two tests).
6. Low-medium - the new paper-shape rule in validate() could lock a map saved before the rule existed; now only new paper-shaped concepts are refused and the message names the concept.
7. Low - reading the second view created the knowledge-base tables / a row / a backup; it is now a pure read on the connection (tested on a database without those tables).

Smaller points taken: the detail pane is redrawn after "已读懂"; the worst-case input estimate gap is documented in BUDGET.md; the weak source-text UI tests were strengthened.
Not taken: the frozen branch of App.profile() still computes too_hard_feedback from current feedback (unchanged behaviour, nothing reads it).
