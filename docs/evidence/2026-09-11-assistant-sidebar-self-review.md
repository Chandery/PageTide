# Self-review: assistant no longer covers the PDF, direct questions, sidebar fixes

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Owner feedback and fixes

| Complaint | Cause | Fix |
|---|---|---|
| 进入 PDF 后助手挡住内容 | The floating orb and panel are `position:fixed`, so they sat on top of the full-screen reader | The orb is hidden while the reader is open (`body.reader-open .pet { display:none }`) and the toolbar's 「对这篇提问」opens the panel; when the panel is open in the reader, the page area reflows instead of being covered (`#reader.petside .rbody { margin-right:424px }`) |
| 不划段落也要能直接提问 | The panel already accepted free questions, but the orb was unreachable behind the reader | Same fix; the input works with no selection (context = title + abstract), and the toolbar button focuses it |
| 页数一多缩略图被压扁、边栏不能滑 | Sidebar thumbs are flex children with default `flex-shrink:1`, so 50 pages compressed into the column height, and my markup had no scroll affordance | Thumbs are now `flex:0 0 auto` at a fixed 120px width, the sidebar is `overflow-y:auto`, and the row container gets `min-height:0` |
| 希望助手给几个可点的提问 | — | Six suggested questions are rendered as chips in the panel; clicking one sends it immediately |

## Extra improvement made while fixing the above

Thumbnails were rendered eagerly page-by-page; on a 50-page paper that is slow
and was part of the compressed look. They now render lazily through an
IntersectionObserver (`renderThumb`) as they scroll into the sidebar.

## Verified

- 95 tests pass; `harness.py check` and `budget.py --check` pass.
- Both inline scripts pass `node --check` after the edits.
- The served page contains the new markers (`renderThumb`, `petSugg`,
  `reader-open`, `petside`, `standardFontDataUrl`); `GET /` returns 200.
- Structure was re-checked before committing; unique anchors were used this time.

## Honest limits

- Still no visual confirmation from me: I cannot see the rendered page, so the
  reflow width (424px) and chip wrapping are judged from the CSS, not observed.
- Suggested questions are static; they are not tailored to the specific paper.
- Very large PDFs still render every page lazily but keep all canvases in memory.
- Recommendation quality remains unproven; quality gates stay `not_run`.
