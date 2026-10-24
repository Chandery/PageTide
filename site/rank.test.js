// node --test site/
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const R = require("./assets/rank.js");
const P = require("./assets/platform.js");
const papers = require("./assets/papers.json");

const index = R.buildIndex(papers);
const tags = (list) => list.map(([text, w]) => ({ text, weight: R.WEIGHTS[w] }));
const top = (list, n = 5) => R.rank(index, tags(list)).ranked.slice(0, n).map((r) => r.id);

test("stemming folds plurals and endings", () => {
  assert.strictEqual(R.stem("transformers"), R.stem("transformer"));
  assert.strictEqual(R.stem("alignment"), R.stem("aligned"));
  assert.strictEqual(R.stem("attention"), "attention");
});

test("tokens drop stop words and punctuation", () => {
  assert.deepStrictEqual(R.tokens("The Attention-Is of it"), ["attention"]);
});

test("a strong keyword outranks the same keyword weak", () => {
  const strong = R.rank(index, tags([["vision", "strong"], ["alignment", "weak"]])).ranked[0];
  assert.ok(strong.matched.includes("vision"));
  const flipped = top([["vision", "weak"], ["alignment", "strong"]], 2);
  assert.ok(["2212.08073", "2305.18290"].includes(flipped[0]), "alignment papers lead when alignment is strong: " + flipped);
});

test("off keywords do not score", () => {
  const r = R.rank(index, tags([["transformer", "off"], ["attention", "off"]]));
  assert.ok(r.ranked.every((x) => x.score === 0));
  assert.deepStrictEqual(r.ranked.map((x) => x.id), papers.map((p) => p.id), "empty profile keeps the library order");
});

test("a keyword no paper mentions is reported, not silently ignored", () => {
  const r = R.rank(index, tags([["zzzz", "strong"], ["attention", "strong"]]));
  assert.deepStrictEqual(r.unmatched, ["zzzz"]);
});

test("a multi-word tag gets a phrase bonus", () => {
  const phrase = R.rank(index, tags([["language model", "strong"]])).ranked[0];
  assert.ok(phrase.score > 0);
});

test("ranking is deterministic", () => {
  const a = top([["transformer", "strong"], ["vision", "weak"]], 10);
  const b = top([["transformer", "strong"], ["vision", "weak"]], 10);
  assert.deepStrictEqual(a, b);
});

test("platform detection", () => {
  const mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15";
  const win = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36";
  const iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148";
  const android = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36";
  const linux = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36";
  assert.strictEqual(P.classify({ ua: mac, platform: "MacIntel", maxTouchPoints: 0 }), "mac");
  assert.strictEqual(P.classify({ ua: win, platform: "Win32", maxTouchPoints: 0 }), "win");
  assert.strictEqual(P.classify({ ua: iphone, platform: "iPhone", maxTouchPoints: 5 }), "mobile");
  assert.strictEqual(P.classify({ ua: android, platform: "Linux armv8l", maxTouchPoints: 5 }), "mobile");
  assert.strictEqual(P.classify({ ua: mac, platform: "MacIntel", maxTouchPoints: 5 }), "mobile", "iPadOS posing as a Mac");
  assert.strictEqual(P.classify({ ua: linux, platform: "Linux x86_64", maxTouchPoints: 0 }), "other");
  assert.strictEqual(P.classify({ ua: win, platform: "Win32", maxTouchPoints: 10 }), "win", "Windows touch laptops stay Windows");
  assert.strictEqual(P.classify({ ua: "", uaPlatform: "macOS", uaMobile: false }), "mac");
  assert.strictEqual(P.classify({ ua: "", uaPlatform: "Android", uaMobile: true }), "mobile");
});

test("architecture hints", () => {
  assert.strictEqual(P.archKind("arm"), "arm");
  assert.strictEqual(P.archKind("x86"), "x86");
  assert.strictEqual(P.archKind(""), "unknown");
  assert.strictEqual(P.archKind(undefined), "unknown");
});
