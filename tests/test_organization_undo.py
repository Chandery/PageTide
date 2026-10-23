"""Named undo (layout saves are never what the button undoes) and nested suggestion apply."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.clustering import corpus_fingerprint
from app.db import Store
from app.organization import Conflict, Organization


class NamedUndoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "library.sqlite"
        self.store = Store(self.path)
        self.store.init()
        self.addCleanup(self.store.close)
        self.papers = [{"key": k, "title": "World model " + k} for k in ("a", "b", "c")]
        self.store.upsert_papers(self.papers)
        for paper in self.papers:
            self.store.save_to_library(paper["key"])
        self.org = Organization(self.store)

    def save(self, name="Planning", **extra):
        return self.org.action(dict(action="direction-save", name=name, color="#123456", **extra))

    def test_snapshot_names_the_latest_visible_change(self):
        self.assertIsNone(self.org.snapshot()["undo"])
        snap = self.save()
        self.assertEqual(snap["undo"]["label"], "新建类别")
        direction = snap["directions"][0]["id"]
        snap = self.org.action({"action": "membership", "keys": ["a"], "add": [direction]})
        self.assertEqual(snap["undo"]["label"], "调整分类")
        snap = self.org.action({"action": "note", "key": "a", "text": "n", "version": 0})
        self.assertEqual(snap["undo"]["label"], "编辑笔记")
        self.assertEqual(self.save("Renamed", id=direction)["undo"]["label"], "编辑类别")

    def test_layout_saves_are_not_offered_and_survive_named_undo(self):
        direction = self.save()["directions"][0]["id"]
        target = self.org.snapshot()["undo"]
        node = "paper:a"
        snap = self.org.action({"action": "positions", "positions": {node: {"x": 5, "y": 7}}})
        snap = self.org.action({"action": "collapse", "id": direction, "collapsed": True})
        self.assertEqual(snap["undo"], target)
        undone = self.org.action({"action": "undo", "event": target["id"]})
        self.assertEqual(undone["directions"], [])
        self.assertEqual(undone["positions"].get(node), {"x": 5, "y": 7})
        self.assertEqual(undone["collapsed"], [])  # the collapsed category no longer exists
        self.assertIsNone(undone["undo"])

    def test_rearrange_is_a_named_change_that_restores_positions(self):
        self.org.action({"action": "positions", "positions": {"paper:a": {"x": 1, "y": 1}}})
        snap = self.org.action({"action": "positions", "rearrange": True,
                                "positions": {"paper:a": {"x": 9, "y": 9}}})
        self.assertEqual(snap["undo"]["label"], "重新排列")
        undone = self.org.action({"action": "undo", "event": snap["undo"]["id"]})
        self.assertEqual(undone["positions"]["paper:a"], {"x": 1, "y": 1})

    def test_stale_event_conflicts_without_mutation(self):
        first = self.save()["undo"]
        self.save("Second")
        before = self.org.snapshot()
        with self.assertRaises(Conflict):
            self.org.action({"action": "undo", "event": first["id"]})
        self.assertEqual(self.org.snapshot(), before)

    def test_legacy_unlabelled_events_stay_undoable_but_unnamed(self):
        self.save()
        self.store.conn.execute("UPDATE org_events SET label=NULL")
        self.store.conn.commit()
        self.assertIsNone(self.org.snapshot()["undo"])
        self.assertEqual(self.org.action({"action": "undo"})["directions"], [])

    def test_undoing_a_delete_restores_the_category_layout(self):
        direction = self.save()["directions"][0]["id"]
        node = "direction:" + direction
        self.org.action({"action": "positions", "positions": {node: {"x": 3, "y": 4},
                                                               "paper:b": {"x": 1, "y": 2}}})
        self.org.action({"action": "collapse", "id": direction, "collapsed": True})
        snap = self.org.action({"action": "direction-delete", "id": direction})
        self.assertNotIn(node, snap["positions"])
        self.org.action({"action": "positions", "positions": {"paper:b": {"x": 8, "y": 8}}})
        undone = self.org.action({"action": "undo", "event": snap["undo"]["id"]})
        self.assertEqual(undone["positions"][node], {"x": 3, "y": 4})
        self.assertEqual(undone["positions"]["paper:b"], {"x": 8, "y": 8})  # later layout kept
        self.assertEqual(undone["collapsed"], [direction])

    def test_undoing_a_delete_keeps_the_current_unclassified_fold(self):
        direction = self.save()["directions"][0]["id"]
        self.org.action({"action": "collapse", "id": "", "collapsed": True})
        snap = self.org.action({"action": "direction-delete", "id": direction})
        self.org.action({"action": "collapse", "id": "", "collapsed": False})
        undone = self.org.action({"action": "undo", "event": snap["undo"]["id"]})
        self.assertNotIn("", undone["collapsed"])

    def test_undoing_a_creation_drops_its_layout(self):
        direction = self.save()["directions"][0]["id"]
        target = self.org.snapshot()["undo"]
        self.org.action({"action": "positions", "positions": {"direction:" + direction: {"x": 1, "y": 1}}})
        self.org.action({"action": "collapse", "id": direction, "collapsed": True})
        undone = self.org.action({"action": "undo", "event": target["id"]})
        self.assertNotIn("direction:" + direction, undone["positions"])
        self.assertEqual(undone["collapsed"], [])

    def test_unchanged_save_is_an_edit_and_rank_change_is_a_reorder(self):
        direction = self.save()["directions"][0]["id"]
        self.assertEqual(self.save(id=direction)["undo"]["label"], "编辑类别")
        self.assertEqual(self.save(id=direction, rank=0)["undo"]["label"], "调整类别顺序")

    def test_event_id_must_be_an_integer(self):
        target = self.save()["undo"]
        before = self.org.snapshot()
        for bad in (str(target["id"]), float(target["id"]), True, None):
            with self.assertRaises(ValueError):
                self.org.action({"action": "undo", "event": bad})
        self.assertEqual(self.org.snapshot(), before)

    def test_old_event_table_gains_label_column(self):
        path = Path(self.tmp.name) / "old.sqlite"
        store = Store(path)
        store.init()
        self.addCleanup(store.close)
        Organization(store).action({"action": "direction-save", "name": "Old", "color": "#123456"})
        store.conn.execute("ALTER TABLE org_events DROP COLUMN label")
        store.conn.commit()
        self.assertNotIn("label", {row[1] for row in store.conn.execute("PRAGMA table_info(org_events)")})
        org = Organization(store)
        self.assertIn("label", {row[1] for row in store.conn.execute("PRAGMA table_info(org_events)")})
        backup = Path(org.backup_path)  # private pre-migration copy, still without the column
        self.addCleanup(backup.unlink)
        # `with sqlite3.connect()` only ends a transaction; it does not close, and Windows cannot delete an open file.
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("label", {row[1] for row in conn.execute("PRAGMA table_info(org_events)")})
        self.assertIsNone(Organization(store).backup_path)  # no second migration, no second copy
        self.assertIsNone(org.snapshot()["undo"])
        self.assertEqual(org.action({"action": "undo"})["directions"], [])
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")


class NestedApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "library.sqlite")
        self.store.init()
        self.addCleanup(self.store.close)
        self.papers = [{"key": k, "title": "World model " + k} for k in ("a", "b", "c")]
        self.store.upsert_papers(self.papers)
        for paper in self.papers:
            self.store.save_to_library(paper["key"])
        self.org = Organization(self.store)
        self.preview = {"fingerprint": corpus_fingerprint(self.papers), "groups": [
            {"id": "facet-top", "name": "世界模型", "keys": ["a", "b", "c"], "parent": None},
            {"id": "facet-kid", "name": "JEPA", "keys": ["a", "b"], "parent": "facet-top"}]}

    def suggest(self):
        with patch("app.organization.review_papers", return_value=self.preview):
            self.org.action({"action": "suggest"})

    def apply(self, ids):
        groups = [g for g in self.preview["groups"] if g["id"] in ids]
        return self.org.action({"action": "apply-suggestions", "apply_mode": "add",
                                "fingerprint": self.preview["fingerprint"], "suggestions": groups})

    def parents(self, snap):
        return {d["name"]: d.get("parent_id") for d in snap["directions"]}

    def test_child_lands_under_parent_applied_together(self):
        self.suggest()
        snap = self.apply({"facet-top", "facet-kid"})
        top = next(d["id"] for d in snap["directions"] if d["name"] == "世界模型")
        self.assertEqual(self.parents(snap), {"世界模型": None, "JEPA": top})
        self.assertEqual(snap["undo"]["label"], "应用建议")

    def test_child_requires_parent_and_finds_parent_applied_earlier(self):
        self.suggest()
        before = self.org.snapshot()
        with self.assertRaisesRegex(ValueError, "父类别"):
            self.apply({"facet-kid"})
        self.assertEqual(self.org.snapshot(), before)
        self.suggest()
        first = self.apply({"facet-top"})
        top = first["directions"][0]["id"]
        self.suggest()
        self.assertEqual(self.parents(self.apply({"facet-kid"}))["JEPA"], top)


if __name__ == "__main__":
    unittest.main()
