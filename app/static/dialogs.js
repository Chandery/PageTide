/* Native webviews do not guarantee alert/confirm support. Decisions stay in DOM,
   remain cancellable, and validate their original scope before approval. */
(() => {
'use strict';
const queue = [];
let current = null, noticeNode = null, sequence = 0;
const text = value => window.PTi18n?.translate(String(value ?? '')) || String(value ?? '');
const valid = request => { try { return !request.options.valid || request.options.valid(); } catch { return false; } };
function next() {
  if (current) return;
  const request = queue.shift();
  if (!request) return;
  if (!valid(request)) { request.resolve(false); next(); return; }
  const previous = document.activeElement;
  const dialog = document.createElement('dialog');
  dialog.className = 'pt-confirm';
  const title = document.createElement('h2'), message = document.createElement('p'), actions = document.createElement('div');
  title.id = 'pt-confirm-title-' + (++sequence); title.textContent = text('请确认');
  message.id = 'pt-confirm-message-' + sequence; message.textContent = text(request.message);
  dialog.setAttribute('aria-labelledby', title.id); dialog.setAttribute('aria-describedby', message.id);
  actions.className = 'pt-confirm-actions';
  const cancel = document.createElement('button'), approve = document.createElement('button');
  cancel.type = approve.type = 'button'; cancel.textContent = text('取消'); approve.textContent = text('确认');
  approve.className = 'primary'; actions.append(cancel, approve); dialog.append(title, message, actions);
  let finished = false;
  const finish = accepted => {
    if (finished) return;
    finished = true;
    const result = accepted === true && valid(request);
    if (dialog.open) dialog.close();
    dialog.remove(); current = null;
    if (previous?.isConnected && !previous.inert && !previous.disabled) previous.focus();
    request.resolve(result); next();
  };
  current = dialog;
  cancel.onclick = () => finish(false); approve.onclick = () => finish(true);
  dialog.addEventListener('cancel', event => { event.preventDefault(); finish(false); });
  dialog.addEventListener('close', () => finish(false));
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); finish(false); }
    else if (event.key === 'Tab') {
      const outside = !dialog.contains(document.activeElement);
      if ((event.shiftKey && (document.activeElement === cancel || outside)) || (!event.shiftKey && (document.activeElement === approve || outside))) {
        event.preventDefault(); (event.shiftKey ? approve : cancel).focus();
      }
    }
  });
  document.body.append(dialog);
  try { dialog.showModal(); cancel.focus(); } catch { finish(false); }
}
function confirm(message, options = {}) {
  return new Promise(resolve => { queue.push({message, options, resolve}); next(); });
}
function notice(message, options = {}) {
  let node = options.target;
  if (!node) {
    if (!noticeNode?.isConnected) { noticeNode = document.createElement('div'); noticeNode.className = 'pt-notice'; document.body.append(noticeNode); }
    node = noticeNode;
  }
  node.setAttribute('role', options.kind === 'error' ? 'alert' : 'status');
  node.setAttribute('aria-live', options.kind === 'error' ? 'assertive' : 'polite');
  node.setAttribute('aria-atomic', 'true'); node.dataset.kind = options.kind || 'info';
  node.textContent = text(message); node.hidden = false;
  return node;
}
window.PTDialogs = {confirm, notice, active: () => !!current};
})();
