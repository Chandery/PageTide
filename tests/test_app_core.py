import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recommendation_fixtures import english_papers
from app import ranking
from app.db import Store
from app.gateway import BudgetExceeded, Gateway
from app.service import App


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "t.sqlite")
        self.store.init()
        self.addCleanup(self.store.close)

    def _paper(self, key, title="World Model Paper"):
        self.store.upsert_papers([{"key": key, "title": title, "abstract": "latent prediction",
                                   "published": "2026-01-01", "group_name": "field"}])

    def test_papers_batch_and_cards(self):
        self._paper("p1")
        self._paper("p2")
        batch_id = self.store.create_batch("2026-09-11", ["p1", "p2"])
        rows = self.store.batch(batch_id)
        self.assertEqual([r["key"] for r in rows], ["p1", "p2"])
        self.assertEqual(rows[0]["rank"], 1)

    def test_upsert_is_idempotent(self):
        self._paper("p1")
        added = self.store.upsert_papers([{"key": "p1", "title": "World Model Paper"}])
        self.assertEqual(added, 0)
        self.assertEqual(len(self.store.papers()), 1)

    def test_feedback_and_undo(self):
        self._paper("p1")
        fid = self.store.add_feedback("p1", "useful")
        self.assertEqual(self.store.feedback_by_paper()["p1"]["action"], "useful")
        self.store.undo_feedback(fid)
        self.assertEqual(self.store.feedback_by_paper(), {})
        self.assertEqual(len(self.store.feedback(include_undone=True)), 1)

    def test_profile_versions_are_append_only(self):
        self.store.save_profile({"pinned_terms": []}, note="v1")
        self.store.save_profile({"pinned_terms": ["jepa"]}, note="v2")
        versions = self.store.profile_versions()
        self.assertEqual([v["note"] for v in versions], ["v1", "v2"])
        self.assertEqual(self.store.current_profile()["pinned_terms"], ["jepa"])


class RankingTests(unittest.TestCase):
    def test_rocchio_subtracts_negatives(self):
        seed = [ranking.l2_normalize({"world": 1.0, "model": 1.0})]
        pos = [ranking.l2_normalize({"planning": 1.0})]
        neg = [ranking.l2_normalize({"cancer": 1.0})]
        profile = ranking.rocchio(seed, pos, neg, 1.0, 1.0)
        self.assertIn("planning", profile)
        self.assertNotIn("cancer", profile)

    def test_mmr_prefers_diverse_selection(self):
        vectors = {
            "a": {"world": 1.0},
            "b": {"world": 0.99, "x": 0.01},   # near-duplicate of a
            "c": {"robotics": 1.0},            # different but relevant
        }
        scored = [("a", 1.0), ("b", 0.99), ("c", 0.8)]
        chosen = ranking.mmr_select(scored, vectors, 2, lambda_=0.5)
        self.assertEqual(chosen[0], "a")
        self.assertEqual(chosen[1], "c")

    def test_mmr_is_deterministic(self):
        vectors = {"a": {"x": 1.0}, "b": {"y": 1.0}, "c": {"z": 1.0}}
        scored = [("a", 1.0), ("b", 1.0), ("c", 1.0)]
        self.assertEqual(ranking.mmr_select(scored, vectors, 3),
                         ranking.mmr_select(scored, vectors, 3))


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_dry_run_reserves_without_network(self):
        gateway = Gateway(root=".", ledger=Path(self.tmp.name) / "usage.jsonl")
        result = gateway.call("daily_triage", [], dry_run=True)
        self.assertTrue(result["ok"]) if result.get("ok") else None
        if result.get("ok"):
            self.assertEqual(result["operation"], "daily_triage")
            self.assertIn("reservation", result)

    def test_dev_mode_uses_separate_ledger_and_loose_limits(self):
        from app.gateway import DEV_LEDGER, DEV_POLICY, Gateway
        runtime = Gateway(root=".", ledger=Path(self.tmp.name) / "runtime.jsonl", dev=False)
        dev = Gateway(root=".", ledger=Path(self.tmp.name) / "runtime.jsonl", dev=True)
        self.assertEqual(runtime.ledger.name, "runtime.jsonl")
        self.assertEqual(dev.ledger, Path(".") / DEV_LEDGER)
        self.assertFalse(runtime.limits()['aggregate_limits_enabled'])
        self.assertIsNone(runtime.limits()["daily_total_tokens"])
        self.assertTrue(dev.limits()['aggregate_limits_enabled'])
        self.assertEqual(dev.limits()["daily_total_tokens"], DEV_POLICY["daily_total_tokens"])
        self.assertGreater(dev.limits()["daily_total_tokens"], runtime.config["policy"]["daily_total_tokens"])
        self.assertNotEqual(dev.ledger, runtime.ledger)

    def test_unregistered_operation_is_rejected(self):
        gateway = Gateway(root=".", ledger=Path(self.tmp.name) / "usage.jsonl")
        result = gateway.call("not_registered", [], dry_run=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["degraded"])

    def test_operation_without_owner_approval_is_forced_to_local_mode(self):
        gateway = Gateway(root=".", ledger=Path(self.tmp.name) / "usage.jsonl")
        gateway.config["operations"]["project_guidance"] = {
            **gateway.config["operations"]["project_guidance"], "owner_approved": False}
        result = gateway.call("project_guidance", [], dry_run=True)
        self.assertFalse(result["ok"])
        self.assertIn("owner approval", result["reason"])

    def test_owner_approved_project_guidance_is_admitted(self):
        gateway = Gateway(root=".", ledger=Path(self.tmp.name) / "usage.jsonl")
        self.assertIs(gateway.config["operations"]["project_guidance"]["owner_approved"], True)
        result = gateway.call("project_guidance", [], dry_run=True)
        if not result["ok"]:  # AI switch or provider config may degrade, never the approval gate
            self.assertNotIn("owner approval", result["reason"])


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=".", data_dir=Path(self.tmp.name) / "app")
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=False)
        self.app.store.upsert_papers([
            {"key": "p1", "title": "World Model Planning", "abstract": "latent planning",
             "published": "2026-08-01", "group_name": "field"},
            {"key": "p2", "title": "Cancer Biomarker Study", "abstract": "clinical trial",
             "published": "2026-08-02", "group_name": "distractor"},
        ])

    def test_too_hard_does_not_change_interest(self):
        result = self.app.record_feedback("p1", "too_hard")
        self.assertFalse(result["interest_changed"])
        profile = self.app.profile()
        self.assertIn("p1", profile["too_hard_feedback"])
        self.assertNotIn("p1", profile["positive_feedback"])

    def test_understood_is_familiarity_not_interest_and_needs_a_saved_paper(self):
        with self.assertRaisesRegex(ValueError, "先收藏"):
            self.app.record_feedback("p1", "understood")
        self.app.store.save_to_library("p1", project_id=self.app.get_default_project_id())
        result = self.app.record_feedback("p1", "understood")
        self.assertFalse(result["interest_changed"])
        self.assertFalse(result["saved"])   # this call saved nothing itself
        profile = self.app.profile()
        self.assertNotIn("p1", profile["positive_feedback"] + profile["explicit_negatives"] + profile["too_hard_feedback"])
        self.assertEqual(self.app.stats()["understood"], 1)

    def test_a_mistaken_understood_can_be_taken_back_even_when_recorded_twice(self):
        pid = self.app.get_default_project_id()
        self.app.store.save_to_library("p1", project_id=pid)
        self.app.record_feedback("p1", "useful")
        first = self.app.record_feedback("p1", "understood")["feedback_id"]
        self.app.store.conn.execute('INSERT INTO feedback(paper_key,action,reason,created_at,project_id) VALUES (?,?,?,?,?)',
                                    ("p1", "understood", None, "2099-01-01T00:00:00+00:00", pid))   # a second record (map reconfirmation)
        self.app.store.conn.commit()
        out = self.app.retract_feedback("p1", "understood", pid)
        self.assertIn(first, out["retracted"]); self.assertEqual(len(out["retracted"]), 2)
        entry = self.app.latest_feedback(pid)["p1"]
        self.assertIsNone(entry.get("familiar"))
        self.assertEqual(entry["action"], "useful")                  # the interest label stays
        self.assertEqual(self.app.stats()["understood"], 0)
        self.assertEqual(self.app.retract_feedback("p1", "understood", pid)["retracted"], [])   # nothing left: no error
        with self.assertRaisesRegex(ValueError, "只能取消"):
            self.app.retract_feedback("p1", "useful", pid)

    def test_taking_back_understood_restores_the_state_before_it_and_touches_nothing_else(self):
        pid = self.app.get_default_project_id()
        other = self.app.create_project("Other")["project_id"]
        for project in (pid, other):
            self.app.store.save_to_library("p1", project_id=project)
            self.app.store.conn.execute("INSERT OR IGNORE INTO project_papers(project_id,paper_key) VALUES (?,?)", (project, "p1"))
        self.app.store.conn.commit()
        self.app.record_feedback("p1", "too_hard", project_id=pid)
        self.app.record_feedback("p1", "understood", project_id=pid)
        self.app.record_feedback("p1", "understood", project_id=other)
        self.app.retract_feedback("p1", "understood", pid)
        self.assertEqual(self.app.latest_feedback(pid)["p1"]["familiar"]["action"], "too_hard")   # the press before comes back
        self.assertEqual(self.app.latest_feedback(other)["p1"]["familiar"]["action"], "understood")   # other project untouched
        with self.assertRaisesRegex(ValueError, "不属于当前项目"):
            self.app.retract_feedback("no-such-paper", "understood", pid)
        with self.assertRaisesRegex(ValueError, "不属于当前项目"):
            self.app.retract_feedback("p1", "understood", "missing-project")

    def test_after_a_learning_map_revision_one_press_confirms_the_mark_anew(self):
        pid = self.app.get_default_project_id()
        self.app.store.save_to_library("p1", project_id=pid)
        first = self.app.record_feedback("p1", "understood", project_id=pid)["feedback_id"]
        with mock.patch.object(self.app, "_route_reconfirmation_needed", return_value=True):
            out = self.app.retract_feedback("p1", "understood", pid)
        self.assertTrue(out["reconfirmed"]); self.assertEqual(out["retracted"], [])
        self.assertNotEqual(out["feedback_id"], first)                    # a fresh record the map counts again
        self.assertEqual(self.app.latest_feedback(pid)["p1"]["familiar"]["action"], "understood")

    def test_a_familiarity_label_does_not_replace_an_interest_label(self):
        self.app.record_feedback("p1", "useful")
        self.app.record_feedback("p1", "too_hard")
        self.app.record_feedback("p1", "understood")
        entry = self.app.latest_feedback()["p1"]
        self.assertEqual((entry["action"], entry["familiar"]["action"]), ("useful", "understood"))
        self.assertIn("p1", self.app.profile()["positive_feedback"])

    def test_irrelevant_is_explicit_negative(self):
        result = self.app.record_feedback("p2", "irrelevant")
        self.assertTrue(result["interest_changed"])
        self.assertIn("p2", self.app.profile()["explicit_negatives"])

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            self.app.record_feedback("p1", "hate")

    def test_build_batch_excludes_seen_and_feedback(self):
        english_papers(self.app, None)
        first = self.app.build_batch(limit=2)
        self.assertEqual(len(first["cards"]), 2)
        english_papers(self.app, None)
        second = self.app.build_batch(limit=2)
        self.assertEqual(second["cards"], [])  # everything already exposed

    def test_cards_have_reason_and_url(self):
        english_papers(self.app, None)
        self.app.build_batch(limit=1)
        card = self.app.cards()[0]
        self.assertTrue(card["why"])
        self.assertEqual(card["mode"], "sparse")

    def test_pinned_terms_are_used(self):
        data = self.app.store.current_profile() or {"project": "world-models", "weights": {"pos": 1.0, "neg": 0.5}}
        data["pinned_terms"] = ["planning"]
        self.app.save_profile(data, note="pin")
        self.assertEqual(self.app.profile()["pinned_terms"], ["planning"])

    def test_useful_saves_to_library_and_card_stays(self):
        english_papers(self.app, None)
        self.app.build_batch(limit=2)
        cards = self.app.cards()
        self.assertEqual(len(cards), 2)
        key = cards[0]["key"]
        result = self.app.record_feedback(key, "useful")
        self.assertTrue(result["saved"])
        self.assertEqual(len(self.app.library()), 1)
        # The card must remain visible and marked as saved, not vanish.
        self.assertEqual(len(self.app.cards()), 2)
        self.assertTrue(next(c for c in self.app.cards() if c["key"] == key)["saved"])
        # Saving twice is idempotent.
        self.app.record_feedback(key, "useful")
        self.assertEqual(len(self.app.library()), 1)

    def test_unsave_removes_from_library(self):
        english_papers(self.app, None)
        self.app.build_batch(limit=1)
        key = self.app.cards()[0]["key"]
        self.app.record_feedback(key, "useful")
        self.app.unsave(key)
        self.assertEqual(self.app.library(), [])

    def test_feedback_does_not_remove_card_from_view(self):
        english_papers(self.app, None)
        self.app.build_batch(limit=2)
        for card in self.app.cards():
            self.app.record_feedback(card["key"], "irrelevant")
        self.assertEqual(len(self.app.cards()), 2)

    def test_explain_is_specific_and_names_a_reference(self):
        # Explicit useful feedback becomes an interest reference; saving alone is inventory.
        self.app.store.upsert_papers([{"key": "ref1", "title": "World Model Planning with JEPA",
                                       "abstract": "latent prediction and planning for robotics",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.record_feedback("ref1", "useful")
        explanation = self.app.explain({"title": "Zero-shot planning with a world model",
                                        "abstract": "latent prediction enables planning",
                                        "topic": "Robotics"})
        self.assertTrue(explanation["why"])
        self.assertIn("有用反馈论文《World Model Planning with JEPA》", explanation["nearest_reference"] or "")
        self.assertTrue(explanation["shared_terms"])
        self.assertIn("领域：Robotics", explanation["why"])

    def test_qa_parses_answer_and_followups(self):
        import json as _json
        class FakeGateway:
            def call(self, op, messages, dry_run=False):
                return {"ok": True, "content": _json.dumps(
                    {"answer": "**答**案", "followups": ["q1", "q2", "q3", "q4"]}),
                    "usage": {"total_tokens": 10}, "usd": "0.0001", "model": "fake"}
        self.app.gateway = FakeGateway()
        result = self.app.qa("p1", "这篇讲什么？")
        self.assertTrue(result["ok"])
        self.assertEqual(result["answer"], "**答**案")
        self.assertEqual(result["followups"], ["q1", "q2", "q3"])  # capped at three
        self.assertEqual([h["role"] for h in self.app.qa_history("p1")], ["user", "assistant"])

    def test_qa_falls_back_to_raw_text_without_json(self):
        class FakeGateway:
            def call(self, op, messages, dry_run=False):
                return {"ok": True, "content": "纯文本回答", "usage": {"total_tokens": 5},
                        "usd": "0.00005", "model": "fake"}
        self.app.gateway = FakeGateway()
        result = self.app.qa("p1", "问")
        self.assertTrue(result["ok"])
        self.assertEqual(result["answer"], "纯文本回答")
        self.assertEqual(result["followups"], [])

    def test_qa_dry_run_records_no_history(self):
        result = self.app.qa("p1", "问", dry_run=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["degraded"])
        self.assertEqual(self.app.qa_history("p1"), [])

    def test_fulltext_cache_and_retrieval(self):
        key = "ft1"
        self.app.store.upsert_papers([{"key": key, "title": "World Model Paper", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.save_fulltext(key, [
            {"page": 1, "text": "Introduction. " + "filler " * 40},
            {"page": 2, "text": "Figure 2 shows the latent prediction pipeline with a JEPA encoder. " + "x " * 40},
            {"page": 3, "text": "Experiments on robot manipulation tasks. " + "y " * 40},
        ])
        status = self.app.fulltext_status(key)
        self.assertEqual(status["pages"], 3)
        hits = self.app.passages(key, "what does figure 2 show about the jepa encoder?", k=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["page"], 2)

    def test_caption_passages_anchor_on_the_figure_number(self):
        key = "cap1"
        self.app.store.upsert_papers([{"key": key, "title": "T", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.save_fulltext(key, [
            {"page": 2, "text": "Introduction. " + "filler " * 40},
            {"page": 6, "text": "Figure 3: GigaBrain-0 self-collected real-world robot data. " + "x " * 200},
            {"page": 7, "text": "Figure 4: something else entirely. " + "y " * 200},
        ])
        hits = self.app.caption_passages(key, "这篇论文的 Figure 3 展示了什么？")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["page"], 6)
        self.assertIn("Figure 3", hits[0]["text"])
        self.assertEqual(self.app.caption_passages(key, "没有图号的问题"), [])

    def test_figure_page_prefers_caption_over_body_references(self):
        key = "fig1"
        self.app.store.upsert_papers([{"key": key, "title": "T", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.save_fulltext(key, [
            {"page": 3, "text": "As shown in Figure 8 and Figure 9, the results improve. Figure 8 also compares baselines. " * 3},
            {"page": 11, "text": "Figure 8: Robot execution processes for real-world tasks. " + "x " * 60},
            {"page": 12, "text": "Figure 9: Illustration of compositional generalization. " + "y " * 60},
            {"page": 20, "text": "Some text mentioning Figure 8 once more."},
        ])
        self.assertEqual(self.app.figure_page(key, "这篇论文的 Figure 8 展示了什么？"), 11)
        self.assertEqual(self.app.figure_page(key, "Figure 9 讲的是什么？"), 12)
        self.assertIsNone(self.app.figure_page(key, "Figure 42 呢？"))
        self.assertIsNone(self.app.figure_page(key, "没有图号的问题"))

    def test_figure_page_handles_mid_line_captions_and_fallback(self):
        key = "fig2"
        self.app.store.upsert_papers([{"key": key, "title": "T", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.save_fulltext(key, [
            {"page": 2, "text": "intro text " + "f " * 40},
            {"page": 5, "text": "Some prose. Figure 7: describes the pipeline in detail. " + "z " * 40},
        ])
        self.assertEqual(self.app.figure_page(key, "Figure 7 是什么？"), 5)

    def test_passages_empty_without_fulltext(self):
        self.assertEqual(self.app.passages("nope", "anything"), [])

    def test_qa_reports_mode_pages_and_uses_vision_operation(self):
        import json as _json
        seen = {}
        class FakeGateway:
            def call(self, op, messages, dry_run=False):
                seen["op"] = op
                seen["messages"] = messages
                return {"ok": True, "content": _json.dumps({"answer": "A", "followups": ["f1"]}),
                        "usage": {"total_tokens": 1}, "usd": "0", "model": "fake"}
        self.app.gateway = FakeGateway()
        key = "v1"
        self.app.store.upsert_papers([{"key": key, "title": "T", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.save_fulltext(key, [{"page": 4, "text": "Figure 4 shows the pipeline. " + "z " * 60}])
        text_mode = self.app.qa(key, "explain the method")
        self.assertEqual(text_mode["mode"], "text")
        self.assertEqual(seen["op"], "paper_qa")
        self.assertIn(4, text_mode["pages"])
        vision = self.app.qa(key, "what is in figure 4?", image="data:image/jpeg;base64,AAAA", page_hint=4)
        self.assertEqual(vision["mode"], "vision")
        self.assertEqual(seen["op"], "paper_vision_qa")
        parts = seen["messages"][-1]["content"]
        self.assertIsInstance(parts, list)
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertEqual(parts[1]["image_url"]["url"], "data:image/jpeg;base64,AAAA")
        self.assertIn("附有论文页面图片", seen["messages"][0]["content"])
        self.app.qa(key, "explain the method")
        self.assertNotIn("附有论文页面图片", seen["messages"][0]["content"])

    def test_chinese_numeral_figure_references_resolve(self):
        # The owner asked "图二讲了什么？": a Chinese numeral must find Figure 2 like "图2" does.
        for question, number in [("图二讲了什么？", 2), ("你看一下图二这个图片", 2), ("第三张图", 3),
                                 ("表十二的结果", 12), ("Fig. 3a", 3), ("Eq. (4)", 4), ("图 21", 21)]:
            self.assertEqual(self.app.figure_number(question), number, question)
        for question in ["试图解决什么问题", "图像生成效果", "这表明了什么", "图神经网络", "二十一"]:
            self.assertIsNone(self.app.figure_number(question), question)
        # Review findings: English labels glued to Chinese text, and compound words that only
        # look like a label or a count that only looks like a number.
        for question, ref in [("解释一下Figure 2", ("figure", 2)), ("看一下Figure2", ("figure", 2)),
                              ("图一中的箭头", ("figure", 1)), ("第一个表格", ("table", 1))]:
            self.assertEqual(self.app.figure_ref(question), ref, question)
        for question in ["这个向量代表一个token吗", "发表一篇", "试图一次性解决", "第一个表示方法",
                         "把这些图一起看", "列表三项"]:
            self.assertIsNone(self.app.figure_ref(question), question)
        key = "cn1"
        self.app.store.upsert_papers([{"key": key, "title": "T", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.save_fulltext(key, [{"page": 1, "text": "As shown in Figure 2, we train."},
                                     {"page": 3, "text": "Figure 2: Data composition and pipeline."}])
        self.assertEqual(self.app.figure_page(key, "图二讲了什么？"), 3)
        captions = self.app.caption_passages(key, "图二讲了什么？")
        self.assertTrue(any(c["page"] == 3 for c in captions))

    def test_figure_page_never_takes_a_table_caption_for_a_figure(self):
        # Shaped like the owner's Zero-WAM PDF: "Figure 2" resolved to the page with the
        # "Table 2" caption, and the real caption was glued to the previous word.
        key = "zw"
        self.app.store.upsert_papers([{"key": key, "title": "T", "abstract": "a",
                                       "published": "2026-08-01", "group_name": "field"}])
        self.app.save_fulltext(key, [
            {"page": 2, "text": "for pretraining. Figure 2 summarizes the resulting data composition."},
            {"page": 3, "text": "Real-world ICL (Section 2.3). Figure 2 summarizes this data"},
            {"page": 4, "text": "RobotwinFigure 2 Data construction and in-context human video generation.\n"
                                "The bottom part of Figure 2 shows the pipeline."},
            {"page": 9, "text": "A Stable 2 baseline is reported in figure 3."},
            {"page": 11, "text": "Results\nTable 2 Zero-shot cross-task results on seven unseen tasks."},
        ])
        for question in ["图二讲了什么？", "Figure 2", "第二张图", "fig. 2 的箭头"]:
            self.assertEqual(self.app.figure_page(key, question), 4, question)
        self.assertEqual(self.app.figure_page(key, "表二的结果"), 11)
        self.assertEqual(self.app.figure_page(key, "Table 2"), 11)
        self.assertEqual(self.app.caption_passages(key, "图二讲了什么？")[0]["page"], 4)
        self.assertFalse(any(c["page"] == 11 for c in self.app.caption_passages(key, "Figure 2")))

    def test_qa_rejects_an_image_that_is_not_a_local_page_render(self):
        class Never:
            def call(self, *a, **k):
                raise AssertionError("must not reach the gateway")
        self.app.gateway = Never()
        for image in ["https://example.com/x.png", "data:text/html;base64,AAAA", "data:image/jpeg;base64,AA AA", 42]:
            with self.assertRaises(ValueError):
                self.app.qa(None, "这张图是什么？", image=image)

    def test_cards_have_distinct_reasons(self):
        english_papers(self.app, None)
        self.app.build_batch(limit=2)
        cards = self.app.cards()
        self.assertTrue(all(c["why"] for c in cards))


if __name__ == "__main__":
    unittest.main()
