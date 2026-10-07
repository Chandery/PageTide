"""The weekly report says what moved in which direction, not only how many things were saved. Everything is a
count of the person's own explicit records in two UTC windows; a quiet direction is never read as lost interest."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.organization import Organization
from app.service import App
from app.weekly_report import generate_weekly_report

PLAN = {"concepts": [
    {"id": "a", "name": "Crystal basics", "terms": ["crystal growth"], "hint": 1, "needs": []},
    {"id": "b", "name": "Epitaxy", "terms": ["epitaxy"], "hint": 2, "needs": ["a"]}], "targets": ["b"]}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("Crystals", "manual", ["epitaxy"])["project_id"]
        self.org = Organization(self.app.store, project="default")
        self.today = datetime.now(timezone.utc)

    def paper(self, key, title, abstract="", published="2026-01-01"):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": published}], project_id=self.pid)

    def direction(self, name, parent=None):
        body = {"action": "direction-save", "name": name, "color": "#3366aa", **({"parent_id": parent} if parent else {})}
        return self.org.action(body)["directions"][-1]["id"]

    def put(self, keys, direction):
        for key in keys:
            self.app.store.save_to_library(key, project_id=self.pid)
        self.org.action({"action": "membership", "keys": keys, "add": [direction]})
        old = (self.today - timedelta(days=60)).isoformat()   # filed long ago: only what the test then does is "this week"
        for key in keys:
            self.app.store.conn.execute("UPDATE project_library SET saved_at=? WHERE paper_key=? AND project_id=?", (old, key, self.pid))
        self.app.store.conn.commit()

    def say(self, key, action, days_ago=0):
        if action == "understood" and not self.app.store.in_library(key, self.pid):
            # "understood" needs a saved paper; it was filed long ago so the save is not this week's record
            self.app.store.save_to_library(key, project_id=self.pid)
            self.app.store.conn.execute("UPDATE project_library SET saved_at=? WHERE paper_key=? AND project_id=?",
                                        ((self.today - timedelta(days=60)).isoformat(), key, self.pid))
            self.app.store.conn.commit()  # Finish fixture setup before the feedback service owns its transaction.
        self.app.record_feedback(key, action, project_id=self.pid)
        stamp = (self.today - timedelta(days=days_ago)).isoformat()
        self.app.store.conn.execute("UPDATE feedback SET created_at=? WHERE id=(SELECT MAX(id) FROM feedback)", (stamp,))
        if action == "useful":
            self.app.store.conn.execute("UPDATE project_library SET saved_at=? WHERE paper_key=? AND project_id=?", (stamp, key, self.pid))
        self.app.store.conn.commit()

    def report(self):
        return generate_weekly_report(self.pid, self.app)

    def direction_row(self, report, name):
        return next(d for d in report["directions"] if d["name"] == name)


class DirectionTests(Fixture):
    def setUp(self):
        super().setUp()
        self.models = self.direction("World models")
        self.sub = self.direction("Latent dynamics", parent=self.models)
        self.vision = self.direction("Vision")
        for key in ("m1", "m2", "m3", "l1", "v1", "v2"):
            self.paper(key, f"Paper {key}", "text")
        self.put(["m1", "m2", "m3"], self.models)
        self.put(["l1"], self.sub)
        self.put(["v1", "v2"], self.vision)

    def test_each_direction_gets_this_weeks_and_last_weeks_explicit_records(self):
        self.say("m1", "useful"); self.say("m2", "understood"); self.say("m3", "irrelevant")
        self.say("v1", "useful", days_ago=9); self.say("v2", "useful", days_ago=9)
        report = self.report()
        models = self.direction_row(report, "World models")
        self.assertEqual((models["current"]["positive"], models["current"]["understood"], models["current"]["negative"]), (1, 1, 1))
        self.assertEqual(models["current"]["papers"], 3)
        vision = self.direction_row(report, "Vision")
        self.assertEqual((vision["current"]["papers"], vision["previous"]["positive"]), (0, 2))

    def test_a_subdirectory_is_named_with_its_path(self):
        self.say("l1", "useful")
        names = [d["name"] for d in self.report()["directions"]]
        self.assertIn("World models / Latent dynamics", names)

    def test_status_words_never_say_the_person_lost_interest(self):
        self.say("m1", "useful")                                   # new this week
        self.say("v1", "useful", days_ago=9)                       # last week only
        report = self.report()
        self.assertEqual(self.direction_row(report, "World models")["status"], "new")
        self.assertEqual(self.direction_row(report, "Vision")["status"], "quiet")
        statuses = {d["status"] for d in report["directions"]}
        self.assertTrue(statuses <= {"new", "more", "same", "fewer", "quiet", "other"})

    def test_a_week_with_only_a_not_relevant_record_is_not_called_quiet(self):
        self.say("v1", "useful", days_ago=9); self.say("v2", "useful", days_ago=9)
        self.say("v1", "irrelevant")                               # this week: one record, not a positive one
        row = self.direction_row(self.report(), "Vision")
        self.assertEqual(row["status"], "other")                   # "no record this week" would be false: there is one
        self.assertEqual(row["current"]["papers"], 1)

    def test_more_than_last_week_is_more_and_less_is_fewer(self):
        self.say("m1", "useful"); self.say("m2", "useful")
        self.say("m3", "useful", days_ago=9)
        self.say("v1", "useful"); self.say("v2", "useful", days_ago=9); self.say("m3", "understood", days_ago=9)
        report = self.report()
        self.assertEqual(self.direction_row(report, "World models")["status"], "more")
        self.assertEqual(self.direction_row(report, "Vision")["status"], "same")

    def test_the_papers_behind_a_direction_are_listed_with_what_happened(self):
        self.say("m1", "useful"); self.say("m1", "understood")
        row = self.direction_row(self.report(), "World models")
        self.assertEqual([(p["key"], p["title"], sorted(p["kinds"])) for p in row["papers"]], [("m1", "Paper m1", ["positive", "saved", "understood"])])

    def test_papers_outside_every_direction_are_reported_as_unsorted(self):
        self.paper("loose", "A loose paper", "text")
        self.say("loose", "useful")
        self.assertIn("未分类", [d["name"] for d in self.report()["directions"]])

    def test_a_week_without_records_has_no_directions_and_no_conclusion_about_interest(self):
        report = self.report()
        self.assertEqual(report["directions"], [])
        self.assertFalse(report["has_activity"])

    def test_the_profile_page_and_the_report_page_get_the_same_detail(self):
        self.say("m1", "useful")
        insights = self.app.profile_insights(self.pid)["weekly_change"]
        self.assertEqual(insights["directions"], self.report()["directions"])
        self.assertIn("daily", insights)

    def test_another_projects_paper_in_the_shared_tree_is_not_listed(self):
        other = self.app.create_project("Poetry", "manual", ["poetry"])["project_id"]
        self.app.store.upsert_papers([{"key": "po", "title": "Poem", "abstract": "x", "published": "2026-01-01"}], project_id=other)
        self.app.store.save_to_library("po", project_id=other)
        self.org.action({"action": "membership", "keys": ["po"], "add": [self.vision]})   # the category tree is shared
        self.app.record_feedback("po", "useful", project_id=other)
        self.say("v1", "useful")
        row = self.direction_row(self.report(), "Vision")
        self.assertEqual([p["key"] for p in row["papers"]], ["v1"])
        self.assertEqual(row["current"]["papers"], 1)

    def test_a_database_without_the_library_tables_still_gives_a_report(self):
        self.say("m1", "useful")
        for table in ("org_events", "org_notes", "org_drafts", "org_projects"):
            self.app.store.conn.execute(f"DROP TABLE IF EXISTS {table}")
        self.app.store.conn.commit()
        report = self.report()
        self.assertEqual([d["name"] for d in report["directions"]], ["未分类"])

    def test_a_membership_pointing_at_a_deleted_category_does_not_break_the_report(self):
        self.say("m1", "useful")
        revision, data = self.org._load()
        data["memberships"]["m1"] = ["no-such-category"]
        self.app.store.conn.execute("UPDATE org_projects SET data=? WHERE project='default'", (json.dumps(data),))
        self.app.store.conn.commit()
        self.assertEqual([d["name"] for d in self.report()["directions"]], ["未分类"])

    def test_more_than_twelve_directions_are_cut_but_still_counted(self):
        for i in range(14):
            did = self.direction(f"Extra {i}")
            self.paper(f"e{i}", f"Extra paper {i}", "text")
            self.put([f"e{i}"], did)
            self.say(f"e{i}", "useful")
        report = self.report()
        self.assertEqual(len(report["directions"]), 12)
        self.assertEqual(report["more_directions"], 2)
        self.assertEqual(report["highlights"]["directions"], 14)

    def test_the_other_projects_records_are_not_counted(self):
        other = self.app.create_project("Poetry", "manual", ["poetry"])["project_id"]
        self.app.store.upsert_papers([{"key": "po", "title": "Poem", "abstract": "x", "published": "2026-01-01"}], project_id=other)
        self.app.record_feedback("po", "useful", project_id=other)
        self.assertEqual(self.report()["directions"], [])


class DailyAndHighlightTests(Fixture):
    def setUp(self):
        super().setUp()
        d = self.direction("Models")
        for key in ("a", "b", "c"):
            self.paper(key, f"Paper {key}", "text")
        self.put(["a", "b", "c"], d)

    def test_seven_days_with_a_count_per_kind(self):
        self.say("a", "useful", days_ago=0); self.say("b", "understood", days_ago=2); self.say("c", "irrelevant", days_ago=2)
        days = self.report()["daily"]
        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1]["positive"], 1)
        self.assertEqual((days[-3]["understood"], days[-3]["negative"]), (1, 1))
        self.assertEqual([d["date"] for d in days], sorted(d["date"] for d in days))
        self.assertTrue(all(0 <= d["weekday"] <= 6 for d in days))

    def test_a_paper_rated_useful_and_then_not_relevant_counts_once_as_not_relevant(self):
        self.say("a", "useful"); self.say("a", "irrelevant")
        h = self.report()["highlights"]
        self.assertEqual((h["positive"], h["negative"], h["judged"]), (0, 1, 1))

    def test_highlights_count_papers_and_directions_and_the_explicit_rate(self):
        self.say("a", "useful"); self.say("b", "useful"); self.say("c", "irrelevant")
        h = self.report()["highlights"]
        self.assertEqual((h["papers"], h["directions"]), (3, 1))
        self.assertEqual((h["judged"], h["positive"], h["negative"]), (3, 2, 1))

    def test_this_weeks_picks_name_their_direction(self):
        self.say("a", "useful"); self.say("b", "understood"); self.say("c", "too_hard")
        picks = self.report()["picks"]
        self.assertEqual(sorted(p["key"] for p in picks), ["a", "b"])   # too hard is not a pick
        self.assertEqual({p["directions"][0] for p in picks}, {"Models"})

    def test_an_exposed_but_untouched_paper_is_counted_as_seen_not_as_rejected(self):
        self.app.store.conn.execute("INSERT INTO batches (run_date, created_at, source, project_id) VALUES (?,?,?,?)", (self.today.date().isoformat(), self.today.isoformat(), "test", self.pid))
        batch = self.app.store.conn.execute("SELECT MAX(id) FROM batches").fetchone()[0]
        self.app.store.conn.execute("INSERT INTO exposures (batch_id, paper_key, rank, shown_at) VALUES (?,?,?,?)", (batch, "c", 1, self.today.isoformat()))
        self.app.store.conn.commit()
        self.say("a", "useful")
        h = self.report()["highlights"]
        self.assertEqual(h["seen"], 1)
        self.assertEqual(h["negative"], 0)


class LearningMapTests(Fixture):
    def setUp(self):
        super().setUp()
        self.paper("c1", "Crystal growth basics", "crystal growth")
        self.paper("c2", "More crystal growth", "crystal growth")
        self.paper("e1", "Epitaxy intro", "epitaxy")
        self.paper("x", "Nothing relevant", "poetry")

    def test_without_a_map_there_are_no_units(self):
        self.say("c1", "understood")
        report = self.report()
        self.assertIsNone(report["units"])

    def test_units_show_this_weeks_evidence_and_the_overall_progress(self):
        self.app.route_save(self.pid, plan=PLAN)
        self.say("c1", "understood"); self.say("c2", "understood"); self.say("e1", "useful"); self.say("x", "useful")
        report = self.report()
        units = {u["name"]: u for u in report["units"]["items"]}
        self.assertEqual((units["Crystal basics"]["current"]["understood"], units["Crystal basics"]["status"]), (2, "satisfied"))
        self.assertEqual(units["Epitaxy"]["current"]["positive"], 1)
        self.assertEqual((report["units"]["done"], report["units"]["total"]), (1, 2))
        self.assertEqual(report["units"]["advanced"], ["Crystal basics"])

    def test_a_map_that_is_switched_off_is_reported_as_off_with_its_progress(self):
        self.app.route_save(self.pid, plan=PLAN)
        self.app.route_mode(self.pid, "off")
        self.say("c1", "understood")
        units = self.report()["units"]
        self.assertEqual(units["enabled"], False)
        self.assertEqual(units["advanced"], ["Crystal basics"])

    def test_an_unreadable_stored_map_leaves_the_report_without_a_unit_section(self):
        self.app.route_save(self.pid, plan=PLAN)
        revision, data = self.app._route_org(self.pid)._load()
        data["route"]["graph"] = {"concepts": [{"id": "x"}], "prereqs": [], "targets": []}   # a concept without a name
        self.app.store.conn.execute("UPDATE org_projects SET data=? WHERE project=?", (json.dumps(data), self.pid))
        self.app.store.conn.commit()
        self.say("c1", "useful")
        report = self.report()
        self.assertIsNone(report["units"])
        self.assertTrue(report["has_activity"])

    def test_the_route_is_only_matched_for_papers_that_had_a_record_this_week(self):
        self.app.route_save(self.pid, plan=PLAN)
        from unittest import mock
        from app import pathgrowth
        seen = []
        real = pathgrowth.assign
        def spy(graph, papers):
            seen.append(sorted(p["key"] for p in papers)); return real(graph, papers)
        with mock.patch.object(pathgrowth, "assign", spy):
            self.say("c1", "understood")
            seen.clear()
            self.report()
        self.assertIn(["c1"], seen)   # the weekly pass matched only the paper with a record

    def test_saving_alone_does_not_advance_a_unit(self):
        self.app.route_save(self.pid, plan=PLAN)
        self.say("c1", "useful"); self.say("c2", "useful")
        self.assertEqual(self.report()["units"]["advanced"], [])

    def test_a_unit_with_nothing_this_week_is_listed_without_a_verdict(self):
        self.app.route_save(self.pid, plan=PLAN)
        self.say("c1", "understood")
        units = {u["name"]: u for u in self.report()["units"]["items"]}
        self.assertEqual(units["Epitaxy"]["current"]["understood"], 0)
        self.assertTrue({u["status"] for u in self.report()["units"]["items"]} <= {"satisfied", "unlocked", "locked"})


if __name__ == "__main__":
    unittest.main()
