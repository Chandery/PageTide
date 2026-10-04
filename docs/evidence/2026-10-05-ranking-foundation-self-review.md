# Self-review: 2026-10-05-ranking-foundation (Route Mode slice 0)

Implementing agent's own review; not independent. Ranking is the recommendation core.

- Bug fixed: build_batch built the profile vector from the candidate pool only, and the pool excludes every paper that was already shown or rated, so 收藏/不感兴趣 and already-shown seeds never reached the ranking. Verified by mutation: restoring the pool-only vector makes the steering and seed tests fail.
- IDF now comes from all of the project's papers (not the pool), so seed and feedback vectors use the same vocabulary weights. Rankings can differ slightly from before for the same data; that is intended and covered by the replay test (same input, same batch).
- Chinese: tokenize() appends character bigrams of Chinese runs; English output is byte-identical to the old tokenizer (oracle test over nine inputs). words() is the old ASCII-only tokenizer and is used for everything shown to the user (guidance keywords, profile interest terms, "shared topics"), so no two-character fragment is ever displayed. Chinese appears in a reason only as a whole pinned phrase.
- Determinism: equal scores break by newest date, then key (sort_scored); a profile with no vocabulary overlap no longer depends on database row order.
- Not changed: how the profile is saved, freeze/undo semantics, weights, MMR, the batch size. too_hard still never enters the negatives (test).
- Not verified: ranking quality on real data (the existing baselines are saturated, P@5 = 1.0, so this cannot be shown as an improvement); Chinese ranking quality beyond a toy example.
- Known leftover: a pure-Chinese paper contributes bigrams that profile_insights does not show as interest terms (words() is ASCII-only), so a Chinese-only project has no interest terms in the profile page; pinned phrases still work.
