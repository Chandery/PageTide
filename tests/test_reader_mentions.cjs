'use strict';
// Notes can @ other notes (owner 2026-10-28). The arrows in the 笔记 list stay readable with several @s: one trunk per
// @-ing note branching to its targets, overlapping trunks side by side, arrows into one note spread apart.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const M = require('../app/static/reader-mentions.js');
const source = fs.readFileSync(path.join(__dirname, '../app/static/index.html'), 'utf8');

const card = (i) => ({top: i * 100, bottom: i * 100 + 80});
const boxes = (n) => Object.fromEntries(Array.from({length: n}, (_, i) => ['n' + i, card(i)]));
const note = (i, ...to) => ({id: 'n' + i, mentions: to.map((t) => 'n' + t)});

test('no @ means no gutter', () => {
  const r = M.arrows([note(0), note(1)], boxes(2));
  assert.equal(r.width, 0);
  assert.deepEqual(r.groups, []);
});

test('one @ is one trunk from the source to the target, with the source above or below', () => {
  const down = M.arrows([note(0, 2), note(1), note(2)], boxes(3));
  assert.equal(down.groups.length, 1);
  const g = down.groups[0];
  assert.equal(g.src, 'n0'); assert.equal(g.srcY, 40); assert.deepEqual(g.targets.map((t) => t.id), ['n2']);
  assert.equal(g.targets[0].y, 240);
  assert.equal(down.width, M.EDGE * 2 + M.LANE);
  assert.equal(g.x, down.width - M.EDGE);                                   // the first lane is the one next to the cards
  const up = M.arrows([note(0), note(1), note(2, 0)], boxes(3)).groups[0];
  assert.equal(up.srcY, 240); assert.equal(up.targets[0].y, 40);
});

test('several @s of one note share a single trunk', () => {
  const r = M.arrows([note(0, 1, 2, 3), note(1), note(2), note(3)], boxes(4));
  assert.equal(r.groups.length, 1);
  assert.deepEqual(r.groups[0].targets.map((t) => t.id), ['n1', 'n2', 'n3']);
  assert.equal(r.width, M.EDGE * 2 + M.LANE);
});

test('trunks that overlap take different lanes; ones that do not overlap share a lane', () => {
  const overlapping = M.arrows([note(0, 3), note(1, 4), note(2), note(3), note(4)], boxes(5));
  assert.deepEqual(overlapping.groups.map((g) => g.lane).sort(), [0, 1]);
  assert.equal(overlapping.width, M.EDGE * 2 + 2 * M.LANE);
  const apart = M.arrows([note(0, 1), note(1), note(2), note(3, 4), note(4)], boxes(5));
  assert.deepEqual(apart.groups.map((g) => g.lane), [0, 0]);
  const x = (r) => r.groups.map((g) => g.x);
  assert.notEqual(x(overlapping)[0], x(overlapping)[1]);
});

test('arrows into one note are spread apart and stay on its card; self and unknown targets are ignored', () => {
  const r = M.arrows([note(0, 3), note(1, 3), note(2, 3), note(3, 3, 9)], boxes(4));
  const into = r.groups.flatMap((g) => g.targets.filter((t) => t.id === 'n3').map((t) => t.y)).sort((a, b) => a - b);
  assert.equal(new Set(into).size, 3);
  assert.ok(into.every((y) => y >= 306 && y <= 374), into);
  assert.deepEqual(r.groups.map((g) => g.src), ['n0', 'n1', 'n2']);         // n3 only @s itself and a note that is not listed
});

test('more overlapping trunks than lanes share the last lane and are marked crowded', () => {
  const n = M.LANES_SHOWN + 2, notes = Array.from({length: n}, (_, i) => note(i, n + i));
  const b = boxes(2 * n);
  const r = M.arrows([...notes, ...Array.from({length: n}, (_, i) => note(n + i))], b);
  assert.equal(r.width, M.EDGE * 2 + M.LANES_SHOWN * M.LANE);
  assert.equal(Math.max(...r.groups.map((g) => g.lane)), M.LANES_SHOWN - 1);
  assert.equal(r.groups.filter((g) => g.crowded).length, 2);
});

test('a minimum width keeps the gutter the reader already made room for', () => {
  assert.equal(M.arrows([note(0, 1), note(1)], boxes(2), 40).width, 40);
  assert.equal(M.arrows([note(0), note(1)], boxes(2), 40).width, 0);
});

test('a group is drawn as stubs, a trunk, a dot at the source and a head at each target', () => {
  const r = M.arrows([note(0, 1, 2), note(1), note(2)], boxes(3));
  const s = M.shape(r.groups[0], r.width);
  assert.equal((s.d.match(/H/g) || []).length, 3);                          // the source stub and one stub per target
  assert.equal(s.heads.length, 2);
  assert.deepEqual(s.dot, {cx: r.width - 0.5, cy: 40});
  assert.match(s.d, /V/);
});

test('the picker offers other notes not yet @ed, narrowed by a typed word or a page', () => {
  const notes = [{id: 'a', page: 1, quote: 'Attention is all', comment: ''}, {id: 'b', page: 3, quote: 'Residual', comment: '看这里 attention'},
                 {id: 'c', page: 3, quote: 'Dropout', comment: ''}];
  assert.deepEqual(M.candidates(notes, 'a', [], '').map((n) => n.id), ['b', 'c']);
  assert.deepEqual(M.candidates(notes, 'a', ['b'], '').map((n) => n.id), ['c']);
  assert.deepEqual(M.candidates(notes, 'c', [], 'ATTENTION').map((n) => n.id), ['a', 'b']);
  assert.deepEqual(M.candidates(notes, 'a', [], '第 3 页').map((n) => n.id), ['b', 'c']);
  assert.deepEqual(M.mentionedBy([{id: 'a', mentions: ['b']}, {id: 'c', mentions: ['b', 'a']}], 'b'), ['a', 'c']);
});

test('a note is named by its quote, else its text, cut short', () => {
  assert.equal(M.label({quote: ' Attention  is\nall ', comment: 'x'}), 'Attention is all');
  assert.equal(M.label({quote: '', comment: '只有笔记'}), '只有笔记');
  assert.equal(M.label({quote: 'a'.repeat(40)}, 10), 'a'.repeat(10) + '…');
  assert.equal(M.label({quote: '', comment: ''}), '');
});

const ID = (c) => c.repeat(32);
const notes3 = [{id: ID('a')}, {id: ID('b')}, {id: ID('c')}];

test('notes are numbered from the top down', () => {
  const {numberOf, idOf} = M.numbering(notes3);
  assert.deepEqual([...numberOf], [[ID('a'), 1], [ID('b'), 2], [ID('c'), 3]]);
  assert.equal(idOf.get(2), ID('b'));
});

test('the text box shows @3 and what is saved holds a reference, so numbers can move without breaking a reference', () => {
  const {numberOf, idOf} = M.numbering(notes3);
  const saved = M.fromEditable('这一句回答了@1 的问题，用了@3 的观点', idOf, ID('b'));
  assert.equal(saved, `这一句回答了@[${ID('a')}] 的问题，用了@[${ID('c')}] 的观点`);
  assert.equal(M.toEditable(saved, numberOf), '这一句回答了@1 的问题，用了@3 的观点');
  // a note is added above: the same saved text now reads @2 and @4
  const shifted = M.numbering([{id: ID('z')}, ...notes3]).numberOf;
  assert.equal(M.toEditable(saved, shifted), '这一句回答了@2 的问题，用了@4 的观点');
  assert.deepEqual(M.ids(saved + saved), [ID('a'), ID('c')]);
});

test('only an @ with a number of another note is a reference; the rest stays as typed', () => {
  const {idOf} = M.numbering(notes3);
  for (const same of ['a@1', 'name@3 y', '@9', '@', '@a', '@@1', '5@1']) {   // glued to a word, no such note, not a number
    assert.equal(M.fromEditable(same, idOf, ID('b')), same, same);
  }
  assert.equal(M.fromEditable('看@2', idOf, ID('b')), '看@2');                    // its own number is not a reference
  assert.equal(M.fromEditable('@1@3', idOf, ID('b')), `@[${ID('a')}]@3`);       // a digit run or @ right before is not a start
  const twelve = Array.from({length: 12}, (_, i) => ({id: ID('abcdef0123456789'[i])}));   // @12 is the twelfth note, not @1 then 2
  assert.equal(M.fromEditable('@12 和 @1', M.numbering(twelve).idOf, ID('z')), `@[${ID('5')}] 和 @[${ID('a')}]`);
});

test('a reference to a deleted note reads as the marker; the text is cut into pieces for drawing', () => {
  const {numberOf} = M.numbering([{id: ID('a')}, {id: ID('c')}]);
  const stored = `见@[${ID('c')}] 与@[${ID('b')}]末`;
  assert.equal(M.toEditable(stored, numberOf), `见@2 与${M.GONE}末`);
  assert.deepEqual(M.segments(stored, numberOf), [{text: '见'}, {n: 2, id: ID('c')}, {text: ' 与'}, {text: M.GONE}, {text: '末'}]);
  assert.deepEqual(M.segments('', numberOf), []);
});

test('picking a note puts @n into the text at the caret, spaced so it reads as a reference', () => {
  assert.deepEqual(M.insertMention('这一句回答了', 6, 6, 2), {value: '这一句回答了@2 ', caret: 9});
  assert.deepEqual(M.insertMention('see', 3, 3, 4), {value: 'see @4 ', caret: 7});                // a letter before: a space first
  assert.deepEqual(M.insertMention('回答了@ 的问题', 4, 4, 1, true), {value: '回答了@1 的问题', caret: 5});   // the typed @ is replaced
  assert.deepEqual(M.insertMention('用了，好', 2, 2, 3), {value: '用了@3，好', caret: 4});           // punctuation after: no space
  assert.deepEqual(M.insertMention('abc def', 3, 4, 5), {value: 'abc @5 def', caret: 7});          // a selection is replaced
});

test('the reader wires the @ button, picker, numbers and arrows', () => {
  assert.match(source, /src="\/reader-mentions\.js"/);
  for (const id of ['noteAt', 'noteNum', 'notePicker', 'notePickQ', 'notePickList']) assert.match(source, new RegExp(`id="${id}"`));
  assert.ok(!/noteMentions|nchip|paintMentions/.test(source), 'the old chips are gone');
  // typing @ offers the notes; the choice goes into the text
  assert.match(source, /e\.inputType !== 'insertText' \|\| e\.data !== '@'/);
  assert.match(source, /PTReaderMentions\.insertMention\(t\.value, pickRange\.start, pickRange\.end, n, pickTyped\)/);
  // the text box shows numbers, what is saved holds references
  assert.match(source, /\$\('#noteText'\)\.value = PTReaderMentions\.toEditable\(note\.comment, nums\.numberOf\)/);
  assert.match(source, /PTReaderMentions\.fromEditable\(\$\('#noteText'\)\.value, noteNumbers\(\)\.idOf, noteOpen\.id\)/);
  assert.match(source, /const \{ mentions, \.\.\.send \} = change;/);               // the server works the arrows out from the text
  // every card, picker row and the editor show the note's number
  assert.match(source, /num\.className = 'nn'; num\.textContent = nums\.numberOf\.get\(a\.id\)/);
  assert.match(source, /PTReaderMentions\.segments\(a\.comment, nums\.numberOf\)/);
  assert.match(source, /\$\('#noteNum'\)\.textContent = nums\.numberOf\.get\(note\.id\)/);
  assert.match(source, /drawMentions\(list, cards\);/);
  assert.match(source, /if \(tab === 'notes'\) listNotes\(\);/);                // measured only while the list is on screen
  assert.match(source, /e\.key === 'Escape' && !e\.isComposing && !\$\('#notePicker'\)\.hidden\) \{ e\.preventDefault\(\); closePicker\(\)/);   // Esc closes the picker, not the editor
  assert.match(source, /a\.comment = a\.comment\.split\(`@\[\$\{note\.id\}\]`\)\.join\(PTReaderMentions\.GONE\)/);
  assert.match(source, /\.nlist\.mhot \.mg:not\(\.hot\) \{ opacity:\.16; \}/);   // other arrows step back while one note is pointed at
  // owner 2026-10-28: a selected or pointed-at note lights only the arrows it sends, never those pointing at it
  const hot = source.slice(source.indexOf('function hotMentions'), source.indexOf('function hotMentions') + 500);
  assert.match(hot, /const on = Boolean\(id\) && g\.dataset\.src === id;/);
  assert.ok(!/dataset\.t/.test(hot), 'targets do not light up');
});
