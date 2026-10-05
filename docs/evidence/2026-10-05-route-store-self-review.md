# Self-review: 2026-10-05-route-store (Route Mode slice 4)

Implementing agent's own review; not independent (see 2026-10-05-route-store-review.md).

- Storage choice: the learning map lives in the knowledge-base record keyed by the real project id (`Organization(store, project=<project id>)`), inside the same JSON as categories. It reuses the revision check, the undo log (named and generic) and the pre-migration backup. The category forest and the saved-paper corpus of the shared "default" record were NOT changed: they still read the global library. The map is project-scoped; the classification view is not yet. This is narrower than the plan's "make Organization project-scoped" and was chosen because the notes triggers and the corpus are hard-wired to the global library and 'default'.
- Progress is derived, never stored: statuses come from the latest effective feedback per paper (undone events gone), cut at a frozen profile's through_feedback_id, with seeds as explicit positives and a paper counting for the single concept it fits best. Silence, irrelevant and unmet prerequisites never lower mastery; proposed and archived concepts collect nothing and block nothing.
- Writes are validated before anything is persisted (normalize for a plan, validate for a structured map); a failed write leaves the revision unchanged; a no-op writes nothing.
- Privacy and budget: no model, no network, no outbound data; the map holds concept names and search terms the user already sees and edits.
- Weak spots: route_get recomputes assignment of every project paper per call (about 0.3 s per 5000 papers before the column fix; not cached); the classification view still ignores project boundaries; the route block has no schema version field; nothing in the UI uses the map yet (slice 6).
