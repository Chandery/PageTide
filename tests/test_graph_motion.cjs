'use strict';
const test=require('node:test'), assert=require('node:assert/strict');
const {create,limited}=require('../app/static/graph-motion.js');
function fixture(reduced=false) {
  let time=0;
  function node(id,x) { return { id:()=>id, p:{x,y:0}, length:1, classes:new Set(), animations:[],
    position(p){if(p){this.p={...p};return this;}return this.p;},removed:()=>false,
    addClass(c){this.classes.add(c);return this;},removeClass(c){c.split(' ').forEach(s=>this.classes.delete(s));return this;},hasClass(c){return this.classes.has(c);},
    stop(){return this;},animate(t,o){this.animations.push({t,o});if(t.position)this.p={...t.position};return this;},
    grabbed:()=>false,selected:()=>false,degree:()=>2,neighborhood:()=>[b],connectedEdges:()=>elements}; }
  const a=node('a',0), b=node('b',100), far=node('far',300);
  const elements={stop(){return this;},removeStyle(){return this;},removeClass(c){[a,b,far].forEach(n=>n.removeClass(c));return this;},addClass(){return this;}};
  const listeners={};
  const cy={elements:()=>elements,zoom:()=>1,stop(){},batch:fn=>fn(),on:(k,fn)=>{listeners[k]=fn;},container:()=>null};
  const motion=create(cy,{reduced:()=>reduced,now:()=>time});
  return {a,b,far,motion,listeners,tick:t=>{time=t;}};
}
test('elastic neighbors are bounded and never leak into saved coordinates',()=>{
  const f=fixture();f.motion.begin(f.a);f.tick(16);f.a.position({x:300,y:0});f.motion.drag(f.a);
  assert.ok(f.b.position().x>100 && f.b.position().x<=118);
  assert.equal(f.motion.position(f.b).x,100);assert.equal(f.far.position().x,300);
  f.motion.end(f.a);assert.equal(f.motion.position(f.a).x,300);
  assert.ok(f.a.position().x<=310);f.motion.settle();
  assert.equal(f.a.position().x,300);assert.equal(f.b.position().x,100);
});
test('pause before release has no throw and interruption restores neighbors',()=>{
  const f=fixture();f.motion.begin(f.a);f.tick(20);f.a.position({x:20,y:0});f.motion.drag(f.a);f.tick(200);f.motion.end(f.a);
  assert.equal(f.a.position().x,20);f.motion.settle();assert.equal(f.b.position().x,100);
});
test('reduced motion keeps direct drag without neighbor animation',()=>{
  const f=fixture(true);f.motion.begin(f.a);f.tick(20);f.a.position({x:70,y:0});f.motion.drag(f.a);f.motion.end(f.a);
  assert.equal(f.b.animations.length,0);assert.equal(f.a.position().x,70);f.listeners.destroy();
});
test('selected reading neighbors do not move, and vector limits are radial',()=>{
  const f=fixture();f.b.selected=()=>true;f.motion.begin(f.a);f.a.position({x:80,y:0});f.motion.drag(f.a);
  assert.equal(f.b.animations.length,0);assert.equal(Math.hypot(...Object.values(limited(30,40,10))),10);f.motion.settle();
});

test('vendored Cytoscape settles real animated nodes without drifting their anchors',async()=>{
  const cytoscape=require('../app/static/vendor/cytoscape/cytoscape.min.js');
  const cy=cytoscape({headless:true,styleEnabled:true,elements:[{data:{id:'a'},position:{x:100,y:100}},
    {data:{id:'b'},position:{x:300,y:100}},{data:{id:'ab',source:'a',target:'b'}}],layout:{name:'preset'}});
  const m=create(cy), a=cy.$id('a'), b=cy.$id('b');
  try {
    m.begin(a);a.position({x:180,y:100});m.drag(a);m.end(a);
    assert.deepEqual(m.position(b),{x:300,y:100});
    await new Promise(resolve=>setTimeout(resolve,650));
    assert.deepEqual(a.position(),{x:180,y:100});assert.deepEqual(b.position(),{x:300,y:100});
  } finally {m.settle();cy.destroy();}
});
