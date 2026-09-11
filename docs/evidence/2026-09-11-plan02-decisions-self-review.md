# Self-review: PLAN-02 owner decisions folded into the plan

Date: 2026-09-11 (UTC). Reviewer: implementing agent. Scope: task/requirement/evaluation registries, budget defaults, and planning docs updated with the owner's confirmed answers. **Not** an independent review; no runtime or quality claim.

## Decisions recorded

- Domain/language: English AI / world models; Chinese UI and explanations.
- 10 positive seed papers recorded in `docs/DOMAIN.md`; **no explicit negatives** → kept as unknown, no auto negatives.
- v1 scope: recommendation/profile core + PDF download/archive + AI daily triage with follow-up QA. Notes/highlights/selection-translation deferred.
- macOS-only, no server, local storage; Zotero read-only/import only.
- AI triage and follow-up QA default-on; `selection_translate`, `query_expand`, `weekly_digest` remain default-off.

## Registry changes checked

- New `R-PDF` + `E-PDF-ARCHIVE` (blocking) + task `PDF-01`; `R-CAPTURE`/`E-CAPTURE` moved to deferred/non-blocking.
- `E-AI-OPTIONAL` and `E-BUDGET` made blocking because the AI layer is now in v1.
- `PLAN-02` moved `blocked → in_progress`; READ-01/READ-02 marked blocked with reasons.
- Traceability: every requirement covered by a task, every evaluation referenced by a requirement (orphan check), all gates exist.
- Budget arithmetic unchanged by the `enabled_by_default` flags; generated doc still byte-identical.

## Honest limits

- Seeds are owner-provided and **not yet resolved to canonical IDs**; venues unverified.
- The numeric AI ceilings are still **not explicitly accepted** by the owner; `approved_by_owner` stays false.
- Data-source egress scope and PDF storage location (local folder vs Zotero) are still open.
- No candidate was installed/run; no model call; all evaluations remain `not_run`.
