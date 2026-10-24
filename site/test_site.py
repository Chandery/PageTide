"""Checks for the static site (standard library only). Run from the repository root:

    python3 site/test_site.py -v                 # (not "-m unittest site...": that name clashes with the stdlib "site")
    node --test site/rank.test.js                # rank.js and platform.js logic (needs Node)
"""
import json
import re
import shutil
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

PAGES = {"en": HERE / "index.html", "zh": HERE / "zh" / "index.html"}
URL_ATTRS = ("href", "src", "poster", "srcset", "content")


class Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.links, self.ids, self.imgs, self.html_lang = [], [], [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.html_lang = a.get("lang")
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "img":
            self.imgs.append(a)
        if tag == "link":
            self.links.append(a)
        for k in ("href", "src", "poster"):
            if a.get(k):
                self.refs.append((tag, k, a[k]))
        if a.get("srcset"):
            for part in a["srcset"].split(","):
                self.refs.append((tag, "srcset", part.strip().split()[0]))
        if tag == "meta" and a.get("property") in ("og:image", "og:url") or (tag == "meta" and a.get("name") == "twitter:image"):
            self.refs.append((tag, "content", a["content"]))


def parse(path):
    p = Collect()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def local_path(ref):
    """Map a site-absolute reference to a file under site/, or None when it is external or not a file."""
    if ref.startswith(build.SITE):
        ref = ref[len(build.SITE):] or "/"
    if not ref.startswith("/") or ref.startswith("//"):
        return None
    ref = ref.split("#")[0].split("?")[0]
    if ref.endswith("/"):
        ref += "index.html"
    return HERE / ref.lstrip("/")


def ignored(path):
    if not shutil.which("git"):
        return False
    r = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=REPO)
    return r.returncode == 0


def luminance(hexcolor):
    h = hexcolor.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class SiteTests(unittest.TestCase):
    def test_pages_exist_and_are_current(self):
        before = {k: p.read_bytes() for k, p in PAGES.items()}
        date = re.search(r"<lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", (HERE / "sitemap.xml").read_text()).group(1)
        extra = {n: (HERE / n).read_bytes() for n in ("sitemap.xml", "assets/papers.json")}
        try:
            build.build(date)
            for k, p in PAGES.items():
                self.assertEqual(before[k], p.read_bytes(), "%s is stale: run python3 site/build.py --date %s" % (p, date))
            for n, b in extra.items():
                self.assertEqual(b, (HERE / n).read_bytes(), n + " is stale")
        finally:
            for k, p in PAGES.items():
                p.write_bytes(before[k])
            for n, b in extra.items():
                (HERE / n).write_bytes(b)

    def test_hreflang_and_canonical(self):
        for lang, path in PAGES.items():
            links = parse(path).links
            alts = {l["hreflang"]: l["href"] for l in links if l.get("rel") == "alternate" and l.get("hreflang")}
            self.assertEqual(alts, {"en": build.SITE + "/", "zh-Hans": build.SITE + "/zh/", "x-default": build.SITE + "/"})
            canon = [l["href"] for l in links if l.get("rel") == "canonical"]
            self.assertEqual(canon, [build.SITE + ("/" if lang == "en" else "/zh/")])
            self.assertEqual(parse(path).html_lang, "en" if lang == "en" else "zh-Hans")
        text = {k: p.read_text(encoding="utf-8") for k, p in PAGES.items()}
        self.assertIn('href="/zh/"', text["en"])
        self.assertIn('href="/"', text["zh"])

    def test_local_references_exist(self):
        for lang, path in PAGES.items():
            for tag, attr, ref in parse(path).refs:
                target = local_path(ref)
                if target is None:
                    continue
                self.assertTrue(target.exists(), "%s: %s=%s -> %s is missing" % (lang, tag, ref, target))

    def test_css_and_manifest_and_sitemap_references(self):
        css = (HERE / "assets" / "site.css").read_text(encoding="utf-8")
        for ref in re.findall(r'url\("?([^")]+)"?\)', css):
            self.assertTrue(local_path(ref).exists(), ref)
        manifest = json.loads((HERE / "site.webmanifest").read_text(encoding="utf-8"))
        for icon in manifest["icons"]:
            self.assertTrue(local_path(icon["src"]).exists(), icon["src"])
        sm = (HERE / "sitemap.xml").read_text(encoding="utf-8")
        for loc in re.findall(r"<loc>([^<]+)</loc>", sm):
            self.assertTrue(local_path(loc).exists(), loc)
        self.assertIn("hreflang=\"zh-Hans\"", sm)
        self.assertIn(build.SITE + "/sitemap.xml", (HERE / "robots.txt").read_text())
        vercel = json.loads((HERE / "vercel.json").read_text())
        self.assertTrue(vercel["cleanUrls"])

    def test_nothing_published_is_gitignored(self):
        paths = set()
        for path in PAGES.values():
            for _, _, ref in parse(path).refs:
                t = local_path(ref)
                if t:
                    paths.add(t)
        for f in ("favicon.ico", "favicon.png", "apple-touch-icon.png", "site.webmanifest", "robots.txt", "sitemap.xml",
                  "vercel.json", "assets/papers.json", "assets/rank.js", "assets/demo.js", "assets/site.js",
                  "assets/platform.js", "assets/site.css", "index.html", "zh/index.html"):
            paths.add(HERE / f)
        for p in sorted(paths):
            self.assertFalse(ignored(p), "%s is git-ignored, so Vercel would not get it" % p)
        for path in PAGES.values():   # repository links must point at tracked, un-ignored files
            for m in re.findall(r'github\.com/Chandery/PageTide/blob/main/([^"#]+)', path.read_text(encoding="utf-8")):
                self.assertTrue((REPO / m).exists() and not ignored(REPO / m), m)

    def test_download_links_match_version(self):
        ver = json.loads((REPO / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"]
        base = "https://github.com/Chandery/PageTide/releases/latest/download/"
        for lang, path in PAGES.items():
            text = path.read_text(encoding="utf-8")
            self.assertIn(base + "PageTide-macos-arm64.zip", text)
            self.assertIn(base + "PageTide_%s_x64-setup.exe" % ver, text)
            self.assertEqual(set(re.findall(r"PageTide_([\d.]+)_x64-setup\.exe", text)), {ver})
            self.assertIn("v" + ver, text)

    def test_i18n_parity_and_page_structure(self):
        en = json.loads((HERE / "i18n/en.json").read_text(encoding="utf-8"))
        zh = json.loads((HERE / "i18n/zh.json").read_text(encoding="utf-8"))

        def keys(d, p=""):
            out = set()
            for k, v in d.items():
                if isinstance(v, dict):
                    out |= keys(v, p + k + ".")
                else:
                    out.add(p + k)
            return out
        self.assertEqual(keys(en), keys(zh))
        self.assertEqual(len(en["features"]["items"]), 6)
        self.assertEqual(len(zh["features"]["items"]), 6)
        for lang, path in PAGES.items():
            p = parse(path)
            for img in p.imgs:
                self.assertIn("alt", img, "img without alt on the %s page: %s" % (lang, img.get("src")))
            self.assertEqual(len(p.ids), len(set(p.ids)), "duplicate ids on " + lang)
            for anchor in ("today", "why", "features", "numbers", "watch", "download", "contribute", "main"):
                self.assertIn(anchor, p.ids)
        # no newspaper wording on either page
        for path in PAGES.values():
            low = path.read_text(encoding="utf-8")
            for word in ("Daily Tide", "每日潮报", "Editorial", "社论", "专栏", "数据版", "影像版", "订阅指南", "读者来信", "From readers", "Vol. 1"):
                self.assertNotIn(word, low)
        # screenshots follow the page language
        self.assertIn("/assets/zh-today.png", PAGES["zh"].read_text(encoding="utf-8"))
        self.assertNotIn("/assets/zh-today.png", PAGES["en"].read_text(encoding="utf-8"))
        # no analytics, no third-party scripts
        for path in PAGES.values():
            for tag, attr, ref in parse(path).refs:
                if tag == "script":
                    self.assertTrue(ref.startswith("/assets/"), ref)

    def test_demo_data(self):
        data = json.loads((HERE / "assets/papers.json").read_text(encoding="utf-8"))
        papers = data["papers"]
        self.assertTrue(150 <= len(papers) <= 250, len(papers))
        self.assertLess((HERE / "assets/papers.json").stat().st_size, 150 * 1024)
        ids = [p["id"] for p in papers]
        self.assertEqual(len(ids), len(set(ids)))
        fx = build.load_fixture()
        self.assertTrue({p["arxiv_id"] for p in fx.PAPERS} <= set(ids))
        meta = json.loads((HERE / "data/arxiv-meta.json").read_text(encoding="utf-8"))["papers"]
        for i in build.INITIAL_IDS:
            self.assertIn(i, ids)
        for p in papers:
            self.assertIn(p["topic"], data["topics"])
            self.assertTrue(p["preview"]["en"] and p["preview"]["zh"] and p["kw"]["en"] and p["kw"]["zh"], p["id"])
            self.assertRegex(p["id"], r"^(\d{4}\.\d{4,5}|[a-z-]+(\.[A-Z]{2})?/\d{7})$")   # only real, checked arXiv ids
            if p["id"] in meta:   # titles and dates come from the checked arXiv snapshot, never from the summaries
                self.assertEqual(p["title"], meta[p["id"]]["title"])
                self.assertEqual(p["date"], meta[p["id"]]["date"])
        self.assertGreaterEqual(len(data["topics"]), 12)

    def test_initial_ranking_matches_rank_js(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = ("const R=require(%s);const P=require(%s);const idx=R.buildIndex(R.prepare(P));"
                  "const tags=%s.map(t=>({text:t[0],weight:R.WEIGHTS[t[1]]}));"
                  "console.log(JSON.stringify(R.pickTop(R.rank(idx,tags),tags,5).map(r=>r.id)))"
                  % (json.dumps(str(HERE / "assets/rank.js")), json.dumps(str(HERE / "assets/papers.json")),
                     json.dumps(build.DEFAULT_TAGS)))
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), build.INITIAL_IDS)

    def test_colour_contrast_is_aa(self):
        css = (HERE / "assets/site.css").read_text(encoding="utf-8")
        light = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", re.search(r":root \{(.*?)\n\}", css, re.S).group(1)))
        self.assertEqual(light["accent"], "#0a6bef", "the site must use the app's accent")
        dark = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})",
                               re.search(r"prefers-color-scheme: dark\) \{\s*:root \{(.*?)\n  \}", css, re.S).group(1)))
        dark = dict(light, **dark)
        pairs = [("text", "base"), ("text", "surface-1"), ("text", "surface-2"), ("muted", "base"), ("muted", "surface-1"),
                 ("muted", "surface-2"), ("accent-text", "base"), ("accent-text", "surface-1"), ("accent-text", "surface-2"),
                 ("accent-ink", "accent"), ("good", "surface-1"), ("good", "base"), ("warn", "surface-1"), ("warn", "base")]
        for name, theme in (("light", light), ("dark", dark)):
            for fg, bg in pairs:
                self.assertGreaterEqual(contrast(theme[fg], theme[bg]), 4.5, "%s: %s on %s" % (name, fg, bg))


if __name__ == "__main__":
    unittest.main()
