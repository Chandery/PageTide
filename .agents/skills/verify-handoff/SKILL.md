---
name: verify-handoff
description: Close a PageTide work session or assess a release with fresh check evidence, honest unfinished gates, budget status and portable agent handoff.
---
# Verify and hand off

1. Re-read actual Git state and the task record. Confirm which acceptance items are implemented, tested, blocked or only designed.
2. Run current commands against the final files: budget parity, harness checks, unit tests, and review the change record. After any material fix rerun affected checks.
3. Update task/evaluation status only with evidence. A passed harness test is not a passed PDF, performance, provider or budget-gateway evaluation.
4. For release, run `python3 scripts/harness.py check --release` and review with `--release`. Check independent review and user release approval, sources/prices, real macOS package and restore evidence. Do not weaken gates to get green.
5. Update docs/HANDOFF.md concisely: active task, branch/commit/dirty work, completed outcomes, exact check commands/results, unverified risks, budget approval/usage status and next concrete action.
6. Keep evidence sanitized; real API logs, private notes, PDFs and keys stay out of Git. Refer to files instead of pasting huge logs into AGENTS or chat.
7. Receiving agent verifies instructions, Git and checks independently, then continues one bounded task. No hidden personal memory or vendor-specific task store is required.

If interrupted or out of budget, save a truthful blocked/in-progress handoff, including failing commands. Never mark unfinished work done to simplify handoff.
