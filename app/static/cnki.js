// 知网 (CNKI) from the desktop app's own CNKI window (ADR 0045). The shell searches CNKI in a hidden window; this helper starts
// a job there, polls it once a second and hands each batch of items to the caller, which posts them to the server (the server
// validates every field). Only the desktop app has the window: in a browser `available()` is false and nothing is asked.
(() => {
  const tauri = () => window.__TAURI_INTERNALS__;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  // One short status per way a run can end; only these words are shown, whatever came back.
  const PROBLEMS = {
    verification_needed: '知网：等待验证超时，这次跳过了',
    network_error: '知网：无法连接',
    busy: '知网：正在进行另一项检索',
    unavailable: '知网：暂时不可用',
  };

  // Polls the running job until it ends. onItems(batch) is awaited for every batch; onVerification(true|false) fires when the
  // window asks the person to slide CNKI's puzzle and when that is over; onProgress(poll) after every poll.
  async function follow({onItems, onVerification, onProgress, limitMs = 50 * 60 * 1000} = {}) {
    let asking = false, problem = null;
    const end = Date.now() + limitMs;
    const stop = async () => { try { await tauri().invoke('cnki_cancel'); } catch (e) { /* the shell ends it at its own limit */ } };
    while (Date.now() < end) {
      let poll;
      try { poll = await tauri().invoke('cnki_poll'); } catch (e) { return 'unavailable'; }
      // A batch the server refuses (e.g. 知网 was just switched off) ends the run: CNKI is not searched any further.
      if (poll.items?.length && onItems) {
        try { await onItems(poll.items); } catch (e) { await stop(); return 'unavailable'; }
      }
      const waiting = poll.state === 'verification';
      if (waiting !== asking) { asking = waiting; onVerification?.(waiting); }
      onProgress?.(poll);
      if (poll.state === 'done') return null;
      if (poll.state === 'failed') return poll.problem || 'unavailable';
      if (poll.state === 'idle') return problem;
      await sleep(1000);
    }
    await stop();
    return 'unavailable';
  }

  // Starts a job (mode refresh | guidance | seed | detail) and follows it. Returns the problem kind, or null when it finished.
  async function run(job, handlers = {}) {
    if (!tauri()) return 'desktop_only';
    try { await tauri().invoke('cnki_start', {job}); }
    catch (e) { return /busy/i.test(String(e)) ? 'busy' : 'unavailable'; }
    return follow(handlers);
  }

  // The job the shell holds now, if any (state, tag, mode, pending items), without taking anything from it.
  async function current() {
    if (!tauri()) return null;
    try {
      const poll = await tauri().invoke('cnki_poll', {peek: true});
      return poll.state === 'idle' ? null : poll;
    } catch (e) { return null; }
  }

  async function cancel() {
    if (!tauri()) return;
    try { await tauri().invoke('cnki_cancel'); } catch (e) { /* nothing running */ }
  }

  window.PTCnki = {
    available: () => !!tauri(),
    run, follow, current, cancel,
    problemText: (kind) => (kind ? PROBLEMS[kind] || PROBLEMS.unavailable : ''),
  };
})();
