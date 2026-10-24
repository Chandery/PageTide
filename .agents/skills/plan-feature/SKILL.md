---
name: plan-feature
description: Plan a new PageTide feature or scope change before coding; trace requirements, low-compute constraints, token impact and staged approval.
---
# Plan a feature

1. Read AGENTS.md, HANDOFF and the relevant task/requirement. Verify actual files and Git status; do not trust a previous chat's completion claims.
2. Describe the user outcome, failure states and non-goals. Check default 8GB/no-local-model/local-storage/privacy constraints.
3. Compare at least the simple deterministic implementation against any proposed LLM or infrastructure addition. Do not add AI where structured code suffices.
4. Assign feature or critical class by consequence. Add/update one task with dependencies, observable acceptance and relevant evaluations; do not maintain a second task list.
5. For each proposed model call, identify operation, trigger/frequency, complete input budget, output cap, retries, cache invalidation, authorization and no-AI fallback. Use audit-budget skill.
6. New data/lifecycle/security boundary: add or supersede an ADR. New user-visible behavior: update PRODUCT; source-of-truth values stay in JSON.
7. Obtain owner approval for new scope, paid calls, budget increases, new external data sharing or changing agreed platform support. Agent cannot set approval on their own.
8. Implement the smallest independently testable slice. Before a real API call, the gateway and offline failure tests must exist.

Exit: task/requirements/evaluators agree, budget delta is explicit, unverified assumptions remain visible, next concrete implementation step fits one work unit. If quality or low-compute tests fail, revise the design rather than silently increasing compute or context.
