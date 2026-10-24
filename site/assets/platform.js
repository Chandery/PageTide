/* Which download to put first. Pure functions so they can be tested without a browser. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PTPlatform = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /* info: {ua, platform, maxTouchPoints, uaMobile, uaPlatform}. Returns "mobile" | "win" | "mac" | "other".
     Phones and tablets come first (an iPad reports itself as a Mac), then Windows, then macOS. */
  function classify(info) {
    info = info || {};
    var ua = info.ua || "", plat = info.platform || "", touch = info.maxTouchPoints || 0;
    if (info.uaMobile === true) return "mobile";
    if (/Android|iPhone|iPad|iPod|Mobile|Tablet|Silk|Kindle/i.test(ua)) return "mobile";
    if ((/Mac/i.test(plat) || /Macintosh/.test(ua)) && touch > 1) return "mobile";   // iPadOS asks for the desktop site
    if (/CrOS/.test(ua)) return "other";
    var up = info.uaPlatform || "";
    if (/^Windows$/i.test(up) || /Windows NT/.test(ua) || /^Win/i.test(plat)) return "win";
    if (/^macOS$/i.test(up) || /Macintosh|Mac OS X/.test(ua) || /^Mac/i.test(plat)) return "mac";
    return "other";
  }

  /* The value of userAgentData's "architecture" hint: "arm" on Apple Silicon, "x86" on Intel. Anything else (or no hint,
     as in Safari and Firefox) is "unknown": a Mac's user agent string says "Intel" even on Apple Silicon. */
  function archKind(architecture) {
    var a = String(architecture || "").toLowerCase();
    if (a === "arm" || a === "arm64" || a === "aarch64") return "arm";
    if (a === "x86" || a === "x64" || a === "x86_64") return "x86";
    return "unknown";
  }

  return { classify: classify, archKind: archKind };
});
