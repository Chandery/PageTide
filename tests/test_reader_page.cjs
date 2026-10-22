'use strict';
// "附本页图" sent page 5 while the reader showed page 4: the current page came from the observer that pre-renders
// pages 800 px beyond the view, so the next page counted as current as soon as it entered that margin.
// The current page is now the page the reader actually shows. These tests run the real choice.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const P = require('../app/static/reader-page.js');
const page = (n, top, bottom) => ({n, top, bottom});

test('the page across the middle of the view is the current page, not the next one being pre-rendered', () => {
  const pages = [page(3, -2200, -1100), page(4, -1080, 700), page(5, 720, 2500)];
  assert.equal(P.inView({top: 0, bottom: 800}, pages), 4);
});

test('between two pages, the one showing more wins', () => {
  const pages = [page(4, -1500, 300), page(5, 322, 2100)];
  assert.equal(P.inView({top: 0, bottom: 800}, pages), 5);
});

test('nothing on screen gives no page', () => {
  assert.equal(P.inView({top: 0, bottom: 800}, [page(1, 900, 1800)]), null);
  assert.equal(P.inView({top: 0, bottom: 800}, []), null);
});

test('the reader takes the current page from the view, not from the pre-render observer', () => {
  const html = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');
  assert.match(html, /<script src="\/reader-page\.js"><\/script>/);
  assert.doesNotMatch(html, /nextJobs\.size <= R\.pages\.length\) markCurrent/);
  assert.match(html, /const here = quotedPage \|\| pageInView\(\) \|\| R\.current \|\| 1;/);
});
