/* Shared fixed requirements form and revision preview. Text stays data. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PDHBrief = api;
})(typeof window !== 'undefined' ? window : this, function () {
  const FIELDS = [
    ['goal', '学习目标', 250, '例如：能读懂并复现基础世界模型论文'],
    ['known', '已知基础', 150, '例如：会概率论，没学过强化学习；留空表示未说明'],
    ['include', '希望包含', 150, '例如：潜变量、评估方法'],
    ['exclude', '希望排除', 150, '例如：本轮不学机器人硬件'],
    ['structure', '结构意见', 500, '粘贴老师的意见，例如：先补概率，再学潜变量；合并重复概念'],
  ];
  const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function validate(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(k => !FIELDS.some(f => f[0] === k))) throw new Error('学习需求必须使用固定五字段');
    const out = {};
    for (const [key, label, cap] of FIELDS) {
      const text = value[key] === undefined ? '' : value[key];
      if (typeof text !== 'string' || [...text].length > cap || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(text)) throw new Error(`${label}必须是文本且不超过 ${cap} 个字符`);
      out[key] = text.trim();
    }
    if (!out.goal) throw new Error('请填写学习目标');
    return out;
  }
  function mount(holder, value = {}) {
    holder.innerHTML = FIELDS.map(([key, label, cap, placeholder]) => `<label class="brief-field"><span>${label}${key === 'goal' ? '（必填）' : ''} · 最多 ${cap} 字</span><textarea data-brief="${key}" rows="${key === 'structure' ? 3 : 2}" placeholder="${esc(placeholder)}"></textarea></label>`).join('');
    set(holder, value);
  }
  function set(holder, value = {}) {
    for (const [key] of FIELDS) holder.querySelector(`[data-brief="${key}"]`).value = typeof value[key] === 'string' ? value[key] : '';
  }
  function read(holder) {
    return validate(Object.fromEntries(FIELDS.map(([key]) => [key, holder.querySelector(`[data-brief="${key}"]`).value])));
  }
  function names(graph, ids) {
    return (ids || []).map(id => ((graph?.concepts || []).find(c => c.id === id) || {}).name || '已删除概念').join('、');
  }
  function previewHTML(preview) {
    if (!preview) return '';
    const before = preview.before || {}, after = preview.after || {}, changes = preview.changes || {};
    const rows = [];
    for (const [kind, label] of [['added','新增'],['removed','删除'],['updated','修改'],['reset','重新计算掌握']]) {
      if (changes[kind]?.length) rows.push(`<tr><th>${label}</th><td>${esc(names(kind === 'removed' ? before.graph : after.graph, changes[kind]))}</td></tr>`);
    }
    const briefs = FIELDS.filter(([k]) => (before.brief?.[k] || '') !== (after.brief?.[k] || '')).map(([k,label]) => `<tr><th>${label}</th><td>${esc(before.brief?.[k] || '未说明')}</td><td>${esc(after.brief?.[k] || '未说明')}</td></tr>`).join('');
    const status = key => ({completed:'当前目标已完成',learning:'当前目标学习中',needs_review:'目标或前置关系需要检查'})[key] || '尚无目标状态';
    return `<h3>修改预览</h3><p>${esc(status(before.goal_status))} → ${esc(status(after.goal_status))}</p>
      <p>目标：${esc(names(before.graph, before.graph?.targets))} → ${esc(names(after.graph, after.graph?.targets))}</p>
      ${rows.length ? `<table class="revision-table"><tbody>${rows.join('')}</tbody></table>` : '<p>没有结构修改。</p>'}
      ${briefs ? `<table class="revision-table"><thead><tr><th>需求</th><th>原需求</th><th>新需求</th></tr></thead><tbody>${briefs}</tbody></table>` : ''}
      ${(changes.warnings || []).map(w => {
        const relation = w && typeof w === 'object' ? `${names(after.graph, [w.from])} → ${names(after.graph, [w.to])}` : '';
        const text = typeof w === 'string' ? w : w?.kind === 'prerequisite_review'
          ? `请核对这条前置是否必要：${relation}。依据：${w.reason || '未说明；建议补充依据或删除关系'}`
          : w?.kind === 'hint_inversion' ? `前置难度高于后续概念：${relation}` : '请核对学习关系';
        return `<p class="map-note">${esc(text)}</p>`;
      }).join('')}
      <p class="map-note">新增或语义改变的任务不继承旧掌握；兴趣反馈和论文历史保留。人工简介与稳定节点的关注保持。</p>
      ${preview.stale ? '<p class="notice error">学习图或有效反馈已变化，草稿保留；请重新生成预览后确认。</p>' : ''}
      ${preview.confirmed ? '<p class="notice">这次修改已确认。</p>' : ''}`;
  }
  return {FIELDS, validate, mount, set, read, previewHTML};
});
