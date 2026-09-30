'use strict';
// Project overview (macOS Mission Control style): ordering, grid layout and the key/pinch state machine.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function load() {
  const context = vm.createContext({ module: { exports: {} }, window: {} });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/project-switcher.js'), 'utf8'), context);
  return context.module.exports;
}

const P = ids => ids.map(id => ({ id, name: `项目${id}` }));
const key = (k, extra = {}) => ({ type: 'key', key: k, alt: false, ctrl: false, shift: false, ...extra });

test('current project first, then most recently used, then the rest in list order', () => {
  const sw = load();
  const order = sw.order(P(['a', 'b', 'c', 'd']), ['c', 'gone', 'a', 'b'], 'a');
  assert.deepEqual([...order.map(p => p.id)], ['a', 'c', 'b', 'd']);
});

test('a switch records both projects, newest first, bounded', () => {
  const sw = load();
  assert.deepEqual([...sw.recordSwitch(['x'], 'a', 'b')], ['b', 'a', 'x']);
  assert.deepEqual([...sw.touch(['a', 'b', 'c'], 'c')], ['c', 'a', 'b']);
  assert.equal(sw.touch(Array.from({ length: 40 }, (_, i) => `p${i}`), 'new').length, 20);
});

test('grid cards keep the window aspect ratio, fit the area and do not overlap', () => {
  const sw = load();
  for (const n of [1, 2, 3, 5, 9, 14]) {
    const g = sw.grid(n, 1000, 600, 1.6);
    assert.equal(g.cards.length, n);
    for (const c of g.cards) {
      assert.ok(Math.abs(c.w / c.h - 1.6) < 0.01, `aspect n=${n}`);
      assert.ok(c.x >= -0.5 && c.y >= -0.5 && c.x + c.w <= 1000.5 && c.y + c.h + g.label <= 600.5, `fits n=${n}`);
    }
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = g.cards[i], b = g.cards[j];
      const apart = a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h + g.label <= b.y || b.y + b.h + g.label <= a.y;
      assert.ok(apart, `overlap n=${n} ${i}/${j}`);
    }
  }
  // A lone project is not blown up to fill the whole screen.
  assert.ok(sw.grid(1, 1000, 600, 1.6).cards[0].w <= 1000 * 0.55);
  assert.equal(sw.grid(0, 1000, 600, 1.6).cards.length, 0);
});

test('option+up opens on the current project; escape or option+up again returns to it', () => {
  const sw = load();
  let r = sw.reduce(sw.initial(4, 2), key('ArrowUp', { alt: true }));
  assert.equal(r.effect, 'open');
  assert.equal(r.state.open, true);
  assert.equal(r.state.index, 0);
  const moved = sw.reduce(r.state, key('ArrowRight')).state;
  for (const k of [key('Escape'), key('ArrowUp', { alt: true })]) {
    const back = sw.reduce(moved, k);
    assert.equal(back.effect, 'select');
    assert.equal(back.index, 0);
    assert.equal(back.state.open, false);
  }
  // Plain arrows and escape do nothing while closed, so the page keeps them.
  assert.equal(sw.reduce(sw.initial(4, 2), key('ArrowUp')).handled, false);
  assert.equal(sw.reduce(sw.initial(4, 2), key('Escape')).handled, false);
});

test('arrows move through the grid by column and row, clamped; enter selects', () => {
  const sw = load();
  let s = sw.openState(sw.initial(5, 3));
  s = sw.reduce(s, key('ArrowRight')).state; assert.equal(s.index, 1);
  s = sw.reduce(s, key('ArrowDown')).state; assert.equal(s.index, 4);
  s = sw.reduce(s, key('ArrowDown')).state; assert.equal(s.index, 4);
  s = sw.reduce(s, key('ArrowRight')).state; assert.equal(s.index, 4);
  s = sw.reduce(s, key('ArrowUp')).state; assert.equal(s.index, 1);
  s = sw.reduce(s, key('ArrowLeft')).state; assert.equal(s.index, 0);
  s = sw.reduce(s, key('ArrowLeft')).state; assert.equal(s.index, 0);
  s = sw.reduce(s, key('Tab', { shift: true })).state; assert.equal(s.index, 4);
  const r = sw.reduce(s, key('Enter'));
  assert.equal(r.effect, 'select');
  assert.equal(r.index, 4);
});

test('pinch in opens, spreading enters the highlighted project', () => {
  const sw = load();
  let r = sw.reduce(sw.initial(3, 3), { type: 'pinch', delta: -10, time: 0 });
  assert.equal(r.state.open, false);  // small movements accumulate, no jitter
  r = sw.reduce(r.state, { type: 'pinch', delta: -40, time: 16 });
  assert.equal(r.effect, 'open');
  // Still pinching in after it opened changes nothing; reversing starts a new count.
  r = sw.reduce(r.state, { type: 'pinch', delta: -30, time: 32 });
  assert.equal(r.effect, null);
  r = sw.reduce(sw.reduce(r.state, key('ArrowRight')).state, { type: 'pinch', delta: 60, time: 48 });
  assert.equal(r.effect, 'select');
  assert.equal(r.index, 1);
});

test('a pause between pinch movements starts a new gesture', () => {
  const sw = load();
  let r = sw.reduce(sw.initial(3, 3), { type: 'pinch', delta: -30, time: 0 });
  r = sw.reduce(r.state, { type: 'pinch', delta: -30, time: 1000 });
  assert.equal(r.state.open, false);
});
