# 2026-10-22 reader selection and detail backdrop — self-review

Reviewer: coordinating agent, not independent. Class standard: presentation only (app/static), no API, model, storage or IPC change.

## Owner reports and root causes

- **Grey backdrop with a round edge behind the paper detail.** The backdrop is a full-screen `<button>` (click to close).
  The restyle's global `button` rule gives every button `border-radius:999px` and a border, so the backdrop became a giant
  pill. Fix: the backdrop rule removes radius, border, padding and the press transform.
- **PDF text selection drawn as dark, misaligned stripes (Zotero looks clean).** pdf.js 4.6 places invisible text spans
  over the canvas; the browser's own highlight for each span uses the substitute font's ascent/descent, so neighbouring
  lines overlap, and our 45 %-transparent colour darkened every overlap. WebKit also fills gaps between spans. Fix,
  as Zotero does: hide the native highlight, collect the client rectangles of the selected text nodes only (element
  boxes such as pdf.js's end-of-content block, which fills the page while selecting, are skipped), merge them into one
  box per line and column, trim overlaps between neighbouring lines, and paint them in one opaque light blue on a
  per-page layer with `mix-blend-mode:multiply` under the text layer. The real selection stays, so copy, translate and
  ask are unchanged. Repainted on `selectionchange` and after a page is rebuilt at a new zoom.

## Checks

Failing tests first (`tests/test_reader_selection.cjs`); the first run also caught a single-pass merge that left one line in
two boxes. Browser check on a synthetic two-column Times PDF; numbers in the checks file.

## Limits

- Verified in Chromium (the preview pane), not in WebKit, the engine of the macOS app. The method does not depend on the
  native highlight, but WebKit's text rectangles were not measured.
- Not tested on real papers with ligatures, rotated text or right-to-left text.
