/* Download button by operating system, language hint banner, and a language switch that keeps the #anchor. */
(function () {
  "use strict";
  var P = window.PTPlatform;
  var tx = JSON.parse(document.getElementById("site-i18n").textContent);
  var KEY = "pt-zh-banner-dismissed";

  function $(id) { return document.getElementById(id); }
  function show(el, on) { if (el) el.hidden = !on; }

  var nav = navigator, uad = nav.userAgentData;
  var os = P.classify({
    ua: nav.userAgent, platform: nav.platform, maxTouchPoints: nav.maxTouchPoints,
    uaMobile: uad ? uad.mobile : undefined, uaPlatform: uad ? uad.platform : ""
  });

  var cta = $("cta"), mac = $("dl-mac"), win = $("dl-win"), copy = $("dl-copy"), note = $("cta-note"), alt = $("cta-alt");
  var rows = document.querySelectorAll("[data-os-row]");

  function setNote(text, warn) { note.textContent = text; note.classList.toggle("warn", !!warn); }
  function altLink(other) {
    alt.textContent = "";
    var a = document.createElement("a");
    a.href = "#download";
    a.textContent = tx.other_os.replace("{other}", tx[other]);
    alt.appendChild(a);
    show(alt, true);
  }

  cta.setAttribute("data-os", os);
  rows.forEach(function (r) { r.classList.toggle("mine", r.getAttribute("data-os-row") === os); });

  if (os === "win") {
    win.textContent = tx.dl_win; show(mac, false);
    setNote(tx.note_win); altLink("mac");
  } else if (os === "mac") {
    mac.textContent = tx.dl_mac; show(win, false);
    setNote(tx.note_mac_unknown); altLink("win");
    if (uad && uad.getHighEntropyValues) {
      uad.getHighEntropyValues(["architecture"]).then(function (v) {
        var k = P.archKind(v.architecture);
        if (k === "arm") setNote(tx.note_mac_arm);
        else if (k === "x86") setNote(tx.note_mac_intel, true);
      }, function () { /* keep the generic Apple Silicon note */ });
    }
  } else if (os === "mobile") {
    show(mac, false); show(win, false); show(copy, true);
    setNote(tx.note_mobile);
    copy.addEventListener("click", function () {
      var url = location.href.split("#")[0];
      if (nav.share) {
        nav.share({ title: tx.share_title, url: url }).catch(function () {});
      } else if (nav.clipboard && nav.clipboard.writeText) {
        nav.clipboard.writeText(url).then(function () { setNote(tx.copied); }, function () { setNote(tx.copy_failed + url); });
      } else {
        setNote(tx.copy_failed + url);
      }
    });
  }

  /* The language switch keeps whatever #anchor the reader is on. */
  function carryHash(e) {
    var a = e.currentTarget, base = a.getAttribute("href").split("#")[0];
    a.setAttribute("href", base + location.hash);
  }
  document.querySelectorAll("[data-lang-switch]").forEach(function (a) {
    a.addEventListener("click", carryHash);
    a.addEventListener("focus", carryHash);
    a.addEventListener("mouseover", carryHash);
  });

  /* A Chinese browser on the English page gets one small, dismissible hint. Nothing redirects. */
  var banner = $("zh-banner");
  if (banner) {
    var langs = nav.languages && nav.languages.length ? nav.languages : [nav.language || ""];
    var zh = /^zh\b/i.test(langs[0] || "");
    var dismissed = false;
    try { dismissed = localStorage.getItem(KEY) === "1"; } catch (e) {}
    if (zh && !dismissed) {
      show(banner, true);
      $("zh-banner-close").addEventListener("click", function () {
        show(banner, false);
        try { localStorage.setItem(KEY, "1"); } catch (e) {}
      });
    }
  }
})();
