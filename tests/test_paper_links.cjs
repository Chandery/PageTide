const test = require('node:test');
const assert = require('node:assert/strict');
const L = require('../app/static/paper-links.js');

const q = (url) => decodeURIComponent(new URL(url).searchParams.get('q'));

test('the link is the Connected Papers search page, filled with the arXiv address when there is one', () => {
  const url = L.connectedPapersURL({ arxiv_id: '2301.04104', doi: '10.1000/x', title: 'A long enough title' });
  assert.equal(new URL(url).origin + new URL(url).pathname, 'https://www.connectedpapers.com/search');
  assert.equal(q(url), 'https://arxiv.org/abs/2301.04104');
});

test('a versioned, prefixed or old-style arXiv id works', () => {
  assert.equal(q(L.connectedPapersURL({ arxiv_id: 'arXiv:2301.04104v2' })), 'https://arxiv.org/abs/2301.04104v2');
  assert.equal(q(L.connectedPapersURL({ arxiv_id: 'hep-th/9901001' })), 'https://arxiv.org/abs/hep-th/9901001');
});

test('without an arXiv id the DOI is used, in any of its usual spellings', () => {
  for (const doi of ['10.1145/3295222', 'doi:10.1145/3295222', 'https://doi.org/10.1145/3295222', 'https://dx.doi.org/10.1145/3295222']) {
    assert.equal(q(L.connectedPapersURL({ doi })), '10.1145/3295222', doi);
  }
});

test('with neither, a real title is searched, cut to a bounded length', () => {
  assert.equal(q(L.connectedPapersURL({ title: '  Attention   Is All You Need ' })), 'Attention Is All You Need');
  assert.equal(q(L.connectedPapersURL({ title: 'x'.repeat(500) })).length, 200);
});

test('nothing usable gives no link rather than a bad one', () => {
  for (const paper of [null, {}, { title: 'short' }, { arxiv_id: 'not an id', doi: 'nope' }, { title: '' }]) assert.equal(L.connectedPapersURL(paper), null);
});

test('whatever the data holds, the link stays on the one host and the query is encoded', () => {
  const url = L.connectedPapersURL({ title: 'Hostile "title" & more <script>alert(1)</script> ?q=evil#frag' });
  assert.equal(new URL(url).host, 'www.connectedpapers.com');
  assert.equal(new URL(url).protocol, 'https:');
  assert.equal([...new URL(url).searchParams.keys()].join(), 'q');
  assert.ok(!url.includes('<') && !url.includes('"') && !url.includes('#'));
});
