# Independent review: path algorithm core (Route Mode slice 3), 2026-10-05

Reviewer: one separate read-only code-review agent with a fresh context (same model family as the author, not a human). It ran short offline snippets for every finding. The author fixed all of them afterwards with tests written from the findings; those fixes were NOT re-read by a reviewer.

Findings (11) and disposition, all FIXED with tests:
1. HIGH, concepts without ids, or repeated ids, all got the same canonical id (three unnamed-id concepts became c3, c3, c3 with targets [c3, c3, c3]). Fix: concepts are tracked by position; ids in the input only serve to resolve `needs`; a need may also name its concept.
2. MEDIUM-HIGH, truncating to 12 nodes could drop the target itself (a 20-step chain with target n19 kept n0..n11). Fix: targets first, then ancestors breadth-first from the targets; dropped concepts are reported.
3. MEDIUM, over-eager merging ("Transformer" and "Vision Transformer" merged through a shared one-word term; punctuation-only names merged). Fix: merge only on equal names or identical *specific* term sets (two terms or a multi-word term); punctuation-only names are dropped.
4. MEDIUM, exceptions on odd types (targets: 5, needs: 5, needs: "abc"). Fix: type checks; seeded random-input test with missing/odd ids and types.
5. MEDIUM, progress() raised KeyError on a cycle that got into stored data. Fix: unknown prerequisites count as unmet; a cycle stays locked until the reader breaks it.
6. MEDIUM, progress()/frontier() ignored `state`: proposed or archived concepts appeared on the frontier and an archived prerequisite kept its dependents locked. Fix: only active concepts and edges take part; proposed/archived get their own status.
7. MEDIUM, add_concept() enforced no rules (14 nodes, fan-in 5, redundant edges, hint order). Fix: same rules as normalize (map cap 40, fan-in 3, hint order, cycles) and transitive reduction on the result.
8. LOW, a manually mastered concept with unmet prerequisites: documented as intended (the reader says they know it); `unmet` is still reported.
9. LOW, exploration_slots with batch size 1 or a negative index, allocate with NaN weights. Fix: documented and hardened.
10. MEDIUM, a separators-only term ("-") matched almost any text; phrases built from stop-word-filtered neighbours ("policy robot" from "policy for robot") could never be found again by term_in_text. Fix: no-match for empty terms; bigrams are adjacent content words of the raw text; a property test checks that every term of every candidate matches a member paper.
11. MEDIUM, the evidence gates could be passed by duplicates (the same paper under two keys, "arXiv" vs "arxiv "). Fix: papers are identified by DOI or normalised title; sources are trimmed and lower-cased.
Smaller: branch_candidates performance (3000 papers took 5.5 s, now 0.42 s via an inverted index and memoised term hits); coherence samples positives first; merge_candidate is idempotent and adds no redundant edge; mixed date types and keyless papers no longer raise.
Confirmed sound by the reviewer: 3,000 random graphs satisfied every invariant, large inputs normalise quickly, the regex has no catastrophic backtracking, no deadlock on acyclic graphs, low_interest never blocks the only path, exploration cumulative rounding, no AGENTS.md boundary violation (no network, model or clock; nothing infers dislike from silence).
Test gaps the reviewer named (missing ids, wrong types, states, duplicates, invariants after add/merge) are now covered.
