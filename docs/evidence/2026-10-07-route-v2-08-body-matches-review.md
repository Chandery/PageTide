# Current-body matching independent review

Baseline deec31a on codex/route-discovery-rework. Critical unit. Reviewer /root/route_logic independently inspected current diff, temporary backend fixtures and production UI functions. Previous navigation review is not reused.

Six P2 findings and confirmed fixes:

1. A usable abstract was hidden as pending when only verified-language PDF checking exhausted its allowance. Learning pending/deferred now requires missing usable abstract. Abstract relations/progress remain ready while language remains unverified. Actual fixture reprobe passed.
2. Graph matches and progress independently recaptured body evidence; an intervening PDF replacement mixed an old body edge with newer progress. They now share captured matching rows and one physical verification budget. Immediately before returning, current PDF identity/version and bounded text are compared without rehashing; any changed captured body rejects the derived response. Detail has the same guard, including changes during explanation rendering. Original replacement probe and new regressions passed.
3. Body-source provenance did not mean all terms occurred in the body: title also participates. Hover now explicitly says title or current-version body. Original title-only/body-source probe passed without inventing body hits.
4. Ready graph/context caches froze unmatched results after first fulltext extraction. All Map contexts/graphs now expose re-verification, clearing both caches and invalidating older replies. Successful fulltext saving and reader return invalidate the views. Deferred-progress evidence has a re-verification entry even without pending saved papers. Actual contextFor and handle probes passed; hidden views do not request/loop.
5. Today’s open drawer retained old learning context beneath the reader. Its actual dRead handler now closes/invalidate-token before opening the reader; reopening reads new matching evidence. Actual drawer/handler VM regression and independent recheck passed.
6. A late reader save could cancel a newer project's in-flight graph/context without another request. Visible invalidation now starts a replacement read in the current scope, ignoring old replies. Hidden views only clear caches. Independent graph/context cross-project interleaving probes passed, no permanent loading state or automatic retry loop.

Final independent commands:
- PYTHONPATH=tests python3 -m unittest test_recommendation_eligibility test_route_detail test_route_goal test_route_batches -q:103 passed, exit0,1.771s (tool output72f63f).
- node --test tests/test_paper_context.cjs tests/test_organization_ui.cjs tests/test_route_detail.cjs tests/test_i18n.cjs tests/test_paper_policy.cjs:128 passed, exit0 (c1d4e9).
- Actual graph/context/hidden async production-VM probe:exit0 (80934e).
- Final diff/budget/harness:exit0 (ca6ba3).
These are recorded tool outputs, not a separately saved independent log. Earlier broader target runs128Python/126Node also passed.

Reviewer confirmed test_harness only copies the registered isolated-flow evidence into its fixture; it does not weaken source evidence checks. Package additions operate on temporary body_pid/PDF, use the same project for Routeoff and validate changed PDF. Actual new build/package execution was by the main agent, not the independent reviewer. Final verdict:passed, no remainingP1/P2 for this unit; not native or whole-release acceptance.

Self review: body is bounded/local/version-bound and absent from outbound/card/context payloads. Learning matching writes no categories/mastery/exposure; actual hash proofs remain bounded local settings only. At most2 displayed unit matches vs strongest-unit progress preserved. No new model operation/source call/approval. Daily mandatory model tokens0. Explicit pending states and retries preserve uncertainty; no silence feedback. Final1461Python/280Node, fresh backend/App, local signing verification and signed-package backend passed. Initial harness fixture and unsigned local resource-seal failures are recorded honestly, then fixed/rechecked. Native permission denial is not bypassed; E08not_run/taskin_progress and original release gates retained.
