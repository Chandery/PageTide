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

  /* An even word spacing still drifts inside a line by up to a few pixels: TeX puts more space after a full stop and
     kerns some gaps. refine() reads where each word starts on the rendered page (the canvas) and gives every gap its
     own spacing, so selection boxes start and end on the printed letters. */

  /* ink: one flag per pixel column of a line's band (1 = printed). Returns the columns where printing resumes after at
     least minGap blank columns: the starts of words (and of the line's first letters). */
  function inkStarts(ink, minGap) {
    const out = [];
    let blank = minGap;
    for (let x = 0; x < ink.length; x++) {
      if (ink[x]) { if (blank >= minGap) out.push(x); blank = 0; } else blank++;
    }
    return out;
  }

  /* predicted: where each word after the first starts now; starts: where words start on the page; tol: the farthest a
     word may move. Returns each word's shift (0 for the first; a word with no printed start nearby keeps the shift of
     the word before it). */
  function shifts(predicted, starts, tol) {
    const out = [0];
    for (const x of predicted) {
      let best = null;
      for (const s of starts) if (Math.abs(s - x) <= tol && (best === null || Math.abs(s - x) < Math.abs(best - x))) best = s;
      out.push(best === null ? out[out.length - 1] : best - x);
    }
    return out;
  }

  /* textDivs: the page's TextLayer.textDivs after apply() (fitted or not); canvas: the same page, already rendered. */
  function refine(textDivs, canvas, doc = document) {
    const ctx = canvas && canvas.getContext && canvas.getContext('2d');
    const page = canvas && canvas.getBoundingClientRect();
    if (!ctx || !page || !(page.width > 0)) return 0;
    const k = canvas.width / page.width;   // canvas pixels per screen pixel
    const range = doc.createRange(), W = canvas.width;
    // The page's pixels, read once (far cheaper than one read per line); a very large zoomed page is read line by line.
    const whole = W * canvas.height <= 8e6;
    let all = null;
    const pixels = (x0, y0, w, h) => whole
      ? {px: all || (all = new Uint32Array(ctx.getImageData(0, 0, W, canvas.height).data.buffer)), start: y0 * W + x0, stride: W}
      : {px: new Uint32Array(ctx.getImageData(x0, y0, w, h).data.buffer), start: 0, stride: w};
    const plans = [];
    for (const div of textDivs || []) {   // read everything first: one layout for the whole page
      const text = div.firstChild;
      if (div.childNodes.length !== 1 || !text || text.nodeType !== 3 || /rotate/.test(div.style.transform)) continue;
      const words = [];
      for (const m of text.data.matchAll(/\S+/g)) words.push({at: m.index, end: m.index + m[0].length});
      if (words.length < 2) continue;
      const box = div.getBoundingClientRect();
      if (!(box.width > 0 && box.height > 0)) continue;
      const x0 = Math.max(0, Math.floor((box.left - page.left) * k) - 2);
      const w = Math.min(W - x0, Math.ceil(box.width * k) + 4);
      // From above the capitals to the baseline: a T's bar and a Y's arms count, descenders (which lean left) do not.
      const y0 = Math.max(0, Math.round((box.top - page.top + box.height * 0.1) * k));
      const h = Math.min(canvas.height - y0, Math.max(1, Math.round(box.height * 0.7 * k)));
      if (!(w > 0 && h > 0)) continue;
      const {px, start, stride} = pixels(x0, y0, w, h), ink = new Uint8Array(w);
      for (let y = 0, row = start; y < h; y++, row += stride) {   // row by row over 32-bit pixels (RGBA in memory, little-endian)
        for (let x = 0; x < w; x++) {
          if (ink[x]) continue;
          const v = px[row + x];
          if ((v >>> 24) > 100 && (v & 255) * 77 + ((v >>> 8) & 255) * 150 + ((v >>> 16) & 255) * 29 < 38400) ink[x] = 1;   // dark
        }
      }
      const starts = inkStarts(ink, Math.max(1, 0.12 * box.height * k)).map((x) => (x + x0) / k + page.left);
      const predicted = words.slice(1).map((word) => { range.setStart(text, word.at); range.setEnd(text, word.at + 1); return range.getBoundingClientRect().left; });
      const scale = div.offsetWidth ? box.width / div.offsetWidth : 1;   // screen pixels per layout pixel (zoom, pinch)
      plans.push({div, text, words, shift: shifts(predicted, starts, 0.4 * box.height), scale});
    }
    let changed = 0;
    for (const {div, text, words, shift, scale} of plans) {
      const str = text.data, base = div.style.wordSpacing || '0px', parts = [];
      let pos = 0;
      for (let j = 1; j < words.length; j++) {
        const gap = doc.createElement('i');   // not a span: the text layer positions every span absolutely
        gap.textContent = str.slice(words[j - 1].end, words[j].at);
        const extra = (shift[j] - shift[j - 1]) / scale;
        if (Math.abs(extra) > 0.05) { gap.style.wordSpacing = `calc(${base} + ${extra.toFixed(2)}px)`; changed++; }
        parts.push(str.slice(pos, words[j - 1].end), gap);
        pos = words[j].at;
      }
      parts.push(str.slice(pos));
      div.replaceChildren(...parts);
    }
    return changed;
  }

  return {fitLine, baselineShift, apply, inkStarts, shifts, refine};
});
