#!/usr/bin/env python3
"""DATA-01 read-only probe: resolve owner seeds and build a field candidate pool.

Zero model tokens, read-only. Public paper titles/terms go to public metadata
APIs (never private seed IDs to a recommender service); raw responses are cached
for replay and coverage statistics are reported.

Sources:
  openalex  primary: DOI/arXiv IDs, abstracts, citation counts, arXiv source filter.
  arxiv     metadata API fallback; frequently HTTP 429 for shared/limited IPs.

Discovery recipe (DATA-01 finding): free-text `search` is NOT a field filter.
Use `primary_location.source.id:<arXiv> + title.search:<terms> + date bounds`.

Usage:
    python3 tools/data_probe.py --source openalex --out-dir .local/data01
    python3 tools/data_probe.py --source openalex --refresh   # force network
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.sources import oa_of  # noqa: E402  (shared open-access extraction)

ARXIV = "https://export.arxiv.org/api/query"
OPENALEX = "https://api.openalex.org/works"
ARXIV_SOURCE_ID = "S4306400194"  # OpenAlex source: "arXiv (Cornell University)"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
UA = "PaperDigHelper-DATA01-probe/0.1 (local read-only research)"
ARXIV_GAP_SECONDS = 3.1
OPENALEX_GAP_SECONDS = 2.0
MAILTO = "owner@example.invalid"  # OpenAlex polite pool; replace with owner contact before heavier use


def normalize_title(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_overlap(a, b):
    left, right = set(normalize_title(a).split()), set(normalize_title(b).split())
    if not left:
        return 0.0
    if normalize_title(a) == normalize_title(b):
        return 1.0
    if normalize_title(a).startswith(normalize_title(b)) or normalize_title(b).startswith(normalize_title(a)):
        return 0.9
    return round(len(left & right) / max(len(left), 1), 3)


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


class NotFound(RuntimeError):
    """HTTP 404: the identifier is unknown to the source. Retrying cannot change that."""


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
            if exc.code == 404:
                raise NotFound(f"not found: {url}") from exc
            last_error = exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
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


def _cached(snapshot_dir, tag, url, refresh):
    snapshot = _snapshot(snapshot_dir, tag, url)
    if snapshot is not None and snapshot.exists() and not refresh:
        return json.loads(snapshot.read_text()), {}
    body, headers = fetch(url, snapshot, gap=OPENALEX_GAP_SECONDS)
    time.sleep(OPENALEX_GAP_SECONDS)
    return json.loads(body), headers


def query_openalex(params, snapshot_dir, tag, refresh=False):
    url = f"{OPENALEX}?{urllib.parse.urlencode(dict(params, mailto=MAILTO))}"
    return _cached(snapshot_dir, tag, url, refresh)


def fetch_work(identifier, snapshot_dir, refresh=False):
    url = f"{OPENALEX}/{identifier}?mailto={urllib.parse.quote(MAILTO)}"
    payload, _ = _cached(snapshot_dir, "work", url, refresh)
    return payload


def pdf_coverage(works):
    """How many works have a PDF source the app could try: an arXiv ID or an https OA link.

    Zero model tokens; reads fields already in the fetched works. The arXiv-source pool is
    biased toward arXiv, so a high share there says nothing about non-arXiv papers.
    """
    with_arxiv = with_oa = with_any = 0
    for work in works:
        has_arxiv = bool(openalex_ids(work)["arxiv_id"])
        has_oa = bool((oa_of(work) or {}).get("pdf_urls"))
        with_arxiv += has_arxiv
        with_oa += has_oa
        with_any += has_arxiv or has_oa
    return {"checked": len(works), "with_arxiv_id": with_arxiv, "with_oa_pdf_url": with_oa,
            "with_any_pdf_candidate": with_any, "without_candidate": len(works) - with_any}


def openalex_ids(work):
    ids = work.get("ids") or {}
    doi = work.get("doi") or ""
    return {
        "openalex_id": work.get("id"),
        "doi": doi,
        "arxiv_id": ids.get("arxiv") or (doi.rsplit("arxiv.", 1)[-1] if "arxiv." in doi else None),
    }


def seed_identifier(seed):
    ids = seed.get("ids") or {}
    if ids.get("arxiv_id"):
        return f"https://doi.org/10.48550/arxiv.{ids['arxiv_id']}", "arxiv_id"
    if ids.get("openalex_id"):
        return ids["openalex_id"], "openalex_id"
    if ids.get("doi"):
        return f"https://doi.org/{ids['doi']}", "doi"
    return None, None


def seed_result(seed, entry, score, resolution):
    entry = entry or {}
    abstract = abstract_text(entry.get("abstract_inverted_index"))
    location = entry.get("primary_location") or {}
    return {
        "seed_title": seed["title"], "venue_hint": seed.get("venue_hint"), "rating": seed.get("rating"),
        "status": "resolved" if entry and score >= 0.6 else ("ambiguous" if entry else "not_found"),
        "match_score": score, "resolution": resolution,
        "title_matches": bool(entry.get("title")) and normalize_title(entry["title"]) == normalize_title(seed["title"]),
        **openalex_ids(entry),
        "matched_title": entry.get("title"),
        "publication_date": entry.get("publication_date"),
        "source": (location.get("source") or {}).get("display_name"),
        "abstract_chars": len(abstract),
        "cited_by_count": entry.get("cited_by_count"),
        "referenced_works": len(entry.get("referenced_works") or []),
        "related_works": len(entry.get("related_works") or []),
        "pdf_candidate": bool(entry) and bool(pdf_coverage([entry])["with_any_pdf_candidate"]),
    }


def resolve_seeds_openalex(seeds, snapshot_dir, min_score=0.6, refresh=False):
    results = []
    for seed in seeds:
        identifier, resolution = seed_identifier(seed)
        if identifier:
            try:
                entry = fetch_work(identifier, snapshot_dir, refresh=refresh)
            except NotFound:
                # A stale ID (e.g. a merged OpenAlex record) must not abort the other seeds.
                results.append(seed_result(seed, None, 0.0, resolution + "+http_404"))
                continue
            score = title_overlap(seed["title"], entry.get("title")) if entry.get("title") else 0.0
            # An explicit ID is authoritative: keep status resolved even on a title mismatch,
            # but expose the mismatch instead of hiding it.
            if score < min_score:
                resolution += "+title_mismatch"
                score = max(score, min_score)
            results.append(seed_result(seed, entry, score, resolution))
        else:
            payload, _ = query_openalex({"search": seed["title"], "per-page": 5}, snapshot_dir, "seed", refresh=refresh)
            entry, score = best_match(seed["title"], payload.get("results", []), "title")
            results.append(seed_result(seed, entry, score, "title_search"))
    return results


def best_match(seed_title, candidates, key):
    best, score = None, 0.0
    for entry in candidates:
        value = title_overlap(seed_title, entry.get(key))
        if value > score:
            best, score = entry, value
    return (best, score) if best is not None else (None, 0.0)


def resolve_seeds_arxiv(seeds, snapshot_dir, min_score=0.6):
    results = []
    for seed in seeds:
        entries = query_arxiv(f'ti:"{seed["title"]}"', 5, snapshot_dir, "seed")
        entry, score = best_match(seed["title"], entries, "title")
        results.append({
            "seed_title": seed["title"], "venue_hint": seed.get("venue_hint"), "rating": seed.get("rating"),
            "status": "resolved" if score >= min_score else ("ambiguous" if entry else "not_found"),
            "match_score": score, "resolution": "title_search",
            "title_matches": normalize_title((entry or {}).get("title")) == normalize_title(seed["title"]),
            "openalex_id": None, "doi": None, "arxiv_id": (entry or {}).get("arxiv_id"),
            "matched_title": (entry or {}).get("title"), "publication_date": (entry or {}).get("published"),
            "source": "arXiv", "abstract_chars": len((entry or {}).get("summary") or ""),
            "cited_by_count": None, "referenced_works": 0, "related_works": 0,
        })
    return results


def query_arxiv(search_query, max_results, snapshot_dir, tag):
    params = {"search_query": search_query, "start": 0, "max_results": max_results,
              "sortBy": "relevance", "sortOrder": "descending"}
    url = f"{ARXIV}?{urllib.parse.urlencode(params)}"
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    body, _ = fetch(url, Path(snapshot_dir) / f"{tag}-{digest}.xml" if snapshot_dir else None)
    time.sleep(ARXIV_GAP_SECONDS)
    return parse_arxiv_entries(body)


def openalex_pool(snapshot_dir, search="world model", from_date="2024-01-01", to_date="2026-09-11",
                  per_page=200, source_id=ARXIV_SOURCE_ID, refresh=False):
    filters = [f"primary_location.source.id:{source_id}", f"title.search:{search}"]
    if from_date:
        filters.append(f"from_publication_date:{from_date}")
    if to_date:
        filters.append(f"to_publication_date:{to_date}")
    payload, headers = query_openalex(
        {"filter": ",".join(filters), "sort": "publication_date:desc", "per-page": per_page},
        snapshot_dir, "pool", refresh=refresh)
    entries = payload.get("results", [])
    sources, by_doi, by_title = {}, {}, {}
    abstract_missing = references_missing = related_missing = 0
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
        if not (work.get("related_works") or []):
            related_missing += 1
        source = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or "(none)"
        sources[source] = sources.get(source, 0) + 1
    dates = sorted((w.get("publication_date") or "") for w in entries if w.get("publication_date"))
    return {
        "query": search, "source_id": source_id, "from_date": from_date, "to_date": to_date,
        "reported_count": payload.get("meta", {}).get("count"),
        "returned": len(entries),
        "abstract_missing": abstract_missing,
        "references_missing": references_missing,
        "related_works_missing": related_missing,
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "top_sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])[:12]),
        "duplicate_doi_groups": sum(1 for v in by_doi.values() if len(v) > 1),
        "duplicate_title_groups": sum(1 for v in by_title.values() if len(v) > 1),
        "rate_limit": {k: v for k, v in headers.items() if k.lower().startswith("x-ratelimit")},
        "pdf_coverage": pdf_coverage(entries),
        "entries": entries,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("openalex", "arxiv"), default="openalex")
    parser.add_argument("--seeds", default="harness/seeds.json")
    parser.add_argument("--out-dir", default=".local/data01")
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--from-date", default="2024-01-01")
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
        pool = openalex_pool(snapshots, from_date=args.from_date, to_date=args.to_date,
                             per_page=args.max_candidates, refresh=args.refresh)
    else:
        resolved = resolve_seeds_arxiv(seeds, snapshots)
        pool = {"query": 'ti:"world model"', "returned": 0,
                "note": "candidate pool not implemented for arxiv source", "entries": []}

    report = {
        "task": "DATA-01", "source": args.source,
        "policy": "read-only public metadata; zero model tokens; no private seed IDs sent to any recommender",
        "seeds": resolved,
        "candidate_pool": {k: v for k, v in pool.items() if k != "entries"},
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (out_dir / "candidate_pool.json").write_text(
        json.dumps(pool.get("entries", []), ensure_ascii=False, indent=2) + "\n")

    ok = sum(1 for r in resolved if r["status"] == "resolved")
    mismatch = sum(1 for r in resolved if not r["title_matches"])
    print(f"source={args.source}  seeds resolved: {ok}/{len(resolved)}  title_mismatch={mismatch}")
    for r in resolved:
        print(f"  [{r['status']:9}] {r['resolution']:16} {(r.get('arxiv_id') or r.get('openalex_id') or '-'):<20} {r['seed_title'][:55]}")
    print(f"seeds with a PDF candidate (arXiv ID or https OA link): "
          f"{sum(1 for r in resolved if r.get('pdf_candidate'))}/{len(resolved)}")
    print(f"candidate pool: returned={pool['returned']} reported={pool.get('reported_count')} "
          f"dates={pool.get('date_min')}..{pool.get('date_max')}")
    print(f"missing: abstract={pool.get('abstract_missing')} refs={pool.get('references_missing')} "
          f"related={pool.get('related_works_missing')}")
    print(f"duplicates: doi={pool.get('duplicate_doi_groups')} title={pool.get('duplicate_title_groups')}")
    print(f"top sources: {pool.get('top_sources')}")
    print(f"pdf coverage (candidate pool, arXiv-biased): {pool.get('pdf_coverage')}")
    print(f"rate_limit: {pool.get('rate_limit')}")
    print(f"raw snapshots: {snapshots}")
    return 0 if ok == len(resolved) else 1


if __name__ == "__main__":
    sys.exit(main())
