"""Folders become categories: one undo step, nothing existing is removed or renamed, copies in two folders are in both.

The category tree is shared by all projects (Organization project "default"), so reuse by name at the same level
matters: importing a second library must not create a second "强化学习"."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.db import Store
from app.library_import import LibraryImport
from app.organization import Conflict, Organization
from app.project import ProjectManager
from tests.library_import_fixtures import pdf


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "db.sqlite")
        self.store.init()
        self.project = ProjectManager(self.store).create_project("导入测试")
        self.org = Organization(self.store, project="default")
        for key in ("a", "b", "c"):
            self.store.upsert_papers([{"key": key, "title": f"Paper {key}"}], project_id=self.project)
            self.store.save_to_library(key, project_id=self.project)

    def apply(self, groups, **extra):
        return self.org.action({"op": "import-categories", "groups": groups, **extra})

    def tree(self):
        snap = self.org.action({"op": "export"})
        names = {d["id"]: d for d in snap["directions"]}

        def path(direction):
            parent = names.get(direction.get("parent_id"))
            return (path(parent) if parent else []) + [direction["name"]]
        return {tuple(path(d)): d["id"] for d in snap["directions"]}, snap

    def membership(self, key):
        _, snap = self.tree()
        by_id = {d["id"]: d["name"] for d in snap["directions"]}
        return sorted(by_id[i] for i in next(p for p in snap["items"] if p["key"] == key)["directions"])


class ImportCategoriesOpTests(Base):
    def test_nested_folders_become_nested_categories_with_papers_at_the_leaf(self):
        result = self.apply([{"path": ["机器人", "强化学习"], "keys": ["a"]}, {"path": ["机器人"], "keys": ["b"]}])
        tree, _ = self.tree()
        self.assertEqual(set(tree), {("机器人",), ("机器人", "强化学习")})
        self.assertEqual(self.membership("a"), ["强化学习"])
        self.assertEqual(self.membership("b"), ["机器人"])
        self.assertEqual(self.membership("c"), [])
        self.assertEqual((result["apply_result"]["created_categories"], result["apply_result"]["added_memberships"]), (2, 2))

    def test_the_whole_import_is_one_named_undo_step(self):
        self.apply([{"path": ["A", "B"], "keys": ["a"]}, {"path": ["C"], "keys": ["b"]}])
        snap = self.org.action({"op": "export"})
        self.assertEqual(snap["undo"]["label"], "导入分类")
        self.org.action({"op": "undo", "event": snap["undo"]["id"]})
        tree, snap = self.tree()
        self.assertEqual(tree, {})
        self.assertEqual([p["directions"] for p in snap["items"]], [[], [], []])

    def test_an_existing_category_of_the_same_name_at_the_same_level_is_reused(self):
        existing = self.org.action({"op": "direction-save", "name": "Robotics", "color": "#167b70"})["directions"][0]["id"]
        result = self.apply([{"path": ["robotics"], "keys": ["a"]}, {"path": ["ROBOTICS", "Planning"], "keys": ["b"]}])
        tree, _ = self.tree()
        self.assertEqual(tree[("Robotics",)], existing)
        self.assertEqual(set(tree), {("Robotics",), ("Robotics", "Planning")})
        self.assertEqual(result["apply_result"]["created_categories"], 1)
        self.assertEqual(result["apply_result"]["reused_categories"], 1)

    def test_the_same_name_under_another_parent_is_a_different_category(self):
        self.apply([{"path": ["A", "Survey"], "keys": ["a"]}, {"path": ["B", "Survey"], "keys": ["b"]}])
        tree, _ = self.tree()
        self.assertEqual(len({tree[("A", "Survey")], tree[("B", "Survey")]}), 2)

    def test_a_paper_found_in_two_folders_is_in_both_categories(self):
        self.apply([{"path": ["RL"], "keys": ["a"]}, {"path": ["Survey"], "keys": ["a"]}])
        self.assertEqual(self.membership("a"), ["RL", "Survey"])

    def test_nothing_the_person_already_organised_is_removed(self):
        direction = self.org.action({"op": "direction-save", "name": "Mine", "color": "#167b70"})["directions"][0]["id"]
        self.org.action({"op": "membership", "keys": ["a"], "add": [direction]})
        self.apply([{"path": ["RL"], "keys": ["a"]}])
        self.assertEqual(self.membership("a"), ["Mine", "RL"])

    def test_imported_placements_are_protected_from_automatic_regrouping(self):
        self.apply([{"path": ["RL"], "keys": ["a"]}])
        data = self.org._load()[1]
        self.assertIn("a", data["protected"])
        self.assertNotIn("c", data["protected"])

    def test_deep_folders_are_folded_into_the_third_level(self):
        self.apply([{"path": ["1", "2", "3", "4", "5"], "keys": ["a"]}])
        tree, _ = self.tree()
        self.assertEqual(set(tree), {("1",), ("1", "2"), ("1", "2", "3")})
        self.assertEqual(self.membership("a"), ["3"])

    def test_long_names_are_cut_and_blank_ones_are_refused(self):
        self.apply([{"path": ["x" * 90], "keys": ["a"]}])
        self.assertEqual(max(len(p[0]) for p in self.tree()[0]), 60)
        for bad in ([""], ["  "], [3], ["ok", ""]):
            with self.assertRaises(ValueError, msg=bad) as caught:
                self.apply([{"path": bad, "keys": ["b"]}])
            self.assertNotIn("Unknown organization operation", str(caught.exception))

    def test_new_categories_get_distinct_colours(self):
        self.apply([{"path": [str(i)], "keys": ["a"]} for i in range(5)])
        colours = [d["color"] for d in self.org.action({"op": "export"})["directions"]]
        self.assertEqual(len(set(colours)), 5)
        self.assertTrue(all(c.startswith("#") and len(c) == 7 for c in colours))

    def test_files_at_the_top_of_the_folder_create_nothing(self):
        result = self.apply([{"path": [], "keys": ["a"]}])
        self.assertEqual(self.tree()[0], {})
        self.assertEqual(result["apply_result"]["created_categories"], 0)

    def test_applying_the_same_import_twice_changes_nothing_the_second_time(self):
        groups = [{"path": ["RL"], "keys": ["a", "b"]}]
        first = self.apply(groups)
        second = self.apply(groups)
        self.assertEqual(second["revision"], first["revision"])
        self.assertEqual(second["apply_result"]["added_memberships"], 0)
        self.assertEqual(second["apply_result"]["already_present"], 2)

    def test_a_paper_that_is_not_in_the_library_is_refused_and_nothing_changes(self):
        self.store.upsert_papers([{"key": "loose", "title": "Not saved"}], project_id=self.project)
        before = self.org.action({"op": "export"})["revision"]
        with self.assertRaises(ValueError) as caught:
            self.apply([{"path": ["RL"], "keys": ["a", "loose"]}])
        self.assertIn("not saved", str(caught.exception))
        self.assertEqual(self.org.action({"op": "export"})["revision"], before)
        self.assertEqual(self.tree()[0], {})

    def test_malformed_requests_are_refused(self):
        for groups in (None, "x", [None], [{"path": "RL", "keys": ["a"]}], [{"path": ["RL"], "keys": "a"}],
                       [{"path": ["RL"]}], [{"path": ["RL"], "keys": [5]}], [{"path": ["RL"], "keys": ["a"]}] * 6000):
            with self.assertRaises(ValueError, msg=str(groups)[:40]) as caught:
                self.apply(groups)
            self.assertNotIn("Unknown organization operation", str(caught.exception))

    def test_the_result_reports_the_category_count_against_the_ai_review_limit(self):
        result = self.apply([{"path": [f"c{i}"], "keys": ["a"]} for i in range(61)])
        self.assertEqual(result["apply_result"]["total_categories"], 61)
        self.assertTrue(result["apply_result"]["over_ai_limit"])
        self.assertFalse(self.apply([{"path": ["c0"], "keys": ["b"]}])["apply_result"].get("created_categories"))

    def test_a_stale_revision_is_a_conflict(self):
        with self.assertRaises(Conflict):
            self.apply([{"path": ["RL"], "keys": ["a"]}], revision=99)


class BatchCategoriesTests(Base):
    def setUp(self):
        super().setUp()
        self.imp = LibraryImport(Path(self.tmp.name), self.store)

    def committed(self, paths, **options):
        batch = self.imp.create_batch(self.project, "folder", "我的库", options)["id"]
        for n, path in enumerate(paths):
            data = pdf(100 + n)
            item = self.imp.add_pdf(batch, path, io.BytesIO(data), len(data), 1, None)
            self.imp._set(item["id"], "matched", match_source="title",
                          paper={"key": f"https://doi.org/10.1000/n{n}", "title": f"Imported {n}", "group_name": "imported"})
        self.imp.commit(batch)
        return batch

    def test_committed_folders_become_categories_through_the_batch(self):
        batch = self.committed(["我的库/强化学习/a.pdf", "我的库/强化学习/规划/b.pdf", "我的库/c.pdf"])
        result = self.imp.apply_categories(batch, self.org)
        tree, _ = self.tree()
        self.assertEqual(set(tree), {("强化学习",), ("强化学习", "规划")})
        self.assertEqual(result["created_categories"], 2)
        self.assertTrue(self.imp.batch(batch)["categories_applied"])

    def test_turning_folder_categories_off_creates_none(self):
        batch = self.committed(["我的库/强化学习/a.pdf"], folder_categories=False)
        self.assertEqual(self.imp.apply_categories(batch, self.org)["created_categories"], 0)
        self.assertEqual(self.tree()[0], {})

    def test_the_root_folder_can_be_the_top_category(self):
        batch = self.committed(["我的库/强化学习/a.pdf", "我的库/b.pdf"], root_category=True)
        self.imp.apply_categories(batch, self.org)
        tree, _ = self.tree()
        self.assertEqual(set(tree), {("我的库",), ("我的库", "强化学习")})
        self.assertEqual(self.membership("https://doi.org/10.1000/n1"), ["我的库"])

    def test_reapplying_is_safe(self):
        batch = self.committed(["我的库/A/a.pdf"])
        self.imp.apply_categories(batch, self.org)
        again = self.imp.apply_categories(batch, self.org)
        self.assertEqual((again["created_categories"], again["added_memberships"]), (0, 0))

    def test_an_uncommitted_batch_cannot_apply_categories(self):
        batch = self.imp.create_batch(self.project, "folder", "r", {})["id"]
        with self.assertRaises(ValueError):
            self.imp.apply_categories(batch, self.org)


class PreviewTests(Base):
    def setUp(self):
        super().setUp()
        self.imp = LibraryImport(Path(self.tmp.name), self.store)

    def staged(self, rows, **options):
        """rows: [(path, state)] -> batch id, items settled to the given state (no commit)."""
        batch = self.imp.create_batch(self.project, "folder", "我的库", options)["id"]
        for n, (path, state) in enumerate(rows):
            data = pdf(200 + n)
            item = self.imp.add_pdf(batch, path, io.BytesIO(data), len(data), 1, None)
            fields = {"paper": {"key": f"k{n}", "title": f"T{n}"}, "match_source": "title"} if state == "matched" else {}
            self.imp._set(item["id"], state, **fields)
        return batch

    def test_the_preview_counts_what_would_be_placed_in_each_folder(self):
        batch = self.staged([("我的库/强化学习/a.pdf", "matched"), ("我的库/强化学习/b.pdf", "matched"),
                             ("我的库/强化学习/规划/c.pdf", "matched"), ("我的库/top.pdf", "matched")])
        preview = self.imp.category_preview(batch, [])
        self.assertEqual(sorted((tuple(p["path"]), p["count"]) for p in preview["paths"]),
                         [(("强化学习",), 2), (("强化学习", "规划"), 1)])
        self.assertEqual(preview["new_categories"], 2)

    def test_papers_that_will_not_be_imported_are_not_counted(self):
        batch = self.staged([("我的库/A/a.pdf", "matched"), ("我的库/A/b.pdf", "needs_choice"), ("我的库/B/c.pdf", "excluded"),
                             ("我的库/C/d.pdf", "failed"), ("我的库/D/e.pdf", "unmatched")])
        names = sorted(tuple(p["path"]) for p in self.imp.category_preview(batch, [])["paths"])
        self.assertEqual(names, [("A",), ("D",)])

    def test_it_follows_the_batch_options_and_the_same_depth_and_name_limits_as_the_apply(self):
        off = self.staged([("我的库/A/a.pdf", "matched")], folder_categories=False)
        self.assertEqual(self.imp.category_preview(off, [])["paths"], [])
        top = self.staged([("我的库/A/a.pdf", "matched"), ("我的库/b.pdf", "matched")], root_category=True)
        self.assertEqual(sorted(tuple(p["path"]) for p in self.imp.category_preview(top, [])["paths"]), [("我的库",), ("我的库", "A")])
        deep = self.staged([("我的库/1/2/3/4/5/a.pdf", "matched"), (f"我的库/{'x' * 90}/b.pdf", "matched")])
        paths = sorted(tuple(p["path"]) for p in self.imp.category_preview(deep, [])["paths"])
        self.assertEqual(paths, [("1", "2", "3"), ("x" * 60,)])

    def test_categories_that_already_exist_are_reused_not_counted_as_new(self):
        self.org.action({"op": "direction-save", "name": "Robotics", "color": "#167b70"})
        existing = self.org.action({"op": "export"})["directions"]
        batch = self.staged([("我的库/robotics/a.pdf", "matched"), ("我的库/robotics/Planning/b.pdf", "matched")])
        preview = self.imp.category_preview(batch, existing)
        self.assertEqual((preview["new_categories"], preview["total_after"]), (1, 2))

    def test_a_tree_the_ai_review_would_refuse_is_flagged_before_importing(self):
        batch = self.staged([(f"我的库/c{i}/a.pdf", "matched") for i in range(61)])
        preview = self.imp.category_preview(batch, [])
        self.assertEqual((preview["total_after"], preview["over_ai_limit"]), (61, True))


if __name__ == "__main__":
    unittest.main()
