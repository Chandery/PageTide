/* Does a reader question need the page image? Deterministic, zero tokens.
   A numbered reference ("Fig. 3", "图2", "图二", "第三张图") names a figure the server can
   locate from the cached full text; a generic one ("这张图", "this figure") means the page
   the user is on or quoted from. Chinese numerals are normalised to Arabic digits. */
(function(global) {
'use strict';
const CN_DIGIT = {'零':0,'〇':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9};
const CN_NUM = '[零〇一二两三四五六七八九十百]+';

// 一..九十九 (and 一百 etc.) -> integer; null when it is not a well-formed numeral.
function cnToInt(text) {
  if (!text) return null;
  if (/^\d+$/.test(text)) return Number(text);
  let total = 0, current = null;
  for (const ch of text) {
    if (ch in CN_DIGIT) {
      if (current !== null) return null;   // "二三" is not a numeral
      current = CN_DIGIT[ch];
    } else if (ch === '十' || ch === '百') {
      const unit = ch === '十' ? 10 : 100;
      total += (current === null ? 1 : current) * unit;
      current = null;
    } else return null;
  }
  return total + (current || 0) || null;
}

const LABEL = {fig: 'figure', figure: 'figure', figs: 'figure', figures: 'figure', table: 'table', tab: 'table',
  eq: 'equation', equation: 'equation', '图': 'figure', '表': 'table', '公式': 'equation'};
const kindOf = label => LABEL[String(label).toLowerCase().replace(/\.$/, '')] || 'figure';

// Compound words that only look like a label: 试图/意图/地图/企图/构图, 代表/发表/列表/外表/仪表/报表,
// 图像/图谱/图神经网络/图论, 表示/表达/表现/表明. A Chinese numeral followed by a measure word
// ("代表一个", "图一起") is a count, not a figure number.
const FIG_CN = '(?<![试意地企构蓝版])图';
const TAB_CN = '(?<![代发列外图仪报])表';
const FIG_TOPIC = '(?!像|谱|神|论|模型|结构|算法|嵌入|卷积|数据)';
const TAB_TOPIC = '(?!示|达|现|明|态|述|演|情)';
const CN_CHARS = '零〇一二两三四五六七八九十百';
const CN_REF_NUM = `(\\d+(?!\\d)|${CN_NUM}(?![${CN_CHARS}个次篇种样致般些起直]))`;

const NUMBERED = [
  // Fig. 3 / Figure 3a / Table 2 / Eq. (4); also glued to Chinese text ("解释一下Figure 2")
  [new RegExp('(?<![A-Za-z])(fig(?:ure)?s?|tab(?:le)?|eq(?:uation)?)\\s*\\.?\\s*\\(?(\\d+)', 'i'), 1, 2],
  // 图3 / 表 2 / 公式4 / 图二 / 表十二
  [new RegExp(`(${FIG_CN}|${TAB_CN}|公式)\\s*${CN_REF_NUM}`), 1, 2],
  // 第二张图 / 第3个表 / 第 4 幅图 (not 第一个表示方法)
  [new RegExp(`第\\s*(\\d+|${CN_NUM})\\s*(?:张|个|幅|副)?\\s*(图${FIG_TOPIC}|表${TAB_TOPIC}|公式)`), 2, 1],
];

// Asking about a picture without a number: the page in view (or quoted) is the subject.
// Topic words are deliberately absent: 图像生成 / 图神经网络 / image classification / 这表明 /
// graph neural network talk about a subject, not about a picture on the page.
const FIG = `图${FIG_TOPIC}`, TAB = `表${TAB_TOPIC}`;
const GENERIC = new RegExp([
  `(?:这|那|该|此)(?:一)?(?:张|个|幅|副)\\s*(?:${FIG}|${TAB})`,
  `(?:这|那|该|此)(?:${FIG}|表格|示意图)`,
  `(?:上面|下面|左边|右边)的?(?:${FIG}|表格)`,
  `(?:如|见)?(?:上|下|左|右)(?:${FIG}|表(?!示|达|现|明|态|述|演|情|面))`,
  '如图(?:所示|中|里|可见)',
  `看(?:一下|一看|看|下)?(?:这张|这个|该)?${FIG}`,
  '图片',
  '图(?:中|里|上)(?:的|有|是|显示|画)',
  `(?:示意|流程|框架|架构|结构|柱状|折线|曲线|热力|散点)${FIG}`,
  '截图',
  '\\b(?:this|that|these|those)\\s+(?:figure|image|picture|diagram|chart|plot|table|screenshot)s?\\b',
  '\\bthe\\s+(?:figure|picture|diagram|chart|plot|screenshot)s?\\b',
].join('|'), 'i');

function figureRequest(question) {
  const q = String(question || '');
  for (const [re, labelAt, numberAt] of NUMBERED) {
    const m = q.match(re);
    if (!m) continue;
    const number = cnToInt(m[numberAt]);
    if (number) return {kind: kindOf(m[labelAt]), number, generic: false};
  }
  if (GENERIC.test(q)) return {kind: 'figure', number: null, generic: true};
  return null;
}

// Local fallback for app/service.py figure_page when the server has no cached text; same
// rules: only the kind asked about, case-sensitive labels (so "Stable 2" is no table), and a
// caption (line start, colon, or a capitalised caption sentence) beats passing mentions.
const TEXT_LABELS = {
  figure: '(?:Fig(?:ure)?s?\\.?|FIG(?:URE)?S?\\.?|图)',
  table: '(?:Tab(?:le)?s?\\.?|TABLES?|表)',
  equation: '(?:Eq(?:uation)?s?\\.?|EQ\\.?|公式)',
};
function findFigurePage(texts, kind, number) {
  if (!number || !TEXT_LABELS[kind] || !texts || !texts.length) return null;
  const ref = (prefix, suffix, flags) =>
    new RegExp(`${prefix}${TEXT_LABELS[kind]}\\s*\\(?${number}(?!\\d)${suffix}`, flags);
  for (const caption of [ref('^\\s*', '', 'm'), ref('', '\\s*[:：|]\\s*\\S', ''), ref('', '[ \\t]+[A-Z][a-z]', '')]) {
    const i = texts.findIndex((text) => caption.test(text || ''));
    if (i >= 0) return i + 1;
  }
  let best = null, bestHits = 0;
  texts.forEach((text, i) => {
    const hits = (String(text || '').match(ref('', '', 'g')) || []).length;
    if (hits > bestHits) { best = i + 1; bestHits = hits; }
  });
  return best;   // null when the figure is not mentioned anywhere in the extracted text
}

global.PDHFigure = {figureRequest, cnToInt, findFigurePage};
if (typeof module !== 'undefined') module.exports = global.PDHFigure;
})(typeof window !== 'undefined' ? window : globalThis);
