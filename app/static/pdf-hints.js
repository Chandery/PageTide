/* Reading the first pages of a PDF in the page, with the bundled pdf.js, to find what identifies the paper:
   an arXiv id, a DOI, or title guesses (see creation-pdf.js). Shared by project creation and library import.
   Only these hints, never the file's text, leave this reader; the file itself goes to the local server only. */
(function (root, factory) {
  const api = factory(root);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PTPdfHints = api;
})(this, function (root) {
  'use strict';

  const FONTS = '/vendor/pdfjs/standard_fonts/';
  const PAGES = 2;
  let pdfjs = null;

  async function loadPdfjs() {
    if (pdfjs) return pdfjs;
    pdfjs = await import('/vendor/pdfjs/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.min.mjs';
    return pdfjs;
  }

  const withTimeout = (promise, ms) => new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('读取超时')), ms);
    promise.then((value) => { clearTimeout(timer); resolve(value); }, (error) => { clearTimeout(timer); reject(error); });
  });

  // loadLib and identify are injected so the reader can be tested without pdf.js.
  function create(loadLib, identify) {
    async function extractHints(file) {
      const lib = await loadLib();
      const doc = await lib.getDocument({ data: new Uint8Array(await file.arrayBuffer()), standardFontDataUrl: FONTS }).promise;
      try {
        const texts = [];
        let items = [], pageHeight = 0;
        for (let n = 1; n <= Math.min(PAGES, doc.numPages); n += 1) {
          const page = await doc.getPage(n);
          const viewport = page.getViewport({ scale: 1 });
          const content = await page.getTextContent();
          texts.push(content.items.map((i) => i.str).join(' '));
          if (n === 1) {
            pageHeight = viewport.height;
            items = content.items.filter((i) => i.str && i.str.trim())
              .map((i) => ({ str: i.str, height: Math.abs(i.transform[3]) || i.height, y: viewport.height - i.transform[5] }));
          }
        }
        let info = null;
        try { info = (await doc.getMetadata()).info; } catch (error) { /* metadata is optional */ }
        return identify({ pageTexts: texts, items, pageHeight, info, filename: file.name });
      } finally { doc.destroy(); }
    }
    return { extractHints };
  }

  const shared = create(loadPdfjs, (input) => root.PTCreationPdf.identify(input));
  return { extractHints: shared.extractHints, withTimeout, create, loadPdfjs };
});
