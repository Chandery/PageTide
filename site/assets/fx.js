/* Motion for the homepage: scroll reveal, feature showcase, hero tilt and glow.
   Plain JS, no libraries. Everything is skipped under prefers-reduced-motion; nothing here is needed to read the page. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else { root.PTFx = api; if (typeof document !== "undefined") api.init(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function init() {
    var doc = document, html = doc.documentElement;
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) { html.classList.remove("fx"); html.dataset.fxReady = "1"; return; }
    html.dataset.fxReady = "1";
    var fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    var narrow = window.matchMedia("(max-width: 640px)").matches;

    /* Scroll reveal: fade in and rise, siblings one after another. The class is removed afterwards so hover effects work. */
    var targets = doc.querySelectorAll(".section-head, .profile, .stories-wrap, .showcase, .why-card, .num, .video, " +
      ".dl-card, .first-launch, .req-cols .card, .contrib-card");
    var seen = new Map();
    Array.prototype.forEach.call(targets, function (el) {
      var parent = el.parentNode, n = seen.get(parent) || 0;
      seen.set(parent, n + 1);
      el.style.setProperty("--d", Math.min(n, 5) * 70 + "ms");
      el.classList.add("reveal");
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        io.unobserve(el);
        el.classList.add("in");
        setTimeout(function () { el.classList.remove("reveal", "in"); el.style.removeProperty("--d"); }, 1100);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    Array.prototype.forEach.call(doc.querySelectorAll(".reveal"), function (el) {
      io.observe(el);
    });

    /* Feature showcase: pick a feature to change the big screenshot; it also advances by itself while visible and not hovered. */
    var show = doc.getElementById("showcase");
    if (show) {
      var tabs = show.querySelectorAll(".feat"), shots = show.querySelectorAll(".shot, .cap"), cur = 0;
      var select = function (i) {
        cur = (i + tabs.length) % tabs.length;
        Array.prototype.forEach.call(tabs, function (t, k) {
          t.classList.toggle("active", k === cur); t.setAttribute("aria-pressed", k === cur ? "true" : "false");
        });
        Array.prototype.forEach.call(shots, function (s) {
          var k = +s.getAttribute("data-i");
          s.classList.toggle("active", k === cur);
          if (k === cur) s.removeAttribute("aria-hidden"); else s.setAttribute("aria-hidden", "true");
        });
      };
      Array.prototype.forEach.call(tabs, function (t, k) {
        t.addEventListener("click", function () { select(k); show.classList.add("manual"); });
        t.addEventListener("animationend", function (e) { if (e.animationName === "feat-progress" && !show.classList.contains("manual")) select(cur + 1); });
      });
      var vis = new IntersectionObserver(function (es) {
        var on = es[0].isIntersecting;
        show.classList.toggle("playing", on);
        if (on) Array.prototype.forEach.call(show.querySelectorAll("img"), function (im) { im.loading = "eager"; });
      }, { rootMargin: "300px 0px" });
      vis.observe(show);
      show.addEventListener("mouseenter", function () { show.classList.add("hover"); });
      show.addEventListener("mouseleave", function () { show.classList.remove("hover"); });
      show.addEventListener("focusin", function () { show.classList.add("hover"); });
      show.addEventListener("focusout", function () { show.classList.remove("hover"); });
    }

    /* Hero: a faint tilt of the product window and a glow that follows the pointer (fine pointers on wide screens only). */
    var hero = doc.querySelector(".hero"), shot = doc.getElementById("hero-shot");
    if (hero && shot && fine && !narrow) {
      var raf = 0, px = 0, py = 0;
      hero.addEventListener("pointermove", function (e) {
        var r = hero.getBoundingClientRect();
        px = (e.clientX - r.left) / r.width - 0.5; py = (e.clientY - r.top) / r.height - 0.5;
        if (!raf) raf = requestAnimationFrame(function () {
          raf = 0;
          shot.style.setProperty("--ry", (px * 5).toFixed(2) + "deg");
          shot.style.setProperty("--rx", (-py * 3).toFixed(2) + "deg");
          hero.style.setProperty("--gx", (px * 80).toFixed(1) + "px");
          hero.style.setProperty("--gy", (py * 50).toFixed(1) + "px");
        });
      });
      hero.addEventListener("pointerleave", function () {
        shot.style.removeProperty("--ry"); shot.style.removeProperty("--rx");
        hero.style.removeProperty("--gx"); hero.style.removeProperty("--gy");
      });
    }
  }

  return { init: init };
});
