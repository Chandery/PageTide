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
    const passed = await until(() => !puzzle(), 300000, 1000);
    if (!passed) return false;                                         // nobody slid it: the shell ends the run at its limit
    await report({event: 'verified'});
    return true;
  }

  // Newest first: the time window below relies on it (CNKI's default, made sure of here).
  async function newestFirst() {
    for (let i = 0; i < 2; i++) {
      const byDate = document.querySelector('#orderList li#PT');
      if (!byDate || (byDate.classList.contains('cur') && byDate.classList.contains('DESC'))) return 'rows';
      const state = await gridChange(() => byDate.click());
      if (state !== 'rows') return state;
    }
    return 'rows';
  }

  const grid = () => document.querySelector('.result-detail-list, .result-table-list');
  // No result: CNKI's wording differs by page (a long query of several words showed none of the first two, 2026-10-26), so
  // the result count is read as well.
  const empty = () => {
    if (/暂无数据|没有找到|抱歉/.test(text(document.querySelector('#gridTable, #ModuleSearchResult, .result-con')))) return true;
    const count = document.querySelector('.pagerTitleCell em, #countPageDiv em');
    return !!count && text(count).replace(/,/g, '') === '0';
  };
  // A query of several words can find nothing on CNKI where its first words do: drop the last word and search again, down
  // to one word, at most MAX_RELAX times per query.
  const MAX_RELAX = 3;
  const shorter = (query, cursor) => {
    const words = query.split(/\s+/).filter(Boolean);
    return words.length > 1 && (cursor.relaxes || 0) < MAX_RELAX ? words.slice(0, -1).join(' ') : null;
  };

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

  async function search(job, cursor, fresh) {
    const input = await until(() => document.querySelector('input.search-input'), 15000);
    if (!input) {
      if (location.pathname !== '/kns8s/search') { location.href = SEARCH; return; }
      throw new Error('search box not found');
    }
    const query = cursor.relaxed || job.queries[cursor.q];
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
    if (state !== 'rows') {
      // Nothing for this query: try it with fewer words, or go on to the next query. Never a walk through empty tabs.
      const fewer = shorter(query, cursor);
      if (fewer) {
        await report({cursor: {...cursor, submitted: null, retries: 0, relaxed: fewer, relaxes: (cursor.relaxes || 0) + 1},
                      event: 'progress', message: `no result for "${query}": trying "${fewer}"`});
        await pause();
        location.href = SEARCH;
        return;
      }
      return nextQuery(job, cursor, false, `no result for "${query}"`);
    }
    // Every row in the time window is reported; the shell counts which are new (it alone knows the library) and says when the
    // run's cap is reached.
    let full = !!fresh.full;
    const seen = new Set();
    for (const category of job.categories) {
      if (full) break;
      const tab = document.querySelector(`a[name="classify"][resource="${category}"]`);
      if (!tab) continue;
      state = await gridChange(() => tab.click());
      if (state === 'rows') state = await detailView();
      if (state === 'rows') state = await newestFirst();
      if (state === 'puzzle') { if (await waitForPerson()) location.reload(); return; }
      if (state !== 'rows') continue;
      for (let page = 1; page <= PAGES_PER_CATEGORY; page++) {
        let older = false;
        const batch = [];
        for (const row of rowsOnPage()) {
          const id = `${row.dbname}:${row.filename}`;
          if (seen.has(id)) continue;
          seen.add(id);
          if (job.since && row.date && row.date.slice(0, 10) < job.since) { older = true; continue; }
          batch.push(row);
        }
        // Reported page by page: the app stores (and can recommend) each page while the next one loads.
        for (let i = 0; i < batch.length && !full; i += 25) {
          const answer = await report({items: batch.slice(i, i + 25), event: 'progress'});
          full = !!(answer && answer.full);
        }
        const next = document.querySelector('#PageNext');
        if (older || !next || full || page === PAGES_PER_CATEGORY) break;
        await pause();
        state = await gridChange(() => next.click());
        if (state === 'puzzle') { if (await waitForPerson()) location.reload(); return; }
        if (state !== 'rows') break;
      }
      await report({event: 'progress', message: `${category} read`});     // a word to the shell while the run reads on
      await pause();
    }
    return nextQuery(job, cursor, full);
  }

  async function nextQuery(job, cursor, full, message = '') {
    const after = {...cursor, phase: 'search', q: cursor.q + 1, submitted: null, retries: 0, relaxed: null, relaxes: 0};
    if (after.q >= job.queries.length || full) { await report({cursor: after, event: 'done', message}); return; }
    await report({cursor: after, event: 'progress', message});
    await pause();
    location.href = SEARCH;
  }

  // Reaches a paper's detail page the way a person does: search its title, then follow its own link in the results (a fresh
  // link, from a results page). Opening a stored detail link cold brought CNKI's puzzle on almost every paper (2026-10-26);
  // detail pages reached from results pages in the same session did not.
  async function viaResults(target, cursor) {
    const input = await until(() => document.querySelector('input.search-input'), 15000);
    if (!input) { location.href = SEARCH; return; }
    const state = await gridChange(() => {
      input.value = target.title || '';
      input.dispatchEvent(new Event('input', {bubbles: true}));
      document.querySelector('input.search-btn').click();
    });
    if (state === 'puzzle') { if (await waitForPerson()) location.reload(); return; }
    const row = state === 'rows' && rowsOnPage().find(r => r.dbname.toUpperCase() === String(target.dbname || '').toUpperCase()
                                                          && r.filename === target.filename);
    await report({cursor: {...cursor, via: true}, event: 'progress'});
    await pause();
    location.href = row ? row.url : target.url;          // not in the results: the stored link after all
  }

  // One paper's detail page: the full abstract (after 更多), keywords and DOI.
  async function detail(job, cursor) {
    const target = cursor.queue[0];
    if (!target) { await report({cursor, event: 'done'}); return; }
    if (!cursor.via && target.title) return viaResults(target, cursor);
    if (!location.pathname.startsWith('/kcms')) {
      // The stored link may have expired and lead elsewhere: a few tries, never an endless loop.
      if ((cursor.tries || 0) >= 2) throw new Error('detail page not reached');
      await report({cursor: {...cursor, tries: (cursor.tries || 0) + 1}, event: 'progress'});
      location.href = target.url;
      return;
    }
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
    const job = next.job, cursor = next.cursor || {phase: 'search', q: 0, queue: []};
    if (cursor.phase === 'detail') return detail(job, cursor);
    return search(job, cursor, {full: (next.fresh || 0) >= job.max_new});
  }

  const start = () => run().catch(error => {
    const kind = /network|fetch|offline/i.test(String(error)) ? 'network_error' : 'unavailable';
    report({event: 'error', kind, message: String(error).slice(0, 200)}).catch(() => {});
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
