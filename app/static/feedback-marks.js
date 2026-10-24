/* What the paper feedback buttons show (Today cards and the detail pane). Interest (saved / not interested) and
   difficulty are separate marks; the latest interest label wins, so a paper marked not interested does not also
   show as saved. Pressing a pressed mark takes it back (index.html feedbackClick). Pure: Node-testable. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PTMarks = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const INTEREST = ['useful', 'irrelevant'];

  /* c: {saved, feedback (interest label), familiarity}. */
  function view(c) {
    const irrelevant = c.feedback === 'irrelevant';
    return { saved: !!c.saved && !irrelevant, irrelevant: irrelevant, tooHard: c.familiarity === 'too_hard' };
  }

  /* The /api/detail reply carries the stored entry: its interest label and its familiarity label are separate. */
  function detailMarks(d) {
    const entry = d.feedback || {};
    const interest = INTEREST.indexOf(entry.action) >= 0 ? entry : {};
    return { key: d.key, saved: d.saved, feedback: interest.action || null, feedback_id: interest.id == null ? null : interest.id,
      familiarity: (entry.familiar || {}).action || null };
  }

  /* The two mark buttons. esc escapes text for HTML attributes. */
  function buttonsHTML(c, esc) {
    const v = view(c), key = esc(c.key), fid = c.feedback_id == null ? '' : esc(String(c.feedback_id));
    return `<button class="tiny" data-fb="irrelevant" data-key="${key}" data-fid="${fid}" aria-pressed="${v.irrelevant}">不感兴趣</button>
        <button class="tiny" data-fb="too_hard" data-key="${key}" aria-pressed="${v.tooHard}">太难</button>`;
  }

  return { view: view, detailMarks: detailMarks, buttonsHTML: buttonsHTML };
});
