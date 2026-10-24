'use strict';
// The PDF reader paints its own selection (one box per line, no overlaps) instead of the browser's per-span highlight,
// which stacked into dark, misaligned stripes in WebKit. These tests run the real merge function.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const S = require('../app/static/reader-selection.js');
const r = (left, top, right, bottom) => ({left, top, right, bottom});

test('the pieces of one line become one box', () => {
  const out = S.mergeLineRects([r(10, 100, 60, 112), r(60, 101, 140, 112), r(141, 100, 200, 113)]);
  assert.equal(out.length, 1);
  assert.deepEqual(out[0], r(10, 100, 200, 113));
});

test('neighbouring lines never overlap, so nothing darkens where they meet', () => {
  const out = S.mergeLineRects([r(10, 100, 200, 116), r(10, 110, 200, 126), r(10, 120, 120, 136)]);
  assert.equal(out.length, 3);
  for (let i = 1; i < out.length; i++) assert.ok(out[i].top >= out[i - 1].bottom, JSON.stringify(out));
  assert.equal(out[0].top, 100);
  assert.equal(out[2].bottom, 136);
});

test('two columns on the same height stay two boxes', () => {
  const out = S.mergeLineRects([r(10, 100, 280, 112), r(320, 100, 590, 112)]);
  assert.equal(out.length, 2);
});

test('slivers and empty pieces are dropped', () => {
  assert.deepEqual(S.mergeLineRects([r(10, 100, 10.2, 112), r(10, 100, 50, 100.1)]), []);
  assert.deepEqual(S.mergeLineRects([]), []);
});

test('the reader hides the native per-span highlight and loads the painter', () => {
  const html = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');
  assert.match(html, /\.reader \.textLayer ::selection \{ background:transparent; \}/);
  assert.match(html, /<script src="\/reader-selection\.js"><\/script>/);
  assert.match(html, /PTReaderSelection\?\.install\(/);
});
