/* Shared, deterministic profile/weekly presentation. All text is escaped. */
(function(global) {
'use strict';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {positive:'有用',negative:'不相关',too_hard:'太难',saved:'收藏',exposed:'曝光',seed:'种子',other:'历史状态'};
const sources = {seed:'种子',useful_feedback:'有用反馈',saved:'收藏'};
const colors = {positive:'var(--p-positive)',negative:'var(--p-negative)',too_hard:'var(--p-hard)',saved:'var(--p-saved)',exposed:'var(--p-exposed)'};
const date = t => t ? String(t).slice(0,10) : '暂无记录';
const empty = text => `<div class="profile-empty">${esc(text)}</div>`;
const button = (text, attrs='') => `<button type="button" ${attrs}>${text}</button>`;
const evidenceAttrs = (kind, extra='') => `data-evidence="${kind}" ${extra}`;
function weeklyHTML(report) {
  if (!report) return empty('暂未加载周报');
  const cols = ['saved','positive','negative','too_hard','exposed'];
  const rows = cols.map(k=>`<tr><th scope="row">${labels[k]}</th><td>${button(report.previous_stats[k],evidenceAttrs(k,`data-start="${esc(report.previous_start)}" data-end="${esc(report.week_start)}"`))}</td><td>${button(report.stats[k],evidenceAttrs(k,`data-start="${esc(report.week_start)}" data-end="${esc(report.week_end)}"`))}</td></tr>`).join('');
  const terms = Object.values(report.keyword_changes).flat();
  return `<p class="profile-note">按 UTC 自然日统计，右端日期不含当日。上期 ${date(report.previous_start)} 至 ${date(report.week_start)}；本期 ${date(report.week_start)} 至 ${date(report.week_end)}。</p><div class="profile-table-wrap"><table class="profile-table"><thead><tr><th>已记录操作（次）</th><th>上期 7 天</th><th>本期 7 天</th></tr></thead><tbody>${rows}</tbody></table></div>${!report.comparable ? empty('暂无可比较数据：需要两个周期均有活动。没有记录不表示兴趣下降。') : `<h3>相关论文中的词项变化</h3><p class="profile-note">数字为两个周期内收藏或标记有用的去重论文数，不代表兴趣强度。</p>${terms.map(t=>`<div class="profile-feedback-row"><span>${esc(t.term)}</span><span>${button(`${t.previous} → ${t.current}`,evidenceAttrs('term',`data-term="${esc(t.term)}" data-start="${esc(report.week_start)}" data-end="${esc(report.week_end)}"`))}</span></div>`).join('') || empty('暂无词项证据')}`}`;
}
function create(root, options) {
  let data, profile, project, pins=[], allTerms=false, history=false, generation=0, request=0, evidenceQuery=null, items=[], dialog=null;
  const api = options.api;
  function row(e, undo=false) {
    const tag = labels[e.kind] || labels[{useful:'positive',irrelevant:'negative'}[e.action]] || '论文证据';
    return `<div class="profile-feedback-row"><div>${button(esc(e.title),`class="paper-link" data-paper="${esc(e.key)}"`)}<div class="profile-note">${esc(e.published || '年份未知')} · ${esc(tag)} · ${date(e.time)}${e.sources?.length ? ' · '+e.sources.map(s=>esc(sources[s]||s)).join(' / ') : ''}${e.action ? ' · 当前反馈：'+esc({useful:'有用',irrelevant:'不相关',too_hard:'太难'}[e.action]||e.action):''}</div>${e.reason ? `<div class="profile-note">${esc(e.reason)}</div>`:''}</div>${undo && e.feedback_id ? button('撤销',`data-undo="${e.feedback_id}"`):''}</div>`;
  }
  function pinHTML() { return pins.map((p,i)=>`<span class="profile-pin">${esc(p)}${button('×',`data-remove-pin="${i}" aria-label="移除 ${esc(p)}"`)}</span>`).join('') || '<span class="profile-note">未设置固定关键词</span>'; }
  function render(next, p, projectName) {
    generation++; request++; data=next; profile=p; project=p.project_id; pins=[...(p.pinned_terms||[])];
    if(dialog) { dialog.close(); dialog.remove(); dialog=null; }
    const opened = new Set([...root.querySelectorAll('details[open]')].map(el=>el.id));
    const signals=data.signals||{};
    const count=(key,label)=>button(`<b>${signals[key]||0}</b><span>${label}</span>`,evidenceAttrs(key));
    const terms=data.keyword_distribution||[];
    root.innerHTML=`<div class="profile-head"><div class="profile-kicker">${esc(projectName)} · 本地画像</div><div class="profile-headline"><div><h1>系统如何理解你的关注</h1><p>${esc(data.summary)}</p></div></div><div class="profile-meta">活动范围 ${date(data.coverage.start)} 至 ${date(data.coverage.end)}（UTC，右端不含） · 最近记录 ${date(data.coverage.last_activity)}</div><div class="profile-actions">${button('编辑固定关键词','class="primary" data-edit-pins')}${button('查看反馈历史','data-history')}</div><div class="profile-note">依据本地论文、收藏、曝光和明确反馈。当前关注依据全部保留记录；下方活动展示最近 12 周。沉默不表示不感兴趣。</div></div>
    <section class="profile-signals" aria-label="当前画像信号"><article class="profile-signal"><h2>你指定的关注</h2><span class="profile-note">用户填写 · 始终保留</span><div class="profile-pins">${pins.length ? pins.slice(0,4).map(t=>`<span class="profile-pin">${esc(t)}</span>`).join('') : '<span class="profile-note">尚未设置</span>'}</div>${button(`${pins.length} 个固定关键词 · 编辑`,'data-edit-pins')}</article><article class="profile-signal"><h2>你留下的兴趣线索</h2><div class="profile-counts">${count('positive','有用')}${count('saved','收藏')}</div><p class="profile-note">两组可重叠，不相加。收藏是保留资料，不等于确认强烈兴趣。</p></article><article class="profile-signal"><h2>排除与暂时困难</h2><div class="profile-counts">${count('negative','不相关')}${count('too_hard','太难')}</div><p class="profile-note">不相关用于排除；太难单独记录，不作为负兴趣展示。</p></article></section>
    <section class="profile-section"><div class="profile-section-heading"><h2>为什么这样判断</h2>${button(`${data.keyword_evidence.papers} 篇证据`,evidenceAttrs('term'))}</div><p class="profile-note">论文词项按覆盖篇数排序，每篇只计一次。点击查看来源；这不是偏好概率。</p><div class="profile-keywords">${terms.length ? terms.slice(0,allTerms?20:5).map(t=>button(`<span>${esc(t.term)}<small>${t.sources.map(s=>esc(sources[s]||s)).join(' / ')}</small></span><span class="profile-bar" aria-hidden="true"><i style="width:${Math.max(0,Math.min(100,t.score*100))}%"></i></span><span class="profile-term-count">${t.documents} 篇 →</span>`,`class="profile-term" ${evidenceAttrs('term',`data-term="${esc(t.term)}"`)}`)).join(''):empty('还没有论文证据。固定关键词独立保留；曝光与太难不会生成兴趣词项。')}</div>${terms.length>5?button(allTerms?'收起词项':`查看全部 ${terms.length} 个词项`,'data-all-terms'):''}</section>
    <details class="profile-section" id="profileActivity"><summary>最近发生了什么<span class="profile-note">最近 12 周 · 展开周记录与最近反馈</span></summary><div class="profile-legend profile-note">${Object.keys(colors).map(k=>`<span><i class="profile-dot" style="background:${colors[k]}"></i>${labels[k]}</span>`).join('')}</div>${data.timeline.has_activity?`<div class="profile-week-grid">${data.timeline.weeks.map(w=>{const total=w.activity;return button(`<span>${w.start.slice(5)} 起</span><b>${total} 次</b><span class="profile-segments" aria-hidden="true">${Object.keys(colors).map(k=>`<i style="width:${total?w[k]/total*100:0}%;background:${colors[k]}"></i>`).join('')}</span><span>${Object.keys(colors).map(k=>`${labels[k]} ${w[k]}`).join(' · ')}</span>`,`class="profile-week" ${evidenceAttrs('week',`data-start="${w.start}" data-end="${w.end}"`)}`)}).join('')}</div>`:empty('最近 12 周没有活动记录，不推断兴趣变化。')}<h3>最近反馈</h3><div>${data.recent_feedback.map(e=>row(e,true)).join('')||empty('暂无明确反馈')}</div>${button('查看全部反馈','data-history')}</details>
    <details class="profile-section" id="profileWeekly"><summary>本周变化<span class="profile-note">与前 7 天比较 · 仅统计本地实际记录</span></summary>${weeklyHTML(data.weekly_change)}<p><a href="/weekly_report.html?project_id=${encodeURIComponent(project)}">打开完整周报 →</a></p></details>
    <details class="profile-section" id="profileCorrection"><summary>修正画像<span class="profile-note">编辑固定项、检查历史版本、撤销反馈</span></summary><h3>固定关键词</h3><div class="profile-pins" id="profilePinDraft">${pinHTML()}</div><form class="profile-form" id="profilePinForm"><input id="profilePinInput" aria-label="新增固定关键词" placeholder="输入关键词，多个用逗号分隔" maxlength="4040">${button('添加','data-add-pin')}${button('保存修改','class="primary" data-save-pins')}</form><p class="profile-note">移除标签后需保存。撤销反馈会保留收藏；收藏可在论文库单独取消。</p><div id="profileMessage" role="status"></div><h3>自动学习</h3><p class="profile-note" id="profileFreezeState">${profile.frozen ? `已冻结（${date(profile.frozen_at)}起）：新反馈照常记录，但不改变推荐。` : '学习中：明确的“有用 / 不相关”会调整推荐；“太难”不算不感兴趣。'}</p><div class="profile-actions">${button(profile.frozen ? '恢复自动学习' : '冻结画像', `data-freeze="${profile.frozen ? 'false' : 'true'}"`)}${button('恢复默认','data-restore-default')}</div><details><summary>固定关键词版本（最近 10 次）</summary>${(data.versions||[]).map(v=>`<div class="profile-feedback-row"><span>${date(v.created_at)} · ${esc((v.data.pinned_terms||[]).join('、')||'无固定词')}</span>${button('载入编辑',`data-version="${v.id}"`)}</div>`).join('')||empty('暂无编辑版本')}</details>${button('查看反馈历史','data-history')}</details>`;
    opened.forEach(id=>{const d=root.querySelector('#'+id);if(d)d.open=true;});
  }
  function focusCorrection() { const d=root.querySelector('#profileCorrection');d.open=true;d.scrollIntoView({block:'start'});root.querySelector('#profilePinInput').focus(); }
  function addPins() { const input=root.querySelector('#profilePinInput');pins=[...new Set([...pins,...input.value.split(/[,，]/).map(s=>s.trim()).filter(Boolean)])];input.value='';root.querySelector('#profilePinDraft').innerHTML=pinHTML(); }
  async function showEvidence(query, more=false) {
    const token=++request, gen=generation;
    evidenceQuery=query;
    if(!more) {
      items=[];
      if(dialog)dialog.remove();
      dialog=document.createElement('dialog');dialog.className='profile-evidence';dialog.setAttribute('aria-label','画像来源证据');
      dialog.innerHTML=`<header><h2>${query.kind==='feedback'?'反馈历史':query.term?esc(query.term)+' · 论文证据':'来源明细'}</h2>${button('关闭','data-close-evidence')}</header><div class="profile-evidence-body" aria-live="polite">正在读取本地记录…</div>`;
      root.append(dialog);dialog.showModal();
    }
    const params=new URLSearchParams({project_id:project,...query,offset:String(items.length)});
    try {
      const result=await api('/api/profile/evidence?'+params);
      if(token!==request||gen!==generation||!dialog?.open)return;
      items.push(...result.items);
      dialog.querySelector('.profile-evidence-body').innerHTML=`<p class="profile-note">${result.total} 条${query.start?' · '+date(query.start)+' 至 '+date(query.end)+'（UTC，不含右端）':''}</p>${items.map(e=>row(e,query.kind==='feedback')).join('')||empty('当前筛选没有记录')}${items.length<result.total?button('加载更多','data-more-evidence'):''}`;
    } catch(e) { if(token===request&&dialog)dialog.querySelector('.profile-evidence-body').innerHTML=`<p class="profile-error">加载失败：${esc(e.message)}</p>${button('重试','data-retry-evidence')}`; }
  }
  root.addEventListener('submit',e=>{e.preventDefault();addPins();});
  root.addEventListener('click',async e=>{
    const b=e.target.closest('button');if(!b)return;
    try {
      if(b.hasAttribute('data-edit-pins'))focusCorrection();
      else if(b.hasAttribute('data-all-terms')) {allTerms=!allTerms;render(data,profile,options.projectName());}
      else if(b.hasAttribute('data-add-pin'))addPins();
      else if(b.hasAttribute('data-remove-pin')) {pins.splice(Number(b.dataset.removePin),1);root.querySelector('#profilePinDraft').innerHTML=pinHTML();}
      else if(b.hasAttribute('data-version')) {const v=data.versions.find(v=>String(v.id)===b.dataset.version);pins=[...v.data.pinned_terms];root.querySelector('#profilePinDraft').innerHTML=pinHTML();root.querySelector('#profileMessage').textContent='已载入编辑，保存后才生效。';}
      else if(b.hasAttribute('data-save-pins')) {addPins();b.disabled=true;await api('/api/pin',{project_id:project,terms:pins.join(',')});await options.refresh();root.querySelector('#profileMessage').textContent='固定关键词已保存。';}
      else if(b.hasAttribute('data-undo')) {b.disabled=true;await api('/api/undo',{project_id:project,feedback_id:Number(b.dataset.undo)});await options.refresh();options.notify('反馈已撤销，收藏保持不变。');}
      else if(b.hasAttribute('data-freeze')) {b.disabled=true;await api('/api/profile/freeze',{project_id:project,frozen:b.dataset.freeze==='true'});await options.refresh();options.notify(b.dataset.freeze==='true'?'画像已冻结。':'已恢复自动学习。');}
      else if(b.hasAttribute('data-restore-default')) {if(!confirm('恢复为创建项目时的关键词并恢复自动学习？反馈记录不会删除，旧关键词可在版本中重新载入。'))return;b.disabled=true;const r=await api('/api/profile/restore',{project_id:project});await options.refresh();options.notify(`已恢复默认。原固定词：${(r.previous_pinned_terms||[]).join('、')||'无'}`);}
      else if(b.hasAttribute('data-history'))await showEvidence({kind:'feedback'});
      else if(b.hasAttribute('data-evidence')) {const q={kind:b.dataset.evidence};if(b.dataset.term)q.term=b.dataset.term;if(b.dataset.start){q.start=b.dataset.start;q.end=b.dataset.end;}await showEvidence(q);}
      else if(b.hasAttribute('data-more-evidence'))await showEvidence(evidenceQuery,true);
      else if(b.hasAttribute('data-retry-evidence'))await showEvidence(evidenceQuery);
      else if(b.hasAttribute('data-close-evidence')) {request++;dialog.close();dialog.remove();dialog=null;}
      else if(b.hasAttribute('data-paper')) {if(dialog)dialog.close();options.openPaper(b.dataset.paper);}
    } catch(error) {b.disabled=false;options.notify(error.message);}
  });
  return {render, invalidate(){generation++;request++;if(dialog){dialog.close();dialog.remove();dialog=null;}root.innerHTML=empty('正在读取当前项目画像…');}, weekly:weeklyHTML};
}
global.PDHProfile={create,weeklyHTML,esc};
})(typeof window !== 'undefined' ? window : globalThis);
