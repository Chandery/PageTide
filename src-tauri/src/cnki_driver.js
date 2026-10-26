// PageTide's CNKI page script (ADR 0045). Injected by the shell into its own CNKI window only (src-tauri/src/cnki.rs) and run
// on every page load there. It asks the shell for the job, works on the page it is on, reports what it read and where it left
// off, and moves on. It never touches a puzzle: on CNKI's verification page or slider it reports "verification" and waits for
// the person.
//
// Searches (refresh, creation candidates, seed hits) read result pages only, in CNKI's 详情 view (50 per page), which shows an
// abstract snippet and the keywords under each title: no detail page is opened, so a refresh takes seconds and every page is
// reported as soon as it is read. Only a `detail` job opens one paper's detail page, clicks 更多 and reads the full abstract
// (the app asks for it when the person opens the paper).
//
// Selectors follow cookjohn/cnki-skills (MIT) and pages saved on 2026-10-26: view switch `#DivDisplayMode li[data-mode]`, rows
// `dl.result-detail-list dd` (or `.result-table-list tbody tr` in the list view), stable ids on `.icon-collect` (data-dbname /
// data-filename / data-resource), snippet `p.abstract`, keywords `p.keywords a`, next page `#PageNext`, page size
// `#perPageDiv li[data-val]`, categories `a[name=classify][resource=JOURNAL|DISSERTATION]`; detail page ids `#paramdbcode` /
// `#param-filename`, abstract `#ChDivSummary` (cut at about 500 characters until `#ChDivSummaryMore` is clicked).
(() => {
  if (window.top !== window || window.__pageTideCnki) return;
  window.__pageTideCnki = true;
  const SEARCH = 'https://kns.cnki.net/kns8s/search';
  const PAGES_PER_CATEGORY = 4;

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const pause = () => sleep(1500 + Math.random() * 2500);
  const text = el => ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
  const invoke = (cmd, args) => window.__TAURI_INTERNALS__.invoke(cmd, args || {});
  const report = payload => invoke('cnki_report', {payload});

  async function until(test, ms = 30000, step = 400) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      try { const value = test(); if (value) return value; } catch (e) { /* the page is still changing */ }
      await sleep(step);
    }
    return null;
  }

  function puzzle() {
    if (location.pathname.startsWith('/verify')) return true;
    const slider = document.querySelector('#tcaptcha_transform_dy');       // preloaded off screen; shown only when it is asked
    return !!(slider && slider.getBoundingClientRect().top >= 0);
  }

  async function waitForPerson() {
    await report({event: 'verification'});
    if (location.pathname.startsWith('/verify')) return false;        // a pass reloads a search page: start again there
    await until(() => !puzzle(), 300000, 1000);
    await report({event: 'verified'});
    return true;
  }

  const grid = () => document.querySelector('.result-detail-list, .result-table-list');
  const empty = () => /暂无数据|没有找到/.test(text(document.querySelector('#gridTable')));

  // Runs `act` and waits until the result grid was replaced (the old one is marked first) or says there is nothing.
  async function gridChange(act) {
    const old = grid();
    if (old) old.dataset.ptSeen = '1';
    act();
    await sleep(600);
    return until(() => puzzle() ? 'puzzle'
      : document.querySelector('.result-detail-list:not([data-pt-seen]), .result-table-list:not([data-pt-seen])') ? 'rows'
      : empty() ? 'empty' : null, 30000);
  }

  // The 详情 view (snippets and keywords) with 50 rows a page; each switch reloads the grid.
  async function detailView() {
    const tab = document.querySelector('#DivDisplayMode li[data-mode="custommode"]');
    if (tab && !tab.classList.contains('active') && !document.querySelector('.result-detail-list')) {
      const state = await gridChange(() => tab.click());
      if (state !== 'rows') return state;
    }
    const fifty = document.querySelector('#perPageDiv li[data-val="50"]');
    if (fifty && !fifty.classList.contains('cur')) {
      const state = await gridChange(() => fifty.querySelector('a')?.click() || fifty.click());
      if (state !== 'rows') return state;
    }
    return 'rows';
  }

  function rowsOnPage() {
    const detailRows = [...document.querySelectorAll('.result-detail-list dd')];
    const rows = detailRows.length ? detailRows : [...document.querySelectorAll('.result-table-list tbody tr')];
    return rows.map(row => {
      const link = row.querySelector('a.fz14');
      const ids = row.querySelector('.icon-collect');
      if (!link || !ids) return null;
      const snippet = row.querySelector('p.abstract');
      const abstract = snippet ? text(snippet).replace(/^摘要[:：]\s*/, '') : '';
      return {dbname: ids.dataset.dbname || '', filename: ids.dataset.filename || '', resource: ids.dataset.resource || '',
              title: text(link), url: link.href,
              date: text(row.querySelector('.baseinfo .date, td.date')),
              source: text(row.querySelector('.baseinfo .journal, td.source')),
              abstract, abstract_partial: !!abstract,
              keywords: [...row.querySelectorAll('p.keywords a')].map(a => text(a).replace(/[;；]\s*$/, '')).filter(Boolean).slice(0, 12),
              authors: [...row.querySelectorAll('.authorinfo > p > a, td.author a')].map(text).filter(Boolean).slice(0, 8)};
    }).filter(Boolean);
  }

  async function search(job, cursor) {
    const input = await until(() => document.querySelector('input.search-input'), 15000);
    if (!input) {
      if (location.pathname !== '/kns8s/search') { location.href = SEARCH; return; }
      throw new Error('search box not found');
    }
    const query = job.queries[cursor.q];
    let state;
    if (cursor.submitted !== cursor.q) {
      // Noted before the click: if submitting loads a new page, this script starts again there and only waits for the rows.
      cursor = {...cursor, submitted: cursor.q};
      await report({cursor, event: 'progress'});
      state = await gridChange(() => {
        input.value = query;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        document.querySelector('input.search-btn').click();
      });
    } else {
      state = await until(() => puzzle() ? 'puzzle' : grid() ? 'rows' : empty() ? 'empty' : null, 30000);
      if (!state) {
        if ((cursor.retries || 0) >= 2) throw new Error('no results page');     // CNKI changed: end the run, never loop
        cursor = {...cursor, submitted: null, retries: (cursor.retries || 0) + 1};
        await report({cursor, event: 'progress'});
        location.href = SEARCH;
        return;
      }
    }
    if (state === 'puzzle') { if (await waitForPerson()) location.reload(); return; }
    const want = job.mode === 'refresh' ? job.max_new : job.per_query;
    let found = cursor.new || 0;            // new papers (refresh) or hits (other searches) reported so far in this run
    const knownIds = new Set(job.known || []);
    const seen = new Set();
    for (const category of job.categories) {
      if (found >= want) break;
      const tab = document.querySelector(`a[name="classify"][resource="${category}"]`);
      if (!tab) continue;
      state = await gridChange(() => tab.click());
      if (state === 'rows') state = await detailView();
      if (state === 'puzzle') { if (await waitForPerson()) location.reload(); return; }
      if (state !== 'rows') continue;
      for (let page = 1; page <= PAGES_PER_CATEGORY; page++) {
        let older = false;
        const batch = [];
        for (const row of rowsOnPage()) {
          const id = `${row.dbname}:${row.filename}`;
          if (seen.has(id)) continue;
          seen.add(id);
          if (job.since && row.date && row.date.slice(0, 10) < job.since) { older = true; break; }   // newest first
          if (job.mode === 'refresh' && knownIds.has(id)) { batch.push(row); continue; }      // links it to this project
          if (found >= want) break;
          batch.push(row);
          found += 1;
        }
        // Reported page by page: the app stores (and can recommend) each page while the next one loads.
        for (let i = 0; i < batch.length; i += 25) await report({items: batch.slice(i, i + 25), event: 'progress'});
        await report({cursor: {...cursor, new: found}, event: 'progress'});
        const next = document.querySelector('#PageNext');
        if (older || !next || found >= want || page === PAGES_PER_CATEGORY) break;
        await pause();
        state = await gridChange(() => next.click());
        if (state === 'puzzle') { if (await waitForPerson()) location.reload(); return; }
        if (state !== 'rows') break;
      }
      await pause();
    }
    const after = {...cursor, phase: 'search', q: cursor.q + 1, new: found, submitted: null, retries: 0};
    if (after.q >= job.queries.length || found >= want) { await report({cursor: after, event: 'done'}); return; }
    await report({cursor: after, event: 'progress'});
    await pause();
    location.href = SEARCH;
  }

  // One paper's detail page: the full abstract (after 更多), keywords and DOI.
  async function detail(job, cursor) {
    const target = cursor.queue[0];
    if (!target) { await report({cursor, event: 'done'}); return; }
    if (!location.pathname.startsWith('/kcms')) { location.href = target.url; return; }
    await until(() => document.querySelector('#paramdbcode, .wx-tit'));
    const more = document.querySelector('#ChDivSummaryMore');
    if (more && more.offsetParent !== null) {
      more.click();
      await until(() => document.querySelector('#ChDivSummaryMore')?.offsetParent === null, 3000, 200);
    }
    const abstract = text(document.querySelector('#ChDivSummary') || document.querySelector('.abstract-text'));
    const doiRow = [...document.querySelectorAll('.top-space, .row li, .row')].find(el => /^DOI[:：]/.test(text(el.querySelector('.rowtit'))));
    const cut = /(\.\.\.\.\.\.|……)$/.test(abstract);
    const item = {
      ...target,
      dbname: document.querySelector('#paramdbcode')?.value || target.dbname,
      filename: document.querySelector('#param-filename')?.value || target.filename,
      title: text(document.querySelector('.wx-tit h1')) || target.title,
      abstract, abstract_partial: cut || !abstract,
      keywords: [...document.querySelectorAll('.keywords a')].map(a => text(a).replace(/[;；]\s*$/, '')).filter(Boolean).slice(0, 12),
      doi: doiRow ? text(doiRow.querySelector('p')) : '',
    };
    const after = {...cursor, queue: cursor.queue.slice(1)};
    await report({items: [item], cursor: after, event: after.queue.length ? 'progress' : 'done'});
    if (after.queue.length) { await pause(); location.href = after.queue[0].url; }
  }

  async function run() {
    await until(() => document.readyState === 'complete', 30000, 200);
    await sleep(500);
    if (puzzle()) { if (await waitForPerson()) location.reload(); return; }
    const next = await invoke('cnki_next');
    if (!next || !next.job) return;
    const job = next.job, cursor = next.cursor || {phase: 'search', q: 0, queue: [], new: 0};
    if (cursor.phase === 'detail') return detail(job, cursor);
    return search(job, cursor);
  }

  const start = () => run().catch(error => {
    const kind = /network|fetch|offline/i.test(String(error)) ? 'network_error' : 'unavailable';
    report({event: 'error', kind, message: String(error).slice(0, 200)}).catch(() => {});
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
