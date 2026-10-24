/* The weekly report page: what moved this week, by day and by direction, and how the learning map advanced.
   Pure functions from the server's weekly report to HTML. Every value that came from data goes through esc() or
   Number(); nothing is estimated here. A quiet direction or a day without records is shown as "no record", never
   as lost interest. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PDHWeekly = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const n = (value) => Number(value) || 0;
  // "已读懂" moves the learning map on; with the map switched off in Settings it is not shown here either.
  const mapOn = () => typeof window === 'undefined' || window.PAGETIDE_ROUTE_BETA !== false;
  const shown = (list) => mapOn() ? list : list.filter((k) => k !== 'understood');
  const KINDS = ['saved', 'positive', 'understood', 'negative', 'too_hard'];
  const LABEL = { saved: '收藏', positive: '有用', understood: '已读懂', negative: '不相关', too_hard: '太难' };
  const STATUS = { new: '新出现', more: '比上周多', same: '与上周持平', fewer: '比上周少', quiet: '本周没有记录', other: '本周没有收藏或已读懂' };
  const UNIT_STATUS = { satisfied: '已读懂', unlocked: '可以读', locked: '未解锁', proposed: '建议', archived: '已归档' };
  const WEEKDAY = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
  const day = (iso) => String(iso || '').slice(0, 10);
  const signed = (v) => (v > 0 ? `+${v}` : `−${-v}`);   // only called for a real change
  const UNSORTED = '未分类';   // the server's name for papers outside every category; the page translates it, a person's own names stay as typed
  const named = (tag, name, cls = '') => `<${tag}${cls ? ` class="${cls}"` : ''}${name === UNSORTED ? '' : ' data-no-i18n'}>${esc(name)}</${tag}>`;
  const empty = (text) => `<div class="profile-empty">${esc(text)}</div>`;
  const evidence = (kind, report, current = true) => `data-evidence="${esc(kind)}" data-start="${esc(current ? report.week_start : report.previous_start)}" data-end="${esc(current ? report.week_end : report.week_start)}"`;

  function lastDay(iso) {   // the window's right end is exclusive: show the last day inside it
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? day(iso) : new Date(d.getTime() - 86400000).toISOString().slice(0, 10);
  }

  function hero(r) {
    const h = r.highlights || {};
    const range = `${day(r.week_start)} 至 ${lastDay(r.week_end)}`;
    if (!r.has_activity) {
      return `<section class="wk-hero"><div class="wk-range">${esc(range)}</div><h2>本周还没有记录</h2></section>`;
    }
    const diff = n(h.papers) - n(h.previous_papers);
    const chip = n(h.previous_papers) ? `<span class="wk-delta ${diff > 0 ? 'is-up' : diff < 0 ? 'is-down' : ''}">${diff ? `论文数比上周 ${signed(diff)}` : '与上周持平'}</span>` : '';
    return `<section class="wk-hero"><div class="wk-range">${esc(range)}</div><h2>本周涉及 ${n(h.directions)} 个方向，${n(h.papers)} 篇论文</h2>${chip}</section>`;
  }

  function kpis(r) {
    const now = r.stats || {}, before = r.previous_stats || {};
    return `<section class="wk-kpis" aria-label="本周数字">${shown(KINDS).map((k) => {
      const diff = n(now[k]) - n(before[k]);
      return `<button type="button" class="wk-kpi k-${k}" ${evidence(k, r)}><span class="wk-kpi-label"><i></i>${LABEL[k]}</span><b>${n(now[k])}</b>`
        + `<span class="wk-kpi-delta">${diff ? `较上周 ${signed(diff)}` : '与上周持平'}</span></button>`;
    }).join('')}</section>`;
  }

  function days(r) {
    const list = r.daily || [];
    const order = shown(['understood', 'positive', 'saved', 'negative', 'too_hard']);
    const totals = list.map((d) => order.reduce((sum, k) => sum + n(d[k]), 0));
    const peak = Math.max(1, ...totals);
    const cols = list.map((d, i) => {
      const stack = order.map((k) => (n(d[k]) ? `<i class="k-${k}" style="height:${(n(d[k]) / peak * 100).toFixed(1)}%"></i>` : '')).join('');
      const tip = `${day(d.date)} · ${order.filter((k) => n(d[k])).map((k) => `${LABEL[k]} ${n(d[k])}`).join(' · ') || '没有记录'}`;
      return `<div class="wk-day${i === list.length - 1 ? ' is-today' : ''}" title="${esc(tip)}"><span class="wk-day-n">${totals[i] || ''}</span><span class="wk-day-bar">${stack}</span>`
        + `<span class="wk-day-l">${WEEKDAY[n(d.weekday)] || ''}<small>${esc(day(d.date).slice(5))}</small></span></div>`;
    }).join('');
    return `<section class="wk-card"><div class="wk-head"><h3>这一周每天</h3></div>`
      + (totals.some(Boolean) ? `<div class="wk-days">${cols}</div>` : empty('没有记录'))
      + '</section>';
  }

  function segments(tally, papers) {
    // a "useful" is also a save, so only the saves that came without a rating of their own get their own colour
    const own = { ...tally, saved: Math.max(0, n(tally.saved) - n(tally.positive)) };
    const parts = shown(['understood', 'positive', 'saved', 'negative', 'too_hard']).filter((k) => n(own[k]));
    const total = parts.reduce((sum, k) => sum + n(own[k]), 0);
    if (!total) return n(papers) ? '<i class="k-saved" style="width:100%"></i>' : '';
    return parts.map((k) => `<i class="k-${k}" style="width:${(n(own[k]) / total * 100).toFixed(1)}%"></i>`).join('');
  }

  function directions(r) {
    const list = r.directions || [];
    const head = `<div class="wk-head"><h3>方向的变动</h3></div>`;
    if (!list.length) return `<section class="wk-card">${head}${empty('本周没有记录')}</section>`;
    const widest = Math.max(1, ...list.flatMap((d) => [n(d.current.papers), n(d.previous.papers)]));
    const cards = list.map((d) => {
      const counts = shown(KINDS).filter((k) => n(d.current[k])).map((k) => `<span class="k-${k}"><i></i>${LABEL[k]} ${n(d.current[k])}</span>`).join('');
      const papers = (d.papers || []).map((p) => `<li><span class="wk-paper-title" data-no-i18n>${esc(p.title)}</span>${(p.kinds || []).filter((k) => LABEL[k]).map((k) => `<em class="k-${k}">${LABEL[k]}</em>`).join('')}</li>`).join('');
      return `<article class="wk-dir s-${esc(d.status)}"><header>${named('h4', d.name)}<span class="wk-pill s-${esc(d.status)}">${esc((d.status === 'other' && !mapOn() ? '本周没有收藏' : STATUS[d.status]) || '')}</span></header>`
        + `<div class="wk-bars"><div class="wk-track is-prev"><div class="wk-bar" style="width:${(n(d.previous.papers) / widest * 100).toFixed(1)}%">${segments(d.previous, d.previous.papers)}</div></div><span>上周论文 ${n(d.previous.papers)}</span>`
        + `<div class="wk-track"><div class="wk-bar" style="width:${(n(d.current.papers) / widest * 100).toFixed(1)}%">${segments(d.current, d.current.papers)}</div></div><span>本周论文 ${n(d.current.papers)}</span></div>`
        + (counts ? `<div class="wk-counts">${counts}</div>` : '')
        + (papers ? `<details><summary>本周涉及的论文</summary><ul class="wk-papers">${papers}</ul></details>` : '')
        + '</article>';
    }).join('');
    return `<section class="wk-card">${head}<div class="wk-dirs">${cards}</div></section>`;
  }

  function units(r) {
    if (!mapOn()) return '';
    const u = r.units;
    if (!u) return '';
    const share = u.total ? Math.round(n(u.done) / n(u.total) * 100) : 0;
    const rows = [...(u.items || [])].sort((a, b) => n(b.current.understood) - n(a.current.understood) || (n(b.current.papers) - n(a.current.papers)))
      .map((it) => {
        const c = it.current || {};
        const parts = [['understood', c.understood], ['positive', c.positive], ['too_hard', c.too_hard]].filter(([, v]) => n(v)).map(([k, v]) => `<span class="k-${k}"><i></i>${LABEL[k]} ${n(v)}</span>`).join('');
        return `<li class="wk-unit${n(c.understood) ? ' is-advanced' : ''}"><span class="wk-unit-name" data-no-i18n>${esc(it.name)}</span><span class="wk-chip st-${esc(it.status)}">${esc(UNIT_STATUS[it.status] || '')}</span><span class="wk-unit-counts">${parts}</span></li>`;
      }).join('');
    return `<section class="wk-card"><div class="wk-head"><h3>学习图进度</h3><span class="wk-note">已读懂 ${n(u.done)} / ${n(u.total)} 个概念</span></div>`
      + `<div class="wk-progress" role="img" aria-label="已读懂 ${n(u.done)} / ${n(u.total)} 个概念"><i style="width:${share}%"></i></div><ul class="wk-units">${rows}</ul></section>`;
  }

  function picks(r) {
    const list = r.picks || [];
    if (!list.length) return '';
    const rows = list.map((p) => `<li><span class="wk-paper-title" data-no-i18n>${esc(p.title)}</span><span class="wk-tags">`
      + (p.directions || []).map((d) => named('span', d, 'wk-chip')).join('')
      + (p.unit ? `<span class="wk-chip is-unit" data-no-i18n>${esc(p.unit)}</span>` : '')
      + (p.kinds || []).filter((k) => LABEL[k]).map((k) => `<em class="k-${k}">${LABEL[k]}</em>`).join('') + '</span></li>').join('');
    return `<section class="wk-card"><div class="wk-head"><h3>本周留下的论文</h3></div><ul class="wk-picks">${rows}</ul></section>`;
  }

  function exposure(r) {
    const h = r.highlights || {};
    const lines = [];
    if (n(h.judged)) lines.push(esc(`有用率 ${Math.round(n(h.positive) / n(h.judged) * 100)}%`));
    return lines.length ? `<section class="wk-card wk-lines">${lines.map((l) => `<p>${l}</p>`).join('')}</section>` : '';
  }

  function terms(r) {
    if (!r.comparable) return `<section class="wk-card"><div class="wk-head"><h3>词项变化</h3></div>${empty('暂无可比较的数据')}</section>`;
    const ch = r.keyword_changes || {};
    const chip = (t, dir) => `<button type="button" class="wk-term is-${dir}" data-evidence="term" data-term="${esc(t.term)}" data-start="${esc(r.week_start)}" data-end="${esc(r.week_end)}"><span data-no-i18n>${esc(t.term)}</span><small>${n(t.previous)} → ${n(t.current)}</small></button>`;
    const up = (ch.rising || []).map((t) => chip(t, 'up')).join(''), down = (ch.falling || []).map((t) => chip(t, 'down')).join('');
    return `<section class="wk-card"><div class="wk-head"><h3>词项变化</h3></div>`
      + (up || down ? `<div class="wk-terms">${up}${down}</div>` : '<p class="wk-adv">与上周持平</p>') + '</section>';
  }

  function weeklyHTML(report) {
    if (!report) return empty('暂未加载周报');
    return [hero(report), kpis(report), days(report), directions(report), units(report), picks(report), exposure(report), terms(report)].join('');
  }

  return { weeklyHTML, hero, kpis, days, directions, units, picks, exposure, terms, STATUS };
});
