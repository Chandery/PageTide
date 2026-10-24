/* Simplified demo ranking for the homepage: TF-IDF over the demo library, scored against the profile tags.
   Pure functions, no DOM, no network. The app itself ranks with the full profile and feedback; this is a stand-in.
   Latin words are lower-cased and lightly stemmed, and a word also matches longer words that start with it (robot -> robotics).
   Chinese keywords match the hand-written Chinese keywords and one-liners of each paper (exact keyword scores highest). */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PTRank = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var WEIGHTS = { strong: 3, weak: 1, off: 0 };
  var PREFIX_FACTOR = 0.8, HAN_UNIT = 0.07;
  var STOP = {};
  ("a an and are as at be been but by can for from has have in into is it its of on or such that the their then " +
   "there these this to was were which while with without not no than also both each other more most over under " +
   "via using use used we our new").split(" ").forEach(function (w) { STOP[w] = 1; });

  function stem(w) {
    if (w.length > 4 && /ies$/.test(w)) return w.slice(0, -3) + "y";
    if (w.length > 3 && /s$/.test(w) && !/(ss|us|is)$/.test(w)) w = w.slice(0, -1);
    if (w.length > 8 && /ation$/.test(w)) w = w.slice(0, -5);
    if (w.length > 7 && /ment$/.test(w)) w = w.slice(0, -4);
    if (w.length > 6 && /ing$/.test(w)) w = w.slice(0, -3);
    else if (w.length > 5 && /ed$/.test(w)) w = w.slice(0, -2);
    return w;
  }

  /* Latin-script words, stemmed, stop words removed. Han characters are handled separately (hanRuns). */
  function tokens(text) {
    var m = String(text).toLowerCase().match(/[\p{Script=Latin}\p{N}]+/gu) || [];
    var out = [];
    for (var i = 0; i < m.length; i++) {
      var s = stem(m[i]);
      if (s.length > 1 && !STOP[s]) out.push(s);
    }
    return out;
  }
  function hanRuns(text) { return String(text).match(/\p{Script=Han}+/gu) || []; }

  /* Raw demo data ({topics, papers}) -> the {id, title, abstract, zh, zhkw} records that buildIndex reads. */
  function prepare(data, lang) {
    return data.papers.map(function (p) {
      var t = data.topics[p.topic] || { en: "", zh: "" };
      var kwEn = (p.kw && p.kw.en) || "", kwZh = (p.kw && p.kw.zh) || "";
      return {
        id: p.id, title: p.title,
        abstract: (p.abstract || p.preview.en) + " " + kwEn.replace(/;/g, " ") + " " + t.en,
        zh: p.preview.zh + " " + kwZh + " " + t.zh,
        zhkw: kwZh.split(/[;；]/).map(function (s) { return s.trim(); }).filter(Boolean).concat([t.zh])
      };
    });
  }

  /* papers: [{id, title, abstract, zh?, zhkw?}] -> index. The title counts twice; tf is sublinear; vectors are L2-normalised. */
  function buildIndex(papers) {
    var docs = [], df = {};
    papers.forEach(function (p, i) {
      var seq = tokens(p.title).concat(tokens(p.title), tokens(p.abstract));
      var tf = {};
      seq.forEach(function (t) { tf[t] = (tf[t] || 0) + 1; });
      Object.keys(tf).forEach(function (t) { df[t] = (df[t] || 0) + 1; });
      docs.push({ id: p.id, order: i, tf: tf, seq: tokens(p.title).concat(["|"], tokens(p.abstract)),
                  zh: p.zh || "", zhkw: p.zhkw || [] });
    });
    var n = papers.length, idf = {};
    Object.keys(df).forEach(function (t) { idf[t] = Math.log((n + 1) / (df[t] + 1)) + 1; });
    docs.forEach(function (d) {
      var vec = {}, norm = 0;
      Object.keys(d.tf).forEach(function (t) {
        var v = (1 + Math.log(d.tf[t])) * idf[t];
        vec[t] = v; norm += v * v;
      });
      norm = Math.sqrt(norm) || 1;
      Object.keys(vec).forEach(function (t) { vec[t] /= norm; });
      d.vec = vec; d.terms = Object.keys(vec);
    });
    return { docs: docs, idf: idf, n: n, hanCache: {} };
  }

  function hasPhrase(seq, toks) {
    for (var i = 0; i + toks.length <= seq.length; i++) {
      var ok = true;
      for (var j = 0; j < toks.length; j++) if (seq[i + j] !== toks[j]) { ok = false; break; }
      if (ok) return true;
    }
    return false;
  }

  /* How strongly one stemmed word is present in a document: the word itself, or (for 4+ letters) a longer word starting with it. */
  function wordScore(d, t) {
    if (d.vec[t]) return d.vec[t];
    if (t.length < 4) return 0;
    var best = 0;
    for (var i = 0; i < d.terms.length; i++) {
      var w = d.terms[i];
      if (w.length > t.length && w.lastIndexOf(t, 0) === 0 && d.vec[w] > best) best = d.vec[w];
    }
    return best * PREFIX_FACTOR;
  }

  /* One Chinese phrase: the strongest of an exact keyword, a substring of the text, or (4+ characters) a 3+ character part. */
  function hanMatch(d, run) {
    if (d.zhkw.indexOf(run) >= 0) return 1;
    if (d.zh.indexOf(run) >= 0) return 0.7;
    if (run.length >= 4 && (d.zh.indexOf(run.slice(0, -1)) >= 0 || d.zh.indexOf(run.slice(1)) >= 0)) return 0.45;
    return 0;
  }
  function hanWeight(index, run) {
    if (index.hanCache[run] === undefined) {
      var df = 0;
      index.docs.forEach(function (d) { if (hanMatch(d, run) > 0) df++; });
      index.hanCache[run] = HAN_UNIT * (Math.log((index.n + 1) / (df + 1)) + 1);
    }
    return index.hanCache[run];
  }

  /* tags: [{text, weight}] with weight in {0,1,3}. Returns {ranked:[{id,score,matched:[text]}], unmatched:[text]}.
     A tag scores a paper by the mean score of its words (x1.5 when a multi-word tag appears as a phrase); the paper's score
     is the weighted sum over tags. Ties keep the library order, so an empty profile changes nothing. */
  function rank(index, tags) {
    var active = [];
    tags.forEach(function (t) {
      var toks = tokens(t.text), han = hanRuns(t.text);
      if (t.weight > 0 && (toks.length || han.length)) active.push({ text: t.text, w: t.weight, toks: toks, han: han });
    });
    var matchedSomewhere = {};
    var ranked = index.docs.map(function (d) {
      var score = 0, hits = [];
      active.forEach(function (a) {
        var sum = 0, parts = a.toks.length + a.han.length;
        a.toks.forEach(function (t) { sum += wordScore(d, t); });
        a.han.forEach(function (r) { sum += hanMatch(d, r) * hanWeight(index, r); });
        var s = sum / parts;
        if (s > 0 && a.toks.length > 1 && hasPhrase(d.seq, a.toks)) s *= 1.5;
        if (s > 0) { hits.push({ text: a.text, v: a.w * s }); matchedSomewhere[a.text] = 1; score += a.w * s; }
      });
      hits.sort(function (x, y) { return y.v - x.v; });
      var parts = {};
      hits.forEach(function (h) { parts[h.text] = h.v; });
      return { id: d.id, score: score, order: d.order, matched: hits.map(function (h) { return h.text; }), parts: parts };
    });
    ranked.sort(function (x, y) { return (y.score - x.score) || (x.order - y.order); });
    return {
      ranked: ranked,
      unmatched: active.filter(function (a) { return !matchedSomewhere[a.text]; }).map(function (a) { return a.text; })
    };
  }

  /* The n papers to show. The best overall paper comes first; then every keyword that no chosen paper yet represents gets its own
     best paper (strong keywords first, the most recently added first), so a new keyword always shows up on the page; leftover
     slots go to the next best overall. The chosen papers are listed best score first. tags: the same list that was ranked. */
  function pickTop(res, tags, n) {
    var ranked = res.ranked, chosen = [], byId = {};
    ranked.forEach(function (r) { byId[r.id] = r; });
    function add(r) { if (r && r.score > 0 && chosen.indexOf(r) < 0 && chosen.length < n) chosen.push(r); }
    var order = tags.map(function (t, i) { return { text: t.text, w: t.weight, i: i }; })
      .filter(function (t) { return t.w > 0; })
      .sort(function (a, b) { return (b.w - a.w) || (b.i - a.i); });
    add(ranked[0]);
    order.forEach(function (t) {
      var best = null, bestV = 0;
      ranked.forEach(function (r) { var v = r.parts[t.text] || 0; if (v > bestV) { best = r; bestV = v; } });
      if (!best) return;
      var represented = chosen.some(function (c) { return (c.parts[t.text] || 0) >= 0.6 * bestV; });
      if (!represented) add(best);
    });
    ranked.forEach(add);
    if (chosen.length < n) ranked.forEach(function (r) { if (chosen.indexOf(r) < 0 && chosen.length < n) chosen.push(r); });
    return chosen.sort(function (a, b) { return (b.score - a.score) || (a.order - b.order); });
  }

  return { pickTop: pickTop, WEIGHTS: WEIGHTS, stem: stem, tokens: tokens, hanRuns: hanRuns, prepare: prepare, buildIndex: buildIndex, rank: rank };
});
