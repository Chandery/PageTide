/* Explicit exit choices for creation-only drafts. Never create a project,
   confirm an AI proposal, or erase a persisted guidance draft at quit. */
(() => {
'use strict';
function mount(options) {
  const $ = selector => document.querySelector(selector);
  const dialog=$('#creationQuitDialog'), cancel=$('#creationQuitCancel'), review=$('#creationQuitReview'), discard=$('#creationQuitDiscard');
  const buttons=[cancel,review,discard];
  let completing=false, leaving=false, previous=null;
  const busy=()=>!!options.busy(), dirty=()=>!!options.dirty();
  const notice=(message,kind='error')=>window.PTDialogs.notice(message,{target:$(dialog.open?'#creationQuitError':'#creationQuitStatus'),kind});
  const close=restore=>{dialog.close();if(restore && previous?.isConnected && !previous.inert && !previous.disabled)previous.focus();};
  async function complete() {
    if(completing)return;
    if(busy()){notice('当前操作还没结束，请等完成后再退出。');return;}
    completing=true;leaving=true;buttons.forEach(button=>button.disabled=true);
    try { await window.__TAURI_INTERNALS__.invoke('complete_quit'); }
    catch(error) {
      completing=false;leaving=false;buttons.forEach(button=>button.disabled=false);
      notice(`退出未完成，草稿和输入保持不变：${error.message}`);
    }
  }
  window.PTPrepareQuit=async()=>{
    if(completing)return;
    if(busy()){notice('当前操作还没结束，请等完成后再退出。');return;}
    if(!dirty()){await complete();return;}
    if(!dialog.open) {previous=document.activeElement;dialog.showModal();}
    cancel.focus();
  };
  cancel.onclick=()=>{if(!completing)close(true);};
  review.onclick=()=>{if(completing)return;close(false);options.focus();};
  discard.onclick=complete;
  dialog.addEventListener('cancel',event=>{event.preventDefault();if(!completing)close(true);});
  dialog.addEventListener('keydown',event=>{
    if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();if(!completing)close(true);}
    else if(event.key==='Tab') {
      const outside=!dialog.contains(document.activeElement);
      if((event.shiftKey && (document.activeElement===cancel || outside)) || (!event.shiftKey && (document.activeElement===discard || outside))) {
        event.preventDefault();(event.shiftKey?discard:cancel).focus();
      }
    }
  });
  window.addEventListener('beforeunload',event=>{
    if(!leaving && !options.leaving?.() && (dirty() || busy())) {event.preventDefault();event.returnValue='';}
  });
}
window.PTCreationQuit={mount};
})();
