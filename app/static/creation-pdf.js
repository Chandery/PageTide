/* Recognising which paper a dropped PDF is, and what a pasted string is.
   Pure functions, no DOM and no network: the page extracts text with the bundled pdf.js and
   passes it in. Only an identifier (arXiv id, DOI) or a title found in the file is ever looked up,
   and the file itself never leaves the machine. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PTCreationPdf = api;
})(this, function () {
  'use strict';

  const ARXIV_STAMP = /arXiv\s*:\s*(\d{4}\.\d{4,5})(v\d+)?/i;
  const ARXIV_NAME = /^(\d{4}\.\d{4,5})(v\d+)?$/;
  const DOI = /\b(10\.\d{4,9}\/[^\s"'<>]+)/;
  const ARXIV_DOI = /^10\.48550\/arxiv\.(\d{4}\.\d{4,5})(v\d+)?$/i;
  const IDENTIFIER = [
    /^(?:arxiv:)?\d{4}\.\d{4,5}(?:v\d+)?$/i,
    /^https?:\/\/(?:www\.)?arxiv\.org\/(?:abs|pdf)\/\d{4}\.\d{4,5}(?:v\d+)?(?:\.pdf)?\/?$/i,
    /^(?:doi:\s*)?10\.\d{4,9}\/\S+$/i,
    /^https?:\/\/(?:dx\.)?doi\.org\/10\.\d{4,9}\/\S+$/i,
    /^(?:https?:\/\/openalex\.org\/)?W\d+$/i,
  ];

  // The same shapes the server accepts: anything else typed in the seed box is a paper name.
  function looksLikeIdentifier(text) {
    const value = String(text || '').trim();
    return IDENTIFIER.some((re) => re.test(value));
  }

  function cleanDoi(raw) {
    return raw.replace(/[.,;:)\]}>]+$/, '');
  }

  function findArxivId(text) {
    const match = ARXIV_STAMP.exec(text || '');
    return match ? match[1] : null;
  }

  // First DOI in the text. A DOI that is really an arXiv one is reported as the arXiv id.
  function findDoi(text) {
    const match = DOI.exec(text || '');
    if (!match) return {doi: null, arxiv: null};
    const doi = cleanDoi(match[1]);
    const arxiv = ARXIV_DOI.exec(doi);
    return arxiv ? {doi: null, arxiv: arxiv[1]} : {doi, arxiv: null};
  }

  function arxivFromFilename(name) {
    const base = String(name || '').replace(/\.pdf$/i, '').trim();
    const match = ARXIV_NAME.exec(base);
    return match ? match[1] : null;
  }

  // pdf.js text items of one page -> the title: the biggest type in the upper part of the page,
  // consecutive lines of that size joined. items: [{str, height, y}] with y measured from the top.
  function titleFromItems(items, pageHeight) {
    const top = pageHeight ? pageHeight * 0.6 : Infinity;
    const lines = [];
    for (const item of items || []) {
      const text = String(item.str || '').replace(/\s+/g, ' ').trim();
      if (!text || !(item.height > 0) || item.y > top) continue;
      const last = lines[lines.length - 1];
      if (last && Math.abs(last.y - item.y) < Math.max(2, last.height * 0.3)) {
        last.text += ' ' + text;           // same baseline: one line
        last.height = Math.max(last.height, item.height);
      } else {
        lines.push({text, height: item.height, y: item.y});
      }
    }
    if (!lines.length) return null;
    const biggest = Math.max(...lines.map((l) => l.height));
    const first = lines.findIndex((l) => l.height >= biggest * 0.92);
    let end = first;
    while (end + 1 < lines.length && lines[end + 1].height >= biggest * 0.92
           && lines[end + 1].y - lines[end].y < biggest * 2.2) end += 1;
    const title = lines.slice(first, end + 1).map((l) => l.text).join(' ').replace(/\s+/g, ' ').trim();
    return title.length >= 8 && title.length <= 250 ? title : null;
  }

  const GENERIC_TITLE = /^(untitled|microsoft word|document|paper|slides?|main|manuscript|\S+\.(tex|dvi|docx?|pdf))\b/i;

  function metadataTitle(info) {
    const title = String((info && info.Title) || '').replace(/\s+/g, ' ').trim();
    return title.length >= 8 && title.length <= 250 && !GENERIC_TITLE.test(title) ? title : null;
  }

  // What to look up, strongest first: ids found in the file (or its name), then title guesses.
  function identify({pageTexts, items, pageHeight, info, filename}) {
    const text = (pageTexts || []).join('\n');
    let arxiv = findArxivId(text) || arxivFromFilename(filename);
    let {doi, arxiv: arxivFromDoi} = findDoi(text);
    arxiv = arxiv || arxivFromDoi;
    const titles = [];
    for (const title of [metadataTitle(info), titleFromItems(items, pageHeight)]) {
      if (title && !titles.some((t) => similarity(t, title) > 0.9)) titles.push(title);
    }
    return {arxiv, doi, titles};
  }

  function words(text) {
    return String(text || '').toLowerCase().match(/[a-z0-9一-鿿]+/g) || [];
  }

  // Word-set overlap, 0..1: how sure we can be that a search hit is the title we looked for.
  function similarity(a, b) {
    const left = new Set(words(a));
    const right = new Set(words(b));
    if (!left.size || !right.size) return 0;
    let shared = 0;
    for (const word of left) if (right.has(word)) shared += 1;
    return shared / (left.size + right.size - shared);
  }

  return {looksLikeIdentifier, findArxivId, findDoi, arxivFromFilename, titleFromItems, metadataTitle,
    identify, similarity};
});
