# Self-review: project_guidance connected to the model (2026-10-01)

Self-review by the implementing agent. This is not an independent review.

## Root cause
- `harness/budget.json` had `project_guidance.owner_approved=false`. `Gateway.admit()` raises
  `BudgetExceeded("operation awaiting owner approval")` for it, `Gateway.call()` turns that into a degraded
  result, and `App.guidance_turn()` then answers with `_local_guidance`. Quick creation and AI-guided creation both
  go through `guidance_turn`; manual creation never calls a model by design.
- The owner approved the real call explicitly in the session on 2026-10-01 (AGENTS.md boundary 9: an agent may not
  approve this itself).

## Change
- `owner_approved: true` with an approval note; caps, scope and `enabled_by_default=false` metadata unchanged.
- The system prompt's JSON example lacked the opening quote on `search_queries` and `next_question`. It had never
  been sent while the gate was closed. Fixed, with a test that parses the example.
- Tests that asserted "project_guidance is refused" now test the gate with an operation whose approval is switched
  off, and the approved path is covered: one request, `max_tokens` equal to the registered output cap, reserved and
  reconciled ledger rows, `mode == "ai"` for a well-formed reply.

## Checked
- Failure paths still degrade to local without retry: no key, AI switch off, budget ceilings, network error,
  malformed reply (existing tests plus `test_project_chain` with an offline transport).
- No provider SDK in the UI; the call still goes through the one gateway; the six-turn cap is enforced before the
  gateway is reached (`call_count == GUIDANCE_MAX_TURNS`).
- Privacy: payload is unchanged (current draft + last four turns, truncated), no other project data.

## Not verified
- No live DeepSeek request was made in this unit: no measured answer quality, latency or token usage. Budget
  figures remain registered caps, not measurements.
- The page still labels quick creation "本地优先" and shows only "AI 未参与本轮" when degraded, without the reason.
- Independent review not run.
