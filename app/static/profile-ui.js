/* Shared, deterministic profile/weekly presentation. All text is escaped. */
(function(global) {
'use strict';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {positive:'有用',negative:'不相关',too_hard:'太难',understood:'已读懂',saved:'收藏',exposed:'曝光',seed:'种子',other:'历史状态'};
const sources = {seed:'种子',useful_feedback:'有用反馈',saved:'收藏'};
const sourceText = key => sources[key] ? (global.PDHi18n?.t(sources[key]) || sources[key]) : key;
const colors = {understood:'var(--p-understood)',positive:'var(--p-positive)',negative:'var(--p-negative)',too_hard:'var(--p-hard)',saved:'var(--p-saved)',exposed:'var(--p-exposed)'};
const date = t => t ? String(t).slice(0,10) : '暂无记录';
const empty = text => `<div class="profile-empty">${esc(text)}</div>`;
const button = (text, attrs='') => `<button type="button" ${attrs}>${text}</button>`;
const evidenceAttrs = (kind, extra='') => `data-evidence="${kind}" ${extra}`;
const signed = n => n>0 ? `+${n}` : String(n);
/* Pure numbers for the dashboard; everything is a count of local records, nothing is estimated. */
function dashboard(data) {
  const weeks=data.timeline?.weeks||[], s=data.signals||{}, wc=data.weekly_change||{};
  const now=wc.stats||{}, prev=wc.previous_stats||{};
  const kpis=['saved','positive','negative','too_hard'].map(key=>({key, label:labels[key], value:s[key]||0, week:now[key]||0, prev:prev[key]||0, trend:weeks.map(w=>w[key]||0), color:colors[key], evidence:evidenceAttrs(key), unit:'篇'}));
  const activity={key:'activity', label:'本周活动', value:now.activity||0, week:now.activity||0, prev:prev.activity||0, trend:weeks.map(w=>w.activity||0), color:'var(--accent)', unit:'次', weekly:true,
    evidence:evidenceAttrs('week',`data-start="${esc(wc.week_start||'')}" data-end="${esc(wc.week_end||'')}"`)};
  const positive=s.positive||0, negative=s.negative||0, tooHard=s.too_hard||0, judged=positive+negative;
  const peak=Math.max(0,...weeks.map(w=>w.activity||0));
  const maxDocs=Math.max(1,...(data.keyword_distribution||[]).map(t=>t.documents||0));
  return {kpis, activity,
    feedback:{positive, negative, too_hard:tooHard, judged, rate:judged ? Math.round(positive/judged*100) : null, few:judged<5},
    weeks:{list:weeks, peak, active:weeks.filter(w=>w.activity>0).length},
    termWidth:t=>Math.max(3,Math.round((t.documents||0)/maxDocs*100))};
}
function spark(values, color) {
  if(values.length<2 || !values.some(Boolean)) return '<span class="pd-spark is-flat" aria-hidden="true"></span>';
  const max=Math.max(...values), n=values.length;
  const pts=values.map((v,i)=>`${(i/(n-1)*100).toFixed(1)},${(29-v/max*25).toFixed(1)}`).join(' ');
  return `<svg class="pd-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true" style="color:${color}"><polygon points="0,30 ${pts} 100,30" fill="currentColor" opacity=".12"/><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
}
function kpiHTML(k) {
  const delta=k.weekly ? `上周 ${k.prev} 次` : `本周新增 ${k.week} · 上周 ${k.prev}`;
  const note=k.key==='too_hard' ? '<span class="pd-kpi-tag">不算负面</span>' : '';
  return button(`<span class="pd-kpi-label"><i class="profile-dot" style="background:${k.color}"></i>${k.label}${note}</span><b>${k.value}<small>${k.unit}</small></b><span class="pd-kpi-delta">${delta}</span>${spark(k.trend,k.color)}`,`class="pd-kpi" data-kpi="${k.key}" ${k.evidence}`);
}
function feedbackHTML(f) {
  const parts=[['positive',f.positive],['negative',f.negative],['too_hard',f.too_hard]], total=f.positive+f.negative+f.too_hard;
  let at=0;
  const rings=total ? parts.filter(([,v])=>v).map(([k,v])=>{const len=v/total*100, seg=`<circle r="15.915" cx="18" cy="18" fill="none" stroke="${colors[k]}" stroke-width="3.6" stroke-dasharray="${len.toFixed(2)} ${(100-len).toFixed(2)}" stroke-dashoffset="${(25-at).toFixed(2)}"/>`;at+=len;return seg;}).join('') : '';
  const center=f.rate===null ? '<b>—</b><span>还没有评价</span>' : `<b>${f.rate}%</b><span>有用率</span>`;
  return `<div class="pd-card-head"><h2>明确反馈</h2></div><div class="pd-donut-wrap"><div class="pd-donut"><svg viewBox="0 0 36 36" aria-hidden="true"><circle r="15.915" cx="18" cy="18" fill="none" stroke="var(--surface-2)" stroke-width="3.6"/>${rings}</svg><div class="pd-donut-center">${center}</div></div>
    <div class="pd-legend">${parts.map(([k,v])=>button(`<i class="profile-dot" style="background:${colors[k]}"></i><span>${labels[k]}</span><b>${v}</b>`,`class="pd-legend-row" ${evidenceAttrs(k)}`)).join('')}</div></div>
    <p class="pd-foot"><span>${f.judged ? `有用率 = 有用 ÷（有用 + 不相关），共 ${f.judged} 篇。` : '标记“有用 / 不相关”后显示有用率。'}</span> ${f.judged&&f.few?'<span>样本还少，仅供参考。</span> ':''}<span>“太难”不计入。</span></p>`;
}
function activityHTML(w) {
  const order=['positive','saved','negative','too_hard','exposed'];
  const legend=order.map(k=>`<span><i class="profile-dot" style="background:${colors[k]}"></i>${labels[k]}</span>`).join('');
  const head=`<div class="pd-card-head"><h2>最近 12 周</h2><span class="profile-note">${w.active} / ${w.list.length} 周有记录${w.peak?` · 最多 ${w.peak} 次/周`:''}</span></div>`;
  if(!w.list.length || !w.peak) return head+empty('最近 12 周没有活动记录，不推断兴趣变化。');
  const cols=w.list.map((x,i)=>{
    const last=i===w.list.length-1, tip=`${x.start.slice(5)} 起 · ${order.map(k=>`${labels[k]} ${x[k]||0}`).join(' · ')}`;
    const stack=order.map(k=>x[k] ? `<i style="height:${(x[k]/w.peak*100).toFixed(1)}%;background:${colors[k]}"></i>` : '').join('');
    return button(`<span class="pd-col-value">${x.activity||''}</span><span class="pd-col-bar">${stack}</span><span class="pd-col-label">${last?'本周':x.start.slice(5)}</span>`,`class="pd-col${last?' is-current':''}" title="${esc(tip)}" aria-label="${esc(tip)}" ${evidenceAttrs('week',`data-start="${esc(x.start)}" data-end="${esc(x.end)}"`)}`);
  }).join('');
  return `${head}<div class="pd-chart">${cols}</div><div class="profile-legend profile-note">${legend}</div>`;
}
function trendHTML(wc) {
  const now=wc.stats||{}, prev=wc.previous_stats||{}, kinds=['saved','positive','negative','too_hard'];
  const max=Math.max(1,...kinds.flatMap(k=>[now[k]||0,prev[k]||0]));
  const bars=kinds.map(k=>`<div class="pd-pair"><span>${labels[k]}</span><span class="pd-pair-bars"><i class="is-prev" style="width:${(prev[k]||0)/max*100}%;background:${colors[k]}"></i><i style="width:${(now[k]||0)/max*100}%;background:${colors[k]}"></i></span><span class="pd-pair-num">${prev[k]||0} → <b>${now[k]||0}</b></span></div>`).join('');
  const changes=wc.keyword_changes||{}, chip=(t,dir)=>button(`${dir==='up'?'↑':'↓'} <span data-no-i18n>${esc(t.term)}</span> <small>${signed(t.delta)}</small>`,`class="pd-chip is-${dir}" ${evidenceAttrs('term',`data-term="${esc(t.term)}" data-start="${esc(wc.week_start)}" data-end="${esc(wc.week_end)}"`)}`);
  const terms=!wc.comparable ? `<p class="pd-foot">${wc.has_activity ? '上周没有记录' : '本周还没有记录'}，暂不比较词项；这不表示兴趣下降。</p>`
    : `<div class="pd-chips">${(changes.rising||[]).map(t=>chip(t,'up')).join('')}${(changes.falling||[]).map(t=>chip(t,'down')).join('')}</div>${!(changes.rising||[]).length&&!(changes.falling||[]).length?'<p class="pd-foot">词项与上周持平。</p>':''}`;
  return `<div class="pd-pairs"><div class="pd-pair pd-pair-head"><span></span><span class="profile-note">淡色 上周 · 实色 本周（${date(wc.week_start)} 起）</span><span></span></div>${bars}</div>${terms}`;
}
function create(root, options) {
  let data, profile, project, pins=[], allTerms=false, history=false, generation=0, request=0, evidenceQuery=null, items=[], dialog=null;
  const api = options.api;
  function row(e, undo=false) {
    const tag = labels[e.kind] || labels[{useful:'positive',irrelevant:'negative'}[e.action]] || '论文证据';
    return `<div class="profile-feedback-row"><div>${button(`<span data-no-i18n>${esc(e.title)}</span>`,`class="paper-link" data-paper="${esc(e.key)}"`)}<div class="profile-note"><span>${esc(e.published || '年份未知')}</span> · <span>${esc(tag)}</span> · <span>${date(e.time)}</span>${e.sources?.length ? ' · '+e.sources.map(s=>`<span${sources[s]?'':' data-no-i18n'}>${esc(sources[s]||s)}</span>`).join(' / ') : ''}${e.action ? ' · <span>当前反馈：</span><span>'+esc({useful:'有用',irrelevant:'不相关',understood:'已读懂',too_hard:'太难'}[e.action]||e.action)+'</span>':''}</div>${e.reason ? `<div class="profile-note"><span>反馈理由：</span><span data-no-i18n>${esc(e.reason)}</span></div>`:''}</div>${undo && e.feedback_id ? button('撤销',`data-undo="${e.feedback_id}"`):''}</div>`;
  }
  function pinHTML() { return pins.map((p,i)=>`<span class="profile-pin"><span data-no-i18n>${esc(p)}</span>${button('×',`data-remove-pin="${i}" aria-label="移除固定关键词"`)}</span>`).join('') || '<span class="profile-note">未设置固定关键词</span>'; }
  function render(next, p, projectName) {
    generation++; request++; data=next; profile=p; project=p.project_id; pins=[...(p.pinned_terms||[])];
    if(dialog) { dialog.close(); dialog.remove(); dialog=null; }
    const opened = new Set([...root.querySelectorAll('details[open]')].map(el=>el.id));
    const m=dashboard(data), terms=data.keyword_distribution||[], wc=data.weekly_change||{};
    const lede=terms.length ? `种子与明确“有用”反馈中常见 ${terms.slice(0,3).map(t=>`<b data-no-i18n>${esc(t.term)}</b>`).join(' · ')}` : '还没有种子或“有用”反馈；收藏资料不会自动成为兴趣';
    const status=profile.frozen ? `<span class="pd-status is-frozen">已冻结</span>` : `<span class="pd-status">学习中</span>`;
    root.innerHTML=`<header class="pd-head"><div><div class="profile-kicker"><span data-no-i18n>${esc(projectName)}</span> · <span>本地画像</span></div><h1>兴趣画像 ${status}</h1><p class="pd-lede">${lede}</p><div class="profile-meta">${date(data.coverage.start)} 至 ${date(data.coverage.end)} · 最近记录 ${date(data.coverage.last_activity)}</div></div><div class="profile-actions">${button('编辑固定关键词','class="primary" data-edit-pins')}${button('反馈历史','data-history')}</div></header>
    <section class="pd-kpis" aria-label="画像指标">${m.kpis.map(kpiHTML).join('')}${kpiHTML(m.activity)}</section>
    <div class="pd-row">
      <section class="pd-card pd-terms" aria-label="兴趣词项"><div class="pd-card-head"><h2>兴趣词项</h2>${button(`${data.keyword_evidence.papers} 篇证据 →`,`class="pd-link" ${evidenceAttrs('term')}`)}</div>
        <div class="pd-pins"><span class="pd-pins-label">固定</span>${pins.length ? pins.map(t=>`<span class="profile-pin" data-no-i18n>${esc(t)}</span>`).join('') : '<span class="profile-note">未设置</span>'}${button(pins.length?'编辑':'添加','class="pd-link" data-edit-pins')}</div>
        <div class="profile-keywords">${terms.length ? terms.slice(0,allTerms?20:8).map(t=>button(`<span class="pd-term-name" data-no-i18n>${esc(t.term)}</span><span class="profile-bar" aria-hidden="true"><i style="width:${m.termWidth(t)}%"></i></span><span class="profile-term-count">${t.documents} 篇</span>`,`class="profile-term" title="来源：${esc(t.sources.map(sourceText).join(' / '))}" ${evidenceAttrs('term',`data-term="${esc(t.term)}"`)}`)).join('') : empty('还没有兴趣证据。选种子或明确标记“有用”后会出现词项。')}</div>
        ${terms.length>8?button(allTerms?'收起':`查看全部 ${terms.length} 个`,'class="pd-link" data-all-terms'):''}
        <p class="pd-foot">长度 = 含该词的种子 / 明确有用论文篇数（每篇计一次），不是偏好概率。</p></section>
      <section class="pd-card pd-feedback" aria-label="明确反馈">${feedbackHTML(m.feedback)}</section>
    </div>
    <section class="pd-card pd-block" aria-label="收藏库内容词项"><div class="pd-card-head"><h2>收藏库内容词项</h2>${button(`${data.inventory_evidence?.papers||0} 篇库存 →`,`class="pd-link" ${evidenceAttrs('inventory_term')}`)}</div><p class="pd-foot">包括导入与收藏的论文，只说明资料库内容，不参与兴趣反馈；实验数值和泛词已过滤。</p><div class="pd-chips">${(data.inventory_distribution||[]).slice(0,8).map(t=>button(`<span data-no-i18n>${esc(t.term)}</span>`,`class="pd-chip" ${evidenceAttrs('inventory_term',`data-term="${esc(t.term)}"`)}`)).join('')||empty('当前没有收藏资料。')}</div></section>
    <section class="pd-card pd-block" aria-label="最近 12 周活动">${activityHTML(m.weeks)}</section>
    <div class="pd-row pd-row-even">
      <section class="pd-card" aria-label="本周动向"><div class="pd-card-head"><h2>本周动向</h2><a class="pd-link" href="/weekly_report.html?project_id=${encodeURIComponent(project)}">完整周报 →</a></div>${trendHTML(wc)}</section>
      <section class="pd-card" aria-label="最近反馈"><div class="pd-card-head"><h2>最近反馈</h2>${button('全部 →','class="pd-link" data-history')}</div><div>${data.recent_feedback.map(e=>row(e,true)).join('')||empty('暂无明确反馈')}</div></section>
    </div>
    <p class="pd-honesty">全部由本地记录计算，不调用模型。没有操作不代表不感兴趣；“太难”单独记录，不算负面兴趣。</p>
    <details class="profile-section" id="profileCorrection"><summary>修正画像<span class="profile-note">编辑固定项、冻结学习、历史版本</span></summary><h3>固定关键词</h3><div class="profile-pins" id="profilePinDraft">${pinHTML()}</div><form class="profile-form" id="profilePinForm"><input id="profilePinInput" aria-label="新增固定关键词" placeholder="输入关键词，多个用逗号分隔" maxlength="4040">${button('添加','data-add-pin')}${button('保存修改','class="primary" data-save-pins')}</form><p class="profile-note">移除标签后需保存。撤销反馈会保留收藏；收藏可在论文库单独取消。</p><div id="profileMessage" role="status"></div><h3>自动学习</h3><p class="profile-note" id="profileFreezeState">${profile.frozen ? `已冻结（${date(profile.frozen_at)}起）：新反馈照常记录，但不改变推荐。` : '学习中：明确的“有用 / 不相关”会调整推荐；“太难”不算不感兴趣。'}</p><div class="profile-actions">${button(profile.frozen ? '恢复自动学习' : '冻结画像', `data-freeze="${profile.frozen ? 'false' : 'true'}"`)}${button('恢复默认','data-restore-default')}</div><details><summary>固定关键词版本（最近 10 次）</summary>${(data.versions||[]).map(v=>`<div class="profile-feedback-row"><span>${date(v.created_at)}</span> · <span${v.data.pinned_terms?.length?' data-no-i18n':''}>${esc((v.data.pinned_terms||[]).join('、')||'无固定词')}</span>${button('载入编辑',`data-version="${v.id}"`)}</div>`).join('')||empty('暂无编辑版本')}</details></details>`;
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
      dialog.innerHTML=`<header><h2>${query.kind==='feedback'?'反馈历史':query.term?'<span data-no-i18n>'+esc(query.term)+'</span> · 论文证据':'来源明细'}</h2>${button('关闭','data-close-evidence')}</header><div class="profile-evidence-body" aria-live="polite">正在读取本地记录…</div>`;
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
      else if(b.hasAttribute('data-restore-default')) {
        if(b.disabled)return;
        const originalProject=project, gen=generation; b.disabled=true;
        try {
          if(!await window.PDHDialogs.confirm('恢复为创建项目时的关键词并恢复自动学习？反馈记录不会删除，旧关键词可在版本中重新载入。',{valid:()=>project===originalProject && generation===gen}))return;
          const r=await api('/api/profile/restore',{project_id:originalProject});
          if(project!==originalProject || generation!==gen)return;
          await options.refresh();options.notify(`已恢复默认。原固定词：${(r.previous_pinned_terms||[]).join('、')||'无'}`);
        } finally {b.disabled=false;}
      }
      else if(b.hasAttribute('data-history'))await showEvidence({kind:'feedback'});
      else if(b.hasAttribute('data-evidence')) {const q={kind:b.dataset.evidence};if(b.dataset.term)q.term=b.dataset.term;if(b.dataset.start){q.start=b.dataset.start;q.end=b.dataset.end;}await showEvidence(q);}
      else if(b.hasAttribute('data-more-evidence'))await showEvidence(evidenceQuery,true);
      else if(b.hasAttribute('data-retry-evidence'))await showEvidence(evidenceQuery);
      else if(b.hasAttribute('data-close-evidence')) {request++;dialog.close();dialog.remove();dialog=null;}
      else if(b.hasAttribute('data-paper')) {if(dialog)dialog.close();options.openPaper(b.dataset.paper);}
    } catch(error) {b.disabled=false;options.notify(error.message);}
  });
  return {render, invalidate(){generation++;request++;if(dialog){dialog.close();dialog.remove();dialog=null;}root.innerHTML=empty('正在读取当前项目画像…');}};
}
global.PDHProfile={create,esc,dashboard,kpiHTML,feedbackHTML,activityHTML,trendHTML};
if (typeof module !== 'undefined') module.exports=global.PDHProfile;
})(typeof window !== 'undefined' ? window : globalThis);
