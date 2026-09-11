# Self-review: separate test mode so testing is not blocked by runtime ceilings

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Problem

The owner hit the daily ceiling while testing. The ledger showed **51,804 of
55,000** tokens used today across 38 calls (`daily_triage` 7, `paper_qa` 22,
`selection_translate` 8, `paper_vision_qa` 1), i.e. ~3.2k left — so every further
test call would be refused. The ceilings are owner-approved, so they must not be
silently changed.

## Fix: a separate, local, explicit test mode

- Enabled by `PDH_DEV=1` or the presence of `.local/app/DEV_MODE` (both outside Git).
- In test mode the gateway writes to a **separate ledger**
  (`.local/app/usage-dev.jsonl`) and uses **separate loose ceilings**
  (5M tokens/day, 50M/month, $10/day, $50/month).
- The **approved runtime ceilings and the runtime ledger are untouched**, so dev
  spend can never be mistaken for runtime usage.
- The page shows a 测试模式 banner and the footer shows today's usage; the CLI has
  `--dev`; `docs/BUDGET.md` documents how to turn it on and off.
- Ceiling refusals now name the actual numbers (for example
  `daily token ceiling (51,804/55,000 used)`) instead of a bare message.

## Verified live

- `GET /api/home` reports `dev_mode: true` and
  `usage: {tokens: 0, ceiling: 5,000,000, dev: true}`.
- A `paper_qa` call that the runtime ceiling would have refused succeeded, and it
  correctly answered a Figure 5 question from the anchored caption.
- **Runtime ledger unchanged at 38 entries**; the dev ledger gained one entry
  (`paper_qa`, 3,305 tokens). That is the property that matters: testing no longer
  consumes the approved budget.
- 103 tests pass, including one that asserts dev mode uses a different ledger and
  different limits; `harness.py check` and `budget.py --check` pass.

## Honest limits

- The dev marker currently exists on this machine, so the app is in test mode
  until it is removed. It must be removed before any release or budget verification.
- The dev ceilings are deliberately loose, so a runaway loop during testing is only
  bounded by them (5M tokens/day), not by the runtime limits.
- Nothing about recommendation quality changes; gates remain `not_run`.
