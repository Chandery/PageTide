# Self-review: reader rework (DPR, sidebar, zoom, official text layer, fonts)

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Owner complaints and causes

| Complaint | Cause found | Fix |
|---|---|---|
| 模糊 | The canvas was rendered at CSS size with no device-pixel-ratio scaling, so on a Retina display it was upscaled | Canvas is now sized `viewport × devicePixelRatio` and rendered with a matching transform; the CSS size stays the logical size |
| 没有边栏 | I never built one | Page thumbnail sidebar, **open by default** like the native viewer, built lazily per page; click a thumbnail to jump, current page highlighted by an IntersectionObserver |
| 划词出问题 | I hand-rolled the text layer and positioned spans with a wrong baseline, so selection drifted | Switched to pdf.js's own exported `TextLayer` (verified exported in 4.6.82) with `--scale-factor` set, which positions spans correctly |
| 和之前的阅读器不一样 | No zoom, no page navigation, everything rendered at once | Added zoom in/out/fit-width, per-page numbering, lazy rendering near the viewport, and a **浏览器打开** button for the native viewer when preferred |

## Extra defect found while testing

Loading a real paper in Node produced
`fetchStandardFontData: failed to fetch file "FoxitSerif.pfb"` — the vendored
build had no standard fonts, which makes some glyphs fall back and look wrong.
The `standard_fonts` set (16 files, ~800 KB, with the Foxit and Liberation
licence files) is now vendored and passed via `standardFontDataUrl`.

## Verified

- 95 tests pass; `harness.py check` and `budget.py --check` pass.
- Both inline scripts pass `node --check`; the HTML structure was re-verified
  after the edit (reader markup, module script, closing tags).
- pdf.js data path exercised against a real 50-page paper in Node:
  `PAGES 50`, `VIEWPORT 857x1109 scale 1.4`, `TEXT_ITEMS 189 CHARS 3051`,
  `TextLayer function`.
- All reader assets are served: `pdf.min.mjs`, `pdf.worker.min.mjs`,
  `FoxitSerif.pfb`, `LiberationSans-Regular.ttf`, `LICENSE_FOXIT` → 200.

## Process note

A misguided scripted edit matched a CSS comment that shared a string with the
module's comment and deleted a large block of the page. I detected it with a
structure check, restored the file from the previous commit, and redid the edit
with a unique anchor, verifying byte count, markers and `node --check`
afterwards. No broken file was ever committed.

## Honest limits

- I still cannot visually confirm crispness, sidebar looks or selection feel; a
  headless Chrome run reached `getDocument` but did not finish within the time
  budget, so the DOM-level rendering check is not complete.
- Page rendering is eager per page but only near the viewport; very large PDFs
  are still not optimised.
- CJK `cmaps` are not vendored, so Chinese PDFs may miss some glyphs.
- Recommendation quality remains unproven; quality gates stay `not_run`.
