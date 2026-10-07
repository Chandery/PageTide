"""Bring an existing PDF library into a project: staging batches, paced metadata matching, one commit.

A batch is a staging area. Files are uploaded one at a time into `imports/batches/<id>/`, each item is
matched to public metadata (or kept as an unresolved PDF), the person reviews the result, and only then
does one commit write papers, links, library saves and archived PDFs. Nothing here is a model call.

The two tables are created lazily (like organization.py's drafts): they are new, nothing is altered or
back-filled, and they cannot collide with another branch's migration number on a shared database."""
import hashlib
import json
import re
import shutil
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import operation_lock, reference_files
from .creation import archive_pdf, parse_seed
from .db import now
from .sources import SourceError, fetch_seed_work, similarity, slim, title_key

SOURCES = ("files", "folder", "zotero")
OPEN_STATUSES = ("collecting", "resolving", "paused", "review")
STATES = ("pending", "resolving", "matched", "needs_choice", "unmatched", "duplicate", "failed", "excluded")
OPTION_DEFAULTS = {"online": True, "folder_categories": True, "root_category": False,
                   "include_fileless": False, "replace_pdf": False}

MAX_FILE_BYTES = 60 * 1024 * 1024
MAX_FILES = 2000
MAX_SEGMENTS = 40
MAX_NAME = 200
MAX_HINT_TITLES = 3
MAX_HINT_TEXT = 300
DISK_RESERVE_BYTES = 512 * 1024 * 1024
STALE_DAYS = 30
CHUNK = 1024 * 1024

DOI_CHUNK = 50            # DOIs per OpenAlex request
AUTO_MATCH = 0.8          # title similarity accepted without asking (as on the creation page)
CANDIDATE_MIN = 0.25      # below this a hit is noise, not a candidate
MAX_CANDIDATES = 5
AUTO_GAP = 0.05           # the best title hit must beat the runner-up by this much to be accepted without asking
MIN_COMPARE_WORDS = 3     # titles shorter than this are too thin to check an identifier against
MIN_AUTO_WORDS = 2        # a one-word title is never accepted on its own
_WORD = re.compile(r"[a-z0-9\u4e00-\u9fff]+")
MAX_TITLE_LOOKUPS = 2     # title guesses tried per PDF
ACTIONS = ("pick", "lookup", "unresolved", "exclude", "include")
LOOKUP_MESSAGES = {"unavailable": "OpenAlex 暂时限流，请稍后再试", "network_error": "无法连接 OpenAlex，请检查网络",
                   "not_found": "OpenAlex 没有找到这个标识"}
CREDITS_PER_SEARCH = 10   # OpenAlex meters each search; fewer credits left than this pauses the batch
_STORAGE_KEY = re.compile(r"[A-Z0-9]{8}")
_ARXIV_NAME = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?")

SCHEMA = """
CREATE TABLE IF NOT EXISTS import_batches (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source TEXT NOT NULL CHECK(source IN ('files','folder','zotero')),
  root_name TEXT,
  options TEXT NOT NULL,
  sidecar TEXT,
  status TEXT NOT NULL CHECK(status IN ('collecting','resolving','paused','review','committing','committed','discarded','failed')),
  pause_reason TEXT,
  result TEXT,
  categories_applied INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  committed_at TEXT);
CREATE TABLE IF NOT EXISTS import_items (
  id INTEGER PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('pdf','entry')),
  relative_path TEXT,
  original_name TEXT,
  size INTEGER,
  last_modified INTEGER,
  sha256 TEXT,
  hints TEXT,
  entry TEXT,
  folders TEXT NOT NULL DEFAULT '[[]]',
  state TEXT NOT NULL CHECK(state IN ('pending','resolving','matched','needs_choice','unmatched','duplicate','failed','excluded')),
  match_source TEXT,
  paper TEXT,
  candidates TEXT,
  error TEXT,
  duplicate_of INTEGER,
  paper_key TEXT,
  committed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(batch_id, relative_path));
CREATE INDEX IF NOT EXISTS idx_import_items_state ON import_items(batch_id, state);
CREATE INDEX IF NOT EXISTS idx_import_items_sha ON import_items(sha256);
"""

_BATCH_JSON = ("options", "sidecar", "result")
_ITEM_JSON = ("hints", "entry", "folders", "paper", "candidates")


def _loads(value, default=None):
    try:
        return json.loads(value) if value else default
    except ValueError:
        return default


def _segment(text):
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_NAME:  # keep the extension: ".pdf" is how a person recognises the file
        suffix = Path(text).suffix[:12]
        text = text[:MAX_NAME - len(suffix)] + suffix
    return text


def clean_path(path):
    """Segments of a relative path that cannot leave the batch: NFC, no '..', no absolute root, no NUL."""
    text = unicodedata.normalize("NFC", str(path or ""))
    if "\x00" in text:
        raise ValueError("文件路径无效")
    segments = []
    for part in text.replace("\\", "/").split("/"):
        part = _segment(part)
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("文件路径无效")
        segments.append(part)
    if not segments or len(segments) > MAX_SEGMENTS:
        raise ValueError("文件路径无效")
    return segments


def clean_hints(hints):
    """Only what pdf.js can read off the first pages, short and typed; anything else is dropped."""
    if not isinstance(hints, dict):
        return {}
    out = {}
    for key in ("arxiv", "doi"):
        value = hints.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()[:MAX_HINT_TEXT]
    titles = [t.strip()[:MAX_HINT_TEXT] for t in (hints.get("titles") or []) if isinstance(t, str) and t.strip()]
    if titles:
        out["titles"] = titles[:MAX_HINT_TITLES]
    return out


def clean_options(options):
    options = options if isinstance(options, dict) else {}
    return {key: bool(options.get(key, default)) for key, default in OPTION_DEFAULTS.items()}


class LibraryImport:
    def __init__(self, data_dir, store, client=None):
        self.data = Path(data_dir)
        self.store = store
        self.client = client
        self.conn = store.conn
        self.conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ rows
    def _staging(self, batch_id):
        return self.data / "imports" / "batches" / batch_id

    def _batch_row(self, batch_id):
        row = self.conn.execute("SELECT * FROM import_batches WHERE id=?", (str(batch_id),)).fetchone()
        if not row:
            raise ValueError("导入批次不存在")
        return row

    @staticmethod
    def _batch_dict(row):
        out = dict(row)
        for key in _BATCH_JSON:
            out[key] = _loads(out.get(key), {} if key == "options" else None)
        return out

    @staticmethod
    def _item_dict(row):
        out = dict(row)
        for key in _ITEM_JSON:
            out[key] = _loads(out.get(key), [[]] if key == "folders" else None)
        out["committed"] = bool(out["committed"])
        return out

    def _touch(self, batch_id, **fields):
        fields["updated_at"] = now()
        names = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE import_batches SET {names} WHERE id=?", (*fields.values(), batch_id))

    def _touch_open(self, batch_id, **fields):
        """Like _touch, but only while the batch is open: a resolver that finishes after the batch was discarded (or
        committed) must not bring it back."""
        fields["updated_at"] = now()
        names = ", ".join(f"{k}=?" for k in fields)
        marks = ",".join("?" for _ in OPEN_STATUSES)
        self.conn.execute(f"UPDATE import_batches SET {names} WHERE id=? AND status IN ({marks})",
                          (*fields.values(), batch_id, *OPEN_STATUSES))

    def counts(self, batch_id):
        return {r["state"]: r["n"] for r in self.conn.execute(
            "SELECT state, COUNT(*) n FROM import_items WHERE batch_id=? GROUP BY state", (batch_id,))}

    # --------------------------------------------------------------- batches
    def create_batch(self, project_id, source, root_name, options):
        if source not in SOURCES:
            raise ValueError("导入来源无效")
        if not self.conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise ValueError("项目不存在")
        batch_id = uuid.uuid4().hex
        stamp = now()
        root = _segment(unicodedata.normalize("NFC", str(root_name or "")))[:MAX_NAME]
        self.conn.execute(
            "INSERT INTO import_batches(id,project_id,source,root_name,options,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (batch_id, project_id, source, root, json.dumps(clean_options(options)), "collecting", stamp, stamp))
        self.conn.commit()
        return self._batch_dict(self._batch_row(batch_id))

    def batch(self, batch_id, state=None, offset=0, limit=200):
        out = self._batch_dict(self._batch_row(batch_id))
        out["counts"] = self.counts(batch_id)
        out["copies"] = self.conn.execute("SELECT COUNT(*) FROM import_items WHERE batch_id=? AND duplicate_of IS NOT NULL", (batch_id,)).fetchone()[0]
        limit = max(0, min(int(limit), 200))
        clause, args = ("AND state=?", [state]) if state else ("", [])
        rows = self.conn.execute(
            f"SELECT * FROM import_items WHERE batch_id=? AND duplicate_of IS NULL {clause} ORDER BY id LIMIT ? OFFSET ?",
            (batch_id, *args, limit, max(0, int(offset)))).fetchall()
        out["items"] = [self._with_placements(self._item_dict(r)) for r in rows]
        return out

    def list_batches(self, project_id):
        self.purge_stale()
        return [self._batch_dict(r) | {"counts": self.counts(r["id"])} for r in self.conn.execute(
            "SELECT * FROM import_batches WHERE project_id=? AND status!='discarded' ORDER BY created_at, id",
            (project_id,))]

    def resume_index(self, batch_id):
        """[[relative path, size, modified]] of every file already in the batch, so a page that was closed can
        send only what is missing. Uncapped (a page of items holds at most 200) and small: no hints, no metadata."""
        self._batch_row(batch_id)
        return [[r["relative_path"], r["size"], r["last_modified"]] for r in self.conn.execute(
            "SELECT relative_path, size, last_modified FROM import_items WHERE batch_id=? AND kind='pdf' ORDER BY id", (batch_id,))]

    def ensure_open(self, batch_id):
        if self._batch_row(batch_id)["status"] not in OPEN_STATUSES:
            raise ValueError("导入批次已关闭")

    def discard(self, batch_id):
        row = self._batch_row(batch_id)
        if row["status"] == "committing":
            raise ValueError("批次正在提交")
        if row["status"] == "committed":
            raise ValueError("批次已提交")
        self.conn.execute("DELETE FROM import_items WHERE batch_id=?", (batch_id,))
        self._touch(batch_id, status="discarded")
        self.conn.commit()
        shutil.rmtree(self._staging(batch_id), ignore_errors=True)

    def batch_ids(self, project_id):
        return [r["id"] for r in self.conn.execute("SELECT id FROM import_batches WHERE project_id=?", (project_id,))]

    def remove_staging(self, batch_ids):
        for batch_id in batch_ids:
            shutil.rmtree(self._staging(batch_id), ignore_errors=True)

    def purge_stale(self, days=STALE_DAYS):
        """Uncommitted batches nobody came back to are not kept; committed ones stay as provenance."""
        import datetime
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).replace(microsecond=0).isoformat()
        stale = [r["id"] for r in self.conn.execute(
            "SELECT id FROM import_batches WHERE status!='committed' AND status!='committing' AND updated_at<?", (cutoff,))]
        for batch_id in stale:
            self.conn.execute("DELETE FROM import_batches WHERE id=?", (batch_id,))
            shutil.rmtree(self._staging(batch_id), ignore_errors=True)
        if stale:
            self.conn.commit()

    # ----------------------------------------------------------------- items
    def item(self, batch_id, item_id):
        row = self.conn.execute("SELECT * FROM import_items WHERE batch_id=? AND id=?", (batch_id, item_id)).fetchone()
        if not row:
            raise ValueError("导入条目不存在")
        return self._with_placements(self._item_dict(row))

    def _with_placements(self, item):
        """A primary item is placed in every folder where an identical file was found."""
        placements = [list(p) for p in item["folders"]]
        for row in self.conn.execute("SELECT folders FROM import_items WHERE duplicate_of=? ORDER BY id", (item["id"],)):
            for placement in _loads(row["folders"], [[]]):
                if placement not in placements:
                    placements.append(placement)
        item["folders"] = placements
        return item

    def _folders_of(self, segments, root, source="folder"):
        """The categories a file's folders stand for. The chosen folder itself is not one, and neither are the
        folders a reference manager invents: Zotero's export copies attachments into a files/ folder (numbered
        subfolders inside it, in the layouts seen; only for a batch that came with an export file), and its storage
        folder has one 8-character key per item. Everything else is the person's own structure."""
        directory = segments[:-1]
        if root and directory and unicodedata.normalize("NFC", directory[0]) == root:
            directory = directory[1:]
        storage = str(root or "").lower() == "storage"
        kept, i = [], 0
        while i < len(directory):
            name = directory[i]
            if name == "files" and i == 0 and source == "zotero":
                numbered = i + 1 < len(directory) and directory[i + 1].isascii() and directory[i + 1].isdigit()
                i += 2 if numbered else 1
                continue
            if storage and i == 0 and _STORAGE_KEY.fullmatch(name):
                i += 1
                continue
            kept.append(name)
            i += 1
        return [kept]

    # ---------------------------------------------------------------- upload
    def add_pdf(self, batch_id, relative_path, stream, length, last_modified=0, hints=None):
        """Stream one PDF into the batch's staging folder, hashing as it goes, and record it as pending."""
        batch = self._batch_row(batch_id)
        if batch["status"] not in OPEN_STATUSES:
            raise ValueError("导入批次已关闭")
        segments = clean_path(relative_path)
        path = "/".join(segments)
        length = int(length)
        if length <= 0 or length > MAX_FILE_BYTES:
            raise ValueError("PDF 超过 60 MB，无法导入" if length > 0 else "文件是空的")
        modified = int(last_modified or 0)
        existing = self.conn.execute("SELECT * FROM import_items WHERE batch_id=? AND relative_path=?",
                                     (batch_id, path)).fetchone()
        if existing and existing["sha256"] and existing["size"] == length and existing["last_modified"] == modified:
            return self._with_placements(self._item_dict(existing))  # the same file again: resuming an upload
        if not existing and self.conn.execute("SELECT COUNT(*) FROM import_items WHERE batch_id=? AND kind='pdf'",
                                              (batch_id,)).fetchone()[0] >= MAX_FILES:
            raise ValueError(f"一次最多导入 {MAX_FILES} 个文件，请分批导入")
        folder = self._staging(batch_id)
        folder.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(folder).free < length + DISK_RESERVE_BYTES:
            raise ValueError("磁盘空间不足")
        sha, size = self._stream(folder, stream, length)
        stamp = now()
        name = segments[-1]
        placement = json.dumps(self._folders_of(segments, batch["root_name"], batch["source"]), ensure_ascii=False)
        if existing:
            old_sha, old_id = existing["sha256"], existing["id"]
            self._release(batch_id, old_id)
            self.conn.execute(
                "UPDATE import_items SET original_name=?, size=?, last_modified=?, sha256=?, hints=?, folders=?, state='pending', "
                "match_source=NULL, paper=NULL, candidates=NULL, error=NULL, duplicate_of=NULL, paper_key=NULL, "
                "committed=0, updated_at=? WHERE id=?",
                (name, size, modified, sha, json.dumps(clean_hints(hints), ensure_ascii=False), placement, stamp, old_id))
            item_id = old_id
            if old_sha and old_sha != sha:
                self._drop_unused_file(batch_id, old_sha)
        else:
            item_id = self.conn.execute(
                "INSERT INTO import_items(batch_id,kind,relative_path,original_name,size,last_modified,sha256,hints,folders,"
                "state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (batch_id, "pdf", path, name, size, modified, sha, json.dumps(clean_hints(hints), ensure_ascii=False),
                 placement, "pending", stamp, stamp)).lastrowid
        primary = self.conn.execute(
            "SELECT id FROM import_items WHERE batch_id=? AND sha256=? AND id!=? AND duplicate_of IS NULL ORDER BY id LIMIT 1",
            (batch_id, sha, item_id)).fetchone()
        if primary:
            self.conn.execute("UPDATE import_items SET state='duplicate', duplicate_of=? WHERE id=?", (primary["id"], item_id))
        self._touch(batch_id, **({"status": "collecting"} if batch["status"] == "review" else {}))
        self.conn.commit()
        return self.item(batch_id, item_id)

    def _stream(self, folder, stream, length):
        part = folder / f"{uuid.uuid4().hex}.part"
        digest, size, head = hashlib.sha256(), 0, b""
        try:
            with part.open("wb") as handle:
                while size < length:
                    chunk = stream.read(min(CHUNK, length - size))
                    if not chunk:
                        break
                    if len(head) < 5:
                        head = (head + chunk)[:5]
                        if head[:5] != b"%PDF-"[:len(head)]:
                            raise ValueError("这不是 PDF 文件")
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise ValueError("PDF 超过 60 MB，无法导入")
                    digest.update(chunk)
                    handle.write(chunk)
            if size != length:
                raise ValueError("上传中断：收到的内容比声明的短")
            if head != b"%PDF-":
                raise ValueError("这不是 PDF 文件")
            sha = digest.hexdigest()
            target = folder / f"{sha}.pdf"
            if target.exists():
                part.unlink()
            else:
                part.replace(target)
            return sha, size
        except BaseException:
            part.unlink(missing_ok=True)
            raise

    def _release(self, batch_id, item_id):
        """The file of this item is about to change: a duplicate that rode on it becomes the primary."""
        dups = [r["id"] for r in self.conn.execute(
            "SELECT id FROM import_items WHERE duplicate_of=? ORDER BY id", (item_id,))]
        if dups:
            self.conn.execute("UPDATE import_items SET state='pending', duplicate_of=NULL WHERE id=?", (dups[0],))
            for other in dups[1:]:
                self.conn.execute("UPDATE import_items SET duplicate_of=? WHERE id=?", (dups[0], other))

    def _drop_unused_file(self, batch_id, sha):
        if not self.conn.execute("SELECT 1 FROM import_items WHERE batch_id=? AND sha256=?", (batch_id, sha)).fetchone():
            (self._staging(batch_id) / f"{sha}.pdf").unlink(missing_ok=True)

    # --------------------------------------------------------------- resolve
    @contextmanager
    def _claim(self, scope, busy, error=None):
        """A cross-process single-flight section (the shared lock's own message is about AI, so ours replaces it)."""
        guard = operation_lock.claim(self.data, scope)
        try:
            guard.__enter__()
        except ValueError:
            raise (error or ValueError)(busy) from None
        try:
            yield
        finally:
            guard.__exit__(None, None, None)

    def _single_flight(self):
        """One resolver at a time: OpenAlex is paced and metered, so two workers would only fight for it."""
        return self._claim("library-import-resolve", "已有导入正在匹配论文信息，请稍候", ResolveBusy)

    def resolve(self, batch_id, cancel=None):
        """Match every pending item to public metadata, locally first and then (if allowed) online.

        Returns 'review' when every item has an outcome, or 'paused' when it stopped early (credits used
        up, no network, cancelled): items not yet matched stay pending and a later call continues."""
        try:
            with self._single_flight():
                return self._resolve(batch_id, cancel)
        except ResolveBusy:
            # Another resolver holds OpenAlex. If this batch is not the one running, say why it is waiting.
            row = self._batch_row(batch_id)
            if row["status"] in ("collecting", "paused", "review"):
                self._pause(batch_id, "busy")
            raise

    def _resolve(self, batch_id, cancel):
        batch = self._batch_row(batch_id)
        if batch["status"] not in OPEN_STATUSES:
            raise ValueError("导入批次已关闭")
        options = clean_options(_loads(batch["options"], {}))
        self.conn.execute("UPDATE import_items SET state='pending' WHERE batch_id=? AND state='resolving'", (batch_id,))
        self._touch(batch_id, status="resolving", pause_reason=None)
        self.conn.commit()
        try:
            self._join_sidecar(batch_id, options, batch["root_name"])
            self._match_local(batch_id)
            if options["online"]:
                self._match_online(batch_id, cancel)
            self._from_entries(batch_id)
            self._finish_unmatched(batch_id)
        except _Pause as pause:
            return self._pause(batch_id, pause.reason)
        except BaseException:
            self._pause(batch_id, "error")
            raise
        self._touch_open(batch_id, status="review", pause_reason=None)
        self.conn.commit()
        return "review"

    def settle_rest(self, batch_id):
        """Stop waiting for lookups (the allowance is used up, there is no network, or the person is done waiting):
        an export entry keeps its own record and every other waiting file is kept as the plain PDF it is. Nothing is
        sent anywhere. Refused while a resolver is running."""
        with self._single_flight():
            if self._batch_row(batch_id)["status"] not in OPEN_STATUSES:
                raise ValueError("导入批次已关闭")
            self._from_entries(batch_id)
            self._finish_unmatched(batch_id)
            self._touch(batch_id, status="review", pause_reason=None)
            self.conn.commit()
        return self.counts(batch_id)

    def _pause(self, batch_id, reason):
        self.conn.execute("UPDATE import_items SET state='pending' WHERE batch_id=? AND state='resolving'", (batch_id,))
        self._touch_open(batch_id, status="paused", pause_reason=reason)
        self.conn.commit()
        return "paused"

    def _pending(self, batch_id):
        return [self._item_dict(r) for r in self.conn.execute(
            "SELECT * FROM import_items WHERE batch_id=? AND state='pending' AND duplicate_of IS NULL ORDER BY id",
            (batch_id,))]

    def _set(self, item_id, state, **fields):
        fields = {"state": state, "updated_at": now(), **fields}
        for key in ("paper", "candidates"):
            if key in fields and fields[key] is not None:
                fields[key] = json.dumps(fields[key], ensure_ascii=False)
        names = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE import_items SET {names} WHERE id=?", (*fields.values(), item_id))
        self.conn.commit()

    @staticmethod
    def _normalize_id(raw):
        """('doi', lowercase DOI URL, None) or ('arxiv', bare id, identifier for the lookup) or None."""
        try:
            identifier, arxiv_id, dedupe = parse_seed(raw)
        except ValueError:
            return None
        if arxiv_id:
            return "arxiv", arxiv_id, identifier
        if dedupe.startswith("https://doi.org/"):
            return "doi", dedupe, None
        return None

    def _plan(self, item):
        """What can identify this file: a DOI and/or arXiv id (sidecar first, then the PDF, then the file name)
        and up to a few title guesses."""
        hints, entry = item["hints"] or {}, item["entry"] or {}
        plan = {"doi": None, "arxiv": None, "arxiv_identifier": None, "origin": "pdf_id", "titles": [], "from_entry": bool(entry)}
        raws = [(entry.get("doi"), "sidecar"), (entry.get("arxiv"), "sidecar"),
                (hints.get("doi"), "pdf_id"), (hints.get("arxiv"), "pdf_id")]
        stem = Path(item.get("original_name") or "").stem if item.get("kind") == "pdf" else ""
        if _ARXIV_NAME.fullmatch(stem):
            raws.append((stem, "pdf_id"))
        for raw, origin in raws:
            found = self._normalize_id(raw) if raw else None
            if not found:
                continue
            kind, value, identifier = found
            if kind == "doi" and not plan["doi"]:
                plan["doi"], plan["origin"] = value, plan["origin"] if plan["arxiv"] else origin
            elif kind == "arxiv" and not plan["arxiv"]:
                plan["arxiv"], plan["arxiv_identifier"] = value, identifier
                plan["origin"] = plan["origin"] if plan["doi"] else origin
        titles = [t for t in [entry.get("title"), *(hints.get("titles") or [])] if isinstance(t, str) and t.strip()]
        plan["titles"] = list(dict.fromkeys(t.strip() for t in titles))
        return plan

    def _match_local(self, batch_id):
        by_title = {}
        for row in self.conn.execute("SELECT key, title FROM papers"):
            tk = title_key(row["title"])
            if len(tk) >= 8:
                by_title.setdefault(tk, row["key"])
        for item in self._pending(batch_id):
            row = self.conn.execute("SELECT paper_key FROM pdfs WHERE sha256=?", (item["sha256"],)).fetchone()
            existing = row["paper_key"] if row else None
            plan = self._plan(item)
            if not existing and plan["doi"]:
                found = self.conn.execute("SELECT key FROM papers WHERE key=? OR lower(doi)=?",
                                          (plan["doi"], plan["doi"])).fetchone()
                existing = found["key"] if found else None
            if not existing and plan["arxiv"]:
                found = self.conn.execute(
                    "SELECT key FROM papers WHERE arxiv_id=? OR arxiv_id LIKE ? OR lower(doi)=?",
                    (plan["arxiv"], "%/" + plan["arxiv"],
                     "https://doi.org/10.48550/arxiv." + plan["arxiv"])).fetchone()
                existing = found["key"] if found else None
            if existing:
                paper = self.conn.execute("SELECT key, title FROM papers WHERE key=?", (existing,)).fetchone()
                if paper:
                    self._set(item["id"], "duplicate", match_source="existing", paper_key=existing,
                              paper={"key": paper["key"], "title": paper["title"]})
                    continue
            for title in plan["titles"]:
                key = by_title.get(title_key(title))
                if key:
                    paper = self.conn.execute("SELECT key, title FROM papers WHERE key=?", (key,)).fetchone()
                    self._set(item["id"], "needs_choice", match_source="existing", candidates=[
                        {"paper": {"key": paper["key"], "title": paper["title"]}, "score": 1.0, "existing": True}])
                    break

    def _quota_low(self):
        limit = getattr(self.client, "rate_limit", lambda: None)()
        if not isinstance(limit, dict) or limit.get("remaining") is None:
            return False
        observed, reset = limit.get("observed_at"), limit.get("reset_seconds")
        if observed is not None and reset is not None and time.time() > observed + reset:
            return False  # the allowance note is older than its own reset: it says nothing about now
        return limit["remaining"] < CREDITS_PER_SEARCH

    def _checkpoint(self, cancel):
        if cancel is not None and cancel.is_set():
            raise _Pause("cancelled")
        if self._quota_low():
            raise _Pause("openalex_quota")

    @staticmethod
    def _call(function):
        try:
            return function()
        except SourceError as exc:
            if exc.kind == "unavailable":
                raise _Pause("openalex_quota") from None
            if exc.kind == "network_error":
                raise _Pause("network") from None
            if exc.kind == "not_found":
                return None
            raise _Failed(str(exc)[:200]) from None

    def _matched(self, item, work, source):
        paper = slim(work, group="imported")
        if not paper.get("key") or not paper.get("title"):
            return False
        entry = item.get("entry") or {}
        if not paper.get("abstract") and entry.get("abstract"):
            paper["abstract"] = entry["abstract"]   # the person's own export has it when OpenAlex does not
        if source == "pdf_id" and self._contradicts(item, paper):
            # An identifier read off the first pages can be a cited paper's. Nobody confirms hundreds of matches,
            # so one whose title shares nothing with the title read from the same PDF is put to the person.
            shown = max(similarity(t, paper["title"]) for t in (item.get("hints") or {}).get("titles") or [""])
            self._set(item["id"], "needs_choice", match_source=source, error=None,
                      candidates=[{"paper": paper, "score": round(shown, 3), "existing": False}])
            return True
        self._set(item["id"], "matched", match_source=source, paper=paper, error=None)
        return True

    @staticmethod
    def _contradicts(item, paper):
        titles = [t for t in ((item.get("hints") or {}).get("titles") or []) if len(_WORD.findall(t.lower())) >= MIN_COMPARE_WORDS]
        if not titles or len(_WORD.findall(str(paper.get("title") or "").lower())) < MIN_COMPARE_WORDS:
            return False
        return max(similarity(t, paper["title"]) for t in titles) < CANDIDATE_MIN

    def _match_online(self, batch_id, cancel):
        items = self._pending(batch_id)
        plans = {item["id"]: self._plan(item) for item in items}
        open_ids = {item["id"] for item in items if self._state(item["id"]) == "pending"}

        def todo(test):
            return [i for i in items if i["id"] in open_ids and test(plans[i["id"]])]

        def settle(item):
            open_ids.discard(item["id"])

        def alone(item):
            work = self._one(item, cancel, lambda i=item: self.client.work(plans[i["id"]]["doi"]), settle)
            if work and self._matched(item, work, plans[item["id"]]["origin"]):
                settle(item)
            elif item["id"] in open_ids:
                self._set(item["id"], "pending")

        # 1. DOIs, fifty per request. A DOI that could change the filter is fetched alone below.
        batched = todo(lambda p: p["doi"] and "," not in p["doi"] and "|" not in p["doi"])
        for start in range(0, len(batched), DOI_CHUNK):
            chunk = batched[start:start + DOI_CHUNK]
            self._checkpoint(cancel)
            for item in chunk:
                self._set(item["id"], "resolving")
            try:
                works = self._call(lambda: self.client.works_by_dois([plans[i["id"]]["doi"] for i in chunk])) or []
            except _Failed as failure:
                for item in chunk:
                    if len(chunk) > 1:
                        alone(item)    # the whole request was refused: ask one DOI at a time to find the one at fault
                    else:
                        self._fail(item, failure, settle)
                continue
            except _Pause:
                raise
            by_doi = {str(w.get("doi") or "").lower(): w for w in works}
            for item in chunk:
                work = by_doi.get(plans[item["id"]]["doi"])
                if work and self._matched(item, work, plans[item["id"]]["origin"]):
                    settle(item)
                else:
                    self._set(item["id"], "pending")
        for item in todo(lambda p: p["doi"] and ("," in p["doi"] or "|" in p["doi"])):
            alone(item)
        # 2. arXiv ids, one request each (fetch_seed_work falls back to the landing page for pre-2022 papers)
        for item in todo(lambda p: p["arxiv"]):
            plan = plans[item["id"]]
            work = self._one(item, cancel, lambda p=plan: fetch_seed_work(self.client, p["arxiv_identifier"], p["arxiv"]), settle)
            if work and self._matched(item, work, plan["origin"]):
                settle(item)
            elif item["id"] in open_ids:
                self._set(item["id"], "pending")
        # 3. titles read from the PDF
        for item in todo(lambda p: p["titles"] and not p["from_entry"]):   # an entry has its own record: no title search
            self._match_title(item, plans[item["id"]]["titles"][:MAX_TITLE_LOOKUPS], cancel)
            settle(item)

    def _state(self, item_id):
        return self.conn.execute("SELECT state FROM import_items WHERE id=?", (item_id,)).fetchone()["state"]

    def _one(self, item, cancel, function, settle):
        """One metered request for one item; a failed reply fails only that item."""
        self._checkpoint(cancel)
        self._set(item["id"], "resolving")
        try:
            return self._call(function)
        except _Failed as failure:
            self._fail(item, failure, settle)
            return None

    def _fail(self, item, failure, settle):
        """A lookup was refused or came back unusable. An export entry has its own record and falls back to it; anything
        else is shown as failed, with the reason, so the person can keep it as a plain PDF."""
        if item.get("entry"):
            self._set(item["id"], "pending")
            return
        self._set(item["id"], "failed", error=str(failure))
        settle(item)

    def _match_title(self, item, titles, cancel):
        candidates = {}
        for title in titles:
            self._checkpoint(cancel)
            self._set(item["id"], "resolving")
            try:
                works = self._call(lambda t=title: self.client.title_lookup(t)) or []
            except _Failed as failure:
                self._set(item["id"], "failed", error=str(failure))
                return
            for work in works:
                paper = slim(work, group="imported")
                if not paper.get("key") or not paper.get("title"):
                    continue
                score = similarity(title, paper["title"])
                if paper["key"] not in candidates or candidates[paper["key"]]["score"] < score:
                    candidates[paper["key"]] = {"paper": paper, "score": round(score, 3), "existing": False}
            ranked = sorted(candidates.values(), key=lambda c: c["score"], reverse=True)
            best = ranked[0] if ranked else None
            runner = ranked[1]["score"] if len(ranked) > 1 else 0.0
            if (best and best["score"] >= AUTO_MATCH and best["score"] - runner >= AUTO_GAP
                    and len(_WORD.findall(title.lower())) >= MIN_AUTO_WORDS):
                self._set(item["id"], "matched", match_source="title", paper=best["paper"], error=None)
                return
        ranked = sorted((c for c in candidates.values() if c["score"] >= CANDIDATE_MIN),
                        key=lambda c: c["score"], reverse=True)[:MAX_CANDIDATES]
        if ranked:
            self._set(item["id"], "needs_choice", match_source="title", candidates=ranked)
        else:
            self._set(item["id"], "pending")  # nothing usable came back: finished as an unresolved PDF below

    def _finish_unmatched(self, batch_id):
        """What nothing could identify is kept as the PDF it is, under a key made from its content."""
        for item in self._pending(batch_id):
            title = ((item["hints"] or {}).get("titles") or [None])[0] or Path(item["original_name"] or "").stem
            self._set(item["id"], "unmatched", match_source="unresolved",
                      paper={"key": "pdf:" + item["sha256"], "title": title, "unresolved": True})

    # --------------------------------------------------------------- export files
    def add_sidecar(self, batch_id, filename, data):
        """Read an export file (BibTeX, RIS, CSL-JSON) and keep its entries as rows without a file; they are joined to
        the PDFs they name when the batch is resolved. A second export replaces the entries not yet joined."""
        batch = self._batch_row(batch_id)
        if batch["status"] not in OPEN_STATUSES:
            raise ValueError("导入批次已关闭")
        name = _segment(unicodedata.normalize("NFC", str(filename or "")))[:MAX_NAME]
        fmt = reference_files.format_of(name)
        if not fmt:
            raise ValueError("不认识这种导出文件，请选择 .bib、.ris 或 .json")
        parsed = reference_files.parse(fmt, data)
        if not parsed["entries"]:
            raise ValueError("没有从导出文件里读到任何条目" + ("：" + parsed["errors"][0] if parsed["errors"] else ""))
        stamp = now()
        self.conn.execute("DELETE FROM import_items WHERE batch_id=? AND kind='entry' AND committed=0", (batch_id,))
        for entry in parsed["entries"]:
            self.conn.execute(
                "INSERT INTO import_items(batch_id,kind,original_name,entry,folders,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (batch_id, "entry", entry["title"][:MAX_NAME], json.dumps(entry, ensure_ascii=False), "[[]]", "pending", stamp, stamp))
        with_files = sum(1 for e in parsed["entries"] if e["files"])
        summary = {"filename": name, "format": fmt, "entries": len(parsed["entries"]), "with_files": with_files,
                   "errors": parsed["errors"][:5]}
        self._touch(batch_id, sidecar=json.dumps(summary, ensure_ascii=False),
                    **({"status": "collecting"} if batch["status"] == "review" else {}))
        self.conn.commit()
        return summary

    @staticmethod
    def _entry_paper(entry):
        """The paper an export entry describes, in the shape a matched paper has. Its key is its DOI, or a hash of what
        identifies it, so importing the same export twice links to the first import instead of making twins."""
        doi, title = entry.get("doi"), entry["title"]
        if doi:
            key = "https://doi.org/" + doi
        else:
            seed = "|".join((title_key(title), str(entry.get("year") or ""), (entry.get("authors") or [""])[0].lower()))
            key = "entry:" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:24]
        year = entry.get("year")
        return {"key": key, "doi": ("https://doi.org/" + doi) if doi else None, "arxiv_id": entry.get("arxiv"), "title": title,
                "abstract": entry.get("abstract"), "published": f"{year}-01-01" if year else None, "source": entry.get("venue"),
                "authors": entry.get("authors") or [], "group_name": "imported", "oa": None}

    @staticmethod
    def _match_file(file, root, by_path, by_name):
        """The uploaded PDF an export's `file` path names: by its path under the chosen folder, by the tail of its path,
        or by its file name when only one PDF has that name. Never a guess between several."""
        parts = [_segment(unicodedata.normalize("NFC", p)) for p in str(file).replace("\\", "/").split("/")]
        parts = [p for p in parts if p and p != "."]
        if not parts:
            return None
        want = "/".join(parts)
        for candidate in ((root + "/" + want) if root else None, want):
            if candidate and candidate in by_path:
                return by_path[candidate]
        same = by_name.get(parts[-1], [])
        tail = [p for p in same if p["relative_path"].endswith("/" + want)]
        if len(tail) == 1:
            return tail[0]
        return same[0] if len(same) == 1 else None

    def _join_sidecar(self, batch_id, options, root):
        """Fold each export entry into the PDF it names; entries that name none are references with no file."""
        rows = self.conn.execute("SELECT * FROM import_items WHERE batch_id=? AND kind='entry' AND committed=0 "
                                 "AND state IN ('pending','excluded') ORDER BY id", (batch_id,)).fetchall()
        if not rows:
            return
        by_path, by_name = {}, {}
        uploaded = self.conn.execute("SELECT id, relative_path, entry, duplicate_of FROM import_items WHERE batch_id=? "
                                     "AND kind='pdf' AND committed=0 ORDER BY id", (batch_id,)).fetchall()
        primaries = {r["id"]: {"id": r["id"], "entry": r["entry"]} for r in uploaded if r["duplicate_of"] is None}
        for r in uploaded:
            primary = primaries.get(r["duplicate_of"] if r["duplicate_of"] is not None else r["id"])
            if primary is None:
                continue
            # one record per file the person picked, all pointing at the primary that stands for identical content
            item = {"relative_path": r["relative_path"], "target": primary}
            by_path[r["relative_path"]] = item
            by_name.setdefault(r["relative_path"].rsplit("/", 1)[-1], []).append(item)
        for row in rows:
            item = self._item_dict(row)
            joined = False
            for file in item["entry"].get("files") or []:
                found = self._match_file(file, root, by_path, by_name)
                if found is None:
                    continue
                target = found["target"]
                if target["entry"] is None:
                    target["entry"] = json.dumps(item["entry"], ensure_ascii=False)
                    self.conn.execute("UPDATE import_items SET entry=?, updated_at=? WHERE id=?", (target["entry"], now(), target["id"]))
                joined = True
            if joined:
                self.conn.execute("DELETE FROM import_items WHERE id=?", (item["id"],))
            elif item["state"] == "pending" and not options["include_fileless"]:
                self.conn.execute("UPDATE import_items SET state='excluded', paper=?, updated_at=? WHERE id=?",
                                  (json.dumps(self._entry_paper(item["entry"]), ensure_ascii=False), now(), item["id"]))
        self.conn.commit()

    def _from_entries(self, batch_id):
        """What no lookup settled is described by the export itself."""
        for item in self._pending(batch_id):
            if item["entry"]:
                self._set(item["id"], "matched", match_source="sidecar", paper=self._entry_paper(item["entry"]), error=None)

    # ---------------------------------------------------------------- commit
    def _target(self, item):
        """(paper key, paper to insert or None) for an item that is going into the library."""
        if item["state"] == "duplicate":
            return item["paper_key"], None
        paper = dict(item["paper"] or {})
        if item["state"] == "unmatched":
            paper = {"key": "pdf:" + item["sha256"], "title": paper.get("title") or "未命名 PDF"}
        paper["group_name"] = "imported"
        paper["relation_kind"] = "imported"
        return paper["key"], paper

    def commit(self, batch_id):
        """Write the reviewed batch into the library in one transaction and return what happened.

        Only matched, unresolved-PDF and already-known items go in. Choices left open, failures and exclusions
        are counted, not written. No feedback, seed or exposure is ever written: an import says what the person
        owns, not what they like."""
        with self._claim(f"library-import-commit:{batch_id}", "这个批次正在提交，请稍候"):
            batch = self._batch_row(batch_id)
            if batch["status"] in ("committed", "discarded"):
                raise ValueError("批次已关闭")
            counts = self.counts(batch_id)
            if counts.get("pending") or counts.get("resolving"):
                raise ValueError("还有论文在匹配中，请等待完成后再提交")
            options = clean_options(_loads(batch["options"], {}))
            project = batch["project_id"]
            self._touch(batch_id, status="committing")
            self.conn.commit()
            result = {"new_papers": 0, "linked_existing": 0, "unresolved": 0, "pdfs_archived": 0, "already_in_library": 0,
                      "skipped_needs_choice": 0, "skipped_failed": 0, "excluded": 0, "extra_pdfs": 0, "extra_pdf_names": []}
            saved_before = {r[0] for r in self.conn.execute("SELECT paper_key FROM project_library WHERE project_id=?", (project,))}
            work, created, recording = [], [], {}
            try:
                for item in self._unfinished(batch_id):
                    if item["state"] == "needs_choice":
                        result["skipped_needs_choice"] += 1
                    elif item["state"] == "failed":
                        result["skipped_failed"] += 1
                    elif item["state"] == "excluded":
                        result["excluded"] += 1
                    elif item["state"] in ("matched", "unmatched", "duplicate"):
                        key, paper = self._target(item)
                        path = None
                        record = self._should_record(key, item, options)
                        if record and recording.get(key) not in (None, item["sha256"]) and not options["replace_pdf"]:
                            # A second, different file for a paper this import already gives a PDF: it must not replace
                            # the first. Nothing is lost (the original stays where it is); the result says which.
                            record = False
                            result["extra_pdfs"] += 1
                            if len(result["extra_pdf_names"]) < 20:
                                result["extra_pdf_names"].append(item["original_name"])
                        if record:
                            recording[key] = item["sha256"]
                            target = self.data / "pdfs" / f"import-{item['sha256'][:24]}.pdf"
                            existed = target.exists()
                            try:
                                path = archive_pdf(self.data, item["sha256"], self._staging(batch_id) / f"{item['sha256']}.pdf")
                            except (ValueError, OSError) as exc:
                                self._set(item["id"], "failed", error=str(exc)[:200])
                                result["skipped_failed"] += 1
                                continue
                            if not existed:
                                created.append(path)
                        work.append((item, key, paper, path))
                self.conn.execute("BEGIN IMMEDIATE")
                for item, key, paper, path in work:
                    added = self.store.upsert_papers([paper], project_id=project, commit=False) if paper else 0
                    if not paper:
                        self.store.add_project_paper(project, key, "imported", commit=False)
                    self.store.save_to_library(key, project_id=project, commit=False)
                    if path:
                        self.store.record_pdf(key, path, f"user-import:batch/{batch_id}", sha256=item["sha256"],
                                              size=item["size"], source_kind="user_import", commit=False)
                        result["pdfs_archived"] += 1
                    result["new_papers" if added else "linked_existing"] += 1
                    result["unresolved"] += item["state"] == "unmatched"
                    result["already_in_library"] += key in saved_before
                    self.conn.execute(
                        "UPDATE import_items SET committed=1, paper_key=?, updated_at=? WHERE id=? OR duplicate_of=?",
                        (key, now(), item["id"], item["id"]))
                self._touch(batch_id, status="committed", result=json.dumps(result), committed_at=now())
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                for path in created:  # files this attempt wrote; a retry writes them again
                    Path(path).unlink(missing_ok=True)
                self._touch(batch_id, status="review")
                self.conn.commit()
                raise
            shutil.rmtree(self._staging(batch_id), ignore_errors=True)
            return result

    def _unfinished(self, batch_id):
        return [self._with_placements(self._item_dict(r)) for r in self.conn.execute(
            "SELECT * FROM import_items WHERE batch_id=? AND committed=0 AND duplicate_of IS NULL ORDER BY id",
            (batch_id,))]

    def _should_record(self, key, item, options):
        """The imported file becomes the paper's current PDF only if it has none, or replacing was asked for."""
        if not item["sha256"]:
            return False
        current = self.conn.execute("SELECT sha256 FROM pdfs WHERE paper_key=?", (key,)).fetchone()
        if current is None:
            return True
        return bool(options["replace_pdf"]) and current["sha256"] != item["sha256"]

    def placements(self, batch_id):
        """Every committed paper with the folders it was found in (copies in several folders merged)."""
        merged = {}
        for row in self.conn.execute(
                "SELECT * FROM import_items WHERE batch_id=? AND committed=1 AND duplicate_of IS NULL AND paper_key IS NOT NULL ORDER BY id",
                (batch_id,)):
            item = self._with_placements(self._item_dict(row))
            slot = merged.setdefault(item["paper_key"], [])
            slot.extend(f for f in item["folders"] if f not in slot)
        return [{"key": key, "folders": folders} for key, folders in merged.items()]

    # ---------------------------------------------------------------- review
    def act(self, batch_id, item_id, action, index=None, text=None):
        """One decision of the person about one item. Nothing happens on its own; a failed lookup changes nothing."""
        if self._batch_row(batch_id)["status"] not in OPEN_STATUSES:
            raise ValueError("导入批次已关闭")
        if action not in ACTIONS:
            raise ValueError("操作无效")
        item = self.item(batch_id, item_id)
        if item["committed"]:
            raise ValueError("这条已经导入，不能再修改")
        if item["duplicate_of"] is not None:
            raise ValueError("这是同一个文件的副本，请在原条目上操作")
        if item["state"] == "resolving":
            raise ValueError("这条正在匹配中")
        if action == "exclude":
            self._set(item["id"], "excluded")
        elif action == "include":
            self._set(item["id"], self._restored_state(item))
        elif action == "unresolved":
            self._keep_as_pdf(item)
        elif action == "pick":
            self._pick(item, index)
        else:
            self._lookup(item, text)
        return self.item(batch_id, item["id"])

    @staticmethod
    def _restored_state(item):
        if item["paper_key"] and item["match_source"] == "existing":
            return "duplicate"
        if item["paper"]:
            return "unmatched" if item["paper"].get("unresolved") else "matched"
        return "needs_choice" if item["candidates"] else "pending"

    def _keep_as_pdf(self, item):
        if not item["sha256"]:
            raise ValueError("这条没有 PDF 文件")
        title = ((item["hints"] or {}).get("titles") or [None])[0] or Path(item["original_name"] or "").stem
        self._set(item["id"], "unmatched", match_source="unresolved", paper_key=None,
                  paper={"key": "pdf:" + item["sha256"], "title": title, "unresolved": True})

    def _pick(self, item, index):
        candidates = item["candidates"] or []
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(candidates):
            raise ValueError("候选不存在")
        chosen = candidates[index]
        if chosen.get("existing"):
            self._set(item["id"], "duplicate", match_source="existing", paper_key=chosen["paper"]["key"], paper=chosen["paper"])
        else:
            self._set(item["id"], "matched", match_source="user_pick", paper_key=None, paper=chosen["paper"], error=None)

    def _lookup(self, item, text):
        """A typed DOI / arXiv id is fetched; a typed name is searched and the hits are offered. The text is the
        person's own query and the only thing sent."""
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(text) < 3 or len(text) > 300:
            raise ValueError("请输入 DOI、arXiv 编号，或至少 3 个字符的论文名称")
        if self.client is None:
            raise ValueError("当前无法联网查询")
        try:
            identifier, arxiv_id, _ = parse_seed(text)
        except ValueError:
            identifier = arxiv_id = None
        try:
            if identifier:
                paper = slim(fetch_seed_work(self.client, identifier, arxiv_id), group="imported")
                if not paper.get("key") or not paper.get("title"):
                    raise ValueError("公开元数据缺少论文标题")
                self._set(item["id"], "matched", match_source="user_lookup", paper_key=None, paper=paper, error=None)
                return
            hits = {}
            for work in self.client.title_lookup(text) or []:
                paper = slim(work, group="imported")
                score = similarity(text, paper.get("title"))
                if paper.get("key") and paper.get("title") and score > 0:
                    hits.setdefault(paper["key"], {"paper": paper, "score": round(score, 3), "existing": False})
        except SourceError as exc:
            raise ValueError(LOOKUP_MESSAGES.get(exc.kind, "查询失败：" + str(exc)[:120])) from None
        if not hits:
            raise ValueError("没有找到相近的论文，可以改用 DOI 或换个关键词")
        ranked = sorted(hits.values(), key=lambda c: c["score"], reverse=True)[:MAX_CANDIDATES]
        self._set(item["id"], "needs_choice", match_source="user_lookup", paper_key=None, candidates=ranked)

    # ------------------------------------------------------------ categories
    def category_preview(self, batch_id, existing):
        """The categories this import would create or reuse, before anything is written: [{path, count}] for the
        papers that would be imported, and how many of those categories are new. `existing` is the current tree
        ([{id, name, parent_id}]). It follows the same options, depth and name limits as apply_categories."""
        from .category_review import MAX_CATEGORIES
        from .organization import IMPORT_MAX_DEPTH, IMPORT_NAME_MAX
        from .organization_terms import category_identity
        batch = self._batch_row(batch_id)
        options = clean_options(_loads(batch["options"], {}))
        counts = {}
        if options["folder_categories"]:
            root = batch["root_name"] if options["root_category"] and batch["root_name"] else None
            for item in self._unfinished(batch_id):
                if item["state"] not in ("matched", "unmatched", "duplicate"):
                    continue
                for folders in item["folders"]:
                    names = [re.sub(r"\s+", " ", n).strip()[:IMPORT_NAME_MAX].strip() for n in ([root] if root else []) + list(folders)]
                    path = tuple(n for n in names if n)[:IMPORT_MAX_DEPTH]
                    if path:
                        counts[path] = counts.get(path, 0) + 1
        tree = {(d.get("parent_id") or None, category_identity(d["name"])): d["id"] for d in existing}
        new = 0
        for path in sorted(counts, key=lambda p: (len(p), p)):
            parent = None
            for name in path:
                key = (parent, category_identity(name))
                if key not in tree:
                    new += 1
                    tree[key] = f"new{new}"
                parent = tree[key]
        total = len(existing) + new
        return {"paths": [{"path": list(path), "count": n} for path, n in sorted(counts.items())],
                "new_categories": new, "total_after": total, "over_ai_limit": total > MAX_CATEGORIES}

    def apply_categories(self, batch_id, organization):
        """Turn the folders the committed papers were found in into categories (one undo step). Safe to repeat."""
        batch = self._batch_row(batch_id)
        if batch["status"] != "committed":
            raise ValueError("批次还没有提交")
        options = clean_options(_loads(batch["options"], {}))
        none = {"created_categories": 0, "reused_categories": 0, "added_memberships": 0, "already_present": 0,
                "changed_papers": 0}
        groups = {}
        if options["folder_categories"]:
            root = batch["root_name"] if options["root_category"] and batch["root_name"] else None
            for placement in self.placements(batch_id):
                for folders in placement["folders"]:
                    path = ([root] if root else []) + list(folders)
                    if path:
                        groups.setdefault(tuple(path), []).append(placement["key"])
        result = dict(none)
        if groups:
            done = organization.action({"op": "import-categories",
                                        "groups": [{"path": list(p), "keys": k} for p, k in groups.items()]})
            result = {**done["apply_result"], "undo": done.get("undo")}
        self._touch(batch_id, categories_applied=1)
        self.conn.commit()
        return result


class ResolveBusy(ValueError):
    """Another import is being matched right now."""


class _Pause(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _Failed(Exception):
    pass
