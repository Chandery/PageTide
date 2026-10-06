# Self-review: 2026-10-06-route-layers (implementing agent, not independent)

Checked against the plan and AGENTS.md boundaries.

- Never infer dislike from silence / no selection / difficulty: `understood`, `too_hard`, silence and unopened papers change neither interest nor the profile; a `too_hard` after `useful` no longer removes the interest (two dimensions per paper). Growth ignores not-interested, too-hard and silence.
- Source text is untrusted: titles, unit names and reasons go through esc()/h()/textContent or canvas data fields; tests cover a markup title in the detail view, in candidateHTML and in the failed-read message.
- Model calls: only the existing gateway operations; the boundary is two enum values validated before an attempt is reserved; the raised cap was first registered as owner_approved:false by the agent; the owner approved it in the session on 2026-10-06 and the file now records that in their words (tests assert it).
- Offline default: the second view, feedback semantics and growth proposals are local and deterministic; no new network egress; no citation edges.
- Originals preserved: nothing is stored for matches; layouts of the second view are in memory only; `rejected` is an additive key that route-save keeps.
- Known gaps: see open_risks in the change record. The pessimistic worst-case input estimate with the longest boundary (about 1447) is above the registered 1400 by the existing +150 tolerance of the test.
