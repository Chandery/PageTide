/* "Today's 5": the front-page demo. Tags -> TF-IDF scores (rank.js) -> the five best papers, moved with FLIP. */
(function () {
  "use strict";
  var cfg = JSON.parse(document.getElementById("demo-i18n").textContent), ui = cfg.ui, lang = cfg.lang;
  var tagsEl = document.getElementById("tags"), storiesEl = document.getElementById("stories");
  var statusEl = document.getElementById("demo-status"), form = document.getElementById("add-form");
  var input = document.getElementById("add-input"), resetBtn = document.getElementById("reset");
  var MAX_TAGS = 12, TOP = 5, ORDER = ["strong", "weak", "off"];
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var papers = {}, index = null;
  var tags = cfg.default_tags.map(function (t) { return { text: t.text, w: t.w }; });

  function fmt(s, vars) { return s.replace(/\{(\w+)\}/g, function (_, k) { return vars[k]; }); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }

  function renderTags() {
    tagsEl.innerHTML = tags.map(function (t) {
      var w = ui[t.w], label = fmt(ui.tag_aria, { tag: t.text, weight: w });
      return '<li class="tag-item" data-w="' + t.w + '"><button type="button" class="tag" data-tag="' + esc(t.text) +
        '" aria-label="' + esc(label) + '"><span class="tag-text">' + esc(t.text) + '</span><span class="tag-w">' + esc(w) +
        '</span></button><button type="button" class="tag-x" data-remove="' + esc(t.text) + '" aria-label="' +
        esc(fmt(ui.remove, { tag: t.text })) + '"><span aria-hidden="true">×</span></button></li>';
    }).join("");
  }

  function storyInner(p, rank, matched) {
    var why = matched.length ? '<span class="why-label">' + esc(ui.matched) + '</span>' +
      matched.slice(0, 4).map(function (m) { return '<span class="kw">' + esc(m) + '</span>'; }).join("") : "";
    return '<p class="story-meta"><span class="rank" aria-hidden="true">' + rank + '</span><span class="st">' + esc(p.source) +
      '</span> <time datetime="' + esc(p.date) + '">' + esc(p.date) + '</time></p>' +
      '<h3><a href="https://arxiv.org/abs/' + esc(p.id) + '" rel="noopener">' + esc(p.title) + '</a></h3>' +
      '<p class="by">' + esc(p.authors[0]) + " " + esc(ui.et_al) + '</p><p class="blurb">' + esc(p.preview[lang]) + '</p>' +
      '<p class="why"' + (why ? "" : " hidden") + ">" + why + "</p>";
  }

  function currentTags() {
    return tags.map(function (t) { return { text: t.text, weight: PTRank.WEIGHTS[t.w] }; });
  }

  function update(opts) {
    opts = opts || {};
    var res = PTRank.rank(index, currentTags());
    var top = res.ranked.slice(0, TOP);
    var nothing = res.ranked.every(function (r) { return r.score === 0; });
    var existing = {};
    Array.prototype.forEach.call(storiesEl.children, function (li) { existing[li.getAttribute("data-id")] = li; });
    var first = {};
    Object.keys(existing).forEach(function (id) { first[id] = existing[id].getBoundingClientRect(); });

    var frag = document.createDocumentFragment(), created = [];
    top.forEach(function (r, i) {
      var li = existing[r.id];
      if (!li) { li = document.createElement("li"); li.setAttribute("data-id", r.id); created.push(li); }
      delete existing[r.id];
      li.className = "story" + (i === 0 ? " lead" : "");
      li.innerHTML = storyInner(papers[r.id], i + 1, nothing ? [] : r.matched);
      frag.appendChild(li);
    });
    storiesEl.innerHTML = "";
    storiesEl.appendChild(frag);

    if (!reduce) {
      Array.prototype.forEach.call(storiesEl.children, function (li) {
        var id = li.getAttribute("data-id"), f = first[id];
        if (!f) return;
        var l = li.getBoundingClientRect(), dx = f.left - l.left, dy = f.top - l.top;
        if (!dx && !dy) return;
        li.style.transition = "none";
        li.style.transform = "translate(" + dx + "px," + dy + "px)";
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            li.style.transition = "transform .45s cubic-bezier(.2,.8,.3,1)";
            li.style.transform = "";
          });
        });
      });
      created.forEach(function (li) {
        li.classList.add("enter");
        requestAnimationFrame(function () { requestAnimationFrame(function () { li.classList.remove("enter"); }); });
      });
    }

    var list = top.map(function (r, i) { return (i + 1) + ", " + papers[r.id].title; }).join(". ");
    var msg = "";
    if (res.unmatched.length) msg = fmt(ui.unmatched, { tags: res.unmatched.join(", ") });
    else if (nothing) msg = ui.nothing;
    statusEl.textContent = (opts.say ? opts.say + " " : "") + (opts.announce ? fmt(opts.announce, { list: list }) : "") +
      (msg ? " " + msg : "");
    statusEl.classList.toggle("warn", !!msg);
  }

  function cycle(text) {
    tags.forEach(function (t) {
      if (t.text === text) t.w = ORDER[(ORDER.indexOf(t.w) + 1) % ORDER.length];
    });
    renderTags();
    focusTag(text, ".tag");
    update({ announce: ui.announce });
  }
  function focusTag(text, sel) {
    var els = tagsEl.querySelectorAll(sel);
    for (var i = 0; i < els.length; i++) if (els[i].getAttribute(sel === ".tag" ? "data-tag" : "data-remove") === text) { els[i].focus(); return; }
  }

  tagsEl.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b || !index) return;
    if (b.hasAttribute("data-tag")) { cycle(b.getAttribute("data-tag")); return; }
    if (b.hasAttribute("data-remove")) {
      var text = b.getAttribute("data-remove"), at = 0;
      tags = tags.filter(function (t, i) { if (t.text === text) at = i; return t.text !== text; });
      renderTags();
      var next = tagsEl.querySelectorAll(".tag")[Math.min(at, tags.length - 1)];
      (next || input).focus();
      update({ say: fmt(ui.removed, { tag: text }), announce: ui.announce });
    }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!index) return;
    var text = input.value.replace(/\s+/g, " ").trim();
    if (!text) return;
    if (tags.length >= MAX_TAGS) { statusEl.textContent = ui.max; statusEl.classList.add("warn"); return; }
    var dupe = tags.some(function (t) { return t.text.toLowerCase() === text.toLowerCase(); });
    if (dupe) { statusEl.textContent = fmt(ui.dupe, { tag: text }); statusEl.classList.add("warn"); return; }
    tags.push({ text: text, w: "strong" });
    input.value = "";
    renderTags();
    update({ say: fmt(ui.added, { tag: text }), announce: ui.announce });
  });

  resetBtn.addEventListener("click", function () {
    if (!index) return;
    tags = cfg.default_tags.map(function (t) { return { text: t.text, w: t.w }; });
    renderTags();
    update({ announce: ui.reset_done });
  });

  fetch(cfg.papers_url).then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (list) {
    list.forEach(function (p) { papers[p.id] = p; });
    index = PTRank.buildIndex(list);
    update();   // the first render matches the prerendered HTML and only adds the "Matched" line
    statusEl.textContent = "";
  }).catch(function () {
    statusEl.textContent = ui.load_failed;
    statusEl.classList.add("warn");
  });
})();
