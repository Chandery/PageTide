'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup(window){vm.runInNewContext(fs.readFileSync('app/static/save-file.js','utf8'),{window});return window.PTSaveFile;}
test('native export waits for a saved path or cancellation receipt',async()=>{
  const calls=[];
  const saved=setup({__TAURI_INTERNALS__:{invoke:async(...args)=>{calls.push(args);return '{"status":"saved","path":"/chosen/export.json"}';}}});
  assert.equal((await saved('export.json','payload')).path,'/chosen/export.json');
  assert.deepEqual(calls[0][0],'save_export');
  const cancelled=setup({__TAURI_INTERNALS__:{invoke:async()=>'{"status":"cancelled"}'}});
  assert.equal((await cancelled('export.json','payload')).status,'cancelled');
});
test('native errors and unsupported browser never pretend download succeeded',async()=>{
  const failed=setup({__TAURI_INTERNALS__:{invoke:async()=>{throw new Error('Permission denied');}}});
  await assert.rejects(failed('export.json','payload'),/Permission denied/);
  await assert.rejects(setup({})('export.json','payload'),/桌面应用/);
});
