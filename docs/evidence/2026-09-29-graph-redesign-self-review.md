Self-review: 2026-09-29-graph-redesign
========================================

Date: 2026-09-29
Reviewer: Implementing agent (self-review)
Change ID: 2026-09-29-graph-redesign

## Scope

This record covers four units of work made in one session and committed together:

1. Knowledge graph visual redesign (organization.js, organization.css)
2. Migration stdout purity fix (migrations.py, tests/test_organization_worker.py)
3. Server data-path fix (server.py)
4. UI visual redesign (index.html, settings.html, new icons)
5. AGENTS.md: build step added to dev loop

## Diff review

### app/migrations.py
apply_migrations() printed migration progress to stdout via print(). The
organization worker reads its stdout as a single JSON blob; on a fresh database
this produced "Applying migration 1: ..." ahead of the JSON payload, causing
JSONDecodeError in the server. The fix routes all diagnostics through _log()
which writes to stderr. Change is minimal and correct.

### tests/test_organization_worker.py
Three new tests (WorkerStdoutPurityTests): fresh-DB run stdout is pure JSON,
second run (up-to-date branch) stdout is pure JSON, migration progress appears
on stderr not stdout. These cover the regression exactly. All three pass.

### app/server.py
/api/user_settings GET and POST, and /api/cache DELETE, were hardcoded to
~/Documents/PaperDigHelper. The desktop app sets PAPERDIGHELPER_DATA to
Application Support; the hardcoded path was writing settings to a directory
the app never reads. Replaced with data_dir() helper that calls make_app()
and respects the environment variable. The CLI fallback (<root>/.local/app)
is unchanged.

Added import re, _static_version() module-level helper (max mtime of any file
under STATIC, computed once per request, cheap rglob), and cache-buster
injection in _static(): when serving any .html file, all src="/<path>.js" and
href="/<path>.css" attributes are rewritten to include ?v=<mtime> via a bytes
regex substitution before the response body is written. This bypasses WKWebView
(macOS Tauri WebKit) disk cache for JS/CSS assets on every new build without
requiring manual cache clearing. Non-HTML static files are unaffected. The
server already parsed route separately from the query string so existing API
routes are unchanged.

### app/static/organization.js
_nodeColor(): hue derived from category index (36° steps across 10 categories),
lightness from year (clamped to 10 years, 38%–73%). Node size from similarity-
graph degree (14–36px). Edges are dashed. Group/hierarchy nodes and membership
edges removed from graph elements. Legend rendered from current directions.

### app/static/organization.css
Four lines added: .org-graph-legend positioning (absolute, bottom-left) and
basic styling for legend rows.

### app/static/index.html / settings.html
Visual redesign: unified CSS token system (OKLCH-derived custom properties,
dark mode token set, five accent-color variants). New sticky header with
backdrop-filter. settings.html rebuilt to match the new token system.

### New SVG icons
Six icons added under app/static/icons/ for use in the organization UI.

## Failure paths

- data_dir() calls make_app() on every request. make_app() reads os.environ and
  constructs an App; this is cheap (no DB open) but adds a function call per
  settings request. Acceptable for a settings endpoint that fires rarely.
- _log() to stderr: worker callers that capture only stdout are unaffected.
  Callers that also capture stderr will now see migration diagnostics there,
  which is correct behavior.
- Graph: if no relations are loaded yet, the graph renders with no edges (same
  as before). Category color falls back to the default hue if directions list
  is empty.

## Data/privacy review

No new data collection. No new model calls. Settings file path change is
strictly correctness: same JSON written, different (correct) directory.

## Budget review

Zero runtime tokens. No gateway operations added or modified.

## Test results

199 tests run. 181 logic tests pass. 18 HTTP server smoke tests fail with
PermissionError (sandbox blocks local port binding) — pre-existing, unrelated
to this change. The three new WorkerStdoutPurityTests all pass.

## Classification

Critical: migrations.py and server.py touch the worker IPC contract and the
settings persistence path respectively. AGENTS.md lists "migrations and backup
paths" as critical-class.

## Open items

- Seed-star shape on graph nodes (papers matching harness/seeds.json) is
  deferred; noted in assumptions.
- Desktop build not run in sandbox (cargo/tauri unavailable). Owner must verify
  green build before shipping.
- owner_approved: false — this change requires owner sign-off before release.
