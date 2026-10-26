'use strict';
// LaTeX in titles and abstracts (math.js + vendored KaTeX), checked on a real arXiv record saved for the purpose.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const staticDir = path.join(__dirname, '../app/static');
const read = (name) => fs.readFileSync(path.join(staticDir, name), 'utf8');
const paper = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/latex_paper.json'), 'utf8'));
const katex = require(path.join(staticDir, 'vendor/katex/katex.min.js'));
const context = { window: {} };
vm.createContext(context);
vm.runInContext(read('math.js'), context);
const { PTMath } = context.window;
const formulas = (text) => [...text.matchAll(new RegExp(PTMath.MATH.source, 'g'))].map((m) => m[1] ?? m[2] ?? m[3] ?? m[4]);
const OPTIONS = { throwOnError: true, displayMode: false, trust: false, strict: 'ignore', maxSize: 10, maxExpand: 200 };

test('every formula in the saved Fuglede paper is found and drawn', () => {
  assert.deepEqual(formulas(paper.title), ['\\mathbb{F}_{p}^{d}', 'p=2,\\,d=8', 'p=11,\\,d=3']);
  const inAbstract = formulas(paper.abstract);
  assert.equal(inAbstract.length, 7);
  for (const tex of [...formulas(paper.title), ...inAbstract]) assert.doesNotThrow(() => katex.renderToString(tex, OPTIONS), tex);
  assert.match(katex.renderToString('\\mathbb{F}_2^8', OPTIONS), /mathbb/);
});

test('prices and lone dollar signs stay text', () => {
  for (const text of ['costs $5 and $10 per month', 'a $ sign', '$ x$ and $y $', 'no math here']) assert.deepEqual(formulas(text), [], text);
  assert.deepEqual(formulas('inline \\(a+b\\) and display $$c^2$$ and \\[d\\]'), ['a+b', 'c^2', 'd']);
  assert.equal(PTMath.hasMath(paper.title), true);
  assert.equal(PTMath.hasMath('plain title'), false);
});

test('source text cannot use KaTeX to make links or load anything', () => {
  for (const tex of ['\\href{javascript:alert(1)}{x}', '\\url{https://example.org}', '\\includegraphics{https://example.org/a.png}']) {
    const html = katex.renderToString(tex, { ...OPTIONS, throwOnError: false });
    assert.doesNotMatch(html, /<a |href=|<img/, tex);
  }
});

test('titles and abstracts are marked on every page that shows them, and those pages load math.js', () => {
  const index = read('index.html');
  for (const marked of ['class="paper-title" data-no-i18n data-tex>${esc(c.title)}', '<span data-no-i18n data-tex>${esc(c.abstract)}</span>',
    '<h2 data-no-i18n data-tex>${esc(d.title)}</h2>', 'data-no-i18n data-tex>${esc(d.abstract)}</div>',
    '<h2 id="readerTitle" data-tex></h2>', 'id="petPaper" data-tex>']) assert.ok(index.includes(marked), marked);
  assert.doesNotMatch(index, /md\(d\.abstract\)/);                     // an abstract is not Markdown: its * and _ belong to formulas
  for (const [file, count] of [['organization.js', 3], ['weekly-ui.js', 2], ['route-editor.js', 3], ['project-creation.js', 3], ['import.js', 2]])
    assert.equal((read(file).match(/data-tex/g) || []).length, count, file);
  for (const page of ['index.html', 'project_creation.html', 'weekly_report.html', 'route.html', 'import.html'])
    assert.match(read(page), /<script src="\/math\.js"><\/script>/, page);
  assert.ok(fs.existsSync(path.join(staticDir, 'vendor/katex/fonts/KaTeX_Main-Regular.woff2')));
  assert.ok(fs.existsSync(path.join(staticDir, 'vendor/katex/LICENSE')));
});
