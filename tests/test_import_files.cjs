'use strict';
// What the import page does with the files a person picked or dropped: pure functions, no DOM, no network.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load() {
  const context = vm.createContext({ module: { exports: {} } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/import-files.js'), 'utf8'), context);
  return context.module.exports;
}
const F = load();
const MB = 1024 * 1024;
const file = (relative, size = 1000, extra = {}) => ({ name: relative.split('/').pop(), size, type: '', webkitRelativePath: relative, ...extra });
// Values built inside the vm sandbox have that realm's Array/Object prototypes: compare plain copies.
const plain = (value) => JSON.parse(JSON.stringify(value));
const paths = (list) => plain(list.map((item) => item.path));

test('only PDFs are uploaded; the folder structure comes from the relative path', () => {
  const out = F.classify([file('lib/a.pdf'), file('lib/deep/b.PDF'), file('lib/notes.docx'), file('lib/c.txt')]);
  assert.deepEqual(paths(out.pdfs), ['lib/a.pdf', 'lib/deep/b.PDF']);
  assert.equal(out.ignored, 2);
  assert.deepEqual(plain(out.skipped), []);
});

test('a PDF is recognised by its type even without the extension', () => {
  assert.deepEqual(paths(F.classify([file('lib/paper', 10, { type: 'application/pdf' })]).pdfs), ['lib/paper']);
});

test('hidden and system files are never uploaded, and are not reported one by one', () => {
  const out = F.classify([file('lib/.hidden.pdf'), file('lib/.git/x.pdf'), file('lib/__MACOSX/a.pdf'), file('lib/._a.pdf'),
    file('lib/.DS_Store'), file('lib/ok.pdf')]);
  assert.deepEqual(paths(out.pdfs), ['lib/ok.pdf']);
  assert.equal(out.ignored, 5);
  assert.deepEqual(plain(out.skipped), []);
});

test('a PDF that is too large or empty is skipped with its reason, never silently', () => {
  const out = F.classify([file('lib/big.pdf', 61 * MB), file('lib/zero.pdf', 0), file('lib/edge.pdf', 60 * MB), file('lib/ok.pdf')]);
  assert.deepEqual(paths(out.pdfs), ['lib/edge.pdf', 'lib/ok.pdf']);
  assert.deepEqual(plain(out.skipped), [{ path: 'lib/big.pdf', reason: 'too_large' }, { path: 'lib/zero.pdf', reason: 'empty' }]);
});

test('a path from a dropped folder (no webkitRelativePath) uses the walked path, then the plain name', () => {
  const out = F.classify([{ name: 'a.pdf', size: 5, type: '', _path: 'dropped/x/a.pdf' }, { name: 'b.pdf', size: 5, type: '' }]);
  assert.deepEqual(paths(out.pdfs), ['dropped/x/a.pdf', 'b.pdf']);
});

test('the export files of a reference manager are found at the top of the folder only', () => {
  const out = F.classify([file('z/My Library.bib'), file('z/export.ris'), file('z/items.json'), file('z/files/1/a.pdf'),
    file('z/files/deep/other.bib'), file('z/files/1/meta.json')]);
  assert.deepEqual(plain(out.sidecars.map((s) => [s.path, s.format])),
    [['z/My Library.bib', 'bibtex'], ['z/export.ris', 'ris'], ['z/items.json', 'csljson']]);
  assert.deepEqual(paths(out.pdfs), ['z/files/1/a.pdf']);
});

test('the root folder name is the first segment all files share', () => {
  assert.equal(F.rootOf(['lib/a.pdf', 'lib/x/b.pdf']), 'lib');
  assert.equal(F.rootOf(['a.pdf', 'b.pdf']), '');
  assert.equal(F.rootOf(['lib/a.pdf', 'other/b.pdf']), '');
  assert.equal(F.rootOf(['lib/a.pdf']), 'lib');
  assert.equal(F.rootOf([]), '');
});

test('what the batch already holds is not sent again, but a changed file is', () => {
  const held = F.resumeSet([['lib/a.pdf', 1000, 5], ['lib/b.pdf', 2000, 9]]);
  assert.equal(F.alreadyUploaded(held, { path: 'lib/a.pdf', file: { size: 1000, lastModified: 5 } }), true);
  assert.equal(F.alreadyUploaded(held, { path: 'lib/a.pdf', file: { size: 1001, lastModified: 5 } }), false);
  assert.equal(F.alreadyUploaded(held, { path: 'lib/a.pdf', file: { size: 1000, lastModified: 6 } }), false);
  assert.equal(F.alreadyUploaded(held, { path: 'lib/new.pdf', file: { size: 1, lastModified: 1 } }), false);
});

test('hints are sent percent-encoded and always fit the header limit', () => {
  const small = F.encodeHints({ doi: '10.1/x', titles: ['A title'] });
  assert.deepEqual(plain(JSON.parse(decodeURIComponent(small))), { doi: '10.1/x', titles: ['A title'] });
  const huge = F.encodeHints({ doi: '10.1/x', arxiv: '2401.00001', titles: ['é'.repeat(300), 'é'.repeat(300), 'é'.repeat(300)] });
  assert.ok(huge.length <= 4096);
  const kept = JSON.parse(decodeURIComponent(huge));
  assert.equal(kept.doi, '10.1/x');
  assert.equal(F.encodeHints(null), '');
  assert.equal(F.encodeHints({}), '');
});

test('picking the Zotero storage folder itself is noticed, a normal folder is not', () => {
  const storage = ['storage/ABCD1234/a.pdf', 'storage/EFGH5678/b.pdf', 'storage/IJKL9012/c.pdf'];
  assert.equal(F.looksLikeZoteroStorage(storage), true);
  assert.equal(F.looksLikeZoteroStorage(['lib/RL/a.pdf', 'lib/Survey/b.pdf', 'lib/c.pdf']), false);
  assert.equal(F.looksLikeZoteroStorage(['z/files/1/a.pdf', 'z/files/2/b.pdf']), false);   // an export is fine
  assert.equal(F.looksLikeZoteroStorage([]), false);
});

// A dropped folder is a tree of entries; readEntries returns at most ~100 at a time until it returns [].
function dirEntry(name, children) {
  return { isFile: false, isDirectory: true, name, createReader() {
    let given = 0;
    return { readEntries(done) { const batch = children.slice(given, given + 3); given += 3; done(batch); } };
  } };
}
const fileEntry = (name, size = 10) => ({ isFile: true, isDirectory: false, name, file(done) { done({ name, size, type: '' }); } });

test('a dropped folder is walked completely, however many entries each read returns', async () => {
  const tree = dirEntry('lib', [fileEntry('a.pdf'), fileEntry('b.pdf'), fileEntry('c.pdf'), fileEntry('d.pdf'),
    dirEntry('sub', [fileEntry('e.pdf'), fileEntry('f.pdf'), fileEntry('g.pdf'), fileEntry('h.pdf')])]);
  const found = await F.walkEntries([tree]);
  assert.deepEqual(plain(found.map((f) => f._path).sort()), ['lib/a.pdf', 'lib/b.pdf', 'lib/c.pdf', 'lib/d.pdf',
    'lib/sub/e.pdf', 'lib/sub/f.pdf', 'lib/sub/g.pdf', 'lib/sub/h.pdf']);
});

test('dropped plain files are kept, and a folder that cannot be read does not stop the others', async () => {
  const broken = { isFile: false, isDirectory: true, name: 'locked', createReader() { return { readEntries(done, fail) { fail(new Error('denied')); } }; } };
  const found = await F.walkEntries([fileEntry('single.pdf'), broken, dirEntry('ok', [fileEntry('x.pdf')])]);
  assert.deepEqual(plain(found.map((f) => f._path).sort()), ['ok/x.pdf', 'single.pdf']);
});

test('a drop of a huge folder is bounded', async () => {
  const many = dirEntry('big', Array.from({ length: 50 }, (_, i) => fileEntry(`f${i}.pdf`)));
  const found = await F.walkEntries([many], { limit: 10 });
  assert.equal(found.length, 10);
});

test('batches of pending work are sized for a small machine', () => {
  assert.equal(F.CONCURRENCY, 2);
  assert.equal(F.MAX_FILES, 2000);
  assert.equal(F.MAX_BYTES, 60 * MB);
});
