"""SQLite storage for papers, exposures, feedback, profile versions and PDFs.

Append-only for user events; profile state is versioned so it can be inspected,
edited, frozen and rolled back. No writes touch an external service.
"""
import json
import sqlite3
from pathlib import Path

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
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """Additive migrations so an existing local database keeps working."""
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(papers)")}
        if "topic" not in columns:
            self.conn.execute("ALTER TABLE papers ADD COLUMN topic TEXT")

    def close(self):
        self.conn.close()

    # ---------------------------------------------------------------- papers
    def upsert_papers(self, papers):
        added = 0
        for paper in papers:
            cur = self.conn.execute(
                """INSERT OR IGNORE INTO papers
                   (key, openalex_id, doi, arxiv_id, title, abstract, published, source, topic, group_name, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (paper["key"], paper.get("openalex_id"), paper.get("doi"), paper.get("arxiv_id"),
                 paper["title"], paper.get("abstract"), paper.get("published"),
                 paper.get("source"), paper.get("topic"), paper.get("group_name"), now()))
            added += cur.rowcount
        self.conn.commit()
        return added

    def paper(self, key):
        row = self.conn.execute("SELECT * FROM papers WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def papers(self, limit=None):
        sql = "SELECT * FROM papers ORDER BY published DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in self.conn.execute(sql)]

    # ---------------------------------------------------------------- batches
    def create_batch(self, run_date, keys, source="openalex"):
        cur = self.conn.execute("INSERT INTO batches (run_date, created_at, source) VALUES (?,?,?)",
                                (run_date, now(), source))
        batch_id = cur.lastrowid
        stamp = now()
        for rank, key in enumerate(keys, 1):
            self.conn.execute("INSERT INTO exposures (batch_id, paper_key, rank, shown_at) VALUES (?,?,?,?)",
                              (batch_id, key, rank, stamp))
        self.conn.commit()
        return batch_id

    def batch(self, batch_id):
        rows = self.conn.execute(
            """SELECT e.rank, p.* FROM exposures e JOIN papers p ON p.key=e.paper_key
               WHERE e.batch_id=? ORDER BY e.rank""", (batch_id,)).fetchall()
        return [dict(r) for r in rows]

    def latest_batch(self):
        row = self.conn.execute("SELECT id FROM batches ORDER BY id DESC LIMIT 1").fetchone()
        return self.batch(row["id"]) if row else []

    def seen_keys(self):
        return {r["paper_key"] for r in self.conn.execute("SELECT DISTINCT paper_key FROM exposures")}

    # --------------------------------------------------------------- feedback
    def add_feedback(self, paper_key, action, reason=None):
        cur = self.conn.execute(
            "INSERT INTO feedback (paper_key, action, reason, created_at) VALUES (?,?,?,?)",
            (paper_key, action, reason, now()))
        self.conn.commit()
        return cur.lastrowid

    def undo_feedback(self, feedback_id):
        self.conn.execute("UPDATE feedback SET undone=1, undone_at=? WHERE id=?", (now(), feedback_id))
        self.conn.commit()

    def feedback(self, include_undone=False):
        sql = "SELECT * FROM feedback" + ("" if include_undone else " WHERE undone=0") + " ORDER BY id"
        return [dict(r) for r in self.conn.execute(sql)]

    def feedback_by_paper(self):
        """Latest effective feedback per paper, excluding undone events."""
        result = {}
        for row in self.conn.execute("SELECT * FROM feedback WHERE undone=0 ORDER BY id"):
            result[row["paper_key"]] = {"action": row["action"], "reason": row["reason"], "id": row["id"]}
        return result

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
    def record_pdf(self, paper_key, path, source_url=None):
        self.conn.execute(
            """INSERT INTO pdfs (paper_key, path, source_url, fetched_at) VALUES (?,?,?,?)
               ON CONFLICT(paper_key) DO UPDATE SET path=excluded.path, source_url=excluded.source_url,
               fetched_at=excluded.fetched_at""",
            (paper_key, str(path), source_url, now()))
        self.conn.commit()

    # --------------------------------------------------------------- settings
    def set_setting(self, key, value):
        self.conn.execute("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (key, json.dumps(value, ensure_ascii=False)))
        self.conn.commit()

    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    # ------------------------------------------------------------- summaries
    def save_summary(self, paper_key, one_liner, why_relevant, caution, model):
        self.conn.execute(
            """INSERT INTO summaries (paper_key, one_liner, why_relevant, caution, model, created_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(paper_key) DO UPDATE SET one_liner=excluded.one_liner,
               why_relevant=excluded.why_relevant, caution=excluded.caution, model=excluded.model,
               created_at=excluded.created_at""",
            (paper_key, one_liner, why_relevant, caution, model, now()))
        self.conn.commit()

    def summaries(self):
        return {r["paper_key"]: dict(r) for r in self.conn.execute("SELECT * FROM summaries")}

    # --------------------------------------------------------------- library
    def save_to_library(self, paper_key, note=None):
        """Idempotent: saving the same paper twice is a no-op."""
        self.conn.execute(
            "INSERT OR IGNORE INTO library (paper_key, saved_at, note) VALUES (?,?,?)",
            (paper_key, now(), note))
        self.conn.commit()

    def remove_from_library(self, paper_key):
        self.conn.execute("DELETE FROM library WHERE paper_key=?", (paper_key,))
        self.conn.commit()

    def library(self):
        rows = self.conn.execute(
            """SELECT l.saved_at, l.note, p.* FROM library l JOIN papers p ON p.key=l.paper_key
               ORDER BY l.saved_at DESC""").fetchall()
        return [dict(r) for r in rows]

    def in_library(self, paper_key):
        return self.conn.execute("SELECT 1 FROM library WHERE paper_key=?", (paper_key,)).fetchone() is not None

    # ------------------------------------------------------------ qa history
    def add_qa(self, paper_key, role, content):
        self.conn.execute("INSERT INTO qa_history (paper_key, role, content, created_at) VALUES (?,?,?,?)",
                          (paper_key, role, content, now()))
        self.conn.commit()

    # ------------------------------------------------------------- full text
    def save_fulltext(self, paper_key, pages):
        stamp = now()
        for page in pages:
            self.conn.execute(
                """INSERT INTO fulltext (paper_key, page, content, chars, created_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(paper_key, page) DO UPDATE SET content=excluded.content,
                   chars=excluded.chars, created_at=excluded.created_at""",
                (paper_key, int(page["page"]), page.get("text") or "", len(page.get("text") or ""), stamp))
        self.conn.commit()

    def fulltext_pages(self, paper_key):
        rows = self.conn.execute(
            "SELECT page, content FROM fulltext WHERE paper_key=? ORDER BY page", (paper_key,)).fetchall()
        return [{"page": r["page"], "text": r["content"]} for r in rows]

    def qa_history(self, paper_key, limit=20):
        rows = self.conn.execute(
            "SELECT role, content, created_at FROM qa_history WHERE paper_key IS ? ORDER BY id DESC LIMIT ?",
            (paper_key, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
