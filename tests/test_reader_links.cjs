'use strict';
// The PDF reader draws the paper's own links (owner 2026-10-28: 渲染后没有了引用跳转): citations and section references
// jump inside the paper with a way back, web addresses open outside, anything else is not a link.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const L = require('../app/static/reader-links.js');
const N = require('../app/static/reader-notes.js');
const source = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');

const flip = (r) => [r[0], 800 - r[1], r[2], 800 - r[3]];   // a viewport whose y axis points down, like pdf.js

test('internal and web links become boxes in page pixels; other annotations do not', () => {
  const boxes = L.linkBoxes([
    {subtype: 'Link', rect: [100, 700, 120, 712], dest: 'cite.vaswani2017'},
    {subtype: 'Link', rect: [50, 50, 200, 62], url: 'https://arxiv.org/abs/1706.03762'},
    {subtype: 'Link', rect: [10, 10, 30, 20], dest: [{num: 5, gen: 0}, {name: 'XYZ'}, 72, 500, null]},
    {subtype: 'Link', rect: [0, 0, 10, 10], url: 'javascript:alert(1)'},
    {subtype: 'Link', rect: [0, 0, 10, 10], unsafeUrl: 'file:///etc/passwd'},
    {subtype: 'Link', rect: [0, 0, 0.2, 10], dest: 'tiny'},
    {subtype: 'Text', rect: [0, 0, 10, 10], dest: 'x'},
  ], flip);
  assert.equal(boxes.length, 3);
  assert.deepEqual(boxes[0], {left: 100, top: 88, width: 20, height: 12, dest: 'cite.vaswani2017'});
  assert.equal(boxes[1].url, 'https://arxiv.org/abs/1706.03762');
  assert.ok(Array.isArray(boxes[2].dest));
});

test('only http(s) and mailto addresses are opened', () => {
  assert.equal(L.safeUrl('https://a.b/c'), 'https://a.b/c');
  assert.equal(L.safeUrl('mailto:a@b.c'), 'mailto:a@b.c');
  for (const bad of ['javascript:x', 'file:///x', 'data:text/html,x', '', null]) assert.equal(L.safeUrl(bad), null);
});

test('a named destination resolves to its page and the place on it', async () => {
  const ref = {num: 9, gen: 0};
  const doc = {
    getDestination: async (name) => (name === 'cite.x' ? [ref, {name: 'XYZ'}, 72, 600, null] : null),
    getPageIndex: async (r) => (r === ref ? 11 : 0),
    getPage: async () => ({view: [0, 0, 612, 792]}),
  };
  const to = await L.resolve(doc, 'cite.x', N.destTop);
  assert.equal(to.page, 12);
  assert.ok(Math.abs(to.top - (792 - 600) / 792) < 1e-4);
  assert.equal(await L.resolve(doc, 'missing', N.destTop), null);
  assert.equal(await L.resolve({getDestination: async () => { throw new Error('bad'); }}, 'x', N.destTop), null);
});

test('the reader draws links on every rendered page and offers a way back after a jump', () => {
  assert.match(source, /src="\/reader-links\.js"/);
  assert.match(source, /drawLinks\(pageDiv, await page\.getAnnotations\(\{ intent: 'display' \}\), vp\)/);
  assert.match(source, /id="linkBack"[^>]*hidden/);
  assert.match(source, /#linkBack\[hidden\] \{ display:none; \}/);
  // owner 2026-10-28: the link's letters are blue (a "lighten" block over dark letters), not a selection-like wash
  assert.match(source, /\.linkLayer a \{[^}]*background:#2b62c9; mix-blend-mode:lighten;/);
  assert.match(source, /b\.height > 2 \* b\.width && b\.height > 60\) a\.className = 'plain'/);   // the button style's display must not show it
  const follow = source.slice(source.indexOf('async function followLink'), source.indexOf('function hideLinkBack'));
  assert.match(follow, /linkBack = \{ page: from\.page/);
  assert.match(follow, /goToPlace\(to\.page, to\.top\)/);
  assert.match(source, /R\.path = null;\n  hideLinkBack\(\);/);   // a new paper starts without a way back
  const links = source.slice(source.indexOf('function drawLinks'), source.indexOf('let linkBack'));
  assert.match(links, /a\.target = '_blank'; a\.rel = 'noreferrer'/);
});
