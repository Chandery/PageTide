# 2026-10-22 UI restyle — self-review

Reviewer: implementing agent, not independent. Class standard: CSS tokens and presentation rules only; no model call, route, IPC, schema, prompt or stored-data change.

## What changed

The owner found the warm-paper / serif / bookmark-red look too close to a well-known assistant product and supplied screenshots of another app as the target feel: cool grey page, white cards with large radii, pill controls, one saturated blue, heavy sans headings, almost no borders. Colours were tried on a temporary swatch bar (removed again) and the owner kept blue.

- `app/static/theme.css`: new light and dark palette, `--display` replaces `--serif`, larger radii, flat shadows, segmented control and label shapes. Every text/surface pair still passes WCAG AA in `tests/test_ui_contrast.py`.
- `app/static/index.html`: the "VISUAL LAYER" block was restyled (header, tabs, buttons, cards, inputs, switch, detail rail, chat, toasts, project switcher backdrop).
- Other stylesheets only had `var(--serif)` renamed to `var(--display)`; they follow the new tokens.
- `tests/test_route_graph_page.py`: one literal changed (`.hero h1` 28px → 32px). The test still asserts that sizes scale with `--s`.

## Constraints kept

- No negative letter-spacing (existing layout rule); the first draft used it and `test_ui_layout` caught it.
- Status, PDF and keyword labels keep three different shapes (pill, rounded square, small square); `test_today_cards` caught a draft where two were pills.
- The accent picker stays retired; no `data-accent` block was added.

## Verified

Light and dark home, paper detail rail, library, profile, settings, project creation and the empty learning-map page were opened in the browser pane on a synthetic data directory (not the real database). Full Python suite and repository checks: see the companion checks file.

## Not verified / limits

- Pages that need real data were not seen with content: learning-map graph, import batches, weekly report, project switcher overlay.
- The logo and favicon are still cream, navy and red and do not match the new palette. Not changed; owner decision pending.
- Contrast was checked by token pairs, not by sampling rendered pixels.
- No native window check and no `.app` build: another agent may be testing the main build, so none was made.
