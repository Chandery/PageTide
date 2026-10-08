# Creation and AI failure UX frontend review — 2026-10-08

Reviewer: `creation_ui`, separate implementer from the classification and home-page changes. The creation-page implementation verification below is self-verification; it is not presented as an independent review of those files.

## Independent review scope and outcome

Reviewed `app/static/organization.js`, the changed AI failure presentation in `app/static/index.html`, `tests/test_category_review_async.cjs`, and `tests/test_ai_failure_ui.cjs`.

Result: **passed for the reviewed deterministic UI contracts**. No unresolved blocking defect found. This does not establish live model output quality, original desktop pixel/focus behavior, or a complete release gate.

- Classification failures retain the actual supplied reason in an alert, retain processed/batch counts when known, and expose settings, explicit retry, and explicit local review. There is no automatic retry or automatic application of a local fallback.
- Pending local classification now explains missing metadata, a single-paper evidence limit, or missing repeatable terms, with separate AI and manual-category actions. The proposal remains a preview; paper memberships are changed only by an explicit apply.
- Classification callbacks check review token, project, scope, and epoch. Closing before a job identifier arrives cancels the eventual job. Stale previews, recovery buttons, and applications do not alter another project/view.
- Home-page failures remain in the trigger banner and, for one-paper requests, in that card. Existing summaries remain visible. HTML is escaped. Project switches suppress late failures and notifications; saved failure entries are keyed by project and paper.

Executed `node --test tests/test_category_review_async.cjs tests/test_ai_failure_ui.cjs`: **19 passed**, exit 0. Executed `git diff --check`: exit 0.

## Creation-page implementation verification

Four new behavioral regressions initially failed: stages were not real route concepts, `route_draft` was ignored, discipline errors had no field-local focus behavior, and creation required no graph review. They passed after implementation. Additional coverage exercises explicit map opt-out/finalize and guided answer choices/round-six disabling.

Executed `node --test tests/test_creation_review_fixes.cjs`: **11 passed**, exit 0. Related creation/route static tests: **51 passed**, exit 0. A prior related Node suite (creation exit, route editor, system translations, original four new regressions) ran **84 passed**, exit 0. These VM tests execute shipped functions; they are not native desktop tests.

The first full Node run exposed five older VM-fixture failures because those fixtures extracted only the generation/manual handler and omitted its newly shared validation/change helpers. The fixtures now load the actual shipped helpers, preserving their original assertions. The final `node --test tests/*.cjs` run passed **445 tests**, failed **0**, exit 0; private full output is `.local/creation-ai-ux-verification/node-final.txt`.

The browser verification used an independent temporary root containing only a copy of `harness/budget.json`, a separate temporary data directory, `PDH_DEV=1`, `Gateway.set_enabled(False)`, cleared provider-key environment entries, and a process-wide `urllib.request.urlopen` guard that throws before any outgoing network request.

Observed in the real browser:

- Missing discipline shows the error beside the discipline selector and focuses it.
- Quick creation with the model disabled shows the exact cause, settings/retry actions, and a visible editable local goal graph.
- Adding a stage and submitting commits the stage into the graph; an unconfirmed graph focuses its confirmation checkbox and does not create a project.
- Confirming creates a real temporary project. Its home page displays “按学习图推荐”, both goal and added-stage nodes, and target progress `0 / 2`. The test-mode counter remains zero.
- Guided creation with AI disabled retains the local graph, reports the switch-off reason, and keeps successful AI turn count at `0 / 6`.

The browser check exposed two additional defects that were corrected: programmatic stage inputs could bypass `change` and submit a stale graph, and a local graph incorrectly showed the AI regeneration action. Submission now commits visible stages first; regeneration is shown only for a cached AI plan. Unchanged AI stage prose retains its AI authorship when its title is edited. A further deterministic regression verifies that an explicit replacement AI concept plan rebuilds the bound stage rows, so old stage titles cannot be silently re-added or overflow the new plan's node limit on submission.

After the owner clarified that the brainstorm itself should return the learning structure, a failed-first `setDraft` regression confirmed that old stage rows could disagree with a supplied AI concept graph. The frontend now recognizes `route_draft.source = ai_guidance`, replaces only an untouched automatic map, rebuilds stage rows from the actual concepts/ids, preserves the model's terms, introductions, prerequisite edges and targets, and marks the structure as an AI proposal requiring review. Manually edited or explicitly dropped graphs stay protected. This test proves frontend treatment of a supplied structured response, not live model adherence to the expanded contract.

## Independent creation review follow-up — 2026-10-09

The separate `ai_guide` reviewer found three P2 creation issues. All three were reproduced with additional production-handler tests before correction: starting a manual map retained old bound stage rows; a pending guided request disabled keyword input but left deletion buttons active; and clearing a bound stage could leave the old concept saved under an unchanged confirmation checkbox.

Corrections clear old stage rows when starting a manual map, lock both keyword input and chip deletion while awaiting guidance, and require a nonempty title for a bound stage. Any stage input now revokes map confirmation and protects the partial manual edit from a later response; a new, unbound empty placeholder can still be ignored. These corrections added no model calls or new user strings.

Executed the complete Node suite again: **445 passed, 0 failed**, exit 0. Executed the affected Python creation/route static suite again: **51 passed**, exit 0. `node --check app/static/project-creation.js` and `git diff --check` passed. The failed-first output is `.local/creation-ai-ux-verification/node-review-followup-failing.txt`; the affected Python output is `.local/creation-ai-ux-verification/python-frontend-final.txt`. Reviewer re-verification is reported separately, rather than self-rated here.

## Unexpected live call and fixture correction

The first temporary data-directory-only server was insufficiently isolated: the gateway legitimately falls back to the checkout's legacy key file. One `project_guidance` request unexpectedly reached the runtime provider before this was noticed. The server was immediately stopped. No subsequent model click used that server, no key was printed or changed, and the original temporary usage ledger was preserved.

The actual reconciled record reports model `deepseek-flash`, input **157**, output **188**, total **345** tokens, reported cost **USD 0.0002727**. Its reservation of USD 0.00096 was reconciled. That call was recorded in the original temporary **runtime** `usage.jsonl`; it was not originally in developer mode and must not be relabeled as such. It did not use the owner's production data directory or production usage ledger. The work-unit budget evidence must include this actual unexpected call rather than claiming zero live calls for the whole session.

The replacement fixture uses all four independent barriers described above. The original ledger and replacement temporary library remain preserved for audit; the provider key and the owner's library were never edited.

## Limits

The browser checks prove local graph creation and visible failure recovery, not stable six-round live brainstorm behavior. Structured guided choices are covered with a deterministic response fixture. Release build, full repository checks, and the independent review of the creation implementation are recorded by the parent work unit.
