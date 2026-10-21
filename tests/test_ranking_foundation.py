"""Slice 0 of Route Mode: the recommendation base must actually use feedback and handle Chinese.

Before this slice build_batch built the profile vector only from the candidate pool, and the pool excludes
every paper that already has feedback, so 收藏/不感兴趣 never reached the ranking.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recommendation_fixtures import english_papers
from app import ranking
from app.service import App


def old_tokenize(text):
    """The tokenizer before CJK support, kept here as the oracle for 'English is unchanged'."""
    words = re.findall(r"[a-z0-9][a-z0-9\-]+", (text or "").lower())
    return [w for w in words if len(w) >= 3 and w not in ranking.STOPWORDS]


class TokenizerTests(unittest.TestCase):
    ENGLISH = [
        "", None, "A latent world model for planning", "Self-Supervised Video Models: V-JEPA 2 (2025)!",
        "GaN-on-Si epitaxial growth, MOCVD & MBE; 2D/3D heterostructures", "the of and a an to",
        "ALL CAPS WORDS and mixed-Case-Hyphens a-b c--d", "numbers 123 4567 8 and x1y2 z", "résumé naïve café — dash",
    ]

    def test_english_output_is_byte_identical_to_the_old_tokenizer(self):
        for text in self.ENGLISH:
            self.assertEqual(ranking.tokenize(text), old_tokenize(text), repr(text))

    def test_chinese_runs_become_character_bigrams(self):
        self.assertEqual(ranking.tokenize("半导体晶体生长"), ["半导", "导体", "体晶", "晶体", "体生", "生长"])

    def test_punctuation_splits_runs_and_single_characters_are_ignored(self):
        self.assertEqual(ranking.tokenize("半导体，生长、水"), ["半导", "导体", "生长"])

    def test_mixed_text_keeps_english_tokens_then_adds_chinese_bigrams(self):
        tokens = ranking.tokenize("GaN 外延生长 growth")
        self.assertEqual([t for t in tokens if t.isascii()], old_tokenize("GaN 外延生长 growth"))
        self.assertEqual([t for t in tokens if not t.isascii()], ["外延", "延生", "生长"])

    def test_chinese_vectors_overlap_only_when_they_share_bigrams(self):
        docs = [ranking.tokenize(t) for t in ("半导体生长", "晶体生长", "古典文学")]
        idf = ranking.build_idf(docs)
        vec = [ranking.l2_normalize(ranking.vectorize(d, idf)) for d in docs]
        self.assertGreater(ranking.cosine(vec[0], vec[1]), 0)   # share 生长
        self.assertEqual(ranking.cosine(vec[0], vec[2]), 0)


class DisplayTermsTests(unittest.TestCase):
    def test_words_is_the_old_ascii_tokenizer(self):
        for text in TokenizerTests.ENGLISH + ["GaN 外延生长 growth", "半导体"]:
            self.assertEqual(ranking.words(text), old_tokenize(text), repr(text))


class ReasonAndKeywordTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(root), data_dir=str(root / "data"))
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=False)
        self.addCleanup(self.app.store.close)

    def test_local_guidance_keywords_never_show_chinese_fragments(self):
        self.assertEqual(App._guidance_terms("用视频预训练的世界模型 world models planning"), App._guidance_terms("world models planning"))
        self.assertEqual(App._guidance_terms("半导体生长 epitaxy"), ["epitaxy"])

    def test_a_reason_names_whole_chinese_pinned_phrases_and_no_fragments(self):
        pid = self.app.create_project("P", "manual", ["半导体生长"])["project_id"]
        self.app.store.upsert_papers([{"key": "k", "title": "半导体晶体生长技术", "abstract": "介绍半导体生长", "published": "2026-01-01"}], project_id=pid)
        self.app.store.add_project_paper(pid, "k", "seed")
        paper = {"key": "k", "title": "介绍半导体生长技术", "abstract": "半导体生长的方法", "topic": None}
        why = self.app.explain(paper, pid)
        self.assertEqual(why["matched_terms"], ["半导体生长"])
        self.assertEqual(why["shared_terms"], [])  # no two-character fragments
        self.assertIn("半导体生长", why["why"])


class SortTests(unittest.TestCase):
    def test_equal_scores_break_by_newest_then_key(self):
        scored = [("b", 0.0), ("a", 0.0), ("c", 0.0), ("d", 0.5)]
        published = {"a": "2026-01-01", "b": "2026-03-01", "c": "2026-03-01", "d": "2020-01-01"}
        self.assertEqual([k for k, _ in ranking.sort_scored(scored, published)], ["d", "b", "c", "a"])

    def test_missing_dates_sort_last_and_input_order_does_not_matter(self):
        published = {"a": None, "b": "2026-01-01"}
        one = ranking.sort_scored([("a", 0.0), ("b", 0.0)], published)
        two = ranking.sort_scored([("b", 0.0), ("a", 0.0)], published)
        self.assertEqual(one, two)
        self.assertEqual(one[0][0], "b")


class BatchUsesFeedbackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(root), data_dir=str(root / "data"))
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app)
        self.addCleanup(self.app.store.close)

    def project(self, keywords):
        return self.app.create_project("P", "manual", keywords)["project_id"]

    def add(self, pid, key, title, abstract="", published="2026-01-01"):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": published}], project_id=pid)

    def test_a_useful_and_an_irrelevant_paper_steer_the_next_batch(self):
        pid = self.project(["photonic crystal waveguide epitaxial graphene substrate"])  # an even mix of two directions
        self.add(pid, "liked", "photonic crystal waveguide", "photonic crystal waveguide fabrication")
        self.add(pid, "disliked", "epitaxial graphene substrate", "epitaxial graphene substrate growth")
        self.add(pid, "cand-a", "photonic crystal waveguide design", "photonic crystal waveguide modes", published="2026-02-01")
        self.add(pid, "cand-b", "epitaxial graphene substrate growth", "epitaxial graphene substrate steps", published="2026-03-01")
        # Without feedback the two candidates are symmetric and the newer one (cand-b) would win the tie.
        self.app.record_feedback("liked", "useful", project_id=pid)
        self.app.record_feedback("disliked", "irrelevant", project_id=pid)
        with mock.patch.object(self.app.gateway, "call", side_effect=AssertionError("no model call")):
            english_papers(self.app, pid)
            steered = self.app.build_batch(limit=1, project_id=pid, exclude_seen=False)["cards"][0]["key"]
        self.assertEqual(steered, "cand-a")

    def test_too_hard_never_steers_away(self):
        pid = self.project(["photonic crystal waveguide epitaxial graphene substrate"])
        self.add(pid, "hard", "epitaxial graphene substrate", "epitaxial graphene substrate growth")
        self.add(pid, "cand-a", "photonic crystal waveguide design", "photonic crystal waveguide modes", published="2026-02-01")
        self.add(pid, "cand-b", "epitaxial graphene substrate growth", "epitaxial graphene substrate steps", published="2026-03-01")

        def relative_order():
            english_papers(self.app, pid)
            keys = [c["key"] for c in self.app.build_batch(limit=3, project_id=pid, exclude_seen=False)["cards"]]
            return [k for k in keys if k.startswith("cand")]
        before = relative_order()
        self.app.record_feedback("hard", "too_hard", project_id=pid)
        self.assertEqual(relative_order(), before)  # difficulty is not disinterest

    def test_an_already_shown_seed_still_counts_toward_the_profile(self):
        pid = self.project([])  # no pinned terms: the seed is the only signal
        self.add(pid, "seedA", "photonic crystal waveguide", "photonic crystal waveguide fabrication")
        self.app.store.add_project_paper(pid, "seedA", "seed")
        self.app.store.conn.execute("INSERT INTO batches(run_date, created_at, source, project_id) VALUES ('2026-01-01','x','t',?)", (pid,))
        batch = self.app.store.conn.execute("SELECT MAX(id) FROM batches").fetchone()[0]
        self.app.store.conn.execute("INSERT INTO exposures(batch_id, paper_key, rank, shown_at) VALUES (?, 'seedA', 1, 'x')", (batch,))
        self.app.store.conn.commit()
        self.add(pid, "cand-a", "photonic crystal waveguide design", "photonic crystal waveguide modes", published="2026-02-01")
        self.add(pid, "cand-b", "unrelated topic entirely", "nothing in common here", published="2026-03-01")
        self.app.store.set_setting(f"seed_keys_{pid}", ["seedA"])
        english_papers(self.app, pid)
        self.assertEqual(self.app.build_batch(limit=1, project_id=pid)["cards"][0]["key"], "cand-a")

    def test_a_chinese_project_ranks_by_chinese_overlap(self):
        pid = self.project(["半导体晶体生长"])
        self.add(pid, "zh-hit", "半导体晶体生长技术研究", "介绍半导体晶体生长的方法", published="2025-01-01")
        self.add(pid, "zh-miss", "古典诗歌的发展脉络", "唐诗宋词的演变", published="2026-01-01")
        # This case tests Chinese lexical ranking, with an explicit Chinese
        # project/report rather than the old synthetic English mislabel.
        self.app.set_project_language(pid, 'humanities', ['zh'])
        self.app.store.conn.execute("UPDATE papers SET metadata_language='zh', metadata_language_source='synthetic Chinese fixture' WHERE key IN ('zh-hit','zh-miss')")
        self.app.store.conn.commit()
        self.assertEqual(self.app.build_batch(limit=1, project_id=pid)["cards"][0]["key"], "zh-hit")

    def test_the_same_inputs_give_the_same_batch(self):
        pid = self.project(["photonic crystal"])
        for i in range(8):
            self.add(pid, f"p{i}", f"paper number {i}", "plain filler words", published=f"2026-01-0{i + 1}")
        english_papers(self.app, pid)
        first = [c["key"] for c in self.app.build_batch(limit=3, project_id=pid, exclude_seen=False)["cards"]]
        english_papers(self.app, pid)
        second = [c["key"] for c in self.app.build_batch(limit=3, project_id=pid, exclude_seen=False)["cards"]]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
