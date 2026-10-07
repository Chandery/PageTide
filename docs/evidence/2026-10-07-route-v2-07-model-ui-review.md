# Independent review — Route shared brief/model/UI

Reviewer /root/route_logic, read-only. Final independent local contract/UI/HTTP review passed; no remaining P1/P2.

Backend153 tests and raw probes closed P2s: mixed legacy/new claims/counts; cancelled cached-draft resurrection; same-connection confirmation commit; newer preview overwrite; human-description visibility; complete40 message overhead; invalid Unicode reservation; deleted legacy project reservation; busy flag after write failure.

UI review found confirmation-era new text dirty loss, inaccurate paid bad-reply wording, hidden regeneration after cached Map drop and English gaps. Fixes and actual-handler regressions added; final independent recheck passed.

No real model, source or library calls. Browser/native acceptance is not established by this review.

Final independent commands and results (tool outputs supplied by reviewer, no raw local log retained):

- PYTHONPATH=tests python3 -m unittest test_route_map_model test_route_revision_http test_i18n test_project_creation_ui -q:70 passed,exit0.
- node --test tests/test_route_brief.cjs tests/test_route_brief_page.cjs tests/test_creation_brief_page.cjs tests/test_route_editor.cjs tests/test_i18n.cjs:90 passed,exit0.
- python3 scripts/budget.py --check;python3 scripts/harness.py check;git diff --check:each exit0.
- Actual173651UTF8-byte full Map request,40nodes114edges200Unicode-character IDs, now accepted and actualHTTP saved without model. /api/route retains1000000-byte raw cap;131072 is session request/model response bound. Added typed boolean validation.
- Final reviewer confirms newer-text dirty handling, explicit cached-map regeneration,5xx unknown accounting,restart/day counters, legacy reservation failure recovery. Initial153-backend result is earlier-version evidence, not mislabeled final70.
- Weekly fixture used hours=1 and at UTC midnight assigned days_ago=0 to yesterday. Remove only that subtraction; daily assertions and product code unchanged.

Native surfaces locked; browser policy explicitly rejected test-page access because user denied permission. No alternate browser/surface/workaround. Actual browser/native flow and real-model gates remain unverified.
