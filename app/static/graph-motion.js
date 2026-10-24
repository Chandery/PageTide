(() => {
  'use strict';
  const limited = (x, y, maximum) => {
    const k = Math.min(1, maximum / (Math.hypot(x, y) || 1));
    return { x: x*k, y: y*k };
  };
  function create(cy, { reduced = () => false, now = () => performance.now() } = {}) {
    const rest = new Map(), timers = new Set();
    let gesture = null, generation = 0;
    const later = (fn, delay) => { const timer = setTimeout(() => { timers.delete(timer); fn(); }, delay); timers.add(timer); };
    const position = node => ({ ...(rest.get(node.id())?.position || node.position()) });
    function settle() {
      generation++;
      timers.forEach(clearTimeout); timers.clear();
      cy.elements().stop(true, false).removeStyle('opacity').removeClass('org-arriving org-pulse org-dragging');
      cy.batch(() => rest.forEach(({node, position: p}) => { if (!node.removed()) node.position(p); }));
      rest.clear(); gesture = null;
    }
    function begin(node) {
      settle(); cy.stop(true, false);
      const p = { ...node.position() };
      gesture = { node, start: p, last: p, time: now(), velocity: {x:0,y:0}, moved: false };
      node.addClass('org-dragging');
      if (reduced()) return;
      // Local visual elasticity only; temporary offsets never become saved layout positions.
      node.neighborhood('node').filter(n => !n.grabbed() && !n.selected() && !n.hasClass('org-focused'))
        .slice(0, 32).forEach(n => rest.set(n.id(), { node:n, position:{...n.position()} }));
    }
    function drag(node) {
      if (!gesture || gesture.node.id() !== node.id()) return;
      const p = node.position(), t = now(), dt = t-gesture.time;
      if (dt > 0) gesture.velocity = {x:(p.x-gesture.last.x)/dt, y:(p.y-gesture.last.y)/dt};
      gesture.last = {...p}; gesture.time=t; gesture.moved=true;
      if (reduced()) return;
      rest.forEach(({node:n,position:a}) => {
        const strength = 0.12 / Math.sqrt(Math.max(1,n.degree()));
        const shift = limited((p.x-gesture.start.x)*strength, (p.y-gesture.start.y)*strength, 18/cy.zoom());
        n.stop(true,false).animate({position:{x:a.x+shift.x,y:a.y+shift.y}}, {duration:110,easing:'ease-out-cubic',queue:false});
      });
    }
    function end(node) {
      if (!gesture || gesture.node.id() !== node.id()) return;
      const g=gesture; gesture=null; node.removeClass('org-dragging');
      if (reduced()) { settle(); return; }
      const token=++generation, drop={...node.position()};
      rest.set(node.id(),{node,position:drop});
      rest.forEach(({node:n,position:p}) => n.stop(true,false).animate({position:p},{duration:480,easing:'ease-out-cubic',queue:false}));
      const v = now()-g.time > 70 || !g.moved ? {x:0,y:0} : limited(g.velocity.x*28,g.velocity.y*28,10/cy.zoom());
      if (Math.hypot(v.x,v.y)*cy.zoom() > 0.5) {
        node.stop(true,false).animate({position:{x:drop.x+v.x,y:drop.y+v.y}}, {duration:140,easing:'ease-out-cubic',queue:false,complete:()=>{
          if(token===generation) node.animate({position:drop},{duration:340,easing:'ease-out-cubic',queue:false});
        }});
      }
      later(()=>{if(token===generation) { cy.batch(()=>rest.forEach(({node:n,position:p})=>n.stop(true,false).position(p))); rest.clear(); }},520);
    }
    function enter(previous = new Set()) {
      if (reduced()) return;
      const token=generation;
      cy.elements().filter(e=>!previous.has(e.id())).forEach(e=>{
        const duration=e.isNode() ? (e.data('group')?320:480) : 620;
        const target={style:{opacity:e.isNode()?1:0.5}};
        if(previous.size && e.isNode()) {
          const p={...e.position()}, parent=e.neighborhood('node').filter(n=>n.data('group')).first();
          if(parent.length) {
            const a=parent.position(), shift=limited(a.x-p.x,a.y-p.y,40/cy.zoom());
            rest.set(e.id(),{node:e,position:p});
            e.position({x:p.x+shift.x,y:p.y+shift.y}); target.position=p;
          }
        }
        e.style('opacity',0).animate(target, {duration,easing:'ease-out-cubic',queue:false,complete:()=>{
          if(token===generation && !e.removed()) { e.removeStyle('opacity'); rest.delete(e.id()); }
        }});
      });
    }
    function pulse(node) {
      settle();
      if (reduced() || !node?.length) return;
      node.addClass('org-pulse');
      later(()=>node.connectedEdges().addClass('org-pulse'),120);
      later(()=>node.neighborhood('node').addClass('org-pulse'),220);
      later(()=>cy.elements().removeClass('org-pulse'),650);
    }
    const interrupt = () => { cy.stop(true,false); settle(); };
    const container=cy.container();
    container?.addEventListener('wheel',interrupt,{passive:true});
    container?.addEventListener('pointerdown',interrupt,{passive:true,capture:true});
    const hidden=()=>{if(document.hidden) interrupt();};
    if(typeof document!=='undefined') document.addEventListener('visibilitychange',hidden);
    cy.on('destroy',()=>{
      generation++; timers.forEach(clearTimeout); timers.clear(); rest.clear();
      container?.removeEventListener('wheel',interrupt);
      container?.removeEventListener('pointerdown',interrupt,true);
      if(typeof document!=='undefined') document.removeEventListener('visibilitychange',hidden);
    });
    return { begin, drag, end, position, settle, enter, pulse, cancelGrab:()=>{if(gesture) settle();} };
  }
  const api={create,limited};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  if(typeof window!=='undefined') window.PTGraphMotion=api;
})();
