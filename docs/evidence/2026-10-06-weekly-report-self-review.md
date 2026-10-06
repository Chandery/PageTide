# Self-review: 2026-10-06-weekly-report (implementing agent, not independent)
- No dislike from silence: a direction with no record is "no record this week" (quiet) only when it has no record at all; one with only not-relevant or too-hard records is "other"; being shown a paper is counted as "seen", never as turned down; every page carries the sentence that no record does not mean lower interest.
- Saving is not understanding: a learning unit is listed as having an "understood" record only from understood events; saves show interest only.
- Untrusted text: titles, category names, unit names go through esc()/Number() in weekly-ui.js; tests with markup in titles, names and status.
- Isolation: memberships are looked up only for this project's papers; the learning map is per project.
- Read-only: library_tree is a plain read; learning_map calls route_get (reads) and matches only this week's papers.
- Known gaps: see open_risks.
