(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PDHPaperContext = api;
})(typeof window !== 'undefined' ? window : this, function() {
  const h = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const purpose = {route:'学习路径', remedial:'补前置', explore:'探索方向', explore_new:'探索方向', watch:'关注新进展', normal:'普通推荐'};
  function html(context, key, showCategories = true) {
    if (!context) return '';
    const c = context, recommendation = c.recommendation;
    const jump = (view, label, unit = '') => `<button type="button" class="org-link-button" data-action="graph-navigate" data-key="${h(key)}" data-project="${h(c.project_id)}" data-view="${view}" data-unit="${h(unit)}">${h(label)}</button>`;
    return `<section class="paper-context" aria-label="分类与学习用途">${showCategories ? `<p><b>收藏类别</b> <span data-no-i18n>${c.categories.length ? c.categories.map(d => h(d.name)).join(' · ') : '—'}</span></p>` : ''}<p><b>对应学习单元</b> ${c.map_available ? (c.units.length ? c.units.map(u => `<span data-no-i18n>${h(u.name)}</span>${c.saved_in_project ? jump('route','定位学习单元',u.id) : ''}`).join(' · ') : '没有对应的学习单元') : '这个项目还没有学习图'}</p><p class="hint">对应关系来自标题与摘要检索词，不会改动收藏类别或掌握状态。</p>${c.map_available && !c.route_enabled ? '<p class="hint">Route 已关闭；学习图仍保留。</p>' : ''}<p><b>本次推荐用途</b> ${recommendation ? h(purpose[recommendation.kind] || '历史用途') : '不在本项目当前推荐批次'}${recommendation?.name ? ` · <span data-no-i18n>${h(recommendation.name)}</span>` : ''}</p>${c.saved_in_project ? `<div class="org-tools">${jump('papers','在论文关系图中定位')}${c.map_available ? jump('route','在学习图中定位') : ''}</div>` : '<p class="hint">收藏到这个项目后，可在图中定位论文。</p>'}</section>`;
  }
  return {html};
});
