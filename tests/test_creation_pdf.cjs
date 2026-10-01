'use strict';
// Recognising a dropped PDF and a pasted seed: pure functions, no DOM, no network.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load() {
  const context = vm.createContext({ module: { exports: {} } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/creation-pdf.js'), 'utf8'), context);
  return context.module.exports;
}
const P = load();

test('a seed is an identifier only in the shapes the server accepts; anything else is a paper name', () => {
  for (const text of ['2401.00001', 'arXiv:2401.00001v2', 'https://arxiv.org/abs/2401.00001', 'https://arxiv.org/pdf/2401.00001.pdf',
    '10.1145/3292500.3330701', 'doi: 10.1145/3292500.3330701', 'https://doi.org/10.1145/3292500.3330701', 'W2741809807',
    'https://openalex.org/W2741809807']) assert.equal(P.looksLikeIdentifier(text), true, text);
  for (const text of ['Attention is all you need', 'world models 2024', '10.1/x', '', '  ']) {
    assert.equal(P.looksLikeIdentifier(text), false, text);
  }
});

test('the arXiv stamp, a DOI, or an arXiv file name identify the paper', () => {
  assert.equal(P.findArxivId('foo arXiv:2401.12345v2 [cs.LG] 3 Jan 2024'), '2401.12345');
  assert.equal(P.findArxivId('no stamp here'), null);
  assert.deepEqual({ ...P.findDoi('see https://doi.org/10.1145/3292500.3330701.') }, { doi: '10.1145/3292500.3330701', arxiv: null });
  assert.deepEqual({ ...P.findDoi('doi 10.48550/arXiv.2401.12345') }, { doi: null, arxiv: '2401.12345' });
  assert.equal(P.arxivFromFilename('2401.12345v3.pdf'), '2401.12345');
  assert.equal(P.arxivFromFilename('my paper.pdf'), null);
});

test('the title is the biggest type in the upper page, joined across lines, ignoring small print', () => {
  const items = [
    { str: 'Published as a conference paper at ICLR 2024', height: 8, y: 30 },
    { str: 'Latent World Models', height: 17, y: 90 },
    { str: 'for Planning', height: 17, y: 112 },
    { str: 'Ada Lovelace', height: 11, y: 150 },
    { str: 'Abstract', height: 12, y: 220 },
    { str: 'Footer big text', height: 18, y: 700 },
  ];
  assert.equal(P.titleFromItems(items, 792), 'Latent World Models for Planning');
  assert.equal(P.titleFromItems([], 792), null);
  assert.equal(P.titleFromItems([{ str: 'Hi', height: 20, y: 10 }], 792), null);  // too short to be a title
});

test('file metadata titles are used unless they are generic', () => {
  assert.equal(P.metadataTitle({ Title: 'Latent World Models for Planning' }), 'Latent World Models for Planning');
  for (const bad of ['Microsoft Word - draft.docx', 'untitled', 'main.tex', '', undefined]) {
    assert.equal(P.metadataTitle({ Title: bad }), null, String(bad));
  }
});

test('identify combines ids and de-duplicates the title guesses', () => {
  const found = P.identify({
    pageTexts: ['Latent World Models arXiv:2401.12345v1', 'page two'],
    items: [{ str: 'Latent World Models for Planning', height: 17, y: 90 }],
    pageHeight: 792, info: { Title: 'Latent World Models for Planning' }, filename: 'download.pdf',
  });
  assert.equal(found.arxiv, '2401.12345');
  assert.equal(found.doi, null);
  assert.deepEqual([...found.titles], ['Latent World Models for Planning']);
  const named = P.identify({ pageTexts: [''], items: [], filename: '2312.00001.pdf' });
  assert.equal(named.arxiv, '2312.00001');
  assert.deepEqual([...named.titles], []);
});

test('similarity tells the intended paper from a near miss', () => {
  assert.ok(P.similarity('Latent World Models for Planning', 'latent world models for planning!') > 0.95);
  assert.ok(P.similarity('Latent World Models for Planning', 'A Survey of Reinforcement Learning') < 0.2);
  assert.equal(P.similarity('', 'x'), 0);
});
