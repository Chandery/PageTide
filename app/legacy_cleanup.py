"""One-time removal of the untouched "default project" that older desktop builds created on first launch.

Old builds made a project with the literal id `default_project` (name 默认项目), ten world-model seed papers and an
automatic fetch on the very first start, whether the person wanted them or not. This build creates none of that, so a
library that still holds exactly that auto-made state is cleaned once. Anything the person did makes the whole check fail
and nothing is touched: it deletes data, so it is deliberately cautious (ADR 0042, "旧默认项目的自动清理").

The check runs once per library (result kept in settings under `legacy_default_cleanup`, no migration number is used because
several branches open the same real database). Before deleting, a consistent copy is written next to the database
(`<db>.pre-legacy-cleanup.bak`); the deletion and the marker are one transaction, rolled back on any error.
"""
import json
import sqlite3

KEY = "legacy_default_cleanup"
PROJECT = "default_project"
NAMES = ("默认项目", "Default project")
BACKUP_SUFFIX = ".pre-legacy-cleanup.bak"

# Settings the old first start wrote or derived by itself (keyed `<name>_default_project`).
AUTO_SETTINGS = ("seed_keys", "last_refresh", "last_refresh_result", "last_attempt", "last_error",
                 "recommendation_eligibility", "route_recall", "source_publication_anomalies")
# Settings only a person's own action creates: their presence means the project was used.
INTENT_SETTINGS = ("project_goal", "import_seed_keys", "route_revision", "route_revision_attempt", "route_plan_project",
                   "profile_freeze", "project_default_terms", "route_directions")
EMPTY_ORGANIZATION = {"directions": [], "memberships": {}, "positions": {}, "protected": []}
AUTO_PROFILE_PROJECTS = ("default", "world-models")   # `project` in the profile version the first start wrote (note "initial")


def now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _count(conn, sql, args=()):
    return conn.execute(sql, args).fetchone()[0]


def _empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return True
        try:
            value = json.loads(value)
        except ValueError:
            return False
    return value in ([], {}, "", None)


def linked_papers(conn):
    keys = {r[0] for r in conn.execute("SELECT paper_key FROM project_papers WHERE project_id=?", (PROJECT,))}
    keys |= {r[0] for r in conn.execute("SELECT key FROM papers WHERE project_id=?", (PROJECT,))}
    return keys


def blocker(conn):
    """None when the library holds exactly the untouched auto-made default project, else why it is not that."""
    tables = _tables(conn)
    row = conn.execute("SELECT * FROM projects WHERE id=?", (PROJECT,)).fetchone() if "projects" in tables else None
    if row is None:
        return "no_default_project"
    cols = row.keys() if hasattr(row, "keys") else []
    if row["name"] not in NAMES:
        return "renamed"
    if row["creation_mode"] not in (None, "manual"):
        return "creation_mode"
    for column in ("keywords", "guidance_transcript", "recommended_learning_path", "discipline"):
        if column in cols and not _empty(row[column]):
            return "project_" + column
    if "language_policy_revision" in cols and (row["language_policy_revision"] or 0) > 1:
        return "language_policy"

    paper_keys = linked_papers(conn)
    if _count(conn, "SELECT COUNT(*) FROM feedback WHERE project_id=? OR project_id IS NULL", (PROJECT,)):
        return "feedback"
    if _count(conn, "SELECT COUNT(*) FROM project_library WHERE project_id=?", (PROJECT,)):
        return "library"
    for key in paper_keys:
        if conn.execute("SELECT 1 FROM library WHERE paper_key=?", (key,)).fetchone():
            return "library"
    if _count(conn, "SELECT COUNT(*) FROM qa_history WHERE project_id=? OR project_id IS NULL", (PROJECT,)):
        return "qa_history"
    if "project_guidance_sessions" in tables:
        for (draft,) in conn.execute("SELECT draft FROM project_guidance_sessions"):
            if PROJECT in str(draft):
                return "guidance"
    for table in ("org_notes", "org_drafts"):
        if table in tables:
            column = "text"
            for (text,) in conn.execute(f"SELECT {column} FROM {table} WHERE project IN (?,?)", (PROJECT, "default")):
                if text and str(text).strip():
                    return "notes"
    if "org_events" in tables and _count(conn, "SELECT COUNT(*) FROM org_events WHERE project=?", (PROJECT,)):
        return "organization"
    if "org_projects" in tables:
        found = conn.execute("SELECT data FROM org_projects WHERE project=?", (PROJECT,)).fetchone()
        if found:
            try:
                data = json.loads(found[0])
            except ValueError:
                return "organization"
            if any(not _empty(v) for v in data.values()):
                return "organization"
    if "import_batches" in tables and _count(conn, "SELECT COUNT(*) FROM import_batches WHERE project_id=?", (PROJECT,)):
        return "import"
    for (name,) in conn.execute("SELECT key FROM settings WHERE key LIKE ?", ("%" + PROJECT + "%",)):
        base = name[:-len(PROJECT) - 1] if name.endswith("_" + PROJECT) else None
        if base in AUTO_SETTINGS:
            continue
        return "setting:" + (base or name)
    for key in paper_keys:   # reading: a stored PDF or full text means the person opened or imported the paper
        for table in ("pdfs", "pdf_versions", "fulltext"):
            if table in tables and conn.execute(f"SELECT 1 FROM {table} WHERE paper_key=?", (key,)).fetchone():
                return "reading"
    for version in conn.execute("SELECT note, data FROM profile_versions"):
        if version["note"] in ("pin", "restore"):
            try:
                owner = json.loads(version["data"]).get("project_id", PROJECT)
            except ValueError:
                return "pinned_terms"
            if owner == PROJECT:
                return "pinned_terms"
    return None


def _write_marker(conn, result):
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)",
                 (KEY, json.dumps({"done_at": now(), "result": result}, ensure_ascii=False)))


def _delete_everything(conn):
    """Inside the caller's transaction. Returns what was deleted."""
    tables = _tables(conn)
    deleted = {}
    candidates = linked_papers(conn)
    batches = [r[0] for r in conn.execute("SELECT id FROM batches WHERE project_id=?", (PROJECT,))]
    deleted["exposures"] = sum(conn.execute("DELETE FROM exposures WHERE batch_id=?", (b,)).rowcount for b in batches)
    deleted["batches"] = conn.execute("DELETE FROM batches WHERE project_id=?", (PROJECT,)).rowcount
    deleted["project_papers"] = conn.execute("DELETE FROM project_papers WHERE project_id=?", (PROJECT,)).rowcount
    deleted["profile_snapshots"] = conn.execute("DELETE FROM profile_snapshots WHERE project_id=?", (PROJECT,)).rowcount
    deleted["weekly_reports"] = conn.execute("DELETE FROM weekly_reports WHERE project_id=?", (PROJECT,)).rowcount
    for table in ("org_projects", "org_notes", "org_events", "org_drafts"):
        if table in tables:
            conn.execute(f"DELETE FROM {table} WHERE project=?", (PROJECT,))
    names = AUTO_SETTINGS + INTENT_SETTINGS
    conn.executemany("DELETE FROM settings WHERE key=?", [(f"{n}_{PROJECT}",) for n in names])
    # Papers that belonged only to this project: no other project links them, nobody saved or rated them, nothing else shows them.
    gone = 0
    for key in sorted(candidates):
        if conn.execute("SELECT 1 FROM project_papers WHERE paper_key=?", (key,)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM project_library WHERE paper_key=?", (key,)).fetchone() or \
           conn.execute("SELECT 1 FROM library WHERE paper_key=?", (key,)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM feedback WHERE paper_key=?", (key,)).fetchone() or \
           conn.execute("SELECT 1 FROM qa_history WHERE paper_key=?", (key,)).fetchone() or \
           conn.execute("SELECT 1 FROM exposures WHERE paper_key=?", (key,)).fetchone():
            continue
        if "import_items" in tables and conn.execute("SELECT 1 FROM import_items WHERE paper_key=?", (key,)).fetchone():
            continue
        conn.execute("DELETE FROM summaries WHERE paper_key=?", (key,))
        if "fulltext_languages" in tables:
            conn.execute("DELETE FROM fulltext_languages WHERE paper_key=?", (key,))
        conn.execute("DELETE FROM settings WHERE key=?", ("pdf_verification_" + key,))
        conn.execute("DELETE FROM papers WHERE key=?", (key,))
        gone += 1
    deleted["papers"] = gone
    # What stays (shared with another project) no longer points at the removed project.
    conn.execute("UPDATE papers SET project_id=NULL WHERE project_id=?", (PROJECT,))
    deleted["projects"] = conn.execute("DELETE FROM projects WHERE id=?", (PROJECT,)).rowcount
    # The profile version the first start wrote ("initial", no pinned terms). It is global, so it goes only when it is
    # all that is left: no project remains and no other kind of version exists.
    deleted["profile_versions"] = 0
    if not conn.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
        versions = conn.execute("SELECT id, note, data FROM profile_versions").fetchall()
        def auto(v):
            try:
                data = json.loads(v["data"])
            except ValueError:
                return False
            return v["note"] == "initial" and data.get("project") in AUTO_PROFILE_PROJECTS and not data.get("pinned_terms")
        if versions and all(auto(v) for v in versions):
            deleted["profile_versions"] = conn.execute("DELETE FROM profile_versions").rowcount
    return deleted


def run(store, backup_path=None):
    """Check once, clean if (and only if) the library is exactly the untouched default project. Returns the stored
    result dict, or None when it had already run. Never raises: a failure is rolled back and recorded."""
    conn = store.conn
    try:
        with store._lock:
            if conn.in_transaction:
                return None
            if conn.execute("SELECT 1 FROM settings WHERE key=?", (KEY,)).fetchone():
                return None
            why = blocker(conn)
            if why is not None:
                conn.execute("BEGIN IMMEDIATE")
                _write_marker(conn, "kept" if why == "no_default_project" else "kept: " + why)
                conn.commit()
                return {"result": "kept" if why == "no_default_project" else "kept: " + why}
            target = backup_path or store.path.with_name(store.path.name + BACKUP_SUFFIX)
            store.backup(target)
            conn.execute("BEGIN IMMEDIATE")
            try:
                if conn.execute("SELECT 1 FROM settings WHERE key=?", (KEY,)).fetchone() or blocker(conn) is not None:
                    conn.rollback()
                    return None
                deleted = _delete_everything(conn)
                _write_marker(conn, {"cleaned": deleted, "backup": str(target)})
                conn.commit()
                return {"result": {"cleaned": deleted, "backup": str(target)}}
            except BaseException as exc:
                conn.rollback()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    _write_marker(conn, "failed: " + type(exc).__name__ + ": " + str(exc)[:200])
                    conn.commit()
                except sqlite3.Error:
                    conn.rollback()
                return {"result": "failed: " + str(exc)}
    except sqlite3.Error as exc:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return {"result": "failed: " + str(exc)}
