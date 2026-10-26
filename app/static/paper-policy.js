(function (root) {
  'use strict';
  const languages = {en:'英文',zh:'中文',ja:'日文',ko:'韩文',fr:'法文',de:'德文',es:'西班牙文',pt:'葡萄牙文',ru:'俄文',ar:'阿拉伯文',it:'意大利文',el:'希腊文',la:'拉丁文'};
  // The editor offers the two languages people choose between. A project saved earlier with other languages keeps
  // them: they appear as extra ticked boxes, so nothing is dropped unless the person unticks it.
  const OFFERED = ['zh', 'en'];
  let mounted = 0;
  const known = code => typeof code === 'string' && Object.hasOwn(languages, code);
  function validate(value) {
    const allowed = value && Array.isArray(value.allowed_languages) ? value.allowed_languages : [];
    if (!allowed.length || !allowed.every(known)) throw new Error('请至少选择一种论文语言');
    return {allowed_languages: [...new Set(allowed)]};
  }
  // `options.onChange(selected)` runs after the person ticks or unticks a language; `note(text)` shows one quiet line under
  // the boxes (for example that a ticked language has no source switched on), `note('')` hides it.
  function mount(container, initial, options = {}) {
    const doc = container.ownerDocument;
    const fieldset = doc.createElement('fieldset');
    // A heading inside the card, like the other cards' titles (a legend would sit on the fieldset's border).
    const heading = doc.createElement('h3'); heading.id = 'paperLanguageTitle' + (++mounted); heading.textContent = '论文语言';
    fieldset.setAttribute('aria-labelledby', heading.id);
    const choices = doc.createElement('div'); choices.className = 'paper-language-choices';
    const error = doc.createElement('p'); error.className = 'field-error'; error.setAttribute('role', 'alert'); error.hidden = true;
    const hint = doc.createElement('p'); hint.className = 'field-note'; hint.setAttribute('role', 'status'); hint.hidden = true;
    let boxes = [];
    function fail(message, focus = true) {
      error.textContent = message || ''; error.hidden = !message;
      boxes.forEach(box => { if (message) box.setAttribute('aria-invalid', 'true'); else box.removeAttribute('aria-invalid'); });
      if (message && focus && boxes[0]) { boxes[0].scrollIntoView({behavior: 'smooth', block: 'center'}); boxes[0].focus({preventScroll: true}); }
    }
    function note(text) { hint.textContent = text || ''; hint.hidden = !text; }
    function row(code) {
      const label = doc.createElement('label'), box = doc.createElement('input');
      box.type = 'checkbox'; box.value = code;
      box.onchange = () => { fail(''); if (typeof options.onChange === 'function') options.onChange(selected()); };
      label.append(box, doc.createTextNode(languages[code])); choices.append(label);
      return box;
    }
    fieldset.append(heading, choices, error, hint); container.replaceChildren(fieldset);
    container.classList.add('paper-language-editor');
    const selected = () => boxes.filter(box => box.checked).map(box => box.value);
    function set(value) {
      const saved = Array.isArray(value && value.allowed_languages) ? value.allowed_languages.filter(known) : [];
      choices.replaceChildren();
      boxes = [...OFFERED, ...saved.filter(code => !OFFERED.includes(code))].map(row);
      boxes.forEach(box => { box.checked = saved.includes(box.value); });
      fail('');
    }
    set(initial);
    return {read: () => validate({allowed_languages: selected()}), selected, set, error: fail, note,
      disabled: value => { fieldset.disabled = !!value; }};
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
