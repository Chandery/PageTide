/* Which PDF page the reader is showing. pdf.js pages are pre-rendered well beyond the view, so "a page became
   visible to the pre-render observer" is not "the page being read"; this picks the page across the middle of the
   view, or else the one with the most visible height. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PDHReaderPage = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  /* view: {top, bottom}; pages: [{n, top, bottom}] in the same coordinates. Returns a page number or null. */
  function inView(view, pages) {
    const middle = (view.top + view.bottom) / 2;
    let best = null, shown = 0;
    for (const p of pages) {
      if (p.top <= middle && p.bottom >= middle) return p.n;
      const height = Math.min(p.bottom, view.bottom) - Math.max(p.top, view.top);
      if (height > shown) { best = p.n; shown = height; }
    }
    return best;
  }

  return {inView};
});
