"""Moving the library to a folder the person chooses (app/data_location.py) and the settings API around it."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import data_location
from app.data_location import MoveError


def library(folder, rows=3):
    """A small library: a WAL database with rows, a PDF, a nested cache file and the files a move must skip."""
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "pagetide.sqlite")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE papers(key TEXT)")
    conn.executemany("INSERT INTO papers VALUES (?)", [(f"p{i}",) for i in range(rows)])
    conn.commit()
    (folder / "pdfs").mkdir(exist_ok=True)
    (folder / "pdfs" / "a.pdf").write_bytes(b"%PDF-1.4 test")
    (folder / "cache" / "deep").mkdir(parents=True, exist_ok=True)
    (folder / "cache" / "empty").mkdir()
    (folder / "cache" / "deep" / "x.json").write_text("{}")
    (folder / ".desktop.lock").write_text("")
    (folder / "operation-locks").mkdir(exist_ok=True)
    (folder / "operation-locks" / "lock").write_text("")
    return conn


def keys(db):
    with sqlite3.connect(db) as conn:
        return [r[0] for r in conn.execute("SELECT key FROM papers ORDER BY key")]


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.default = self.root / "default"


class ResolveTests(Base):
    def test_no_pointer_means_the_default_folder(self):
        self.assertEqual(data_location.resolve(self.default), (self.default, None))

    def test_a_pointer_to_a_library_is_followed(self):
        library(self.root / "elsewhere").close()
        data_location.write_pointer(self.default, self.root / "elsewhere")
        self.assertEqual(data_location.resolve(self.default), (self.root / "elsewhere", None))

    def test_a_pointer_to_a_missing_library_falls_back_and_says_where_it_looked(self):
        data_location.write_pointer(self.default, self.root / "unplugged")
        self.assertEqual(data_location.resolve(self.default), (self.default, str(self.root / "unplugged")))

    def test_pointing_at_the_default_folder_removes_the_pointer(self):
        data_location.write_pointer(self.default, self.root / "x")
        data_location.write_pointer(self.default, self.default)
        self.assertFalse((self.default / "location.json").exists())


class InspectTests(Base):
    def setUp(self):
        super().setUp()
        library(self.default).close()

    def kind(self, folder):
        return data_location.inspect(str(self.default), str(folder))

    def reason(self, folder):
        with self.assertRaises(MoveError) as caught:
            self.kind(folder)
        return caught.exception.reason

    def test_folders_that_cannot_be_used(self):
        self.assertEqual(self.reason("relative/path"), "invalid")
        self.assertEqual(self.reason(""), "invalid")
        self.assertEqual(self.reason(self.root / "nope"), "not_found")
        self.assertEqual(self.reason(self.default), "same")
        (self.default / "inner").mkdir()
        self.assertEqual(self.reason(self.default / "inner"), "inside_current")

    def test_what_each_kind_of_folder_becomes(self):
        (self.root / "empty").mkdir()
        self.assertEqual(self.kind(self.root / "empty"), {"kind": "empty", "target": str(self.root / "empty")})
        (self.root / "docs").mkdir(); (self.root / "docs" / "note.txt").write_text("mine")
        self.assertEqual(self.kind(self.root / "docs"), {"kind": "subfolder", "target": str(self.root / "docs" / "PageTide")})
        library(self.root / "old").close()
        self.assertEqual(self.kind(self.root / "old")["kind"], "library")
        library(self.root / "docs2" / "PageTide").close()
        self.assertEqual(self.kind(self.root / "docs2"), {"kind": "library", "target": str(self.root / "docs2" / "PageTide")})
        (self.root / "busy" / "PageTide").mkdir(parents=True); (self.root / "busy" / "PageTide" / "x").write_text("")
        self.assertEqual(self.reason(self.root / "busy"), "occupied")


class MoveTests(Base):
    def setUp(self):
        super().setUp()
        self.conn = library(self.default)
        self.addCleanup(self.conn.close)

    def test_the_library_is_copied_checked_and_pointed_at_and_the_old_folder_is_untouched(self):
        (self.root / "new").mkdir()
        before = sorted(p.relative_to(self.default) for p in self.default.rglob("*"))
        seen = []
        out = data_location.move(self.default, str(self.root / "new"), self.default, lambda d, t: seen.append((d, t)))
        new = self.root / "new"
        self.assertEqual((out["data_dir"], out["kind"]), (str(new), "empty"))
        self.assertEqual(keys(new / "pagetide.sqlite"), ["p0", "p1", "p2"])   # rows still in the WAL are in the copy
        self.assertEqual((new / "pdfs" / "a.pdf").read_bytes(), b"%PDF-1.4 test")
        self.assertTrue((new / "cache" / "deep" / "x.json").is_file())
        self.assertTrue((new / "cache" / "empty").is_dir())                  # empty folders come along too
        for skipped in (".desktop.lock", "operation-locks", "location.json"):   # the copy may open its own -wal; the old one is never copied
            self.assertFalse((new / skipped).exists(), skipped)
        self.assertFalse(list(new.glob(".pagetide-moving-*")))
        self.assertEqual(sorted(p.relative_to(self.default) for p in self.default.rglob("*") if p.name != "location.json"), before)
        self.assertEqual(data_location.read_pointer(self.default), str(new))
        self.assertEqual(seen[-1][0], seen[-1][1])

    def test_a_folder_with_other_files_gets_a_pagetide_subfolder(self):
        (self.root / "docs").mkdir(); (self.root / "docs" / "note.txt").write_text("mine")
        out = data_location.move(self.default, str(self.root / "docs"), self.default)
        self.assertEqual(out["data_dir"], str(self.root / "docs" / "PageTide"))
        self.assertEqual((self.root / "docs" / "note.txt").read_text(), "mine")
        self.assertEqual(sorted(p.name for p in (self.root / "docs").iterdir()), ["PageTide", "note.txt"])

    def test_an_existing_library_is_used_as_it_is_and_never_overwritten(self):
        other = library(self.root / "old", rows=1); other.close()
        out = data_location.move(self.default, str(self.root / "old"), self.default)
        self.assertEqual((out["kind"], out["copied"]), ("library", 0))
        self.assertEqual(keys(self.root / "old" / "pagetide.sqlite"), ["p0"])
        self.assertEqual(data_location.read_pointer(self.default), str(self.root / "old"))

    def test_a_database_written_during_the_copy_is_copied_again(self):
        (self.root / "new").mkdir()
        wrote = []

        def progress(done, total):
            if not wrote:
                self.conn.execute("INSERT INTO papers VALUES ('late')"); self.conn.commit(); wrote.append(1)
        data_location.move(self.default, str(self.root / "new"), self.default, progress)
        self.assertIn("late", keys(self.root / "new" / "pagetide.sqlite"))

    def test_a_failed_copy_leaves_no_partial_folder_and_no_pointer(self):
        (self.root / "new").mkdir()
        with mock.patch.object(data_location.shutil, "copy2", side_effect=OSError("disk full")):
            with self.assertRaises(MoveError) as caught:
                data_location.move(self.default, str(self.root / "new"), self.default)
        self.assertEqual(caught.exception.reason, "copy_failed")
        self.assertEqual(list((self.root / "new").iterdir()), [])
        self.assertIsNone(data_location.read_pointer(self.default))
        self.assertEqual(keys(self.default / "pagetide.sqlite"), ["p0", "p1", "p2"])


    def test_a_wal_database_nobody_has_open_is_copied_too(self):
        # e.g. paperdig.sqlite left by an older version: WAL mode, no -shm, so it cannot be opened read-only
        legacy = sqlite3.connect(self.default / "legacy.sqlite")
        legacy.execute("PRAGMA journal_mode=WAL"); legacy.execute("CREATE TABLE t(x)"); legacy.execute("INSERT INTO t VALUES (7)")
        legacy.commit(); legacy.close()
        self.assertFalse((self.default / "legacy.sqlite-shm").exists())
        (self.root / "new").mkdir()
        data_location.move(self.default, str(self.root / "new"), self.default)
        with sqlite3.connect(self.root / "new" / "legacy.sqlite") as copy:
            self.assertEqual(copy.execute("SELECT x FROM t").fetchall(), [(7,)])


    def test_a_database_error_during_the_copy_also_leaves_nothing_behind(self):
        (self.root / "new").mkdir()
        with mock.patch.object(data_location, "_backup", side_effect=sqlite3.OperationalError("unable to open database file")):
            with self.assertRaises(MoveError) as caught:
                data_location.move(self.default, str(self.root / "new"), self.default)
        self.assertEqual(caught.exception.reason, "copy_failed")
        self.assertEqual(list((self.root / "new").iterdir()), [])
        self.assertIsNone(data_location.read_pointer(self.default))


class ServerTests(Base):
    def setUp(self):
        super().setUp()
        from app import server
        self.server = server
        library(self.default).close()

    def place(self, source):
        env = {"PAGETIDE_DATA_SOURCE": source, "PAGETIDE_DEFAULT_DATA": str(self.default)}
        with mock.patch.dict(os.environ, env):
            return self.server._location(str(self.default))

    def test_only_the_desktop_default_or_a_moved_library_can_be_moved(self):
        self.assertTrue(self.place("default")["movable"])
        self.assertTrue(self.place("moved")["movable"] and self.place("moved")["moved"])
        self.assertFalse(self.place("env")["movable"])
        self.assertFalse(self.place("")["movable"])              # a source run (python -m app.server) has no default to point from
        out = self.place("default")
        self.assertEqual((out["data_dir"], out["default_dir"], out["move"]["state"] in ("idle", "done", "failed")),
                         (str(self.default), str(self.default), True))

    def test_a_move_waits_for_background_work(self):
        with self.server.JOBS_LOCK:
            self.server.JOBS["job-test"] = {"id": "job-test", "state": "running"}
        try:
            self.assertTrue(self.server._busy())
        finally:
            with self.server.JOBS_LOCK:
                del self.server.JOBS["job-test"]


class StartTests(Base):
    """What the desktop backend opens at start (app/desktop.py choose_data_root)."""

    def choose(self, **env):
        from app import desktop
        environ = {"HOME": str(self.root), **env}
        with mock.patch.object(desktop.platform_compat, "default_data_dir", return_value=self.default):
            return desktop.choose_data_root(environ), environ

    def test_the_default_folder_then_the_moved_one_then_a_fallback_when_it_is_gone(self):
        library(self.default).close()
        root, env = self.choose()
        self.assertEqual((root, env["PAGETIDE_DATA_SOURCE"], env["PAGETIDE_DEFAULT_DATA"]), (self.default, "default", str(self.default)))
        (self.root / "new").mkdir()
        data_location.move(self.default, str(self.root / "new"), self.default)
        root, env = self.choose()
        self.assertEqual((root, env["PAGETIDE_DATA_SOURCE"]), (self.root / "new", "moved"))
        (self.root / "new" / "pagetide.sqlite").unlink()          # the drive is gone: back to the library the move started from
        root, env = self.choose()
        self.assertEqual((root, env["PAGETIDE_DATA_SOURCE"], env["PAGETIDE_DATA_MISSING"]), (self.default, "default", str(self.root / "new")))

    def test_an_environment_choice_wins_and_cannot_be_moved(self):
        root, env = self.choose(PAGETIDE_DATA=str(self.root / "chosen"))
        self.assertEqual((root, env["PAGETIDE_DATA_SOURCE"]), (self.root / "chosen", "env"))


    def test_a_failed_move_gives_the_page_a_reason_and_keeps_the_details_in_a_log(self):
        import time
        from app import server
        library(self.default).close()
        (self.root / "new").mkdir()
        with mock.patch.dict(os.environ, {"PAGETIDE_DEFAULT_DATA": str(self.default)}), \
                mock.patch.object(data_location, "_backup", side_effect=sqlite3.OperationalError("unable to open database file")):
            self.assertTrue(server._move_start(str(self.default), str(self.root / "new"))["ok"])
            for _ in range(100):
                with server.MOVE_LOCK:
                    if server.MOVE.get("state") != "running":
                        break
                time.sleep(.02)
        with server.MOVE_LOCK:
            self.assertEqual((server.MOVE["state"], server.MOVE["reason"]), ("failed", "copy_failed"))
        self.assertIn("unable to open database file", (self.default / "logs" / "move.log").read_text())


class WiringTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_the_settings_page_chooses_a_folder_natively_and_restarts_through_the_shell(self):
        page = (self.ROOT / "app/static/settings.html").read_text()
        self.assertIn('<button type="button" id="moveDataBtn" hidden>更改…</button>', page)   # shown only when the folder can move
        self.assertIn("invoke('pick_folder'", page)
        self.assertIn("invoke('relaunch')", page)
        self.assertIn("action:'inspect'", page)
        self.assertIn("if(!await window.PTDialogs.confirm(question))return;", page)          # nothing is copied without a yes
        rust = (self.ROOT / "src-tauri/src/main.rs").read_text()
        self.assertIn("generate_handler![save_export, complete_quit, pick_folder, relaunch]", rust)
        self.assertIn('"allow-pick-folder", "allow-relaunch"', rust)
        self.assertIn('"pick_folder", "relaunch"', (self.ROOT / "src-tauri/build.rs").read_text())


if __name__ == "__main__":
    unittest.main()
