import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

from app.db import Store
from app.organization import Conflict, Organization, SCHEMA
from app.clustering import ClusteringUnavailable


HAS_NETWORKX = importlib.util.find_spec("networkx") is not None


class OrganizationTests(unittest.TestCase):
    def test_graph_is_read_only_and_uses_only_saved_metadata(self):
        before = self.org.snapshot()
        result = self.org.action({"action": "graph"})["relations"]
        self.assertEqual(self.org.snapshot(), before)
        self.assertEqual({key for group in result["groups"] for key in group["keys"]}, {"a", "b"})
        self.assertTrue(result["edges"])
        self.assertTrue(all(edge["kind"] == "similarity" for edge in result["edges"]))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "library.sqlite"
        self.store = Store(self.path)
        self.store.init()
        self.addCleanup(self.store.close)
        self.store.upsert_papers([
            {"key": "a", "title": "Robot motion planning", "abstract": "robot control planning"},
            {"key": "b", "title": "Robot motion planning", "abstract": "robot control planning"},
            {"key": "c", "title": "Clinical cancer trial", "abstract": "clinical cancer trial"}])
        self.store.save_to_library("a", "legacy note")
        self.store.save_to_library("b")
        self.org = Organization(self.store)

    def direction(self, org=None, name="Planning"):
        org = org or self.org
        return org.action({"action": "direction-save", "name": name, "color": "#12Ab34"})["directions"][-1]["id"]

    def item(self, snapshot=None, key="a"):
        return next(p for p in (snapshot or self.org.snapshot())["items"] if p["key"] == key)

    def test_backup_precedes_schema_and_preserves_wal_data(self):
        backup = Path(self.org.backup_path)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(backup.parent.resolve(), self.path.parent.resolve())
        with sqlite3.connect(backup) as conn:
            self.assertEqual(conn.execute("SELECT note FROM library WHERE paper_key='a'").fetchone()[0], "legacy note")
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='org_projects'").fetchone())
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertIsNone(Organization(self.store).backup_path)
        self.assertEqual(len(list(self.path.parent.glob(".*pre-organization*"))), 1)

    def test_injected_schema_failure_rolls_back_and_backup_restores(self):
        path = Path(self.tmp.name) / "failure.sqlite"
        original = Store(path)
        self.addCleanup(original.close)
        original.init()
        original.upsert_papers([{"key": "original", "title": "Keep metadata", "abstract": "Original abstract"}])
        original.save_to_library("original", "Keep note")
        with patch("app.organization.SCHEMA", SCHEMA + ("INVALID SQL",)):
            with self.assertRaises(sqlite3.OperationalError):
                Organization(original)
        self.assertFalse(original.conn.in_transaction)
        self.assertEqual(original.conn.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'org_%'").fetchall(), [])
        self.assertEqual(original.library()[0]["note"], "Keep note")
        backups = list(path.parent.glob(".failure.sqlite.pre-organization-*.sqlite"))
        self.assertEqual(len(backups), 1)
        restored_path = Path(self.tmp.name) / "restored.sqlite"
        source = sqlite3.connect(backups[0])
        destination = sqlite3.connect(restored_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        restored = Store(restored_path)
        self.addCleanup(restored.close)
        restored.init()
        self.assertEqual(restored.library(), original.library())
        self.assertEqual(restored.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        recovered = Organization(restored)
        self.assertEqual(recovered.snapshot()["items"][0]["note"], "Keep note")

    def test_backup_failure_prevents_schema_creation(self):
        store = Store(Path(self.tmp.name) / "backup-failure.sqlite")
        self.addCleanup(store.close)
        store.init()
        with patch.object(Organization, "_backup", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                Organization(store)
        self.assertFalse(store.conn.in_transaction)
        self.assertEqual(store.conn.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'org_%'").fetchall(), [])

    def test_project_isolation_notes_memberships_positions_revisions_and_undo(self):
        other = Organization(self.store, "other")
        direction = self.direction()
        self.org.action({"action": "membership", "keys": ["a"], "add": [direction]})
        self.org.action({"action": "note", "key": "a", "text": "private", "version": 0})
        self.org.action({"action": "positions", "positions": {"paper:a": {"x": 1, "y": 2}}})
        snap = other.snapshot()
        self.assertEqual(snap["revision"], 0)
        self.assertEqual(snap["directions"], [])
        self.assertEqual(snap["positions"], {})
        self.assertEqual(self.item(snap)["note"], "")
        self.assertEqual(self.item(snap)["directions"], [])
        with self.assertRaises(ValueError):
            other.action({"action": "membership", "keys": ["a"], "add": [direction]})
        with self.assertRaises(ValueError):
            other.action({"action": "undo"})
        other.action({"action": "note", "key": "a", "text": "other note", "version": 0})
        other.action({"action": "undo"})
        self.assertEqual(self.item()["note"], "private")
        self.assertEqual(self.item(other.snapshot())["note"], "")

    def test_legacy_import_and_notes_optimistic_history_restore(self):
        self.assertEqual(self.item()["note"], "legacy note")
        self.assertEqual(self.item()["note_version"], 0)
        with self.assertRaises(ValueError):
            self.org.action({"action": "note", "key": "a", "text": "missing version"})
        self.org.action({"action": "note", "key": "a", "text": "edited", "version": 0})
        with self.assertRaises(Conflict):
            self.org.action({"action": "note", "key": "a", "text": "stale", "version": 0})
        history = self.org.action({"action": "history", "key": "a"})["history"]
        self.assertEqual([h["text"] for h in history], ["legacy note", "edited"])
        restored = self.org.action({"action": "note", "key": "a", "text": history[0]["text"], "version": 1})
        self.assertEqual(self.item(restored)["note_version"], 2)
        undone = self.org.action({"action": "undo"})
        self.assertEqual(self.item(undone)["note"], "edited")
        self.assertEqual(self.item(undone)["note_version"], 3)
        self.assertEqual([h["version"] for h in self.org.action({"action": "history", "key": "a"})["history"]], [0, 1, 2, 3])

    def test_direction_edit_rank_delete_and_undo(self):
        first, second = self.direction(name="One"), self.direction(name="Two")
        self.org.action({"action": "membership", "keys": ["a", "b"], "add": [first, second]})
        self.org.action({"action": "direction-save", "id": second, "name": "Renamed", "color": "#ABCDEF", "rank": 0})
        self.assertEqual([d["id"] for d in self.org.snapshot()["directions"]], [second, first])
        self.org.action({"action": "positions", "positions": {"direction:" + first: {"x": 3, "y": 4}}})
        before = self.org.snapshot()
        deleted = self.org.action({"action": "direction-delete", "id": first})
        self.assertEqual(self.item(deleted)["directions"], [second])
        self.assertEqual(deleted["positions"], {})
        restored = self.org.action({"action": "undo"})
        self.assertGreater(restored["revision"], before["revision"])
        restored["revision"] = before["revision"]
        self.assertEqual(restored, before)

    def test_validation_and_atomic_batch_rollback(self):
        direction = self.direction()
        before = self.org.snapshot()
        bad = [
            {"action": "membership", "keys": ["a", "unknown"], "add": [direction]},
            {"action": "membership", "keys": ["c"], "add": [direction]},
            {"action": "membership", "keys": ["a"], "add": [direction], "remove": [direction]},
            {"action": "membership", "keys": "a"},
            {"action": "direction-save", "name": "X", "color": "red"},
            {"action": "direction-save", "name": "X", "color": "#123456", "rank": 99},
            {"action": "direction-save", "id": "unknown", "name": "X", "color": "#123456"},
            {"action": "note", "key": "a", "version": True, "text": "bad"},
            {"action": "positions", "positions": {"paper:a": {"x": 1, "y": 2}, "paper:b": {"x": float("nan"), "y": 0}}},
            {"action": "positions", "positions": {"paper:a": {"x": True, "y": 0}}},
            {"action": "positions", "positions": {"direction:unknown": {"x": 0, "y": 0}}},
            {"action": "positions", "positions": {"a": {"x": 0, "y": 0}}},
            {"action": "note", "key": "unknown", "version": 0, "text": "bad"},
        ]
        for body in bad:
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.org.action(body)
            self.assertEqual(self.org.snapshot(), before)

    def test_revision_conflict_across_connections(self):
        second = Store(self.path)
        self.addCleanup(second.close)
        peer = Organization(second)
        revision = peer.snapshot()["revision"]
        self.direction()
        with self.assertRaises(Conflict):
            peer.action({"action": "direction-save", "name": "Stale", "color": "#123456", "revision": revision})
        peer.action({"action": "note", "key": "a", "text": "peer", "version": 0})
        with self.assertRaises(Conflict):
            self.org.action({"action": "note", "key": "a", "text": "lost update", "version": 0})

    def test_unsave_resave_preserves_organization_and_note(self):
        direction = self.direction()
        self.org.action({"action": "membership", "keys": ["a"], "add": [direction]})
        self.org.action({"action": "note", "key": "a", "text": "keep", "version": 0})
        self.org.action({"action": "positions", "positions": {"paper:a": {"x": 1, "y": 2}}})
        self.store.remove_from_library("a")
        self.assertEqual([p["key"] for p in self.org.snapshot()["items"]], ["b"])
        exported = self.org.action({"action": "export"})
        self.assertEqual(self.item(exported)["note"], "keep")
        self.assertIsNone(self.item(exported)["saved_at"])
        self.store.save_to_library("a", "must not overwrite")
        item = self.item()
        self.assertEqual(item["note"], "keep")
        self.assertEqual(item["directions"], [direction])
        self.assertEqual(self.org.snapshot()["positions"]["paper:a"], {"x": 1, "y": 2})
        self.assertEqual(self.store.paper("a")["title"], "Robot motion planning")

    def test_unsaved_position_cleanup_and_rearrangement_keep_write_validation(self):
        direction = self.direction()
        alias = "paper:a:" + direction
        original = {"paper:a": {"x": 1, "y": 2}, alias: {"x": 3, "y": 4}}
        self.org.action({"action": "positions", "positions": original})
        self.store.remove_from_library("a")
        before = self.org.snapshot()
        for node in ("paper:a", alias, "paper:c"):
            with self.subTest(node=node), self.assertRaises(ValueError):
                self.org.action({"action": "positions", "positions": {node: {"x": 5, "y": 6}}})
            self.assertEqual(self.org.snapshot(), before)
        result = self.org.action({"action": "positions", "positions": {
            "paper:a": None, alias: None, "paper:b": {"x": 7, "y": 8}}})
        self.assertEqual(result["positions"], {"paper:b": {"x": 7, "y": 8}})
        self.assertEqual(self.org.action({"action": "undo"})["positions"], original)
        with self.assertRaises(ValueError):
            self.org.action({"action": "positions", "positions": {"paper:a": None, "paper:unknown": None}})
        self.assertEqual(self.org.snapshot()["positions"], original)

    def test_new_legacy_note_saved_then_unsaved_without_snapshot_is_retained(self):
        self.store.save_to_library("c", "captured by trigger")
        self.store.remove_from_library("c")
        history = self.org.action({"action": "history", "key": "c"})["history"]
        self.assertEqual(history[0]["text"], "captured by trigger")

    def test_persistence_export_and_position_removal(self):
        direction = self.direction()
        self.org.action({"action": "membership", "keys": ["a"], "add": [direction]})
        self.org.action({"action": "positions", "positions": {"paper:a": {"x": -1.5, "y": 2}}})
        reopened = Store(self.path)
        self.addCleanup(reopened.close)
        peer = Organization(reopened)
        self.assertEqual(peer.snapshot(), self.org.snapshot())
        exported = peer.action({"action": "export"})
        self.assertEqual(json.loads(json.dumps(exported)), exported)
        self.assertEqual(exported["project"], "default")
        peer.action({"action": "positions", "positions": {"paper:a": None}})
        self.assertEqual(self.org.snapshot()["positions"], {})
        self.org.action({"action": "undo"})
        self.assertEqual(self.org.snapshot()["positions"], {"paper:a": {"x": -1.5, "y": 2}})

    def test_active_transaction_not_committed_or_discarded(self):
        self.store.conn.execute("INSERT INTO settings VALUES ('pending','1')")
        with self.assertRaises(RuntimeError):
            self.org.snapshot()
        self.assertTrue(self.store.conn.in_transaction)
        self.store.conn.rollback()

    def test_missing_dependency_does_not_mutate_state(self):
        before = self.org.snapshot()
        with patch.dict("sys.modules", {"networkx": None}):
            with self.assertRaises(ClusteringUnavailable):
                self.org.action({"action": "graph"})
            self.assertEqual(self.org.snapshot(), before)
            # Category suggestions are plain lexical matching and need no optional dependency.
            self.assertTrue(self.org.action({"action": "suggest"})["suggestions"]["groups"])

    def test_compound_positions_virtual_anchor_and_direction_delete(self):
        key = "doi:10.1234/paper:part"
        self.store.upsert_papers([{"key": key, "title": "Paper"}])
        self.store.save_to_library(key)
        first, second = self.direction(), self.direction(name="Other")
        self.org.action({"action": "membership", "keys": [key], "add": [first, second]})
        alias = "paper:" + quote(key, safe="") + ":" + first
        alias2 = "paper:" + quote(key, safe="") + ":" + second
        positions = {alias: {"x": 1, "y": 2}, alias2: {"x": 3, "y": 4},
                     "direction:" + first + ":anchor": {"x": 5, "y": 6},
                     "direction::anchor": {"x": 7, "y": 8}, "paper:b:": {"x": 9, "y": 10}}
        result = self.org.action({"action": "positions", "positions": positions})
        self.assertEqual(result["positions"], positions)
        result = self.org.action({"action": "direction-delete", "id": first})
        self.assertNotIn(alias, result["positions"])
        self.assertNotIn("direction:" + first + ":anchor", result["positions"])
        self.assertIn(alias2, result["positions"])
        self.assertIn("direction::anchor", result["positions"])
        self.org.action({"action": "undo"})
        self.assertEqual(self.org.snapshot()["positions"], positions)

    def test_collapse_persists_is_project_scoped_and_undoable(self):
        direction = self.direction()
        self.org.action({"action": "collapse", "id": direction, "collapsed": True})
        result = self.org.action({"action": "collapse", "id": "", "collapsed": True})
        self.assertEqual(set(result["collapsed"]), {"", direction})
        self.assertEqual(Organization(self.store).snapshot()["collapsed"], result["collapsed"])
        self.assertEqual(Organization(self.store, "other").snapshot()["collapsed"], [])
        self.assertEqual(self.org.action({"action": "undo"})["collapsed"], [direction])
        self.assertEqual(self.org.action({"action": "direction-delete", "id": direction})["collapsed"], [])
        self.assertEqual(self.org.action({"action": "undo"})["collapsed"], [direction])
        with self.assertRaises(ValueError):
            self.org.action({"action": "collapse", "id": direction, "collapsed": "false"})

    def test_draft_survives_reopen_and_unsave_without_changing_notes_or_undo(self):
        revision = self.org.snapshot()["revision"]
        saved = self.org.action({"action": "draft-save", "key": "a", "client": "editor-1",
                                 "text": "unfinished work", "version": 0})["draft"]
        self.assertEqual(saved["version"], 1)
        self.assertEqual(self.org.snapshot()["revision"], revision)
        self.assertEqual(self.item()["note"], "legacy note")
        with self.assertRaises(ValueError):
            self.org.action({"action": "undo"})
        self.store.remove_from_library("a")
        reopened = Store(self.path)
        self.addCleanup(reopened.close)
        peer = Organization(reopened)
        self.assertEqual(peer.snapshot()["drafts"], [saved])
        self.assertEqual(peer.action({"action": "drafts", "key": "a"})["drafts"], [saved])
        self.assertEqual(peer.action({"action": "export"})["drafts"], [saved])
        self.assertEqual(Organization(reopened, "other").snapshot()["drafts"], [])

    def test_draft_versions_clients_and_stale_clear_protect_newer_edits(self):
        def save(client, text, version):
            return self.org.action({"action": "draft-save", "key": "a", "client": client,
                                    "text": text, "version": version})
        save("one", "first", 0)
        save("two", "different client", 0)
        save("one", "newer", 1)
        with self.assertRaises(Conflict):
            save("one", "stale", 1)
        with self.assertRaises(Conflict):
            self.org.action({"action": "draft-clear", "key": "a", "client": "one", "version": 1})
        self.assertEqual(len(self.org.snapshot()["drafts"]), 2)
        self.org.action({"action": "note", "key": "a", "text": "newer", "version": 0})
        cleared = self.org.action({"action": "draft-clear", "key": "a", "client": "one", "version": 2})["draft"]
        self.assertEqual(cleared["version"], 3)
        self.assertIsNone(cleared["text"])
        self.assertEqual([d["client"] for d in self.org.snapshot()["drafts"]], ["two"])
        with self.assertRaises(Conflict):
            save("one", "stale resurrect", 0)
        self.org.action({"action": "undo"})
        self.assertEqual(self.item()["note"], "legacy note")
        self.assertEqual([d["client"] for d in self.org.snapshot()["drafts"]], ["two"])

    def test_selected_suggestion_names_colors_and_members_are_editable(self):
        preview = self.org.action({"action": "suggest"})["suggestions"]
        group = preview["groups"][0]
        result = self.org.action({"action": "apply-suggestions", "fingerprint": preview["fingerprint"],
                                 "suggestions": [{"id": group["id"], "name": "My label",
                                                  "color": "#ABCDEF", "keys": ["b"]}]})
        self.assertEqual(result["directions"], [{"id": group["id"], "name": "My label",
                                               "color": "#abcdef", "rank": 0, "parent_id": None}])
        self.assertEqual(self.item(result)["directions"], [])
        self.assertEqual(self.item(result, "b")["directions"], [group["id"]])

    def test_selected_suggestions_cannot_inject_or_duplicate_keys(self):
        preview = self.org.action({"action": "suggest"})["suggestions"]
        group = preview["groups"][0]
        before = self.org.snapshot()
        for keys in (["c"], ["a", "a"], ["unknown"]):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                self.org.action({"action": "apply-suggestions", "fingerprint": preview["fingerprint"],
                                 "suggestions": [{"id": group["id"], "keys": keys}]})
            self.assertEqual(self.org.snapshot(), before)

    def test_suggest_releases_transaction_and_preserves_concurrent_edits(self):
        from app.organization_facets import suggest_groups
        second = Store(self.path)
        self.addCleanup(second.close)
        peer = Organization(second)

        def during_compute(papers, **kwargs):
            self.assertFalse(self.org.conn.in_transaction)
            peer.action({"action": "direction-save", "name": "Concurrent", "color": "#123456"})
            peer.action({"action": "note", "key": "a", "text": "during compute", "version": 0})
            return suggest_groups(papers, **kwargs)

        with patch("app.organization.suggest_groups", side_effect=during_compute):
            result = self.org.action({"action": "suggest"})
        self.assertEqual(result["directions"][0]["name"], "Concurrent")
        self.assertEqual(self.item(result)["note"], "during compute")
        self.assertEqual(result["revision"], 3)

    def test_suggest_rechecks_corpus_and_explicit_revision_after_computation(self):
        from app.organization_facets import suggest_groups

        def corpus_changed(papers, **kwargs):
            self.store.save_to_library("c")
            return suggest_groups(papers, **kwargs)

        with patch("app.organization.suggest_groups", side_effect=corpus_changed), self.assertRaises(Conflict):
            self.org.action({"action": "suggest"})
        self.assertNotIn("suggestions", self.org.snapshot())
        self.assertEqual(self.org.snapshot()["revision"], 0)

        def revision_changed(papers, **kwargs):
            self.direction()
            return suggest_groups(papers, **kwargs)

        with patch("app.organization.suggest_groups", side_effect=revision_changed), self.assertRaises(Conflict):
            self.org.action({"action": "suggest", "revision": 0})
        self.assertNotIn("suggestions", self.org.snapshot())
        self.assertEqual(len(self.org.snapshot()["directions"]), 1)

    def test_suggestions_preview_apply_stale_and_manual_protection(self):
        direction = self.direction()
        preview = self.org.action({"action": "suggest"})
        self.assertEqual(self.item(preview)["directions"], [])
        fingerprint = preview["suggestions"]["fingerprint"]
        self.org.action({"action": "membership", "keys": ["a"], "add": [direction]})
        self.org.action({"action": "note", "key": "b", "text": "keep note", "version": 0})
        applied = self.org.action({"action": "apply-suggestions", "fingerprint": fingerprint})
        self.assertEqual(self.item(applied)["directions"], [direction])
        self.assertEqual(self.item(applied, "b")["note"], "keep note")
        self.assertTrue(self.item(applied, "b")["directions"][0].startswith("facet-"))
        self.org.action({"action": "undo"})
        self.assertEqual(self.item(key="b")["directions"], [])
        self.assertEqual(self.item(key="b")["note"], "keep note")
        self.org.action({"action": "suggest"})
        self.store.save_to_library("c")
        self.assertTrue(self.org.snapshot()["suggestions"]["stale"])
        with self.assertRaises(Conflict):
            self.org.action({"action": "suggest-apply", "fingerprint": fingerprint})

    def test_metadata_changes_stale_and_preview_cannot_be_forged(self):
        preview = self.org.action({"action": "suggest"})["suggestions"]
        self.store.conn.execute("UPDATE papers SET abstract='changed' WHERE key='a'")
        self.store.conn.commit()
        with self.assertRaises(Conflict):
            self.org.action({"action": "suggest-apply", "fingerprint": preview["fingerprint"]})
        with self.assertRaises(Conflict):
            self.org.action({"action": "apply-suggestions", "suggestions": [{"name": "Forged", "keys": ["a"]}]})

    def test_manually_removed_membership_stays_removed_after_reclassification(self):
        preview = self.org.action({"action": "suggest"})["suggestions"]
        self.org.action({"action": "suggest-apply", "fingerprint": preview["fingerprint"]})
        direction = self.item()["directions"][0]
        self.org.action({"action": "membership", "keys": ["a"], "remove": [direction]})
        preview = self.org.action({"action": "suggest"})["suggestions"]
        result = self.org.action({"action": "suggest-apply", "fingerprint": preview["fingerprint"]})
        self.assertEqual(self.item(result)["directions"], [])

    def test_membership_edit_that_empties_a_category_deletes_it(self):
        kept, emptied, untouched = (self.direction(name=n) for n in ("Kept", "Emptied", "Untouched"))
        self.org.action({"action": "membership", "keys": ["a", "b"], "add": [kept, emptied]})
        self.org.action({"action": "positions", "positions": {"direction:" + emptied: {"x": 1, "y": 2}}})
        self.org.action({"action": "collapse", "id": emptied, "collapsed": True})
        before = self.org.snapshot()
        self.org.action({"action": "membership", "keys": ["a"], "remove": [emptied]})
        self.assertIn(emptied, [d["id"] for d in self.org.snapshot()["directions"]])
        result = self.org.action({"action": "membership", "keys": ["b"], "remove": [emptied]})
        ids = [d["id"] for d in result["directions"]]
        # Only the category this edit emptied goes; a still-empty new category stays.
        self.assertEqual(ids, [kept, untouched])
        self.assertEqual([d["rank"] for d in result["directions"]], [0, 1])
        self.assertEqual(result["positions"], {})
        self.assertEqual(result["collapsed"], [])
        self.assertEqual(result["undo"]["label"], "调整分类")
        self.org.action({"action": "undo"})
        restored = self.org.action({"action": "undo"})
        restored["revision"] = before["revision"]
        self.assertEqual(restored, before)

    def test_emptied_subcategory_is_deleted_and_empty_ancestors_follow(self):
        parent = self.direction(name="Parent")
        busy = self.direction(name="Busy")
        child = self.org.action({"action": "direction-save", "name": "Child", "color": "#123456",
                                 "parent_id": parent})["directions"][-1]["id"]
        sibling = self.org.action({"action": "direction-save", "name": "Sibling", "color": "#123456",
                                   "parent_id": busy})["directions"][-1]["id"]
        self.org.action({"action": "membership", "keys": ["a"], "add": [child, sibling, busy]})
        result = self.org.action({"action": "membership", "keys": ["a"], "remove": [child, sibling]})
        self.assertEqual([d["id"] for d in result["directions"]], [busy])

    def test_category_holding_only_an_unsaved_paper_counts_as_empty(self):
        direction = self.direction()
        self.org.action({"action": "membership", "keys": ["a", "b"], "add": [direction]})
        self.store.remove_from_library("b")
        result = self.org.action({"action": "membership", "keys": ["a"], "remove": [direction]})
        self.assertEqual(result["directions"], [])
        self.store.save_to_library("b")
        self.assertEqual(self.item(self.org.snapshot(), "b")["directions"], [])


if __name__ == "__main__":
    unittest.main()
