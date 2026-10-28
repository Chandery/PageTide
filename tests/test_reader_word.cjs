'use strict';
// 划词翻译 of a word is a dictionary entry with "what it means here" (owner 2026-10-28), so the reader sends the sentence
// the word was selected from. Longer selections are translated as before and send no sentence.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const W = require('../app/static/reader-word.js');
const source = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');

test('one to three English words are a word lookup; sentences and other scripts are not', () => {
  for (const yes of ['verbal', 'world model', "agent's", 'state-of-the-art', 'Markov decision process']) assert.ok(W.isWord(yes), yes);
  for (const no of ['', 'the root of the problem', '注意力', 'GPT-4', 'x'.repeat(41), 'a, b']) assert.ok(!W.isWord(no), no);
});

test('the sentence around the selection is taken, whitespace folded', () => {
  const text = 'First sentence here. The root of the problem is visual rather than\nverbal abuse. Last one.';
  const at = text.indexOf('verbal');
  assert.equal(W.sentenceAround(text, at), 'The root of the problem is visual rather than verbal abuse.');
  assert.equal(W.sentenceAround(text, -1, 'Last'), 'Last one.');
  assert.equal(W.sentenceAround('', 0), '');
});

test('a hyphen at a line end is joined and the position stays on the word', () => {
  const text = 'We use rein- forcement learning for control.';
  assert.equal(W.sentenceAround(text, text.indexOf('control')), 'We use reinforcement learning for control.');
});

test('a very long sentence is cut around the selection', () => {
  const text = 'a '.repeat(400) + 'target ' + 'b '.repeat(400) + '.';
  const out = W.sentenceAround(text, text.indexOf('target'));
  assert.ok(out.length <= W.CONTEXT_MAX, out.length);
  assert.ok(out.includes('target'));
});

test('the reader sends the sentence with a word and renders the entry', () => {
  assert.match(source, /src="\/reader-word\.js"/);
  assert.match(source, /selContext = window\.PTReaderWord\?\.contextFor\(sel\.getRangeAt\(0\), text\) \|\| ''/);
  assert.match(source, /translate\(text, rect, context\)/);
  assert.match(source, /api\('\/api\/translate', context \? \{ text, context \} : \{ text \}\)/);
  assert.match(source, /r\.kind === 'word' && r\.entry \? wordEntry\(r\.entry\)/);
  const entry = source.slice(source.indexOf('function wordEntry'), source.indexOf('async function translate'));
  for (const field of ['e.uk', 'e.us', 'e.senses', 's.pos', 's.meaning', 'e.here', 'e.word']) assert.ok(entry.includes(field), field);
  assert.ok(!/\$\{(e\.word|e\.here|s\.meaning|s\.pos|ipa)\}/.test(entry), 'model text is escaped');
});
