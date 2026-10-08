/* The local settings file is authoritative across desktop origins/restarts. */
(function(global){
'use strict';
const modes=new Set(['light','dark','auto']);
function apply(mode){
  const value=modes.has(mode)?mode:'auto';
  document.documentElement.dataset.mode=value==='auto'?(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'):value;
  if(value==='auto')localStorage.removeItem('pdh-mode');else localStorage.setItem('pdh-mode',value);
  global.dispatchEvent?.(new CustomEvent('pdh-mode',{detail:document.documentElement.dataset.mode}));
  return value;
}
let selected='auto';
apply(localStorage.getItem('pdh-mode')||'auto');
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
global.PDHTheme={ready,apply,set};
})(window);
