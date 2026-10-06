# Self-review: direction loop (2026-10-06)

Implementing agent, not independent.

- Privacy: direction_judge sends p1..p3 (title <=80, abstract <=180 chars, no ids), concept names (<=10, 20 chars), stored direction names + short line (<=3). concept_intro adds up to three matching papers (title, abstract <=200). Tests parse the single user message and assert the exact key sets; no notes, profile, feedback, seeds or other projects.
- The model's output is an opinion: verdict whitelisted, labels p/c/d validated, needs mapped to existing concept ids, names/intro/barrier cleaned and cut, 'new' re-checked locally. The app never adds to the map without a click and all four local gates; direction text is stored as the model's and merged with intro_by "ai".
- No dislike from silence: pending needs an explicit useful/understood on a paper shown as exploration; irrelevant / too hard / undone / merely shown do not count; a member turned down or undone later stops counting.
- Budget failure paths: attempt reserved before the call, refunded only when the gateway refused before sending, one call at a time per project, 10 per day; dry run counts nothing.
- Not measured: real model output, the effect of the thresholds on real libraries.
