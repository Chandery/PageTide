#!/usr/bin/env python3
"""Generate the two static pages from template.html and i18n/{en,zh}.json (Python 3.9+, standard library only).

    python3 site/build.py [--date YYYY-MM-DD]

Writes site/index.html (English, "/"), site/zh/index.html (Chinese, "/zh/"), site/assets/papers.json (the demo
library) and site/sitemap.xml. Version and installer file names come from src-tauri/tauri.conf.json. The generated files
are committed, so Vercel needs no build step (Root Directory = site). Binary assets are made by prep_assets.py.
"""
import argparse
import datetime
import hashlib
import html
import importlib.util
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SITE = "https://pagetide.chandery.org"
GITHUB = "https://github.com/Chandery/PageTide"

# The demo profile the page starts with, and the five papers that profile ranks first. tests check that rank.js agrees.
DEFAULT_TAGS = [("transformer", "strong"), ("attention", "strong"), ("vision", "weak"),
                ("efficient attention", "weak"), ("alignment", "weak"), ("language model", "strong")]
INITIAL_IDS = ["2012.12877", "2006.04768", "2001.04451", "2103.14030", "1706.03762"]


def esc(s):
    return html.escape(str(s), quote=True)


def version():
    return json.loads((REPO / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"]


def load_fixture():
    spec = importlib.util.spec_from_file_location("demo_fixture", REPO / "app" / "demo_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def papers_json():
    """The 29 demo papers as the page's data file. Abstracts are the fixture's own paraphrases; nothing is fetched."""
    fx = load_fixture()
    out = []
    for p in fx.PAPERS:
        prev = fx.PREVIEWS[p["arxiv_id"]]
        out.append({"id": p["arxiv_id"], "title": p["title"], "date": p["published"], "authors": p["authors"],
                    "abstract": p["abstract"], "source": "arXiv",
                    "preview": {"en": prev["en"]["one_liner"], "zh": prev["zh"]["one_liner"]}})
    return out


def icon(name):
    """Inline a Lucide icon (ISC) from the app's own icon set so the site and the app share one look."""
    svg = (REPO / "app" / "static" / "icons" / (name + ".svg")).read_text(encoding="utf-8")
    svg = re.sub(r'\s+(width|height)="24"', "", svg, count=2)
    return svg.replace("<svg", '<svg class="icon" aria-hidden="true" focusable="false"', 1).replace("\n", "").replace("  ", " ")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = prefix + k
        if isinstance(v, dict):
            out.update(flat(v, key + "."))
        elif isinstance(v, str):
            out[key] = v
    return out


def tag_html(text, weight, ui):
    w = ui[weight]
    label = ui["tag_aria"].format(tag=text, weight=w)
    return ('<li class="tag-item" data-w="%s"><button type="button" class="tag" data-tag="%s" aria-label="%s">'
            '<span class="tag-text">%s</span><span class="tag-w">%s</span></button>'
            '<button type="button" class="tag-x" data-remove="%s" aria-label="%s"><span aria-hidden="true">×</span></button></li>'
            % (weight, esc(text), esc(label), esc(text), esc(w), esc(text), esc(ui["remove"].format(tag=text))))


def story_html(p, rank, lang, ui):
    first = p["authors"][0] + " " + ui["et_al"]
    return ('<li class="story%s" data-id="%s"><p class="story-meta"><span class="rank" aria-hidden="true">%d</span>'
            '<span class="st">%s</span> <time datetime="%s">%s</time></p>'
            '<h3><a href="https://arxiv.org/abs/%s" rel="noopener">%s</a></h3>'
            '<p class="by">%s</p><p class="blurb">%s</p><p class="why" hidden></p></li>'
            % (" lead" if rank == 1 else "", esc(p["id"]), rank, esc(p["source"]), esc(p["date"]), esc(p["date"]),
               esc(p["id"]), esc(p["title"]), esc(first), esc(p["preview"][lang])))


def render(tpl, ctx):
    def sub(m):
        key = m.group(1)
        if key not in ctx:
            raise KeyError("template key missing: " + key)
        return ctx[key]
    out = re.sub(r"\{\{([\w.]+)\}\}", sub, tpl)
    left = re.findall(r"\{\{[^}]*\}\}", out)
    if left:
        raise ValueError("unrendered tokens: %s" % left)
    return out


def build(date):
    ver = version()
    papers = papers_json()
    by_id = {p["id"]: p for p in papers}
    (HERE / "assets").mkdir(exist_ok=True)
    (HERE / "assets" / "papers.json").write_text(json.dumps(papers, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    asset_v = hashlib.sha1(b"".join((HERE / "assets" / f).read_bytes()
                                    for f in ("site.css", "site.js", "platform.js", "rank.js", "demo.js"))).hexdigest()[:8]
    mac_file = "PageTide-macos-arm64.zip"
    win_file = "PageTide_%s_x64-setup.exe" % ver
    mac_url = GITHUB + "/releases/latest/download/" + mac_file
    win_url = GITHUB + "/releases/latest/download/" + win_file
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    pages = {"en": SITE + "/", "zh": SITE + "/zh/"}

    for lang in ("en", "zh"):
        t = json.loads((HERE / "i18n" / ("%s.json" % lang)).read_text(encoding="utf-8"))
        ui = t["demo"]["ui"]
        ctx = {k: v.replace("{version}", ver) for k, v in flat(t).items()}
        other = "zh" if lang == "en" else "en"
        ctx.update({
            "html_lang": t["html_lang"], "lang": lang, "path": t["path"], "other_path": t["other_path"],
            "other_hreflang": "zh-Hans" if other == "zh" else "en",
            "canonical": pages[lang], "url_en": pages["en"], "url_zh": pages["zh"], "site": SITE,
            "version": ver, "asset_v": asset_v,
            "mac_file": mac_file, "win_file": win_file, "mac_url": mac_url, "win_url": win_url,
        })
        ctx["tags_html"] = "".join(tag_html(tx, w, ui) for tx, w in DEFAULT_TAGS)
        ctx["stories_html"] = "".join(story_html(by_id[i], n + 1, lang, ui) for n, i in enumerate(INITIAL_IDS))
        ctx["editorial_html"] = "".join("<p>%s</p>" % para for para in t["editorial"]["body"])
        feats = []
        for it in t["features"]["items"]:
            base = "/assets/%s-%s" % (lang, it["img"])
            w, h = png_size(HERE / "assets" / ("%s-%s.png" % (lang, it["img"])))
            feats.append('<article class="feat card"><span class="feat-icon">%s</span><h3>%s</h3><p>%s</p>'
                         '<figure><picture><source type="image/webp" srcset="%s.webp">'
                         '<img src="%s.png" width="%d" height="%d" loading="lazy" decoding="async" alt="%s"></picture></figure></article>'
                         % (icon(it["icon"]), it["title"], it["body"], base, base, w, h, esc(it["alt"])))
        ctx["features_html"] = "".join(feats)
        for kind in ("less", "more"):
            ctx["numbers_%s_html" % kind] = "".join('<li class="num card"><span class="num-v">%s</span><span class="num-t">%s</span></li>'
                                                    % (esc(n["v"]), esc(n["t"])) for n in t["numbers"][kind])
        ctx["keys_html"] = "".join("<li><strong>%s</strong> %s</li>" % (k["name"], k["note"]) for k in t["get"]["keys"])
        banner = ""
        if lang == "en":
            b = t["banner"]
            banner = ('<div class="banner" id="zh-banner" lang="zh-Hans" role="region" aria-label="中文" hidden>'
                      '<p>%s <a href="/zh/" hreflang="zh-Hans" data-lang-switch>%s</a></p>'
                      '<button type="button" id="zh-banner-close" aria-label="%s"><span aria-hidden="true">×</span></button></div>'
                      % (b["text"], b["link"], b["close"]))
        ctx["banner"] = banner
        ctx["demo_json"] = json.dumps({"lang": lang, "ui": ui, "initial_ids": INITIAL_IDS,
                                       "default_tags": [{"text": a, "w": b} for a, b in DEFAULT_TAGS],
                                       "papers_url": "/assets/papers.json?v=" + asset_v}, ensure_ascii=False).replace("</", "<\\/")
        ctx["site_json"] = json.dumps(dict(t["js"], lang=lang, mac_url=mac_url, win_url=win_url), ensure_ascii=False).replace("</", "<\\/")
        ctx["jsonld"] = json.dumps({
            "@context": "https://schema.org", "@type": "SoftwareApplication", "name": "PageTide",
            "description": t["meta"]["description"], "url": pages[lang], "applicationCategory": "ProductivityApplication",
            "operatingSystem": "macOS, Windows", "softwareVersion": ver, "inLanguage": ["en", "zh-Hans"],
            "license": "https://opensource.org/licenses/MIT", "downloadUrl": mac_url,
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            "image": SITE + "/assets/og.png", "author": {"@type": "Person", "name": "Chandery"},
            "sameAs": [GITHUB], "codeRepository": GITHUB,
        }, ensure_ascii=False).replace("</", "<\\/")
        out = render(tpl, ctx)
        dest = HERE / "index.html" if lang == "en" else HERE / "zh" / "index.html"
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(out, encoding="utf-8")

    urls = [("en", "/"), ("zh", "/zh/")]
    items = []
    for _, path in urls:
        links = ('<xhtml:link rel="alternate" hreflang="en" href="%s/"/>'
                 '<xhtml:link rel="alternate" hreflang="zh-Hans" href="%s/zh/"/>'
                 '<xhtml:link rel="alternate" hreflang="x-default" href="%s/"/>' % (SITE, SITE, SITE))
        items.append("  <url><loc>%s%s</loc><lastmod>%s</lastmod>%s</url>" % (SITE, path, date, links))
    (HERE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(items) + "\n</urlset>\n", encoding="utf-8")
    return ver


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()
    print("built", build(a.date), a.date)
