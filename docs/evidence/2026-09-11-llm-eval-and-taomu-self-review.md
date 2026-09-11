# Self-review: LLM-assisted evaluation, annotator separation and provider probes

Date: 2026-09-11 (UTC). Reviewer: implementing agent. Scope: registries, docs, budget model and two provider probes. **Not** an independent review; no product-quality or billing claim.

## What changed

- Owner chose LLM-assisted relevance judging; the judging provider is a third-party relay (`taomu.xyz`, model `gpt-6-astra`), while the shipped app keeps DeepSeek official (ADR 0004).
- `judge_relevance` moved out of runtime operations into a new `evaluation` section of `harness/budget.json`; runtime ceilings and scenarios are unchanged for the app.
- `scripts/budget.py` gained `validate_evaluation` + a token-only render section (never USD, since taomu has no public price). `scripts/harness.py` now counts evaluation prompts in the prompt registry.
- Added `LABEL-01`, `R-EVAL-LABEL`, `E-LLM-LABEL-VALIDITY`; updated `E-RANKING`.
- Two live non-private probes recorded: DeepSeek (122 tokens, $0.000058 derived) and taomu (reported 4403 prompt tokens for a few words → ~4,403 hidden injected input tokens).

## What was verified

- `budget.py --write`/`--check` parity, including the new evaluation section.
- `harness.py check`: prompt registry (7 runtime + 1 evaluation prompt files), requirement/gate traceability, links.
- 41 unit tests pass, including that the annotator price flag cannot be flipped to verifiable without failing validation and that the hidden prefix is charged per evaluation call.
- Probe usage fields match `budget.reconcile_usage` for DeepSeek; taomu's usage does not expose cache-miss fields in the same shape, so it is kept token-only and out of the runtime accounting.

## Honest limits

- Neither probe is a product measurement; no gate passed.
- taomu pricing is unverifiable and its model identity is self-reported; hidden prefix may vary by request and cannot be audited.
- `LABEL-01` cannot run until `DATA-01` produces a frozen candidate set; seeds are still not resolved to canonical IDs.
- Evaluation labels remain an unvalidated proxy until `E-LLM-LABEL-VALIDITY` passes.
- Both API keys were shared in chat and only stored in `.local/` (gitignored); they should be rotated.
