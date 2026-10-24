#!/usr/bin/env python3
"""One real, tiny request to a keyed paper source, to check the shape the code assumes. Run it in a terminal that has the key.

    python3 tools/source_smoke.py baidu_scholar --query 知识图谱            # the saved key (or BAIDU_SCHOLAR_API_KEY)
    python3 tools/source_smoke.py baidu_scholar --query 知识图谱 --wrong-key  # how a refused key answers
    python3 tools/source_smoke.py baidu_web --query 知识图谱                  # Baidu AI Search restricted to xueshu.baidu.com (POST)

`baidu_web` uses the same Qianfan key (BAIDU_SCHOLAR_API_KEY or baidu_scholar.key). It prints only: HTTP status, the top-level
field names, the number of references, their field names, how many the app's parser reads with authors / an abstract / keywords,
how many patents it leaves out, one date sample and the key's format; never paper text.

For `baidu_scholar` it prints only: HTTP status, the response code, the number of items, hasMore, the field names of the items, whether DOIs
and https links are present, the types of publishYear, whether aiAbstract comes back by default, what the app's own parser
makes of it, and the key's format (segment lengths and character classes, never the key). The raw answer is saved under
.local/source-smoke/ (git-ignored; it may contain paper text and an AI summary) and never committed.

It spends one of the provider's calls (Baidu: about 50 free a day; for baidu_web the monthly quota of 1500) and does not touch
the app's database or its daily counter, so the request is not counted locally: it uses Baidu's allowance without the app's count
of 40 a day (shared by both Baidu sources) knowing about it. Every Baidu field name in app/baidu_scholar.py is UNVERIFIED until this has run once with a real key.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import baidu_scholar, baidu_web, source_keys  # noqa: E402
from app.sources import SourceError  # noqa: E402

WRONG_KEY = "wrong-key-for-smoke-test-0000000000"
MAX_BODY = 2 * 1024 * 1024
ENV = baidu_scholar.BAIDU_SCHOLAR_INFO.key_env


def default_data_dir():
    return Path(os.environ.get("PAGETIDE_DATA") or Path.home() / "Library" / "Application Support" / "PageTide")


def find_key(data_dir):
    """(key, where it came from) or None. The environment variable wins, as in the app."""
    env = (os.environ.get(ENV) or "").strip()
    if env:
        return env, "environment"
    key = source_keys.load(data_dir, baidu_scholar.SOURCE_ID)
    return (key, "key file") if key else None


def describe_key(key):
    """The key's format only: segment count and lengths, character classes, punctuation. The first segment is shown only
    when it looks like a short version label (bce-v3); nothing else of the key is ever printed."""
    segments = key.split("/")
    first = segments[0] if len(segments) > 1 and re.fullmatch(r"[a-z]{2,6}-v\d{1,2}", segments[0]) else None
    return {"length": len(key), "segments": len(segments), "lengths": [len(part) for part in segments],
            "has_upper": bool(re.search(r"[A-Z]", key)), "has_lower": bool(re.search(r"[a-z]", key)),
            "has_digit": bool(re.search(r"\d", key)), "punctuation": "".join(sorted(set(re.findall(r"[^A-Za-z0-9]", key)))),
            "first_segment": first}


def _clean(text, key=None, limit=80):
    text = re.sub(r"\s+", " ", str(text if text is not None else ""))
    if key:
        text = text.replace(key, "***")
    return text[:limit]


def summarise(status, payload, key=None):
    """Lines describing the answer's shape. Names and counts only, never paper text."""
    lines = [f"HTTP {status}"]
    if not isinstance(payload, dict):
        return lines + ["body is not a JSON object"]
    lines.append(f"code: {_clean(payload.get('code'), key, 40)!r} ({type(payload.get('code')).__name__}), message: {_clean(payload.get('message'), key)!r}")
    lines.append("top-level fields: " + ", ".join(sorted(map(str, payload))))
    lines.append(f"hasMore: {payload.get('hasMore')}")
    items = payload.get("data")
    if isinstance(items, list):
        objects = [i for i in items if isinstance(i, dict)]
        fields = sorted({str(k) for i in objects for k in i})
        years = sorted({type(i["publishYear"]).__name__ for i in objects if "publishYear" in i})
        lines.append(f"items: {len(items)}")
        lines.append("item fields: " + ", ".join(fields))
        lines.append("with doi: " + str(sum(1 for i in objects if str(i.get("doi") or "").strip())))
        urls = [str(i.get("url") or "") for i in objects]
        lines.append(f"https page link: {sum(u.startswith('https://') for u in urls)}, http: {sum(u.startswith('http://') for u in urls)}, none: {sum(not u for u in urls)}")
        lines.append("publishYear types: " + (", ".join(years) or "none"))
        lines.append("keyword types: " + (", ".join(sorted({type(i['keyword']).__name__ for i in objects if 'keyword' in i})) or "none"))
        lines.append("aiAbstract returned by default: " + ("yes" if any("aiabstract" in str(k).lower().replace("_", "") for i in objects for k in i) else "no"))
    else:
        lines.append(f"data: {type(items).__name__} (not a list)")
    try:
        lines.append(f"parsed by app: {len(baidu_scholar.parse_search(payload))}")
    except SourceError as exc:
        lines.append(f"kind from the app's parser: {exc.kind}")
    return lines


def summarise_web(status, payload, key=None):
    """Lines describing the answer of the web search. Names and counts only, never paper text."""
    lines = [f"HTTP {status}"]
    if not isinstance(payload, dict):
        return lines + ["body is not a JSON object"]
    lines.append(f"code: {_clean(payload.get('code'), key, 40)!r}, message: {_clean(payload.get('message'), key)!r}")
    lines.append("top-level fields: " + ", ".join(sorted(map(str, payload))))
    refs = payload.get("references")
    if isinstance(refs, list):
        objects = [r for r in refs if isinstance(r, dict)]
        lines.append(f"references: {len(refs)}")
        lines.append("reference fields: " + ", ".join(sorted({str(k) for r in objects for k in r})))
        urls = [str(r.get("url") or "") for r in objects]
        lines.append(f"xueshu https page: {sum(baidu_web._page_url(u, upgrade=False) is not None for u in urls)}, other or none: "
                     f"{sum(baidu_web._page_url(u, upgrade=False) is None for u in urls)}")
        parsed = [baidu_web.parse_content(r.get("content"), r.get("title") or "") for r in objects]
        kept = [p for p in parsed if not p["patent"]]
        lines.append(f"with authors: {sum(bool(p['authors']) for p in kept)}, with abstract: {sum(bool(p['abstract']) for p in kept)}, "
                     f"with keywords: {sum(bool(p['keywords']) for p in kept)}, patents left out: {len(parsed) - len(kept)}")
        dates = [r.get("date") for r in objects if isinstance(r.get("date"), str) and r.get("date")]
        lines.append(f"date sample: {_clean(dates[0], key, 30) if dates else 'none'}")
    else:
        lines.append(f"references: {type(refs).__name__} (not a list)")
    try:
        lines.append(f"parsed by app: {len(baidu_web.parse_search(payload))}")
    except SourceError as exc:
        lines.append(f"kind from the app's parser: {exc.kind}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", choices=["baidu_scholar", "baidu_web"])
    parser.add_argument("--query", default=baidu_scholar.VERIFY_WORD, help="public search word (default %(default)s)")
    parser.add_argument("--wrong-key", action="store_true", help="send a fixed dummy key to see how a refused key answers")
    parser.add_argument("--data-dir", help="where baidu_scholar.key lives (default: PAGETIDE_DATA or the macOS app folder)")
    parser.add_argument("--raw-dir", help="where the raw answer is saved (default: .local/source-smoke)")
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    found = (WRONG_KEY, "fixed dummy") if args.wrong_key else find_key(data_dir)
    if not found:
        print(f"no key: set {ENV} or save one in Settings (looked in {data_dir / 'baidu_scholar.key'}, the key both Baidu sources use). Nothing was sent.")
        return 2
    key, where = found
    web = args.source == "baidu_web"
    query = baidu_web.clean_query(args.query) if web else baidu_scholar.clean_query(args.query)
    request = (baidu_web.request_for(baidu_web.request_body(query, 10), key) if web
               else baidu_scholar.request_for(baidu_scholar.BaiduScholar._url(query, 0), key))
    print(f"source: {args.source}   query: {query}   key from: {where}")
    print("key format: " + json.dumps(describe_key(key), ensure_ascii=False))
    status, body = None, b""
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, body = getattr(response, "status", 200), response.read(MAX_BODY)
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = exc.read(MAX_BODY)
        except Exception:
            body = b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"network error: {type(exc).__name__} (nothing came back)")
        return 1
    raw_dir = Path(args.raw_dir) if args.raw_dir else ROOT / ".local" / "source-smoke"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    saved = raw_dir / f"{args.source}-{stamp}-{'wrongkey' if args.wrong_key else 'ok'}.json"
    text = body.decode("utf-8", "replace").replace(key, "***")
    saved.write_text(text, encoding="utf-8")
    try:
        payload = json.loads(text)
    except ValueError:
        payload = None
    for line in (summarise_web if web else summarise)(status, payload, key):
        print(line)
    print(f"raw answer saved: {saved}")
    if web:
        return 0 if status == 200 and isinstance(payload, dict) and isinstance(payload.get("references"), list) else 1
    return 0 if status == 200 and isinstance(payload, dict) and str(payload.get("code")) == "0" else 1


if __name__ == "__main__":
    sys.exit(main())
