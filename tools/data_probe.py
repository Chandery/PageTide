#!/usr/bin/env python3
"""DATA-01 read-only probe: resolve owner seeds and measure field coverage.

Zero model tokens, read-only. It sends public paper *titles/terms* to public
metadata APIs (never private seed IDs to a recommender service), saves raw
response snapshots for local replay, and reports coverage statistics.

Sources:
  openalex  primary for this probe: DOI/arXiv IDs, abstracts, citation counts.
  arxiv     metadata API fallback; frequently HTTP 429 for shared/limited IPs.

Usage:
    python3 tools/data_probe.py --source openalex --out-dir .local/data01
    python3 tools/data_probe.py --source arxiv --out-dir .local/data01
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ARXIV = "https://export.arxiv.org/api/query"
OPENALEX = "https://api.openalex.org/works"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
UA = "PaperDigHelper-DATA01-probe/0.1 (local read-only research)"
ARXIV_GAP_SECONDS = 3.1
OPENALEX_GAP_SECONDS = 2.0
MAILTO = "owner@example.invalid"  # OpenAlex polite pool; replace with the owner's contact before heavier use


def normalize_title(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def abstract_text(inverted):
    """Rebuild plain abstract text from OpenAlex's inverted index."""
    if not inverted:
        return ""
    positions = []
    for word, indexes in inverted.items():
        for index in indexes:
            positions.append((index, word))
    positions.sort()
    return " ".join(word for _, word in positions)


# ---------------------------------------------------------------- arXiv source
def _text(entry, path):
    return re.sub(r"\s+", " ", entry.findtext(path, "", NS)).strip()


def parse_arxiv_entries(xml_text):
    root = ET.fromstring(xml_text)
    entries = []
    for entry in root.findall("a:entry", NS):
        primary = entry.find("arxiv:primary_category", NS)
        entries.append({
            "arxiv_id": _text(entry, "a:id").rsplit("/", 1)[-1],
            "title": _text(entry, "a:title"),
            "published": _text(entry, "a:published"),
            "updated": _text(entry, "a:updated"),
            "summary": _text(entry, "a:summary"),
            "primary_category": primary.get("term") if primary is not None else None,
            "authors": [_text(a, "a:name") for a in entry.findall("a:author", NS)],
        })
    return entries


def fetch(url, snapshot_path=None, retries=3, gap=ARXIV_GAP_SECONDS):
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=45) as response:
                body = response.read().decode("utf-8", "replace")
                headers = dict(response.headers)
            if snapshot_path is not None:
                path = Path(snapshot_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body)
            return body, headers
        except urllib.error.HTTPError as exc:
            last_error = exc
            retry_after = (exc.headers.get("Retry-After") if exc.headers else None)
            try:
                delay = float(retry_after) if retry_after is not None else gap * (attempt + 1)
            except (TypeError, ValueError):
                delay = gap * (attempt + 1)
            time.sleep(min(max(delay, gap), 60))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            time.sleep(gap * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} attempts: {url}: {last_error}")


def _snapshot(snapshot_dir, tag, key):
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    return Path(snapshot_dir) / f"{tag}-{digest}.json" if snapshot_dir else None


def query_openalex(params, snapshot_dir, tag, retries=3, refresh=False):
    query = dict(params, mailto=MAILTO)
    url = f"{OPENALEX}?{urllib.parse.urlencode(query)}"
    snapshot = _snapshot(snapshot_dir, tag, url)
    if snapshot is not None and snapshot.exists() and not refresh:
        return json.loads(snapshot.read_text()), {}
    body, headers = fetch(url, snapshot, retries=retries, gap=OPENALEX_GAP_SECONDS)
    time.sleep(OPENALEX_GAP_SECONDS)
    return json.loads(body), headers


def query_arxiv(search_query, max_results, snapshot_dir, tag):
    params = {"search_query": search_query, "start": 0, "max_results": max_results,
              "sortBy": "relevance", "sortOrder": "descending"}
    url = f"{ARXIV}?{urllib.parse.urlencode(params)}"
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    body, _ = fetch(url, Path(snapshot_dir) / f"{tag}-{digest}.xml" if snapshot_dir else None)
    time.sleep(ARXIV_GAP_SECONDS)
    return parse_arxiv_entries(body)


def best_match(seed_title, candidates, key):
    target = normalize_title(seed_title)
    best, score = None, 0.0
    for entry in candidates:
        candidate = normalize_title(entry.get(key) or "")
        if candidate == target:
            value = 1.0
        elif candidate.startswith(target) or target.startswith(candidate):
            value = 0.9
        else:
            seed_words, cand_words = set(target.split()), set(candidate.split())
            value = round(len(seed_words & cand_words) / max(len(seed_words), 1), 3)
        if value > score:
            best, score = entry, value
    return (best, score) if best is not None else (None, 0.0)


def openalex_ids(work):
    ids = work.get("ids") or {}
    doi = work.get("doi") or ""
    return {
        "openalex_id": work.get("id"),
        "doi": doi,
        "arxiv_id": ids.get("arxiv") or (doi.rsplit("arxiv.", 1)[-1] if "arxiv." in doi else None),
    }


def resolve_seeds_openalex(seeds, snapshot_dir, min_score=0.6, refresh=False):
    results = []
    for seed in seeds:
        payload, _ = query_openalex({"search": seed["title"], "per-page": 5}, snapshot_dir, "seed", refresh=refresh)
        entries = payload.get("results", [])
        entry, score = best_match(seed["title"], entries, "title")
        abstract = abstract_text((entry or {}).get("abstract_inverted_index"))
        location = ((entry or {}).get("primary_location") or {})
        source = (location.get("source") or {}).get("display_name")
        results.append({
            "seed_title": seed["title"],
            "venue_hint": seed.get("venue_hint"),
            "rating": seed.get("rating"),
            "status": "resolved" if score >= min_score else ("ambiguous" if entry else "not_found"),
            "match_score": score,
            **(openalex_ids(entry) if entry else {"openalex_id": None, "doi": None, "arxiv_id": None}),
            "matched_title": (entry or {}).get("title"),
            "publication_date": (entry or {}).get("publication_date"),
            "source": source,
            "abstract_chars": len(abstract),
            "cited_by_count": (entry or {}).get("cited_by_count"),
            "referenced_works": len((entry or {}).get("referenced_works") or []),
            "candidates_returned": len(entries),
        })
    return results


def resolve_seeds_arxiv(seeds, snapshot_dir, min_score=0.6):
    results = []
    for seed in seeds:
        entries = query_arxiv(f'ti:"{seed["title"]}"', 5, snapshot_dir, "seed")
        entry, score = best_match(seed["title"], entries, "title")
        results.append({
            "seed_title": seed["title"], "venue_hint": seed.get("venue_hint"), "rating": seed.get("rating"),
            "status": "resolved" if score >= min_score else ("ambiguous" if entry else "not_found"),
            "match_score": score,
            "arxiv_id": (entry or {}).get("arxiv_id"), "doi": None, "openalex_id": None,
            "matched_title": (entry or {}).get("title"),
            "publication_date": (entry or {}).get("published"),
            "source": "arXiv",
            "abstract_chars": len((entry or {}).get("summary") or ""),
            "cited_by_count": None,
            "referenced_works": 0,
            "candidates_returned": len(entries),
        })
    return results


def openalex_pool(snapshot_dir, search="world model", from_date="2024-01-01", to_date="2026-09-11", per_page=200):
    filters = [f"from_publication_date:{from_date}"]
    if to_date:
        filters.append(f"to_publication_date:{to_date}")
    payload, headers = query_openalex(
        {"search": search, "filter": ",".join(filters),
         "sort": "publication_date:desc", "per-page": per_page},
        snapshot_dir, "pool")
    entries = payload.get("results", [])
    sources, by_doi, by_title = {}, {}, {}
    abstract_missing = references_missing = 0
    for work in entries:
        title = work.get("title") or ""
        doi = (work.get("doi") or "").lower()
        by_title.setdefault(normalize_title(title), []).append(work.get("id"))
        if doi:
            by_doi.setdefault(doi, []).append(work.get("id"))
        if not abstract_text(work.get("abstract_inverted_index")):
            abstract_missing += 1
        if not (work.get("referenced_works") or []):
            references_missing += 1
        source = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or "(none)"
        sources[source] = sources.get(source, 0) + 1
    dates = sorted((w.get("publication_date") or "") for w in entries if w.get("publication_date"))
    return {
        "query": search, "from_date": from_date, "to_date": to_date,
        "reported_count": payload.get("meta", {}).get("count"),
        "returned": len(entries),
        "abstract_missing": abstract_missing,
        "references_missing": references_missing,
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "top_sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])[:12]),
        "duplicate_doi_groups": sum(1 for v in by_doi.values() if len(v) > 1),
        "duplicate_title_groups": sum(1 for v in by_title.values() if len(v) > 1),
        "rate_limit": {k: v for k, v in headers.items() if k.lower().startswith("x-ratelimit")},
        "entries": entries,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("openalex", "arxiv"), default="openalex")
    parser.add_argument("--seeds", default="harness/seeds.json")
    parser.add_argument("--out-dir", default=".local/data01")
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--from-date", default="2023-01-01")
    parser.add_argument("--to-date", default="2026-09-11")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore cached snapshots and re-query the network")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    snapshots = out_dir / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)

    seeds = json.loads(Path(args.seeds).read_text())["seeds"]
    if args.source == "openalex":
        resolved = resolve_seeds_openalex(seeds, snapshots, refresh=args.refresh)
        pool = openalex_pool(snapshots, from_date=args.from_date, to_date=args.to_date, per_page=args.max_candidates)
    else:
        resolved = resolve_seeds_arxiv(seeds, snapshots)
        pool = {"query": 'ti:"world model"', "returned": 0, "note": "candidate pool not implemented for arxiv source",
                "entries": []}

    report = {
        "task": "DATA-01",
        "source": args.source,
        "policy": "read-only public metadata; zero model tokens; no private seed IDs sent to any recommender",
        "seeds": resolved,
        "candidate_pool": {k: v for k, v in pool.items() if k != "entries"},
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (out_dir / "candidate_pool.json").write_text(
        json.dumps(pool.get("entries", []), ensure_ascii=False, indent=2) + "\n")

    ok = sum(1 for r in resolved if r["status"] == "resolved")
    print(f"source={args.source}  seeds resolved: {ok}/{len(resolved)}")
    for r in resolved:
        print(f"  [{r['status']:9}] score={r['match_score']:.2f} "
              f"{(r.get('doi') or r.get('arxiv_id') or '-'):<34} {r['seed_title'][:60]}")
    print(f"candidate pool: returned={pool['returned']} dates={pool.get('date_min')}..{pool.get('date_max')} "
          f"abstract_missing={pool.get('abstract_missing')} refs_missing={pool.get('references_missing')}")
    print(f"duplicates: doi={pool.get('duplicate_doi_groups')} title={pool.get('duplicate_title_groups')}")
    print(f"top sources: {pool.get('top_sources')}")
    print(f"rate_limit: {pool.get('rate_limit')}")
    print(f"raw snapshots: {snapshots}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
