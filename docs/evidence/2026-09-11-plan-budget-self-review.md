# Self-review: recommendation-first plan, reuse survey and token-budget proposal

Date: 2026-09-11 (UTC). Reviewer: the implementing agent (Indent). Scope: research/planning documents, harness registries, prompt contracts, budget arithmetic and the two harness check additions. **Not** an independent review, and not a product/quality/billing review.

## What was inspected

- `git status --short` and `python3 scripts/harness.py impact`: the change set includes the prior legacy-app deletion plus this unit's edits; the record was regenerated after the last edit so `files` matches the live worktree.
- `harness/budget.json` against `docs/BUDGET.generated.md` (`--write` then `--check`): operation envelopes, `input_cap_components` sums, calendar/peak arithmetic and thresholds agree.
- `harness/tasks.json` / `requirements.json` / `evaluations.json`: every requirement is referenced by a task and every gate exists; every evaluation is now referenced by a requirement (new orphan check).
- `prompts/*.md` match the registered operations and carry `operation:` headers.
- `harness/sources.json`: DeepSeek pricing re-fetched HTTP 200 and re-dated; ASReview/txtai/Paper-Agent-Zotero/arXivDigest licenses fetched from LICENSE originals; rank_bm25 license fetched from `LICENSE` (the `.txt` path 404s).
- `docs/*.md` links, stage names and the absence of legacy task IDs as active tasks.

## Honest limits

- No upstream candidate was installed or run; ASReview/X/lite claims are source/README/API audits, not runtime measurements.
- The token envelopes are planning estimates from a 5-abstract sample and provider documentation; no offline tokenizer calibration, no provider billing call, no runtime gateway.
- `approved_by_owner` stays false; enforcement and tokenizer parity stay false; all 20 evaluations remain `not_run`; release remains blocked (recorded in the evidence file).
- The product's value (recommendation usefulness, profile learning gain) is completely unmeasured.

## Findings and fixes during self-review

- Generated budget document was stale at session start; regenerated and verified byte parity.
- `sources.json` initial insert dropped the `ZOTERO-ARXIV-DAILY` key; JSON validation caught it and it was restored.
- A new test initially mutated the wrong JSON shape; fixed and the full suite passes (40 tests).
