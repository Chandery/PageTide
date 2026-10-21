# 2026-10-22 learning-map beta switch — self-review

Reviewer: implementing agent, not independent. The behaviour is feature-level (settings schema, recommendation defaults, page behaviour; no gateway, prompt, provider, IPC contract or migration change), but the change record is class critical because the unit edits `harness/tasks.json` (path rule in scripts/harness.py). Critical needs an independent review before any release; none has been done. Baseline main `0c288b3`, worktree `route-beta-switch`.

## Specification

Owner request and confirmed scope are in task `FEAT-ROUTE-BETA-SWITCH` and ADR 0035. Behaviour: setting `routeBeta` (default off). Off means every recommendation path is hotspot mode and every learning-map entry point is hidden; the stored map, progress, manual marks and watch flags are untouched; on restores everything.

## Cost and privacy

Zero model tokens and no new outbound field. The only change to outbound traffic is the public-metadata `from_date` of the candidate refresh: 30 days by default in hotspot mode instead of five years, unless the owner chose a time preference. The core daily minimum stays 0 tokens. No budget record changed (`budget.py --check` passes).

## How it was checked

- Failing first: `tests/test_route_beta.py` (setting, gate, data kept, no map cards when off, profile report, hotspot window, boost, owner values win, served pages) failed before the implementation; 11 of 14 failed or errored.
- Making the gate default-off broke 60+ legacy tests that assumed an enabled map or a wide time window. They were not loosened: the fixtures now say what the owner would have set (`recommendation_fixtures.legacy_recommendation_settings`: all-time window, beta on where a map is used). Three tests that asserted the old default window were rewritten to assert the 30-day hotspot default and the owner override. Two tests whose fixture dates are in the past now use relative dates.
- Front end: `tests/test_route_beta_ui.cjs` runs the real `paper-context.js`, the real settings page load/save handlers and the real creation-page map literal with the flag on, off and absent. Whole-file checks assert the marked entry points exist. These are source-level checks for the parts that are DOM markup.
- Browser: the worktree's server was run on a synthetic data directory (footer showed the temporary path) with one project that had a two-concept map. Off: home shows only the hotspot line, 400-day-old paper not recommended, creation page uses the map-free sentences, learning-map page shows the "not turned on" notice. Switched on through the real settings page and saved: the map panel, progress and the "热点模式" switch appeared. Switched off through the settings API: back to hotspot.
- Full suites and repository checks: see the companion checks file.

## Findings during the work

- The settings page saves the whole file, so the new key had to be part of the saved object (covered by a round-trip test).
- A first design that hid the creation map block left the Create button demanding a map; the creation page now starts with "no map" when the beta is off, and the leave-page "unsaved" check ignores that automatic state (tested).
- The settings page displayed defaults (boost 0.2, one week) that the backend never used (0, all time). It now shows the real defaults; users who saved settings before have explicit values and are unaffected.
- While the synthetic server ran, opening the app triggered the normal daily refresh against the public source (default settings), which added ~100 public records to the synthetic data directory only. No model call and no private data were involved.

## Limits

- Not run: native window, real library, real recommendation quality with the 30-day / 0.5 defaults (a product judgement, not measured), library graph view and weekly report with real content in the browser (covered by code and unit tests only).
- A page that is already open does not notice the switch until it reloads.
- The AI guidance reply may still contain a map while the beta is off; it is ignored, not stored.
- No `.app` build was made, by design.
