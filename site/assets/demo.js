/* "Try the profile": the front-page demo. Tags -> TF-IDF scores (rank.js) -> the five best papers, moved with FLIP. */
(function () {
  "use strict";
  var cfg = JSON.parse(document.getElementById("demo-i18n").textContent), ui = cfg.ui, lang = cfg.lang;
  var tagsEl = document.getElementById("tags"), storiesEl = document.getElementById("stories");
  var statusEl = document.getElementById("demo-status"), form = document.getElementById("add-form");
  var input = document.getElementById("add-input"), resetBtn = document.getElementById("reset");
  var examplesEl = document.querySelector(".examples");
  var MAX_TAGS = 12, TOP = 5, ORDER = ["strong", "weak", "off"];
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var papers = {}, index = null, pending = [];
  var tags = cfg.default_tags.map(function (t) { return { text: t.text, w: t.w }; });

  function fmt(s, vars) { return s.replace(/\{(\w+)\}/g, function (_, k) { return vars[k]; }); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function same(a, b) { return a.toLowerCase() === b.toLowerCase(); }

  function renderTags() {
    tagsEl.innerHTML = tags.map(function (t) {
      var w = ui[t.w], label = fmt(ui.tag_aria, { tag: t.text, weight: w });
      return '<li class="tag-item" data-w="' + t.w + '"><button type="button" class="tag" data-tag="' + esc(t.text) +
        '" aria-label="' + esc(label) + '"><span class="tag-text">' + esc(t.text) + '</span><span class="tag-w">' + esc(w) +
        '</span></button><button type="button" class="tag-x" data-remove="' + esc(t.text) + '" aria-label="' +
        esc(fmt(ui.remove, { tag: t.text })) + '"><span aria-hidden="true">×</span></button></li>';
    }).join("");
  }

  /* A keyword that matches nothing gets a dashed chip and a "no match" label, so it never looks broken. */
  function markUnmatched(list) {
    Array.prototype.forEach.call(tagsEl.querySelectorAll(".tag-item"), function (li) {
      var b = li.querySelector(".tag"), text = b.getAttribute("data-tag"), w = li.getAttribute("data-w");
      var none = list.some(function (u) { return u === text; });
      li.classList.toggle("nomatch", none);
      b.querySelector(".tag-w").textContent = none ? ui.nomatch_label : ui[w];
    });
  }

  function storyInner(p, rank, matched) {
    var why = matched.length ? '<span class="why-label">' + esc(ui.matched) + '</span>' +
      matched.slice(0, 4).map(function (m) { return '<span class="kw">' + esc(m) + '</span>'; }).join("") : "";
    return '<p class="story-meta"><span class="rank" aria-hidden="true">' + rank + '</span><span class="st">arXiv</span> <time datetime="' +
      esc(p.date) + '">' + esc(p.date) + '</time></p>' +
      '<h3><a href="https://arxiv.org/abs/' + esc(p.id) + '" rel="noopener">' + esc(p.title) + '</a></h3>' +
      '<p class="by">' + esc(p.by) + " " + esc(ui.et_al) + '</p><p class="blurb">' + esc(p.preview[lang]) + '</p>' +
      '<p class="why"' + (why ? "" : " hidden") + ">" + why + "</p>";
  }

  function currentTags() {
    return tags.map(function (t) { return { text: t.text, weight: PTRank.WEIGHTS[t.w] }; });
  }

  /* opts: say (text before the announcement), announce (message with {list}), focus (a keyword whose matching cards get highlighted). */
  function update(opts) {
    opts = opts || {};
    var res = PTRank.rank(index, currentTags());
    var top = PTRank.pickTop(res, currentTags(), TOP);
    var nothing = res.ranked.every(function (r) { return r.score === 0; });
    var existing = {};
    Array.prototype.forEach.call(storiesEl.children, function (li) { existing[li.getAttribute("data-id")] = li; });
    var first = {};
    Object.keys(existing).forEach(function (id) { first[id] = existing[id].getBoundingClientRect(); });

    var frag = document.createDocumentFragment(), created = [], hit = [];
    top.forEach(function (r, i) {
      var li = existing[r.id];
      if (!li) { li = document.createElement("li"); li.setAttribute("data-id", r.id); created.push(li); }
      delete existing[r.id];
      li.className = "story" + (i === 0 ? " lead" : "");
      li.innerHTML = storyInner(papers[r.id], i + 1, nothing ? [] : r.matched);
      if (opts.focus && r.matched.indexOf(opts.focus) >= 0) hit.push(li);
      frag.appendChild(li);
    });
    storiesEl.innerHTML = "";
    storiesEl.appendChild(frag);
    markUnmatched(res.unmatched);

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
    hit.forEach(function (li) { li.classList.add("hl"); setTimeout(function () { li.classList.remove("hl"); }, 2200); });
    if (opts.focus) {   // bring the re-ranked list into view if the reader added a keyword from further up or down the page
      var r = storiesEl.getBoundingClientRect();
      if (r.top < 70 || r.top > window.innerHeight * 0.6) {
        window.scrollTo({ top: window.pageYOffset + r.top - 90, behavior: reduce ? "auto" : "smooth" });
      }
    }

    var list = top.map(function (r, i) { return (i + 1) + ", " + papers[r.id].title; }).join(". ");
    var msg = "";
    if (res.unmatched.length) msg = fmt(ui.unmatched, { tags: res.unmatched.join("”, “") });
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
    var hit = tagsEl.querySelector('.tag[data-tag="' + (window.CSS && CSS.escape ? CSS.escape(text) : text) + '"]');
    if (hit) hit.parentNode.classList.add("pop");
    update({ announce: ui.announce });
  }
  function focusTag(text, sel) {
    var els = tagsEl.querySelectorAll(sel);
    for (var i = 0; i < els.length; i++) if (els[i].getAttribute(sel === ".tag" ? "data-tag" : "data-remove") === text) { els[i].focus(); return; }
  }

  /* New keywords start strong and re-rank at once. An existing one is switched to strong instead of being refused. */
  function addTag(raw) {
    if (!index) { pending.push(raw); return; }   // clicked before the library finished loading
    var text = raw.replace(/\s+/g, " ").trim();
    if (!text) return;
    var found = tags.filter(function (t) { return same(t.text, text); })[0];
    if (found) {
      found.w = "strong"; text = found.text;
    } else {
      if (tags.length >= MAX_TAGS) { statusEl.textContent = ui.max; statusEl.classList.add("warn"); return; }
      tags.push({ text: text, w: "strong" });
    }
    renderTags();
    var chip = tagsEl.querySelector('.tag[data-tag="' + (window.CSS && CSS.escape ? CSS.escape(text) : text) + '"]');
    if (chip) chip.parentNode.classList.add("pop");
    update({ say: fmt(ui.added, { tag: text }), announce: ui.announce, focus: text });
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
    addTag(input.value);
    input.value = "";
  });

  if (examplesEl) examplesEl.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-add]");
    if (b) addTag(b.getAttribute("data-add"));
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
  }).then(function (data) {
    data.papers.forEach(function (p) { papers[p.id] = p; });
    index = PTRank.buildIndex(PTRank.prepare(data));
    update();   // the first render matches the prerendered HTML and only adds the "Matched" line
    statusEl.textContent = "";
    pending.splice(0).forEach(addTag);
  }).catch(function () {
    statusEl.textContent = ui.load_failed;
    statusEl.classList.add("warn");
  });
})();
