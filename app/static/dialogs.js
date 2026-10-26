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
  // A confirm has 取消 / 确认; a choice lists its own buttons (the last one is the suggested one) and answers with its value.
  const buttons = (request.buttons || [{label: '取消', value: false}, {label: '确认', value: true}]).map((spec, index, all) => {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = text(spec.label);
    if (index === all.length - 1) button.className = 'primary';
    button.onclick = () => finish(spec.value);
    return button;
  });
  const cancel = buttons[0], approve = buttons[buttons.length - 1];
  actions.append(...buttons); dialog.append(title, message, actions);
  let finished = false;
  const finish = accepted => {
    if (finished) return;
    finished = true;
    const result = request.buttons ? (valid(request) ? accepted : request.dismissed) : accepted === true && valid(request);
    if (dialog.open) dialog.close();
    dialog.remove(); current = null;
    if (previous?.isConnected && !previous.inert && !previous.disabled) previous.focus();
    request.resolve(result); next();
  };
  current = dialog;
  const dismiss = () => finish(request.buttons ? request.dismissed : false);
  dialog.addEventListener('cancel', event => { event.preventDefault(); dismiss(); });
  dialog.addEventListener('close', dismiss);
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); dismiss(); }
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
// buttons: [{label, value}], left to right; Escape or closing answers `dismissed` (null unless given).
function choose(message, buttons, options = {}) {
  return new Promise(resolve => { queue.push({message, buttons, dismissed: options.dismissed ?? null, options, resolve}); next(); });
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
window.PTDialogs = {confirm, choose, notice, active: () => !!current};
})();
