README v2 checks (2026-10-25), worktree readme-v2
python3 scripts/budget.py --check -> PASS
python3 scripts/harness.py check -> PASS (external-source recheck WARN is pre-existing)
python3 -m unittest discover -s tests -> Ran 3025 tests, OK
All src/srcset image paths in README.md and README-zh.md exist (script check).
Screenshots: fresh empty data dirs, built-in demo project, no key entered, no model call made.
Facts checked in code: key storage (app/source_keys.py, app/gateway.py key_file), OpenAlex 10x quota (app/source_adapters.py),
Baidu cap 40/day (app/baidu_web.py), key URLs (settings.html, source_adapters.py, baidu_web.py), import formats (app/static/import-files.js SIDECAR),
creation modes (project_creation.html), recommend count 1-20 and decay 30 days (settings.html).
Not verified: Qianfan key page URL (marked UNVERIFIED in app/baidu_web.py); Windows build on real hardware.
Layout: Features and Getting started rewritten as vertical stacks after the GitHub-rendered preview showed table columns ignoring widths; re-rendered via .local/readme-preview/build.sh and viewed.
