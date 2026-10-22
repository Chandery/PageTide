(function (root) {
  'use strict';
  const languages = {en:'英文',zh:'中文',ja:'日文',ko:'韩文',fr:'法文',de:'德文',es:'西班牙文',pt:'葡萄牙文',ru:'俄文',ar:'阿拉伯文',it:'意大利文',el:'希腊文',la:'拉丁文'};
  function validate(value) {
    if (!value || !['stem','humanities'].includes(value.discipline)) throw new Error('请选择理工科或文科');
    const allowed = value.discipline === 'stem' ? ['en'] : value.allowed_languages;
    if (!Array.isArray(allowed) || !allowed.length || allowed.some(code => !Object.hasOwn(languages, code))) throw new Error('请至少选择一种允许的论文语言');
    return {discipline:value.discipline, allowed_languages:[...new Set(allowed)]};
  }
  function mount(container, initial) {
    const doc = container.ownerDocument;
    const fieldset = doc.createElement('fieldset');
    const legend = doc.createElement('legend'); legend.textContent = '论文语言';
    const label = doc.createElement('label'); label.textContent = '学科';
    const select = doc.createElement('select'); select.setAttribute('aria-label','项目学科');
    [['','请选择学科'],['stem','理工科'],['humanities','文科']].forEach(([value,text]) => {
      const option=doc.createElement('option'); option.value=value; option.textContent=text; select.append(option);
    });
    label.append(select);
    const fixed=doc.createElement('p'); fixed.className='hint'; fixed.textContent='仅英文论文';
    const choices=doc.createElement('div'); choices.className='paper-language-choices';
    const boxes=[];
    Object.entries(languages).forEach(([code,name]) => {
      const row=doc.createElement('label'), box=doc.createElement('input');
      box.type='checkbox'; box.value=code; row.append(box,doc.createTextNode(name)); choices.append(row); boxes.push(box);
    });
    fieldset.append(legend,label,fixed,choices); container.replaceChildren(fieldset);
    container.classList.add('paper-language-editor');
    function show() { fixed.hidden=select.value!=='stem'; choices.hidden=select.value!=='humanities'; }
    select.onchange=show;
    function set(value) {
      select.value=value?.discipline || '';
      boxes.forEach(box => {box.checked=(value?.allowed_languages || []).includes(box.value);}); show();
    }
    set(initial);
    return {read:()=>validate({discipline:select.value,allowed_languages:boxes.filter(b=>b.checked).map(b=>b.value)}),
      set, disabled:value=>{fieldset.disabled=!!value;}};
  }
  function label(value) {
    if (!value || value.fulltext_status!=='verified') return '全文语言未核验';
    return '全文语言：'+(languages[value.fulltext_language] || value.fulltext_language)+'（已核验）';
  }
  function report(value) {
    const language=languages[value?.metadata_language] || value?.metadata_language || '未知';
    const source=value?.metadata_source ? '（'+value.metadata_source+'）' : '';
    const parts=['来源报告语言：'+language+source,label(value)];
    if (value?.title_metadata_conflict) parts.push('题名文字与英文来源报告不一致');
    return parts.join(' · ');
  }
  const api={languages,validate,mount,label,report};
  if (typeof module==='object' && module.exports) module.exports=api;
  root.PaperPolicy=api;
})(typeof window==='object'?window:globalThis);
