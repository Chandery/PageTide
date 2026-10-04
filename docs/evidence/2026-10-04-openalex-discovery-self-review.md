# Self-review: 2026-10-04-openalex-topic-discovery

Implementing agent's own review; not independent. Prompt and outbound-data changes are critical paths.

- Query safety: clean_query removes , | : ! quotes and backslashes before a phrase is placed in a filter value; the filter is built as exactly two parts (search + type), tested.
- Behaviour kept: the default project and an explicit `search` argument keep the DATA-01 arXiv recipe; ttl=None keeps the old forever cache; the legacy discover()/distractors() signatures are unchanged (they gained a 24 h TTL).
- Offline: a failed refetch falls back to an expired cache copy, so the app keeps working offline for searches it has made before; the first-ever search offline still fails visibly.
- Key handling is unchanged (header only); ratelimit.json holds numbers and a timestamp only.
- Test honesty: tests assert the actual URL parameters of every request; the changed existing tests now patch discover_topic because creation intentionally no longer calls discover. A test that guards AI-off zero requests caught a stray network call during this work.
- Weak spots: the prompt effect is untested against the real model; relevance order surfaces old papers (intended for choosing seeds, stated in the ADR); Chinese results are weak (OpenAlex limitation).
