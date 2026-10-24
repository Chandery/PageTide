/* Interface language. Chinese is the source language: the pages write Chinese inline, and the
   server injects window.PAGETIDE_I18N = {lang, messages} (route /i18n/current.js) from the language
   chosen on the settings page. In English this layer replaces every rendered Chinese text node
   and title / placeholder / aria-label / alt by its pack entry: the exact text first, then a
   pattern key whose "{0}" parts are filled from the text. A part next to a counter (篇, 页…) or
   after 第/共 takes only a number; a Chinese part is translated only when it is a whole pack
   entry, and is otherwise kept verbatim (a name, a note, AI text), never half-translated. It also
   wraps alert / confirm / prompt. Text without a pack entry stays Chinese and is listed in
   PDHi18n.misses() so a preview audit can find it. Zero tokens; nothing leaves the page.
   Never translated: the PDF text layer, form fields being edited, [data-no-i18n] and the
   containers of titles, abstracts, notes and quotes listed in SKIP. */
(function (global) {
'use strict';
const config = global.PAGETIDE_I18N || {};
const lang = config.lang === 'en-US' ? 'en-US' : 'zh-CN';
const HAN = /[㐀-鿿]/;
const PLACEHOLDER = /\{(\d+)\}/g;
const LIST = /\s·\s/;   // the separator of a " · " list
const norm = (text) => String(text).replace(/\s+/g, ' ').trim();
const escapeRe = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// A part next to a counter word, or after 第/共, is a count: "{0} 页" never takes "首" or "见第 3".
const COUNTED = /^\s*[篇页个条次字周]/;
const ORDINAL = /[第共]\s*$/;
const NUMBER = '(\\d[\\d,.]*\\s*[kKmM%]?|[—–?…-])';
const ANY = '([\\s\\S]*?)';

const exact = new Map();
const patterns = [];
for (const [key, value] of Object.entries(lang === 'en-US' && config.messages || {})) {
  if (!/\{\d+\}/.test(key)) { exact.set(norm(key), value); continue; }
  const literals = norm(key).split(/\{\d+\}/);
  const order = [...key.matchAll(PLACEHOLDER)].map((m) => Number(m[1]));
  const slots = order.map((_, i) => (COUNTED.test(literals[i + 1]) || ORDINAL.test(literals[i]) ? NUMBER : ANY));
  const source = literals.map((part) => part.split(' ').map(escapeRe).join('\\s*'))
    .reduce((all, part, i) => all + slots[i - 1] + part);
  // Cheap pre-check: the longest Chinese word of the key (spaces are optional) must occur in the text.
  const anchor = literals.flatMap((part) => part.split(' ')).filter((part) => HAN.test(part))
    .sort((a, b) => b.length - a.length)[0];
  if (!anchor) continue;   // a key needs Chinese text of its own
  patterns.push({re: new RegExp(`^\\s*${source}\\s*$`, 'd'), anchor, order, value,
    listed: LIST.test(key), weight: literals.join('').replace(/\s/g, '').length});
}
patterns.sort((a, b) => b.weight - a.weight);

const missed = new Set();

// ["one paper", "{0} papers"]: the singular form when the first number filled in is 1.
function pick(value, values) {
  if (!Array.isArray(value)) return value;
  const first = values.find((v) => /^\s*\d+\s*$/.test(v));
  return first !== undefined && Number(first) === 1 ? value[0] : value[1];
}

function fill(template, values) {
  return template.replace(PLACEHOLDER, (_, n) => values[Number(n)] ?? '');
}

// A Chinese part filled into a pattern is translated only as a whole: a pack entry, a list of
// them, or another pattern sentence under the same rules ("（2 个查询被限流跳过）" inside
// "新增 3 条{1}"). Anything else is someone's text and comes back as it is.
function whole(part, depth) {
  return depth < 3 ? lookup(part, depth + 1) : null;
}

function lookup(text, depth, patterned = true) {
  const key = norm(text);
  if (exact.has(key)) return pick(exact.get(key), []);
  const listed = depth < 3 ? segments(key, depth, patterned) : null;
  if (listed != null) return listed;
  if (!patterned) return null;
  for (const p of patterns) {
    if (!key.includes(p.anchor)) continue;
    const m = p.re.exec(key);
    // A key that is not itself a list never swallows one: "有用 {0}" must not take "0 · 未知词".
    if (!m || (!p.listed && m.slice(1).some((part) => LIST.test(part)))) continue;
    const values = [];
    let glued = false;
    p.order.forEach((n, i) => {
      const part = m[i + 1];
      const hit = HAN.test(part) ? whole(part, depth) : null;
      // Chinese stuck to the key's own Chinese ("收藏夹" against "收藏 {0}") is one word, not a slot,
      // unless the part is a pack entry by itself; a nested pattern sentence gets no exemption.
      const [start, end] = m.indices[i + 1];
      if (!exact.has(norm(part)) && HAN.test(part) && start < end
          && (HAN.test(key[start - 1] || '') && HAN.test(part[0])
              || HAN.test(key[end] || '') && HAN.test(part[part.length - 1]))) glued = true;
      values[n] = hit ?? part;
    });
    if (glued) continue;
    return fill(pick(p.value, values), values);
  }
  return null;
}

// "有用 0 · 收藏 2": a list joined by " · " is translated part by part, all or nothing. It runs
// before the patterns so a short key such as "有用 {0}" cannot swallow the rest of the list.
function segments(key, depth, patterned) {
  const parts = key.split(/\s+·\s+/);
  if (parts.length < 2) return null;
  const out = [];
  for (const part of parts) {
    const hit = HAN.test(part) ? lookup(part, depth + 1, patterned) : part;
    if (hit == null) return null;
    out.push(hit);
  }
  return out.join(' · ');
}

// Chinese text -> English, keeping the surrounding whitespace; unknown text comes back unchanged.
function translate(text, depth = 0) {
  if (lang !== 'en-US' || text == null) return text;
  const value = String(text);
  if (!HAN.test(value)) return value;
  const hit = lookup(value, depth);
  if (hit == null) {
    if (depth === 0) missed.add(norm(value));
    return value;
  }
  const lead = value.match(/^\s*/)[0], trail = value.match(/\s*$/)[0];
  return lead + norm(hit) + trail;
}

// Chinese source text with {name} slots -> the current language. A plural entry follows the
// first number among the values, so the slots are filled after the form is chosen.
function t(text, vars) {
  const named = (out) => out.replace(/\{(\w+)\}/g, (all, name) => (name in vars ? vars[name] : all));
  if (!vars) return translate(text);
  const key = norm(text);
  if (lang === 'en-US' && exact.has(key)) return named(pick(exact.get(key), Object.values(vars).map(String)));
  return named(translate(text));
}

// Only a whole pack entry: for text that may be someone else's (a model's follow-up question).
function exactly(text) {
  if (lang !== 'en-US' || text == null || !HAN.test(String(text))) return text;
  const key = norm(text);
  return exact.has(key) ? pick(exact.get(key), []) : text;
}

// App-generated parser errors contain raw bibliography keys/snippets. Format
// their known system frame while retaining those values verbatim, even when a
// key equals a UI label. Call this only for typed system notices/errors, never
// for titles, notes, names, quotes or model prose.
function systemText(text) {
  const value = String(text ?? '');
  let match = value.match(/^条目 (.+) 没有标题$/);
  if (match) return t('条目 {entry} 没有标题', {entry:match[1]});
  match = value.match(/^有一个条目没有结束：([\s\S]*)$/);
  if (match) return t('有一个条目没有结束：{snippet}', {snippet:match[1]});
  match = value.match(/^条目 (.+)：(字段没有结束|字段格式不对)$/);
  if (match) return t('条目 {entry}：{reason}', {entry:match[1],reason:t(match[2])});
  match = value.match(/^第 (\d+) 项没有读取：([\s\S]+)$/);
  if (match) return t('第 {entry} 项没有读取：{reason}', {entry:match[1],reason:t(match[2])});
  return t(value);
}

global.PDHi18n = {lang, t, translate, exact: exactly, system: systemText, misses: () => [...missed]};
if (lang !== 'en-US') return;

document.documentElement.lang = 'en';
// Nothing inside is touched: code, the PDF text layer, and what a person or a model wrote
// (titles, abstracts, notes, drafts, quotes) in the library page's own markup.
const SKIP = 'script,style,.textLayer,[data-no-i18n],pre,.org-markdown,.org-detail-title,.org-abstract p,'
  + '.org-paper-open strong';
const FIELD = 'textarea,[contenteditable=""],[contenteditable="true"]';   // the user's text; hints are translated
const QUIET = `${SKIP},${FIELD}`;
const ATTRS = ['title', 'placeholder', 'aria-label', 'alt'];
const written = new WeakMap();   // node -> what this layer wrote, so its own writes are not read again

function textNode(node) {
  const before = node.nodeValue;
  if (!HAN.test(before) || written.get(node) === before) return;
  const parent = node.parentElement;
  if (parent && parent.closest(QUIET)) return;
  const after = translate(before);
  written.set(node, after);
  if (after !== before) node.nodeValue = after;
}

function attributes(el) {
  const mine = written.get(el) || {};
  for (const name of ATTRS) {
    const before = el.getAttribute(name);
    if (before && HAN.test(before) && mine[name] !== before) {
      const after = translate(before);
      mine[name] = after;
      if (after !== before) el.setAttribute(name, after);
    }
  }
  written.set(el, mine);
  if (el.tagName === 'INPUT' && /^(button|submit|reset)$/i.test(el.type) && HAN.test(el.value)) {
    el.value = translate(el.value);
  }
}

function walk(root) {
  if (root.nodeType === 3) { textNode(root); return; }
  if (root.nodeType !== 1 && root.nodeType !== 9) return;
  if (root.nodeType === 1) {
    if (root.closest(SKIP)) return;
    if (root.matches(FIELD)) attributes(root);
    if (root.closest(FIELD)) return;
    attributes(root);
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => {
      if (node.nodeType !== 1) return NodeFilter.FILTER_ACCEPT;
      if (node.matches(SKIP)) return NodeFilter.FILTER_REJECT;
      if (node.matches(FIELD)) { attributes(node); return NodeFilter.FILTER_REJECT; }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.nodeType === 3) textNode(node); else attributes(node);
  }
}

new MutationObserver((records) => {
  for (const record of records) {
    if (record.type === 'childList') record.addedNodes.forEach(walk);
    else if (record.type === 'characterData') textNode(record.target);
    else if (record.target.nodeType === 1 && !record.target.closest(SKIP)) attributes(record.target);
  }
}).observe(document.documentElement, {childList: true, subtree: true, characterData: true,
  attributes: true, attributeFilter: ATTRS.concat('value')});
document.addEventListener('DOMContentLoaded', () => walk(document.documentElement));
walk(document.documentElement);

for (const name of ['alert', 'confirm', 'prompt']) {
  const original = global[name];
  if (typeof original === 'function') {
    global[name] = function (message, ...rest) { return original.call(global, translate(message), ...rest); };
  }
}
})(typeof window !== 'undefined' ? window : globalThis);
