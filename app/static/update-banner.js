/* The quiet "new version" strip on the main page. The backend decides everything (GET /api/update); this only
   shows a name, one button and a close. Closing remembers that version on the backend (origin changes every launch,
   so localStorage would forget). Downloading, checksum and the hand-off to the installer happen in the backend. */
(() => {
'use strict';
function mount(options = {}) {
  const doc = options.document || document;
  const bar = doc.getElementById('updateBar'), label = doc.getElementById('updateLabel');
  const act = doc.getElementById('updateAct'), close = doc.getElementById('updateClose');
  if (!bar || !label || !act || !close) return null;
  const call = options.fetch || ((...args) => fetch(...args));
  const wait = options.wait || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  const quit = options.quit || (() => window.PTPrepareQuit && window.PTPrepareQuit());
  const grace = options.grace ?? 1500;   // if the page is still here this long after asking to quit, the quit was cancelled
  let latest = null, busy = false;
  const post = async (path, body = {}) => {
    const res = await call(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || '请求失败');
    return data;
  };
  const show = (text, button) => {
    label.textContent = text; bar.hidden = false;
    act.hidden = !button; if (button) act.textContent = button;
  };
  async function check() {
    try {
      const res = await call('/api/update');
      const data = await res.json();
      if (res.ok && data.apply_result) {
        show(data.apply_result === 'rollback_failed' ? '更新未完成，旧版本的备份已在访达中显示' : '更新未完成，已在访达中显示下载的文件，请手动替换', null);
      } else if (res.ok && data.available && !data.dismissed) {
        latest = data.latest; bar.title = data.notes || '';
        show(`有新版本 v${latest}`, '更新');
      }
    } catch (error) { /* a failed check stays silent */ }
  }
  async function update() {
    if (busy) return;
    busy = true; act.disabled = true; close.hidden = true;
    show('正在下载…', null);
    try {
      let state = await post('/api/update/download');
      while (state.state === 'downloading') {
        const percent = state.total ? Math.floor(100 * state.received / state.total) : 0;
        show(percent ? `正在下载 ${percent}%` : '正在下载…', null);
        await wait(600);
        state = await (await call('/api/update/download')).json();
      }
      if (state.state !== 'ready') throw new Error(state.message || '下载失败');
      const done = await post('/api/update/apply');
      if (done.mode === 'manual') {
        show('更新已下载，请在访达中用新版本替换旧版本', null);
        close.hidden = false; busy = false; act.disabled = false;
        return;
      }
      show(done.mode === 'installer' ? '应用将关闭以完成安装' : '应用将重启以完成更新', null);
      await quit();   // the page's own quit guard keeps unsaved drafts safe; the helper starts after the app stopped
      await wait(grace);
      // Still running: a draft could not be saved or the dialog was cancelled. Forget the armed update.
      await post('/api/update/cancel').catch(() => {});
      busy = false; act.disabled = false; close.hidden = false;
      show(`有新版本 v${latest}`, '更新');
    } catch (error) {
      busy = false; act.disabled = false; close.hidden = false;
      show(`更新失败：${error.message}`, '重试');
    }
  }
  act.onclick = update;
  close.onclick = async () => {
    bar.hidden = true;
    try { if (latest) await post('/api/update/dismiss', {version: latest}); } catch (error) { /* shown again next time */ }
  };
  check();
  return {check, update};
}
window.PTUpdate = {mount};
})();
