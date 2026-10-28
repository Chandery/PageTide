"""PDF annotations made in the reader: highlights with an optional note, like Zotero's.

An annotation belongs to one PDF file version (paper key + the file's SHA-256), because its boxes are positions on that
file's pages. Boxes are stored as fractions of the page (0..1), so they survive any zoom. A newer file version of the same
paper does not show the old version's annotations, and they are kept, never rewritten. The text is the person's own:
nothing here is sent to a model. The table is created on first use (no numbered migration: see migrations-shared-real-db).

A note can @ other notes of the same file version, inside its own text: the text holds `@[<annotation id>]` where the reader
shows "@3" (the note's number in reading order, so numbers can change while the references stay right). `mentions` is the
list of ids found in the text, kept for drawing the arrows; it is always derived from the text. Deleting a note turns the
references to it in other notes into "@✕" and drops it from their lists.
"""
import json
import re
import uuid
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS annotations (
  id TEXT PRIMARY KEY,
  paper_key TEXT NOT NULL,
  pdf_sha256 TEXT NOT NULL,
  page INTEGER NOT NULL,
  rects TEXT NOT NULL,
  quote TEXT NOT NULL DEFAULT '',
  comment TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_annotations_pdf ON annotations(paper_key, pdf_sha256, page);
"""

COLORS = ("yellow", "red", "green", "blue", "purple")
MAX_RECTS = 400
MAX_QUOTE = 5000
MAX_COMMENT = 20000
MAX_PAGE = 100000
MAX_MENTIONS = 30
_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[0-9a-f]{32}")
_MENTION = re.compile(r"@\[([0-9a-f]{32})\]")
GONE = "@✕"


def _now():
    return datetime.now(timezone.utc).isoformat()


def ensure(store):
    with store._lock:
        store.conn.executescript(SCHEMA)
        columns = {row["name"] for row in store.conn.execute("PRAGMA table_info(annotations)")}
        if "mentions" not in columns:   # added later than the table: a lazily added column, like the table itself
            store.conn.execute("ALTER TABLE annotations ADD COLUMN mentions TEXT NOT NULL DEFAULT '[]'")
            store.conn.commit()


def _row(row):
    return {"id": row["id"], "page": row["page"], "rects": json.loads(row["rects"]), "quote": row["quote"],
            "comment": row["comment"], "color": row["color"], "mentions": _ids(row["mentions"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


def _ids(raw):
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return [i for i in value if isinstance(i, str)] if isinstance(value, list) else []


def _current_sha(store, key):
    row = store.conn.execute("SELECT sha256 FROM pdfs WHERE paper_key=?", (key,)).fetchone()
    return row["sha256"] if row else None


def _rects(raw):
    if not isinstance(raw, list) or not raw or len(raw) > MAX_RECTS:
        raise ValueError("高亮位置无效")
    out = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("高亮位置无效")
        page = item.get("p")
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= MAX_PAGE:
            raise ValueError("高亮位置无效")
        box = []
        for name in ("x0", "y0", "x1", "y1"):
            value = item.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError("高亮位置无效")
            box.append(round(float(value), 5))
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("高亮位置无效")
        out.append({"p": page, "x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3]})
    return out


def _text(value, limit, label):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label}格式无效")
    if len(value) > limit:
        raise ValueError(f"{label}太长")
    return value


def _color(value):
    if value is None:
        return COLORS[0]
    if value not in COLORS:
        raise ValueError("颜色无效")
    return value


def list_for(store, key, sha256):
    if not isinstance(key, str) or not isinstance(sha256, str) or not _SHA.fullmatch(sha256):
        raise ValueError("缺少论文或 PDF 版本")
    ensure(store)
    rows = store.conn.execute("SELECT * FROM annotations WHERE paper_key=? AND pdf_sha256=? ORDER BY page, created_at",
                              (key, sha256)).fetchall()
    return [_row(row) for row in rows]


def create(store, key, sha256, rects, quote="", comment="", color=None):
    if not isinstance(key, str) or not store.paper(key):
        raise ValueError("论文不存在")
    if not isinstance(sha256, str) or not _SHA.fullmatch(sha256):
        raise ValueError("缺少 PDF 版本")
    boxes = _rects(rects)
    quote, comment, color = _text(quote, MAX_QUOTE, "原文"), _text(comment, MAX_COMMENT, "笔记"), _color(color)
    ensure(store)
    row_id, now = uuid.uuid4().hex, _now()
    with store._lock, store.conn:
        if _current_sha(store, key) != sha256:
            raise ValueError("PDF 版本已变化，请重新打开论文")
        store.conn.execute("INSERT INTO annotations (id, paper_key, pdf_sha256, page, rects, quote, comment, color, created_at, updated_at)"
                           " VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (row_id, key, sha256, min(b["p"] for b in boxes), json.dumps(boxes), quote, comment, color, now, now))
    return _row(store.conn.execute("SELECT * FROM annotations WHERE id=?", (row_id,)).fetchone())


def _find(store, annotation_id):
    if not isinstance(annotation_id, str) or not _ID.fullmatch(annotation_id):
        raise ValueError("笔记不存在")
    ensure(store)
    row = store.conn.execute("SELECT * FROM annotations WHERE id=?", (annotation_id,)).fetchone()
    if not row:
        raise ValueError("笔记不存在")
    return row


def _mentioned(store, comment, row):
    """The notes a text @s: ids written as @[id] that are other notes of the same paper and file version, once each."""
    out = []
    for item in _MENTION.findall(comment):
        if item == row["id"] or item in out or len(out) >= MAX_MENTIONS:
            continue
        if store.conn.execute("SELECT 1 FROM annotations WHERE id=? AND paper_key=? AND pdf_sha256=?",
                              (item, row["paper_key"], row["pdf_sha256"])).fetchone():
            out.append(item)
    return out


def update(store, annotation_id, comment=None, color=None):
    row = _find(store, annotation_id)
    comment = row["comment"] if comment is None else _text(comment, MAX_COMMENT, "笔记")
    color = row["color"] if color is None else _color(color)
    mentioned = _ids(row["mentions"]) if comment == row["comment"] else _mentioned(store, comment, row)
    with store._lock, store.conn:
        store.conn.execute("UPDATE annotations SET comment=?, color=?, mentions=?, updated_at=? WHERE id=?",
                           (comment, color, json.dumps(mentioned), _now(), annotation_id))
    return _row(store.conn.execute("SELECT * FROM annotations WHERE id=?", (annotation_id,)).fetchone())


def delete(store, annotation_id):
    row = _find(store, annotation_id)
    with store._lock, store.conn:
        for other in store.conn.execute("SELECT id, comment, mentions FROM annotations WHERE paper_key=? AND pdf_sha256=? AND comment LIKE ?",
                                        (row["paper_key"], row["pdf_sha256"], f"%@[{annotation_id}]%")).fetchall():
            kept = [i for i in _ids(other["mentions"]) if i != annotation_id]
            store.conn.execute("UPDATE annotations SET comment=?, mentions=? WHERE id=?",
                               (other["comment"].replace(f"@[{annotation_id}]", GONE), json.dumps(kept), other["id"]))
        store.conn.execute("DELETE FROM annotations WHERE id=?", (annotation_id,))
    return {"id": annotation_id, "deleted": True}
