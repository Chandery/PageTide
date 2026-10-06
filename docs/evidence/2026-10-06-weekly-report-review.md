# Independent review: 2026-10-06-weekly-report
Reviewer: one separate read-only code-review agent (same model family, not a human).
Found nothing in: window and day arithmetic, missing-key handling, missing library tables, writes and cross-project leakage of the tree, double saved+useful events, XSS and NaN in weekly-ui.js, evidence kinds, other users of the old renderer (apart from item 1), CSS tokens.
Found and fixed afterwards (each with a test; the fixes were not re-read by a reviewer):
1. Critical - removing PDHProfile.weeklyHTML left `weekly: weeklyHTML` in PDHProfile.create(), a ReferenceError that broke opening the profile view; no test called create(). Removed; a smoke test now calls create() (mutation-checked).
2. Important - context() ran the unit matching for the whole library on every call (four callers) and could raise on a malformed stored map. The route is now computed lazily, only by the weekly pass, only for papers with a record this week, and any failure leaves the report without a unit section.
3. Important - a direction with last week's records and only a not-relevant record this week was labelled "no record this week". "quiet" now means no record at all; the other case is "other".
4. Important - the direction bar hid saves whenever a rating existed (3 saves + 1 not relevant looked rejected). Saves without a rating of their own now have a segment.
5. Important - the number of directions in the headline came from the list already cut to 12. It is counted before cutting; the cut ones are announced.
6. Important - the report ignored a switched-off learning map. It now says the map is off.
Smaller points taken: plural-safe English lines; 未分类 is translatable while a person's category names are not; the useful rate counts a paper once by its latest rating that week; a vacuous test was replaced; tests were added for a missing org table, a membership to a deleted category, a malformed map, a switched-off map and another project's paper in the shared tree.
