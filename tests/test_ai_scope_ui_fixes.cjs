'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const R = require('../app/static/route-editor.js');
const source = fs.readFileSync('app/static/project-creation.js', 'utf8');
const i18n = fs.readFileSync('app/static/i18n.js', 'utf8');
function chineseLocale(context) { context.window=context;context.PDH_I18N={lang:'zh-CN'};vm.runInContext(i18n,context); }
const bubble = source.slice(source.indexOf('function guidanceScopeHTML(entry, live)'), source.indexOf('function renderChat(live)'));
const esc = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
function render(entry, live) {
  const el = {innerHTML: '', insertAdjacentHTML(position, html) {this.innerHTML += html;}};
  const context = vm.createContext({document: {createElement: () => el}, esc,
    turnMeta: () => '', retryable: () => false, settingsLink: () => '', $: () => null});
  chineseLocale(context);vm.runInContext(bubble, context);
  return context.bubble(entry, live).innerHTML;
}
test('actual guidance bubble shows saved sent excerpts and escapes untrusted constraints', () => {
  const html = render({role: 'assistant', content: 'Draft', scope_notice: 'Only the shown excerpt was sent.',
    context_excerpt: {goal: '<script>goal</script>', message: 'visible message', keywords: ['NSCLC', 'PD-1']}},
    {scope_notice: 'stale live receipt', context_excerpt: {goal: 'wrong goal'}});
  assert.match(html, /AI 只看到部分内容/);
  assert.doesNotMatch(html, /Only the shown excerpt was sent/);              // no standing paragraph
  assert.match(html, /&lt;script&gt;goal&lt;\/script&gt;/);
  assert.match(html, /visible message/);
  assert.match(html, /NSCLC · PD-1/);
  assert.doesNotMatch(html, /wrong goal|<script>|stale live receipt/);
});
test('guidance receipt supplements a current response and normal full inputs stay uncluttered', () => {
  assert.match(render({role: 'assistant', content: 'Draft'}, {scope_notice: 'excerpt only', context_excerpt: {goal: 'sent goal'}}), /sent goal/);
  assert.doesNotMatch(render({role: 'assistant', content: 'Draft'}), /AI 只看到部分内容/);
  assert.doesNotMatch(render({role: 'user', content: 'Goal', scope_notice: 'unused'}), /AI 只看到部分内容/);
});
test('the judgement history is not drawn on the page, so no source prose can reach it', () => {
  assert.equal(R.judgementsHTML({judgements: [{verdict: 'covered', titles: ['Public paper'], optional_relation: true,
    source_evidence: [{paper: 'p1', title: 'Actual source title', quote: '<img src=x onerror=alert(1)> in vitro evidence', type: 'basic'}]}]}), '');
});
test('intro editing displays the sent matching papers and optional omission notice', () => {
  const html = R.introInputHTML({scope_notice: 'One optional paper omitted.',
    context_excerpt: {concept: 'PD-1', terms: ['PD-1'], goal: 'NSCLC project',
      papers: [{title: 'Public evidence', abstract: '<script>data</script>'}]}});
  assert.doesNotMatch(html, /One optional paper omitted/);
  assert.match(html, /发送给 AI 的内容/);
  assert.match(html, /NSCLC project/);
  assert.match(html, /Public evidence/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.equal(R.introInputHTML({}), '');
});
test('actual quick creation live and restored notes share the same visible scope receipt', () => {
  const quick = source.slice(source.indexOf('function renderQuickNote(entry, live)'), source.indexOf('async function quickTurn('));
  const helper = source.slice(source.indexOf('function guidanceScopeHTML(entry, live)'), source.indexOf('function bubble(entry, live)'));
  for (const cold of [false, true]) {
    const note = {hidden: true, innerHTML: ''};
    const context = vm.createContext({$: id => id === '#quickNote' ? note : null, esc,
      turnMeta: () => '', retryable: () => false, settingsLink: () => ''});
    chineseLocale(context);vm.runInContext(helper + quick, context);
    const receipt = {scope_notice: 'Only this excerpt was sent.', context_excerpt: {goal: '<target>', keywords: ['NSCLC']}};
    context.renderQuickNote({role: 'assistant', content: 'Draft', ...(cold ? receipt : {})}, cold ? null : receipt);
    assert.doesNotMatch(note.innerHTML, /Only this excerpt was sent/);
    assert.match(note.innerHTML, /&lt;target&gt;/);
    assert.match(note.innerHTML, /AI 只看到部分内容/);
  }
});
test('a paid unusable guidance reply retains cost transparency and the local draft', () => {
  const meta = source.slice(source.indexOf('function turnMeta(entry, live)'), source.indexOf('const retryable'));
  const context = vm.createContext({esc}); vm.runInContext(meta, context);
  const unknown = context.turnMeta({mode: 'local', usage_reserved: true, tokens: 1700, reason_text: 'Bad reply'}, null);
  assert.match(unknown, /AI 回复不可用/); assert.match(unknown, /用量未确认/);
  assert.doesNotMatch(unknown, /1700 token|未使用 AI/);
  const plain = context.turnMeta({mode: 'local', reason_text: 'No key'}, null);
  assert.match(plain, /未使用 AI/); assert.doesNotMatch(plain, /用量未确认/);
});
