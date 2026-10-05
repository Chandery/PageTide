# Self-review: 2026-10-06-responsive-controls

Stage 2 of the plan. What changed: the screen steps (--s, --wrap) now live once in theme.css; the low-density pages (Today, detail drawer, profile, learning map, project settings, creation, settings, weekly report) scale text, controls, spacing and page width with --s through calc(Npx * var(--s)); the library and knowledge-base workspace keeps --s:1; the learning-map drawing is laid out at the scale; the detail drawer has two control sizes and a rebuilt action layout (one filled primary); a link styled as a small button is no longer overridden by .btn; the Today route panel and the map page use a segmented switch with explanations instead of a checkbox and a bare link.

Judgement calls: spacing is scaled together with text (so density stays the same on a big screen rather than only the text growing); pixel sizes of icons, borders, radii and fixed illustration sizes (e.g. the donut chart other than its box, the reader chrome, the project overview) were not converted; "dense" is limited to the organization workspace.

Weak spots: converted by a script over line ranges, so small px values written inside shorthand with functions (calc, min, color-mix) were skipped on purpose; some small decorative sizes remain fixed. The mode switch click was not exercised in a browser. The Tauri window and a real large display were not looked at.
