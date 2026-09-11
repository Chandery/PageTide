"""Application service: wires storage, metadata, ranking, profile and the gateway.

The daily loop is zero-token: discover -> dedupe -> rank -> diversify -> 5 cards.
Feedback updates a transparent profile. AI triage is optional and budgeted.
"""
import json
from pathlib import Path

from . import ranking
from .db import Store, now
from .gateway import Gateway
from .sources import OpenAlex, resolve_seed

ACTIONS = ("useful", "irrelevant", "later", "busy", "confused")
POSITIVE_ACTIONS = {"useful"}
NEGATIVE_ACTIONS = {"irrelevant"}   # 'busy'/'confused'/'later' never change interest


class App:
    def __init__(self, root=".", data_dir=None):
        self.root = Path(root)
        self.data = Path(data_dir) if data_dir else self.root / ".local" / "app"
        self.data.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.data / "paperdighelper.sqlite")
        self.store.init()
        self.source = OpenAlex(self.data / "cache")
        self.gateway = Gateway(root=self.root)

    # ---------------------------------------------------------------- profile
    def seeds(self):
        return json.loads((self.root / "harness" / "seeds.json").read_text())["seeds"]

    def seed_keys(self):
        return self.store.get_setting("seed_keys", [])

    def ensure_seed_papers(self):
        keys = []
        for seed in self.seeds():
            paper = resolve_seed(self.source, seed)
            if paper:
                paper = dict(paper)
                paper["published"] = paper.get("published") or None
                self.store.upsert_papers([paper])
                keys.append(paper["key"])
        self.store.set_setting("seed_keys", keys)
        if self.store.current_profile() is None:
            self.save_profile({"project": "world-models", "pinned_terms": [],
                               "weights": {"pos": 1.0, "neg": 0.5}}, note="initial")
        return keys

    def latest_feedback(self):
        return self.store.feedback_by_paper()

    def profile(self):
        base = self.store.current_profile() or {"project": "world-models", "pinned_terms": [],
                                                "weights": {"pos": 1.0, "neg": 0.5}}
        feedback = self.latest_feedback()
        positives = [k for k, v in feedback.items() if v["action"] in POSITIVE_ACTIONS]
        negatives = [k for k, v in feedback.items() if v["action"] in NEGATIVE_ACTIONS]
        return {
            "project": base["project"],
            "pinned_terms": base.get("pinned_terms", []),
            "weights": base.get("weights", {"pos": 1.0, "neg": 0.5}),
            "positive_seeds": self.seed_keys(),
            "positive_feedback": sorted(positives),
            "explicit_negatives": sorted(negatives),
            "neutral_feedback": sorted(k for k, v in feedback.items() if v["action"] in ("later", "busy", "confused")),
        }

    def save_profile(self, data, note=None):
        return self.store.save_profile(data, note=note)

    def profile_vector(self, papers_by_key, idf):
        profile = self.profile()
        weights = profile["weights"]
        seeds = [papers_by_key[k] for k in profile["positive_seeds"] if k in papers_by_key]
        # seed papers may not be in the candidate pool; fall back to the stored seed set
        seed_texts = [f"{p.get('title') or ''} {p.get('abstract') or ''}" for p in seeds]
        if not seed_texts:
            seed_texts = [s["title"] for s in self.seeds()]
        seed_vectors = [ranking.l2_normalize(ranking.vectorize(ranking.tokenize(t), idf)) for t in seed_texts]
        term_text = " ".join(profile["pinned_terms"])
        if term_text.strip():
            seed_vectors.append(ranking.l2_normalize(ranking.vectorize(ranking.tokenize(term_text), idf)))
        pos = [ranking.l2_normalize(ranking.vectorize(ranking.tokenize(
            f"{papers_by_key[k].get('title') or ''} {papers_by_key[k].get('abstract') or ''}"), idf))
            for k in profile["positive_feedback"] if k in papers_by_key]
        neg = [ranking.l2_normalize(ranking.vectorize(ranking.tokenize(
            f"{papers_by_key[k].get('title') or ''} {papers_by_key[k].get('abstract') or ''}"), idf))
            for k in profile["explicit_negatives"] if k in papers_by_key]
        return ranking.rocchio(seed_vectors, pos, neg, weights.get("pos", 1.0), weights.get("neg", 0.5))

    # ------------------------------------------------------------------ daily
    def stats(self):
        feedback = self.latest_feedback()
        return {
            "papers": len(self.store.papers()),
            "seeds": len(self.seed_keys()),
            "positive": sum(1 for v in feedback.values() if v["action"] in POSITIVE_ACTIONS),
            "negative": sum(1 for v in feedback.values() if v["action"] in NEGATIVE_ACTIONS),
            "neutral": sum(1 for v in feedback.values() if v["action"] in ("later", "busy", "confused")),
            "shown": len(self.store.seen_keys()),
            "summaries": len(self.store.summaries()),
        }

    def paper_detail(self, key):
        paper = self.store.paper(key)
        if not paper:
            return None
        return {
            "key": paper["key"], "title": paper["title"], "abstract": paper["abstract"] or "",
            "published": paper["published"], "source": paper["source"],
            "doi": paper["doi"], "arxiv_id": paper["arxiv_id"],
            "url": (f"https://arxiv.org/abs/{paper['arxiv_id']}" if paper["arxiv_id"]
                    else (paper["doi"] or paper["openalex_id"])),
            "feedback": self.latest_feedback().get(key),
            "summary": self.store.summaries().get(key),
        }

    def refresh_candidates(self, search="world model", from_date="2024-01-01", pages=1, per_page=100,
                           include_distractors=False, distractor_per_query=20):
        """Fast by default: one field query; distractors are opt-in (five more calls)."""
        errors = []
        try:
            field = self.source.discover(search=search, from_date=from_date, pages=pages, per_page=per_page)
        except RuntimeError as exc:
            field, errors = [], errors + [{"query": search, "error": str(exc)[-120:]}]
        papers = list(field)
        if include_distractors:
            extra, distractor_errors = self.source.distractors(from_date=from_date, per_query=distractor_per_query)
            papers += extra
            errors += distractor_errors
        added = self.store.upsert_papers(papers)
        return {"fetched": len(papers), "added": added, "field": len(field), "errors": errors}

    def import_candidates(self, path):
        """Load a frozen candidate JSON (e.g. from the DATA-01 experiments) for offline/dev use."""
        payload = json.loads(Path(path).read_text())
        papers = payload.get("all", payload if isinstance(payload, list) else [])
        normalized = [{"key": p["key"], "openalex_id": p.get("openalex_id"), "doi": p.get("doi"),
                       "arxiv_id": p.get("arxiv_id"), "title": p["title"], "abstract": p.get("abstract"),
                       "published": p.get("publication_date") or p.get("published"),
                       "source": p.get("source"), "group_name": p.get("group", "field")}
                      for p in papers]
        added = self.store.upsert_papers(normalized)
        return {"imported": len(normalized), "added": added}

    def build_batch(self, limit=5, run_date=None, exclude_seen=True):
        run_date = run_date or now()[:10]
        papers = self.store.papers()
        seen = self.store.seen_keys() if exclude_seen else set()
        feedback = self.latest_feedback()
        pool = [p for p in papers if p["key"] not in seen and p["key"] not in feedback]
        if not pool:
            return {"batch_id": None, "cards": [], "reason": "no unseen candidates"}
        corpus = [f"{p['title']} {p['abstract'] or ''}" for p in pool]
        idf = ranking.build_idf([ranking.tokenize(doc) for doc in corpus])
        vectors = {p["key"]: ranking.l2_normalize(ranking.vectorize(ranking.tokenize(
            f"{p['title']} {p['abstract'] or ''}"), idf)) for p in pool}
        profile_vector = self.profile_vector({p["key"]: p for p in pool}, idf)
        scored = [(p["key"], ranking.cosine(profile_vector, vectors[p["key"]])) for p in pool]
        scored.sort(key=lambda kv: -kv[1])
        shortlist = scored[:max(limit * 4, limit)]
        chosen = ranking.mmr_select(shortlist, vectors, limit)
        batch_id = self.store.create_batch(run_date, chosen)
        return {"batch_id": batch_id, "cards": self.cards(batch_id)}

    def cards(self, batch_id=None):
        rows = self.store.batch(batch_id) if batch_id is not None else self.store.latest_batch()
        profile = self.profile()
        terms = set(profile["pinned_terms"])
        cards = []
        for row in rows:
            title_words = set(ranking.tokenize(row["title"]))
            matched = sorted(terms & title_words)
            cards.append({
                "key": row["key"], "rank": row["rank"], "title": row["title"],
                "abstract": row["abstract"], "published": row["published"], "source": row["source"],
                "arxiv_id": row["arxiv_id"], "doi": row["doi"],
                "url": (f"https://arxiv.org/abs/{row['arxiv_id']}" if row["arxiv_id"]
                        else (row["doi"] or row["openalex_id"])),
                "why": ("命中钉死关键词: " + ", ".join(matched)) if matched else "与种子/反馈画像相似",
                "mode": "sparse",
            })
        return cards

    # --------------------------------------------------------------- feedback
    def record_feedback(self, paper_key, action, reason=None):
        if action not in ACTIONS:
            raise ValueError(f"unknown action: {action}")
        feedback_id = self.store.add_feedback(paper_key, action, reason)
        self.save_profile(self.store.current_profile() or {"project": "world-models", "pinned_terms": [],
                                                           "weights": {"pos": 1.0, "neg": 0.5}},
                          note=f"feedback:{action}")
        return {"feedback_id": feedback_id, "action": action, "interest_changed": action in (POSITIVE_ACTIONS | NEGATIVE_ACTIONS)}

    def undo_feedback(self, feedback_id):
        self.store.undo_feedback(feedback_id)
        return {"undone": feedback_id}

    # ------------------------------------------------------------------- pdf
    def download_pdf(self, paper_key, timeout=60):
        import urllib.request
        paper = self.store.paper(paper_key)
        if not paper:
            raise ValueError(f"unknown paper: {paper_key}")
        if not paper.get("arxiv_id"):
            return {"ok": False, "reason": "no open-access PDF known for this paper"}
        url = f"https://arxiv.org/pdf/{paper['arxiv_id']}"
        target = self.data / "pdfs"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{paper['arxiv_id']}.pdf"
        if path.exists():
            self.store.record_pdf(paper_key, path, url)
            return {"ok": True, "path": str(path), "cached": True}
        request = urllib.request.Request(url, headers={"User-Agent": "PaperDigHelper/0.1 (local app)"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
        if not data.startswith(b"%PDF"):
            return {"ok": False, "reason": "response was not a PDF"}
        path.write_bytes(data)
        self.store.record_pdf(paper_key, path, url)
        return {"ok": True, "path": str(path), "bytes": len(data)}

    # ---------------------------------------------------------------- triage
    def triage(self, cards, dry_run=False):
        """Optional AI summaries for the cards. Degrades to local-only on any failure."""
        if not cards:
            return {"ok": True, "items": [], "mode": "sparse"}
        profile = self.profile()
        lines = []
        for card in cards:
            lines.append(f"- id={card['key']} | {card['title']} | {(card['abstract'] or '')[:600]}")
        messages = [{
            "role": "user",
            "content": ("你在为一个研究画像速览论文。只输出 JSON 数组，每项 "
                        '{"paper_id": "...", "one_liner": "...", "why_relevant": "...", "caution": "..."}。\n'
                        f"画像钉死词：{', '.join(profile['pinned_terms']) or '(未设置)'}\n"
                        f"画像正向种子数：{len(profile['positive_seeds'])}\n"
                        f"候选：\n" + "\n".join(lines)),
        }]
        result = self.gateway.call("daily_triage", messages, dry_run=dry_run)
        if dry_run or not result.get("ok"):
            return {"ok": False, "degraded": True, "reason": result.get("reason"),
                    "items": [], "mode": "sparse", "reservation": result.get("reservation")}
        import re
        match = re.search(r"\[.*\]", result["content"], re.S)
        items = json.loads(match.group(0)) if match else []
        for item in items:
            key = item.get("paper_id")
            if key:
                self.store.save_summary(key, item.get("one_liner"), item.get("why_relevant"),
                                        item.get("caution"), result.get("model"))
        return {"ok": True, "items": items, "usage": result["usage"], "usd": result["usd"], "mode": "sparse+llm"}
