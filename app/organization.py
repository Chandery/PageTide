"""Project-scoped library organization on an initialized Store.conn.

action accepts {action: ..., revision?: int, ...} ('op' is an alias).
Mutations return snapshot();
history returns {key, history, revision}; export returns a JSON-serializable
archive including unsaved items and note history. Validation raises ValueError,
optimistic conflicts raise Conflict, unavailable clustering raises
ClusteringUnavailable. No HTTP, filesystem export, or model integration here.

The saved corpus is the existing global library. Organization data and notes
are project-local; only 'default' imports legacy library.note. Graph position
IDs are 'paper:<key>', 'direction:<id>', 'paper:<URL-encoded-key>:<direction-id>'
and 'direction:<id>:anchor'. Empty direction IDs identify the unclassified
group. collapse accepts {id, collapsed: bool}; snapshot.collapsed lists IDs.
apply-suggestions accepts {fingerprint, suggestions?: [{id,name,color,keys}]};
selected keys must be a subset of each stored preview group. Existing manual
data is never overwritten. Undo is project-local LIFO; note
undo appends a fresh version, never rewinds history. Caller must not have an
active transaction or concurrently share its connection outside Store._lock.

Drafts are application-owned, not browser-origin storage. draft-save requires
{key, client, text, version}; draft-clear requires {key, client, version}.
New client tokens start at version 0. Both return {draft, revision} without
changing organization revision/undo. drafts accepts an optional key filter.
snapshot.drafts excludes cleared tombstones; distinct clients never overwrite
one another. A caller restores a draft by adopting its client and version.
"""
import itertools
import json
import math
import os
import re
import sqlite3
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote

from . import category_review_units as review_units, eligibility, pathgraph, pathgrowth, route_revision
from .clustering import cluster, corpus_fingerprint
from .organization_terms import category_identity, category_term
from .organization_facets import paper_signature, review as review_papers, structure_hash, suggest_groups
from .db import now


def read_route(conn, project):
    """(revision, the project's route block or None) by a plain read: it creates no tables, rows or backups."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='org_projects'").fetchone():
        return 0, None
    row = conn.execute("SELECT revision,data FROM org_projects WHERE project=?", (project,)).fetchone()
    return (row[0], json.loads(row[1]).get("route")) if row else (0, None)


def saved_corpus(conn, scope=None):
    """The saved papers; with `scope` (a project id) only the ones that project saved."""
    if scope:
        return [dict(row) for row in conn.execute("""SELECT p.* FROM papers p
            JOIN library l ON p.key=l.paper_key
            WHERE p.key IN (SELECT paper_key FROM project_library WHERE project_id=?) ORDER BY p.key""", (scope,))]
    return [dict(row) for row in conn.execute("""SELECT p.* FROM papers p
        JOIN library l ON p.key=l.paper_key ORDER BY p.key""")]


ROUTE_DETAIL_MAX_PAPERS = 120   # the second view draws what can be read, and says how many it left out


def route_detail(conn, project_id, focus_key=None, *, paper_rows=None):
    """The data of the library graph's second view (the learning map): one project's learning units and the papers it saved.

    Read-only and derived. A paper is matched to the (at most two) units whose terms its local retrieval text
    uses (pathgrowth.assign); the service supplies bounded current-body rows when no usable abstract exists.
    The terms and source travel with the match so the line can be
    explained. Nothing is stored: matches are not part of anyone's classification, and a paper that fits no
    unit is listed, not hidden. Unknown project: ValueError. No learning map: {"available": False}."""
    _text(project_id, "project_id", 200)
    if focus_key is not None:
        _text(focus_key, "focus_key", 2000)
    if not conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
        raise ValueError("项目不存在")
    _, route = read_route(conn, project_id)
    graph = (route or {}).get("graph") or {}
    live = [c for c in graph.get("concepts", []) if c.get("state", "active") != "archived"]
    if not live:
        return {"available": False, "reason": "no_route", "project_id": project_id}
    ids = {c["id"] for c in live}
    edges = [e for e in graph.get("prereqs", []) if e["from"] in ids and e["to"] in ids]
    shown = {"concepts": live, "prereqs": edges, "targets": [t for t in graph.get("targets", []) if t in ids]}
    level = pathgraph.layers(shown)
    papers = saved_corpus(conn, project_id)
    prepared = {p['key']: p for p in (paper_rows or [])}
    papers = [prepared.get(p['key'], p) for p in papers]
    pending = {p['key'] for p in papers if not eligibility.usable_abstract(p.get('abstract')) and (p.get('_eligibility') or {}).get('reason') == 'source_verification_deferred'}
    assigned = pathgrowth.assign(shown, [p for p in papers if p['key'] not in pending])
    by_id = {c["id"]: c for c in live}
    matches = []
    for paper in papers:
        for rank, unit in enumerate(assigned.get(paper["key"], [])):
            text = eligibility.retrieval_text(paper)
            terms = [t for t in by_id[unit].get("terms", []) if pathgrowth.term_in_text(text, t)]
            matches.append({"paper": paper["key"], "unit": unit, "rank": rank, "terms": terms,
                            "source": "local_body" if not eligibility.usable_abstract(paper.get('abstract')) and paper.get('_local_body') else "title_abstract"})
    matched = {m["paper"] for m in matches}
    ordered = [p for p in papers if p["key"] in matched] + [p for p in papers if p["key"] not in matched]
    kept = ordered[:ROUTE_DETAIL_MAX_PAPERS]
    # Keep a selected saved paper navigable even when the graph omits a large library's tail.
    focused = next((p for p in ordered if p["key"] == focus_key), None)
    if focused and focused not in kept:
        kept[-1:] = [focused]
    kept_keys = {p["key"] for p in kept}
    return {"available": True, "project_id": project_id,
            "units": [{"id": c["id"], "name": c["name"], "terms": c.get("terms", []), "hint": c.get("hint", 2),
                       "type": c.get("type"), "why": c.get("why"), "state": c.get("state", "active"),
                       "side": bool(c.get("side")), "level": level[c["id"]]} for c in live],
            "prereqs": [{"from": e["from"], "to": e["to"], "state": e.get("state", "active")} for e in edges],
            "papers": [{"key": p["key"], "title": p.get("title") or p["key"], "published": p.get("published")} for p in kept],
            "matches": [m for m in matches if m["paper"] in kept_keys],
            "unmatched": [p["key"] for p in kept if p["key"] not in matched and p['key'] not in pending],
            "unmatched_total": len(papers) - len(matched) - len(pending),
            "pending": [p['key'] for p in kept if p['key'] in pending], "pending_total": len(pending),
            "omitted": len(ordered) - len(kept)}


def paper_context(conn, paper, project_id):
    """Read-only facts for the same paper in both graphs; never writes categories or learning progress."""
    _text(project_id, "project_id", 200)
    if not conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
        raise ValueError("项目不存在")
    categories = []
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='org_projects'").fetchone():
        row = conn.execute("SELECT data FROM org_projects WHERE project='default'").fetchone()
        data = json.loads(row[0]) if row else {}
        member_ids = set(data.get("memberships", {}).get(paper["key"], []))
        categories = [{"id": d["id"], "name": d["name"]} for d in data.get("directions", []) if d["id"] in member_ids]
    _, route = read_route(conn, project_id)
    graph = (route or {}).get("graph") or {"concepts": []}
    live = [c for c in graph["concepts"] if c.get("state", "active") != "archived"]
    pending = not eligibility.usable_abstract(paper.get('abstract')) and (paper.get('_eligibility') or {}).get('reason') == 'source_verification_deferred'
    assigned = [] if pending else pathgrowth.assign({"concepts": live}, [paper]).get(paper["key"], [])
    by_id = {c["id"]: c for c in live}
    # Only the current project batch supplies a 'this recommendation' purpose. Old exposures remain history.
    exposure = conn.execute("""SELECT b.id, e.route_kind, e.route_name FROM batches b
        JOIN exposures e ON e.batch_id=b.id WHERE b.id=(SELECT MAX(id) FROM batches WHERE project_id=?)
        AND e.paper_key=?""", (project_id, paper["key"])).fetchone()
    return {"project_id": project_id, "categories": categories,
            "units": [{"id": cid, "name": by_id[cid]["name"]} for cid in assigned],
            "matching_status": "pending" if pending else "ready",
            "matching_source": "local_body" if not eligibility.usable_abstract(paper.get('abstract')) and paper.get('_local_body') else "title_abstract",
            "map_available": bool(live), "route_enabled": bool(route and route.get("mode", "route") == "route"),
            "saved_in_project": bool(conn.execute("SELECT 1 FROM project_library WHERE project_id=? AND paper_key=?",
                                                   (project_id, paper["key"])).fetchone()),
            "recommendation": {"batch_id": exposure["id"], "kind": exposure["route_kind"] or "normal",
                               "name": exposure["route_name"]} if exposure else None}


class Conflict(ValueError):
    """The revision, note version, or suggestion corpus is stale."""


SCHEMA = (
    """CREATE TABLE org_projects (
        project TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)""",
    """CREATE TABLE org_notes (
        project TEXT NOT NULL, paper_key TEXT NOT NULL, version INTEGER NOT NULL,
        text TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(project, paper_key, version))""",
    """CREATE TABLE org_events (
        id INTEGER PRIMARY KEY, project TEXT NOT NULL, before_data TEXT NOT NULL,
        note_key TEXT, note_before TEXT, undone INTEGER NOT NULL DEFAULT 0, label TEXT)""",
    "CREATE INDEX org_events_project ON org_events(project, undone, id)",
    # Capture legacy notes even when a caller uses Store directly after migration.
    """CREATE TRIGGER org_library_insert AFTER INSERT ON library BEGIN
        INSERT OR IGNORE INTO org_notes VALUES
        ('default', NEW.paper_key, 0, COALESCE(NEW.note, ''), strftime('%Y-%m-%dT%H:%M:%SZ','now'));
        END""",
    """CREATE TRIGGER org_library_delete BEFORE DELETE ON library BEGIN
        INSERT OR IGNORE INTO org_notes VALUES
        ('default', OLD.paper_key, 0, COALESCE(OLD.note, ''), strftime('%Y-%m-%dT%H:%M:%SZ','now'));
        END""",
)

# What the undo button names. Layout events (dragging, folding) stay undoable in
# history order but are never offered on their own: the owner cannot see them.
LAYOUT_LABELS = ("调整布局", "折叠目录")

DRAFT_SCHEMA = """CREATE TABLE IF NOT EXISTS org_drafts (
    project TEXT NOT NULL, paper_key TEXT NOT NULL, client TEXT NOT NULL,
    version INTEGER NOT NULL, text TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY(project, paper_key, client))"""


def _dump(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)


def _text(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("%s must be a nonempty string of at most %d characters" % (label, limit))
    return value


def _version(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(label + " must be a nonnegative integer")
    return value


ROUTE_OPS = {"route-save", "route-manual", "route-watch", "route-start", "route-mode", "route-reject"}
ROUTE_SAVE_LABELS = {"candidate": "加入新方向"}   # what the undo button says when a save adds a proposed direction
MAX_REJECTED = 100
ROUTE_MARKS = {"mastered", "unlocked", "demoted"}
IMPORT_MAX_GROUPS = 5000   # folders in one import
IMPORT_MAX_DEPTH = 3       # deeper folders fold into their third-level ancestor
IMPORT_NAME_MAX = 60
IMPORT_COLORS = ("#167b70", "#3b6fb6", "#b5651d", "#8a4fb0", "#c0392b", "#5b7f2b", "#a8325e", "#4a5568")
MAX_PLAN_CONCEPTS = 200   # a plan from an AI or a person is a dozen concepts; this only bounds hostile input


class Organization:
    def __init__(self, store, project="default"):
        self.store, self.conn = store, store.conn
        self.project = _text(project, "project")
        self.lock = getattr(store, "_lock", threading.RLock())
        self.backup_path = None
        with self._transaction():
            exists = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='org_projects'"
            ).fetchone()
            if not exists:
                self._backup()
                for statement in SCHEMA:
                    self.conn.execute(statement)
                self.conn.execute("""INSERT INTO org_notes
                    SELECT 'default', paper_key, 0, COALESCE(note,''), saved_at FROM library""")
            self.conn.execute(DRAFT_SCHEMA)
            if "label" not in {row[1] for row in self.conn.execute("PRAGMA table_info(org_events)")}:
                # Additive, nullable column; legacy events keep NULL and are never offered by name.
                self._backup()
                self.conn.execute("ALTER TABLE org_events ADD COLUMN label TEXT")
            self.conn.execute("INSERT OR IGNORE INTO org_projects VALUES (?,0,?)",
                              (project, _dump({"directions": [], "memberships": {},
                                               "positions": {}, "protected": []})))

    @contextmanager
    def _transaction(self, write=True):
        with self.lock:
            if self.conn.in_transaction:
                raise RuntimeError("Organization requires a connection without an active transaction")
            self.conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise

    def _backup(self):
        path = next(row[2] for row in self.conn.execute("PRAGMA database_list") if row[1] == "main")
        if not path:
            return  # An in-memory database has no persistent original to back up.
        fd, target = tempfile.mkstemp(prefix="." + Path(path).name + ".pre-organization-",
                                      suffix=".sqlite", dir=str(Path(path).parent))
        os.close(fd)  # mkstemp creates mode 0600 before any private data is written.
        try:
            # A separate reader avoids backing up our own active write transaction.
            source = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
            destination = sqlite3.connect(target)
            try:
                source.backup(destination)
                destination.execute("PRAGMA journal_mode=DELETE")
            finally:
                destination.close()
                source.close()
            # Switching the copied WAL database to DELETE can leave an orphan
            # shared-memory file on macOS. The private backup is now closed.
            Path(target + "-shm").unlink(missing_ok=True)
        except BaseException:
            os.unlink(target)
            raise
        self.backup_path = target

    def _load(self):
        row = self.conn.execute("SELECT revision,data FROM org_projects WHERE project=?",
                                (self.project,)).fetchone()
        return row[0], json.loads(row[1])

    def _note(self, key):
        row = self.conn.execute("""SELECT text,version FROM org_notes
            WHERE project=? AND paper_key=? ORDER BY version DESC LIMIT 1""",
                                (self.project, key)).fetchone()
        return (row[0], row[1]) if row else ("", 0)

    def _write_note(self, key, text):
        old, version = self._note(key)
        self.conn.execute("INSERT OR IGNORE INTO org_notes VALUES (?,?,0,?,?)",
                          (self.project, key, old, now()))
        self.conn.execute("INSERT INTO org_notes VALUES (?,?,?,?,?)",
                          (self.project, key, version + 1, text, now()))

    def _history(self, key):
        return [dict(row) for row in self.conn.execute("""SELECT version,text,created_at
            FROM org_notes WHERE project=? AND paper_key=? ORDER BY version""", (self.project, key))]

    def _paper_key(self, key, saved=False):
        _text(key, "key", 2000)
        if not self.conn.execute("SELECT 1 FROM papers WHERE key=?", (key,)).fetchone():
            raise ValueError("Unknown paper: " + key)
        if saved and not self.conn.execute("SELECT 1 FROM library WHERE paper_key=?", (key,)).fetchone():
            raise ValueError("Paper is not saved: " + key)
        return key

    def _snapshot(self, archived=False):
        revision, data = self._load()
        papers = [dict(row) for row in self.conn.execute("""SELECT p.*,l.saved_at
            FROM papers p JOIN library l ON p.key=l.paper_key ORDER BY p.key""")]
        if archived:
            retained = set(data["memberships"])
            retained.update(row[0] for row in self.conn.execute(
                "SELECT DISTINCT paper_key FROM org_notes WHERE project=?", (self.project,)))
            retained.update(row[0] for row in self.conn.execute(
                "SELECT DISTINCT paper_key FROM org_drafts WHERE project=?", (self.project,)))
            retained.update(self._node_parts(node)[0] for node in data["positions"]
                            if node.startswith("paper:"))
            present = {paper["key"] for paper in papers}
            for key in sorted(retained - present):
                row = self.conn.execute("SELECT * FROM papers WHERE key=?", (key,)).fetchone()
                if row:
                    papers.append(dict(row, saved_at=None))
        owners = self._owners()
        understood = {}   # paper -> projects whose latest familiarity label is "understood" (the library shows it)
        for row in self.conn.execute("""SELECT f.paper_key, f.project_id FROM feedback f
            WHERE f.undone=0 AND f.action='understood' AND f.id=(SELECT MAX(g.id) FROM feedback g
              WHERE g.undone=0 AND g.project_id=f.project_id AND g.paper_key=f.paper_key
                AND g.action IN ('understood','too_hard'))"""):
            understood.setdefault(row[0], []).append(row[1])
        for paper in papers:
            key = paper["key"]
            paper["projects"] = owners.get(key, [])
            paper["understood_in"] = understood.get(key, [])
            paper["directions"] = data["memberships"].get(key, [])
            paper["note"], paper["note_version"] = self._note(key)
            if archived:
                paper["history"] = self._history(key)
        result = {"directions": [{**{k: d[k] for k in ("id", "name", "color", "rank")},
                                   "parent_id": d.get("parent_id")}
                                  for d in data["directions"]],
                  "items": papers, "positions": data["positions"], "revision": revision}
        result["projects"] = self._project_names()
        result["route_projects"] = self._route_projects()
        result["collapsed"] = data.get("collapsed", [])
        result["drafts"] = self._drafts()
        event = self._undoable()
        result["undo"] = {"id": event["id"], "label": event["label"]} if event and event["label"] else None
        if data.get("route"):
            result["route"] = data["route"]
        if data.get("suggestions"):
            result["suggestions"] = data["suggestions"]
            result["suggestions"]["stale"] = (
                corpus_fingerprint(self._corpus(data["suggestions"].get("scope"))) != data["suggestions"]["fingerprint"]
                or (data["suggestions"].get("structure") is not None
                    and data["suggestions"]["structure"] != structure_hash(data["directions"], data["memberships"])))
        if archived:
            result.update({"format": "paperdig-organization-v1", "project": self.project,
                           "organization": data})
        return result

    def _owners(self):
        """{paper_key: [project ids that saved it]}, from project_library (the per-project saved set). The
        organization itself stays one shared tree; this only says whose papers are whose, for the view scope."""
        try:
            rows = self.conn.execute("SELECT paper_key, project_id FROM project_library ORDER BY project_id").fetchall()
        except sqlite3.OperationalError:   # a database that predates project_library
            return {}
        owners = {}
        for key, project in rows:
            owners.setdefault(key, []).append(project)
        return owners

    def _route_projects(self):
        """Ids of the projects that have a learning map with at least one live unit: where the second graph view exists."""
        found = []
        for project, raw in self.conn.execute("SELECT project, data FROM org_projects ORDER BY project"):
            try:
                graph = (json.loads(raw).get("route") or {}).get("graph") or {}
            except ValueError:
                continue
            if any(c.get("state", "active") != "archived" for c in graph.get("concepts", [])):
                found.append(project)
        return found

    def _project_names(self):
        try:
            return [{"id": r[0], "name": r[1]} for r in self.conn.execute("SELECT id, name FROM projects ORDER BY creation_timestamp, id")]
        except sqlite3.OperationalError:
            return []

    def _undoable(self):
        """Latest live event the owner would recognise; later layout events ride along."""
        return self.conn.execute("""SELECT * FROM org_events WHERE project=? AND undone=0
            AND (label IS NULL OR label NOT IN (?,?)) ORDER BY id DESC LIMIT 1""",
                                 (self.project,) + LAYOUT_LABELS).fetchone()

    def _corpus(self, scope=None):
        return saved_corpus(self.conn, scope)

    def directions(self):
        """The category tree only ([{id, name, parent_id}]): cheap enough for a page that polls."""
        with self._transaction(write=False):
            return [{"id": d["id"], "name": d["name"], "parent_id": d.get("parent_id")} for d in self._load()[1]["directions"]]

    def snapshot(self):
        with self._transaction(write=False):
            return self._snapshot()

    def action(self, body, *, precondition=None, revision_builder=None, postcondition=None):
        if not isinstance(body, dict):
            raise ValueError("Action must be an object")
        op = body.get("op", body.get("action"))
        if (revision_builder is not None or postcondition is not None) and op != 'route-save':
            raise ValueError('Revision callbacks require route-save')
        if op == "graph":
            with self._transaction(write=False):
                papers = self._corpus()
            result = cluster(papers)
            with self._transaction(write=False):
                if corpus_fingerprint(self._corpus()) != result["fingerprint"]:
                    raise Conflict("Graph corpus changed; refresh the graph")
            return {"relations": result}
        if op == "apply-suggestions":
            op = "suggest-apply"
        if op not in {"direction-save", "direction-delete", "membership", "note", "history",
                      "positions", "collapse", "undo", "export", "suggest", "suggest-apply", "apply-ai-review",
                      "drafts", "draft-save", "draft-clear", "import-categories"} | ROUTE_OPS:
            raise ValueError("Unknown organization operation")
        if op == "suggest":
            return self._suggest(body)
        with self._transaction(write=op not in {"history", "export", "drafts"}):
            if precondition is not None:
                precondition()
            revision, data = self._load()
            if "revision" in body and _version(body["revision"], "revision") != revision:
                raise Conflict("Organization revision conflict")
            if op == "history":
                key = self._paper_key(body.get("key"))
                return {"key": key, "history": self._history(key), "revision": revision}
            if op == "export":
                return self._snapshot(archived=True)
            if op == "drafts":
                key = self._paper_key(body["key"]) if "key" in body else None
                return {"drafts": self._drafts(key), "revision": revision}
            if op in {"draft-save", "draft-clear"}:
                return {"draft": self._save_draft(body, clear=op == "draft-clear"), "revision": revision}
            before = _dump(data)
            note_key = note_before = None
            apply_result = None
            label = None
            if op == "undo" and "event" in body:
                # Named undo: exactly the change the button showed. Layout saved after
                # it is kept for nodes that still exist instead of jumping back.
                event = self._undoable()
                if type(body["event"]) is not int:
                    raise ValueError("event must be an integer")
                if not event or not event["label"] or body["event"] != event["id"]:
                    raise Conflict("可撤销的操作已变化，请刷新后再试")
                current = data
                data = json.loads(event["before_data"])
                if event["note_key"] is not None:
                    self._write_note(event["note_key"], event["note_before"])
                self.conn.execute("UPDATE org_events SET undone=1 WHERE project=? AND id>=?",
                                  (self.project, event["id"]))
                if event["label"] != "重新排列":
                    # Current layout wins; a restored (e.g. undeleted) category gets its old layout back.
                    live = {d["id"] for d in data["directions"]} | {None, ""}
                    had = {d["id"] for d in current["directions"]} | {""}  # "" is the unclassified group
                    merged = dict(data["positions"])
                    merged.update(current["positions"])
                    data["positions"] = {node: point for node, point in merged.items()
                                         if self._node_parts(node)[1] in live}
                    collapsed = [i for i in current.get("collapsed", []) if i in live]
                    data["collapsed"] = collapsed + [i for i in data.get("collapsed", [])
                                                     if i in live and i not in had and i not in collapsed]
                data.pop("suggestions", None)
            elif op == "undo":
                event = self.conn.execute("""SELECT * FROM org_events WHERE project=? AND undone=0
                    ORDER BY id DESC LIMIT 1""", (self.project,)).fetchone()
                if not event:
                    raise ValueError("Nothing to undo")
                data = json.loads(event["before_data"])
                if event["note_key"] is not None:
                    self._write_note(event["note_key"], event["note_before"])
                self.conn.execute("UPDATE org_events SET undone=1 WHERE id=?", (event["id"],))
                data.pop("suggestions", None)
            elif op in ROUTE_OPS:
                trusted_revision = revision_builder() if revision_builder is not None else None
                label = self._route_op(op, body, data, trusted_revision=trusted_revision)
                if label is None:
                    result = self._snapshot()
                    if postcondition is not None:
                        postcondition(result)
                    return result   # nothing changed: no revision bump, no undo step
            elif op == "note":
                note_key = self._paper_key(body.get("key"))
                version = _version(body.get("version"), "version")
                note_before, current = self._note(note_key)
                if current != version:
                    raise Conflict("Note version conflict")
                text = body.get("text")
                if not isinstance(text, str) or len(text) > 1000000:
                    raise ValueError("Note text must be a string of at most 1000000 characters")
                self._write_note(note_key, text)
                label = "编辑笔记"
            elif op == "direction-save":
                name = _text(body.get("name"), "name").strip()
                color = body.get("color")
                if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    raise ValueError("color must be #RRGGBB")
                direction_id = body.get("id")
                if direction_id is None:
                    direction_id = uuid.uuid4().hex
                    direction = {"id": direction_id, "rank": len(data["directions"])}
                    data["directions"].append(direction)
                    label = "新建类别"
                else:
                    direction = self._direction(data, direction_id)
                    label = ("编辑类别" if (direction.get("name"), direction.get("color", "").lower())
                             != (name, color.lower()) else
                             "移动类别" if body.get("parent_id", direction.get("parent_id")) != direction.get("parent_id")
                             else "调整类别顺序" if "rank" in body else "编辑类别")
                parent = body.get("parent_id", direction.get("parent_id"))
                if parent is not None:
                    _text(parent, "parent_id")
                    cursor, seen = parent, {direction["id"]}
                    while cursor is not None:
                        if cursor in seen:
                            raise ValueError("类别不能放入自身或其子类别")
                        seen.add(cursor)
                        cursor = self._direction(data, cursor).get("parent_id")
                direction.update(name=name, color=color.lower(), manual=True, parent_id=parent)
                if "rank" in body:
                    rank = _version(body["rank"], "rank")
                    if rank >= len(data["directions"]):
                        raise ValueError("rank must be within the direction list")
                    data["directions"].remove(direction)
                    data["directions"].insert(rank, direction)
                    for index, other in enumerate(data["directions"]):
                        other["rank"] = index
            elif op == "direction-delete":
                label = "删除类别"
                direction = self._direction(data, body.get("id"))
                data["directions"].remove(direction)
                for child in data["directions"]:
                    if child.get("parent_id") == direction["id"]:
                        child["parent_id"] = direction.get("parent_id")
                for rank, other in enumerate(data["directions"]):
                    other["rank"] = rank
                for key, memberships in data["memberships"].items():
                    if direction["id"] in memberships:
                        memberships.remove(direction["id"])
                        data["protected"] = sorted(set(data["protected"]) | {key})
                data["positions"].pop("direction:" + direction["id"], None)
                data["collapsed"] = [identifier for identifier in data.get("collapsed", [])
                                     if identifier != direction["id"]]
                for node in list(data["positions"]):
                    if self._node_parts(node)[1] == direction["id"]:
                        data["positions"].pop(node)
            elif op == "membership":
                label = "调整分类"
                keys = self._list(body.get("keys"), "keys")
                add = self._list(body.get("add", []), "add")
                remove = self._list(body.get("remove", []), "remove")
                if set(add) & set(remove):
                    raise ValueError("add and remove overlap")
                for key in keys:
                    self._paper_key(key, saved=True)
                for direction_id in add + remove:
                    self._direction(data, direction_id)
                for key in keys:
                    data["memberships"][key] = sorted(
                        (set(data["memberships"].get(key, [])) | set(add)) - set(remove))
                data["protected"] = sorted(set(data["protected"]) | set(keys))
                self._drop_emptied(data, remove)
            elif op == "import-categories":
                label = "导入分类"
                apply_result = self._import_categories(data, body.get("groups"))
                if _dump(data) == before:   # every folder and placement was already there: no revision, no undo step
                    result = self._snapshot()
                    result["apply_result"] = apply_result
                    return result
            elif op == "collapse":
                label = LAYOUT_LABELS[1]
                identifier = body.get("id")
                if identifier != "":
                    self._direction(data, identifier)
                if type(body.get("collapsed")) is not bool:
                    raise ValueError("collapsed must be a boolean")
                collapsed = set(data.get("collapsed", []))
                if body["collapsed"]:
                    collapsed.add(identifier)
                else:
                    collapsed.discard(identifier)
                data["collapsed"] = sorted(collapsed)
            elif op == "positions":
                # An explicit "rearrange all" is a visible action; ordinary drags are layout.
                label = "重新排列" if body.get("rearrange") is True else LAYOUT_LABELS[0]
                positions = body.get("positions")
                if not isinstance(positions, dict) or len(positions) > 10000:
                    raise ValueError("positions must be a mapping of at most 10000 nodes")
                for node, point in positions.items():
                    if not isinstance(node, str):
                        raise ValueError("Invalid node ID")
                    if point is None and node in data["positions"]:
                        del data["positions"][node]
                        continue
                    key, direction_id = self._node_parts(node)
                    if key is not None:
                        self._paper_key(key, saved=True)
                    if direction_id is not None:
                        self._direction(data, direction_id)
                    if point is None:
                        data["positions"].pop(node, None)
                        continue
                    if not isinstance(point, dict) or set(point) != {"x", "y"}:
                        raise ValueError("Position must contain x and y")
                    if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e7
                           for v in point.values()):
                        raise ValueError("Coordinates must be finite numbers within +/-10000000")
                    data["positions"][node] = dict(point)
            elif op == "apply-ai-review":
                preview = data.get("suggestions") or {}
                if not preview.get("ai_token") or body.get("ai_token") != preview["ai_token"]:
                    raise Conflict("AI 审阅预览已变化，请重新审阅")
                if preview.get("ai_applied"):
                    result = self._snapshot()
                    result["apply_result"] = {"changed_papers": 0, "created_categories": 0, "merged_categories": 0, "deleted_categories": 0, "renamed_categories": 0, "classified_papers": 0}
                    return result
                if body.get("fingerprint") != preview.get("fingerprint") or corpus_fingerprint(self._corpus(preview.get("scope"))) != preview.get("fingerprint"):
                    raise Conflict("论文已变化，请重新审阅")
                if structure_hash(data["directions"], data["memberships"]) != preview.get("structure"):
                    raise Conflict("类别或归属已变化，请重新审阅")
                plan = preview.get("ai_plan")
                if "selection" in body:
                    # Only the chosen units; what they need comes with them, so the part is valid on its own.
                    selection = body["selection"]
                    chosen = selection.get("units") if isinstance(selection, dict) else None
                    units = preview.get("ai_units") or self._offered_units(plan, data)
                    if isinstance(chosen, list) and not chosen:
                        raise ValueError("请至少选择一项要应用的整理内容")
                    asked = review_units.closure(units, chosen)
                    resolved = self._resolve_selection(plan, units, chosen, data)
                    also_applied = sorted(resolved - asked)
                    plan = review_units.select_plan(plan, units, resolved, data["memberships"])
                else:
                    also_applied = []
                apply_result = self._apply_ai_review(data, plan)
                if also_applied:
                    apply_result["also_applied"] = also_applied
                preview["ai_applied"] = True
                label = "应用 AI 分类审阅"
            elif op == "suggest-apply":
                label = "应用建议"
                preview = data.get("suggestions")
                if not preview or body.get("fingerprint") != preview["fingerprint"]:
                    raise Conflict("A matching stored suggestion preview is required")
                if corpus_fingerprint(self._corpus(preview.get("scope"))) != preview["fingerprint"]:
                    raise Conflict("Suggestion corpus is stale; recompute preview")
                if preview.get("structure") is not None and preview["structure"] != structure_hash(data["directions"], data["memberships"]):
                    raise Conflict("The categories changed since this review; run it again")
                groups = self._selected_groups(body, preview)
                mode = body.get("apply_mode")
                if mode not in (None, "add"):
                    raise ValueError("Unknown suggestion application mode")
                if mode == "add":
                    if "suggestions" not in body:
                        raise ValueError("请选择要应用的类别和论文")
                    merges = self._selected_items(body.get("merges"), preview.get("merges", []), "merge")
                    moves = self._selected_items(body.get("moves"), preview.get("moves", []), "move")
                    dismissed = self._selected_items(body.get("dismissed"), preview.get("moves", []), "dismissed move")
                    if {m["id"] for m in moves} & {m["id"] for m in dismissed}:
                        raise ValueError("A move cannot be both applied and dismissed")
                    finish = body.get("finish") is True
                    if not groups and not merges and not moves and not finish:
                        raise ValueError("请选择要应用的类别和论文")
                    apply_result = self._apply_review(data, groups, merges, moves, dismissed, preview)
                    if merges or moves or not groups:
                        label = "应用整理调整"
                    if _dump(data) == before:   # nothing to add, merge or move and nothing newly reviewed
                        result = self._snapshot()
                        result["apply_result"] = apply_result
                        return result
                else:
                    regroup = body.get("regroup_auto", False)
                    if type(regroup) is not bool:
                        raise ValueError("regroup_auto must be a boolean")
                    automatic = {d["id"] for d in data["directions"] if not d.get("manual")}
                    replaced = set()
                    for group in groups:
                        eligible = [key for key in group["keys"] if key not in data["protected"]
                                    and (not data["memberships"].get(key) or
                                         (regroup and set(data["memberships"][key]) <= automatic))]
                        if not eligible:
                            continue
                        if group.get("target") in {d["id"] for d in data["directions"]}:
                            for key in eligible:   # an addition to an existing category
                                if group["target"] not in data["memberships"].setdefault(key, []):
                                    data["memberships"][key].append(group["target"])
                            continue
                        existing = next((d for d in data["directions"] if d["id"] == group["id"]), None)
                        if existing and existing.get("manual"):
                            continue
                        if not existing:
                            parent = group.get("parent")
                            data["directions"].append({"id": group["id"], "name": group["name"],
                                "parent_id": parent if any(d["id"] == parent for d in data["directions"]) else None,
                                "color": group.get("color", "#64748b"),
                                "rank": len(data["directions"]), "manual": group.get("edited", False)})
                        elif regroup:
                            existing.update(name=group["name"], color=group.get("color", "#64748b"),
                                            manual=group.get("edited", False))
                        for key in eligible:
                            replaced.update(data["memberships"].get(key, []))
                            data["memberships"][key] = [group["id"]]
                    occupied = {identifier for memberships in data["memberships"].values() for identifier in memberships}
                    parents = {d.get("parent_id") for d in data["directions"]}
                    self._remove_directions(data, replaced - occupied - parents)
                data.pop("suggestions", None)
            if op not in {"undo", "suggest"}:
                self.conn.execute("""INSERT INTO org_events
                    (project,before_data,note_key,note_before,label) VALUES (?,?,?,?,?)""",
                                  (self.project, before, note_key, note_before, label))
            self.conn.execute("UPDATE org_projects SET revision=?,data=? WHERE project=?",
                              (revision + 1, _dump(data), self.project))
            result = self._snapshot()
            if apply_result is not None:
                result["apply_result"] = apply_result
            if postcondition is not None:
                postcondition(result)
            return result

    def _route_op(self, op, body, data, *, trusted_revision=None):
        """Edit the project's learning map (data["route"]) and return the label shown by the undo button,
        or None when nothing would change (then nothing is written and no undo step is added).

        route-save takes `plan` (an AI or hand-written concept list, normalised) or `graph` (a structured map,
        validated), not both. Manual marks and start nodes follow their concept: by name when a new plan is
        normalised (its ids are renumbered), by id when a structured map is saved; marks of concepts that no
        longer exist are dropped. Everything is explicit user input; nothing is inferred from silence.
        """
        route = data.get("route")
        if op == "route-save":
            if trusted_revision is not None:
                body = {**body, 'graph': trusted_revision['graph'], 'brief': trusted_revision['brief']}
            plan, graph = body.get("plan"), body.get("graph")
            if plan is not None and graph is not None:
                raise ValueError("Give either a plan or a graph, not both")
            old = route or {}
            if plan is not None:
                if not isinstance(plan, dict) or not isinstance(plan.get("concepts"), list) or len(plan["concepts"]) > pathgraph.MAX_NODES:
                    raise ValueError("The plan is missing or too big")
                graph, _ = pathgraph.normalize(plan)
                if not graph["concepts"]:
                    raise ValueError("The plan has no usable concepts")
                prior_nodes = (old.get('graph') or {}).get('concepts', [])
                if len(prior_nodes) > pathgraph.MAX_NODES:
                    raise ValueError('已有学习图超过创建上限，请使用修改预览，不能用新草稿覆盖')
                by_name = {pathgraph._key(c['name']): c for c in prior_nodes}
                identity = {}
                for node in graph['concepts']:
                    prior = by_name.get(pathgraph._key(node['name']))
                    fresh_id = prior['id'] if prior else ('r-' + uuid.uuid4().hex if prior_nodes else node['id'])
                    identity[node['id']] = fresh_id
                    node['id'] = fresh_id
                    if prior and prior.get('intro') and prior.get('intro_by', 'user') == 'user':
                        node['intro'], node['intro_by'] = prior['intro'], 'user'
                for edge in graph['prereqs']:
                    edge['from'], edge['to'] = identity[edge['from']], identity[edge['to']]
                graph['targets'] = [identity[i] for i in graph['targets']]
                fresh = {c['id'] for c in graph['concepts']}
                follow = lambda i: i if i in fresh else None
            else:
                graph = pathgraph.validate(graph, tolerate={pathgraph._key(c.get("name")) for c in (old.get("graph") or {}).get("concepts", [])}, explicit=True)
                before = {c["id"]: pathgraph._key(c["name"]) for c in (old.get("graph") or {}).get("concepts", [])}
                now_ = {c["id"]: pathgraph._key(c["name"]) for c in graph["concepts"]}
                # an id can be reused by a different concept (delete the last one, add another); a mark belongs to the concept
                follow = lambda i: i if i in now_ and before.get(i) == now_[i] else None
            manual = {follow(k): v for k, v in (old.get("manual") or {}).items() if follow(k)}
            start = [follow(i) for i in (old.get("start") or []) if follow(i)]
            watch = list(dict.fromkeys(follow(i) for i in (old.get("watch") or []) if follow(i)))
            if plan is None or old or 'brief' in body:
                previous = {c['id']: c for c in (old.get('graph') or {}).get('concepts', [])}
                cutoff = self.conn.execute('SELECT COALESCE(MAX(id),0) FROM feedback WHERE project_id=?', (self.project,)).fetchone()[0]
                cutoff = route_revision.progress_cutoff(cutoff, self.store.get_setting('profile_freeze_' + self.project))
                reset = set()
                for node in graph['concepts']:
                    prior = previous.get(node['id'])
                    if not prior or route_revision.semantic_key(node) != route_revision.semantic_key(prior):
                        node['progress_since_feedback_id'] = max(cutoff, (prior or {}).get('progress_since_feedback_id', 0))
                        reset.add(node['id'])
                    elif 'progress_since_feedback_id' in prior:
                        node['progress_since_feedback_id'] = prior['progress_since_feedback_id']
                    else:
                        node.pop('progress_since_feedback_id', None)
                manual = {k: v for k, v in manual.items() if k not in reset}
                start = [i for i in start if i not in reset]
                # Watching belongs to stable identity, separately from mastery.
                watch = [i for i in (old.get('watch') or []) if i in {c['id'] for c in graph['concepts']}]
            updated = {"graph": graph, "mode": old.get("mode", "route"), "manual": manual, "start": start, "watch": watch}
            if 'brief' in body:
                updated['brief'] = route_revision.validate_brief(body['brief'])
            elif 'brief' in old:
                updated['brief'] = old['brief']
            if old.get("rejected"):
                updated["rejected"] = old["rejected"]   # a direction the person turned down stays turned down across saves
            if updated == route:
                return None
            data["route"] = updated
            return '修改学习图' if trusted_revision is not None else ROUTE_SAVE_LABELS.get(body.get("label"), "保存学习路径")
        if not route:
            raise ValueError("There is no learning path yet")
        known = {c["id"] for c in route["graph"]["concepts"]}
        if op == "route-watch":
            concept, value = body.get("concept"), body.get("value")
            active = {c["id"] for c in route["graph"]["concepts"] if c.get("state", "active") == "active"}
            if not isinstance(concept, str) or concept not in known or (value is True and concept not in active):
                raise ValueError("Unknown active concept")
            if not isinstance(value, bool):
                raise ValueError("Watching requires a boolean")
            watch = list(route.get("watch") or [])
            if (concept in watch) == value:
                return None
            route["watch"] = watch + [concept] if value else [i for i in watch if i != concept]
            return "设置持续关注"
        if op == "route-reject":
            # a turned-down direction is remembered by its phrases (normalised), because the papers it was found in
            # change with every new paper while the direction stays the same
            terms = body.get("terms")
            if not isinstance(terms, list) or not 1 <= len(terms) <= 4 or any(not isinstance(t, str) or len(t) > 80 for t in terms):
                raise ValueError("Unknown candidate")
            keys = [k for k in dict.fromkeys(pathgraph._key(t) for t in terms) if k]
            if not keys:
                raise ValueError("Unknown candidate")
            rejected = list(route.get("rejected") or [])
            fresh = [k for k in keys if k not in rejected]
            if not fresh:
                return None
            route["rejected"] = (rejected + fresh)[-MAX_REJECTED:]
            return "不再提示这个新方向"
        if op == "route-manual":
            concept, value = body.get("concept"), body.get("value")
            if not isinstance(concept, str) or concept not in known:
                raise ValueError("Unknown concept")
            if value is not None and value not in ROUTE_MARKS:
                raise ValueError("Unknown mark")
            if route["manual"].get(concept) == value:
                return None
            if value is None:
                route["manual"].pop(concept)
            else:
                route["manual"][concept] = value
            return "标记概念状态"
        if op == "route-start":
            start = body.get("start")
            if not isinstance(start, list) or len(start) > pathgraph.MAX_NODES or any(not isinstance(i, str) or i not in known for i in start):
                raise ValueError("Unknown start concept")
            start = list(dict.fromkeys(start))
            if start == route["start"]:
                return None
            route["start"] = start
            return "设置路径起点"
        if body.get("mode") not in ("route", "off"):
            raise ValueError("Unknown route mode")
        if route["mode"] == body["mode"]:
            return None
        route["mode"] = body["mode"]
        return "切换路径模式"

    def _drop_emptied(self, data, candidates):
        """Delete categories an edit left without saved papers or subcategories.

        Only categories that lost papers (and ancestors they leave empty) qualify;
        a category the owner just created and has not filled yet stays."""
        saved = {row[0] for row in self.conn.execute("SELECT paper_key FROM library")}
        occupied = {identifier for key, ids in data["memberships"].items() if key in saved
                    for identifier in ids}
        parents = {d["id"]: d.get("parent_id") for d in data["directions"]}
        removed, pending = set(), list(candidates)
        while pending:
            identifier = pending.pop()
            if (identifier in removed or identifier in occupied or identifier not in parents
                    or any(parent == identifier and child not in removed
                           for child, parent in parents.items())):
                continue
            removed.add(identifier)
            if parents[identifier] is not None:
                pending.append(parents[identifier])
        self._remove_directions(data, removed)

    def _remove_directions(self, data, removed):
        """Drop childless categories with their memberships, ranks, folds and layout."""
        if not removed:
            return
        data["directions"] = [d for d in data["directions"] if d["id"] not in removed]
        for rank, direction in enumerate(data["directions"]):
            direction["rank"] = rank
        for key, memberships in data["memberships"].items():
            data["memberships"][key] = [i for i in memberships if i not in removed]
        data["collapsed"] = [identifier for identifier in data.get("collapsed", []) if identifier not in removed]
        for node in list(data["positions"]):
            if self._node_parts(node)[1] in removed:
                data["positions"].pop(node)

    @staticmethod
    def _add_selected_suggestions(data, groups, redirect=None):
        """Explicit user-selected additions: never erase existing memberships or labels.

        A group may name an existing category (`target`: papers are added to it), and a new category is never made
        beside an existing one of the same name at the same level: the existing one is used."""
        added, already, created, changed = 0, 0, 0, set()
        placed = {}  # suggestion id -> direction id, so children land under their parent
        redirect = redirect or {}
        norm = category_identity
        for group in groups:
            if not group["keys"]:
                raise ValueError("所选类别至少需要一篇论文")
            wanted = redirect.get(group.get("target"), group.get("target"))
            target = next((d for d in data["directions"] if wanted and d["id"] == wanted), None)
            if target is None and group.get("target"):
                continue   # the category this addition was for is gone: skip it, never make a new one in its place
            if target is None:
                parent = group.get("parent")
                level = placed.get(parent) if parent is not None else None
                if parent is not None and level is None:
                    ptarget = redirect.get(group.get("parent_target"), group.get("parent_target"))
                    level = ptarget if ptarget and any(d["id"] == ptarget for d in data["directions"]) else next((d["id"] for d in data["directions"]
                                    if parent in (d["id"], d.get("source_suggestion"))), None)
                    if level is None:
                        raise ValueError("请同时选择此子类别的父类别")
                target = next((d for d in data["directions"]
                               if norm(d["name"]) == norm(group["name"]) and (d.get("parent_id") or None) == (level or None)
                               and (group.get("parent") is None or level is not None)), None)
            if target is None:
                identifier = group["id"]
                if any(d["id"] == identifier for d in data["directions"]):
                    identifier = uuid.uuid4().hex
                parent = group.get("parent")
                if parent is not None and parent not in placed:
                    # An unselected parent may already exist from an earlier application, or be an existing category.
                    ptarget = redirect.get(group.get("parent_target"), group.get("parent_target"))
                    parent = ptarget if ptarget and any(d["id"] == ptarget for d in data["directions"]) else next((d["id"] for d in data["directions"]
                                   if parent in (d["id"], d.get("source_suggestion"))), None)
                else:
                    parent = placed.get(parent)
                target = {"id": identifier, "name": group["name"],
                          "color": group.get("color", "#64748b"), "parent_id": parent,
                          "rank": len(data["directions"]), "manual": True,
                          "source_suggestion": group["id"]}
                data["directions"].append(target)
                created += 1
            placed[group["id"]] = target["id"]
            for key in group["keys"]:
                current = data["memberships"].setdefault(key, [])
                if target["id"] in current:
                    already += 1
                else:
                    current.append(target["id"])
                    added += 1
                    changed.add(key)
        data["protected"] = sorted(set(data["protected"]) | changed)
        return {"added_memberships": added, "already_present": already,
                "created_categories": created, "changed_papers": len(changed)}

    def _import_categories(self, data, groups):
        """Folders of an imported library as categories: [{path: [names], keys: [paper keys]}].

        Each name is looked up at its level by category identity (case and known aliases) and reused, else created;
        the papers join the deepest one. Memberships are only ever added, so nothing the person organised moves, and
        every placed paper is marked protected so automatic regrouping leaves the person's own folders alone."""
        if not isinstance(groups, list) or len(groups) > IMPORT_MAX_GROUPS:
            raise ValueError("groups must be a list of at most %d folders" % IMPORT_MAX_GROUPS)
        parsed = []
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError("Each folder must be an object")
            path, keys = group.get("path"), group.get("keys")
            if not isinstance(path, list) or not isinstance(keys, list) or not keys or len(keys) > 20000:
                raise ValueError("Each folder needs a path list and a non-empty keys list")
            names = []
            for part in path:
                name = re.sub(r"\s+", " ", part).strip()[:IMPORT_NAME_MAX].strip() if isinstance(part, str) else ""
                if not name:
                    raise ValueError("Category names must be non-empty text")
                names.append(name)
            for key in keys:
                self._paper_key(key, saved=True)
            parsed.append((names[:IMPORT_MAX_DEPTH], keys))
        created, reused, added, already, changed = set(), set(), 0, 0, set()
        for names, keys in parsed:
            parent = leaf = None
            for name in names:
                leaf = next((d for d in data["directions"] if category_identity(d["name"]) == category_identity(name)
                             and (d.get("parent_id") or None) == parent), None)
                if leaf is None:
                    leaf = {"id": uuid.uuid4().hex, "name": name, "parent_id": parent, "rank": len(data["directions"]),
                            "color": IMPORT_COLORS[len(data["directions"]) % len(IMPORT_COLORS)], "manual": True,
                            "source": "import"}
                    data["directions"].append(leaf)
                    created.add(leaf["id"])
                elif leaf["id"] not in created:
                    reused.add(leaf["id"])
                parent = leaf["id"]
            if leaf is None:
                continue   # files at the top of the chosen folder stay unclassified
            for key in keys:
                current = data["memberships"].setdefault(key, [])
                if leaf["id"] in current:
                    already += 1
                else:
                    current.append(leaf["id"])
                    added += 1
                    changed.add(key)
        data["protected"] = sorted(set(data["protected"]) | changed)
        from .category_review import MAX_CATEGORIES   # the AI review refuses a tree larger than this
        return {"created_categories": len(created), "reused_categories": len(reused), "added_memberships": added,
                "already_present": already, "changed_papers": len(changed),
                "total_categories": len(data["directions"]), "over_ai_limit": len(data["directions"]) > MAX_CATEGORIES}

    def _drafts(self, key=None):
        sql = """SELECT paper_key AS key,client,text,version,updated_at FROM org_drafts
            WHERE project=? AND text IS NOT NULL"""
        args = [self.project]
        if key is not None:
            sql += " AND paper_key=?"
            args.append(key)
        return [dict(row) for row in self.conn.execute(sql + " ORDER BY paper_key,client", args)]

    def _save_draft(self, body, clear=False):
        key = self._paper_key(body.get("key"))
        client = _text(body.get("client"), "client")
        version = _version(body.get("version"), "version")
        row = self.conn.execute("""SELECT version FROM org_drafts
            WHERE project=? AND paper_key=? AND client=?""", (self.project, key, client)).fetchone()
        if version != (row[0] if row else 0):
            raise Conflict("Draft version conflict")
        text = None if clear else body.get("text")
        if not clear and (not isinstance(text, str) or len(text) > 1000000):
            raise ValueError("Draft text must be a string of at most 1000000 characters")
        stamp = now()
        self.conn.execute("""INSERT INTO org_drafts VALUES (?,?,?,?,?,?)
            ON CONFLICT(project,paper_key,client) DO UPDATE SET
            version=excluded.version,text=excluded.text,updated_at=excluded.updated_at""",
                          (self.project, key, client, version + 1, text, stamp))
        return {"key": key, "client": client, "text": text, "version": version + 1, "updated_at": stamp}

    def _node_parts(self, node):
        if node == "direction::anchor":
            return None, None  # The virtual unclassified group has no direction row.
        if node.startswith("direction:"):
            identifier = node[10:]
            if identifier.endswith(":anchor"):
                identifier = identifier[:-7]
            return None, identifier
        if node.startswith("paper:"):
            identifier = node[6:]
            if self.conn.execute("SELECT 1 FROM papers WHERE key=?", (identifier,)).fetchone():
                return identifier, None
            encoded_key, separator, encoded_direction = identifier.rpartition(":")
            if separator:
                return unquote(encoded_key), unquote(encoded_direction) or None
            return unquote(identifier), None
        raise ValueError("Node IDs must use paper: or direction: prefix")

    @staticmethod
    def _selected_items(selected, available, name):
        """The merge / move items the person ticked: ids of the stored preview only, each once."""
        if selected is None:
            return []
        if not isinstance(selected, list) or len(selected) > len(available):
            raise ValueError(name + "s must be a subset of the stored preview")
        by_id = {item["id"]: item for item in available}
        seen, items = set(), []
        for identifier in selected:
            if not isinstance(identifier, str) or identifier not in by_id or identifier in seen:
                raise ValueError("Unknown or duplicate " + name)
            seen.add(identifier)
            items.append(by_id[identifier])
        return items

    def _apply_review(self, data, groups, merges, moves, dismissed, preview):
        """Apply ticked additions, merges and moves in one change, then mark the papers looked at as reviewed.

        A move proposal stays open (it is proposed again) until it is applied or dismissed on purpose; nothing is
        inferred from a box left unticked. Everything is skipped, not guessed, when the shape it assumed has changed."""
        known = lambda: {d["id"] for d in data["directions"]}
        parent_of = lambda i: next((d.get("parent_id") for d in data["directions"] if d["id"] == i), None)

        def related(a, b):   # one is the other or sits above it
            for start, other in ((a, b), (b, a)):
                up, guard = parent_of(start), 0
                while up is not None and guard < 64:
                    if up == other:
                        return True
                    up, guard = parent_of(up), guard + 1
            return a == b
        changed, redirect, merged, moved = set(), {}, 0, 0
        selected_merges = {item["id"] for item in merges}
        for item in merges:
            if not set(item.get("depends_on", [])) <= selected_merges:
                raise ValueError("请同时选择此重复子类所依赖的父类别合并")
        for item in merges:   # merges first; later steps follow a dropped category to the one kept
            keep = item["keep"]
            if keep not in known():
                continue
            drop = [i for i in item["drop"] if i in known() and i != keep and parent_of(i) == parent_of(keep) and not related(i, keep)]
            for identifier in drop:
                redirect[identifier] = keep
                for key, ids in data["memberships"].items():
                    if identifier in ids:
                        data["memberships"][key] = list(dict.fromkeys(keep if i == identifier else i for i in ids))
                        changed.add(key)
                for direction in data["directions"]:
                    if direction.get("parent_id") == identifier and direction["id"] != keep:
                        direction["parent_id"] = keep
                merged += 1
            self._remove_directions(data, set(drop))
        apply_result = self._add_selected_suggestions(data, groups, redirect) if groups else {
            "added_memberships": 0, "already_present": 0, "created_categories": 0, "changed_papers": 0}
        emptied, applied_moves = set(), set()
        for item in moves:
            key = item["key"]
            target = redirect.get(item["to"], item["to"])
            if target not in known() or key not in data["memberships"]:
                continue
            current = data["memberships"][key]
            leaving = [redirect.get(i, i) for i in item["from"] if redirect.get(i, i) in current and redirect.get(i, i) != target]
            if not leaving:
                continue
            data["memberships"][key] = [i for i in current if i not in leaving] + ([target] if target not in current else [])
            emptied.update(leaving)
            applied_moves.add(item["id"])
            changed.add(key)
            moved += 1
        if emptied:
            # a category is dropped only when nobody at all holds it any more, archived papers included
            holding = {i for ids in data["memberships"].values() for i in ids}
            self._drop_emptied(data, emptied - holding)
        data["protected"] = sorted(set(data["protected"]) | changed)
        apply_result.update(merged_categories=merged, moved_papers=moved)
        open_moves = {m["key"] for m in moves if m["id"] not in applied_moves} | {m["key"] for m in preview.get("moves", [])
                      if m["id"] not in {x["id"] for x in moves} | {x["id"] for x in dismissed}}
        self._mark_reviewed(data, preview, (set(preview.get("evaluated", [])) - open_moves) | changed, changed)
        return apply_result

    def _mark_reviewed(self, data, preview, keys, changed=()):
        """Remember that these organised papers were looked at, so the next review does not repeat itself. A paper
        whose categories did not change since the review keeps the signature the review computed."""
        rows = {row["key"]: row for row in self._corpus(preview.get("scope"))}
        live = {d["id"] for d in data["directions"]}
        stored = preview.get("signatures") or {}
        marks = {}
        for key in keys:
            ids = [i for i in data["memberships"].get(key, []) if i in live]
            if key in rows and ids:
                marks[key] = stored[key] if key in stored and key not in changed else paper_signature(rows[key], ids)
        if marks:
            data.setdefault("reviewed", {}).update(marks)

    @staticmethod
    def _selected_groups(body, preview):
        if "suggestions" not in body:
            return preview["groups"]
        selected = body["suggestions"]
        if not isinstance(selected, list) or len(selected) > len(preview["groups"]):
            raise ValueError("suggestions must be a subset of stored preview groups")
        originals = {group["id"]: group for group in preview["groups"]}
        seen, groups = set(), []
        for selection in selected:
            if not isinstance(selection, dict):
                raise ValueError("Suggested group must be an object")
            group_id = _text(selection.get("id"), "suggested group id")
            if group_id not in originals or group_id in seen:
                raise ValueError("Unknown or duplicate suggested group")
            seen.add(group_id)
            original = originals[group_id]
            keys = Organization._list(selection.get("keys"), "keys")
            if not set(keys) <= set(original["keys"]) or len(keys) != len(set(keys)):
                raise ValueError("Suggested keys must be a unique subset of the stored group")
            name = _text(selection.get("name", original["name"]), "name").strip()
            color = selection.get("color", "#64748b")
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("color must be #RRGGBB")
            groups.append({"id": group_id, "keys": keys, "name": name, "color": color.lower(),
                           "parent": original.get("parent"), "target": original.get("target"),
                           "parent_target": (originals.get(original.get("parent")) or {}).get("target"),
                           "edited": name != original["name"] or color.lower() != "#64748b"})
        # Preview order lists parents first, so a child always finds its new parent.
        order = {group["id"]: index for index, group in enumerate(preview["groups"])}
        return sorted(groups, key=lambda group: order[group["id"]])

    def _suggest(self, body):
        """Review what is saved and propose only changes (see organization_facets.review).

        `scope_project` limits the review to the papers one project saved; the categories are shared. Nothing is
        applied here. When there is nothing to change, the organised papers just looked at are marked reviewed."""
        scope = body.get("scope_project")
        if scope is not None and not isinstance(scope, str):
            raise ValueError("scope_project must be a project id")
        with self._transaction(write=False):
            revision, data = self._load()
            if "revision" in body and _version(body["revision"], "revision") != revision:
                raise Conflict("Organization revision conflict")
            papers = self._corpus(scope)
            directions = [dict(d) for d in data["directions"]]
            memberships = {k: list(v) for k, v in data["memberships"].items()}
            reviewed = dict(data.get("reviewed") or {})
        preview = review_papers(papers, directions, memberships, reviewed, body.get("profile"))
        preview["scope"] = scope
        # The expensive computation owns neither a database transaction nor the
        # Store lock. Re-read state so concurrent manual edits are never lost.
        with self._transaction():
            now_revision, data = self._load()
            if "revision" in body and body["revision"] != now_revision:
                raise Conflict("Organization revision conflict")
            if corpus_fingerprint(self._corpus(scope)) != preview["fingerprint"]:
                raise Conflict("Suggestion corpus changed during computation; retry preview")
            data["suggestions"] = preview
            if not (preview.get("groups") or preview.get("merges") or preview.get("moves")) \
                    and preview.get("structure") == structure_hash(data["directions"], data["memberships"]):
                # Nothing to change (and the categories are as the review saw them): the organised papers just looked
                # at are done until something about them changes.
                self._mark_reviewed(data, preview, set(preview.get("evaluated", [])))
            self.conn.execute("UPDATE org_projects SET revision=?,data=? WHERE project=?",
                              (now_revision + 1, _dump(data), self.project))
            return self._snapshot()

    def store_ai_review(self, plan, revision, corpusfp, structure, scope):
        """Install only a complete, locally validated model preview; never edit the library here."""
        with self._transaction():
            now, data = self._load()
            if now != revision or corpus_fingerprint(self._corpus(scope)) != corpusfp or structure_hash(data['directions'], data['memberships']) != structure:
                raise Conflict("审阅期间论文或分类已变化，请重新审阅")
            if {p.get("key") for p in plan.get("papers", [])} != {p["key"] for p in self._corpus(scope)}:
                raise ValueError("AI 审阅必须覆盖当前范围所有论文")
            candidate = json.loads(_dump(data))
            self._apply_ai_review(candidate, plan)  # Full validation on a private copy, without persistence.
            data['suggestions'] = {'groups': [], 'merges': [], 'moves': [], 'pending_keys': [],
                                  'fingerprint': corpusfp, 'structure': structure, 'scope': scope,
                                  'source': 'ai', 'algorithm': 'ai-category-review-v1',
                                  'ai_plan': plan, 'ai_token': uuid.uuid4().hex,
                                  'ai_units': self._offered_units(plan, data)}
            self.conn.execute('UPDATE org_projects SET revision=?,data=? WHERE project=?',
                              (now + 1, _dump(data), self.project))
            return self._snapshot()

    def plan_error(self, plan):
        """None when `plan` would apply to the library as it is now, else the reason. Read-only (a private copy)."""
        with self._transaction(write=False):
            _, data = self._load()
        try:
            self._apply_ai_review(json.loads(_dump(data)), plan)
        except ValueError as error:
            return str(error)
        return None

    def _selection_probe(self, plan, units, data):
        """works(chosen): would the plan, reduced to the chosen units, apply to the library as it is now?

        Tried on a slim private copy. Papers that keep their categories cannot change whether a plan applies, so only
        the changed ones are sent through; who counts as this scope's papers (for the read-only rule) still comes
        from the whole plan."""
        saved = {row[0] for row in self.conn.execute("SELECT l.paper_key FROM library l JOIN papers p ON p.key=l.paper_key")}
        reviewed = {item["key"] for item in plan["papers"]}

        def works(chosen):
            sub = review_units.select_plan(plan, units, chosen, data["memberships"])
            sub["papers"] = [p for p in sub["papers"] if p["categories"] != data["memberships"].get(p["key"], [])]
            scratch = {"directions": [dict(d) for d in data["directions"]],
                       "memberships": {key: list(ids) for key, ids in data["memberships"].items()},
                       "protected": list(data.get("protected", [])), "collapsed": list(data.get("collapsed", [])), "positions": {}}
            try:
                self._apply_ai_review(scratch, sub, saved, reviewed)
                return True
            except ValueError:
                return False
        return works

    def _offered_units(self, plan, data):
        """The units the preview offers, with what each needs so that the usual choices apply without surprises.

        A label change can depend on another one (a merged parent's children must merge too, a rename into a
        sibling's name needs the sibling's rename, a merge into a renamed target needs the rename). Rather than
        guess every such rule, each label change, each pair of them, and each paper that files under new categories
        (alone and with each label change) is tried on a private copy; whatever fails is bundled with what makes it
        work, up to bundling everything (the whole plan was already validated). This cannot cover every higher-order
        combination, which is why applying has its own safety net (_resolve_selection)."""
        units = review_units.build_units(plan, data["directions"], data["memberships"])
        structural = [unit["id"] for unit in units if unit["section"] == "adjust"]
        by_id = {unit["id"]: unit for unit in units}
        works = self._selection_probe(plan, units, data)
        fresh = {item["id"] for item in plan["new_categories"]}
        # A paper that files under a NEW category brings that category with it, which can repeat the name of a
        # sibling the plan renames, merges or deletes; one try per set of new categories stands for all its papers.
        groups = {}
        for unit in units:
            used = frozenset(i for i in unit.get("to", []) if i in fresh) if unit["kind"] == "paper" else frozenset()
            if used:
                groups.setdefault(used, []).append(unit)
        probes = [[unit] for unit in units if unit["section"] == "adjust"] + list(groups.values())

        def need(unit, extra):
            unit["requires"] = list(dict.fromkeys(unit["requires"] + [i for i in extra if i != unit["id"]]))

        def fix(chosen):
            """The label changes that make `chosen` apply: one, else all of them, else the whole plan."""
            helper = next((c for c in structural if c not in chosen and works(chosen | review_units.closure(units, [c]))), None)
            if helper is not None:
                return [helper]
            if works(chosen | set(structural)):
                return [c for c in structural if c not in chosen]
            return [other["id"] for other in units]
        for _ in range(4):
            changed = False
            for members in probes:
                chosen = review_units.closure(units, [members[0]["id"]])
                if not works(chosen):
                    changed = True
                    extra = fix(chosen)
                    for unit in members:
                        need(unit, extra)
            if len(structural) <= 40:
                for first, second in itertools.combinations(structural, 2):
                    if not works(review_units.closure(units, [first, second])):
                        changed = True
                        need(by_id[first], [second]); need(by_id[second], [first])
                # A paper that files under a new category and a label change can each apply alone yet not together.
                # The fix goes on the label change, so filing unclassified papers never drags other changes along.
                if len(groups) * len(structural) <= 600:       # beyond that, applying has its own safety net
                    for members in groups.values():
                        for label in structural:
                            chosen = review_units.closure(units, [members[0]["id"], label])
                            if not works(chosen):
                                changed = True
                                need(by_id[label], fix(chosen))
            if not changed:
                break
        return units

    def _resolve_selection(self, plan, units, selected, data):
        """The units to apply for a choice: the choice with its requirements, and, if that still cannot apply to the
        library as it is, the fewest more label changes that make it work (at worst the whole plan, which was
        validated). The caller reports anything beyond the choice, so applying never fails for this reason and never
        changes more than it says."""
        chosen = review_units.closure(units, selected)
        works = self._selection_probe(plan, units, data)
        if works(chosen):
            return chosen
        structural = [unit["id"] for unit in units if unit["section"] == "adjust"]
        for label in structural:
            trial = chosen | review_units.closure(units, [label])
            if label not in chosen and works(trial):
                return trial
        current = set(chosen)
        for label in structural:
            current |= review_units.closure(units, [label])
            if works(current):
                return current
        return {unit["id"] for unit in units}

    def _apply_ai_review(self, data, plan, saved=None, reviewed=None):
        """Apply the entire reviewed plan atomically. Deletes require every retained link to be handled."""
        if not isinstance(plan, dict) or not isinstance(plan.get('categories'), list) or not isinstance(plan.get('papers'), list) or not isinstance(plan.get('new_categories'), list):
            raise ValueError('分类审阅方案缺失')
        existing = {d['id']: d for d in data['directions']}
        operations = {item.get('id'): item for item in plan['categories'] if isinstance(item, dict)}
        # A plan made for one project covers the categories that project's directory shows (category_scope);
        # the others are not reviewed and not touched. Older plans cover every category.
        scope = set(existing) if plan.get('category_scope') is None else set(self._list(plan['category_scope'], 'category scope'))
        if len(operations) != len(plan['categories']) or set(operations) != scope or not scope <= set(existing):
            raise ValueError('审阅必须覆盖全部现有类别')
        before = {key: list(ids) for key, ids in data['memberships'].items()}
        if plan.get('scoped'):
            if reviewed is None:
                reviewed = {item.get('key') for item in plan['papers'] if isinstance(item, dict)}
            outside = review_units.outside_keys(data['memberships'], reviewed, self._owners(), plan.get('scope_project'))
            locked = review_units.locked_categories(data['directions'], data['memberships'], outside, scope)
            if any(operations[identifier].get('action') != 'keep' for identifier in locked):
                raise ValueError('与其他项目共用的类别在项目范围内只能接收论文，不能改名、合并或删除')
        redirect, removed, renamed, renamed_ids = {}, set(), 0, set()
        for identifier, item in operations.items():
            action = item.get('action')
            if action == 'rename':
                name = _text(item.get('name'), 'category name').strip()
                if not name:
                    raise ValueError('类别名称不能为空')
                if existing[identifier]['name'] != name:
                    existing[identifier].update(name=name, manual=True)
                    renamed += 1
                    renamed_ids.add(identifier)
            elif action == 'merge':
                target = item.get('target')
                if target not in operations or target == identifier or operations[target].get('action') not in {'keep', 'rename'}:
                    raise ValueError('合并目标必须为保留的现有类别')
                source_term = category_term(existing[identifier]['name'])
                target_name = operations[target].get('name', existing[target]['name'])
                if source_term and category_term(target_name) and category_identity(existing[identifier]['name']) != category_identity(target_name):
                    raise ValueError('已知不同研究概念不能作为重复类别合并')
                redirect[identifier] = target
                removed.add(identifier)
            elif action == 'delete':
                removed.add(identifier)
            elif action != 'keep':
                raise ValueError('未知类别审阅操作')
        fresh = set()
        for item in plan['new_categories']:
            if not isinstance(item, dict):
                raise ValueError('新增类别必须为对象')
            identifier = _text(item.get('id'), 'new category id')
            name = _text(item.get('name'), 'category name').strip()
            if not name or identifier in existing or identifier in fresh:
                raise ValueError('新增类别名称或身份重复')
            fresh.add(identifier)
            data['directions'].append({'id': identifier, 'name': name, 'color': '#64748b',
                                       'rank': len(data['directions']), 'parent_id': item.get('parent_id'),
                                       'manual': True, 'source': 'ai-review'})
        live = {d['id'] for d in data['directions']} - removed
        reparented = set()
        for direction in data['directions']:
            parent = direction.get('parent_id')
            direction['parent_id'] = redirect.get(parent, parent)
            if direction['parent_id'] != parent:
                reparented.add(direction['id'])
            if direction['id'] in live and direction.get('parent_id') is not None and direction['parent_id'] not in live:
                raise ValueError('删除父类别前必须处理子类别')
        by_id = {d['id']: d for d in data['directions'] if d['id'] in live}
        for identifier, direction in by_id.items():
            term = category_term(direction['name'])
            if (identifier in fresh or operations.get(identifier, {}).get('action') == 'rename') and term and term['kind'] == 'method' and direction.get('parent_id') is None:
                raise ValueError('方法类别必须归于明确研究方向下')
        for identifier in live:
            seen, current = set(), identifier
            while current is not None:
                if current in seen:
                    raise ValueError('审阅方案不能产生类别循环')
                seen.add(current)
                current = by_id[current].get('parent_id')
        changed, paper_ids = set(), set()
        for key, ids in data['memberships'].items():
            updated = list(dict.fromkeys(redirect.get(i, i) for i in ids))
            if updated != ids:
                changed.add(key)
                data['memberships'][key] = updated
        for item in plan['papers']:
            if not isinstance(item, dict):
                raise ValueError('论文审阅必须为对象')
            key = item.get('key')
            if saved is None:
                key = self._paper_key(key, saved=True)
            elif not isinstance(key, str) or key not in saved:
                raise ValueError('Paper is not saved: ' + str(key))
            ids = self._list(item.get('categories'), 'review categories')
            ids = list(dict.fromkeys(redirect.get(i, i) for i in ids))
            if key in paper_ids or not set(ids) <= live:
                raise ValueError('重复论文或无效目标类别')
            paper_ids.add(key)
            if data['memberships'].get(key, []) != ids:
                data['memberships'][key] = ids
                changed.add(key)
        deleted = removed - set(redirect)
        if any(set(ids) & deleted for ids in data['memberships'].values()):
            raise ValueError('待删除类别仍有未审阅论文（可能在其他项目或已归档），请审阅全部范围后再删除')
        supported = {i for item in plan['papers'] for i in item['categories']}
        for identifier in list(supported):
            parent = by_id[identifier].get('parent_id')
            while parent is not None and parent not in supported:
                supported.add(parent)
                parent = by_id[parent].get('parent_id')
        if not fresh <= supported:
            raise ValueError('新增类别必须有本次论文证据支持')
        # Only what this plan creates, renames or moves is checked for a same-level synonym; an old duplicate the
        # plan leaves alone (for example one in another project's part of the shared tree) must not block it.
        touched = fresh | renamed_ids | reparented
        rows = list(by_id.values())
        if any((a['id'] in touched or b['id'] in touched)
               and category_identity(a['name']) == category_identity(b['name']) and a.get('parent_id') == b.get('parent_id')
               for index, a in enumerate(rows) for b in rows[index + 1:]):
            raise ValueError('审阅方案仍有同级同义类别')
        self._remove_directions(data, removed)
        data['protected'] = sorted(set(data['protected']) | changed)
        return {'changed_papers': len(changed), 'created_categories': len(fresh),
                'renamed_categories': renamed, 'merged_categories': len(redirect), 'deleted_categories': len(deleted),
                'classified_papers': sum(1 for key in changed if not before.get(key) and data['memberships'].get(key)),
                'still_unclassified': sum(1 for item in plan['papers'] if not data['memberships'].get(item['key']))}

    @staticmethod
    def _list(value, name):
        if not isinstance(value, list) or len(value) > 10000:
            raise ValueError(name + " must be an array of at most 10000 strings")
        for item in value:
            _text(item, name, 2000)
        return value

    @staticmethod
    def _direction(data, direction_id):
        _text(direction_id, "direction id")
        for direction in data["directions"]:
            if direction["id"] == direction_id:
                return direction
        raise ValueError("Unknown project direction: " + direction_id)
