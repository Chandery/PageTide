/* The reader's annotations and outline, the parts that need no page: turning selected line boxes into page fractions,
   finding the highlight under a click, and resolving a PDF outline to page numbers. The reader (index.html) draws them. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTReaderNotes = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  const COLORS = {yellow: '#ffd400', red: '#ff6666', green: '#5fb236', blue: '#2ea8e5', purple: '#a28ae5'};
  const clamp = (v) => Math.min(1, Math.max(0, v));
  const round = (v) => Math.round(v * 1e5) / 1e5;

  /* lines: [{p, left, top, right, bottom}] in the page's own pixels; size: {p: {w, h}}. Returns stored boxes. */
  function toFractions(lines, size) {
    const out = [];
    for (const l of lines) {
      const s = size[l.p];
      if (!s || !s.w || !s.h) continue;
      const box = {p: l.p, x0: round(clamp(l.left / s.w)), y0: round(clamp(l.top / s.h)),
                   x1: round(clamp(l.right / s.w)), y1: round(clamp(l.bottom / s.h))};
      if (box.x1 > box.x0 && box.y1 > box.y0) out.push(box);
    }
    return out;
  }

  /* The annotation drawn at (fx, fy) on page p, as fractions of the page. The newest wins where highlights overlap. */
  function hit(annotations, p, fx, fy, pad = 0.002) {
    for (let i = annotations.length - 1; i >= 0; i--) {
      const a = annotations[i];
      if ((a.rects || []).some((r) => r.p === p && fx >= r.x0 - pad && fx <= r.x1 + pad && fy >= r.y0 - pad && fy <= r.y1 + pad)) return a;
    }
    return null;
  }

  /* Annotations in reading order: page, then the top of their first line, then left to right. */
  function readingOrder(annotations) {
    const start = (a) => (a.rects || []).filter((r) => r.p === a.page).sort((x, y) => x.y0 - y.y0 || x.x0 - y.x0)[0] || {y0: 0, x0: 0};
    return [...annotations].sort((a, b) => a.page - b.page || start(a).y0 - start(b).y0 || start(a).x0 - start(b).x0);
  }

  /* The vertical position a destination points at, as a fraction from the page top, or null for "the page". */
  function destTop(dest, view) {   // view: the page's [x0, y0, x1, y1] in PDF space, which counts up from the bottom
    const kind = dest[1] && dest[1].name;
    const top = {XYZ: dest[3], FitH: dest[2], FitBH: dest[2], FitR: dest[5]}[kind];
    const height = view ? view[3] - view[1] : 0;
    if (typeof top !== 'number' || !(height > 0)) return null;
    return clamp((view[3] - top) / height);
  }

  /* pdf.js outline items -> [{title, page, top, children}]. Items whose destination cannot be found keep page null. */
  async function resolveOutline(doc, items, depth = 0) {
    const out = [];
    for (const item of items || []) {
      let page = null, top = null;
      try {
        const dest = typeof item.dest === 'string' ? await doc.getDestination(item.dest) : item.dest;
        if (Array.isArray(dest) && dest[0] != null) {
          const index = typeof dest[0] === 'number' ? dest[0] : await doc.getPageIndex(dest[0]);
          page = index + 1;
          top = destTop(dest, (await doc.getPage(page)).view);
        }
      } catch (e) { /* a broken destination leaves the title, not a jump */ }
      out.push({title: String(item.title || '').trim(), page, top,
                children: depth < 8 ? await resolveOutline(doc, item.items, depth + 1) : []});
    }
    return out;
  }

  return {COLORS, toFractions, hit, readingOrder, destTop, resolveOutline};
});
