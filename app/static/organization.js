(() => {
  'use strict';
  const S = { snapshot: { directions: [], items: [], positions: {} }, mode: 'library', filter: '*', query: '', selected: new Set(), key: null, collapsed: new Set(), drafts: new Map(), positions: {}, pending: 0, queue: Promise.resolve(), cy: null, root: null, error: '', graphRadialPending: false };
  const h = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const DEFAULT_COLOR = '#64748b';
  const color = value => /^#[0-9a-f]{6}$/i.test(value || '') ? value : DEFAULT_COLOR;
  // Graph colours follow the page palette (index.html tokens) so light/dark stay in sync.
  const theme = (name, fallback) => {
    try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback; }
    catch { return fallback; }
  };
  const $ = selector => S.root.querySelector(selector);
  const icons = { undo: 'undo-2', export: 'download', fit: 'maximize', rearrange: 'grid-2x2', 'zoom-in': 'plus', 'zoom-out': 'minus', 'direction-new': 'plus', collapse: 'chevron-down', 'direction-edit': 'pencil', 'category-child': 'plus', 'direction-delete': 'x', 'direction-up': 'arrow-up', 'direction-down': 'arrow-down', 'detail-close': 'x', 'dialog-close': 'x', history: 'history', 'note-save': 'check' };
  const button = (action, label, symbol, extra = '') => `<button type="button" data-action="${action}" title="${h(label)}" aria-label="${h(label)}" ${extra}><img class="org-icon" src="/icons/org/${icons[action] || 'pencil'}.svg" width="16" height="16" alt=""></button>`;
  const directions = () => [...S.snapshot.directions].sort((a, b) => (a.rank || 0) - (b.rank || 0));
  function treeRows(snapshot = S.snapshot) {
    const all = [...(snapshot.directions || [])].sort((a,b) => (a.rank || 0) - (b.rank || 0));
    const ids = new Set(all.map(d => String(d.id))), children = new Map();
    for (const d of all) {
      const parent = d.parent_id != null && ids.has(String(d.parent_id)) ? String(d.parent_id) : null;
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(d);
    }
    const rows = [], visited = new Set(), folded = new Set(snapshot.collapsed || []);
    const stack = (children.get(null) || []).map(d => ({d, depth:0, path:[], hidden:false})).reverse();
    while (stack.length) {
      const {d,depth,path,hidden} = stack.pop(), id = String(d.id);
      if (visited.has(id)) continue;
      visited.add(id);
      const nextPath = [...path,d.name], nested = children.get(id) || [];
      rows.push({...d, depth, path:nextPath.join(' / '), hidden, hasChildren:!!nested.length});
      for (let i=nested.length-1;i>=0;i--) stack.push({d:nested[i],depth:depth+1,path:nextPath,hidden:hidden || folded.has(id)});
    }
    return rows;
  }
  function categoryIds(id, snapshot = S.snapshot) {
    const selected = new Set([String(id)]), children = new Map();
    for (const d of snapshot.directions || []) {
      const parent = d.parent_id == null ? null : String(d.parent_id);
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(String(d.id));
    }
    const queue = [String(id)];
    for (let i=0;i<queue.length;i++) for (const child of children.get(queue[i]) || []) {
      if (!selected.has(child)) { selected.add(child); queue.push(child); }
    }
    return selected;
  }
  function categoryPath(id, snapshot = S.snapshot) { return treeRows(snapshot).find(d => String(d.id) === String(id))?.path || String(id); }
  const item = key => S.snapshot.items.find(p => p.key === key);
  const memberships = p => (p.directions || []).map(String);
  const groupId = id => `direction:${id}`;
  const cardId = (key, id) => `paper:${encodeURIComponent(key)}:${encodeURIComponent(id)}`;
  const matches = p => `${p.title || ''} ${p.abstract || ''} ${p.note || ''}`.toLocaleLowerCase().includes(S.query.toLocaleLowerCase());
  const visible = () => { const ids = categoryIds(S.filter); return S.snapshot.items.filter(p => matches(p) && (S.filter === '*' || (S.filter === '' ? !memberships(p).length : memberships(p).some(id => ids.has(id))))); };
  function report(error) { S.error = error.message || String(error); status(); window.PDH.toast(S.error, 'error'); }
  function status() {
    const node = $('[data-status]');
    if (node) { node.classList.toggle('org-error', !!S.error); node.textContent = S.error || (S.pending ? '正在保存…' : S.notice || `${S.snapshot.items.length} 篇论文 · ${S.snapshot.directions.length} 个方向`); }
  }
  function accept(data) {
    const snap = data.snapshot || data;
    if (!Array.isArray(snap.items) || !Array.isArray(snap.directions)) throw new Error('组织数据格式不完整，请刷新重试');
    if (S.relationsCorpus !== JSON.stringify(snap.items.map(p => [p.key,p.title,p.abstract,p.topic]))) S.relations = null;
    if (graphSignature(S.snapshot) !== graphSignature(snap)) S.positions = {};
    S.snapshot = snap;
    S.collapsed = new Set((snap.collapsed || []).map(String));
    S.snapshot.positions ||= {};
    const validDirections = new Set(S.snapshot.directions.map(d => String(d.id)));
    const validNodes = new Set(['direction::anchor']);
    S.snapshot.directions.forEach(d => { validNodes.add(`${groupId(d.id)}:anchor`); validNodes.add(groupId(d.id)); });
    S.snapshot.items.forEach(p => validNodes.add(`paper:${p.key}`));
    S.snapshot.items.forEach(p => (memberships(p).length ? memberships(p) : ['']).forEach(id => { if (!id || validDirections.has(id)) validNodes.add(cardId(p.key, id)); }));
    S.validNodes = validNodes;
    S.positions = Object.fromEntries(Object.entries(S.positions).filter(([id]) => validNodes.has(id)));
    if (S.filter && S.filter !== '*' && !snap.directions.some(d => String(d.id) === S.filter)) S.filter = '*';
    S.selected = new Set([...S.selected].filter(key => item(key)));
  }
  function mutate(body, repaint = true) {
    const revision = body.revision ?? S.snapshot.revision;
    S.notice = ''; S.pending++; status();
    const task = S.queue.then(async () => {
      const draftAction = body.action === 'draft-save' || body.action === 'draft-clear';
      const data = await window.PDH.api('/api/organization', { ...body, ...(draftAction ? { version: body.version ?? S.drafts.get(body.key).serverVersion ?? 0 } : {}), ...(body.action === 'note' ? {} : { revision }) });
      if (draftAction) { S.drafts.get(body.key).serverVersion = data.draft.version; cacheDraft(body.key, S.drafts.get(body.key)); }
      else accept(data);
      S.error = '';
      if (repaint) renderData();
      return data;
    });
    S.queue = task.catch(() => {});
    return task.catch(error => { report(error); throw error; }).finally(() => { S.pending--; status(); });
  }
  function draftFor(p) {
    if (!S.drafts.has(p.key)) {
      let saved;
      try { saved = JSON.parse(localStorage.getItem(`pdh.organization.note:${p.key}`)); } catch (_) { /* In-memory drafts remain available when storage is disabled. */ }
      const variants = (S.snapshot.drafts || []).filter(d => d.key === p.key).map(d => ({ text: d.text, version: p.note_version, client: d.client, serverVersion: d.version, dirty: true, recovered: true }));
      const local = saved && typeof saved.text === 'string' && saved.dirty;
      if (!local && variants.length) saved = variants[0];
      if (local && variants.some(d => d.text !== saved.text)) saved.recovered = true;
      S.drafts.set(p.key, saved && typeof saved.text === 'string' && saved.dirty ? { ...saved, dirty: true } : { text: p.note || '', version: p.note_version, dirty: false });
      S.drafts.get(p.key).variants = [...(saved?.variants || []), ...variants];
      S.drafts.get(p.key).client ||= crypto.randomUUID();
      cacheDraft(p.key, S.drafts.get(p.key));
    }
    const draft = S.drafts.get(p.key);
    if (!draft.dirty && !draft.saving) { draft.text = p.note || ''; draft.version = p.note_version; }
    return draft;
  }
  function cacheDraft(key, draft) {
    try { localStorage.setItem(`pdh.organization.note:${key}`, JSON.stringify({ text: draft.text, version: draft.version, dirty: draft.dirty, recovered: !!draft.recovered, client: draft.client, serverVersion: draft.serverVersion, variants: draft.variants || [] })); }
    catch (_) { S.error = '本地草稿存储不可用，请保持页面打开并保存笔记'; status(); }
  }
  function storeDraft(key, draft) {
    cacheDraft(key, draft);
    clearTimeout(draft.remoteTimer);
    if (draft.dirty) draft.remoteTimer = setTimeout(() => persistDraft(key).catch(error => { draft.error = `草稿未持久保存：${error.message}`; noteStatus(key); }), 250);
  }
  async function persistDraft(key) {
    const draft = S.drafts.get(key); clearTimeout(draft.remoteTimer);
    if (!draft.dirty) return;
    if (draft.variants?.some(v => v.client === draft.client && v.text !== draft.text)) { draft.client = crypto.randomUUID(); draft.serverVersion = 0; cacheDraft(key, draft); }
    await mutate({ action: 'draft-save', key, client: draft.client, text: draft.text }, false);
  }
  async function saveNote(key) {
    const draft = S.drafts.get(key);
    if (!draft?.dirty || draft.saving) return;
    clearTimeout(draft.timer);
    if (draft.recovered) { draft.error = '已恢复草稿，请先比较最新笔记并确认保存'; noteStatus(key); return; }
    draft.saving = true; draft.error = '';
    const text = draft.text;
    noteStatus(key);
    try {
      await persistDraft(key);
      await mutate({ action: 'note', key, text, version: draft.version }, false);
      draft.version = item(key)?.note_version;
      draft.dirty = draft.text !== text;
      if (!draft.dirty) await mutate({ action: 'draft-clear', key, client: draft.client, version: draft.serverVersion }, false);
      storeDraft(key, draft);
    } catch (error) { draft.error = `${error.message}。草稿已保留；可查看历史，或刷新后比较版本。`; }
    finally {
      draft.saving = false; noteStatus(key);
      if (draft.dirty && !draft.error) draft.timer = setTimeout(() => saveNote(key), 700);
    }
  }
  function noteStatus(key) {
    if (S.key !== key) return;
    const draft = S.drafts.get(key), node = $('[data-note-status]');
    if (node) {
      node.textContent = draft.error || (draft.recovered ? '已恢复草稿，请先比较最新笔记并确认保存' : draft.saving ? '正在保存…' : draft.dirty ? '草稿未保存' : '已保存'); node.classList.toggle('org-error', !!draft.error);
      if (draft.dirty && (draft.recovered || draft.error || draft.version !== item(key)?.note_version)) {
        const retry = document.createElement('button'); retry.type = 'button'; retry.dataset.action = 'note-rebase'; retry.textContent = '比较最新版本并重试'; node.appendChild(retry);
      }
      if (draft.variants?.length) { const choose = document.createElement('button'); choose.type = 'button'; choose.dataset.action = 'draft-choose'; choose.textContent = '恢复其他草稿'; node.appendChild(choose); }
    }
  }
  function renderShell() {
    S.cy?.destroy(); S.cy = null;
    S.root.classList.add('pdh-organization');
    S.root.innerHTML = `<header class="org-toolbar"><h2>论文整理</h2><div class="org-tabs" role="tablist" aria-label="视图"><button role="tab" data-action="library">论文库</button><button role="tab" data-action="graph">知识图谱</button></div><input class="org-search" type="search" placeholder="搜索论文或笔记" aria-label="搜索论文或笔记" value="${h(S.query)}"><div class="org-tools"><span class="org-undo-slot" data-undo-slot></span><button data-action="suggest"><img src="/icons/sparkles.svg" alt="">整理建议</button>${button('export', '导出', '&#8681;')}</div></header><div class="org-statusbar"><span data-status role="status" aria-live="polite"></span></div><div class="org-workspace"><aside class="org-sidebar" aria-label="类别目录"></aside><main class="org-main"><div class="org-bulk"></div><div class="org-list"></div><div class="org-graph-wrap" hidden><div class="org-graph-tools">${button('rearrange', '重新排列', '&#8862;')}${button('fit', '查看全图', '&#9974;')}${button('zoom-in', '放大', '+')}${button('zoom-out', '缩小', '&#8722;')}</div><div class="org-graph" aria-label="论文关系图谱"></div><div class="org-graph-hint">点击类别定位 · 点击论文查看详情 · 滚轮缩放 / 拖动画布</div><div class="org-graph-legend" aria-label="类别图例" hidden></div></div></main><aside class="org-detail" aria-label="论文详情"></aside></div><div class="org-dialog-host"></div>`;
    S.root.onclick = event => {
      const menu = event.target.closest('.org-category-menu'), b = event.target.closest('[data-action]');
      S.root.querySelectorAll('.org-category-menu[open]').forEach(other => { if (other !== menu || b) other.open = false; });
      if (b && !b.disabled) handle(b.dataset.action, b).catch(report);
    };
    S.root.onkeydown = event => {
      if (event.key === 'Escape') S.root.querySelectorAll('.org-category-menu[open]').forEach(menu => { menu.open = false; menu.querySelector('summary').focus(); event.preventDefault(); });
    };
    S.root.oninput = event => {
      if (event.target.matches('.org-search')) { S.query = event.target.value; renderList(); filterGraph(); }
      if (event.target.matches('[data-note-editor]')) {
        const draft = draftFor(item(S.key)); draft.text = event.target.value; draft.dirty = true; draft.error = ''; storeDraft(S.key, draft);
        clearTimeout(draft.timer); const key = S.key; draft.timer = setTimeout(() => saveNote(key), 900); noteStatus(key);
      }
    };
    S.root.onchange = event => {
      const el = event.target;
      if (el.matches('[data-select-key]')) { el.checked ? S.selected.add(el.dataset.selectKey) : S.selected.delete(el.dataset.selectKey); renderBulk(); }
      if (el.matches('[data-select-all]')) { visible().forEach(p => el.checked ? S.selected.add(p.key) : S.selected.delete(p.key)); renderList(); }
    };
    renderData();
  }
  function renderData() { renderSidebar(); renderList(); renderDetail(); setMode(); renderUndo(); status(); }
  // Only a change the owner made and can recognise is offered, named: never a silent layout save.
  const undoHTML = undo => undo && undo.label ? `<button type="button" class="org-undo" data-action="undo" data-event="${h(undo.id)}" title="撤销：${h(undo.label)}"><img class="org-icon" src="/icons/org/${icons.undo}.svg" width="16" height="16" alt="">撤销${h(undo.label)}</button>` : '';
  function renderUndo() { const slot = $('[data-undo-slot]'); if (slot) slot.innerHTML = undoHTML(S.snapshot.undo); }
  function sidebarHTML() {
    const rows = treeRows();
    const count = id => { const ids = categoryIds(id); return S.snapshot.items.filter(p => memberships(p).some(m => ids.has(m))).length; };
    const graphPaperButton = p => `<button class="org-directory-paper ${S.key === p.key ? 'is-active' : ''}" data-action="graph-paper-focus" data-key="${h(p.key)}" title="${h(p.title || p.key)}"><strong>${h(p.title || p.key)}</strong><span>${h(p.authors?.[0] || p.author || '')}${p.published ? ` · ${h(String(p.published).slice(0,4))}` : ''}</span></button>`;
    const graphPapersUnder = (id, folded) => {
      if (S.mode !== 'graph' || folded) return '';
      const papers = S.snapshot.items.filter(p => id === '' ? !memberships(p).length : memberships(p).includes(String(id))).sort((a, b) => String(a.title || '').localeCompare(String(b.title || '')));
      return papers.length ? `<div class="org-directory-papers" aria-label="${h(id === '' ? '未分类论文' : `${categoryPath(id)} 下的论文`)}">${papers.map(graphPaperButton).join('')}</div>` : '';
    };
    return `<div class="org-section-head org-directory-title"><h3>目录</h3>${button('direction-new','新建类别','')}</div><button class="org-filter ${S.filter === '*' ? 'is-active' : ''}" data-action="filter" data-id="*"><img class="org-folder-icon" src="/icons/org/book-open.svg" alt=""><span>全部论文</span><small>${S.snapshot.items.length}</small></button><div class="org-directory-group org-uncategorized-group"><button class="org-filter ${S.filter === '' ? 'is-active' : ''}" data-action="filter" data-id=""><img class="org-folder-icon" src="/icons/org/folder.svg" alt=""><span>未分类</span><small>${S.snapshot.items.filter(p => !memberships(p).length).length}</small></button>${graphPapersUnder('', false)}</div><div class="org-directions" role="list" aria-label="类别目录">${rows.filter(d => !d.hidden).map(d => {
      const siblings = directions().filter(other => (other.parent_id || null) === (d.parent_id || null)), i = siblings.findIndex(other => other.id === d.id);
      const folded = S.collapsed.has(String(d.id)), selected = S.filter === String(d.id);
      return `<div class="org-directory-group"><div class="org-directory-row ${selected ? 'is-active' : ''}" role="listitem"><span class="org-tree-indent" style="width:${Math.min(d.depth * 16, 80)}px" aria-hidden="true"></span>${d.hasChildren || S.mode === 'graph' ? button('collapse',(folded ? '展开 ' : '折叠 ')+d.name,'',`data-id="${h(d.id)}" aria-expanded="${!folded}"`) : '<span class="org-tree-spacer" aria-hidden="true"></span>'}<button class="org-directory-name" data-action="filter" data-id="${h(d.id)}" title="${h(d.path)}" ${selected ? 'aria-current="page"' : ''}><img class="org-folder-icon" src="/icons/org/${d.hasChildren && !folded ? 'folder-open' : 'folder'}.svg" alt=""><i class="org-category-dot" style="background:${categoryColor(d.id)}" aria-hidden="true"></i><span>${h(d.name)}</span><small>${count(d.id)}</small></button><details class="org-category-menu"><summary aria-label="更多操作 ${h(d.path)}" title="更多操作"><img class="org-icon" src="/icons/org/ellipsis.svg" alt=""></summary><div class="org-category-actions"><div class="org-category-menu-title">${h(d.path)}</div><button type="button" data-action="category-child" data-id="${h(d.id)}">新建子类别</button><button type="button" data-action="direction-edit" data-id="${h(d.id)}">改名或移动</button>${i > 0 ? `<button type="button" data-action="direction-up" data-id="${h(d.id)}">上移</button>` : ''}${i < siblings.length-1 ? `<button type="button" data-action="direction-down" data-id="${h(d.id)}">下移</button>` : ''}<button type="button" class="org-danger" data-action="direction-delete" data-id="${h(d.id)}">删除类别</button></div></details></div>${graphPapersUnder(d.id, folded)}</div>`;
    }).join('') || '<p class="org-directory-empty">还没有类别<br>点击上方 + 建立目录</p>'}</div>`;
  }
  function renderSidebar() { $('.org-sidebar').innerHTML = sidebarHTML(); }
  function renderBulk() {
    const list = visible();
    $('.org-bulk').innerHTML = `<strong class="org-breadcrumb" title="${h(S.filter === '*' ? '全部论文' : S.filter === '' ? '未分类' : categoryPath(S.filter))}">${h(S.filter === '*' ? '全部论文' : S.filter === '' ? '未分类' : categoryPath(S.filter))}</strong><label><input type="checkbox" data-select-all ${list.length && list.every(p => S.selected.has(p.key)) ? 'checked' : ''} aria-label="选择当前列表全部论文"> ${list.length} 篇</label><span>已选 ${S.selected.size}</span><button data-action="membership" ${S.selected.size ? '' : 'disabled'}>编辑类别</button>${S.selected.size ? '<button data-action="clear-selection">清除选择</button>' : ''}`;
    const cb = $('[data-select-all]'); cb.indeterminate = list.some(p => S.selected.has(p.key)) && !list.every(p => S.selected.has(p.key));
  }
  function renderList() {
    renderBulk();
    $('.org-list').innerHTML = visible().map(p => `<article class="org-paper ${S.key === p.key ? 'is-active' : ''}"><input type="checkbox" data-select-key="${h(p.key)}" ${S.selected.has(p.key) ? 'checked' : ''} aria-label="选择 ${h(p.title)}"><button class="org-paper-open" data-action="read" data-key="${h(p.key)}"><strong>${h(p.title || p.key)}</strong><span class="org-paper-meta">${h(p.published || '日期未知')} ${p.note ? ' · 有笔记' : ''}</span><span class="org-tags">${directions().filter(d => memberships(p).includes(String(d.id))).map(d => `<span><i style="background:${categoryColor(d.id)}"></i>${h(categoryPath(d.id))}</span>`).join('')}</span></button><div class="org-paper-actions"><button type="button" data-action="open-detail" data-key="${h(p.key)}" title="打开完整详情：摘要、AI 速览、收藏、所属项目">详情</button><button type="button" data-action="paper-membership" data-key="${h(p.key)}">编辑类别</button>${button('detail', '备注与分类', '', `data-key="${h(p.key)}"`)}</div></article>`).join('') || '<p class="org-empty">没有符合条件的论文</p>';
  }
  // Which categories the open paper belongs to; each chip locates that category, and an
  // uncategorized paper says so instead of showing nothing.
  function detailCategoriesHTML(p) {
    const paperDirections = directions().filter(d => memberships(p).includes(String(d.id)));
    return `<section class="org-detail-categories" aria-label="所属类别"><div class="org-detail-categories-head"><span>所属类别</span><button type="button" class="org-link-button" data-action="paper-membership" data-key="${h(p.key)}">编辑类别</button></div><div class="org-detail-badges">${paperDirections.length ? paperDirections.map(d => `<button type="button" class="org-detail-badge" data-action="filter" data-id="${h(d.id)}" title="查看类别：${h(categoryPath(d.id))}"><i style="background:${categoryColor(d.id)}"></i>${h(categoryPath(d.id))}</button>`).join('') : '<button type="button" class="org-detail-badge is-empty" data-action="filter" data-id="" title="查看未分类论文">未分类</button>'}</div></section>`;
  }
  function renderDetail() {
    const panel = $('.org-detail'), p = item(S.key);
    panel.classList.toggle('has-paper', !!p);
    if (!p) { panel.innerHTML = '<p class="org-empty">选择一篇论文</p>'; return; }
    const draft = draftFor(p);
    const sourceMeta = [p.published, p.source, p.arxiv_id ? `arXiv:${p.arxiv_id}` : '', p.doi ? 'DOI' : ''].filter(Boolean);
    const editor = $('[data-note-editor]');
    const focused = editor && document.activeElement === editor;
    const selection = focused ? [editor.selectionStart, editor.selectionEnd] : null;
    panel.innerHTML = `<div class="org-section-head"><h3>论文详情</h3>${button('detail-close', '关闭详情', '&#215;')}</div><h2 class="org-detail-title">${h(p.title)}</h2><div class="org-detail-meta">${sourceMeta.map(h).map(v => `<span>${v}</span>`).join('')}</div>${detailCategoriesHTML(p)}<details class="org-abstract" open><summary>摘要</summary><p>${h(p.abstract || '暂无摘要')}</p></details><section class="org-notes"><div class="org-section-head"><h3>笔记</h3><div class="org-tools"><button data-action="note-edit" aria-pressed="true">编辑</button><button data-action="note-preview" aria-pressed="false">预览</button>${button('history', '笔记历史', '&#9719;')}${button('note-save', '保存笔记', '&#10003;')}</div></div><textarea data-note-editor aria-label="Markdown 笔记" placeholder="写下笔记…">${h(draft.text)}</textarea><div class="org-markdown" data-note-preview hidden></div><div data-note-status role="status" class="org-note-status"></div></section>`;
    const reading = document.createElement('div'); reading.className = 'org-reading-tools';
    const read = document.createElement('button'); read.type = 'button'; read.innerHTML = '<img class="org-icon" src="/icons/org/book-open.svg" width="16" height="16" alt="">阅读 PDF';
    read.disabled = typeof window.PDH.openReader !== 'function';
    read.title = read.disabled ? '阅读器尚未加载，请刷新' : '阅读 PDF';
    read.onclick = () => window.PDH.openReader(p.key, p.title); reading.append(read);
    const full = document.createElement('button'); full.type = 'button'; full.dataset.action = 'open-detail'; full.dataset.key = p.key; full.textContent = '完整详情';
    full.title = '打开完整详情：AI 速览、收藏、所属项目'; reading.append(full);
    const url = paperURL(p);
    if (url) { const link = document.createElement('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = '打开论文'; reading.append(link); }
    panel.querySelector('.org-detail-categories').after(reading);
    if (selection) { $('[data-note-editor]').focus(); $('[data-note-editor]').setSelectionRange(...selection); }
    noteStatus(p.key);
  }
  function setMode() {
    const graph = S.mode === 'graph';
    $('.org-list').hidden = graph; $('.org-graph-wrap').hidden = !graph;
    for (const el of S.root.querySelectorAll('[role=tab]')) { el.setAttribute('aria-selected', String(el.dataset.action === S.mode)); el.classList.toggle('is-active', el.dataset.action === S.mode); }
    if (graph && !S.loading) renderGraph(); else { S.cy?.destroy(); S.cy = null; }
  }
  function capturePositions() {
    if (S.renderedSignature !== graphSignature(S.snapshot)) return;
    S.cy?.nodes().forEach(n => { if (!n.isParent() && S.validNodes?.has(n.id())) S.positions[n.id()] = graphPosition(n); });
  }
  function graphPosition(node) { return S.motion?.position(node) || {...node.position()}; }
  const paperNodeId = key => `paper:${key}`;
  // Categories keep one hue; publication year only changes the lightness.
  // This mirrors Connected Papers' visual grammar while remaining deterministic
  // when an imported category does not have a saved color. Saturation is capped
  // low so the graph reads as ink on paper, not a colour chart.
  const _categoryHues = [214, 18, 152, 40, 262, 188, 336, 90, 2, 232];
  function _hexHsl(value) {
    const hex = String(value || '').replace('#', '');
    if (!/^[0-9a-f]{6}$/i.test(hex)) return null;
    const r = parseInt(hex.slice(0, 2), 16) / 255, g = parseInt(hex.slice(2, 4), 16) / 255, b = parseInt(hex.slice(4, 6), 16) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    let hue = 0;
    if (d) {
      if (max === r) hue = ((g - b) / d) % 6;
      else if (max === g) hue = (b - r) / d + 2;
      else hue = (r - g) / d + 4;
      hue = Math.round(hue * 60); if (hue < 0) hue += 360;
    }
    const lightness = (max + min) / 2;
    const saturation = d ? d / (1 - Math.abs(2 * lightness - 1)) : 0;
    return { hue, saturation: Math.round(saturation * 100), lightness: Math.round(lightness * 100) };
  }
  function _nodeColor(paper, category, yearRange = {}) {
    const fallbackHue = _categoryHues[Math.max(0, Number(category?.index) || 0) % _categoryHues.length];
    // The stored default slate means "no colour chosen"; otherwise every such category shares one hue.
    const chosen = String(category?.color || '').toLowerCase() === DEFAULT_COLOR ? null : _hexHsl(category?.color);
    const base = chosen || { hue: fallbackHue, saturation: 34, lightness: 48 };
    const published = parseInt(String(paper.published || '').slice(0, 4), 10);
    const year = Number.isFinite(published) ? published : (yearRange.max || new Date().getFullYear());
    const minYear = yearRange.min ?? year, maxYear = yearRange.max ?? year;
    const yearProgress = maxYear > minYear ? Math.max(0, Math.min(1, (year - minYear) / (maxYear - minYear))) : 0.5;
    // Newer papers are darker; clamp to keep labels and node edges legible.
    const lightness = Math.round(68 - yearProgress * 30);
    const saturation = Math.max(20, Math.min(38, base.saturation || 34));
    return `hsl(${base.hue},${saturation}%,${lightness}%)`;
  }
  // Mid-age tone of a category's graph hue, shared by the directory, list tags and detail pane.
  function categoryColor(id) {
    const rows = treeRows(), index = rows.findIndex(r => String(r.id) === String(id));
    return index < 0 ? _nodeColor({}, { index: 0 }) : _nodeColor({}, { ...rows[index], index });
  }
  function graphLabel(paper) {
    const title = String(paper.title || paper.key || '').replace(/\s+/g, ' ').trim();
    const year = String(paper.published || '').slice(0, 4);
    // Metadata currently has no author column, so use a short title anchor until author import exists.
    const anchor = title.split(':')[0].split('—')[0].trim();
    const short = anchor.length > 22 ? `${anchor.slice(0, 21).trim()}…` : anchor;
    return year ? `${short}, ${year}` : short;
  }
  function radialPositions(nodes, originId) {
    const dataOf = node => typeof node.data === 'function' ? node.data() : (node.data || {});
    const idOf = node => dataOf(node).id;
    const origin = nodes.find(n => idOf(n) === originId) || nodes[0];
    const rest = nodes.filter(n => n !== origin).sort((a, b) => (dataOf(b).degree || 0) - (dataOf(a).degree || 0));
    const out = {};
    if (!origin) return out;
    out[idOf(origin)] = { x: 0, y: 0 };
    const rings = [];
    let cursor = 0, remaining = rest.length;
    for (let ring = 0; remaining > 0; ring++) {
      const count = Math.min(8 + ring * 6, remaining);
      const radius = 190 + ring * 165;
      rings.push({ count, radius }); remaining -= count;
    }
    for (const ring of rings) {
      for (let i = 0; i < ring.count; i++) {
        const n = rest[cursor++], angle = -Math.PI / 2 + (i / ring.count) * Math.PI * 2 + (ring.count % 2 ? 0.12 : 0);
        out[idOf(n)] = { x: Math.cos(angle) * ring.radius, y: Math.sin(angle) * ring.radius };
      }
    }
    return out;
  }
  function networkElements(snapshot, relations, positions = {}, revealed = new Set()) {
    const papers = snapshot.items || [], rows = treeRows(snapshot);
    const collapsed = new Set(snapshot.collapsed || []);
    const groupIds = new Set(rows.filter(d => !d.hidden).map(d => String(d.id)));
    const shown = papers.filter(p =>
      revealed.has(p.key) || !memberships(p).length || memberships(p).some(id => groupIds.has(id) && !collapsed.has(id))
    );
    const present = new Set(shown.map(p => p.key)), elements = [];
    // degree from similarity edges — proxy for how prominent a paper is in this corpus
    const deg = new Map(shown.map(p => [p.key, 0]));
    (relations?.edges || []).forEach(e => {
      if (present.has(e.source) && present.has(e.target)) {
        deg.set(e.source, (deg.get(e.source) || 0) + 1);
        deg.set(e.target, (deg.get(e.target) || 0) + 1);
      }
    });
    const years = shown.map(p => parseInt(String(p.published || '').slice(0, 4), 10)).filter(Number.isFinite);
    const yearRange = { min: years.length ? Math.min(...years) : new Date().getFullYear(), max: years.length ? Math.max(...years) : new Date().getFullYear() };
    shown.forEach(p => {
      const id = paperNodeId(p.key), d = deg.get(p.key) || 0;
      const row = rows.find(r => memberships(p).includes(String(r.id)));
      const category = row ? { ...row, index: rows.indexOf(row) } : { index: 0 };
      elements.push({ data: { id, key: p.key, label: graphLabel(p), degree: d, color: _nodeColor(p, category, yearRange), size: Math.round(28 + Math.min(24, d * 3)) }, ...(positions[id] ? { position: { ...positions[id] } } : {}) });
    });
    const linked = new Set();
    (relations?.edges || []).forEach((edge, i) => {
      if (edge.source !== edge.target && present.has(edge.source) && present.has(edge.target)) {
        linked.add([edge.source, edge.target].sort().join('\0'));
        elements.push({ data: { id: `similar:${i}`, source: paperNodeId(edge.source), target: paperNodeId(edge.target), kind: 'similarity', color: '#a89e8b', weight: edge.weight } });
      }
    });
    // Keep the graph readable when the similarity worker returns a sparse result: connect a bounded
    // number of papers that share a saved direction. This is an organization relation, never a citation claim.
    let categoryEdge = 0;
    for (let i = 0; i < shown.length; i++) for (let j = i + 1; j < shown.length; j++) {
      const a = shown[i], b = shown[j], key = [a.key, b.key].sort().join('\0');
      if (linked.has(key) || !memberships(a).some(id => memberships(b).includes(id))) continue;
      elements.push({ data: { id: `category:${categoryEdge++}`, source: paperNodeId(a.key), target: paperNodeId(b.key), kind: 'category', color: '#cbbfa9', weight: 0.22 } });
      linked.add(key);
    }
    return elements;
  }
  function graphStyle(transition) {
    const paper = theme('--surface-1', '#fbf8f2'), ink = theme('--text', '#1c2230'),
      muted = theme('--muted', '#5e5a52'), mark = theme('--mark', '#d9462b');
    return [
      { selector: 'node', style: { shape: 'ellipse', width: 'data(size)', height: 'data(size)', 'background-color': 'data(color)', 'border-color': paper, 'border-width': 2, label: 'data(label)', color: ink, 'font-size': 14, 'font-weight': 500, 'text-wrap': 'ellipsis', 'text-max-width': 150, 'text-valign': 'bottom', 'text-margin-y': 8, 'text-background-color': paper, 'text-background-opacity': 0.82, 'text-background-padding': 2, 'transition-property': 'opacity, border-color, border-width', 'transition-duration': transition } },
      { selector: 'node.org-current, node:selected, node.org-connected', style: { 'text-background-opacity': 0.95, 'text-background-padding': 3 } },
      { selector: 'edge', style: { width: 'mapData(weight, 0, 1, 0.6, 2.4)', 'line-color': 'data(color)', opacity: 'mapData(weight, 0, 1, 0.18, 0.72)', 'curve-style': 'straight', 'transition-property': 'opacity, line-color, width', 'transition-duration': transition } },
      { selector: '.org-dim', style: { opacity: 0.2 } },
      { selector: '.org-leaving', style: { opacity: 0 } },
      { selector: '.org-current, :selected', style: { 'border-color': ink, 'border-width': 3 } },
      { selector: 'edge.org-connected', style: { opacity: 1, 'line-color': muted, width: 2 } },
      { selector: 'node.org-focused, node.org-dragging, node.org-pulse', style: { 'border-color': ink, 'border-width': 4, 'overlay-color': 'data(color)', 'overlay-opacity': 0.12, 'overlay-padding': 9, 'overlay-shape': 'ellipse' } },
      { selector: 'node.org-focused', style: { 'font-size': 16, 'font-weight': 650, 'text-max-width': 180, 'text-background-opacity': 1 } },
      { selector: 'node.org-origin', style: { 'border-color': mark, 'border-width': 5, 'overlay-color': mark, 'overlay-opacity': 0.18, 'overlay-padding': 8 } },
      { selector: 'edge.org-pulse', style: { opacity: 1, width: 2.5 } }
    ];
  }
  // index.html announces light/dark switches; restyle a live graph instead of rebuilding it.
  window.addEventListener('pdh-mode', () => {
    if (S.cy) S.cy.style(graphStyle(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? '0ms' : '180ms'));
  });
  function renderGraphLegend() {
    const legend = $('.org-graph-legend');
    if (!legend) return;
    const rows = treeRows();
    if (!rows.length) { legend.hidden = true; return; }
    legend.hidden = false;
    legend.innerHTML = rows.slice(0, 10).map((d, i) =>
      `<div class="org-graph-legend-item"><span class="org-graph-legend-dot" style="background:${categoryColor(d.id)}"></span><span>${h(d.name)}</span></div>`
    ).join('');
  }
  async function loadRelations() {
    if (S.relationsLoading) { S.relationsReload = true; return; }
    const corpus = JSON.stringify(S.snapshot.items.map(p => [p.key,p.title,p.abstract,p.topic]));
    if (S.relations && S.relationsCorpus === corpus) return;
    S.relations = null;
    S.relationsLoading = true;
    try {
      let { job } = await window.PDH.api('/api/organization', { action: 'graph' });
      while (job.state === 'running') {
        await new Promise(resolve => setTimeout(resolve, 500));
        job = await window.PDH.api(`/api/jobs/${encodeURIComponent(job.id)}`);
      }
      if (job.state !== 'done') throw new Error(job.error || '相似关系计算失败');
      if (corpus !== JSON.stringify(S.snapshot.items.map(p => [p.key,p.title,p.abstract,p.topic]))) return;
      S.relations = job.result.relations; S.relationsCorpus = corpus;
      if (S.mode === 'graph' && !S.root.classList.contains('hidden')) {
        await S.positionQueue;
        if(S.graphDragging) S.relationsPending=true; else renderGraph();
      }
    } catch (error) { report(new Error(`相似关系未加载：${error.message}；现有分类关系仍可查看`)); }
    finally {
      S.relationsLoading = false;
      const changed = corpus !== JSON.stringify(S.snapshot.items.map(p => [p.key,p.title,p.abstract,p.topic]));
      if (S.relationsReload || changed) {
        S.relationsReload = false;
        if (S.mode === 'graph') await loadRelations();
      }
    }
  }
  // The node the camera starts from: the paper being read when it is drawn, otherwise the first node. The paper may
  // be missing (its category is collapsed, it was removed, or it was chosen under another project); a node that
  // does not exist must never be the origin.
  function graphOrigin(nodes, key) {
    const present = new Set(nodes.map(n => n.data.id));
    return key && present.has(paperNodeId(key)) ? paperNodeId(key) : nodes[0]?.data.id;
  }
  function renderGraph(persistInitial = true) {
    capturePositions();
    S.relationsPending=false;
    const previousElements = S.graphSeen || new Set();
    const prior = S.cy ? { zoom: S.cy.zoom(), pan: { ...S.cy.pan() } } : null;
    S.cy?.destroy(); S.cy = null;
    const container = $('.org-graph'); container.innerHTML = '';
    if (!window.cytoscape) { container.innerHTML = '<p class="org-empty org-error">图谱组件未加载，请刷新重试</p>'; return; }
    if (!S.snapshot.items.length) { container.innerHTML = '<p class="org-empty">暂无已收藏论文</p>'; return; }
    const forceRadial = S.graphRadialPending && !!S.relations;
    const positions = forceRadial ? {} : { ...S.snapshot.positions, ...S.positions };
    const revealed = S.filter !== '*' ? new Set(visible().map(p => p.key)) : new Set();
    const elements = networkElements(S.snapshot, S.relations, positions, revealed);
    const nodes = elements.filter(e => !e.data.source), allPlaced = !forceRadial && nodes.every(n => n.position);
    const hasPlaced = nodes.some(n => n.position);
    if (hasPlaced) {
      nodes.filter(n => !n.position).forEach((n, i) => {
        const link = elements.find(e => e.data.target === n.data.id && nodes.some(a => a.data.id === e.data.source && a.position));
        const anchor = nodes.find(a => a.data.id === link?.data.source)?.position || nodes.find(a => a.position).position;
        const angle = i * 2.399963, radius = 150 + 45 * Math.sqrt(i);
        n.position = { x: anchor.x + Math.cos(angle) * radius, y: anchor.y + Math.sin(angle) * radius };
      });
    }
    S.renderedSignature = graphSignature(S.snapshot);
    const transition = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? '0ms' : '180ms';
    container.setAttribute('aria-label', `论文关系网络，${nodes.length} 个节点，${elements.length - nodes.length} 条关系`);
    S.cy = window.cytoscape({ container, elements,
      // Positions are assigned below by the bounded radial layout. Do not start
      // CoSE here: its asynchronous relaxation can move nodes after the camera
      // is centered and scatter the first view out of frame.
      layout: { name: 'preset' },
      minZoom: 0.08, maxZoom: 3, wheelSensitivity: 0.18, boxSelectionEnabled: true,
      style: graphStyle(transition) });
    const originId = graphOrigin(nodes, S.key);
    if (!allPlaced) {
      const radial = radialPositions(S.cy.nodes().toArray(), originId);
      S.cy.nodes().forEach(n => { if (radial[n.id()]) n.position(radial[n.id()]); });
    }
    S.motion = window.PDHGraphMotion?.create(S.cy, {reduced:()=>window.matchMedia?.('(prefers-reduced-motion: reduce)').matches});
    if (originId) S.cy.getElementById(originId).addClass('org-origin');
    if (forceRadial) S.graphRadialPending = false;
    if (prior && allPlaced) { S.cy.zoom(prior.zoom); S.cy.pan(prior.pan); }
    else if (forceRadial && originId) {
      const origin = S.cy.getElementById(originId), p = origin.length ? origin.position() : { x: 0, y: 0 }, zoom = Math.min(0.84, S.cy.maxZoom());
      S.cy.viewport({ zoom, pan: { x: S.cy.width()/2 - p.x*zoom, y: S.cy.height()/2 - p.y*zoom } });
    } else {
      const keys = new Set(visible().map(p => p.key));
      const initial = S.cy.nodes().filter(n => keys.has(n.data('key')));
      const target = graphViewport(initial.length ? initial : S.cy.nodes());
      if (target) S.cy.viewport(target);
    }
    S.cy.nodes().forEach(n => { if (S.selected.has(n.data('key'))) n.select(); });
    let before;
    S.cy.on('tap', 'node', e => {
      if (e.target.data('key')) { S.key = e.target.data('key'); renderSidebar(); renderDetail(); renderList(); S.root.querySelector('.org-directory-paper.is-active')?.scrollIntoView?.({ block: 'nearest' }); }
      else { S.filter = e.target.data('direction'); renderSidebar(); }
      filterGraph(); focusGraph(e.target.id());
    });
    S.cy.on('mouseover', 'node', e => {
      S.cy.elements().addClass('org-dim'); e.target.closedNeighborhood().removeClass('org-dim').addClass('org-connected');
      container.title = e.target.data('key') ? item(e.target.data('key'))?.title || '' : e.target.data('label');
    });
    S.cy.on('mouseout', 'node', () => { container.title = ''; highlightGraph(); });
    S.cy.on('mouseover', 'edge', e => { container.title = e.target.data('kind') === 'similarity' ? `内容相似度 ${Math.round(e.target.data('weight') * 100)}%（非引用关系）` : e.target.data('kind') === 'category' ? '同一研究方向（非引用关系）' : e.target.data('kind') === 'hierarchy' ? '类别上下级关系' : '研究方向归属'; });
    S.cy.on('select unselect', 'node', () => { syncGraphSelection(S.cy.nodes()); renderBulk(); });
    const cy = S.cy;
    const writer = positionWriter(S.snapshot.revision, data => { if (data && S.cy === cy) { S.renderedSignature = graphSignature(S.snapshot); capturePositions(); } });
    const savePositions = positions => {
      S.positionQueue = writer(positions).catch(() => { if (S.cy === cy) { S.positions = {}; cy.destroy(); S.cy = null; renderGraph(); } });
      return S.positionQueue;
    };
    bindGraphDrag(cy, e => { S.graphDragging=true; S.motion?.begin(e.target); cy.stop(true,false); capturePositions(); before={...S.positions}; },
      e => S.motion?.drag(e.target), e => {
      S.graphDragging=false;
      S.motion?.end(e.target);
      const after = {}; cy.nodes().forEach(n => { after[n.id()] = graphPosition(n); });
      savePositions(changedPositions(before || {}, after)).then(()=>{
        if(S.cy===cy && S.relationsPending && !S.graphDragging) renderGraph();
      });
    }, e => {
      S.graphDragging=false;
      if(e.type==='destroy') return;
      S.motion?.cancelGrab();
      Promise.resolve().then(async()=>{
        await S.positionQueue;
        if(S.cy===cy && S.relationsPending && !S.graphDragging) renderGraph();
      });
    });
    if (persistInitial && !allPlaced && S.relations) {
      const initial = {};
      S.cy.nodes().forEach(n => { initial[n.id()] = graphPosition(n); });
      savePositions(initial);
      if (forceRadial) localStorage.setItem('pdh-graph-layout-v3', '1');
    }
    highlightGraph();
    renderGraphLegend();
    S.motion?.enter(previousElements);
    S.graphSeen = new Set(S.cy.elements().map(e=>e.id()));
    S.resizeObserver?.disconnect(); S.resizeObserver = new ResizeObserver(() => S.cy?.resize()); S.resizeObserver.observe(container);
  }
  function graphSignature(snap) { return JSON.stringify([snap.positions || {}, snap.directions || [], (snap.items || []).map(p => [p.key, p.directions]), snap.collapsed || []]); }
  function bindGraphDrag(cy, begin, drag, end, cancel = () => {}) {
    let moved=false;
    cy.on('grabon','node',e=>{moved=false;begin(e);});
    cy.on('drag','node',e=>{moved=true;drag(e);});
    cy.on('dragfreeon','node',end);
    cy.on('freeon','node',e=>{if(!moved) cancel(e);});
    cy.on('destroy',cancel);
  }
  function positionWriter(revision, acknowledge = () => {}) {
    let queue = Promise.resolve();
    return positions => {
      queue = queue.then(async () => {
        const data = await mutate({ action: 'positions', positions, revision }, false);
        revision = data.revision; acknowledge(data); return data;
      });
      return queue;
    };
  }
  function changedPositions(before, after) { return Object.fromEntries(Object.entries(after).filter(([id, p]) => !before[id] || p.x !== before[id].x || p.y !== before[id].y)); }
  function persistPositions(before, revision) {
    capturePositions();
    const positions = Object.fromEntries(Object.entries(S.positions).filter(([id]) => S.validNodes?.has(id)));
    S.cy?.nodes().forEach(n => { if (!n.isParent()) positions[n.id()] = graphPosition(n); });
    const changed = changedPositions(before || {}, positions);
    return Object.keys(changed).length ? mutate({ action: 'positions', positions: changed, revision }) : Promise.resolve();
  }
  function filterGraph() {
    const keys = new Set(visible().map(p => p.key));
    S.cy?.nodes().forEach(n => { const p = item(n.data('key')); n.toggleClass('org-dim', !!p && !keys.has(p.key)); n.toggleClass('org-current', !!p && p.key === S.key); });
  }
  function highlightGraph() {
    const cy = S.cy; if (!cy) return;
    cy.elements().removeClass('org-dim org-connected org-focused');
    const node = S.graphFocus ? cy.getElementById(S.graphFocus) : null;
    if (node?.length) {
      cy.elements().addClass('org-dim');
      node.closedNeighborhood().removeClass('org-dim').addClass('org-connected');
      node.addClass('org-focused');
    } else filterGraph();
  }
  // Keep reading views legible. Only the explicit overview may shrink the whole corpus.
  function graphViewport(nodes, overview = false) {
    const cy = S.cy;
    if (!cy || !nodes.length) return null;
    const b = nodes.boundingBox({ includeLabels: true });
    const fit = Math.min((cy.width() - 100) / Math.max(1, b.w), (cy.height() - 140) / Math.max(1, b.h));
    const zoom = Math.max(cy.minZoom(), Math.min(cy.maxZoom(), overview ? Math.min(1.15, fit) : Math.max(0.9, Math.min(1.15, fit))));
    let center = { x: (b.x1 + b.x2)/2, y: (b.y1 + b.y2)/2 };
    // A large saved layout can have an empty center. Anchor to an actual paper.
    if (!overview && fit < 0.9) {
      let closest, distance = Infinity;
      nodes.forEach(n => { const p = n.position(), d = (p.x-center.x)**2 + (p.y-center.y)**2; if (d < distance) { closest = p; distance = d; } });
      if (closest) center = closest;
    }
    return { zoom, pan: { x: cy.width()/2-center.x*zoom, y: cy.height()/2-center.y*zoom } };
  }
  function focusCategory() {
    const cy = S.cy; if (!cy) return;
    S.graphFocus = null; highlightGraph(); cy.resize();
    const keys = new Set(visible().map(p => p.key));
    const nodes = cy.nodes().filter(n => keys.has(n.data('key')));
    const target = graphViewport(nodes);
    S.notice = nodes.length ? `${visible().length} 篇论文 · 已定位，滚轮缩放或拖动画布浏览` : '当前类别或搜索没有可显示的论文';
    status();
    if (target) animateViewport(target);
  }
  function focusGraph(id) {
    const cy = S.cy; if (!cy) return;
    S.graphFocus = id; highlightGraph(); cy.resize();
    const node = id ? cy.getElementById(id) : null;
    S.motion?.pulse(node);
    let target;
    if (node?.length) {
      const p = node.position(), zoom = Math.min(cy.maxZoom(), Math.max(1.15, Math.min(1.5, cy.zoom())));
      target = { zoom, pan: { x: cy.width()/2-p.x*zoom, y: cy.height()/2-p.y*zoom } };
    } else target = graphViewport(cy.nodes(), true);
    if (target) animateViewport(target);
  }
  function animateViewport(target) {
    const cy = S.cy; if (!cy) return;
    cy.stop(true, false);
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) cy.viewport(target);
    else cy.animate(target, { duration: 550, easing: 'ease-in-out-cubic', queue: false });
  }
  function zoomGraph(factor) {
    const cy = S.cy; if (!cy) return;
    const zoom = Math.max(cy.minZoom(), Math.min(cy.maxZoom(), cy.zoom() * factor));
    const ratio = zoom / cy.zoom(), pan = cy.pan();
    animateViewport({ zoom, pan: { x: cy.width()/2 + (pan.x-cy.width()/2)*ratio, y: cy.height()/2 + (pan.y-cy.height()/2)*ratio } });
  }
  function syncGraphSelection(nodes) {
    const represented = new Set(nodes.map(n => n.data('key')).filter(Boolean));
    represented.forEach(key => S.selected.delete(key));
    nodes.forEach(n => { if (n.data('key') && n.selected()) S.selected.add(n.data('key')); });
  }
  function closeDialog(d, host, previous) {
    d.remove();
    if (!host.querySelector('dialog')) previous?.focus();
  }
  function confirmDraftVersion(key, comparedVersion) {
    const draft = S.drafts.get(key);
    draft.version = comparedVersion; draft.recovered = false; draft.error = '';
  }
  function chooseDraftVariant(key, candidate) {
    const draft = S.drafts.get(key);
    clearTimeout(draft.timer); clearTimeout(draft.remoteTimer);
    const variants = [...(draft.variants || []), { text: draft.text, version: draft.version, client: draft.client, serverVersion: draft.serverVersion }];
    Object.assign(draft, { text: candidate.text, version: candidate.version, client: crypto.randomUUID(), serverVersion: 0, dirty: true, recovered: true, error: '', variants });
    cacheDraft(key, draft);
  }
  function safePaperURL(value) {
    try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
    catch (_) { return null; }
  }
  function paperURL(paper) {
    const direct = safePaperURL(paper?.url || paper?.source_url || paper?.landing_page_url);
    if (direct) return direct;
    if (paper?.arxiv_id) return `https://arxiv.org/abs/${encodeURIComponent(String(paper.arxiv_id))}`;
    if (paper?.doi) {
      const doi = String(paper.doi).replace(/^https?:\/\/doi\.org\//i, '').replace(/^doi:/i, '');
      return doi ? `https://doi.org/${encodeURIComponent(doi).replace(/%2F/g, '/')}` : null;
    }
    return safePaperURL(paper?.openalex_id);
  }
  function dialog(title, body, submitLabel, submit) {
    const host = $('.org-dialog-host'), previous = document.activeElement;
    host.innerHTML = `<dialog class="org-dialog"><form><div class="org-section-head"><h3>${h(title)}</h3>${button('dialog-close', '关闭', '&#215;')}</div><div class="org-dialog-body">${body}</div><p class="org-dialog-error" role="alert"></p><footer><button type="button" data-action="dialog-close">取消</button>${submitLabel ? `<button type="submit" class="org-primary">${h(submitLabel)}</button>` : ''}</footer></form></dialog>`;
    const d = host.querySelector('dialog');
    d.dataset.revision = String(S.snapshot.revision);
    d.addEventListener('close', () => closeDialog(d, host, previous));
    d.querySelector('form').onsubmit = async e => {
      e.preventDefault(); const b = d.querySelector('[type=submit]'); b.disabled = true;
      try { await submit(d); d.close(); } catch (error) { d.querySelector('.org-dialog-error').textContent = error.message; b.disabled = false; }
    };
    d.showModal(); return d;
  }
  function editDirection(id, parentId = null) {
    const revision = S.snapshot.revision;
    const d = directions().find(d => String(d.id) === id), excluded = d ? categoryIds(id) : new Set();
    const parent = d ? d.parent_id : parentId;
    dialog(d ? '编辑类别' : '新建类别', `<label>名称<input name="name" required maxlength="120" value="${h(d?.name || '')}"></label><label>上级类别<select name="parent"><option value="">顶层目录</option>${treeRows().filter(row => !excluded.has(String(row.id))).map(row => `<option value="${h(row.id)}" ${String(parent) === String(row.id) ? 'selected' : ''}>${h(row.path)}</option>`).join('')}</select></label><label>颜色<input name="color" type="color" value="${color(d?.color)}"></label>${d ? `<button type="button" class="org-danger" data-action="direction-delete" data-id="${h(id)}">删除此类别</button>` : ''}`, '保存类别', async el => {
      const name = el.querySelector('[name=name]').value.trim(); if (!name) throw new Error('请输入类别名称');
      await mutate({ action: 'direction-save', revision, ...(d ? { id: d.id, rank: d.rank } : {}), name, color: el.querySelector('[name=color]').value, parent_id: el.querySelector('[name=parent]').value || null });
    });
  }
  function deleteDirection(id) {
    const d = directions().find(row => String(row.id) === id); if (!d) throw new Error('类别不存在，请刷新');
    const revision = S.snapshot.revision;
    const children = directions().filter(row => row.parent_id === d.id).length;
    const count = S.snapshot.items.filter(p => memberships(p).includes(id)).length;
    dialog('删除类别', `<p>删除「${h(categoryPath(id))}」？</p><p>只解除 ${count} 篇已收藏论文与此类别的直接归属，论文、PDF、笔记和其他类别归属均保留。</p><p>${children ? `${children} 个直接子类别会移到${d.parent_id ? '「'+h(categoryPath(d.parent_id))+'」下' : '顶层目录'}。` : '此类别没有子类别。'}可以使用「撤销上一步」恢复。</p>`, '删除类别并保留论文', async () => {
      await mutate({ action:'direction-delete', id, revision });
    });
  }
  function editMembership(keys) {
    const revision = S.snapshot.revision, single = keys.length === 1;
    const rows = treeRows();
    const before = new Set(single ? memberships(item(keys[0])) : []);
    const body = `<p>${single ? '勾选需要归属的类别；取消勾选即可移除已有归属。' : '批量操作只修改你明确选择的类别，其他归属保持不变。'}同一篇论文可同时属于多个子类别。移除后不再包含论文的类别会自动删除，可用「撤销上一步」恢复。</p>` + (rows.map(d => single ? `<label class="org-membership-row"><input type="checkbox" data-membership="${h(d.id)}" ${before.has(String(d.id)) ? 'checked' : ''}><i style="background:${categoryColor(d.id)}"></i><span>${h(d.path)}</span></label>` : `<label class="org-membership-row"><i style="background:${categoryColor(d.id)}"></i><span>${h(d.path)}</span><select data-membership="${h(d.id)}" aria-label="${h(d.path)}"><option value="">保持 (${keys.filter(k => memberships(item(k)).includes(String(d.id))).length}/${keys.length})</option><option value="add">添加</option><option value="remove">移除</option></select></label>`).join('') || '<p>还没有类别，请先新建类别。</p><button type="button" data-action="direction-new">新建类别</button>');
    dialog(`编辑类别 · ${keys.length} 篇`, body, '保存归属', async el => {
      const add = [], remove = [];
      el.querySelectorAll('[data-membership]').forEach(field => {
        const id = field.dataset.membership;
        if (single) { if (field.checked && !before.has(id)) add.push(id); if (!field.checked && before.has(id)) remove.push(id); }
        else { if (field.value === 'add') add.push(id); if (field.value === 'remove') remove.push(id); }
      });
      if (add.length || remove.length) await mutate({ action:'membership', revision, keys, add, remove });
    });
  }
  async function history() {
    const key = S.key, result = await window.PDH.api('/api/organization', { action: 'history', key });
    const rows = result.history || [];
    const d = dialog('笔记历史', rows.map((r, i) => `<section class="org-history-entry"><div class="org-section-head"><span>版本 ${h(r.version ?? r.note_version)} · ${h(r.created_at || r.created || '')}</span><button type="button" data-history-restore="${i}">恢复到草稿</button></div><div class="org-markdown">${window.PDH.md(r.text ?? r.note ?? '')}</div></section>`).join('') || '<p>暂无历史版本</p>', null);
    d.querySelectorAll('[data-history-restore]').forEach(b => b.onclick = () => {
      const draft = draftFor(item(key));
      if (draft.dirty && !window.confirm('替换当前未保存的草稿？')) return;
      draft.text = rows[Number(b.dataset.historyRestore)].text ?? rows[Number(b.dataset.historyRestore)].note ?? '';
      draft.version = item(key).note_version; draft.dirty = true; draft.error = ''; storeDraft(key, draft); d.close(); renderDetail();
    });
  }
  // Profile first: pinned terms are the top level, repeated title phrases subdivide them.
  function suggestionsHTML(preview, lookup = item) {
    const groups = preview.groups || [], profile = preview.profile || {}, index = new Map(groups.map((g, i) => [g.id, i]));
    const depth = g => { let n = 0, p = g.parent; while (p != null && index.has(p) && n < 4) { n++; p = groups[index.get(p)].parent; } return n; };
    const pinned = (profile.pinned || []).map(h).join('、');
    const basis = pinned ? `<p class="org-paper-meta">依据${profile.project ? `「${h(profile.project)}」` : '当前项目'}画像的固定关键词：${pinned}。一级类别来自这些关键词；类别内部再按标题里反复出现的短语细分。</p>`
      : `<p class="org-paper-meta">${profile.project ? `「${h(profile.project)}」` : '当前项目'}还没有固定关键词，先按标题里反复出现的短语分组。在“画像”页固定关键词后再生成，会以它们为一级类别。</p>`;
    const unmatched = (profile.unmatched || []).map(u => u.same_as ? `${h(u.term)}（与「${h(u.same_as)}」基本是同一批论文）` : u.dropped ? `${h(u.term)}（${Number(u.documents) || 0} 篇提到，超出 12 个一级类别上限）` : `${h(u.term)}（${u.documents ? `只有 ${u.documents} 篇提到` : '没有论文提到'}）`);
    const members = keys => `<details class="org-suggestion-members-wrap"><summary>${keys.length} 篇论文 · 查看或取消</summary><div class="org-suggestion-members">${keys.map(k => `<label><input type="checkbox" data-member="${h(k)}" checked><span>${h(lookup(k)?.title || k)}</span></label>`).join('')}</div></details>`;
    const cards = groups.map((g, i) => { const level = depth(g), parent = level ? groups[index.get(g.parent)] : null;
      return `<fieldset class="org-suggestion${level ? ' is-child' : ''}" data-suggestion="${i}" style="--depth:${level}"><div class="org-suggestion-head"><input type="checkbox" data-enabled checked aria-label="采用此类别">${parent ? `<span class="org-suggestion-parent">${h(parent.name)} ›</span>` : ''}<input data-name aria-label="类别名称" value="${h(g.name)}" required maxlength="120"><input type="color" data-color aria-label="类别颜色" value="${color(g.color || DEFAULT_COLOR)}"></div><p class="org-paper-meta">${h(g.reason || '请核对分组内容')}</p>${members(g.keys || [])}</fieldset>`; }).join('');
    return `${basis}${unmatched.length ? `<p class="org-paper-meta">未单独成类：${unmatched.join('；')}</p>` : ''}<p class="org-paper-meta">${groups.length} 个类别 · ${(preview.pending_keys || []).length} 篇没有共同短语，暂不归类。取消勾选上级类别时，其子类会成为一级类别。应用后只添加类别，已有分类保留，可以撤销。</p>${cards || '<p>没有可应用的建议</p>'}`;
  }
  async function suggest() {
    const d = dialog('整理建议', '<p role="status">正在生成建议…</p>', null);
    try {
      await S.queue;
      let result = await window.PDH.api('/api/organization', { action: 'suggest', revision: S.snapshot.revision, ...(window.PDH.state?.currentProject ? { project_id: window.PDH.state.currentProject } : {}) });
      if (result.job) {
        let job = result.job;
        while (job.state !== 'done') {
          if (!d.isConnected) return;
          if (job.state === 'failed') throw new Error(job.error || '整理建议生成失败');
          await new Promise(resolve => setTimeout(resolve, 1200));
          job = await window.PDH.api(`/api/jobs/${encodeURIComponent(job.id)}`);
        }
        result = job.result;
      }
      if (!d.isConnected) return;
      if (Array.isArray(result.items) && result.revision >= S.snapshot.revision) { accept(result); renderData(); }
      d.close();
      const preview = result.suggestions || result.snapshot?.suggestions || {};
      const proposals = preview.groups || (Array.isArray(preview) ? preview : []);
      dialog('审核整理建议', suggestionsHTML(preview), '应用所选建议', async el => {
        const suggestions = [...el.querySelectorAll('[data-suggestion]')].filter(f => f.querySelector('[data-enabled]').checked).map(f => ({ id: proposals[Number(f.dataset.suggestion)].id, name: f.querySelector('[data-name]').value.trim(), color: f.querySelector('[data-color]').value, keys: [...f.querySelectorAll('[data-member]:checked')].map(c => c.dataset.member) }));
        if (!suggestions.length || suggestions.some(s => !s.name || !s.keys.length)) throw new Error('请选择至少一个有名称和论文的类别');
        const result = await mutate({ action:'apply-suggestions', apply_mode:'add', fingerprint:preview.fingerprint, suggestions });
        const applied = result.apply_result;
        if (!applied) throw new Error('当前服务端未返回应用结果，请退出旧版并打开最新应用后重试');
        S.filter = '*'; renderData();
        S.notice = applied.added_memberships ? `已为 ${applied.changed_papers} 篇论文新增 ${applied.added_memberships} 条类别归属（新建 ${applied.created_categories} 个类别），原有分类保留。` : '所选论文已属于这些类别，无需重复添加。';
        status(); window.PDH.toast(S.notice, 'ok', 6000);
      });
    } catch (error) { if (d.isConnected) d.querySelector('.org-dialog-body').textContent = `建议生成失败：${error.message}`; else report(error); }
  }
  async function exportData() {
    const result = await window.PDH.api('/api/organization', { action: 'export' });
    const data = result.export || result;
    if (data == null) throw new Error('导出数据缺失');
    dialog('导出论文整理', '<label>格式<select name="format"><option value="json">JSON</option><option value="md">Markdown</option></select></label>', '下载', async el => {
      const format = el.querySelector('select').value;
      const payload = format === 'json' ? JSON.stringify(data, null, 2) : (data.markdown || markdownExport(data));
      const blob = new Blob([payload], { type: format === 'json' ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = `paperdighelper-organization-${new Date().toISOString().slice(0, 10)}.${format}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    });
  }
  function markdownExport(data) {
    const snap = data.snapshot || data;
    if (!Array.isArray(snap.items)) throw new Error('导出数据缺少论文列表');
    return '# PaperDigHelper\n\n' + snap.items.map(p => `## ${String(p.title || p.key).replace(/\n/g, ' ')}\n\n${p.published || ''}\n\n${(snap.directions || []).filter(d => memberships(p).includes(String(d.id))).map(d => categoryPath(d.id, snap)).join(', ')}\n\n${p.abstract || ''}\n\n### Note\n\n${p.note || ''}\n`).join('\n');
  }
  async function refresh() { await S.positionQueue; await S.queue; accept(await window.PDH.api('/api/organization')); S.loading = false; S.error = ''; S.positions = {}; S.cy?.destroy(); S.cy = null; if (S.mode === 'graph' && !item(S.key)) S.key = S.snapshot.items[0]?.key || null; renderData(); if (S.mode === 'graph') await loadRelations(); }
  async function handle(action, b) {
    switch (action) {
      case 'library': case 'graph': await S.positionQueue; capturePositions(); S.mode = action; renderSidebar(); setMode(); if (action === 'graph') await loadRelations(); break;
      case 'filter': {
        S.filter = b.dataset.id; S.graphFocus = null;
        renderSidebar(); renderList();
        if (S.cy) {
          // Folded directory rows must not make a selected category impossible to locate.
          const missing = visible().some(p => !S.cy.getElementById(paperNodeId(p.key)).length);
          if (missing) renderGraph(false);
          focusCategory();
        }
        break;
      }
      case 'graph-paper-focus': {
        const p = item(b.dataset.key); if (!p || !S.cy) break;
        S.key = p.key; S.graphFocus = paperNodeId(p.key); renderSidebar(); renderDetail(); renderList();
        S.notice = `${p.title || p.key} · 已定位`; status(); focusGraph(S.graphFocus); break;
      }
      case 'read': { const p = item(b.dataset.key); if (p) await window.PDH.openReader(p.key, p.title); break; }
      case 'open-detail': { const key = b.dataset.key || S.key; if (key && typeof window.PDH.openDetail === 'function') await window.PDH.openDetail(key); break; }
      case 'detail': S.key = b.dataset.key; renderDetail(); renderList(); filterGraph(); break;
      case 'detail-close': S.key = null; renderDetail(); renderList(); renderSidebar(); filterGraph(); S.cy?.resize(); break;
      case 'direction-new': editDirection(); break;
      case 'category-child': editDirection(undefined, b.dataset.id); break;
      case 'direction-edit': editDirection(b.dataset.id); break;
      case 'direction-delete': deleteDirection(b.dataset.id); break;
      case 'direction-up': case 'direction-down': {
        const moved = directions().find(d => String(d.id) === b.dataset.id);
        const siblings = directions().filter(d => (d.parent_id || null) === (moved.parent_id || null));
        const i = siblings.findIndex(d => d.id === moved.id), j = i + (action === 'direction-up' ? -1 : 1);
        if (!siblings[j]) break;
        await mutate({ action:'direction-save', id:moved.id, name:moved.name, color:moved.color, rank:siblings[j].rank });
        break;
      }
      case 'collapse': {
        const id=b.dataset.id, collapsing=!S.collapsed.has(id), revision=S.snapshot.revision;
        S.motion?.settle(); capturePositions();
        if(collapsing && S.cy && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
          const next={...S.snapshot,collapsed:[...S.collapsed,id]};
          const keep=new Set(networkElements(next,S.relations).map(e=>e.data.id));
          S.cy.elements().filter(e=>!keep.has(e.id())).addClass('org-leaving');
          await new Promise(resolve=>setTimeout(resolve,180));
        }
        try { await mutate({action:'collapse',id,collapsed:collapsing,revision}); }
        finally { S.cy?.elements().removeClass('org-leaving'); }
        break;
      }
      case 'membership': editMembership([...S.selected]); break;
      case 'paper-membership': editMembership([b.dataset.key]); break;
      case 'clear-selection': S.selected.clear(); S.cy?.elements().unselect(); renderList(); break;
      case 'note-save': await saveNote(S.key); break;
      case 'draft-choose': {
        const key = S.key, draft = S.drafts.get(key);
        const candidates = [...(draft.variants || []), ...(S.snapshot.drafts || []).filter(d => d.key === key).map(d => ({ ...d, version: item(key).note_version, serverVersion: d.version }))];
        dialog('恢复草稿', candidates.map((d, i) => `<label><input type="radio" name="candidate" value="${i}" ${i === 0 ? 'checked' : ''}>草稿 ${i + 1}<pre>${h(d.text)}</pre></label>`).join(''), '恢复所选草稿', async el => {
          const selected = el.querySelector('[name=candidate]:checked');
          if (!selected) throw new Error('请选择草稿');
          chooseDraftVariant(key, candidates[Number(selected.value)]); renderDetail();
        }); break;
      }
      case 'note-rebase': {
        const key = S.key, draft = S.drafts.get(key);
        await refresh();
        const comparedVersion = item(key).note_version;
        dialog('比较笔记版本', `<h3>最新保存版本</h3><div class="org-markdown">${window.PDH.md(item(key).note || '')}</div><h3>你的草稿</h3><div class="org-markdown">${window.PDH.md(draft.text)}</div>`, '确认以草稿保存新版本', async () => {
          confirmDraftVersion(key, comparedVersion); storeDraft(key, draft); await saveNote(key);
          if (draft.error) throw new Error(draft.error);
        }); break;
      }
      case 'note-edit': case 'note-preview': {
        const preview = action === 'note-preview'; $('[data-note-editor]').hidden = preview; $('[data-note-preview]').hidden = !preview;
        $('[data-note-preview]').innerHTML = window.PDH.md(draftFor(item(S.key)).text);
        $('[data-action=note-edit]').setAttribute('aria-pressed', String(!preview)); $('[data-action=note-preview]').setAttribute('aria-pressed', String(preview)); break;
      }
      case 'history': await history(); break;
      case 'undo': {
        const undo = S.snapshot.undo;
        if (!undo) break;
        await mutate({ action: 'undo', event: undo.id }, false); S.positions = {}; S.cy?.destroy(); S.cy = null; renderData();
        S.notice = `已撤销：${undo.label}`; status(); break;
      }
      case 'suggest': await suggest(); break;
      case 'export': await exportData(); break;
      case 'fit': focusGraph(null); break;
      case 'rearrange':
        dialog('重新排列', '<p>重新排列所有论文卡片？之后可点击「撤销重新排列」恢复原布局。</p>', '重新排列', async () => {
          await S.positionQueue;
          const previous = S.snapshot.positions;
          S.snapshot.positions = {}; S.positions = {}; S.cy?.destroy(); S.cy = null; renderGraph(false); capturePositions();
          try { await mutate({ action: 'positions', rearrange: true, positions: { ...Object.fromEntries(Object.keys(previous).map(id => [id, null])), ...S.positions } }, false); renderGraph(false); }
          catch (error) { S.snapshot.positions = previous; S.positions = {}; S.cy?.destroy(); S.cy = null; renderGraph(); throw error; }
        }); break;
      case 'zoom-in': case 'zoom-out': zoomGraph(action === 'zoom-in' ? 1.2 : 1 / 1.2); break;
      case 'dialog-close': $('dialog')?.close(); break;
    }
  }
  window.addEventListener('beforeunload', event => { if ([...S.drafts.values()].some(d => d.dirty)) { event.preventDefault(); event.returnValue = ''; } });
  window.PDHOrganization = { async open(mode = 'library') {
    S.root = document.getElementById('organizationRoot');
    if (!S.root) throw new Error('Missing #organizationRoot');
    S.loading = true; S.mode = mode === 'graph' || mode === 'knowledge' ? 'graph' : 'library';
    if (S.mode === 'graph' && !localStorage.getItem('pdh-graph-layout-v3')) S.graphRadialPending = true;
    S.root.hidden = false; renderShell();
    try { await refresh(); } catch (error) { report(error); }
  } };
  if (typeof module !== 'undefined' && module.exports) module.exports = { renderList, suggestionsHTML, undoHTML, renderUndo, sidebarHTML, treeRows, categoryIds, visible, editMembership, editDirection, deleteDirection, S, accept, draftFor, saveNote, persistDraft, syncGraphSelection, closeDialog, cardId, safePaperURL, paperURL, confirmDraftVersion, mutate, changedPositions, graphSignature, cacheDraft, chooseDraftVariant, handle, networkElements, graphOrigin, detailCategoriesHTML, categoryColor, graphViewport, focusCategory, focusGraph, zoomGraph, positionWriter, bindGraphDrag, radialPositions };
})();
