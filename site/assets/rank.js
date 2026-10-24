/* Simplified demo ranking for the homepage: TF-IDF over the 29 demo papers, scored against the profile tags.
   Pure functions, no DOM, no network. The app itself ranks with the full profile and feedback; this is a stand-in. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PTRank = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var WEIGHTS = { strong: 3, weak: 1, off: 0 };
  var STOP = {};
  ("a an and are as at be been but by can for from has have in into is it its of on or such that the their then " +
   "there these this to was were which while with without not no than also both each other more most over under " +
   "via using use used we our new").split(" ").forEach(function (w) { STOP[w] = 1; });

  function stem(w) {
    if (w.length > 4 && /ies$/.test(w)) return w.slice(0, -3) + "y";
    if (w.length > 3 && /s$/.test(w) && !/(ss|us|is)$/.test(w)) w = w.slice(0, -1);
    if (w.length > 7 && /ment$/.test(w)) w = w.slice(0, -4);
    if (w.length > 6 && /ing$/.test(w)) w = w.slice(0, -3);
    else if (w.length > 5 && /ed$/.test(w)) w = w.slice(0, -2);
    return w;
  }

  function tokens(text) {
    var m = String(text).toLowerCase().match(/[\p{L}\p{N}]+/gu) || [];
    var out = [];
    for (var i = 0; i < m.length; i++) {
      var s = stem(m[i]);
      if (s.length > 1 && !STOP[s]) out.push(s);
    }
    return out;
  }

  /* papers: [{id, title, abstract}] -> index. The title counts twice; tf is sublinear; vectors are L2-normalised. */
  function buildIndex(papers) {
    var docs = [], df = {};
    papers.forEach(function (p, i) {
      var seq = tokens(p.title).concat(tokens(p.title), tokens(p.abstract));
      var tf = {};
      seq.forEach(function (t) { tf[t] = (tf[t] || 0) + 1; });
      Object.keys(tf).forEach(function (t) { df[t] = (df[t] || 0) + 1; });
      docs.push({ id: p.id, order: i, tf: tf, seq: tokens(p.title).concat(["|"], tokens(p.abstract)) });
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
      d.vec = vec;
    });
    return { docs: docs, idf: idf };
  }

  function hasPhrase(seq, toks) {
    for (var i = 0; i + toks.length <= seq.length; i++) {
      var ok = true;
      for (var j = 0; j < toks.length; j++) if (seq[i + j] !== toks[j]) { ok = false; break; }
      if (ok) return true;
    }
    return false;
  }

  /* tags: [{text, weight}] with weight in {0,1,3}. Returns {ranked:[{id,score,matched:[text]}], unmatched:[text]}.
     A tag scores a paper by the mean TF-IDF of its words in that paper (x1.5 when a multi-word tag appears as a phrase);
     the paper's score is the weighted sum over tags. Ties keep the library order, so an empty profile changes nothing. */
  function rank(index, tags) {
    var active = [];
    tags.forEach(function (t) {
      var toks = tokens(t.text);
      if (t.weight > 0 && toks.length) active.push({ text: t.text, w: t.weight, toks: toks });
    });
    var matchedSomewhere = {};
    var ranked = index.docs.map(function (d) {
      var score = 0, hits = [];
      active.forEach(function (a) {
        var sum = 0;
        a.toks.forEach(function (t) { sum += d.vec[t] || 0; });
        var s = sum / a.toks.length;
        if (s > 0 && a.toks.length > 1 && hasPhrase(d.seq, a.toks)) s *= 1.5;
        if (s > 0) { hits.push({ text: a.text, v: a.w * s }); matchedSomewhere[a.text] = 1; score += a.w * s; }
      });
      hits.sort(function (x, y) { return y.v - x.v; });
      return { id: d.id, score: score, order: d.order, matched: hits.map(function (h) { return h.text; }) };
    });
    ranked.sort(function (x, y) { return (y.score - x.score) || (x.order - y.order); });
    return {
      ranked: ranked,
      unmatched: active.filter(function (a) { return !matchedSomewhere[a.text]; }).map(function (a) { return a.text; })
    };
  }

  return { WEIGHTS: WEIGHTS, stem: stem, tokens: tokens, buildIndex: buildIndex, rank: rank };
});
