"""SQLite storage for papers, exposures, feedback, profile versions and PDFs.

Append-only for user events; profile state is versioned so it can be inspected,
edited, frozen and rolled back. No writes touch an external service.
"""
import json
import sqlite3
import uuid
from pathlib import Path

from .sources import merge_oa

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
  key TEXT PRIMARY KEY,              -- DOI or OpenAlex ID or normalized title
  openalex_id TEXT, doi TEXT, arxiv_id TEXT,
  title TEXT NOT NULL, abstract TEXT, published TEXT, source TEXT, topic TEXT,
  group_name TEXT,                   -- 'field' or 'distractor'
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date TEXT NOT NULL, created_at TEXT NOT NULL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exposures (
  batch_id INTEGER NOT NULL, paper_key TEXT NOT NULL, rank INTEGER NOT NULL,
  shown_at TEXT NOT NULL, PRIMARY KEY (batch_id, paper_key)
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_key TEXT NOT NULL, action TEXT NOT NULL, reason TEXT,
  created_at TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0,
  undone_at TEXT
);
CREATE TABLE IF NOT EXISTS profile_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL, note TEXT, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pdfs (
  paper_key TEXT PRIMARY KEY, path TEXT NOT NULL, source_url TEXT, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
  paper_key TEXT PRIMARY KEY, one_liner TEXT, why_relevant TEXT, caution TEXT,
  model TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS library (
  paper_key TEXT PRIMARY KEY, saved_at TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS fulltext (
  paper_key TEXT NOT NULL, page INTEGER NOT NULL, content TEXT NOT NULL, chars INTEGER NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (paper_key, page)
);
CREATE TABLE IF NOT EXISTS qa_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_key TEXT, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qa_paper ON qa_history(paper_key, id);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_feedback_paper ON feedback(paper_key, undone);
CREATE INDEX IF NOT EXISTS idx_exposures_paper ON exposures(paper_key);
"""


def now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


INTEREST_ACTIONS = ("useful", "irrelevant")      # what the reader likes
FAMILIARITY_ACTIONS = ("understood", "too_hard")  # how well the reader knows it


def collapse_feedback(rows):
    """{paper_key: entry} from feedback rows in id order (undone ones already left out).

    A paper keeps its latest label in each of two separate dimensions, so a later "understood" or "too hard"
    never replaces an earlier "useful" or "irrelevant", and the other way round. The entry is the interest
    label when there is one, else the familiarity label ({action, reason, id}); `familiar` is the latest
    familiarity label or None; `at` is when it was given. An action this version does not know is ignored.
    """
    interest, familiar = {}, {}
    for row in rows:
        entry = {"action": row["action"], "reason": row["reason"], "id": row["id"], "at": row["created_at"]}
        if row["action"] in INTEREST_ACTIONS:
            interest[row["paper_key"]] = entry
        elif row["action"] in FAMILIARITY_ACTIONS:
            familiar[row["paper_key"]] = entry
    return {key: {**(interest.get(key) or familiar[key]), "familiar": familiar.get(key)}
            for key in sorted(interest.keys() | familiar.keys())}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # The HTTP server is single-threaded, but tests and tooling may hand the store to another
        # thread; keep a lock so concurrent access cannot corrupt the file.
        self._lock = __import__("threading").RLock()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def init(self):
        from app.migrations import apply_migrations, get_schema_version, pending
        if self._has_user_data() and 'work_type' not in {r[1] for r in self.conn.execute('PRAGMA table_info(papers)')}:
            target=self.path.with_name(f"{self.path.name}.pre-work-type.bak")
            if target.exists():
                target=self.path.with_name(f"{self.path.name}.pre-work-type-{uuid.uuid4().hex[:12]}.bak")
            try:
                self.backup(target)
            except BaseException:
                # A partial failed backup must not suppress the next attempt; original remains untouched.
                try:target.unlink(missing_ok=True)
                except OSError:pass
                raise
        if self._has_user_data() and pending(self.conn) > 0:
            self.backup(self.path.with_name(
                f"{self.path.name}.pre-v{get_schema_version(self.conn)}.bak"))
        self.conn.executescript(SCHEMA)
        self._migrate()
        # Apply structured migrations
        apply_migrations(self.conn)
        self.conn.commit()

    def _has_user_data(self):
        return self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='papers'").fetchone() is not None

    def backup(self, target):
        """Consistent single-file copy (WAL included); an existing backup is never overwritten."""
        target = Path(target)
        if target.exists():
            return target
        destination = sqlite3.connect(str(target))
        try:
            self.conn.backup(destination)
        finally:
            destination.close()
        return target

    def _migrate(self):
        """Additive migrations so an existing local database keeps working."""
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(papers)")}
        if "topic" not in columns:
            self.conn.execute("ALTER TABLE papers ADD COLUMN topic TEXT")
        if "work_type" not in columns:
            self.conn.execute("ALTER TABLE papers ADD COLUMN work_type TEXT")

    def close(self):
        self.conn.close()

    # ---------------------------------------------------------------- papers
    def upsert_papers(self, papers, project_id=None, commit=True, stats=None):
        """Insert papers, assigning to default project if project_id not specified. Returns how many rows are new to the
        library; a caller that passes `stats` also gets `stats['linked']` (how many project links were new) and `stats['linked_keys']`."""
        # Get default project once if needed
        default_project_id = None
        if not project_id and papers:
            # Check if any paper lacks project_id
            needs_default = any(not p.get("project_id") for p in papers)
            if needs_default:
                default_row = self.conn.execute(
                    "SELECT id FROM projects ORDER BY creation_timestamp LIMIT 1"
                ).fetchone()
                default_project_id = default_row["id"] if default_row else None

        added = linked = 0
        linked_keys = []
        for paper in papers:
            paper_project_id = paper.get("project_id") or project_id or default_project_id
            cur = self.conn.execute(
                """INSERT OR IGNORE INTO papers
                   (key, openalex_id, doi, arxiv_id, title, abstract, published, source, topic, group_name, project_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (paper["key"], paper.get("openalex_id"), paper.get("doi"), paper.get("arxiv_id"),
                 paper["title"], paper.get("abstract"), paper.get("published"),
                 paper.get("source"), paper.get("topic"), paper.get("group_name"), paper_project_id, now()))
            added += cur.rowcount
            for column in ("openalex_id", "arxiv_id"):       # a later lookup fills a blank identifier; a stored one is never replaced
                if paper.get(column):
                    self.conn.execute(f"UPDATE papers SET {column}=? WHERE key=? AND ({column} IS NULL OR {column}='')", (paper[column], paper["key"]))
            if isinstance(paper.get('work_type'),str) and paper['work_type']:
                self.conn.execute('UPDATE papers SET work_type=? WHERE key=?',(paper['work_type'][:80],paper['key']))
            if 'metadata_language' in paper or 'language' in paper:
                from .paper_language import metadata_code
                self.conn.execute('''UPDATE papers SET metadata_language=?, metadata_language_source=? WHERE key=?''',
                    (metadata_code(paper.get('metadata_language', paper.get('language'))),
                     str(paper.get('metadata_language_source') or 'metadata')[:80], paper['key']))
            if paper.get("oa") is not None:
                # Open-access status changes over time, so OpenAlex's newest report replaces its old fields; a source
                # that only reports a page (Baidu Scholar) adds it without wiping them, and the other way round.
                stored = self._stored_oa(paper["key"])
                if stored is None and cur.rowcount == 0 and str(paper["key"]).startswith("baidu:"):
                    # An older `baidu:` row with no facts stored is a Baidu Scholar paper without a page (every later Baidu row
                    # carries `via`): keep that attribution when another Baidu source reports the paper too.
                    stored = {"via": ["baidu_scholar"]}
                self.conn.execute("UPDATE papers SET oa_json=? WHERE key=?",
                                  (json.dumps(merge_oa(stored, paper["oa"]), ensure_ascii=False), paper["key"]))
            if paper_project_id:
                if self.add_project_paper(paper_project_id, paper["key"],
                                          paper.get("relation_kind") or
                                          ("seed" if paper.get("group_name") == "seed" else "discovered"),
                                          paper.get("source_project_id"), commit=False):
                    linked += 1
                    linked_keys.append(paper["key"])
        if stats is not None:
            stats["linked"], stats["linked_keys"] = linked, linked_keys
        if commit:
            self.conn.commit()
        return added

    def add_project_paper(self, project_id, paper_key, relation_kind="shared",
                          source_project_id=None, commit=True):
        """Link a canonical paper to a project. An existing link keeps its kind (a seed is
        never downgraded by a later discovery/share); only promotion to 'seed' applies.
        Returns True when the link did not exist before."""
        if relation_kind not in {"discovered", "seed", "imported", "shared"}:
            raise ValueError("关系类型无效")
        if not self.conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise ValueError("项目不存在")
        if source_project_id and not self.conn.execute("SELECT 1 FROM projects WHERE id=?", (source_project_id,)).fetchone():
            raise ValueError("来源项目不存在")
        if not self.conn.execute("SELECT 1 FROM papers WHERE key=?", (paper_key,)).fetchone():
            raise ValueError("论文不存在")
        is_new = not self.conn.execute("SELECT 1 FROM project_papers WHERE project_id=? AND paper_key=?",
                                       (project_id, paper_key)).fetchone()
        self.conn.execute(
            """INSERT INTO project_papers(project_id,paper_key,relation_kind,added_at,source_project_id)
               VALUES (?,?,?,?,?) ON CONFLICT(project_id,paper_key) DO UPDATE SET
               relation_kind=CASE WHEN excluded.relation_kind='seed' THEN 'seed'
                                  ELSE project_papers.relation_kind END,
               source_project_id=COALESCE(project_papers.source_project_id, excluded.source_project_id)""",
            (project_id, paper_key, relation_kind or "shared", now(), source_project_id))
        if commit:
            self.conn.commit()
        return is_new

    def remove_project_paper(self, project_id, paper_key):
        if not self.conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise ValueError("项目不存在")
        relation = self.conn.execute(
            "SELECT relation_kind FROM project_papers WHERE project_id=? AND paper_key=?",
            (project_id, paper_key)).fetchone()
        self.conn.execute("DELETE FROM project_papers WHERE project_id=? AND paper_key=?", (project_id, paper_key))
        self.conn.execute("DELETE FROM project_library WHERE project_id=? AND paper_key=?", (project_id, paper_key))
        if not self.conn.execute("SELECT 1 FROM project_library WHERE paper_key=? LIMIT 1", (paper_key,)).fetchone():
            self.conn.execute("DELETE FROM library WHERE paper_key=?", (paper_key,))
        if relation and relation[0] == "seed":
            keys = self.get_setting(f"seed_keys_{project_id}", [])
            self.set_setting(f"seed_keys_{project_id}", [key for key in keys if key != paper_key])
        self.conn.commit()

    def project_papers(self, project_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT p.*, pp.relation_kind, pp.added_at, pp.source_project_id "
            "FROM project_papers pp JOIN papers p ON p.key=pp.paper_key "
            "WHERE pp.project_id=? ORDER BY p.published DESC, p.key", (project_id,))]

    def paper_projects(self, paper_key):
        return [dict(r) for r in self.conn.execute(
            "SELECT pp.*, pr.name, spr.name AS source_project_name FROM project_papers pp "
            "JOIN projects pr ON pr.id=pp.project_id LEFT JOIN projects spr ON spr.id=pp.source_project_id "
            "WHERE pp.paper_key=? ORDER BY pr.creation_timestamp", (paper_key,))]

    def paper(self, key):
        row = self.conn.execute("SELECT * FROM papers WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def papers(self, limit=None):
        sql = "SELECT * FROM papers ORDER BY published DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in self.conn.execute(sql)]

    # ---------------------------------------------------------------- batches
    def create_batch(self, run_date, keys, source="openalex", project_id=None, route=None, route_evidence=None):
        """route: optional {paper_key: (concept_id, kind, concept_name, layer)} for batches built from a learning map."""
        receipt = None
        if route_evidence:
            if not isinstance(route_evidence, dict) or set(route_evidence)-set(keys) or len(route_evidence)>5:
                raise ValueError('Invalid exploration evidence')
            receipt=json.dumps(route_evidence,ensure_ascii=False,allow_nan=False)
            if len(receipt.encode('utf-8'))>32768:raise ValueError('Exploration evidence exceeds 32 KiB')
        cur = self.conn.execute("INSERT INTO batches (run_date, created_at, source, project_id) VALUES (?,?,?,?)",
                                (run_date, now(), source, project_id))
        batch_id = cur.lastrowid
        stamp = now()
        route = route or {}
        for rank, key in enumerate(keys, 1):
            node, kind, name, layer = (tuple(route.get(key, ())) + (None, None, None, None))[:4]
            self.conn.execute("""INSERT INTO exposures (batch_id, paper_key, rank, shown_at, route_node, route_kind, route_name, route_layer)
                                 VALUES (?,?,?,?,?,?,?,?)""", (batch_id, key, rank, stamp, node, kind, name, layer))
        if receipt is not None:
            self.conn.execute('INSERT INTO settings(key,value) VALUES (?,?)',('route_exploration_evidence_'+str(batch_id),receipt))
        self.conn.commit()
        return batch_id

    def batch(self, batch_id):
        rows = self.conn.execute(
            """SELECT e.batch_id, e.rank, e.route_node, e.route_kind, e.route_name, e.route_layer, p.* FROM exposures e JOIN papers p ON p.key=e.paper_key
               WHERE e.batch_id=? ORDER BY e.rank""", (batch_id,)).fetchall()
        return [dict(r) for r in rows]

    def latest_batch(self, project_id=None):
        if project_id:
            row = self.conn.execute(
                "SELECT id FROM batches WHERE project_id=? ORDER BY id DESC LIMIT 1",
                (project_id,)).fetchone()
        else:
            row = self.conn.execute("SELECT id FROM batches ORDER BY id DESC LIMIT 1").fetchone()
        return self.batch(row["id"]) if row else []

    def seen_keys(self, project_id=None):
        if project_id:
            return {r["paper_key"] for r in self.conn.execute(
                """SELECT DISTINCT e.paper_key FROM exposures e
                   JOIN batches b ON b.id = e.batch_id
                   WHERE b.project_id=?""", (project_id,))}
        return {r["paper_key"] for r in self.conn.execute("SELECT DISTINCT paper_key FROM exposures")}

    # --------------------------------------------------------------- feedback
    def add_feedback(self, paper_key, action, reason=None):
        cur = self.conn.execute(
            "INSERT INTO feedback (paper_key, action, reason, created_at) VALUES (?,?,?,?)",
            (paper_key, action, reason, now()))
        self.conn.commit()
        return cur.lastrowid

    def undo_feedback(self, feedback_id):
        with self._lock:
            if self.conn.in_transaction:
                raise RuntimeError("Feedback undo requires an idle connection")
            self.conn.execute("UPDATE feedback SET undone=1, undone_at=? WHERE id=?", (now(), feedback_id))
            self.conn.commit()

    def feedback(self, include_undone=False):
        sql = "SELECT * FROM feedback" + ("" if include_undone else " WHERE undone=0") + " ORDER BY id"
        return [dict(r) for r in self.conn.execute(sql)]

    def feedback_by_paper(self):
        """Latest effective feedback per paper, excluding undone events. See collapse_feedback."""
        return collapse_feedback(self.conn.execute("SELECT * FROM feedback WHERE undone=0 ORDER BY id"))

    # ---------------------------------------------------------------- profile
    def save_profile(self, data, note=None):
        cur = self.conn.execute("INSERT INTO profile_versions (created_at, note, data) VALUES (?,?,?)",
                                (now(), note, json.dumps(data, ensure_ascii=False, sort_keys=True)))
        self.conn.commit()
        return cur.lastrowid

    def profile_versions(self):
        return [{"id": r["id"], "created_at": r["created_at"], "note": r["note"],
                 "data": json.loads(r["data"])}
                for r in self.conn.execute("SELECT * FROM profile_versions ORDER BY id")]

    def current_profile(self):
        row = self.conn.execute("SELECT * FROM profile_versions ORDER BY id DESC LIMIT 1").fetchone()
        return json.loads(row["data"]) if row else None

    # -------------------------------------------------------------------- pdf
    def record_pdf(self, paper_key, path, source_url=None, sha256=None, size=None,
                   source_kind=None, license=None, commit=True):
        self.conn.execute('DELETE FROM settings WHERE key=?',('pdf_verification_'+paper_key,))
        self.conn.execute(
            """INSERT INTO pdfs (paper_key, path, source_url, fetched_at, sha256, bytes, source_kind, license)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(paper_key) DO UPDATE SET path=excluded.path, source_url=excluded.source_url,
               fetched_at=excluded.fetched_at, sha256=excluded.sha256, bytes=excluded.bytes,
               source_kind=excluded.source_kind, license=excluded.license""",
            (paper_key, str(path), source_url, now(), sha256, size, source_kind, license))
        self.conn.execute(
            """INSERT INTO pdf_versions (paper_key, path, source_url, sha256, bytes, source_kind, license, fetched_at)
               SELECT ?,?,?,?,?,?,?,? WHERE NOT EXISTS
               (SELECT 1 FROM (SELECT path,sha256 FROM pdf_versions WHERE paper_key=? ORDER BY id DESC LIMIT 1) WHERE path=? AND sha256 IS ?)""",
            (paper_key, str(path), source_url, sha256, size, source_kind, license, now(), paper_key, str(path), sha256))
        if commit:
            self.conn.commit()

    def pdf_history(self, paper_key):
        """Every archived copy of a paper's PDF, oldest first, with where each one came from. The last entry is the current one."""
        return [dict(r) for r in self.conn.execute(
            "SELECT path, source_url, sha256, bytes, source_kind, license, fetched_at FROM pdf_versions "
            "WHERE paper_key=? ORDER BY id", (paper_key,))]

    def _stored_oa(self, paper_key):
        """The open-access facts stored for a paper as a dict, or None (nothing stored, or text that is not JSON)."""
        row = self.conn.execute("SELECT oa_json FROM papers WHERE key=?", (paper_key,)).fetchone()
        try:
            stored = json.loads(row["oa_json"]) if row and row["oa_json"] else None
        except ValueError:
            stored = None
        return stored if isinstance(stored, dict) else None

    def set_paper_oa(self, paper_key, oa):
        """Merge a report into the stored open-access facts (see sources.merge_oa); None clears them."""
        merged = merge_oa(self._stored_oa(paper_key), oa) if oa is not None else None
        self.conn.execute("UPDATE papers SET oa_json=? WHERE key=?",
                          (json.dumps(merged, ensure_ascii=False) if merged is not None else None, paper_key))
        self.conn.commit()

    def set_metadata_language_if_unknown(self, paper_key, code, source):
        """Record a source's language report only where none is stored: a stored report is never replaced."""
        from .paper_language import metadata_code
        code = metadata_code(code)
        if code:
            self.conn.execute("UPDATE papers SET metadata_language=?, metadata_language_source=? WHERE key=? AND metadata_language IS NULL",
                              (code, str(source)[:80], paper_key))
            self.conn.commit()

    def record_fulltext_language(self, paper_key, language, pdf_sha256, method):
        from .paper_language import LANGUAGES
        if (not isinstance(pdf_sha256, str) or len(pdf_sha256) != 64
                or any(c not in '0123456789abcdef' for c in pdf_sha256)):
            raise ValueError('全文语言核验必须对应当前 PDF 版本')
        if not isinstance(language, str) or language not in LANGUAGES or method != 'manual':
            raise ValueError('全文语言或核验方式无效')
        cur = self.conn.execute('''INSERT INTO fulltext_languages
            SELECT ?,?,?,?,? FROM pdfs WHERE paper_key=? AND sha256=?
            ON CONFLICT(paper_key,pdf_sha256) DO UPDATE SET language=excluded.language,
            method=excluded.method, verified_at=excluded.verified_at''',
            (paper_key, pdf_sha256, language, method, now(), paper_key, pdf_sha256))
        if cur.rowcount != 1:
            self.conn.rollback()
            raise ValueError('全文语言核验必须对应当前 PDF 版本')
        self.conn.commit()

    def paper_language(self, paper_key):
        paper = self.paper(paper_key)
        if not paper:
            raise ValueError('论文不存在')
        verified = self.conn.execute('''SELECT l.* FROM fulltext_languages l
            JOIN pdfs p ON p.paper_key=l.paper_key AND p.sha256=l.pdf_sha256
            WHERE l.paper_key=?''', (paper_key,)).fetchone()
        return {'metadata_language': paper['metadata_language'],
                'metadata_source': paper['metadata_language_source'],
                'fulltext_language': verified['language'] if verified else None,
                'fulltext_status': 'verified' if verified else 'unverified',
                'verification_method': verified['method'] if verified else None,
                'pdf_sha256': verified['pdf_sha256'] if verified else None}

    # --------------------------------------------------------------- settings
    def set_setting(self, key, value):
        self.conn.execute("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (key, json.dumps(value, ensure_ascii=False)))
        self.conn.commit()

    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    # ------------------------------------------------------------- summaries
    def save_summary(self, paper_key, one_liner, why_relevant, caution, model, commit=True):
        self.conn.execute(
            """INSERT INTO summaries (paper_key, one_liner, why_relevant, caution, model, created_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(paper_key) DO UPDATE SET one_liner=excluded.one_liner,
               why_relevant=excluded.why_relevant, caution=excluded.caution, model=excluded.model,
               created_at=excluded.created_at""",
            (paper_key, one_liner, why_relevant, caution, model, now()))
        if commit:
            self.conn.commit()

    def summaries(self):
        return {r["paper_key"]: dict(r) for r in self.conn.execute("SELECT * FROM summaries")}

    # --------------------------------------------------------------- library
    def save_to_library(self, paper_key, note=None, project_id=None, commit=True):
        """Idempotent: saving the same paper twice is a no-op. `commit=False` leaves the write inside the caller's
        transaction (library import saves hundreds of papers atomically)."""
        if project_id:
            self.add_project_paper(project_id, paper_key, "shared", commit=False)
            self.conn.execute(
                "INSERT OR IGNORE INTO project_library(project_id,paper_key,saved_at,note) VALUES (?,?,?,?)",
                (project_id, paper_key, now(), note))
            # Keep the legacy global view available to older callers.  It is only
            # a compatibility index; project_library remains the source of truth.
            self.conn.execute(
                "INSERT OR IGNORE INTO library (paper_key, saved_at, note) VALUES (?,?,?)",
                (paper_key, now(), note))
            if commit:
                self.conn.commit()
            return
        # Older integrations did not pass a project.  Mirror the save into the
        # owning project when one can be determined, while retaining the legacy
        # row for compatibility with those integrations.
        owner = self.conn.execute("SELECT project_id FROM papers WHERE key=?", (paper_key,)).fetchone()
        if owner and owner[0]:
            self.add_project_paper(owner[0], paper_key, "discovered", commit=False)
            self.conn.execute(
                "INSERT OR IGNORE INTO project_library(project_id,paper_key,saved_at,note) VALUES (?,?,?,?)",
                (owner[0], paper_key, now(), note))
        self.conn.execute(
            "INSERT OR IGNORE INTO library (paper_key, saved_at, note) VALUES (?,?,?)",
            (paper_key, now(), note))
        if commit:
            self.conn.commit()

    def remove_from_library(self, paper_key, project_id=None):
        if project_id:
            self.conn.execute("DELETE FROM project_library WHERE project_id=? AND paper_key=?", (project_id, paper_key))
            remaining = self.conn.execute("SELECT 1 FROM project_library WHERE paper_key=? LIMIT 1", (paper_key,)).fetchone()
            if not remaining:
                self.conn.execute("DELETE FROM library WHERE paper_key=?", (paper_key,))
            self.conn.commit()
            return
        self.conn.execute("DELETE FROM library WHERE paper_key=?", (paper_key,))
        self.conn.commit()

    def library(self, project_id=None):
        if project_id:
            rows = self.conn.execute(
                """SELECT l.saved_at, l.note, p.* FROM project_library l
                   JOIN papers p ON p.key=l.paper_key WHERE l.project_id=?
                   ORDER BY l.saved_at DESC""", (project_id,)).fetchall()
            return [dict(r) for r in rows]
        rows = self.conn.execute(
            """SELECT l.saved_at, l.note, p.* FROM library l JOIN papers p ON p.key=l.paper_key
               ORDER BY l.saved_at DESC""").fetchall()
        return [dict(r) for r in rows]

    def in_library(self, paper_key, project_id=None):
        if project_id:
            return self.conn.execute("SELECT 1 FROM project_library WHERE project_id=? AND paper_key=?",
                                     (project_id, paper_key)).fetchone() is not None
        return self.conn.execute("SELECT 1 FROM library WHERE paper_key=?", (paper_key,)).fetchone() is not None

    # -------------------------------------------------------- guidance drafts
    def create_guidance_session(self, session_id, name, transcript, draft, status="draft"):
        stamp = now()
        self.conn.execute("""INSERT INTO project_guidance_sessions
            (id,name,status,transcript,draft,turn_count,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (session_id, name, status, json.dumps(transcript, ensure_ascii=False),
             json.dumps(draft, ensure_ascii=False), 0, stamp, stamp))
        self.conn.commit()

    def guidance_session(self, session_id):
        row = self.conn.execute("SELECT * FROM project_guidance_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["transcript"] = json.loads(result["transcript"] or "[]")
        result["draft"] = json.loads(result["draft"] or "{}")
        return result

    def update_guidance_session(self, session_id, **fields):
        allowed = {"status", "transcript", "draft", "turn_count"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        if "transcript" in fields:
            fields["transcript"] = json.dumps(fields["transcript"], ensure_ascii=False)
        if "draft" in fields:
            fields["draft"] = json.dumps(fields["draft"], ensure_ascii=False)
        fields["updated_at"] = now()
        sql = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE project_guidance_sessions SET {sql} WHERE id=?", (*fields.values(), session_id))
        self.conn.commit()

    # ------------------------------------------------------------ qa history
    def add_qa(self, paper_key, role, content, project_id=None):
        self.conn.execute("INSERT INTO qa_history (paper_key, role, content, created_at, project_id) VALUES (?,?,?,?,?)",
                          (paper_key, role, content, now(), project_id))
        self.conn.commit()

    # ------------------------------------------------------------- full text
    def save_fulltext(self, paper_key, pages, source_pdf_sha256=None):
        stamp = now()
        if source_pdf_sha256 is not None and (
                not isinstance(source_pdf_sha256, str) or len(source_pdf_sha256) != 64
                or any(c not in '0123456789abcdef' for c in source_pdf_sha256)):
            raise ValueError('正文来源 PDF 版本无效')
        # An unversioned reader may save text for legacy reading, but it cannot
        # claim this came from today's PDF. A supplied version is checked in the
        # write statement, under the same transaction as every page.
        with self._lock, self.conn:
            for page in pages:
                cur = self.conn.execute(
                    """INSERT INTO fulltext (paper_key, page, content, chars, created_at, source_pdf_sha256)
                       SELECT ?,?,?,?,?,? WHERE ? IS NULL OR EXISTS
                       (SELECT 1 FROM pdfs WHERE paper_key=? AND sha256=?)
                       ON CONFLICT(paper_key, page) DO UPDATE SET content=excluded.content,
                       chars=excluded.chars, created_at=excluded.created_at, source_pdf_sha256=excluded.source_pdf_sha256""",
                    (paper_key, int(page["page"]), page.get("text") or "", len(page.get("text") or ""),
                     stamp, source_pdf_sha256, source_pdf_sha256, paper_key, source_pdf_sha256))
                if cur.rowcount != 1:
                    raise ValueError('PDF 已变化，请重新提取正文')

    def fulltext_pages(self, paper_key, current_only=False, source_pdf_sha256=None):
        clause, params = '', [paper_key]
        if source_pdf_sha256 is not None:
            clause = ' AND source_pdf_sha256=? AND EXISTS (SELECT 1 FROM pdfs WHERE paper_key=? AND sha256=?)'
            params.extend((source_pdf_sha256, paper_key, source_pdf_sha256))
        elif current_only:
            clause = ''' AND (NOT EXISTS (SELECT 1 FROM pdfs WHERE paper_key=?)
                OR source_pdf_sha256=(SELECT sha256 FROM pdfs WHERE paper_key=?))'''
            params.extend((paper_key, paper_key))
        rows = self.conn.execute(
            "SELECT page, content FROM fulltext WHERE paper_key=?" + clause + " ORDER BY page", params).fetchall()
        return [{"page": r["page"], "text": r["content"]} for r in rows]

    def qa_history(self, paper_key, limit=20, project_id=None):
        if project_id:
            rows = self.conn.execute(
                "SELECT role, content, created_at FROM qa_history WHERE paper_key IS ? AND project_id=? ORDER BY id DESC LIMIT ?",
                (paper_key, project_id, limit)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT role, content, created_at FROM qa_history WHERE paper_key IS ? AND project_id IS NULL ORDER BY id DESC LIMIT ?",
                (paper_key, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
