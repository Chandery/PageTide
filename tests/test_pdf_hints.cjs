'use strict';
// Reading the first pages of a PDF for an identifier or a title: the shared reader behind project creation and
// library import. A fake pdf.js stands in for the library, so this checks what is read and what is passed on.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load() {
  const context = vm.createContext({ module: { exports: {} }, setTimeout, clearTimeout, Promise, Uint8Array });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/pdf-hints.js'), 'utf8'), context);
  return context.module.exports;
}
const H = load();
const plain = (value) => JSON.parse(JSON.stringify(value));

function fakeLib({ pages = 3, failOn = null, info = { Title: 'A real looking title' } } = {}) {
  const log = { read: [], destroyed: 0, data: null };
  const doc = {
    numPages: pages,
    async getPage(n) {
      log.read.push(n);
      if (failOn === n) throw new Error('bad page');
      return {
        getViewport: () => ({ height: 800 }),
        async getTextContent() {
          return { items: [{ str: `page ${n} text`, transform: [1, 0, 0, 12, 0, 700], height: 12 },
            { str: '  ', transform: [1, 0, 0, 12, 0, 650], height: 12 }] };
        },
      };
    },
    async getMetadata() { return { info }; },
    destroy() { log.destroyed += 1; },
  };
  return { log, lib: { getDocument(options) { log.data = options; return { promise: Promise.resolve(doc) }; } } };
}
const file = (name = 'x.pdf') => ({ name, async arrayBuffer() { return new ArrayBuffer(8); } });

test('only the first two pages are read, and the first page supplies the title candidates', async () => {
  const { lib, log } = fakeLib();
  let received = null;
  const reader = H.create(async () => lib, (input) => { received = input; return { arxiv: null, doi: null, titles: [] }; });
  await reader.extractHints(file('paper.pdf'));
  assert.deepEqual(plain(log.read), [1, 2]);
  assert.deepEqual(plain(received.pageTexts), ['page 1 text   ', 'page 2 text   ']);
  assert.equal(received.pageHeight, 800);
  assert.deepEqual(plain(received.items), [{ str: 'page 1 text', height: 12, y: 100 }]);   // blank runs dropped, y from the top
  assert.equal(received.filename, 'paper.pdf');
  assert.equal(received.info.Title, 'A real looking title');
});

test('the document is released whether reading worked or not', async () => {
  const ok = fakeLib();
  await H.create(async () => ok.lib, () => ({})).extractHints(file());
  assert.equal(ok.log.destroyed, 1);
  const bad = fakeLib({ failOn: 2 });
  await assert.rejects(H.create(async () => bad.lib, () => ({})).extractHints(file()), /bad page/);
  assert.equal(bad.log.destroyed, 1);
});

test('a one-page PDF is read once and metadata that cannot be read is optional', async () => {
  const { lib, log } = fakeLib({ pages: 1 });
  lib.getDocument = ((original) => (options) => { const out = original(options); out.promise = out.promise.then((doc) => { doc.getMetadata = async () => { throw new Error('no metadata'); }; return doc; }); return out; })(lib.getDocument);
  let received = null;
  await H.create(async () => lib, (input) => { received = input; return {}; }).extractHints(file());
  assert.deepEqual(plain(log.read), [1]);
  assert.equal(received.info, null);
});

test('the PDF bytes are given to pdf.js with the bundled fonts', async () => {
  const { lib, log } = fakeLib();
  await H.create(async () => lib, () => ({})).extractHints(file());
  assert.ok(log.data.data instanceof Uint8Array);
  assert.equal(log.data.standardFontDataUrl, '/vendor/pdfjs/standard_fonts/');
});

test('a read that takes too long is abandoned with a plain message', async () => {
  await assert.rejects(H.withTimeout(new Promise(() => {}), 20), /读取超时/);
  assert.equal(await H.withTimeout(Promise.resolve(7), 1000), 7);
});
