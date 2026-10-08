'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const Brief = require('../app/static/route-brief.js');

test('same five fields validate complete Unicode characters without silently shortening', () => {
  assert.deepEqual(Brief.validate({goal:' g '}), {goal:'g',known:'',include:'',exclude:'',structure:''});
  for (const [key,,cap] of Brief.FIELDS) {
    const input = {goal:'g',[key]:'😀'.repeat(cap)};
    assert.equal([...Brief.validate(input)[key]].length,cap);
    assert.throws(() => Brief.validate({...input,[key]:input[key]+'中'}));
    assert.throws(() => Brief.validate({goal:'g',[key]:null}));
  }
  assert.throws(() => Brief.validate({goal:''}));
  assert.throws(() => Brief.validate({goal:'g',extra:'text'}));
  assert.throws(() => Brief.validate({goal:'g',structure:'\ud800'}));
});
test('shared form retains teacher text as data and never rewrites it', () => {
  const controls = new Map();
  const holder = {innerHTML:'',querySelector(selector) {if (!controls.has(selector)) controls.set(selector,{value:''});return controls.get(selector);}};
  const input = {goal:'学习目标',structure:'<script>danger</script>\n# 老师：先概率，再模型'};
  Brief.mount(holder,input);
  assert.equal(Brief.read(holder).structure,input.structure);
  assert.equal((holder.innerHTML.match(/data-brief=/g) || []).length,5);
  assert.ok(!holder.innerHTML.includes(input.structure));
});
test('preview explains changes, goals, resets and stale preservation without exposing IDs', () => {
  const graph={concepts:[{id:'private-id',name:'<img src=x>'}],targets:['private-id']};
  const html=Brief.previewHTML({before:{graph,goal_status:'completed'},after:{graph,goal_status:'learning',brief:{goal:'new'}},changes:{reset:['private-id']},stale:true});
  assert.match(html,/重新计算掌握/);assert.match(html,/草稿保留/);
  assert.match(html,/当前目标已完成/);assert.match(html,/当前目标学习中/);
  assert.ok(!html.includes('private-id'));assert.ok(!html.includes('<img src=x>'));
});
test('AI prerequisite warnings show the relation and missing necessity evidence', () => {
  const graph={concepts:[{id:'private-a',name:'Representation'},{id:'private-b',name:'Planning'}],targets:['private-b']};
  const html=Brief.previewHTML({before:{graph},after:{graph},changes:{warnings:[{kind:'prerequisite_review',from:'private-a',to:'private-b',reason:''}]}});
  assert.match(html,/Representation → Planning/);assert.match(html,/必要/);assert.match(html,/补充依据或删除/);
  assert.ok(!html.includes('[object Object]'));assert.ok(!html.includes('private-a'));
});
