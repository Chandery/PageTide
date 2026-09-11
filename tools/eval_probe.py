#!/usr/bin/env python3
"""Offline ranking experiment: freeze a candidate set, rank it, label it, score it.

Zero model tokens for freeze/rank/score. `label` calls the evaluation annotator
(taomu) only, never the shipped runtime provider, and caches every label.

The profile here is the 10 owner seeds (seed-based cold start). This builds the
measurement harness and the fixed baselines; it is NOT the upstream-reuse probe
(REUSE-01) and it is NOT a product-quality result.

Commands:
    freeze   fetch + dedupe + split a replayable candidate set
    rank     TF-IDF seed-similarity vs recency / keyword+date baselines
    label    ask the annotator to label the union of shown candidates (cached)
    score    P@k per system against the labels
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_probe  # noqa: E402

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "we", "our", "is", "are",
    "that", "this", "as", "by", "from", "it", "its", "be", "can", "which", "these", "their", "at",
    "using", "use", "used", "based", "such", "than", "then", "into", "over", "more", "most", "also",
    "show", "shows", "propose", "proposed", "paper", "method", "results", "approach", "new", "model",
    "models", "learning", "learn", "however", "while", "when", "where", "between", "we", "our",
}


def tokenize(text):
    words = re.findall(r"[a-z0-9][a-z0-9\-]+", (text or "").lower())
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


def build_idf(token_lists):
    total = len(token_lists)
    df = {}
    for tokens in token_lists:
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1
    return {token: math.log((1 + total) / (1 + count)) + 1.0 for token, count in df.items()}


def vectorize(tokens, idf):
    counts = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    vector = {token: (1.0 + math.log(count)) * idf.get(token, 0.0) for token, count in counts.items()}
    return dict(sorted(vector.items(), key=lambda kv: -kv[1]))


def l2_normalize(vector):
    norm = math.sqrt(sum(value * value for value in vector.values()))
    return {k: v / norm for k, v in vector.items()} if norm else vector


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(token, 0.0) for token, value in a.items())


def centroid(vectors):
    total = {}
    for vector in vectors:
        for token, value in vector.items():
            total[token] = total.get(token, 0.0) + value
    count = max(len(vectors), 1)
    return l2_normalize({k: v / count for k, v in total.items()})


def paper_text(work):
    abstract = data_probe.abstract_text(work.get("abstract_inverted_index"))
    return f"{work.get('title') or ''} {abstract}".strip()


def openalex_key(work):
    ids = data_probe.openalex_ids(work)
    return ids["doi"] or ids["openalex_id"] or data_probe.normalize_title(work.get("title"))


def fetch_candidates(pages, per_page, snapshot_dir, refresh=False):
    seen_keys, seen_titles, works = set(), set(), []
    for page in range(1, pages + 1):
        payload, _ = data_probe.query_openalex(
            {"filter": (f"primary_location.source.id:{data_probe.ARXIV_SOURCE_ID},"
                        "title.search:world model,from_publication_date:2024-01-01,to_publication_date:2026-09-11"),
             "sort": "publication_date:desc", "per-page": per_page, "page": page},
            snapshot_dir, f"pool-p{page}", refresh=refresh)
        for work in payload.get("results", []):
            key = openalex_key(work)
            title = data_probe.normalize_title(work.get("title"))
            # OpenAlex can hold duplicate records for the same paper under different IDs;
            # dedupe on both canonical ID and normalized title so P@k is not inflated.
            if key in seen_keys or (title and title in seen_titles):
                continue
            seen_keys.add(key)
            if title:
                seen_titles.add(title)
            works.append(work)
    return works


def slim(work):
    ids = data_probe.openalex_ids(work)
    return {
        "key": openalex_key(work), "openalex_id": ids["openalex_id"], "doi": ids["doi"],
        "arxiv_id": ids["arxiv_id"], "title": work.get("title"),
        "publication_date": work.get("publication_date"),
        "abstract_chars": len(data_probe.abstract_text(work.get("abstract_inverted_index"))),
        "abstract": data_probe.abstract_text(work.get("abstract_inverted_index")),
    }


def dataset_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ commands
def cmd_freeze(args):
    out = Path(args.out_dir)
    snapshots = out / "snapshots"
    seeds = json.loads(Path(args.seeds).read_text())["seeds"]
    works = fetch_candidates(args.pages, args.per_page, snapshots, refresh=args.refresh)
    seed_keys = {str((s.get("ids") or {}).get("arxiv_id")) for s in seeds if (s.get("ids") or {}).get("arxiv_id")}
    candidates = [slim(w) for w in works if str(slim(w).get("arxiv_id")) not in seed_keys]
    profile = [c for c in candidates if (c["publication_date"] or "") < args.holdout_from]
    holdout = [c for c in candidates if (c["publication_date"] or "") >= args.holdout_from]
    payload = {"profile": profile, "holdout": holdout}
    (out / "candidates.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"fetched works={len(works)} deduped={len(candidates)} seeds_excluded={len(seed_keys)}")
    print(f"profile(<{args.holdout_from})={len(profile)} holdout(>={args.holdout_from})={len(holdout)}")
    print(f"holdout dates: {min(c['publication_date'] for c in holdout)} .. {max(c['publication_date'] for c in holdout)}")
    print(f"holdout abstract_missing={sum(1 for c in holdout if not c['abstract'])}")
    print(f"dataset_hash={dataset_hash(payload)}")
    return 0


def cmd_rank(args):
    out = Path(args.out_dir)
    payload = json.loads((out / "candidates.json").read_text())
    seeds = json.loads(Path(args.seeds).read_text())["seeds"]
    holdout = payload["holdout"]
    seed_docs = [f"{s['title']}" for s in seeds]
    corpus = seed_docs + [paper_text_from_slim(c) for c in holdout]
    idf = build_idf([tokenize(doc) for doc in corpus])
    seed_vectors = [l2_normalize(vectorize(tokenize(doc), idf)) for doc in seed_docs]
    profile_vector = centroid(seed_vectors)
    candidate_vectors = [l2_normalize(vectorize(tokenize(paper_text_from_slim(c)), idf)) for c in holdout]
    profile_terms = [t for t, _ in sorted(profile_vector.items(), key=lambda kv: -kv[1])[:40]]

    systems = {
        "recency_baseline": sorted(range(len(holdout)),
                                   key=lambda i: holdout[i]["publication_date"] or "", reverse=True),
        "keyword_date_baseline": sorted(
            range(len(holdout)),
            key=lambda i: (sum(1 for t in profile_terms if t in paper_text_from_slim(holdout[i]).lower()),
                           holdout[i]["publication_date"] or ""),
            reverse=True),
        "tfidf_seed_centroid": sorted(range(len(holdout)), key=lambda i: -cosine(profile_vector, candidate_vectors[i])),
    }
    rankings = {name: [holdout[i]["key"] for i in order] for name, order in systems.items()}
    (out / "rankings.json").write_text(json.dumps(
        {"profile_terms": profile_terms, "systems": rankings}, ensure_ascii=False, indent=2) + "\n")
    for name, order in rankings.items():
        print(f"\n[{name}] top 5:")
        for key in order[:5]:
            work = next(c for c in holdout if c["key"] == key)
            print(f"   {work['publication_date']} {work['title'][:72]}")
    return 0


def paper_text_from_slim(candidate):
    return f"{candidate.get('title') or ''} {candidate.get('abstract') or ''}".strip()


def _load_annotator_env():
    base = os.environ.get("TAOMU_BASE_URL", "https://taomu.xyz").rstrip("/")
    key = os.environ.get("TAOMU_API_KEY")
    if not key:
        env_file = Path(".local/taomu.env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("TAOMU_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                if line.startswith("TAOMU_BASE_URL="):
                    base = line.split("=", 1)[1].strip().rstrip("/")
    if not key:
        raise SystemExit("TAOMU_API_KEY not set and .local/taomu.env missing")
    return base, key


def annotate_batch(papers, profile_terms, seed_titles, base, key, model):
    listing = "\n".join(
        f"{i+1}. id={p['key']} | {p['title']} | {p['publication_date']} | "
        f"{(p['abstract'] or '')[:400]}" for i, p in enumerate(papers))
    prompt = (
        "你是论文相关性评审。给定研究画像与候选论文，判断每篇是否对画像“有用/值得读”。\n"
        f"画像关键词：{', '.join(profile_terms[:20])}\n"
        f"画像种子标题：{'; '.join(seed_titles[:10])}\n\n"
        f"候选论文：\n{listing}\n\n"
        "只输出 JSON 数组，每项 {\"paper_id\": \"...\", \"useful\": true/false, "
        "\"confidence\": 0-1, \"reason\": \"<=15词\"}。不要输出其他文字。"
    )
    body = json.dumps({
        "model": model, "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    request = urllib.request.Request(f"{base}/v1/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json",
                                              "Accept": "application/json",
                                              "User-Agent": "PaperDigHelper-eval/0.1 (local research)"})
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            detail = ""
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    detail = " body=" + exc.read().decode("utf-8", "replace")[:200]
                except Exception:
                    detail = ""
            last_error = f"{exc}{detail}"
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"annotator failed after 4 attempts: {last_error}")
    content = payload["choices"][0]["message"]["content"]
    match = re.search(r"\[.*\]", content, re.S)
    if not match:
        raise RuntimeError(f"annotator did not return JSON: {content[:200]}")
    return json.loads(match.group(0)), payload.get("usage", {})


def cmd_label(args):
    out = Path(args.out_dir)
    candidates = json.loads((out / "candidates.json").read_text())["holdout"]
    rankings = json.loads((out / "rankings.json").read_text())
    seeds = json.loads(Path(args.seeds).read_text())["seeds"]
    profile_terms = rankings["profile_terms"]
    by_key = {c["key"]: c for c in candidates}
    union, seen = [], set()
    for order in rankings["systems"].values():
        for key in order[:args.top_per_system]:
            if key not in seen:
                seen.add(key)
                union.append(by_key[key])
    labels_path = out / "labels.json"
    labels = json.loads(labels_path.read_text()) if labels_path.exists() else {}
    pending = [p for p in union if p["key"] not in labels]
    base, key = _load_annotator_env()
    print(f"union={len(union)} already_labelled={len(union) - len(pending)} pending={len(pending)}")
    for start in range(0, len(pending), args.batch):
        batch = pending[start:start + args.batch]
        result, usage = annotate_batch(batch, profile_terms, [s["title"] for s in seeds], base, key, args.model)
        for item in result:
            labels[item["paper_id"]] = {"useful": bool(item.get("useful")),
                                        "confidence": item.get("confidence"),
                                        "reason": item.get("reason")}
        labels_path.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n")
        print(f"  labelled {start + len(batch)}/{len(pending)} usage={usage}")
        time.sleep(1)
    unlabelled = [p["key"] for p in union if p["key"] not in labels]
    print(f"labels={len(labels)} unlabelled_in_union={unlabelled}")
    return 0


def precision_at_k(order, labels, k):
    """P@k over labelled items, or None if any top-k item is unjudged."""
    top = order[:k]
    if any(key not in labels for key in top):
        return None
    return sum(1 for key in top if labels[key].get("useful")) / k


def cmd_score(args):
    out = Path(args.out_dir)
    rankings = json.loads((out / "rankings.json").read_text())["systems"]
    labels = json.loads((out / "labels.json").read_text())
    useful_total = sum(1 for v in labels.values() if v.get("useful"))
    print(f"labelled={len(labels)} useful={useful_total} not_useful={len(labels) - useful_total} "
          f"(positive_rate={useful_total / max(len(labels), 1):.0%})")
    print(f"{'system':24} {'P@5':>6} {'useful@5':>8} {'P@10':>6} {'judged':>7} {'unjudged_top5':>13}")
    for name, order in rankings.items():
        top5, top10 = order[:5], order[:10]
        judged = [k for k in order if k in labels]
        useful5 = sum(1 for k in top5 if labels.get(k, {}).get("useful"))
        unjudged5 = sum(1 for k in top5 if k not in labels)
        p5 = precision_at_k(order, labels, 5)
        p10 = precision_at_k(order, labels, 10)
        p5_text = f"{p5:.2f}" if p5 is not None else "n/a"
        p10_text = f"{p10:.2f}" if p10 is not None else "n/a"
        print(f"{name:24} {p5_text:>6} {useful5:8d} {p10_text:>6} {len(judged):7d} {unjudged5:13d}")
    print("\nNOTE: exploratory single-slice run; the annotator is a proxy, not the owner's judgement.")
    if useful_total / max(len(labels), 1) > 0.9:
        print("WARNING: annotator labelled almost everything useful -> P@k cannot discriminate systems here.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    common = dict(out_dir=".local/experiments", seeds="harness/seeds.json")

    freeze = sub.add_parser("freeze")
    freeze.add_argument("--out-dir", default=common["out_dir"])
    freeze.add_argument("--seeds", default=common["seeds"])
    freeze.add_argument("--pages", type=int, default=2)
    freeze.add_argument("--per-page", type=int, default=200)
    freeze.add_argument("--holdout-from", default="2026-07-01")
    freeze.add_argument("--refresh", action="store_true")

    rank = sub.add_parser("rank")
    rank.add_argument("--out-dir", default=common["out_dir"])
    rank.add_argument("--seeds", default=common["seeds"])

    label = sub.add_parser("label")
    label.add_argument("--out-dir", default=common["out_dir"])
    label.add_argument("--seeds", default=common["seeds"])
    label.add_argument("--top-per-system", type=int, default=10)
    label.add_argument("--batch", type=int, default=5)
    label.add_argument("--model", default="gpt-6-astra")

    score = sub.add_parser("score")
    score.add_argument("--out-dir", default=common["out_dir"])

    args = parser.parse_args(argv)
    try:
        return {"freeze": cmd_freeze, "rank": cmd_rank, "label": cmd_label, "score": cmd_score}[args.command](args)
    except (RuntimeError, urllib.error.URLError, KeyError, ValueError) as exc:
        print(f"FAIL {args.command}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
