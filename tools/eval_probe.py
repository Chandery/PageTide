#!/usr/bin/env python3
"""Offline ranking experiment: freeze a mixed candidate set, rank, label, score.

Zero model tokens for freeze/rank/score/spotcheck. `label` calls the evaluation
annotator (taomu) only, never the shipped runtime provider, and caches labels.

The profile is the 10 owner seeds (seed-based cold start). The candidate pool is
deliberately mixed: field papers (arXiv title.search:"world model") plus
off-field distractors from adjacent CS topics, so relevance is not trivially 1.0.

Relevance is graded 0-3 (0 not related, 1 related but off-topic, 2 worth a
skim, 3 want to read) so P@k has variance.

This builds the measurement harness and fixed baselines; it is NOT the
upstream-reuse probe (REUSE-01) and NOT a product-quality result.

Commands:
    freeze     fetch + dedupe + split a replayable mixed candidate set
    rank       recency / keyword+date / TF-IDF-seed-centroid
    label      annotate the union of shown candidates + a random sample (cached)
    score      graded P@k and mean relevance per system
    spotcheck  write a blind sheet for the owner to validate annotator labels
"""
import argparse
import hashlib
import json
import math
import os
import random
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
    "models", "learning", "learn", "however", "while", "when", "where", "between",
}
FIELD_QUERY = "world model"
DISTRACTOR_QUERIES = [
    "diffusion model", "large language model", "reinforcement learning",
    "video generation", "image segmentation",
]


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
    return {token: (1.0 + math.log(count)) * idf.get(token, 0.0) for token, count in counts.items()}


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


def precision_at_k(order, labels, k, threshold=2):
    """Fraction of top-k whose graded relevance >= threshold, or None if unjudged."""
    top = order[:k]
    if any(key not in labels for key in top):
        return None
    return sum(1 for key in top if (labels[key].get("relevance") or 0) >= threshold) / k


def mean_relevance_at_k(order, labels, k):
    top = order[:k]
    if any(key not in labels for key in top):
        return None
    return sum(labels[key].get("relevance", 0) for key in top) / k


def paper_text(work):
    return f"{work.get('title') or ''} {data_probe.abstract_text(work.get('abstract_inverted_index'))}".strip()


def openalex_key(work):
    ids = data_probe.openalex_ids(work)
    return ids["doi"] or ids["openalex_id"] or data_probe.normalize_title(work.get("title"))


def fetch_candidates(specs, snapshot_dir, refresh=False):
    """specs: list of (group, search, pages). Dedupe by key and normalized title."""
    seen_keys, seen_titles, works = set(), set(), []
    for group, search, pages in specs:
        for page in range(1, pages + 1):
            payload, _ = data_probe.query_openalex(
                {"filter": (f"primary_location.source.id:{data_probe.ARXIV_SOURCE_ID},"
                            f"title.search:{search},from_publication_date:2024-01-01,to_publication_date:2026-09-11"),
                 "sort": "publication_date:desc", "per-page": 200, "page": page},
                snapshot_dir, f"pool-{re.sub(r'[^a-z0-9]+', '-', search.lower())}-p{page}", refresh=refresh)
            for work in payload.get("results", []):
                key = openalex_key(work)
                title = data_probe.normalize_title(work.get("title"))
                if key in seen_keys or (title and title in seen_titles):
                    continue
                seen_keys.add(key)
                if title:
                    seen_titles.add(title)
                works.append((group, work))
    return works


def slim(group, work):
    ids = data_probe.openalex_ids(work)
    return {
        "group": group, "key": openalex_key(work), "openalex_id": ids["openalex_id"], "doi": ids["doi"],
        "arxiv_id": ids["arxiv_id"], "title": work.get("title"),
        "publication_date": work.get("publication_date"),
        "abstract": data_probe.abstract_text(work.get("abstract_inverted_index")),
        "abstract_chars": len(data_probe.abstract_text(work.get("abstract_inverted_index"))),
    }


def paper_text_from_slim(candidate):
    return f"{candidate.get('title') or ''} {candidate.get('abstract') or ''}".strip()


def dataset_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def cmd_freeze(args):
    out = Path(args.out_dir)
    snapshots = out / "snapshots"
    seeds = json.loads(Path(args.seeds).read_text())["seeds"]
    specs = [("field", FIELD_QUERY, args.field_pages)]
    if args.distractors:
        specs += [("distractor", q, args.distractor_pages) for q in DISTRACTOR_QUERIES]
    works = fetch_candidates(specs, snapshots, refresh=args.refresh)
    seed_arxiv = {str((s.get("ids") or {}).get("arxiv_id")) for s in seeds if (s.get("ids") or {}).get("arxiv_id")}
    candidates = [slim(g, w) for g, w in works if str(data_probe.openalex_ids(w).get("arxiv_id")) not in seed_arxiv]
    payload = {"all": candidates}
    (out / "candidates.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    field = sum(1 for c in candidates if c["group"] == "field")
    print(f"deduped={len(candidates)} field={field} distractor={len(candidates) - field} "
          f"seeds_excluded={len(seed_arxiv)}")
    date_lo = min(c["publication_date"] for c in candidates)
    date_hi = max(c["publication_date"] for c in candidates)
    print(f"dates {date_lo} .. {date_hi}  abstract_missing={sum(1 for c in candidates if not c['abstract'])}")
    print(f"dataset_hash={dataset_hash(payload)}")
    return 0


def cmd_rank(args):
    out = Path(args.out_dir)
    holdout = json.loads((out / "candidates.json").read_text())["all"]
    seeds = json.loads(Path(args.seeds).read_text())["seeds"]
    seed_docs = [s["title"] for s in seeds]
    corpus = seed_docs + [paper_text_from_slim(c) for c in holdout]
    idf = build_idf([tokenize(doc) for doc in corpus])
    profile_vector = centroid([l2_normalize(vectorize(tokenize(doc), idf)) for doc in seed_docs])
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
    by_key = {c["key"]: c for c in holdout}
    for name, order in rankings.items():
        print(f"\n[{name}] top 5:")
        for key in order[:5]:
            work = by_key[key]
            print(f"   {work['publication_date']} [{work['group'][:4]}] {work['title'][:68]}")
    return 0


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
        f"{i+1}. id={p['key']} | {p['title']} | {p['publication_date']} | {(p['abstract'] or '')[:400]}"
        for i, p in enumerate(papers))
    prompt = (
        "你是论文相关性评审。给定研究画像与候选论文，为每篇打一个 0-3 的相关度：\n"
        "0=不相关；1=属于计算机/相关领域但不是该方向；2=相关、值得扫一眼；"
        "3=与画像高度相关、很想读。\n"
        "判断要严格：仅仅在标题里出现 world model 不等于高分；必须与本画像关心的"
        "（latent prediction、planning、视频/机器人世界模型、JEPA 等）实质相关。\n"
        f"画像关键词：{', '.join(profile_terms[:20])}\n"
        f"画像种子标题：{'; '.join(seed_titles[:10])}\n\n"
        f"候选论文：\n{listing}\n\n"
        "只输出 JSON 数组，每项 {\"paper_id\": \"...\", \"relevance\": 0-3, "
        "\"reason\": \"<=15词\"}。不要输出其他文字。"
    )
    body = json.dumps({"model": model, "max_tokens": 2000,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    request = urllib.request.Request(
        f"{base}/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
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


def select_union(candidates, rankings, top_per_system, random_sample, seed=0):
    by_key = {c["key"]: c for c in candidates}
    union, seen = [], set()
    for order in rankings["systems"].values():
        for key in order[:top_per_system]:
            if key not in seen:
                seen.add(key)
                union.append(by_key[key])
    if random_sample:
        pool = sorted(by_key)
        for key in random.Random(seed).sample(pool, min(random_sample, len(pool))):
            if key not in seen:
                seen.add(key)
                union.append(by_key[key])
    return union


def cmd_label(args):
    out = Path(args.out_dir)
    candidates = json.loads((out / "candidates.json").read_text())["all"]
    rankings = json.loads((out / "rankings.json").read_text())
    seeds = json.loads(Path(args.seeds).read_text())["seeds"]
    union = select_union(candidates, rankings, args.top_per_system, args.random_sample, args.seed)
    labels_path = out / "labels.json"
    labels = json.loads(labels_path.read_text()) if labels_path.exists() else {}
    pending = [p for p in union if p["key"] not in labels]
    base, key = _load_annotator_env()
    print(f"union={len(union)} already_labelled={len(union) - len(pending)} pending={len(pending)}")
    for start in range(0, len(pending), args.batch):
        batch = pending[start:start + args.batch]
        result, usage = annotate_batch(batch, rankings["profile_terms"], [s["title"] for s in seeds],
                                       base, key, args.model)
        for item in result:
            level = item.get("relevance")
            level = int(level) if isinstance(level, (int, float)) else 0
            labels[item["paper_id"]] = {"relevance": max(0, min(3, level)), "reason": item.get("reason")}
        labels_path.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n")
        print(f"  labelled {min(start + len(batch), len(pending))}/{len(pending)} usage={usage}")
        time.sleep(1)
    print(f"labels={len(labels)} unlabelled_in_union={[p['key'] for p in union if p['key'] not in labels]}")
    return 0


def cmd_score(args):
    out = Path(args.out_dir)
    rankings = json.loads((out / "rankings.json").read_text())["systems"]
    labels = json.loads((out / "labels.json").read_text())
    counts = {level: sum(1 for v in labels.values() if v.get("relevance") == level) for level in range(4)}
    spread = max(counts.values()) / max(len(labels), 1)
    print(f"labelled={len(labels)} relevance_distribution={counts} "
          f"(share@{max(counts, key=counts.get)}={spread:.0%})")
    print(f"{'system':24} {'P@5>=2':>7} {'P@5>=3':>7} {'meanRel@5':>9} {'P@10>=2':>8} {'judged':>7}")
    for name, order in rankings.items():
        p5_2 = precision_at_k(order, labels, 5, 2)
        p5_3 = precision_at_k(order, labels, 5, 3)
        mr5 = mean_relevance_at_k(order, labels, 5)
        p10_2 = precision_at_k(order, labels, 10, 2)
        fmt = lambda v: f"{v:.2f}" if v is not None else "n/a"  # noqa: E731
        print(f"{name:24} {fmt(p5_2):>7} {fmt(p5_3):>7} {fmt(mr5):>9} {fmt(p10_2):>8} "
              f"{sum(1 for k in order if k in labels):7d}")
    print("\nNOTE: exploratory slice; annotator is a proxy, not the owner's judgement.")
    if spread > 0.8:
        print("WARNING: one relevance level dominates -> metric still has little variance.")
    return 0


def cmd_spotcheck(args):
    out = Path(args.out_dir)
    candidates = {c["key"]: c for c in json.loads((out / "candidates.json").read_text())["all"]}
    labels = json.loads((out / "labels.json").read_text())
    picked = random.Random(args.seed).sample(sorted(labels), min(args.count, len(labels)))
    sheet = ["# 抽检表（盲评）", "",
             "请只根据标题+摘要判断，不要参考任何模型结论。把 `relevance` 填 0/1/2/3：",
             "0=不相关 1=相关领域但不是这个方向 2=值得扫一眼 3=很想读", ""]
    key = {}
    for i, k in enumerate(picked, 1):
        c = candidates[k]
        key[k] = labels[k]
        sheet += [f"## {i}. relevance = __", f"- {c['title']}", f"- {c['publication_date']} · {c['key']}",
                  "", (c["abstract"] or "")[:600], ""]
    (out / "spotcheck-sheet.md").write_text("\n".join(sheet))
    (out / "spotcheck-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {out / 'spotcheck-sheet.md'} ({len(picked)} items) and the hidden key {out / 'spotcheck-key.json'}")
    print("The sheet is blind; the key stays in .local for later agreement scoring.")
    return 0


def parse_spotcheck_sheet(path):
    """Return [(candidate_key, owner_level)] parsed from a filled blind sheet."""
    items = []
    for block in re.split(r"\n## ", Path(path).read_text())[1:]:
        level = re.search(r"relevance\s*=\s*_?(\d)_?", block)
        key = None
        for line in block.splitlines():
            if line.startswith("- ") and " · " in line:
                key = line.split(" · ")[-1].strip()
        if level and key:
            items.append((key, int(level.group(1))))
    return items


def spotcheck_agreement(items, annotator_labels):
    rows = [(key, owner, annotator_labels[key]["relevance"])
            for key, owner in items if key in annotator_labels]
    n = max(len(rows), 1)
    exact = sum(1 for _, o, a in rows if o == a)
    within1 = sum(1 for _, o, a in rows if abs(o - a) <= 1)
    binary = sum(1 for _, o, a in rows if (o >= 2) == (a >= 2))
    confusion = {}
    for _, o, a in rows:
        confusion.setdefault(o, {}).setdefault(a, 0)
        confusion[o][a] += 1
    return {"n": len(rows), "exact": exact / n, "within1": within1 / n, "binary": binary / n,
            "owner_distribution": {lvl: sum(1 for _, o, _ in rows if o == lvl) for lvl in range(4)},
            "annotator_distribution": {lvl: sum(1 for _, _, a in rows if a == lvl) for lvl in range(4)},
            "confusion_owner_rows": confusion}


def cmd_spotcheck_score(args):
    out = Path(args.out_dir)
    items = []
    used = []
    for name in [s.strip() for s in args.sheets.split(",") if s.strip()]:
        path = out / name
        if path.exists():
            items += parse_spotcheck_sheet(path)
            used.append(name)
    labels = json.loads((out / "labels.json").read_text())
    stats = spotcheck_agreement(items, labels)
    print(f"sheets={used} compared={stats['n']}  exact={stats['exact']:.0%}  "
          f"within1={stats['within1']:.0%}  binary(>=2)={stats['binary']:.0%}")
    print(f"owner distribution     : {stats['owner_distribution']}")
    print(f"annotator distribution : {stats['annotator_distribution']}")
    print("confusion (owner row -> annotator col):")
    for owner in sorted(stats["confusion_owner_rows"]):
        print(f"  owner={owner}: {dict(sorted(stats['confusion_owner_rows'][owner].items()))}")
    print("threshold sweep (annotator>=T as 'useful' vs owner>=2):")
    rows = [(k, o, labels[k]["relevance"]) for k, o in items if k in labels]
    for threshold in (2, 3):
        agree = sum(1 for _, o, a in rows if (o >= 2) == (a >= threshold))
        tp = sum(1 for _, o, a in rows if o >= 2 and a >= threshold)
        fp = sum(1 for _, o, a in rows if o < 2 and a >= threshold)
        fn = sum(1 for _, o, a in rows if o >= 2 and a < threshold)
        print(f"  T>={threshold}: agreement={agree / max(len(rows), 1):.0%} tp={tp} fp={fp} fn={fn}")
    print("\nNOTE: small sample; threshold chosen on this sample is post-hoc, freeze it only for future sets.")
    return 0


def build_rocchio_profile(seed_vectors, pos_vectors, neg_vectors, pos_weight=1.0, neg_weight=0.5):
    """Seed centroid + weighted positive centroid - weighted negative centroid (Rocchio-style)."""
    combined = {}
    for name, weight in (("seed", 1.0), ("pos", pos_weight), ("neg", -neg_weight)):
        vectors = {"seed": seed_vectors, "pos": pos_vectors, "neg": neg_vectors}[name]
        if not vectors:
            continue
        center = centroid(vectors)
        for token, value in center.items():
            combined[token] = combined.get(token, 0.0) + weight * value
    positive = {token: value for token, value in combined.items() if value > 0}
    return l2_normalize(positive)


def feedback_split(candidates, labels, split_date=None):
    """Chronological split of labelled candidates into (feedback batch A, evaluation batch B)."""
    labelled = [c for c in candidates if c["key"] in labels]
    labelled.sort(key=lambda c: c["publication_date"] or "")
    if split_date is None:
        split_date = labelled[len(labelled) // 2]["publication_date"]
    batch_a = [c for c in labelled if (c["publication_date"] or "") < split_date]
    batch_b = [c for c in labelled if (c["publication_date"] or "") >= split_date]
    return batch_a, batch_b, split_date


def ranking_auc(order, labels, threshold=2):
    """P(a useful item is ranked above a not-useful item); 0.5 credit for ties."""
    useful = [i for i, key in enumerate(order) if labels.get(key, {}).get("relevance", 0) >= threshold]
    bad = [i for i, key in enumerate(order) if key in labels and labels[key].get("relevance", 0) < threshold]
    if not useful or not bad:
        return None
    pairs = len(useful) * len(bad)
    wins = sum(1.0 if u < b else 0.5 if u == b else 0.0 for u in useful for b in bad)
    return wins / pairs


def mean_rank_of_useful(order, labels, threshold=2):
    ranks = [i + 1 for i, key in enumerate(order)
             if labels.get(key, {}).get("relevance", 0) >= threshold]
    return sum(ranks) / len(ranks) if ranks else None


def cmd_feedback(args):
    out = Path(args.out_dir)
    candidates = json.loads((out / "candidates.json").read_text())["all"]
    labels = json.loads((out / "labels.json").read_text())
    seeds = json.loads(Path(args.seeds).read_text())["seeds"]
    batch_a, batch_b, split_date = feedback_split(candidates, labels, args.split_date)
    print(f"split_date={split_date}  feedback_batch_A={len(batch_a)}  evaluation_batch_B={len(batch_b)}")

    # IDF is fit only on information available before batch B (seeds + batch A).
    available = [s["title"] for s in seeds] + [paper_text_from_slim(c) for c in batch_a]
    idf = build_idf([tokenize(doc) for doc in available])
    seed_vectors = [l2_normalize(vectorize(tokenize(doc), idf)) for doc in [s["title"] for s in seeds]]
    a_vectors = [l2_normalize(vectorize(tokenize(paper_text_from_slim(c)), idf)) for c in batch_a]
    b_vectors = [l2_normalize(vectorize(tokenize(paper_text_from_slim(c)), idf)) for c in batch_b]

    pos_a = [a_vectors[i] for i, c in enumerate(batch_a) if labels[c["key"]]["relevance"] >= 2]
    neg_a = [a_vectors[i] for i, c in enumerate(batch_a) if labels[c["key"]]["relevance"] <= 1]
    print(f"batch_A feedback: positive={len(pos_a)} negative={len(neg_a)}")

    profiles = {
        "frozen_seed": build_rocchio_profile(seed_vectors, [], []),
        "updated_pos_only": build_rocchio_profile(seed_vectors, pos_a, [], 1.0, 0.0),
        "updated_pos_neg": build_rocchio_profile(seed_vectors, pos_a, neg_a, args.pos_weight, args.neg_weight),
    }
    order_by_date = sorted(range(len(batch_b)), key=lambda i: batch_b[i]["publication_date"] or "", reverse=True)
    systems = {"recency_baseline": order_by_date}
    for name, vector in profiles.items():
        systems[name] = sorted(range(len(batch_b)), key=lambda i: -cosine(vector, b_vectors[i]))

    print(f"{'system':22} {'P@5':>6} {'P@10':>6} {'AUC':>6} {'meanRankUseful':>15} {'meanRel@10':>11}")
    for name, order in systems.items():
        keys = [batch_b[i]["key"] for i in order]
        p5 = precision_at_k(keys, labels, 5, 2)
        p10 = precision_at_k(keys, labels, 10, 2)
        auc = ranking_auc(keys, labels, 2)
        mrank = mean_rank_of_useful(keys, labels, 2)
        mr10 = mean_relevance_at_k(keys, labels, 10)
        fmt = lambda v: f"{v:.2f}" if v is not None else "n/a"  # noqa: E731
        print(f"{name:22} {fmt(p5):>6} {fmt(p10):>6} {fmt(auc):>6} {fmt(mrank):>15} {fmt(mr10):>11}")
    print("\nNOTE: chronological split of a small labelled set; single split, not a rolling sequence.")
    print("AUC and mean rank use all labels; P@5/P@10 saturate when the pool is easy at the top.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    out_default = ".local/experiments"

    freeze = sub.add_parser("freeze")
    freeze.add_argument("--out-dir", default=out_default)
    freeze.add_argument("--seeds", default="harness/seeds.json")
    freeze.add_argument("--field-pages", type=int, default=2)
    freeze.add_argument("--distractor-pages", type=int, default=1)
    freeze.add_argument("--no-distractors", dest="distractors", action="store_false")
    freeze.add_argument("--refresh", action="store_true")

    rank = sub.add_parser("rank")
    rank.add_argument("--out-dir", default=out_default)
    rank.add_argument("--seeds", default="harness/seeds.json")

    label = sub.add_parser("label")
    label.add_argument("--out-dir", default=out_default)
    label.add_argument("--seeds", default="harness/seeds.json")
    label.add_argument("--top-per-system", type=int, default=10)
    label.add_argument("--random-sample", type=int, default=20)
    label.add_argument("--batch", type=int, default=5)
    label.add_argument("--seed", type=int, default=0)
    label.add_argument("--model", default="gpt-6-astra")

    score = sub.add_parser("score")
    score.add_argument("--out-dir", default=out_default)

    spot = sub.add_parser("spotcheck")
    spot.add_argument("--out-dir", default=out_default)
    spot.add_argument("--count", type=int, default=15)
    spot.add_argument("--seed", type=int, default=0)

    spot_score = sub.add_parser("spotcheck-score")
    spot_score.add_argument("--out-dir", default=out_default)
    spot_score.add_argument("--sheets", default="spotcheck-sheet.md,spotcheck-sheet-2.md")

    feedback = sub.add_parser("feedback")
    feedback.add_argument("--out-dir", default=out_default)
    feedback.add_argument("--seeds", default="harness/seeds.json")
    feedback.add_argument("--split-date", default=None)
    feedback.add_argument("--pos-weight", type=float, default=1.0)
    feedback.add_argument("--neg-weight", type=float, default=0.5)

    args = parser.parse_args(argv)
    handlers = {"freeze": cmd_freeze, "rank": cmd_rank, "label": cmd_label,
                "score": cmd_score, "spotcheck": cmd_spotcheck, "spotcheck-score": cmd_spotcheck_score,
                "feedback": cmd_feedback}
    try:
        return handlers[args.command](args)
    except (RuntimeError, urllib.error.URLError, KeyError, ValueError) as exc:
        print(f"FAIL {args.command}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
