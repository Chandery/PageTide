/* Paints the PDF reader's text selection the way Zotero does: one light box per line, behind the text, never stacking.
   The browser keeps the real selection (copy, translate, ask still work); only its own per-span highlight is hidden,
   because on pdf.js's invisible, absolutely placed spans it overlaps between lines and darkens into stripes (WebKit). */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTReaderSelection = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  /* rects: [{left, top, right, bottom}] in one page's own coordinates. Returns one box per line piece, top to bottom,
     with the boundary between neighbouring lines moved to the middle of their overlap. */
  function mergeLineRects(rects) {
    const pieces = rects.filter((q) => q.right - q.left >= 0.5 && q.bottom - q.top >= 0.5)
      .map((q) => ({left: q.left, top: q.top, right: q.right, bottom: q.bottom}))
      .sort((a, b) => a.top - b.top || a.left - b.left);
    const sameLine = (a, b) => {   // same line and same column
      const overlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      const gap = Math.max(b.left - a.right, a.left - b.right);
      const ha = a.bottom - a.top, hb = b.bottom - b.top;
      return overlap >= 0.5 * Math.min(ha, hb) && gap <= 1.2 * Math.max(ha, hb);
    };
    let lines = pieces;
    for (let changed = true; changed;) {   // repeat: a merged box can now reach a piece it could not reach before
      changed = false;
      const next = [];
      for (const q of lines) {
        const line = next.find((l) => sameLine(l, q));
        if (line) { Object.assign(line, {left: Math.min(line.left, q.left), top: Math.min(line.top, q.top),
                                         right: Math.max(line.right, q.right), bottom: Math.max(line.bottom, q.bottom)}); changed = true; }
        else next.push(q);
      }
      lines = next;
    }
    lines.sort((a, b) => a.top - b.top || a.left - b.left);
    for (let i = 1; i < lines.length; i++) {
      for (let j = 0; j < i; j++) {
        const a = lines[j], b = lines[i];
        const sideBySide = Math.min(a.right, b.right) - Math.max(a.left, b.left) <= 0;
        if (sideBySide || a.bottom <= b.top) continue;
        const mid = (Math.max(a.top, b.top) + Math.min(a.bottom, b.bottom)) / 2;
        if (a.top < b.top) { a.bottom = Math.min(a.bottom, mid); b.top = Math.max(b.top, mid); }
      }
    }
    return lines.filter((l) => l.bottom - l.top >= 0.5);
  }

  /* The client rectangles of the selected text only: element boxes (whole spans, pdf.js's end-of-content block, which
     fills the page while selecting) are not text and must not be painted. */
  function textRects(range, scope) {
    const out = [];
    const doc = scope.ownerDocument;
    const common = range.commonAncestorContainer;
    const top = common.nodeType === 3 ? common.parentNode : common;
    const walker = doc.createTreeWalker(top, 4 /* NodeFilter.SHOW_TEXT */);
    const piece = doc.createRange();
    let node = common.nodeType === 3 ? common : walker.nextNode(), seen = 0;
    while (node && seen < 20000) {
      if (range.intersectsNode(node) && node.parentElement?.closest('.textLayer') && scope.contains(node)) {
        const start = node === range.startContainer ? range.startOffset : 0;
        const end = node === range.endContainer ? range.endOffset : node.length;
        if (end > start) {
          piece.setStart(node, start); piece.setEnd(node, end);
          for (const q of piece.getClientRects()) out.push(q);
        }
      }
      seen++;
      node = common.nodeType === 3 ? null : walker.nextNode();
    }
    return out;
  }

  function paint(scope) {
    scope.querySelectorAll('.pg > .selLayer').forEach((layer) => layer.replaceChildren());
    const sel = scope.ownerDocument.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;
    const pages = [...scope.querySelectorAll('.pg')].map((pg) => ({pg, box: pg.getBoundingClientRect()}));
    const byPage = new Map();
    for (let i = 0; i < sel.rangeCount; i++) {
      for (const q of textRects(sel.getRangeAt(i), scope)) {
        const cx = (q.left + q.right) / 2, cy = (q.top + q.bottom) / 2;
        const hit = pages.find(({box}) => cx >= box.left && cx <= box.right && cy >= box.top && cy <= box.bottom);
        if (!hit) continue;
        const k = hit.pg.offsetWidth / (hit.box.width || 1);   // undo a pinch-zoom transform on the page surface
        const local = {left: (q.left - hit.box.left) * k, right: (q.right - hit.box.left) * k,
                       top: (q.top - hit.box.top) * k, bottom: (q.bottom - hit.box.top) * k};
        if (!byPage.has(hit.pg)) byPage.set(hit.pg, []);
        byPage.get(hit.pg).push(local);
      }
    }
    for (const [pg, rects] of byPage) {
      let layer = pg.querySelector(':scope > .selLayer');
      if (!layer) {
        layer = scope.ownerDocument.createElement('div');
        layer.className = 'selLayer';
        layer.setAttribute('aria-hidden', 'true');
        pg.insertBefore(layer, pg.querySelector('.textLayer'));   // under the text layer, over the canvas
      }
      for (const l of mergeLineRects(rects)) {
        const box = scope.ownerDocument.createElement('i');
        box.style.cssText = `left:${l.left}px;top:${l.top}px;width:${l.right - l.left}px;height:${l.bottom - l.top}px`;
        layer.appendChild(box);
      }
    }
  }

  const api = {mergeLineRects, textRects, paint, install, current: null};

  function install(scope) {
    let frame = 0;
    const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; paint(scope); }); };
    scope.ownerDocument.addEventListener('selectionchange', schedule);
    api.current = {repaint: schedule};
    return api.current;
  }

  return api;
});
