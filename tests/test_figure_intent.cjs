'use strict';
// Reader questions that need the page image: numbered (incl. Chinese numerals) and generic ones.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function load() {
  const context = vm.createContext({ module: { exports: {} } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/figure-intent.js'), 'utf8'), context);
  return context.module.exports;
}
const { figureRequest, cnToInt } = load();
const plain = (value) => (value ? { ...value } : value);

test('the owner\'s questions with Chinese numerals ask for the figure', () => {
  assert.deepEqual(plain(figureRequest('图二讲了什么？')), { kind: 'figure', number: 2, generic: false });
  assert.deepEqual(plain(figureRequest('你看一下图二这个图片，然后总结一下，不要只看它的 caption')),
    { kind: 'figure', number: 2, generic: false });
});

test('numbered references in both languages', () => {
  const cases = [['Fig. 3a 的含义', 'figure', 3], ['what does Figure 12 show', 'figure', 12], ['Table 2 结果', 'table', 2],
    ['Eq. (4) 怎么推导', 'equation', 4], ['图3', 'figure', 3], ['表 十二', 'table', 12], ['公式五', 'equation', 5],
    ['第三张图在说什么', 'figure', 3], ['第 2 个表', 'table', 2], ['第二十一幅图', 'figure', 21],
    ['解释一下Figure 2', 'figure', 2], ['看一下Figure2', 'figure', 2], ['图一中的箭头', 'figure', 1],
    ['第一个表格', 'table', 1]];
  for (const [q, kind, number] of cases) assert.deepEqual(plain(figureRequest(q)), { kind, number, generic: false }, q);
});

test('generic picture questions use the page in view', () => {
  for (const q of ['这张图说明了什么', '看一下这个图', '图中的箭头是什么意思', '上图的流程', '解释一下框架图',
    '这个截图', 'what does this figure show?', 'explain the diagram', '这幅图', '该表格的指标', '如图所示的流程',
    '这张图示', '上表的结果', '见下表']) {
    assert.deepEqual(plain(figureRequest(q)), { kind: 'figure', number: null, generic: true }, q);
  }
});

test('topic words about images or graphs never attach a page', () => {
  for (const q of ['试图解决什么问题', '这表明了什么', '图像生成的效果如何', '图神经网络怎么聚合', '知识图谱',
    'image classification accuracy', 'graph neural network', '这个方法的核心假设是什么？', '意图识别', '',
    // review findings: compounds that only look like 图/表, and counts that only look like numbers
    '这个向量代表一个token吗', '发表一篇', '试图一次性解决', '第一个表示方法', '这个表示是怎么学到的？',
    '这个表现怎么样', '这个图神经网络怎么训练', 'Is this graph neural network inductive?', '该图谱的规模',
    '列表三项', '这个图模型的推断', '上表面的纹理']) {
    assert.equal(figureRequest(q), null, q);
  }
});

test('Chinese numerals', () => {
  assert.equal(cnToInt('二'), 2);
  assert.equal(cnToInt('两'), 2);
  assert.equal(cnToInt('十'), 10);
  assert.equal(cnToInt('十二'), 12);
  assert.equal(cnToInt('二十'), 20);
  assert.equal(cnToInt('九十九'), 99);
  assert.equal(cnToInt('一百'), 100);
  assert.equal(cnToInt('二三'), null);
  assert.equal(cnToInt('零'), null);
});

test('local figure-page fallback matches the server: a Table 2 caption never answers Figure 2', () => {
  const { findFigurePage } = load();
  const pages = ['cover', 'for pretraining. Figure 2 summarizes the resulting data composition.',
    'Real-world ICL (Section 2.3). Figure 2 summarizes this data',
    'RobotwinFigure 2 Data construction and in-context human video generation.\nThe bottom part of Figure 2 shows it.',
    'x', 'x', 'x', 'x', 'A Stable 2 baseline is reported in figure 3.', 'x',
    'Results\nTable 2 Zero-shot cross-task results on seven unseen tasks.'];
  assert.equal(findFigurePage(pages, 'figure', 2), 4);
  assert.equal(findFigurePage(pages, 'table', 2), 11);
  assert.equal(findFigurePage(pages, 'table', 9), null);
  assert.equal(findFigurePage(['As in Fig. 7 and Fig. 7b', 'see Fig. 7'], 'figure', 7), 1);
  assert.equal(findFigurePage([], 'figure', 2), null);
});
