'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app/static/route-page.js'), 'utf8');
// Run the actual recovery/request functions; graph rendering has separate tests.
const refresh = source.slice(source.indexOf('async function refreshRoute()'), source.indexOf('async function load()'));
const watch = source.slice(source.indexOf('async function watch('), source.indexOf('function change('));
function page(dirty, response, calls = []) {
  const old = {concepts: [{id: 'c1', name: 'Old topic'}]};
  const context = vm.createContext({state: {dirty, route: {graph: old, revision: 1}, draft: old, busy: false},
    api: async (body) => { calls.push(body); return response; }, notice() {}, render() {}, renderDetail() {},
    document: {body: {classList: {add() {}, remove() {}}}}, CONFLICT: 'conflict'});
  vm.runInContext(refresh + watch, context);
  return context;
}
const latest = () => ({graph: {concepts: [{id: 'c1', name: 'Replacement topic'}]}, revision: 2, watch: []});

test('clean conflict recovery displays graph belonging to refreshed revision', async () => {
  const p = page(false, latest());
  await vm.runInContext('guarded(async () => { throw new Error("revision conflict"); })', p);
  assert.equal(p.state.route.revision, 2);
  assert.equal(p.state.route.graph.concepts[0].name, 'Replacement topic');
  assert.equal(p.state.draft.concepts[0].name, 'Replacement topic');
});
test('dirty conflict recovery retains edits and reads the latest stored graph separately', async () => {
  const p = page(true, latest());
  await vm.runInContext('refreshRoute()', p);
  assert.equal(p.state.draft.concepts[0].name, 'Old topic');
  assert.equal(p.state.route.graph.concepts[0].name, 'Replacement topic');
  assert.equal(p.state.dirty, true);
});
test('watch cannot write during unsaved edits or an in-flight request', async () => {
  const calls = [], p = page(true, latest(), calls);
  await vm.runInContext('watch("c1", true)', p);
  p.state.dirty = false; p.state.busy = true;
  await vm.runInContext('watch("c1", true)', p);
  assert.equal(calls.length, 0);
});
test('watch sends explicit boolean and current revision, with no AI operation', async () => {
  const calls = [], p = page(false, latest(), calls);
  await vm.runInContext('watch("c1", true)', p);
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [{action: 'watch', concept: 'c1', value: true, revision: 1}]);
  assert.equal(p.state.route.revision, 2);
});
