# Independent review: OpenAlex discovery (2026-10-04)

Reviewer: a separate read-only code-review agent with a fresh context (same model family as the author, not a human). It ran the targeted tests and reproduced finding 1 with stubs.

Findings and disposition:
1. IMPORTANT, title de-duplication dropped non-ASCII titles (normalize_title keeps only [a-z0-9], so Chinese-only titles became empty and 'GaN 外延生长' / 'GaN 薄膜缺陷' both became 'gan'). A regression for the seed picker and for topic search. FIXED: title_key keeps Unicode; tests for Chinese-only titles in both paths.
2. IMPORTANT, refresh for Chinese keywords was unbounded and not newest-first (order='recent' was ignored for CJK). FIXED: all keywords use from_date; CJK relevance requests add sort=publication_date:desc when order='recent'. Consequence stated in ADR 0012: a Chinese-only project may get no new papers until a Chinese source (channels branch) is merged. Not changed: only the first three keywords are used.
3. IMPORTANT (privacy/process), refresh now sends project keywords (including pinned profile terms) to OpenAlex on every refresh, where before it sent only the constant 'world model'; no change record existed; the English-UI prompt wording could conflict. FIXED/RECORDED: ADR 0012 and docs/ARCHITECTURE.md state the new outbound data; change record added with owner_approved false and the item listed as an open risk for the owner to confirm; the prompt sentence now says Chinese queries are added only when the user describes the topic in Chinese.
4. SUGGESTION, a second request when per_page < 3. FIXED (min(STRICT_MIN_RESULTS, per_page)).
5. SUGGESTION, cache edge cases: non-JSON reply did not fall back to the stale copy; future-dated entries counted as fresh; legacy discover()/distractors() had no TTL; one bad rate-limit header discarded the others. FIXED, each with a test. NOT FIXED: papers topped up in relevance mode are saved without match_mode (the daily feed cannot label them); the settings line shows the allowance without its age.
Also fixed: a leading '!' in a phrase could negate the filter value (now stripped).
Confirmed sound by the reviewer: filter-injection handling and encoding of '|', ratelimit.json cannot collide with cache entries, ttl=None callers unchanged, the API key stays a header to api.openalex.org only, strict/relevance merge order, default-project detection, i18n of the allowance line, prompt budget inside the registered cap.
Not covered: live behaviour after the review fixes was not re-read by the reviewer; a second review pass has not been done.
