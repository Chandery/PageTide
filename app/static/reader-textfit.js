/* Puts the PDF reader's invisible text exactly over the printed letters, so a selection or a double-click takes the
   letters the reader sees. pdf.js writes each line in a generic font and stretches the whole line evenly to the line's
   width; on justified lines set in Times (Nimbus Roman) that drifts by up to a word ("learning" was copied as
   "t learning"). Here each line uses the PDF's own embedded font, which pdf.js has already loaded for the canvas, and
   the justification goes into the spaces only. Lines that cannot be fitted safely keep the pdf.js layout. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTReaderTextFit = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  /* str: the line; target: its printed width; natural: its width in the embedded font; fallback: its width in the
     pdf.js font; all at fontSize px. Returns {mode:'words', wordSpacing} or {mode:'scale', scaleX}, or null to keep pdf.js. */
  function fitLine({str, target, natural, fallback, fontSize}) {
    if (!str || !str.trim() || !(target > 0) || !(natural > 0) || !(fontSize > 0)) return null;
    if (Math.abs(natural - fallback) <= 0.002 * natural) return null;   // the embedded font draws none of these letters
    const spaces = (str.match(/ /g) || []).length;
    if (spaces) {
      const wordSpacing = (target - natural) / spaces;
      if (wordSpacing >= -0.3 * fontSize && wordSpacing <= 3 * fontSize) return {mode: 'words', wordSpacing};
    }
    const scaleX = target / natural;
    return scaleX >= 0.8 && scaleX <= 1.25 ? {mode: 'scale', scaleX} : null;
  }

  /* With line-height 1 the baseline sits (1 + ascent - descent) / 2 em below the top of a line. Returns how far the top
     must move so the baseline stays put when the font changes from `old` to `next` (metrics in em). */
  function baselineShift(old, next, fontSize) {
    const base = (m) => (1 + m.ascent - m.descent) / 2;
    return (base(old) - base(next)) * fontSize;
  }

  let ctx = null;
  const widthCache = new Map(), metricCache = new Map();
  function context(doc) { return ctx || (ctx = doc.createElement('canvas').getContext('2d')); }
  function width(doc, family, str, size) {
    const key = family + '\u0000' + str;
    if (!widthCache.has(key)) {
      if (widthCache.size > 20000) widthCache.clear();
      const c = context(doc); c.font = `100px ${family}`;
      widthCache.set(key, c.measureText(str).width);
    }
    return widthCache.get(key) * size / 100;
  }
  function metrics(doc, family) {
    if (!metricCache.has(family)) {
      const c = context(doc); c.font = `100px ${family}`;
      const m = c.measureText('');
      const a = m.fontBoundingBoxAscent, d = m.fontBoundingBoxDescent;
      metricCache.set(family, Number.isFinite(a) && Number.isFinite(d) ? {ascent: a / 100, descent: Math.abs(d) / 100} : null);
    }
    return metricCache.get(family);
  }

  /* textDivs: TextLayer.textDivs; items: the same page's getTextContent() items (one div per item with a str). */
  function apply(textDivs, items, styles, doc = document) {
    const lines = items.filter((item) => item.str !== undefined);
    if (!textDivs || lines.length !== textDivs.length || !doc.fonts) return 0;
    const loaded = new Set();
    doc.fonts.forEach((face) => { if (face.status === 'loaded') loaded.add(face.family.replace(/^["']|["']$/g, '')); });
    let fitted = 0;
    textDivs.forEach((div, i) => {
      const item = lines[i], style = div.style;
      if (!item.str || !loaded.has(item.fontName) || styles?.[item.fontName]?.vertical) return;
      if (/rotate/.test(style.transform)) return;
      const size = Number((/\*\s*([\d.]+)px/.exec(style.fontSize) || [])[1]);
      const own = Math.hypot(item.transform[2], item.transform[3]);
      if (!(size > 0) || !(own > 0)) return;
      const oldFamily = style.fontFamily, newFamily = `"${item.fontName}", ${oldFamily}`;
      const oldMetrics = metrics(doc, oldFamily), newMetrics = metrics(doc, newFamily);
      if (!oldMetrics || !newMetrics) return;
      const fit = fitLine({str: item.str, target: item.width * size / own, fontSize: size,
                           natural: width(doc, newFamily, item.str, size), fallback: width(doc, oldFamily, item.str, size)});
      if (!fit) return;
      const rest = style.transform.replace(/scaleX\([^)]*\)\s*/, '').trim();
      style.fontFamily = newFamily;
      style.top = `calc(${style.top} + var(--scale-factor) * ${baselineShift(oldMetrics, newMetrics, own).toFixed(3)}px)`;
      if (fit.mode === 'words') {
        style.wordSpacing = `calc(var(--scale-factor) * ${fit.wordSpacing.toFixed(3)}px)`;
        style.transform = rest;
      } else style.transform = `scaleX(${fit.scaleX}) ${rest}`.trim();
      fitted++;
    });
    return fitted;
  }

  return {fitLine, baselineShift, apply};
});
