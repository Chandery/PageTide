/* First-run guided tour (PDHTour). UMD: the pure layer (STEPS, shouldOffer, next, stepsFor,
   finishTarget, state serialisation) is Node-testable; the DOM layer (boot/begin/finish/skip)
   draws a spotlight and a small bubble. Chinese UI text lives here; i18n.js translates it. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PDHTour = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const KEY = 'pdh-tour';
  const OFFERED_KEY = 'pdh-tour-offered';
  const VERSION = 1;
  const WAIT_MS = 15000;
  const DEMO_ID = 'pdh-demo';
  const PAGE_URL = {
    index: '/',
    settings: '/settings.html',
    weekly: '/weekly_report.html?project_id=' + DEMO_ID,
    creation: '/project_creation.html',
  };

  /* Four phases, in this order. A step: id, page, phase, text, advance ('next' | 'click'),
     target (CSS selector, null = centred bubble), closest (optional ancestor to highlight),
     ready (optional selector to wait for before showing; defaults to target), view (index tab to
     show first), primary / secondary ({label, choice}), skipTo (step for choice 'skip'), end. */
  const STEPS = [
    // The welcome card: the person's language is unknown, so it is bilingual and has no spotlight target.
    // Its look and wording live in renderWelcome(); text/phase here are the Chinese defaults.
    { id: 'w0', page: 'index', phase: '开始', target: null, advance: 'next', welcome: true,
      text: '欢迎使用 PageTide',
      primary: { label: '开始', choice: 'primary' } },
    { id: 'p1', page: 'index', phase: '项目', target: '#projectBtn', advance: 'next',
      text: '这是项目。点它切换项目，或用 ＋ 新建。现在打开的是演示项目。',
      primary: { label: '下一步', choice: 'primary' } },
    { id: 'p2', page: 'index', phase: '项目', target: '#projectEdit', advance: 'next',
      text: '关键词、论文语言在「管理项目」里改。',
      primary: { label: '下一步', choice: 'primary' } },
    { id: 's1', page: 'index', phase: '设置', target: '#settingsBtn', advance: 'next',
      text: 'AI 和论文来源在设置里配置。',
      primary: { label: '去设置', choice: 'primary' },
      secondary: { label: '跳过这段', choice: 'skip' }, skipTo: 'r1' },
    { id: 's2', page: 'settings', phase: '设置', target: '#apiKey', closest: '.section', advance: 'next',
      text: '填 DeepSeek 密钥后可用 AI 速览和提问。',
      primary: { label: '下一步', choice: 'primary' } },
    { id: 's3', page: 'settings', phase: '设置', target: '#openalexKey', closest: '.source-row', advance: 'next',
      text: '期刊与会议论文来自 OpenAlex，密钥可选。',
      primary: { label: '下一步', choice: 'primary' } },
    { id: 's4', page: 'settings', phase: '设置', target: '#baiduScholarKey', closest: '.source-row', advance: 'next',
      text: '中文论文可打开百度学术，需要千帆密钥。',
      primary: { label: '回到演示', choice: 'primary' } },
    { id: 'r1', page: 'index', phase: '推荐', target: '#btnDaily', advance: 'click', view: 'today',
      text: '点这里生成今天的推荐。' },
    { id: 'r2', page: 'index', phase: '推荐', target: '#cards .card:first-child .ai-line', advance: 'next', view: 'today',
      text: '这是 AI 速览：一句话讲清论文和它与你的关系。演示里的速览是预先写好的。',
      primary: { label: '下一步', choice: 'primary' } },
    { id: 'f1', page: 'index', phase: '推荐', target: '#cards .card:first-child [data-fb="useful"]', advance: 'click', view: 'today',
      text: '觉得有用就收藏。画像只从你明确的操作里学习。' },
    { id: 'f2', page: 'index', phase: '论文库与画像', target: '.tab[data-view="library"]', advance: 'click',
      text: '收藏的论文在论文库里。' },
    { id: 'f3', page: 'index', phase: '论文库与画像', target: '#organizationRoot .org-list', advance: 'next', view: 'library',
      ready: '#organizationRoot .org-list .org-paper',
      text: '列表里是收藏的论文。',
      primary: { label: '下一步', choice: 'primary' } },
    { id: 'f4', page: 'index', phase: '论文库与画像', target: '#organizationRoot .org-tabs [data-action="graph"]', advance: 'click', view: 'library',
      text: '切到图谱，看论文之间的关系。' },
    { id: 'f5', page: 'index', phase: '论文库与画像', target: '.tab[data-view="profile"]', advance: 'click',
      text: '画像里是从收藏和反馈学到的兴趣词。' },
    { id: 'f6', page: 'index', phase: '论文库与画像', target: '#view-profile a.pd-link[href*="weekly_report"]', advance: 'click', view: 'profile',
      text: '周报在这里，按周看画像的变化。' },
    { id: 'f7', page: 'weekly', phase: '论文库与画像', target: '#weeklyContent', advance: 'next',
      ready: '#weeklyContent > :not(.profile-empty)',
      text: '这周的收藏和反馈都汇总在这里。',
      primary: { label: '完成', choice: 'primary' }, end: true },
    // Shown on the creation page after the tour when there is no real project yet.
    { id: 'c1', page: 'creation', phase: '项目', target: '.modes', advance: 'next', standalone: true,
      text: '从这里创建你的第一个项目。',
      primary: { label: '知道了', choice: 'primary' }, end: true },
  ];
  const BY_ID = {};
  STEPS.forEach(function (s) { BY_ID[s.id] = s; });
  const SKIP_LABEL = '跳过指引';
  const FALLBACK_LABEL = '下一步';

  /* ---------- pure layer ---------- */

  function stepsFor(page) { return STEPS.filter(function (s) { return s.page === page; }); }

  /* ob: the /api/onboarding body. A boolean `show` wins; otherwise it is derived from
     no project (project_count === 0 / has_project === false) or seen_version !== version. */
  function shouldOffer(ob, offeredVersion) {
    if (!ob || typeof ob !== 'object') return false;
    const version = ob.version == null ? '' : String(ob.version);
    let show;
    if (typeof ob.show === 'boolean') show = ob.show;
    else {
      const noProject = ob.has_project === false || ob.project_count === 0;
      show = noProject || (ob.seen_version == null ? '' : String(ob.seen_version)) !== version;
    }
    if (!show) return false;
    return offeredVersion == null || String(offeredVersion) !== version;
  }

  /* Next step id, or 'finish'. choice: 'primary' (default) | 'skip' (the optional "skip this part"). */
  function next(state, stepId, choice) {
    const i = STEPS.findIndex(function (s) { return s.id === stepId; });
    if (i < 0) return 'finish';
    const s = STEPS[i];
    if (choice === 'skip' && s.skipTo) return s.skipTo;
    if (s.end || i + 1 >= STEPS.length || STEPS[i + 1].standalone) return 'finish';
    return STEPS[i + 1].id;
  }

  /* Where the tour ends. No real project: the creation page, with the c1 hint there. */
  function finishTarget(hasRealProject) {
    return hasRealProject ? { url: PAGE_URL.index, step: null } : { url: PAGE_URL.creation, step: 'c1' };
  }

  /* Welcome card wording, one table per interface language. Each card shows only the chosen language; the two
     group labels are always bilingual so a reader of either language can find them. */
  const WELCOME_GROUPS = { lang: '语言 / Language', mode: '外观 / Appearance' };
  const WELCOME = {
    'zh-CN': { title: '欢迎使用 PageTide', light: '浅色', dark: '深色', auto: '跟随系统', start: '开始', skip: '跳过指引' },
    'en-US': { title: 'Welcome to PageTide', light: 'Light', dark: 'Dark', auto: 'System', start: 'Start', skip: 'Skip tour' },
  };
  const THEME_MODES = ['light', 'dark', 'auto'];
  /* The saved interface language wins; without one the browser language decides (zh* -> Chinese, else English). */
  function welcomeLang(saved, navigatorLanguage) {
    if (saved === 'zh-CN' || saved === 'en-US') return saved;
    return /^zh/i.test(String(navigatorLanguage || '')) ? 'zh-CN' : 'en-US';
  }
  /* Save the two choices through io = {saveLanguage(lang), saveTheme(mode)}. Both are always tried; returns the
     first error or null. Used by Start and by Skip alike: a person who skipped has still chosen. */
  async function saveChoice(choice, io) {
    let failure = null;
    try { await io.saveLanguage(choice.lang); } catch (e) { failure = e; }
    try { await io.saveTheme(choice.mode); } catch (e) { failure = failure || e; }
    return failure;
  }

  /* The page was opened while the stored step belongs to another page (a reload on the main page during the settings
     steps, a closed weekly report): the demo is still on, so say so and offer to go on. Returns a step-like object
     (never stored) or null. The creation hint is not demo mode and is left alone. */
  function strandedStep(state, page) {
    const st = state && BY_ID[state.step];
    if (!st || st.page === page || st.id === 'c1' || page !== 'index') return null;
    return { id: '__resume', resume: PAGE_URL[st.page] || '/', page: page, phase: st.phase, target: null, advance: 'next',
      text: '指引还没有走完。', primary: { label: '继续', choice: 'resume' } };
  }

  function serialize(state) {
    return JSON.stringify({ v: VERSION, step: state.step, version: state.version == null ? null : state.version,
      returnProject: state.returnProject == null ? null : state.returnProject });
  }
  function parse(text) {
    if (!text) return null;
    let o;
    try { o = JSON.parse(text); } catch (e) { return null; }
    if (!o || o.v !== VERSION || !BY_ID[o.step]) return null;
    return { v: VERSION, step: o.step, version: o.version == null ? null : o.version,
      returnProject: o.returnProject == null ? null : o.returnProject };
  }

  let storage = null;
  function store() {
    if (storage) return storage;
    try { return typeof sessionStorage !== 'undefined' ? sessionStorage : null; } catch (e) { return null; }
  }
  function setStorage(s) { storage = s; }
  function pending() { const s = store(); return s ? parse(s.getItem(KEY)) : null; }
  /* The tour is running (demo mode). The c1 hint is not demo mode, so it is not "current". */
  function current() { const s = pending(); return s && s.step !== 'c1' ? s : null; }
  function writeState(state) {
    const s = store();
    if (s) s.setItem(KEY, serialize({ step: state.step, version: state.version, returnProject: state.returnProject }));
  }
  function clearState() { const s = store(); if (s) s.removeItem(KEY); }

  /* ---------- DOM layer ---------- */

  let ctx = null;   // {page, hooks, token, step, ui, el, active, raf, ...}
  let finishing = false;

  function reduced() {
    try { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (e) { return false; }
  }
  function visible(el) {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && el.getClientRects().length > 0;
  }
  function pick(sel, closest) {
    let q = document.querySelector(sel);
    if (q && closest) q = q.closest(closest) || q;
    return visible(q) ? q : null;
  }

  /* Resolves with the first visible match of `selector`, or null after `ms`. */
  function waitFor(selector, ms, closest) {
    return new Promise(function (resolve) {
      let done = false, mo = null, timer = null, poll = null;
      function end(v) {
        if (done) return;
        done = true;
        if (mo) mo.disconnect();
        clearTimeout(timer); clearInterval(poll);
        resolve(v);
      }
      function check() { const q = pick(selector, closest); if (q) end(q); }
      check();
      if (done) return;
      mo = new MutationObserver(check);
      mo.observe(document.documentElement, { childList: true, subtree: true, attributes: true,
        attributeFilter: ['class', 'hidden', 'style', 'open'] });
      poll = setInterval(check, 300);   // layout-only changes do not mutate the DOM
      timer = setTimeout(function () { end(null); }, ms == null ? WAIT_MS : ms);
    });
  }

  function mk(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function buildUI() {
    const rootEl = mk('div', 'pdh-tour');
    rootEl.setAttribute('data-pdh-tour', '');
    const blocks = {};
    ['t', 'b', 'l', 'r', 'h'].forEach(function (k) {
      blocks[k] = mk('div', 'pdh-tour-block pdh-tour-block-' + k);
      rootEl.appendChild(blocks[k]);
    });
    const hole = mk('div', 'pdh-tour-hole');
    rootEl.appendChild(hole);
    document.body.appendChild(rootEl);
    return { root: rootEl, blocks: blocks, hole: hole, bubble: null };
  }

  function setBox(e, x, y, w, h) {
    e.style.display = (w <= 0 || h <= 0) ? 'none' : 'block';
    e.style.left = x + 'px'; e.style.top = y + 'px'; e.style.width = Math.max(0, w) + 'px'; e.style.height = Math.max(0, h) + 'px';
  }

  /* Spotlight + blockers. rect null = centred bubble over a plain dim layer. Blockers swallow clicks
     everywhere except the hole; a "next" step also blocks the hole so the page cannot be used mid-step. */
  function layout(rect, blockHole) {
    const ui = ctx.ui, vw = window.innerWidth, vh = window.innerHeight, b = ui.blocks;
    if (!rect) {
      ui.hole.style.display = 'none';
      setBox(b.t, 0, 0, vw, vh); b.t.classList.add('pdh-tour-dim');
      ['b', 'l', 'r', 'h'].forEach(function (k) { b[k].style.display = 'none'; });
      return null;
    }
    b.t.classList.remove('pdh-tour-dim');
    const pad = 6;
    const x1 = Math.max(0, rect.left - pad), y1 = Math.max(0, rect.top - pad);
    const x2 = Math.min(vw, rect.right + pad), y2 = Math.min(vh, rect.bottom + pad);
    const hb = { left: x1, top: y1, right: x2, bottom: y2, width: x2 - x1, height: y2 - y1 };
    setBox(ui.hole, hb.left, hb.top, hb.width, hb.height);
    setBox(b.t, 0, 0, vw, hb.top);
    setBox(b.b, 0, hb.bottom, vw, vh - hb.bottom);
    setBox(b.l, 0, hb.top, hb.left, hb.height);
    setBox(b.r, hb.right, hb.top, vw - hb.right, hb.height);
    if (blockHole) setBox(b.h, hb.left, hb.top, hb.width, hb.height); else b.h.style.display = 'none';
    return hb;
  }

  function placeBubble(hb) {
    const bub = ctx.ui.bubble;
    if (!bub) return;
    const vw = window.innerWidth, vh = window.innerHeight, gap = 14, m = 12;
    const bw = bub.offsetWidth, bh = bub.offsetHeight;
    let x, y;
    if (!hb) { x = (vw - bw) / 2; y = (vh - bh) / 2; }
    else {
      const cx = hb.left + hb.width / 2;
      x = Math.min(Math.max(m, cx - bw / 2), vw - bw - m);
      if (vh - hb.bottom >= bh + gap + m) y = hb.bottom + gap;
      else if (hb.top >= bh + gap + m) y = hb.top - bh - gap;
      else if (vw - hb.right >= bw + gap + m) { x = hb.right + gap; y = Math.min(Math.max(m, hb.top), vh - bh - m); }
      else if (hb.left >= bw + gap + m) { x = hb.left - bw - gap; y = Math.min(Math.max(m, hb.top), vh - bh - m); }
      else y = vh - bh - m;   // a target as large as the window: the bubble rests at the bottom
    }
    bub.style.left = Math.round(x) + 'px'; bub.style.top = Math.round(y) + 'px';
  }

  function renderBubble(st, anchored) {
    const ui = ctx.ui;
    if (ui.bubble) ui.bubble.remove();
    const id = 'pdh-tour-title';
    const bub = mk('div', 'pdh-tour-bubble');
    bub.setAttribute('role', 'dialog');
    bub.setAttribute('aria-labelledby', id);
    bub.setAttribute('aria-describedby', 'pdh-tour-text');
    bub.tabIndex = -1;
    bub.appendChild(mk('div', 'pdh-tour-phase', st.phase)).id = id;
    const text = mk('p', 'pdh-tour-text', st.text); text.id = 'pdh-tour-text';
    bub.appendChild(text);
    const row = mk('div', 'pdh-tour-actions');
    if (!st.standalone) {
      const skip = mk('button', 'pdh-tour-skip', SKIP_LABEL); skip.type = 'button';
      skip.addEventListener('click', function () { skipTour(); });
      row.appendChild(skip);
    }
    row.appendChild(mk('span', 'pdh-tour-spacer'));
    if (st.secondary) {
      const sec = mk('button', 'pdh-tour-btn', st.secondary.label); sec.type = 'button';
      sec.addEventListener('click', function () { advance(st.secondary.choice); });
      row.appendChild(sec);
    }
    let primary = st.primary;
    if (!primary && !anchored) primary = { label: FALLBACK_LABEL, choice: 'primary' };   // target never appeared
    let main = null;
    if (primary) {
      main = mk('button', 'pdh-tour-btn pdh-tour-main', primary.label); main.type = 'button';
      main.addEventListener('click', function () { advance(primary.choice); });
      row.appendChild(main);
    }
    bub.appendChild(row);
    bub.addEventListener('keydown', function (e) {
      // Enter on the bubble itself runs the main action; Esc deliberately does nothing (no accidental skip).
      if (e.key === 'Enter' && e.target === bub && main) { e.preventDefault(); main.click(); }
    });
    ui.root.appendChild(bub);
    ui.bubble = bub;
    ui.main = main;
    return bub;
  }


  /* ---------- welcome card ---------- */

  async function welcomeInit() {
    let saved = null;
    try {
      const res = await fetch('/api/user_settings');
      if (res.ok) saved = ((await res.json()).settings || {}).language;
    } catch (e) { /* the browser language decides */ }
    let mode = 'auto';
    try { if (window.PDHTheme) mode = await window.PDHTheme.ready; } catch (e) { /* keep auto */ }
    if (THEME_MODES.indexOf(mode) < 0) mode = 'auto';
    return { lang: welcomeLang(saved, typeof navigator !== 'undefined' ? navigator.language : ''), mode: mode };
  }

  /* A radiogroup of buttons: arrow keys move and select, only the selected one is a tab stop. */
  function radioGroup(labelId, values, current, onPick) {
    const el = mk('div', 'seg pdh-tour-seg');
    el.setAttribute('role', 'radiogroup'); el.setAttribute('aria-labelledby', labelId);
    const buttons = values.map(function (v) {
      const b = mk('button', ''); b.type = 'button'; b.setAttribute('role', 'radio'); b.dataset.value = v;
      b.addEventListener('click', function () { pick(v, false); });
      el.appendChild(b);
      return b;
    });
    function mark(v) {
      buttons.forEach(function (b) { const on = b.dataset.value === v; b.setAttribute('aria-checked', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; });
    }
    function pick(v, focus) {
      mark(v);
      if (focus) buttons.filter(function (b) { return b.dataset.value === v; })[0].focus({ preventScroll: true });
      onPick(v);
    }
    el.addEventListener('keydown', function (e) {
      const dir = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!dir) return;
      e.preventDefault();
      const i = buttons.findIndex(function (b) { return b.getAttribute('aria-checked') === 'true'; });
      pick(buttons[(i + dir + buttons.length) % buttons.length].dataset.value, true);
    });
    mark(current);
    return { el: el, buttons: buttons };
  }

  function applyMode(mode) {
    if (window.PDHTheme && window.PDHTheme.apply) window.PDHTheme.apply(mode);
    else if (typeof document !== 'undefined') document.documentElement.dataset.mode = mode === 'dark' ? 'dark' : 'light';
  }

  const realIO = {
    saveLanguage: async function (lang) {
      const res = await fetch('/api/user_settings', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: { language: lang }, merge: true }) });
      if (!res.ok) throw new Error('HTTP ' + res.status);
    },
    saveTheme: async function (mode) { if (window.PDHTheme) await window.PDHTheme.set(mode); },
  };

  function renderWelcome(init) {
    const ui = ctx.ui, hooks = ctx.hooks;
    if (ui.bubble) ui.bubble.remove();
    const choice = { lang: init.lang, mode: init.mode };
    const bub = mk('div', 'pdh-tour-bubble pdh-tour-welcome');
    bub.setAttribute('data-no-i18n', '');   // this card writes both languages itself
    bub.setAttribute('role', 'dialog'); bub.setAttribute('aria-labelledby', 'pdh-tour-title');
    bub.tabIndex = -1;
    const title = mk('h2', 'pdh-tour-title'); title.id = 'pdh-tour-title';
    bub.appendChild(title);
    function group(key, values, current, onPick) {
      const wrap = mk('div', 'pdh-tour-group');
      const label = mk('div', 'pdh-tour-grouplabel', WELCOME_GROUPS[key]); label.id = 'pdh-tour-g-' + key;
      const g = radioGroup(label.id, values, current, onPick);
      wrap.appendChild(label); wrap.appendChild(g.el);
      bub.appendChild(wrap);
      return g;
    }
    const langGroup = group('lang', ['zh-CN', 'en-US'], choice.lang, function (v) { choice.lang = v; paint(); });
    langGroup.buttons[0].textContent = '中文'; langGroup.buttons[0].lang = 'zh';
    langGroup.buttons[1].textContent = 'English'; langGroup.buttons[1].lang = 'en';
    const modeGroup = group('mode', THEME_MODES, choice.mode, function (v) { choice.mode = v; applyMode(v); });
    const row = mk('div', 'pdh-tour-actions');
    const skip = mk('button', 'pdh-tour-skip', ''); skip.type = 'button';
    const main = mk('button', 'pdh-tour-btn pdh-tour-main', ''); main.type = 'button';
    row.appendChild(skip); row.appendChild(mk('span', 'pdh-tour-spacer')); row.appendChild(main);
    bub.appendChild(row);
    function paint() {
      const w = WELCOME[choice.lang];
      bub.lang = choice.lang === 'zh-CN' ? 'zh' : 'en';
      title.textContent = w.title;
      modeGroup.buttons.forEach(function (b) { b.textContent = w[b.dataset.value]; });
      skip.textContent = w.skip; main.textContent = w.start;
    }
    paint();
    let busy = false;
    function lock(on) { busy = on; main.disabled = on; skip.disabled = on; }
    main.addEventListener('click', async function () {
      if (busy) return;
      lock(true);
      const failure = await saveChoice(choice, realIO);
      if (failure && hooks.onError) hooks.onError(failure);
      try {
        // The sandbox is built in the language just saved, then the page reloads so the language pack applies.
        if (hooks.api) await hooks.api('/api/onboarding', { action: 'start' });
        else {
          const res = await fetch('/api/onboarding', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'start' }) });
          if (!res.ok) throw new Error('HTTP ' + res.status);
        }
      } catch (e) { if (hooks.onError) hooks.onError(e); lock(false); return; }
      const cur = pending() || { version: null, returnProject: null };
      writeState({ step: 'p1', version: cur.version, returnProject: cur.returnProject });
      if (hooks.reload) hooks.reload(); else window.location.reload();
    });
    skip.addEventListener('click', async function () {
      if (busy) return;
      lock(true);
      const failure = await saveChoice(choice, realIO);
      if (failure && hooks.onError) hooks.onError(failure);
      await skipTour();
      if (ctx && ctx.ui) lock(false);   // finish() was refused to navigate: the card is still there
    });
    ui.root.appendChild(bub);
    ui.bubble = bub; ui.main = main;
  }

  function focusStep(st, el, anchored) {
    const ui = ctx.ui;
    if (ui.main) { ui.main.focus({ preventScroll: true }); return; }
    // A click step: put focus on the target so Enter/Space press it natively.
    if (anchored && el && /^(BUTTON|A|INPUT|SELECT)$/.test(el.tagName)) { el.focus({ preventScroll: true }); return; }
    ui.bubble.focus({ preventScroll: true });
  }

  function frame() {
    if (!ctx || !ctx.active) return;
    const st = ctx.step;
    if (ctx.anchored) {
      let el = ctx.el;
      if (!el || !el.isConnected || !visible(el)) { el = pick(st.target, st.closest); ctx.el = el; }
      if (!el) { ctx.lost = true; }
      else {
        ctx.lost = false;
        const r = el.getBoundingClientRect();
        const key = [r.left, r.top, r.width, r.height, window.innerWidth, window.innerHeight, ctx.ui.bubble.offsetHeight].join(',');
        if (key !== ctx.key) {
          ctx.key = key;
          placeBubble(layout(r, st.advance !== 'click'));
        }
      }
      if (ctx.lost && ctx.key !== 'lost') {
        ctx.key = 'lost';
        layout(null, true); placeBubble(null);
      }
    }
    ctx.raf = window.requestAnimationFrame(frame);
  }

  function teardownUI() {
    if (!ctx) return;
    ctx.active = false;
    ctx.token++;
    if (ctx.raf) window.cancelAnimationFrame(ctx.raf);
    if (ctx.ui) ctx.ui.root.remove();
    ctx.ui = null; ctx.el = null;
  }

  async function show(stepId, override) {
    const st = override || BY_ID[stepId];
    if (!ctx || !st) return;
    const token = ++ctx.token;
    ctx.step = st; ctx.el = null; ctx.key = ''; ctx.anchored = false; ctx.active = false;
    if (ctx.raf) window.cancelAnimationFrame(ctx.raf);
    if (ctx.ui) { ctx.ui.root.remove(); ctx.ui = null; }
    const cur = pending() || { version: null, returnProject: null };
    if (!override) writeState({ step: st.id, version: cur.version, returnProject: cur.returnProject });   // a resume prompt keeps the stored step
    if (st.view && ctx.hooks.selectView) { try { ctx.hooks.selectView(st.view); } catch (e) { /* the page decides */ } }
    if (st.hook === 'openSwitcher' && ctx.hooks.openSwitcher) { try { ctx.hooks.openSwitcher(); } catch (e) { /* ignore */ } }
    if (st.welcome) {
      const init = await welcomeInit();
      if (!ctx || token !== ctx.token) return;
      ctx.ui = buildUI();
      ctx.active = true; ctx.anchored = false;
      renderWelcome(init);
      layout(null, true); placeBubble(null);
      ctx.ui.main.focus({ preventScroll: true });
      ctx.raf = window.requestAnimationFrame(frame);
      return;
    }
    const el = st.target ? await waitFor(st.ready || st.target, WAIT_MS, st.ready ? null : st.closest) : null;
    if (!ctx || token !== ctx.token) return;   // superseded while waiting
    const anchor = el ? pick(st.target, st.closest) : null;
    ctx.ui = buildUI();
    ctx.active = true;
    ctx.anchored = !!anchor;
    ctx.el = anchor;
    renderBubble(st, ctx.anchored);
    if (anchor) {
      const r = anchor.getBoundingClientRect(), vh = window.innerHeight;
      if (r.top < 0 || r.bottom > vh) {
        anchor.scrollIntoView({ block: r.height > vh * 0.6 ? 'start' : 'center', behavior: reduced() ? 'auto' : 'smooth' });
      }
      placeBubble(layout(anchor.getBoundingClientRect(), st.advance !== 'click'));
    } else { layout(null, true); placeBubble(null); }
    focusStep(st, anchor, ctx.anchored);
    ctx.raf = window.requestAnimationFrame(frame);
  }

  function navigate(url) {
    if (ctx && ctx.hooks.navigate) ctx.hooks.navigate(url);
    else window.location.assign(url);
  }

  function goTo(stepId) {
    const st = BY_ID[stepId];
    if (!st) return;
    const cur = pending() || { version: null, returnProject: null };
    writeState({ step: st.id, version: cur.version, returnProject: cur.returnProject });
    if (st.page !== ctx.page) { teardownUI(); navigate(PAGE_URL[st.page] || '/'); return; }
    show(st.id);
  }

  function advance(choice) {
    if (!ctx || !ctx.step) return;
    if (ctx.step.resume) { teardownUI(); navigate(ctx.step.resume); return; }   // go on where the tour was left
    const nxt = next(pending(), ctx.step.id, choice);
    if (nxt === 'finish' && ctx.step.standalone) { clearState(); teardownUI(); return; }   // the creation-page hint only dismisses
    if (nxt === 'finish') finish(); else goTo(nxt);
  }

  /* The target of a "click" step was pressed. Its own handler runs normally (nothing is blocked there);
     we only note the move. A step on another page is saved at once, because the click may navigate. */
  function onDocClick(e) {
    if (!ctx || !ctx.active || !ctx.anchored || ctx.step.advance !== 'click') return;
    const st = ctx.step, t = e.target;
    if (!(t && t.nodeType === 1)) return;
    if (!((ctx.el && ctx.el.contains(t)) || t.closest(st.target))) return;
    if (ctx.ui && ctx.ui.root.contains(t)) return;
    const nxt = next(pending(), st.id, 'primary');
    if (nxt === 'finish') { setTimeout(finish, 0); return; }
    const cur = pending() || { version: null, returnProject: null };
    writeState({ step: nxt, version: cur.version, returnProject: cur.returnProject });
    if (BY_ID[nxt].page !== ctx.page) { teardownUI(); return; }   // the click itself navigates
    ctx.token++;
    setTimeout(function () { show(nxt); }, 0);
  }

  async function postDone(hooks) {
    if (hooks && hooks.api) return hooks.api('/api/onboarding', { action: 'done' });
    const c = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const t = c ? setTimeout(function () { c.abort(); }, 5000) : null;
    try {
      const res = await fetch('/api/onboarding', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'done' }), signal: c ? c.signal : undefined });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res;
    } finally { if (t) clearTimeout(t); }
  }

  /* Mark the tour done on the server (no retry loop), clear tour state, go to finishTarget. */
  async function finish(opts) {
    if (finishing) return;
    finishing = true;
    const o = opts || {}, hooks = (ctx && ctx.hooks) || o.hooks || {};
    const st = pending() || {};
    teardownUI();
    try { await postDone(hooks); } catch (e) { if (hooks.onError) hooks.onError(e); }
    const has = o.hasRealProject != null ? !!o.hasRealProject
      : hooks.hasRealProject ? !!hooks.hasRealProject() : !!st.returnProject;
    const t = finishTarget(has);
    if (t.step) writeState({ step: t.step, version: st.version, returnProject: null }); else clearState();
    finishing = false;
    if (hooks.onFinish && hooks.onFinish(t, { returnProject: st.returnProject || null, skipped: !!o.skipped }) === false) return;
    if (ctx && ctx.hooks.navigate) ctx.hooks.navigate(t.url); else if (typeof window !== 'undefined') window.location.assign(t.url);
  }
  function skipTour() { return finish({ skipped: true }); }

  /* Start the tour: stores {v:1, step:'p1', version, returnProject} and marks this version offered for the
     session. It draws nothing; call boot() after the page has loaded its demo data. */
  function begin(opts) {
    const o = opts || {};
    const state = { v: VERSION, step: o.step && BY_ID[o.step] ? o.step : 'p1',
      version: o.version == null ? null : o.version, returnProject: o.returnProject == null ? null : o.returnProject };
    writeState(state);
    const s = store();
    if (s && state.version != null) s.setItem(OFFERED_KEY, String(state.version));
    return state;
  }

  /* Show the stored step if it belongs to this page. hooks: {selectView(view), openSwitcher(), api(path, body),
     hasRealProject(), onFinish(target, info) (return false to skip the redirect), onError(err), navigate(url)}.
     Returns true when a step is being shown. */
  function boot(page, hooks) {
    if (typeof document === 'undefined') return false;
    const state = pending();
    if (!state) return false;
    const lost = strandedStep(state, page);
    const st = lost || BY_ID[state.step];
    if (!st || (!lost && st.page !== page)) return false;
    if (st.id === 'c1' && !document.querySelector(st.target)) return false;
    if (ctx) teardownUI();
    ctx = { page: page, hooks: hooks || {}, token: 0, step: st, ui: null, el: null, active: false, anchored: false, raf: 0, key: '' };
    if (!boot.bound) { document.addEventListener('click', onDocClick, true); boot.bound = true; }
    show(st.id, lost || undefined);
    return true;
  }
  /* Drop the stored state (and any bubble); with `onlyStep` only when that step is the stored one. */
  function dismiss(onlyStep) {
    const state = pending();
    if (onlyStep && (!state || state.step !== onlyStep)) return;
    clearState();
    if (ctx) teardownUI();
  }
  function stop() { if (ctx) teardownUI(); }

  return { STEPS: STEPS, KEY: KEY, OFFERED_KEY: OFFERED_KEY, DEMO_ID: DEMO_ID, PAGE_URL: PAGE_URL,
    shouldOffer: shouldOffer, next: next, stepsFor: stepsFor, finishTarget: finishTarget,
    serialize: serialize, parse: parse, WELCOME: WELCOME, THEME_MODES: THEME_MODES,
    welcomeLang: welcomeLang, saveChoice: saveChoice, current: current, pending: pending, setStorage: setStorage,
    waitFor: waitFor, strandedStep: strandedStep, dismiss: dismiss, begin: begin, boot: boot, finish: finish, skip: skipTour, stop: stop };
});
