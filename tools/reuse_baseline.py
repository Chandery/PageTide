#!/usr/bin/env python3
"""REUSE-01 local baseline: existing ranker vs an arxiv-sanity-lite style linear SVM.

Zero model tokens, no network, standard library only. Reads the frozen pool under
.local/experiments (candidates.json + cached labels.json) and harness/seeds.json.

Systems (both see the same features: sublinear TF-IDF fitted on unlabelled text):
    existing_ranker      app.ranking: seed + Rocchio(pos, explicit neg) + MMR, as build_batch does
    svm_unlabelled_neg   arxiv-sanity-lite recipe: positives vs every other earlier paper
                         (treats "not tagged" as negative, which PageTide forbids; reported
                         only to compare with the upstream recipe)
    svm_explicit_neg     same SVM, but negatives are only explicit "irrelevant" labels
    recency              newest first

Protocol: labelled candidates are split chronologically; everything published before
the split date is feedback, everything on/after it is the holdout that is ranked.
Several split dates are run so one lucky split is visible as variance.

EXPLORATORY ONLY. The labels come from the evaluation annotator, which saw the seed
titles, so seed-similarity systems are favoured. This is not an owner-labelled result
and not the upstream arxiv-sanity-lite probe (that probe was not run).
"""
import argparse
import hashlib
import json
import random
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import ranking  # noqa: E402

USEFUL = 2  # relevance >= 2 ("worth a skim") counts as useful, same threshold as eval_probe
SHOWN = 10  # one recommendation batch


def text(paper):
    return f"{paper.get('title') or ''} {paper.get('abstract') or ''}"


def features(doc, idf, bigrams):
    tokens = ranking.tokenize(doc)
    if bigrams:
        tokens = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    return ranking.l2_normalize(ranking.vectorize(tokens, idf))


def fit_idf(docs, bigrams):
    lists = []
    for doc in docs:
        tokens = ranking.tokenize(doc)
        if bigrams:
            tokens = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        lists.append(tokens)
    return ranking.build_idf(lists)


def train_linear_svm(pos, neg, c=0.1, epochs=30, seed=7):
    """Class-balanced hinge-loss SVM via Pegasos SGD on sparse dict vectors.

    Mirrors sklearn LinearSVC(class_weight='balanced', C=0.1) closely enough for a
    ranking comparison; it is deterministic for a fixed seed.
    """
    data = [(v, 1.0) for v in pos] + [(v, -1.0) for v in neg]
    if not pos or not neg:
        return None
    n = len(data)
    weight = {1.0: n / (2.0 * len(pos)), -1.0: n / (2.0 * len(neg))}
    lam = 1.0 / (c * n)
    # w = s * v, so the per-step shrink is O(1) instead of O(features).
    v, s, bias, step = {}, 1.0, 0.0, 0
    rng = random.Random(seed)
    for _ in range(epochs):
        order = list(range(n))
        rng.shuffle(order)
        for i in order:
            step += 1
            eta = 1.0 / (lam * step)
            x, y = data[i]
            margin = y * (s * sum(val * v.get(t, 0.0) for t, val in x.items()) + bias)
            scale = 1.0 - eta * lam
            if scale <= 1e-12:
                v, s = {}, 1.0
            else:
                s *= scale
            if margin < 1.0:
                g = eta * weight[y] * y
                for t, val in x.items():
                    v[t] = v.get(t, 0.0) + g * val / s
                bias += g * 0.1
            if s < 1e-9:
                v, s = {t: val * s for t, val in v.items()}, 1.0
    return {t: val * s for t, val in v.items()}, bias


def svm_score(model, x):
    w, bias = model
    return sum(v * w.get(t, 0.0) for t, v in x.items()) + bias


def auc(order, labels):
    useful = [i for i, k in enumerate(order) if labels[k]["relevance"] >= USEFUL]
    bad = [i for i, k in enumerate(order) if labels[k]["relevance"] < USEFUL]
    if not useful or not bad:
        return None
    return sum(1.0 if u < b else 0.0 for u in useful for b in bad) / (len(useful) * len(bad))


def metrics(order, shown, labels):
    useful_ranks = [i + 1 for i, k in enumerate(order) if labels[k]["relevance"] >= USEFUL]
    return {
        "p_at_5": sum(1 for k in shown[:5] if labels[k]["relevance"] >= USEFUL) / min(5, len(shown)),
        "useful_over_shown": sum(1 for k in shown if labels[k]["relevance"] >= USEFUL) / len(shown),
        "shown": len(shown),
        "auc": auc(order, labels),
        "mean_rank_useful": sum(useful_ranks) / len(useful_ranks) if useful_ranks else None,
    }


def run_split(candidates, labels, seed_titles, split_date):
    labelled = [c for c in candidates if c["key"] in labels]
    train = [c for c in labelled if (c["publication_date"] or "") < split_date]
    holdout = [c for c in labelled if (c["publication_date"] or "") >= split_date]
    earlier_unlabelled = [c for c in candidates
                          if c["key"] not in labels and (c["publication_date"] or "") < split_date]
    pos = [c for c in train if labels[c["key"]]["relevance"] >= USEFUL]
    neg = [c for c in train if labels[c["key"]]["relevance"] <= 1]
    # IDF is unsupervised: it may see any text that exists at ranking time, never labels.
    docs = seed_titles + [text(c) for c in candidates if (c["publication_date"] or "") < split_date] \
        + [text(c) for c in holdout]
    results = {"split_date": split_date, "feedback_positive": len(pos), "feedback_negative": len(neg),
               "holdout": len(holdout),
               "holdout_useful": sum(1 for c in holdout if labels[c["key"]]["relevance"] >= USEFUL),
               "systems": {}}

    started = time.perf_counter()
    idf = fit_idf(docs, bigrams=False)
    vec = {c["key"]: features(text(c), idf, False) for c in train + holdout}
    profile = ranking.rocchio([features(t, idf, False) for t in seed_titles],
                              [vec[c["key"]] for c in pos], [vec[c["key"]] for c in neg], 1.0, 0.5)
    scored = sorted(((c["key"], ranking.cosine(profile, vec[c["key"]])) for c in holdout), key=lambda kv: -kv[1])
    order = [k for k, _ in scored]
    shown = ranking.mmr_select(scored[:SHOWN * 4], vec, SHOWN)
    results["systems"]["existing_ranker"] = {**metrics(order, shown, labels),
                                             "seconds": round(time.perf_counter() - started, 3)}

    idf2 = fit_idf(docs, bigrams=True)
    vec2 = {c["key"]: features(text(c), idf2, True) for c in train + holdout + earlier_unlabelled}
    seed_vecs = [features(t, idf2, True) for t in seed_titles]
    positives = seed_vecs + [vec2[c["key"]] for c in pos]
    for name, negatives in (
            ("svm_unlabelled_neg", [vec2[c["key"]] for c in neg + earlier_unlabelled]),
            ("svm_explicit_neg", [vec2[c["key"]] for c in neg])):
        started = time.perf_counter()
        model = train_linear_svm(positives, negatives)
        if model is None:
            results["systems"][name] = {"skipped": "no negatives before split"}
            continue
        order = sorted((c["key"] for c in holdout), key=lambda k: -svm_score(model, vec2[k]))
        results["systems"][name] = {**metrics(order, order[:SHOWN], labels), "training_negatives": len(negatives),
                                    "seconds": round(time.perf_counter() - started, 3)}

    order = [c["key"] for c in sorted(holdout, key=lambda c: c["publication_date"] or "", reverse=True)]
    results["systems"]["recency"] = metrics(order, order[:SHOWN], labels)
    return results


def peak_rss_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024, 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiments", default=str(ROOT / ".local/experiments"))
    parser.add_argument("--seeds", default=str(ROOT / "harness/seeds.json"))
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)
    exp = Path(args.experiments)
    raw = (exp / "candidates.json").read_bytes()
    candidates = json.loads(raw)["all"]
    labels = json.loads((exp / "labels.json").read_text())
    seed_titles = [s["title"] for s in json.loads(Path(args.seeds).read_text())["seeds"]]
    dates = sorted(c["publication_date"] for c in candidates if c["key"] in labels)
    splits = sorted({dates[int(len(dates) * q)] for q in (0.4, 0.5, 0.6, 0.7)})
    started = time.perf_counter()
    report = {
        "exploratory": True,
        "tokens_used": 0,
        "network_calls": 0,
        "candidates_sha256_16": hashlib.sha256(raw).hexdigest()[:16],
        "pool": len(candidates),
        "labelled": len(labels),
        "useful_threshold": USEFUL,
        "batch_size": SHOWN,
        "splits": [run_split(candidates, labels, seed_titles, d) for d in splits],
    }
    report["total_seconds"] = round(time.perf_counter() - started, 2)
    report["peak_rss_mb"] = peak_rss_mb()
    names = list(report["splits"][0]["systems"])
    means = {}
    for name in names:
        rows = [s["systems"][name] for s in report["splits"] if "p_at_5" in s["systems"][name]]
        means[name] = {m: round(sum(r[m] for r in rows if r[m] is not None) /
                                max(1, sum(1 for r in rows if r[m] is not None)), 3)
                       for m in ("p_at_5", "useful_over_shown", "auc", "mean_rank_useful")}
    report["mean_over_splits"] = means

    fmt = lambda v: "n/a" if v is None else f"{v:.2f}"  # noqa: E731
    print(f"pool={report['pool']} labelled={report['labelled']} sha={report['candidates_sha256_16']} "
          f"tokens=0 network=0 total={report['total_seconds']}s peak_rss={report['peak_rss_mb']}MB")
    for split in report["splits"]:
        print(f"\nsplit {split['split_date']}: feedback +{split['feedback_positive']}/-{split['feedback_negative']} "
              f"holdout={split['holdout']} (useful {split['holdout_useful']})")
        print(f"  {'system':20} {'P@5':>5} {'u/shown':>8} {'shown':>5} {'AUC':>5} {'meanRank':>8}")
        for name, row in split["systems"].items():
            if "p_at_5" not in row:
                print(f"  {name:20} {row['skipped']}")
                continue
            print(f"  {name:20} {fmt(row['p_at_5']):>5} {fmt(row['useful_over_shown']):>8} {row['shown']:>5} "
                  f"{fmt(row['auc']):>5} {fmt(row['mean_rank_useful']):>8}")
    print("\nmean over splits:")
    for name, row in means.items():
        print(f"  {name:20} P@5={fmt(row['p_at_5'])} u/shown={fmt(row['useful_over_shown'])} "
              f"AUC={fmt(row['auc'])} meanRank={fmt(row['mean_rank_useful'])}")
    print("\nEXPLORATORY: annotator labels saw seed titles; not owner labels; upstream probe not run.")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
