# Stage08 navigation independent review

Baseline6302862, branch codex/route-discovery-rework. Critical unit: shared paper context/HTTP contract, graph navigation and async lifetime guards. Stage08 is still in_progress/E08not_run; local evidence is not native acceptance.

Self review: categories remain global library manual memberships; learning matches are read-only project Map/title/abstract matches (at most2); current-purpose means the latest project batch, never the last historical exposure. Focus only includes a saved paper from this project, replaces one displayed paper and keeps120 cap. Unmatched entry states complete count and omitted-paper fallback. Route off keeps graph and navigation. All displayed source fields/IDs are escaped. Default core0 model tokens; no new external scope or source call.

Independent reviewer /root/route_logic inspected actual diff and exercised production functions with delayed replies. Found two P2 defects:

1. After a successful P1 Map, a failed/unavailable P2 Map could leave the old P1 unmatched overlay visible. Fixed by clearing the overlay before every Map read, with failure/unavailable regressions. Original VM reprobe now returns hidden=true and empty overlay.
2. A pending public navigate(one) could overwrite a newer selection(two) or reopen closed details after slow relations completed. Fixed by invalidating navigation generations on paper selection, close, graph taps, project/view changes and leaving the library. Production navigate+handle regressions and original reprobe now retain the newer key.

Final independent targeted command PYTHONPATH=tests python3 -m unittest test_route_detail test_organization test_route_goal test_route_full_flow -q:73 passed, exit0. Node command node --test tests/test_paper_context.cjs tests/test_organization_ui.cjs tests/test_i18n.cjs tests/test_refresh_status.cjs:104 passed, exit0. Budget/harness/diff checks passed. No remainingP1/P2 in navigation scope.

Final small increment: reviewer checked packaged off-context assertions now use the same route_pid/en with saved_in_project and route_enabled=false, rather than a different project. Reviewed restart/undo completed-day batch reuse and independently ran test_route_full_flow:1 passed exit0; diff check passed. No new blocker.

Implementation tests initially exposed missing context/focus support; two initial fixture mistakes (category color and off-mode literal) were fixed without changing product contracts. Full-suite failures exposed a missing complete unmatched-label translation and a test extraction boundary moved by selectView; translations and exact handler extraction were repaired. Existing behavior assertions and new delayed-response tests remain.

Fresh package evidence is separate from actual UI rendering and human usability. Prior browser access was explicitly rejected by policy because the user denied access, and native surfaces were locked. No alternate browser/surface/command workaround was used. A human unlock/authorization request is pending; no permission is inferred from elapsed time. Real model quality, recommendation value, fulltext language accuracy, tokenizer/billing and8GB resources remain unmeasured.
