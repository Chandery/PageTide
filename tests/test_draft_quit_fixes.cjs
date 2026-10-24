'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function setup(fail=false) {
  const events = [];
  const window={addEventListener(){},PT:{toast:(...args)=>events.push(['toast',...args]),api:async(path,body)=>{
    events.push(['write',body]); if(fail) throw new Error('disk failure'); return {draft:{version:1}};
  }},__TAURI_INTERNALS__:{invoke:async cmd=>events.push(['quit',cmd])}};
  const context=vm.createContext({module:{exports:{}},window,document:{querySelectorAll:()=>[]},localStorage:{getItem(){return null;},setItem(){}},crypto:{randomUUID:()=> 'client'},setTimeout,clearTimeout,URL});
  vm.runInContext(fs.readFileSync('app/static/organization.js','utf8'),context);
  const ui=context.module.exports;
  ui.S.root={querySelector:()=>null};
  const draft=ui.draftFor({key:'a',note:'Old note',note_version:1});
  draft.text='Latest edit before 250ms'; draft.dirty=true;
  ui.storeDraft('a',draft);
  return {window,ui,events};
}
test('immediate quit durably writes the latest draft before ending the backend',async()=>{
  const {window,events}=setup();
  await window.PTPrepareQuit();
  assert.equal(events[0][0],'write');
  assert.equal(events[0][1].text,'Latest edit before 250ms');
  assert.equal(events[0][1].action,'draft-save');
  assert.equal(events.at(-1)[0],'quit');
});
test('failed durable write keeps application open and reports the failure',async()=>{
  const {window,events}=setup(true);
  await window.PTPrepareQuit();
  assert.equal(events.some(event=>event[0]==='quit'),false);
  assert.ok(events.some(event=>event[0]==='toast' && event[1].includes('草稿未保存')));
});
