# Self-review: 2026-10-05-graph-origin

Owner report: the knowledge page shows "相似关系未加载：undefined is not an object (evaluating 'p.x')；现有分类关系仍可查看".

Cause and fix: see the checks file. The origin choice is now a small pure function (`graphOrigin`) that only returns a node that is drawn, the camera falls back to the first node, and the two nearby places that read a position from a possibly empty result (the origin and the "closest node" search) are guarded. No data, API or layout change; the similarity relations were being computed correctly, only the redraw after them failed (which is why the category relations still showed).

Weak spot: the fix is covered by a unit test of the pure function and by a before/after run in a browser preview (Chromium-based, not the Tauri/WebKit window), so the exact Safari message was not seen, only the equivalent one.
