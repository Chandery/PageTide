// node --test site/rank.test.js
const test = require("node:test");
const assert = require("node:assert");
const R = require("./assets/rank.js");
const P = require("./assets/platform.js");
const data = require("./assets/papers.json");

const index = R.buildIndex(R.prepare(data));
const tags = (list) => list.map(([text, w]) => ({ text, weight: R.WEIGHTS[w || "strong"] }));
const rank = (list) => R.rank(index, tags(list));
const top = (list, n = 5) => rank(list).ranked.slice(0, n).map((r) => r.id);
const topic = (id) => data.papers.find((p) => p.id === id).topic;

test("stemming folds plurals and endings", () => {
  assert.strictEqual(R.stem("transformers"), R.stem("transformer"));
  assert.strictEqual(R.stem("alignment"), R.stem("aligned"));
  assert.strictEqual(R.stem("attention"), "attention");
});

test("tokens drop stop words and punctuation, and leave Chinese to the Han matcher", () => {
  assert.deepStrictEqual(R.tokens("The Attention-Is of it"), ["attention"]);
  assert.deepStrictEqual(R.tokens("强化学习 robot"), ["robot"]);
  assert.deepStrictEqual(R.hanRuns("强化学习 robot 机器人"), ["强化学习", "机器人"]);
});

test("the library covers many fields", () => {
  assert.ok(data.papers.length >= 150 && data.papers.length <= 250);
  assert.ok(Object.keys(data.topics).length >= 12);
});

test("a keyword the default profile never mentioned changes the ranking and finds its own field", () => {
  const base = [["transformer"], ["attention"]];
  const before = top(base);
  const after = top([...base, ["robot"]]);
  assert.notDeepStrictEqual(after, before);
  assert.ok(after.some((id) => topic(id) === "rob"), "a robotics paper enters the top five: " + after);
  for (const [word, field, n] of [["climate", "earth", 3], ["quantum", "qc", 2], ["galaxy", "astro", 2]]) {
    const ids = top([[word]], n);
    assert.ok(ids.every((id) => topic(id) === field), word + " -> " + ids);
  }
  assert.ok(top([["protein"]], 3).every((id) => ["bio", "chem"].includes(topic(id))));
});

test("prefix and stem matching: robot finds robotics, optimization finds optimizer", () => {
  assert.ok(top([["robot"]], 8).every((id) => rank([["robot"]]).ranked.find((r) => r.id === id).score > 0));
  const hit = rank([["robot"]]).ranked.find((r) => r.id === "2212.06817");   // RT-1: "Robotics Transformer"
  assert.ok(hit.score > 0);
  const opt = rank([["optimizers"]]);
  assert.ok(opt.unmatched.length === 0 && opt.ranked[0].score > 0);
});

test("multi-word keywords score by their words, and a phrase scores more", () => {
  const r = rank([["reinforcement learning"]]);
  assert.ok(r.unmatched.length === 0);
  assert.ok(r.ranked.slice(0, 5).every((x) => topic(x.id) === "rl" || x.score > 0));
  const partial = rank([["learning zebra"]]);   // only one of the two words exists
  assert.ok(partial.ranked[0].score > 0 && partial.unmatched.length === 0);
});

test("Chinese keywords match the hand-written Chinese keywords", () => {
  for (const [word, field] of [["强化学习", "rl"], ["机器人", "rob"], ["蛋白质", "bio"], ["气候", "earth"], ["图神经网络", "gnn"], ["扩散模型", "gen"]]) {
    const ids = top([[word]], 3);
    assert.ok(ids.every((id) => topic(id) === field || ["蛋白质", "机器人", "图神经网络", "扩散模型"].includes(word)), word + " -> " + ids);
    assert.deepStrictEqual(rank([[word]]).unmatched, [], word);
  }
  assert.ok(top([["强化学习"]], 1).every((id) => topic(id) === "rl"));
  assert.ok(!top([["强化学习"]], 5).some((id) => topic(id) === "chem"), "强化学习 must not match 化学");
});

test("a keyword that is added always shows up in the top five, even next to strong older keywords", () => {
  const base = [["transformer"], ["language model"], ["vision", "weak"], ["efficient attention", "weak"], ["alignment", "weak"]];
  const pick = (list) => { const t = tags(list); return R.pickTop(R.rank(index, t), t, 5).map((r) => r.id); };
  const before = pick(base);
  assert.strictEqual(before.length, 5);
  for (const [word, field] of [["robot", "rob"], ["protein", "bio"], ["climate", "earth"], ["quantum", "qc"], ["强化学习", "rl"], ["机器人", "rob"]]) {
    const after = pick([...base, [word]]);
    assert.notDeepStrictEqual(after, before, word);
    assert.ok(after.some((id) => topic(id) === field), word + " -> " + after.map(topic));
  }
  const many = pick([...base, ["robot"], ["protein"], ["climate"]]);
  assert.ok(["rob", "bio", "earth"].every((f) => many.some((id) => topic(id) === f)), many.map(topic).join());
  assert.deepStrictEqual(pick(base), before, "deterministic");
});

test("a keyword with no match changes nothing and is reported", () => {
  const t = tags([["transformer"], ["zzzz"]]);
  const res = R.rank(index, t);
  assert.deepStrictEqual(res.unmatched, ["zzzz"]);
  assert.deepStrictEqual(R.pickTop(res, t, 5).map((r) => r.id), R.pickTop(R.rank(index, tags([["transformer"]])), tags([["transformer"]]), 5).map((r) => r.id));
});

test("off keywords do not score; an empty profile keeps the library order", () => {
  const r = rank([["transformer", "off"], ["attention", "off"]]);
  assert.ok(r.ranked.every((x) => x.score === 0));
  assert.deepStrictEqual(r.ranked.map((x) => x.id), data.papers.map((p) => p.id));
});

test("a keyword no paper mentions is reported as unmatched, not silently ignored", () => {
  assert.deepStrictEqual(rank([["zzzz"], ["attention"]]).unmatched, ["zzzz"]);
  assert.deepStrictEqual(rank([["龘龘"]]).unmatched, ["龘龘"]);
  assert.deepStrictEqual(rank([["zzzz", "off"]]).unmatched, []);
});

test("a strong keyword outranks the same keyword weak", () => {
  const a = rank([["vision", "strong"], ["alignment", "weak"]]).ranked[0];
  const b = rank([["vision", "weak"], ["alignment", "strong"]]).ranked[0];
  assert.notStrictEqual(a.id, b.id);
});

test("ranking is deterministic", () => {
  assert.deepStrictEqual(top([["transformer"], ["vision", "weak"]], 10), top([["transformer"], ["vision", "weak"]], 10));
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

test("count-up text only grows and ends on the real value", () => {
  const F = require("./assets/fx.js");
  for (const text of ["22 MB", "3", "5", "2 × 2", "Zero"]) {
    let prev = F.countText(text, 0);
    for (let i = 1; i <= 20; i++) {
      const cur = F.countText(text, F.ease(i / 20));
      const nums = (s) => (s.match(/\d+/g) || []).map(Number);
      nums(cur).forEach((n, k) => assert.ok(n >= nums(prev)[k], `${text}: ${prev} -> ${cur}`));
      prev = cur;
    }
    assert.strictEqual(prev, text);
  }
  assert.strictEqual(F.countText("22 MB", 0), "0 MB");
  assert.strictEqual(F.countText("Zero", 0.3), "Zero");
});
