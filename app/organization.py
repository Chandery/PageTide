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

from . import pathgraph, pathgrowth
from .clustering import cluster, corpus_fingerprint
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


def route_detail(conn, project_id):
    """The data of the library graph's second view (the learning map): one project's learning units and the papers it saved.

    Read-only and derived. A paper is matched to the (at most two) units whose search terms its title or
    abstract uses (pathgrowth.assign), and the terms that matched travel with the match so the line can be
    explained. Nothing is stored: matches are not part of anyone's classification, and a paper that fits no
    unit is listed, not hidden. Unknown project: ValueError. No learning map: {"available": False}."""
    _text(project_id, "project_id", 200)
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
    assigned = pathgrowth.assign(shown, papers)
    by_id = {c["id"]: c for c in live}
    matches = []
    for paper in papers:
        for rank, unit in enumerate(assigned.get(paper["key"], [])):
            text = f"{paper.get('title') or ''} {paper.get('abstract') or ''}"
            terms = [t for t in by_id[unit].get("terms", []) if pathgrowth.term_in_text(text, t)]
            matches.append({"paper": paper["key"], "unit": unit, "rank": rank, "terms": terms})
    matched = {m["paper"] for m in matches}
    ordered = [p for p in papers if p["key"] in matched] + [p for p in papers if p["key"] not in matched]
    kept = ordered[:ROUTE_DETAIL_MAX_PAPERS]
    kept_keys = {p["key"] for p in kept}
    return {"available": True, "project_id": project_id,
            "units": [{"id": c["id"], "name": c["name"], "terms": c.get("terms", []), "hint": c.get("hint", 2),
                       "type": c.get("type"), "why": c.get("why"), "state": c.get("state", "active"),
                       "side": bool(c.get("side")), "level": level[c["id"]]} for c in live],
            "prereqs": [{"from": e["from"], "to": e["to"], "state": e.get("state", "active")} for e in edges],
            "papers": [{"key": p["key"], "title": p.get("title") or p["key"], "published": p.get("published")} for p in kept],
            "matches": [m for m in matches if m["paper"] in kept_keys],
            "unmatched": [p["key"] for p in kept if p["key"] not in matched],
            "omitted": len(ordered) - len(kept)}


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


ROUTE_OPS = {"route-save", "route-manual", "route-start", "route-mode", "route-reject"}
ROUTE_SAVE_LABELS = {"candidate": "加入新方向"}   # what the undo button says when a save adds a proposed direction
MAX_REJECTED = 100
ROUTE_MARKS = {"mastered", "unlocked", "demoted"}
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
        for paper in papers:
            key = paper["key"]
            paper["projects"] = owners.get(key, [])
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

    def snapshot(self):
        with self._transaction(write=False):
            return self._snapshot()

    def action(self, body):
        if not isinstance(body, dict):
            raise ValueError("Action must be an object")
        op = body.get("op", body.get("action"))
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
                      "positions", "collapse", "undo", "export", "suggest", "suggest-apply",
                      "drafts", "draft-save", "draft-clear"} | ROUTE_OPS:
            raise ValueError("Unknown organization operation")
        if op == "suggest":
            return self._suggest(body)
        with self._transaction(write=op not in {"history", "export", "drafts"}):
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
                label = self._route_op(op, body, data)
                if label is None:
                    return self._snapshot()   # nothing changed: no revision bump, no undo step
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
            return result

    def _route_op(self, op, body, data):
        """Edit the project's learning map (data["route"]) and return the label shown by the undo button,
        or None when nothing would change (then nothing is written and no undo step is added).

        route-save takes `plan` (an AI or hand-written concept list, normalised) or `graph` (a structured map,
        validated), not both. Manual marks and start nodes follow their concept: by name when a new plan is
        normalised (its ids are renumbered), by id when a structured map is saved; marks of concepts that no
        longer exist are dropped. Everything is explicit user input; nothing is inferred from silence.
        """
        route = data.get("route")
        if op == "route-save":
            plan, graph = body.get("plan"), body.get("graph")
            if plan is not None and graph is not None:
                raise ValueError("Give either a plan or a graph, not both")
            old = route or {}
            if plan is not None:
                if not isinstance(plan, dict) or not isinstance(plan.get("concepts"), list) or len(plan["concepts"]) > MAX_PLAN_CONCEPTS:
                    raise ValueError("The plan is missing or too big")
                graph, _ = pathgraph.normalize(plan)
                if not graph["concepts"]:
                    raise ValueError("The plan has no usable concepts")
                names = {c["id"]: pathgraph._key(c["name"]) for c in (old.get("graph") or {}).get("concepts", [])}
                fresh = {pathgraph._key(c["name"]): c["id"] for c in graph["concepts"]}
                follow = lambda i: fresh.get(names.get(i))
            else:
                graph = pathgraph.validate(graph, tolerate={pathgraph._key(c.get("name")) for c in (old.get("graph") or {}).get("concepts", [])})
                before = {c["id"]: pathgraph._key(c["name"]) for c in (old.get("graph") or {}).get("concepts", [])}
                now_ = {c["id"]: pathgraph._key(c["name"]) for c in graph["concepts"]}
                # an id can be reused by a different concept (delete the last one, add another); a mark belongs to the concept
                follow = lambda i: i if i in now_ and before.get(i) == now_[i] else None
            manual = {follow(k): v for k, v in (old.get("manual") or {}).items() if follow(k)}
            start = [follow(i) for i in (old.get("start") or []) if follow(i)]
            updated = {"graph": graph, "mode": old.get("mode", "route"), "manual": manual, "start": start}
            if old.get("rejected"):
                updated["rejected"] = old["rejected"]   # a direction the person turned down stays turned down across saves
            if updated == route:
                return None
            data["route"] = updated
            return ROUTE_SAVE_LABELS.get(body.get("label"), "保存学习路径")
        if not route:
            raise ValueError("There is no learning path yet")
        known = {c["id"] for c in route["graph"]["concepts"]}
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
        norm = lambda text: " ".join(str(text or "").lower().split())
        for group in groups:
            if not group["keys"]:
                raise ValueError("所选类别至少需要一篇论文")
            wanted = redirect.get(group.get("target"), group.get("target"))
            target = next((d for d in data["directions"] if wanted and d["id"] == wanted), None)
            if target is None and group.get("target"):
                continue   # the category this addition was for is gone: skip it, never make a new one in its place
            if target is None:
                target = next((d for d in data["directions"]
                               if (d["id"] == group["id"] or d.get("source_suggestion") == group["id"])
                               and d["name"] == group["name"]
                               and d["color"].lower() == group.get("color", "#64748b").lower()), None)
            if target is None:
                level = placed.get(group.get("parent")) if group.get("parent") is not None else None
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
