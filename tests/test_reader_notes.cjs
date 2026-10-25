'use strict';
// Reader annotations are stored as page fractions and found again under a click; the outline resolves to pages.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const N = require('../app/static/reader-notes.js');

test('line boxes become page fractions, independent of zoom', () => {
  const at100 = N.toFractions([{p: 1, left: 60, top: 100, right: 300, bottom: 112}], {1: {w: 600, h: 800}});
  const at200 = N.toFractions([{p: 1, left: 120, top: 200, right: 600, bottom: 224}], {1: {w: 1200, h: 1600}});
  assert.deepEqual(at100, at200);
  assert.deepEqual(at100, [{p: 1, x0: 0.1, y0: 0.125, x1: 0.5, y1: 0.14}]);
});

test('boxes outside the page are clamped and empty or unknown-page boxes dropped', () => {
  const out = N.toFractions([{p: 1, left: -10, top: 790, right: 620, bottom: 820}, {p: 1, left: 50, top: 10, right: 50, bottom: 20},
                             {p: 9, left: 0, top: 0, right: 10, bottom: 10}], {1: {w: 600, h: 800}});
  assert.deepEqual(out, [{p: 1, x0: 0, y0: 0.9875, x1: 1, y1: 1}]);
});

test('a click finds the highlight on that page, the newest where two overlap', () => {
  const older = {id: 'a', rects: [{p: 2, x0: 0.1, y0: 0.1, x1: 0.5, y1: 0.12}]};
  const newer = {id: 'b', rects: [{p: 2, x0: 0.3, y0: 0.1, x1: 0.8, y1: 0.12}]};
  assert.equal(N.hit([older, newer], 2, 0.2, 0.11).id, 'a');
  assert.equal(N.hit([older, newer], 2, 0.4, 0.11).id, 'b');
  assert.equal(N.hit([older, newer], 1, 0.4, 0.11), null);
  assert.equal(N.hit([older, newer], 2, 0.4, 0.3), null);
});

test('the notes list follows the reading order, not the order they were made', () => {
  const at = (id, p, y0, x0) => ({id, page: p, rects: [{p, x0, y0, x1: x0 + 0.1, y1: y0 + 0.02}]});
  const out = N.readingOrder([at('c', 3, 0.1, 0.1), at('b', 1, 0.5, 0.1), at('a', 1, 0.2, 0.6), at('a2', 1, 0.2, 0.1)]);
  assert.deepEqual(out.map((a) => a.id), ['a2', 'a', 'b', 'c']);
});

test('destinations point at the right height from the top of the page', () => {
  const view = [0, 0, 612, 792];
  assert.equal(N.destTop([{}, {name: 'XYZ'}, 72, 792, null], view), 0);
  assert.equal(N.destTop([{}, {name: 'FitH'}, 396], view), 0.5);
  assert.equal(N.destTop([{}, {name: 'Fit'}], view), null);
  assert.equal(N.destTop([{}, {name: 'XYZ'}, 72, null, null], view), null);
});

test('an outline resolves named and explicit destinations, keeps nesting, survives a broken one', async () => {
  const refs = {r1: 0, r3: 2};
  const doc = {
    getDestination: async (name) => (name === 'sec2' ? [{ref: 'r3'}, {name: 'FitH'}, 396] : null),
    getPageIndex: async (ref) => { if (!(ref.ref in refs)) throw new Error('bad ref'); return refs[ref.ref]; },
    getPage: async () => ({view: [0, 0, 612, 792]}),
  };
  const out = await N.resolveOutline(doc, [
    {title: ' Introduction ', dest: [{ref: 'r1'}, {name: 'XYZ'}, 0, 792, 0], items: [{title: 'Background', dest: 'sec2', items: []}]},
    {title: 'Broken', dest: [{ref: 'nope'}, {name: 'Fit'}], items: []},
    {title: 'Missing', dest: 'nothing', items: []},
  ]);
  assert.deepEqual(out, [
    {title: 'Introduction', page: 1, top: 0, children: [{title: 'Background', page: 3, top: 0.5, children: []}]},
    {title: 'Broken', page: null, top: null, children: []},
    {title: 'Missing', page: null, top: null, children: []},
  ]);
});

test('the reader wires highlights, notes and the outline tab', () => {
  const html = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');
  for (const needle of ['src="/reader-notes.js"', 'data-sel="highlight"', 'data-sel="note"', 'id="notePop"', 'id="readerOutline"',
                        'id="readerThumbs"', 'id="readerNotes"', "'/api/annotations'", 'drawNotes(pageDiv, n)', 'buildOutline(doc, current)'])
    assert.ok(html.includes(needle), needle);
});
