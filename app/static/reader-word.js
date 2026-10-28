/* 划词翻译 for a single word or a short term: the selection is looked up like a dictionary entry (pronunciation, parts of
   speech, meanings, and what it means in this sentence), so the sentence it was selected from goes along with it.
   Longer selections are translated as before. The server applies the same rule (service.WORD_LOOKUP). */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTReaderWord = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  const WORD = /^[A-Za-z][A-Za-z'’-]*(?: [A-Za-z][A-Za-z'’-]*){0,2}$/;
  const CONTEXT_MAX = 400;

  /* One to three English words, at most 40 characters. */
  function isWord(text) {
    const s = String(text || '').replace(/\s+/g, ' ').trim();
    return s.length <= 40 && WORD.test(s);
  }

  /* The sentence around position `at` of `text` (whitespace folded), at most CONTEXT_MAX characters, centred on the
     selection when the sentence is longer. A line-end hyphen ("lear- ning") is joined. */
  function sentenceAround(text, at, selected = '') {
    const raw = String(text || '');
    if (!raw.trim()) return '';
    if (!(at >= 0 && at <= raw.length)) {
      const found = selected ? raw.indexOf(selected) : -1;
      if (found < 0) return '';
      at = found;
    }
    // Fold whitespace while keeping `at` on the same letter.
    let s = '', pos = 0;
    for (let i = 0; i < raw.length; i++) {
      if (i === at) pos = s.length;
      const c = raw[i];
      if (/\s/.test(c)) { if (s && !s.endsWith(' ')) s += ' '; }
      else s += c;
    }
    if (at >= raw.length) pos = s.length;
    const joined = s.replace(/([a-z])- ([a-z])/g, (m, a, b, off) => { if (off + 1 < pos) pos -= 2; return a + b; });
    s = joined;
    const end = /[.!?。！？](?=\s|$)/g;
    let start = 0, stop = s.length, m;
    while ((m = end.exec(s))) {
      const after = m.index + 1;
      if (after <= pos) start = after;
      else { stop = after; break; }
    }
    if (stop - start > CONTEXT_MAX) {
      const half = Math.floor(CONTEXT_MAX / 2);
      start = Math.max(start, pos - half);
      stop = Math.min(stop, start + CONTEXT_MAX);
    }
    return s.slice(start, stop).trim();
  }

  /* The text around a DOM range: the PDF page's text layer (line breaks as spaces), else the nearest block. Returns
     {text, at} with `at` the offset of the range start in `text`, or -1 when it could not be placed. */
  function textAround(range) {
    const node = range && range.startContainer;
    const el = node && (node.nodeType === 1 ? node : node.parentElement);
    const scope = el && (el.closest('.textLayer') || el.closest('p, li, blockquote, td, .abstract-text, div'));
    if (!scope) return {text: '', at: -1};
    const doc = scope.ownerDocument;
    const walker = doc.createTreeWalker(scope, 1 | 4 /* SHOW_ELEMENT | SHOW_TEXT */);
    let text = '', at = -1;
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.nodeType === 1) {
        if (n.tagName === 'BR') text += ' ';
        else if (n === node && at < 0) at = text.length;
        continue;
      }
      if (n === node) at = text.length + range.startOffset;
      text += n.data;
    }
    return {text, at};
  }

  /* The sentence a selection was made in, for a word lookup; '' for anything that is not one. */
  function contextFor(range, selected) {
    if (!isWord(selected)) return '';
    const {text, at} = textAround(range);
    return sentenceAround(text, at, selected);
  }

  return {isWord, sentenceAround, textAround, contextFor, CONTEXT_MAX};
});
