/* Project overview in the style of macOS Mission Control.
   The current page shrinks into a window card, every project is laid out as a window
   thumbnail, and the chosen one zooms back to full screen.
   The four-finger swipe and Ctrl+Up belong to macOS, so it opens with Option+Up,
   a click on the project name, or a trackpad pinch (spread to enter the highlighted project). */
(function () {
  const MRU_KEY = 'pdh-project-mru';
  const MRU_LIMIT = 20;
  const SNAPSHOT_LIMIT = 8;
  const PINCH_STEP = 40;      // accumulated pinch distance that counts as a gesture
  const PINCH_GAP_MS = 250;   // a pause this long starts a new gesture

  // Current project first, then most recently used, then the rest in list order.
  function order(projects, mru, current) {
    const byId = new Map(projects.map(p => [p.id, p]));
    const ids = [current, ...(mru || [])].filter(id => byId.has(id));
    const seen = new Set();
    const out = [];
    for (const id of [...ids, ...projects.map(p => p.id)]) {
      if (!seen.has(id)) { seen.add(id); out.push(byId.get(id)); }
    }
    return out;
  }

  function touch(mru, id) {
    return [id, ...(mru || []).filter(x => x !== id)].slice(0, MRU_LIMIT);
  }

  // Record the project being left as well, so it sits right after the new current one.
  function recordSwitch(mru, from, to) {
    return touch(from ? touch(mru, from) : mru, to);
  }

  /* Lay out n window cards of the given aspect ratio in a W x H area, each with a label
     strip below it. Picks the column count that gives the largest cards, caps a card at
     maxShare of the width so one or two projects do not fill the screen, centres every row. */
  function grid(n, W, H, aspect, gap = 32, label = 30, maxShare = 0.55) {
    let best = { cols: 1, rows: n ? 1 : 0, w: 0 };
    for (let cols = 1; cols <= Math.max(1, n); cols++) {
      const rows = Math.ceil(n / cols);
      const byW = (W - gap * (cols - 1)) / cols;
      const byH = ((H - rows * label - gap * (rows - 1)) / rows) * aspect;
      const w = Math.max(0, Math.min(byW, byH, W * maxShare));
      if (w > best.w + 0.5) best = { cols, rows, w };
    }
    const { cols, rows, w } = best;
    const h = w / aspect;
    const top = (H - (rows * (h + label) + Math.max(0, rows - 1) * gap)) / 2;
    const cards = [];
    for (let i = 0; i < n; i++) {
      const r = Math.floor(i / cols), c = i % cols;
      const inRow = Math.min(cols, n - r * cols);
      const left = (W - (inRow * w + (inRow - 1) * gap)) / 2;
      cards.push({ x: left + c * (w + gap), y: top + r * (h + label + gap), w, h });
    }
    return { cols, rows, label, cards };
  }

  function initial(n, cols = 1) {
    return { open: false, index: 0, n, cols, pinch: 0, pinchAt: null };
  }

  function openState(s) {
    return { ...s, open: true, index: 0, pinch: 0 };
  }

  /* Events: {type:'key', key, alt, ctrl, shift} and {type:'pinch', delta, time}
     (delta < 0 pinches in). Returns {state, handled, effect: 'open' | 'select' | null, index}. */
  function reduce(s, e) {
    const done = (state, effect = null, index = s.index) => ({ state, handled: true, effect, index });
    const select = i => done({ ...s, open: false, pinch: 0 }, 'select', i);
    if (e.type === 'pinch') {
      const sameGesture = e.time == null || s.pinchAt == null || e.time - s.pinchAt <= PINCH_GAP_MS;
      let acc = sameGesture ? s.pinch : 0;
      if (acc && Math.sign(acc) !== Math.sign(e.delta)) acc = 0;
      acc += e.delta;
      const pinchAt = e.time ?? null;
      if (!s.open && acc <= -PINCH_STEP) return done({ ...openState(s), pinchAt }, 'open');
      if (s.open && acc >= PINCH_STEP) return select(s.index);
      return done({ ...s, pinch: acc, pinchAt });
    }
    const ignore = { state: s, handled: false, effect: null, index: s.index };
    if (e.type !== 'key') return ignore;
    // Option+Up toggles; pressed again it returns to the current project, like Mission Control.
    if (e.key === 'ArrowUp' && e.alt && !e.ctrl) return s.open ? select(0) : done(openState(s), 'open');
    if (!s.open) return ignore;
    const cols = Math.max(1, s.cols);
    const to = i => done({ ...s, index: i });
    switch (e.key) {
      case 'ArrowRight': return to(Math.min(s.n - 1, s.index + 1));
      case 'ArrowLeft': return to(Math.max(0, s.index - 1));
      case 'ArrowDown': return to(s.index + cols < s.n ? s.index + cols : s.index);
      case 'ArrowUp': return to(s.index - cols >= 0 ? s.index - cols : s.index);
      case 'Tab': return to(s.n ? (((s.index + (e.shift ? -1 : 1)) % s.n) + s.n) % s.n : 0);
      case 'Enter': case ' ': return select(s.index);
      case 'Escape': return select(0);
      default: return ignore;
    }
  }

  /* While closed, a pinch belongs to the page when it lands on a zoomable area
     (pinchIgnore) or while a full-screen view that zooms by itself is up (pinchBlocked). */
  function pinchIgnored(target, opts, open) {
    if (open) return false;
    if (opts.pinchBlocked && opts.pinchBlocked()) return true;
    return !!(opts.pinchIgnore && target && target.closest && target.closest(opts.pinchIgnore));
  }

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  /* The caption under a project card. The demo project (p.demo) carries a small "演示" tag and cannot be edited. */
  function labelHTML(p, current, canEdit) {
    return `${p.id === current ? '<span class="mc-dot" title="当前项目"></span>' : ''}<span class="mc-name">${esc(p.name)}</span>${p.demo ? '<span class="mc-demo">演示</span>' : ''}${canEdit && !p.demo ? `<button type="button" class="mc-edit" aria-label="管理项目：${esc(p.name)}">管理</button>` : ''}`;
  }
  const editable = el => !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  /* DOM controller.
     opts: {root, button, getProjects(), getCurrent(), onSelect(id) -> Promise, onCreate(),
            pinchIgnore: selector whose own pinch zoom must keep working,
            pinchBlocked(): true while the overview must not open on a pinch at all} */
  function mount(opts) {
    const root = opts.root;
    // After the page in tree order, so ids inside page clones never shadow the live ones.
    document.body.appendChild(root);
    const desk = root.querySelector('.mc-desk');
    const bar = root.querySelector('.mc-bar');
    const stage = root.querySelector('.mc-stage');
    const snapshots = new Map();   // project id -> page clone, kept for this session only
    let state = initial(0);
    let list = [];
    let cards = [];
    let rects = [];
    let busy = false;
    let view = { w: 0, h: 0 };

    const readMRU = () => { try { return JSON.parse(localStorage.getItem(MRU_KEY)) || []; } catch { return []; } };
    const motion = () => (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 0 : 1);
    const EASE = 'cubic-bezier(.2,.86,.24,1)';

    // Clone the visible page into a viewport-sized, inert snapshot.
    function shoot() {
      const vw = view.w, vh = view.h;
      const page = document.createElement('div');
      page.className = 'mc-page';
      page.style.width = `${vw}px`;
      page.style.height = `${vh}px`;
      page.inert = true;
      const flow = document.createElement('div');
      flow.className = 'mc-flow';
      flow.style.transform = `translateY(${-window.scrollY}px)`;
      page.appendChild(flow);
      for (const el of document.body.children) {
        if (el === root || /^(SCRIPT|TEMPLATE|STYLE|LINK)$/.test(el.tagName)) continue;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const pinned = cs.position === 'fixed' || cs.position === 'sticky';
        if (cs.position !== 'fixed') flow.appendChild(copy(el, pinned));
        if (pinned) {
          const r = el.getBoundingClientRect();
          if (r.width && r.height && r.bottom > 0 && r.top < vh) {
            const c = copy(el, false);
            Object.assign(c.style, { position: 'absolute', left: `${r.left}px`, top: `${r.top}px`,
              width: `${r.width}px`, height: `${r.height}px`, margin: '0', transform: 'none' });
            page.appendChild(c);
          }
        }
      }
      page.dataset.w = vw;
      page.dataset.h = vh;
      return page;
    }

    function copy(el, hide) {
      const c = el.cloneNode(true);
      if (hide) c.style.visibility = 'hidden';
      // Radio groups and label targets must not interact with the live page.
      c.querySelectorAll('[name]').forEach(x => x.removeAttribute('name'));
      c.querySelectorAll('iframe, video, audio').forEach(x => x.replaceWith(document.createElement('div')));
      const from = el.querySelectorAll('canvas');
      c.querySelectorAll('canvas').forEach((cv, i) => { try { cv.getContext('2d').drawImage(from[i], 0, 0); } catch { /* tainted or webgl */ } });
      return c;
    }

    // A page-shaped placeholder for projects not opened in this session.
    function placeholder(p) {
      const page = document.createElement('div');
      page.className = 'mc-page mc-ph';
      page.style.width = `${view.w}px`;
      page.style.height = `${view.h}px`;
      const chips = (p.keywords || []).slice(0, 6).map(k => `<span>${esc(k)}</span>`).join('');
      page.innerHTML = `
        <div class="mc-ph-top"><img src="/brand-mark.svg" alt=""><b>Paper<em>Dig</em>Helper</b><span class="mc-ph-pill">${esc(p.name)}</span></div>
        <div class="mc-ph-body">
          <h1>${esc(p.name)}</h1>
          <div class="mc-ph-chips">${chips}</div>
          <div class="mc-ph-grid">${'<div><i></i><i></i><i></i></div>'.repeat(6)}</div>
        </div>`;
      page.dataset.w = view.w;
      page.dataset.h = view.h;
      return page;
    }

    function fullScreen(r) {
      return `translate(${-r.x}px, ${-r.y}px) scale(${view.w / r.w}, ${view.h / r.h})`;
    }

    function highlight() {
      cards.forEach((c, i) => c.setAttribute('aria-selected', String(i === state.index)));
    }

    function build() {
      view = { w: document.documentElement.clientWidth, h: window.innerHeight };
      const current = opts.getCurrent();
      list = order(opts.getProjects(), readMRU(), current);
      const barH = bar.offsetHeight || 64;
      const pad = Math.max(40, view.w * 0.05);
      const area = { x: pad, y: barH + 12, w: view.w - pad * 2, h: view.h - barH - 12 - 36 };
      const g = grid(list.length, area.w, area.h, view.w / view.h);
      rects = g.cards.map(r => ({ ...r, x: r.x + area.x, y: r.y + area.y }));
      stage.innerHTML = '';
      cards = list.map((p, i) => {
        const r = rects[i];
        const card = document.createElement('div');
        card.className = 'mc-card';
        card.setAttribute('role', 'option');
        card.dataset.index = i;
        Object.assign(card.style, { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px` });
        const win = document.createElement('div');
        win.className = 'mc-window';
        Object.assign(win.style, { width: `${r.w}px`, height: `${r.h}px` });
        const page = i === 0 && p.id === current ? shoot() : (snapshots.get(p.id) || placeholder(p));
        const scaler = document.createElement('div');
        scaler.className = 'mc-scale';
        scaler.style.transform = `scale(${r.w / Number(page.dataset.w || view.w)})`;
        scaler.appendChild(page);
        win.appendChild(scaler);
        const label = document.createElement('div');
        label.className = 'mc-label';
        label.innerHTML = labelHTML(p, current, !!opts.onEdit);
        card.append(win, label);
        stage.appendChild(card);
        return card;
      });
      return g;
    }

    async function show() {
      if (busy) return;
      busy = true;
      root.hidden = false;
      root.style.opacity = '';
      const g = build();
      state = openState(initial(list.length, g.cols));
      highlight();
      document.documentElement.classList.add('mc-open');
      const m = motion();
      const runs = [
        desk.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 380 * m, easing: 'ease-out' }),
        bar.animate([{ opacity: 0, transform: 'translateY(-14px)' }, { opacity: 1, transform: 'none' }],
          { duration: 320 * m, delay: 120 * m, easing: EASE, fill: 'backwards' }),
      ];
      cards.forEach((card, i) => {
        if (i === 0 && list[0]?.id === opts.getCurrent()) {
          card.classList.add('front');
          runs.push(card.querySelector('.mc-window').animate(
            [{ transform: fullScreen(rects[0]), borderRadius: '0px' }, { transform: 'none', borderRadius: '10px' }],
            { duration: 460 * m, easing: EASE }));
          runs.push(card.querySelector('.mc-label').animate([{ opacity: 0 }, { opacity: 1 }],
            { duration: 200 * m, delay: 300 * m, fill: 'backwards' }));
        } else {
          runs.push(card.animate([{ opacity: 0, transform: 'scale(.86)' }, { opacity: 1, transform: 'none' }],
            { duration: 380 * m, delay: (110 + i * 30) * m, easing: EASE, fill: 'backwards' }));
        }
      });
      await Promise.all(runs.map(a => a.finished.catch(() => {})));
      cards[0]?.classList.remove('front');
      busy = false;
    }

    async function select(i) {
      busy = true;
      const current = opts.getCurrent();
      const p = list[i];
      const target = cards[i];
      const switching = !!p && p.id !== current;
      let loading = Promise.resolve();
      if (switching) {
        const shot = cards[0]?.querySelector('.mc-page');
        if (shot && list[0].id === current) {
          snapshots.delete(current);
          snapshots.set(current, shot);
          while (snapshots.size > SNAPSHOT_LIMIT) snapshots.delete(snapshots.keys().next().value);
        }
        snapshots.delete(p.id);
        localStorage.setItem(MRU_KEY, JSON.stringify(recordSwitch(readMRU(), current, p.id)));
        loading = Promise.resolve(opts.onSelect(p.id)).catch(() => {});
      }
      const m = motion();
      const runs = [
        desk.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 380 * m, easing: 'ease-in', fill: 'forwards' }),
        bar.animate([{ opacity: 1 }, { opacity: 0, transform: 'translateY(-14px)' }], { duration: 220 * m, fill: 'forwards' }),
      ];
      cards.forEach((card, j) => {
        if (j === i) return;
        runs.push(card.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(.9)' }],
          { duration: 260 * m, easing: 'ease-in', fill: 'forwards' }));
      });
      if (target) {
        target.classList.add('front');
        target.setAttribute('aria-selected', 'false');
        runs.push(target.querySelector('.mc-label').animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140 * m, fill: 'forwards' }));
        runs.push(target.querySelector('.mc-window').animate(
          [{ transform: 'none', borderRadius: '10px' }, { transform: fullScreen(rects[i]), borderRadius: '0px' }],
          { duration: 440 * m, easing: EASE, fill: 'forwards' }));
      }
      await Promise.all(runs.map(a => a.finished.catch(() => {})));
      if (switching) {
        // The snapshot may be stale or a placeholder; dissolve it into the freshly loaded page.
        await Promise.race([loading, sleep(900)]);
        await root.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220 * m, easing: 'ease-out', fill: 'forwards' })
          .finished.catch(() => {});
      }
      close();
    }

    function close() {
      root.hidden = true;
      root.getAnimations({ subtree: true }).forEach(a => a.cancel());
      stage.innerHTML = '';
      cards = [];
      state = { ...state, open: false };
      document.documentElement.classList.remove('mc-open');
      busy = false;
      if (opts.button && root.contains(document.activeElement)) opts.button.focus();
    }

    function dispatch(e, native) {
      if (busy) {
        if (native && (state.open || e.type === 'pinch')) native.preventDefault();
        return;
      }
      if (!state.open && e.type === 'key' && editable(document.activeElement)) return;
      // Enter or Space on the focused "manage" button activates that button, not the highlighted card.
      if (state.open && e.type === 'key' && (e.key === 'Enter' || e.key === ' ') && document.activeElement?.classList?.contains('mc-edit')) return;
      const r = reduce(state, e);
      if (!r.handled) return;
      if (native) { native.preventDefault(); native.stopImmediatePropagation(); }
      if (r.effect === 'open') { show(); return; }
      state = r.state;
      if (r.effect === 'select') select(r.index);
      else if (state.open) highlight();
    }

    window.addEventListener('keydown', ev => dispatch(
      { type: 'key', key: ev.key, alt: ev.altKey, ctrl: ev.ctrlKey || ev.metaKey, shift: ev.shiftKey }, ev), true);

    const ignored = ev => pinchIgnored(ev.target, opts, state.open);
    const hasGestures = typeof window.GestureEvent !== 'undefined';
    // Trackpad pinch arrives as ctrl+wheel in Chromium and as gesture events in WebKit.
    window.addEventListener('wheel', ev => {
      if (!ev.ctrlKey) { if (root.contains(ev.target)) ev.preventDefault(); return; }
      if (ignored(ev)) return;
      ev.preventDefault();
      if (!hasGestures) dispatch({ type: 'pinch', delta: -ev.deltaY, time: ev.timeStamp }, null);
    }, { passive: false, capture: true });
    let lastScale = 1;
    window.addEventListener('gesturestart', ev => { if (ignored(ev)) return; ev.preventDefault(); lastScale = 1; }, { passive: false });
    window.addEventListener('gesturechange', ev => {
      if (ignored(ev)) return;
      ev.preventDefault();
      const delta = (ev.scale - lastScale) * 160;
      lastScale = ev.scale;
      dispatch({ type: 'pinch', delta, time: ev.timeStamp }, null);
    }, { passive: false });

    stage.addEventListener('pointermove', ev => {
      const card = ev.target.closest('.mc-card');
      if (!card || !state.open || busy) return;
      const i = Number(card.dataset.index);
      if (i !== state.index) { state = { ...state, index: i }; highlight(); }
    });
    root.addEventListener('click', ev => {
      if (!state.open || busy) return;
      if (ev.target.closest('.mc-add')) { state = { ...state, open: false }; close(); opts.onCreate(); return; }
      if (ev.target.closest('.mc-bar')) return;
      const edit = ev.target.closest('.mc-edit');
      if (edit && opts.onEdit) {
        const chosen = list[Number(edit.closest('.mc-card').dataset.index)];
        state = { ...state, open: false };
        close();
        if (chosen) opts.onEdit(chosen);
        return;
      }
      const card = ev.target.closest('.mc-card');
      state = { ...state, open: false };
      select(card ? Number(card.dataset.index) : 0);
    });
    if (opts.button) opts.button.addEventListener('click', () => { if (!state.open) show(); });

    return {
      open: show,
      get state() { return state; },
    };
  }

  const api = { order, labelHTML, touch, recordSwitch, grid, initial, openState, reduce, pinchIgnored, mount };
  window.ProjectSwitcher = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
