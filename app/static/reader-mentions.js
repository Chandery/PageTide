/* A note can @ other notes. In the 笔记 list that is drawn as arrows in a gutter on the cards' left side, from the note
   that @s to each note it @s. To stay readable with several @s: one trunk per @-ing note, branching to its targets (not
   one line per pair); trunks whose stretches overlap get lanes side by side; arrows into the same note are spread a few
   pixels apart. Only geometry lives here; the reader (index.html) measures the cards and draws the SVG. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTReaderMentions = api;
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  const LANE = 7, EDGE = 6, LANES_SHOWN = 6, FAN = 4, HEAD = 5;

  /* notes: [{id, mentions}] in list order; boxes: {id: {top, bottom}} in the list's pixels. Returns the gutter's width
     (0 when there is nothing to draw; at least `minWidth` otherwise) and one group per @-ing note: {src, lane, x, srcY, targets: [{id, y}], crowded}. */
  function arrows(notes, boxes, minWidth = 0) {
    const sources = [];
    const incoming = new Map();
    for (const note of notes || []) {
      if (!boxes[note.id]) continue;
      const targets = [...new Set(note.mentions || [])].filter((id) => id !== note.id && boxes[id]);
      if (!targets.length) continue;
      sources.push({id: note.id, targets});
      for (const id of targets) incoming.set(id, (incoming.get(id) || []).concat(note.id));
    }
    const groups = sources.map(({id, targets}) => {
      const box = boxes[id];
      return {src: id, srcY: (box.top + box.bottom) / 2, targets: targets.map((target) => {
        const t = boxes[target], from = incoming.get(target), k = from.length;
        const spread = (from.indexOf(id) - (k - 1) / 2) * FAN, mid = (t.top + t.bottom) / 2;
        return {id: target, y: Math.min(Math.max(mid + spread, t.top + 6), Math.max(t.top + 6, t.bottom - 6))};
      })};
    });
    const span = (g) => [Math.min(g.srcY, ...g.targets.map((t) => t.y)), Math.max(g.srcY, ...g.targets.map((t) => t.y))];
    const laneEnd = [];
    for (const g of groups.slice().sort((a, b) => span(a)[0] - span(b)[0])) {
      const [start, end] = span(g);
      let lane = laneEnd.findIndex((last) => last + FAN < start);
      if (lane < 0) lane = laneEnd.length;
      laneEnd[lane] = end;
      g.lane = Math.min(lane, LANES_SHOWN - 1);
      g.crowded = lane >= LANES_SHOWN;   // more overlapping trunks than lanes: these share the last lane
    }
    if (!groups.length) return {width: 0, groups};
    const lanes = Math.min(laneEnd.length, LANES_SHOWN), width = Math.max(minWidth, EDGE * 2 + lanes * LANE);
    for (const g of groups) g.x = width - EDGE - g.lane * LANE;
    return {width, groups};
  }

  /* One group as SVG pieces, in the gutter's own pixels: `d` (the trunk and its stubs), `dot` (where it leaves the @-ing
     card) and `heads` (a triangle at each target, as a points string). */
  function shape(group, width) {
    const ys = group.targets.map((t) => t.y);
    const lo = Math.min(group.srcY, ...ys), hi = Math.max(group.srcY, ...ys);
    let d = `M${width} ${group.srcY}H${group.x}M${group.x} ${lo}V${hi}`;
    const heads = [];
    for (const y of ys) {
      d += `M${group.x} ${y}H${width - HEAD}`;
      heads.push(`${width - 0.5},${y} ${width - HEAD - 1},${y - 3} ${width - HEAD - 1},${y + 3}`);
    }
    return {d, dot: {cx: width - 0.5, cy: group.srcY}, heads};
  }

  /* The notes the picker offers: not the note itself nor ones it already @s, in the order given, narrowed by a typed
     word that must appear in the note's quote, text or page ("3" finds 第 3 页). */
  function candidates(notes, selfId, taken, query) {
    const q = String(query || '').trim().toLowerCase();
    return (notes || []).filter((n) => n.id !== selfId && !(taken || []).includes(n.id)
      && (!q || `${n.quote || ''}\n${n.comment || ''}\n第 ${n.page} 页`.toLowerCase().includes(q)));
  }

  /* A short name for a note: its quote, else its text, cut to `max` characters. */
  function label(note, max = 28) {
    const raw = String((note && (note.quote || note.comment)) || '').replace(/\s+/g, ' ').trim();
    return raw.length > max ? raw.slice(0, max).trimEnd() + '…' : raw;
  }

  /* Who @s this note (the ids), for the "被 @" count. */
  function mentionedBy(notes, id) {
    return (notes || []).filter((n) => (n.mentions || []).includes(id)).map((n) => n.id);
  }

  /* ---- numbers and the @ in the text ------------------------------------------------------------------------------
     Notes are numbered from the top of the paper down (1, 2, 3 ...). In the text box a reference reads "@3"; stored it is
     "@[<note id>]", so numbers may change when notes are added above without any reference pointing at the wrong note. */
  const TOKEN = /@\[([0-9a-f]{32})\]/g;
  const TYPED = /(^|[^\w@])@(\d{1,4})(?!\d)/g;   // "@3" at the start or after anything but a letter, digit or @
  const GONE = '@✕';                              // what a reference becomes when its note is deleted

  /* notes: in reading order. Returns {numberOf: Map id -> n, idOf: Map n -> id}. */
  function numbering(notes) {
    const numberOf = new Map(), idOf = new Map();
    (notes || []).forEach((n, i) => { numberOf.set(n.id, i + 1); idOf.set(i + 1, n.id); });
    return {numberOf, idOf};
  }

  /* Stored text -> what the text box shows. A reference to a note that is not there shows as the deleted marker. */
  function toEditable(comment, numberOf) {
    return String(comment || '').replace(TOKEN, (m, id) => (numberOf.has(id) ? '@' + numberOf.get(id) : GONE));
  }

  /* What the text box holds -> stored text: "@3" naming a note (not this one) becomes its reference; anything else stays. */
  function fromEditable(text, idOf, selfId) {
    return String(text || '').replace(TYPED, (m, before, n) => {
      const id = idOf.get(Number(n));
      return id && id !== selfId ? `${before}@[${id}]` : m;
    });
  }

  /* The note ids a stored text refers to, in order, once each. */
  function ids(comment) {
    return [...new Set([...String(comment || '').matchAll(TOKEN)].map((m) => m[1]))];
  }

  /* A stored text as pieces for drawing: {text} or {n, id} (a reference with its current number; a deleted one is text). */
  function segments(comment, numberOf) {
    const out = [], raw = String(comment || '');
    let last = 0;
    for (const m of raw.matchAll(TOKEN)) {
      if (m.index > last) out.push({text: raw.slice(last, m.index)});
      out.push(numberOf.has(m[1]) ? {n: numberOf.get(m[1]), id: m[1]} : {text: GONE});
      last = m.index + m[0].length;
    }
    if (last < raw.length) out.push({text: raw.slice(last)});
    return out;
  }

  /* Puts "@n" into the text box's value at the selection [start, end). When the "@" was just typed (`typed`) it is the
     character before `start` and is replaced. A space goes in before when a letter or digit precedes (so it reads as a
     reference) and after unless whitespace or punctuation follows. Returns {value, caret}. */
  function insertMention(value, start, end, n, typed) {
    const text = String(value || '');
    const from = typed && text[start - 1] === '@' ? start - 1 : start;
    const before = text.slice(0, from), after = text.slice(end);
    const lead = /[A-Za-z0-9_]$/.test(before) ? ' ' : '';
    const tail = after === '' || !/^[\s，。、；：！？,.;:!?)）]/.test(after) ? ' ' : '';
    const token = `${lead}@${n}${tail}`;
    return {value: before + token + after, caret: before.length + token.length};
  }

  return {arrows, shape, candidates, label, mentionedBy, numbering, toEditable, fromEditable, ids, segments, insertMention,
          GONE, LANE, EDGE, LANES_SHOWN};
});
