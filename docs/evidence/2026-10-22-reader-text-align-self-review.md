# 2026-10-22 reader text alignment — self-review

Reviewer: coordinating agent, not independent. Class standard: presentation only (app/static), no API, model, storage or IPC change.

## Owner report and root cause

- **Selecting "learning" copied "t learning"; a double-click did not select the word.** pdf.js 4.6 lays the invisible
  text layer in the generic font it guesses for each PDF font. For this paper (Nimbus Roman, a Times clone, bold in the
  abstract) it guessed `sans-serif`, whose letters are wider, and then stretched each line evenly with `scaleX` to the
  printed width. On justified lines the extra width belongs in the spaces only, so the text layer drifted by up to a
  word mid-line. Measured with a red overlay and a canvas ink test: 28.1 % (page 1) and 26.2 % (page 2) of the text
  layer's spaces sat over printed letters. A drag started on a word therefore started inside the previous one, and a
  double-click often hit the text layer's space and selected nothing visible.
- Nothing in the reader cancels a double-click (no `preventDefault` on mouse events, no `user-select:none` above the
  text layer); the double-click symptom is explained by the drift. The preview pane's double-click is synthetic (no
  `dblclick` event, no selection), so the real double-click was not reproduced.

## Fix

`app/static/reader-textfit.js`, called once pdf.js has built a page's text layer: each line switches to the PDF's own
embedded font (already loaded as a font face for the canvas; per-letter widths matched Times exactly), the leftover
width goes into `word-spacing`, and `top` is corrected so the baseline does not move with the new font's metrics. A
line keeps the pdf.js layout when its font is not loaded, is vertical or rotated, draws none of the letters (measures
the same as the fallback), or would need more than 3 em per space or a scale outside 0.8–1.25. Subset fonts without a
space glyph fall back to the pdf.js font for the space only; the measurement includes it, so the spacing stays exact.

## Checks

Failing tests first (`tests/test_reader_textfit.cjs`). One existing test stubbed `streamTextContent`; the reader now
reads `getTextContent` so the stub was updated. Browser numbers in the checks file.

## Limits

- Chromium only; WebKit's `fontBoundingBoxAscent` and font-face list are standard but were not measured.
- One real paper. Fonts that pdf.js re-encodes away from Unicode are detected only when they draw none of the letters.
