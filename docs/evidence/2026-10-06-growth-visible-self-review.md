# Self-review: growth made visible (2026-10-06)

Implementing agent, not independent.

- Privacy: concept_intro sends the concept name, up to two search terms and the project name + first three keywords (80 chars); no paper, note, profile or other project. concept-examples sends only the first search term to OpenAlex (public metadata query). concept-papers is local read-only.
- AI text is never saved without the person's click; it is stored with `intro_by: "ai"` and shown as "Written by AI"; editing it makes it theirs; a model draft never replaces their text.
- Ghost directions never enter `state.draft`; accept is refused server-side unless ready.
- No dislike is inferred: only explicit useful / understood / seeds count; exploration exposure is not evidence.
- Budget failure paths: attempt reserved before the call, refunded only when the gateway refused before sending, one call at a time per project, 20 per day.
- Not measured: real model output, OpenAlex latency, the effect of the 20% share on real libraries.
