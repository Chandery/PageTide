# Self-review: 2026-10-05-path-algorithm (Route Mode slice 3)

Implementing agent's own review; not independent (the independent review is in 2026-10-05-path-algorithm-review.md).

- Scope: two pure modules (app/pathgraph.py, app/pathgrowth.py) and their tests. Nothing is wired into the app yet, so no behaviour a user can see has changed and the default path is unchanged.
- Rules honoured by construction: no model, network, clock or randomness; the same inputs give the same outputs (order-independence is tested, including shuffled papers and reversed positive dicts); silence, "irrelevant" and unmet prerequisites never lower mastery; no state means disliked; proposals never merge themselves (merge_candidate adds a *proposed* concept for a person to confirm).
- Strength of the tests: mutation checks (cycle breaking, shortcut removal, too-hard factor, sources gate, novelty rule, order dependence, recency, support margin) each made at least one test fail; two seeded random-input tests for normalize (valid graphs, odd types) and one for branch_candidates (rules hold on random corpora).
- The thresholds (0.6, 0.35, 0.35, 0.1/0.4, 0.25, 6/3/2/2 gates, +-0.15, 1.5x broader) are proposals. They are named constants. There is no data behind them, and the existing evaluation baselines are saturated, so nothing here can be called an improvement.
- Weak spots: cluster names are a heuristic (the leading title phrase); the "specialisation" rule (a cluster inside a concept 1.5x larger is novel with N = 0.6) is a judgement call; edge support uses only title and abstract text; the specific-terms merge rule can still miss duplicates with different wording.
