---
name: audit-budget
description: Audit PageTide model operations, prompts, token counts, API prices, retries or new features; maintain reproducible runtime and separate developer budgets.
---
# Audit a budget change

1. Read docs/BUDGET.md and harness/budget.json. Distinguish zero-token local operations, provider search charges, app model calls and coding-agent consumption.
2. State the **daily minimum** explicitly before coding: enumerate every recurring operation (search, dedupe, ranking, profile update, archive, DB maintenance) and show it is zero model token; then show the optional AI layer's per-day reference and cap. A proposal may register priced operations with `approved_by_owner` still false, but that is arithmetic, never authorization.
3. Check official model/pricing/tokenizer/protocol sources and freshness. Do not infer that OpenAI-compatible means identical usage or limit semantics. Do not rely on cached search results alone for a changed contract. Record off-peak/peak and cache-hit/miss bases; do not assume cache hits in the ceiling.
4. Register every prompt/operation. Enumerate all input including schemas/history/source labels/protocol framing, max output, attempt count, frequency, privacy permission and fallback. Avoid unbounded context/tools/regeneration. Prompt files under `prompts/*.md` must match the registry and carry an `operation:` header.
5. Recalculate both input/output tokens and USD at peak cache-miss prices; include 30 days + weekly runs, same-day peak, retries and unresolved reservations. No cache discount in the ceiling.
6. Run `python3 scripts/budget.py --write`, inspect the diff, then `--check` and the unit tests. Record before/after numbers or a justified zero delta in the change record.
7. For actual request changes, run pinned offline tokenizer/encoder fixtures and provider contract tests only when those exist and paid testing is approved. Current stdlib tests do not prove tokenization or a runtime spending cap.
8. Verify every app model call traverses the single gateway, and the app checks aggregate in-flight, daily/monthly tokens and money before sending. Unknown usage must remain pending, even after restart.
9. Any increase beyond the approved baseline or new external exposure needs owner approval. Record it, keep historic price versions, update relevant evaluations and handoff.

Developer budgets are separate soft limits if the agent host provides no measured usage/cancellation. Report unknown as unknown; do not pretend this project's JSON controls another agent's API bill.
