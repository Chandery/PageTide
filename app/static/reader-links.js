/* The PDF's own links over the reader's pages: a citation or a "Section 3" reference jumps to its place in the paper,
   a web address opens in the browser. pdf.js only reports them (page.getAnnotations); the reader draws one transparent
   box per link over the text layer, and keeps where a jump started so 返回 can go back there. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTReaderLinks = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  /* A web address the reader may open: http(s) and mailto only, never javascript: or file:. */
  function safeUrl(url) {
    const s = String(url || '').trim();
    return /^(https?:\/\/|mailto:)/i.test(s) ? s : null;
  }

  /* annotations: page.getAnnotations() items; toView: PDF rect -> [x1, y1, x2, y2] in page pixels (viewport order may
     be flipped). Returns [{left, top, width, height, url} | {..., dest}] for the links that go somewhere. */
  function linkBoxes(annotations, toView) {
    const out = [];
    for (const a of annotations || []) {
      if (!a || a.subtype !== 'Link' || !Array.isArray(a.rect)) continue;
      const url = safeUrl(a.url);
      const dest = a.dest != null && (typeof a.dest === 'string' || Array.isArray(a.dest)) ? a.dest : null;
      if (!url && dest == null) continue;
      const [x1, y1, x2, y2] = toView(a.rect);
      const box = {left: Math.min(x1, x2), top: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1)};
      if (!(box.width >= 1 && box.height >= 1)) continue;
      out.push(url ? {...box, url} : {...box, dest});
    }
    return out;
  }

  /* A link's destination -> {page, top} (top: fraction from the page top, or null), or null when it cannot be found.
     destTop: PTReaderNotes.destTop, which the outline already uses for the same kind of destination. */
  async function resolve(doc, dest, destTop) {
    try {
      const d = typeof dest === 'string' ? await doc.getDestination(dest) : dest;
      if (!Array.isArray(d) || d[0] == null) return null;
      const index = typeof d[0] === 'number' ? d[0] : await doc.getPageIndex(d[0]);
      const page = index + 1;
      return {page, top: destTop(d, (await doc.getPage(page)).view)};
    } catch (e) { return null; }
  }

  return {safeUrl, linkBoxes, resolve};
});
