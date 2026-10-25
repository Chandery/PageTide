/* The local settings file is authoritative across desktop origins/restarts. */
(function(global){
'use strict';
const modes=new Set(['light','dark','auto']);
function apply(mode){
  const value=modes.has(mode)?mode:'auto';
  document.documentElement.dataset.mode=value==='auto'?(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'):value;
  if(value==='auto')localStorage.removeItem('pt-mode');else localStorage.setItem('pt-mode',value);
  global.dispatchEvent?.(new CustomEvent('pt-mode',{detail:document.documentElement.dataset.mode}));
  return value;
}
let selected='auto';
apply(localStorage.getItem('pt-mode')||'auto');
const ready=fetch('/api/user_settings').then(r=>{if(!r.ok)throw new Error('Theme settings unavailable');return r.json();}).then(data=>{selected=apply(data.settings?.theme||'auto');return selected;}).catch(()=>selected);
async function set(mode){
  if(!modes.has(mode))throw new Error('Invalid theme');
  await ready;
  const res=await fetch('/api/user_settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({settings:{theme:mode},merge:true})});
  const data=await res.json();if(!res.ok)throw new Error(data.error||'Theme save failed');
  selected=apply(mode);return selected;
}
const media=matchMedia('(prefers-color-scheme:dark)');
media.addEventListener?.('change',()=>{if(selected==='auto')apply('auto');});
global.PTTheme={ready,apply,set};

// Scrollbars (theme.css): a region shows its bar while it scrolls (a wheel, a key or a drag of the bar) or while the
// pointer is at its edge, and hides it 3 s after the last of these.
const SCROLL_IDLE=3000, EDGE=14, timers=new WeakMap();
function reveal(el){
  el.classList.add('pt-scrolling');
  clearTimeout(timers.get(el));
  timers.set(el,setTimeout(()=>el.classList.remove('pt-scrolling'),SCROLL_IDLE));
}
const scrolls=el=>el.scrollHeight>el.clientHeight+1&&/(auto|scroll)/.test(getComputedStyle(el).overflowY);
document.addEventListener?.('scroll',e=>{
  const el=e.target===document?document.documentElement:e.target;
  if(el instanceof Element)reveal(el);
},{capture:true,passive:true});
let pending=null;
document.addEventListener?.('pointermove',e=>{
  if(pending)return;
  pending=requestAnimationFrame(()=>{
    pending=null;
    const root=document.documentElement;
    if(innerWidth-e.clientX<=EDGE&&root.scrollHeight>root.clientHeight){reveal(root);return;}
    for(let el=e.target instanceof Element?e.target:null;el&&el!==root&&el!==document.body;el=el.parentElement){
      if(!scrolls(el))continue;
      if(el.getBoundingClientRect().right-e.clientX<=EDGE)reveal(el);
      return;
    }
  });
},{passive:true});
})(window);
