(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTPaperContext = api;
})(typeof window !== 'undefined' ? window : this, function() {
  const h = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  /* Where a paper sits: its categories and (learning-map beta) its units, with jumps to the graphs. Nothing else, and no
     box at all when there is nothing to show. */
  function html(context, key, showCategories = true) {
    if (!context) return '';
    const c = context;
    const beta = !(typeof window !== 'undefined' && window.PAGETIDE_ROUTE_BETA === false);
    const map = beta && c.map_available;
    const jump = (view, label, unit = '') => `<button type="button" class="org-link-button" data-action="graph-navigate" data-key="${h(key)}" data-project="${h(c.project_id)}" data-view="${view}" data-unit="${h(unit)}">${h(label)}</button>`;
    const categories = showCategories && c.categories.length ? `<p><b>收藏类别</b> <span data-no-i18n>${c.categories.map(d => h(d.name)).join(' · ')}</span></p>` : '';
    const units = map && c.units.length
      ? `<p><b>学习单元</b> ${c.units.map(u => `<span data-no-i18n>${h(u.name)}</span>${c.saved_in_project ? jump('route','定位学习单元',u.id) : ''}`).join(' · ')}</p>` : '';
    const retry = map ? `<button type="button" data-action="learning-match-retry" data-key="${h(key)}" data-project="${h(c.project_id)}">重新匹配</button>` : '';
    const tools = c.saved_in_project ? `<div class="org-tools">${jump('papers','在论文关系图中定位')}${map ? jump('route','在学习图中定位') : ''}</div>` : '';
    const body = categories + units + retry + tools;
    return body ? `<section class="paper-context" aria-label="${beta ? '分类与学习用途' : '分类'}">${body}</section>` : '';
  }
  return {html};
});
