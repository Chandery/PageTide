'use strict';
// pdf.js lays its invisible text over the page in a generic font and stretches each line evenly to the line's width.
// On justified lines in papers set in Times (Nimbus Roman) that drifts by up to a word, so a selection or a double-click
// picks the wrong letters ("learning" became "t learning"). The reader refits each line in the PDF's own font and puts
// the justification into the spaces. These tests run the real fit decision.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const F = require('../app/static/reader-textfit.js');

test('a justified line keeps its letters at their real width and stretches only the spaces', () => {
  const fit = F.fitLine({str: 'a powerful learning framework', target: 140, natural: 128, fallback: 150, fontSize: 9});
  assert.equal(fit.mode, 'words');
  assert.ok(Math.abs(fit.wordSpacing - 4) < 1e-9, JSON.stringify(fit));   // 12 px over 3 spaces
});

test('a line without spaces is scaled as a whole', () => {
  const fit = F.fitLine({str: 'learning', target: 41, natural: 40, fallback: 48, fontSize: 9});
  assert.equal(fit.mode, 'scale');
  assert.ok(Math.abs(fit.scaleX - 41 / 40) < 1e-9);
});

test('a font that draws none of the letters is not used', () => {
  assert.equal(F.fitLine({str: 'abc def', target: 30, natural: 33, fallback: 33, fontSize: 9}), null);
});

test('implausible fits keep the pdf.js layout', () => {
  assert.equal(F.fitLine({str: 'a b', target: 300, natural: 20, fallback: 25, fontSize: 9}), null);    // 140 px per space
  assert.equal(F.fitLine({str: 'abcdef', target: 60, natural: 30, fallback: 36, fontSize: 9}), null);  // 2x squeeze
  assert.equal(F.fitLine({str: '', target: 0, natural: 0, fallback: 0, fontSize: 9}), null);
});

test('the baseline stays where pdf.js put it when the font changes', () => {
  // line-height 1: baseline from the top = (1 + ascent - descent) / 2 em
  const old = {ascent: 0.9, descent: 0.2}, next = {ascent: 0.7, descent: 0.3};
  assert.ok(Math.abs(F.baselineShift(old, next, 10) - 1.5) < 1e-9);   // (0.85 - 0.70) * 10
});

test('the reader refits the text layer after pdf.js builds it', () => {
  const html = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');
  assert.match(html, /<script src="\/reader-textfit\.js"><\/script>/);
  assert.match(html, /PDHReaderTextFit\?\.apply\(textLayer\.textDivs, /);
});
