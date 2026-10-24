"""The demo project of the onboarding tour: a disposable, offline, read-only-for-the-person's-data sandbox.

The demo never touches the person's database. A request that asks for it (header X-PT-Demo: 1, or project_id
"pt-demo") is answered by a DemoApp over a throw-away SQLite file under <data>/demo-sandbox/<generation>/, built with the
real code from app/demo_fixture.py. Inside it the person may generate recommendations, open the pre-written one-line
previews, save, rate and undo, and look at the library, graph, profile and weekly report; every other action answers 403
with reason_code "demo_readonly". Nothing in the sandbox is kept: a new sandbox is built each time the tour starts and
each time the process starts, and the old one is deleted when it can be (Windows may keep it until the next reset).

Zero tokens and no network: the DemoApp's gateway forwards only read-only status to the real one (no key is ever used for
a call), and its sources and PDF fetcher are stubs that raise an offline error.
"""
import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

from . import demo_fixture as fixture
from .gateway import Gateway
from .language import language
from .service import App
from .sources import SourceError
from .db import now

ASSETS = Path(__file__).resolve().parent / "static" / "demo"   # the demo reading material and the sample library file
PROJECT_ID = fixture.PROJECT_ID
HEADER = "X-PT-Demo"
SANDBOX_DIR = "demo-sandbox"
POINTER = "current"
DEMO_MODEL = "demo"     # the `model` of a pre-written preview in the summaries table

# Routes that always use the person's real data directory, with or without the demo header.
REAL_ONLY_EXACT = frozenset({"/api/settings", "/api/user_settings", "/api/ai-test", "/api/source-test", "/api/data-location",
                             "/api/export", "/api/cache", "/api/onboarding"})
REAL_ONLY_PREFIXES = ("/api/update",)
# What the demo may do. Everything else under the demo is blocked.
ALLOWED_GET = frozenset({"/api/home", "/api/state", "/api/profile", "/api/profile/insights", "/api/profile/evidence",
                         "/api/library", "/api/organization", "/api/paper", "/api/qa", "/api/qa/session", "/api/fulltext",
                         "/api/route", "/api/weekly_report", "/api/pdf/view", "/api/figure-page", "/api/import/batches"})
ALLOWED_GET_PREFIXES = ("/api/paper/", "/api/jobs/", "/api/import/batches/")
# /api/qa and /api/translate are answered by DemoApp with pre-written text (zero tokens); /api/pdf/prepare only finds the one
# demo reading material that is already in the sandbox.
ALLOWED_POST = frozenset({"/api/daily", "/api/triage", "/api/feedback", "/api/unsave", "/api/undo", "/api/detail",
                          "/api/maintain", "/api/library", "/api/pdf/prepare", "/api/fulltext", "/api/qa", "/api/qa/session",
                          "/api/translate", "/api/import/batches"})
# The import of a library file runs for real inside the sandbox (offline). Uploading PDFs and setting seeds stay blocked.
IMPORT_POST = re.compile(r"^/api/import/batches/[0-9a-f]{32}/(?:sidecar|resolve|cancel|commit|discard|settle|categories|items/\d+)$")
# POST /api/organization: only the read-only or layout operations.
ALLOWED_ORGANIZATION_OPS = frozenset({"graph", "positions", "collapse", "history", "drafts", "route-detail"})

DEMO_LOCK = threading.RLock()
_PROCESS_RESET = {"done": False}


class DemoBlocked(RuntimeError):
    """The demo tried something it must never do (a model call, a key change)."""


# ----------------------------------------------------------------------------------------------------------- routing
def requested(headers, project_id=None):
    """Does the request ask for the demo: the header, or the reserved project id."""
    return headers.get(HEADER) == "1" or project_id == PROJECT_ID


def real_only(method, route):
    if not route.startswith("/api/"):
        return True     # pages, scripts, the language pack
    if method == "GET" and route == "/api/projects":
        return True     # the real list, plus the demo's description
    return route in REAL_ONLY_EXACT or route.startswith(REAL_ONLY_PREFIXES)


def allowed(method, route, body=None):
    if method == "GET":
        return route in ALLOWED_GET or route.startswith(ALLOWED_GET_PREFIXES)
    if method == "POST":
        if route == "/api/organization":
            return isinstance(body, dict) and body.get("op", body.get("action")) in ALLOWED_ORGANIZATION_OPS
        return route in ALLOWED_POST or bool(IMPORT_POST.match(route))
    return False


def blocked_message(english):
    return ("This isn't available in the demo project. Create your own project to use it." if english
            else "演示项目里不能这样做。创建自己的项目后可用。")


def blocked_payload(english):
    return {"error": blocked_message(english), "reason_code": "demo_readonly"}


def descriptor(english):
    """The demo as /api/projects describes it: the shape of a project row plus demo=true. It matches the sandbox row."""
    return {"id": PROJECT_ID, "name": fixture.NAME["en" if english else "zh"], "creation_mode": "manual",
            "keywords": list(fixture.KEYWORDS), "decay_window_days": 30,
            "language_policy": {"discipline": None, "allowed_languages": ["en"], "revision": 1, "status": "ready"},
            "goal_confirmation": "", "demo": True}


# ------------------------------------------------------------------------------------------------ the offline DemoApp
class DemoGateway:
    """Read-only view of the real gateway (status, limits, usage). Nothing here can call a model or change a key."""

    def __init__(self, root, real_data):
        self._real = Gateway(root=root, data_dir=real_data)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._real, name)

    def _refuse(self, *args, **kwargs):
        raise DemoBlocked("The demo project makes no model calls")

    call = test_connection = save_key = clear_key = set_enabled = _refuse


class _Offline:
    """Stands in for a data source or the PDF fetcher: any use is an offline error."""
    api_key = None

    def rate_limit(self):
        return None

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def blocked(*args, **kwargs):
            raise SourceError("The demo project works offline", "network_error")
        return blocked


class DemoApp(App):
    def __init__(self, root, data_dir, real_data):
        super().__init__(root=root, data_dir=data_dir)
        self.real_data = Path(real_data)
        self.gateway = DemoGateway(root, real_data)
        self.source = _Offline()
        self.adapters = {name: _Offline() for name in self.adapters}
        self.pdf_fetcher = _Offline()

    def language(self):
        return language(self.real_data)   # the person's interface language, not the sandbox's settings

    # ---- reading: the pre-written answers (the gateway stays shut: DemoGateway.call raises) ----
    def qa(self, paper_key, question, selection=None, image=None, page_hint=None, context="normal",
           dry_run=False, project_id=None, session_id=None, reader_context=None):
        """The real route's checks, then a pre-written answer (see reading_reply). Nothing is sent anywhere."""
        if project_id and not self.store.conn.execute(
                "SELECT 1 FROM project_papers WHERE project_id=? AND paper_key=?", (project_id, paper_key)).fetchone():
            raise ValueError("论文不属于当前项目")
        from . import reader_context as reading
        session = reading.session(self.store, paper_key, project_id)
        if session_id is not None and session_id != session["id"]:
            raise ValueError("阅读会话已变化，请在新会话中重新提问")
        if reader_context is not None:
            if not isinstance(reader_context, dict):
                raise ValueError("阅读证据格式无效")
            reading.validate_evidence(self.store, paper_key, project_id, reader_context)
        answer, followups = reading_reply(selection, question, self.english())
        if paper_key:
            with self.store._lock, self.store.conn:
                self.store.conn.execute("BEGIN IMMEDIATE")
                reading.assert_session(self.store, paper_key, project_id, session)
                for role, text in (("user", question), ("assistant", answer)):
                    self.store.conn.execute("INSERT INTO qa_history(paper_key,role,content,created_at,project_id) VALUES (?,?,?,?,?)",
                                            (paper_key, role, text, now(), project_id))
        return {"ok": True, "answer": answer, "followups": followups, "mode": "text", "pages": [], "context_chars": 0,
                "demo": True, "model": DEMO_MODEL, "usage": None, "usd": 0, "usage_unknown": False,
                "usage_reserved": False, "reservation": None}

    def translate(self, text, dry_run=False):
        text = (text or "").strip()
        if not text:
            return {"ok": False, "degraded": True, "reason": "empty selection"}
        return {"ok": True, "translation": reading_translation(text, self.english()), "demo": True, "model": DEMO_MODEL,
                "usage": None, "usd": 0, "usage_unknown": False, "usage_reserved": False, "reservation": None}

    def download_pdf(self, paper_key, refresh=False):
        """Only the one demo reading material can be opened; everything else would need the network."""
        if self.conn_pdf(paper_key):
            return super().download_pdf(paper_key)
        return {"ok": False, "reason": "demo_offline", "attempts": [],
                "detail": "The demo has reading material for one paper only" if self.english() else "演示里只有一篇论文带阅读材料"}


# --------------------------------------------------------------------------------------------------- the sandbox
def sandbox_root(real_data):
    return Path(real_data) / SANDBOX_DIR


def current_generation(real_data):
    """(generation, digest) of the live sandbox, or None."""
    try:
        text = (sandbox_root(real_data) / POINTER).read_text(encoding="utf-8")
        generation, digest = text.split()[:2]
    except (OSError, ValueError):
        return None
    return (generation, digest) if (sandbox_root(real_data) / generation).is_dir() else None


def _stamp(base, days_ago):
    return (base - timedelta(days=days_ago)).replace(microsecond=0).isoformat()


def _seed(app, base):
    """Fill an empty sandbox database through the real code paths, then place every record in time."""
    english = app.english()
    lang = "en" if english else "zh"
    conn = app.store.conn
    app.projects.create_project(fixture.NAME[lang], "manual", [], language_policy={"allowed_languages": ["en"]},
                                project_id=PROJECT_ID, _demo=True)
    app.store.set_setting("project_default_terms_" + PROJECT_ID, list(fixture.KEYWORDS))
    papers = []
    for item in fixture.PAPERS:
        key = fixture.key_of(item)
        papers.append({"key": key, "doi": key, "arxiv_id": item["arxiv_id"], "title": item["title"], "abstract": item["abstract"],
                       "published": item["published"], "source": "arXiv", "work_type": "preprint", "group_name": "field",
                       "project_id": PROJECT_ID, "metadata_language": "en", "metadata_language_source": "demo fixture",
                       "oa": {"is_oa": True, "oa_status": "green", "pdf_urls": ["https://arxiv.org/pdf/" + item["arxiv_id"]],
                              "landing_page": "https://arxiv.org/abs/" + item["arxiv_id"], "license": None, "version": None}})
    app.store.upsert_papers(papers, project_id=PROJECT_ID)
    for item in fixture.PAPERS:
        preview = fixture.PREVIEWS[item["arxiv_id"]][lang]
        app.store.save_summary(fixture.key_of(item), preview["one_liner"], preview["why_relevant"], preview["caution"], DEMO_MODEL)

    # The reading material of the demo (our own text, not the paper's PDF), registered as that paper's local PDF.
    source = ASSETS / fixture.READING_FILE
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    folder = Path(app.data) / "pdfs"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (digest + ".pdf")
    target.write_bytes(data)
    app.store.record_pdf(fixture.READING_KEY, target, "demo:reading-material", sha256=digest, size=len(data), source_kind="user_import")

    # The person's earlier activity, oldest first (a familiarity mark needs the paper to be saved already).
    events = []
    for item in fixture.history():
        events.append((item["days_ago"], item["role"], item))
        for action, days in item["marks"]:
            events.append((days, action, item))
    events.sort(key=lambda event: -event[0])
    saved = {}
    for days_ago, action, item in events:
        key = fixture.key_of(item)
        conn.commit()   # record_feedback wants an idle connection
        result = app.record_feedback(key, action, project_id=PROJECT_ID)
        stamp = _stamp(base, days_ago)
        conn.execute("UPDATE feedback SET created_at=? WHERE id=?", (stamp, result["feedback_id"]))
        if action == "useful":
            saved[key] = stamp
            conn.execute("UPDATE project_library SET saved_at=? WHERE project_id=? AND paper_key=?", (stamp, PROJECT_ID, key))
            conn.execute("UPDATE library SET saved_at=? WHERE paper_key=?", (stamp, key))
        conn.commit()

    # The library's categories (the real Organization actions), then pinned terms with their history.
    from .organization import Organization
    organization = Organization(app.store, project="default")
    for direction in fixture.DIRECTIONS:
        name = direction["name"][lang]
        snapshot = organization.action({"action": "direction-save", "name": name, "color": direction["color"]})
        identifier = next(d["id"] for d in snapshot["directions"] if d["name"] == name)
        keys = [fixture.key_of(p) for p in fixture.history() if p["direction"] == direction["id"] and fixture.key_of(p) in saved]
        organization.action({"action": "membership", "keys": keys, "add": [identifier]})
    for terms, days_ago in fixture.PIN_HISTORY:
        app.pin_terms(terms, PROJECT_ID)
        conn.execute("UPDATE profile_versions SET created_at=? WHERE id=(SELECT MAX(id) FROM profile_versions)",
                     (_stamp(base, days_ago),))
    conn.commit()


def _build(root, directory, real_data):
    directory.mkdir(parents=True)
    (directory / "AI_DISABLED").write_text("The demo sandbox never calls a model\n", encoding="utf-8")
    # Old papers are the point of the demo, so the sandbox recommends from all time instead of the last 30 days.
    (directory / "settings.json").write_text(json.dumps({"timePreference": "all"}), encoding="utf-8")
    app = DemoApp(root, directory, real_data)
    try:
        _seed(app, datetime.now(timezone.utc))
    finally:
        app.store.close()


def _write_pointer(real_data, generation):
    base = sandbox_root(real_data)
    staged = base / (POINTER + "." + uuid.uuid4().hex[:8] + ".tmp")
    staged.write_text(generation + " " + fixture.DIGEST + "\n", encoding="utf-8")
    os.replace(staged, base / POINTER)


def _prune(real_data, keep):
    """Delete every sandbox generation but `keep`. Best effort: a directory that cannot be removed now (Windows keeps an
    open database file) is simply tried again at the next reset."""
    base = sandbox_root(real_data)
    try:
        entries = list(base.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name == keep or entry.name == POINTER:
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            try:
                entry.unlink()
            except OSError:
                pass


def reset(root, real_data):
    """Build a fresh sandbox, make it the current one, delete the old ones. Returns the new generation's name."""
    with DEMO_LOCK:
        base = sandbox_root(real_data)
        base.mkdir(parents=True, exist_ok=True)
        generation = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        directory = base / generation
        try:
            _build(root, directory, real_data)
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        _write_pointer(real_data, generation)
        _PROCESS_RESET["done"] = True
        _prune(real_data, generation)
        return generation


def open_app(root, real_data):
    """The DemoApp over the live sandbox. Builds one when there is none, when the fixture changed, or on this process's
    first use (so every launch starts from a clean demo)."""
    with DEMO_LOCK:
        live = current_generation(real_data)
        if not _PROCESS_RESET["done"] or live is None or live[1] != fixture.DIGEST:
            generation = reset(root, real_data)
        else:
            generation = live[0]
        return DemoApp(root, sandbox_root(real_data) / generation, real_data)


# --------------------------------------------------------------------------------------------------------- reading
_WORDS = re.compile(r"[a-z0-9]+")


def _tokens(text):
    return _WORDS.findall(str(text or "").lower())


def match_selection(selection, strict=False):
    """The pre-written entry whose sentence the selected text is (a part of), or None. Words are compared, not layout, so a
    selection that crosses PDF lines still matches. A selection of fewer than four words never does. `strict` (translation)
    wants almost the whole sentence."""
    chosen = _tokens(selection)
    if len(chosen) < (4 if not strict else 6):
        return None
    best, best_size = None, 0
    for entry in fixture.READING_QA:
        words = _tokens(entry["sentence"])
        found = SequenceMatcher(None, chosen, words, autojunk=False).find_longest_match(0, len(chosen), 0, len(words))
        if strict:
            ok = found.size >= 0.9 * len(words) and found.size >= 0.9 * len(chosen)
        else:
            ok = found.size >= 4 and (found.size >= 0.6 * len(chosen) or found.size >= 0.8 * len(words))
        if ok and found.size > best_size:
            best, best_size = entry, found.size
    return best


def _by_question(question):
    wanted = " ".join(str(question or "").split())
    for entry in fixture.READING_QA:
        if wanted in (entry["question"]["zh"], entry["question"]["en"]):
            return entry
    return None


def _followups(ids, lang):
    by_id = {entry["id"]: entry for entry in fixture.READING_QA}
    return [by_id[i]["question"][lang] for i in ids if i in by_id]


def reading_reply(selection, question, english):
    """(answer, follow-up questions) for a question about the demo reading material. The question decides when it is one of
    the pre-written follow-ups; otherwise the selected text does; anything else gets the one general demo reply."""
    lang = "en" if english else "zh"
    entry = _by_question(question) or (match_selection(selection) if selection else None)
    if entry:
        return entry["answer"][lang], _followups(entry["followups"], lang)
    return fixture.READING_GENERIC["answer"][lang], _followups(fixture.READING_GENERIC["followups"], lang)


def reading_translation(text, english):
    entry = match_selection(text, strict=True)
    return entry["translation"] if entry else fixture.READING_GENERIC["translation"]["en" if english else "zh"]


# --------------------------------------------------------------------------------------------------------- import
def import_options(options):
    """The demo imports offline and takes records that have no PDF: the sample is an export file without files."""
    return {**(options if isinstance(options, dict) else {}), "online": False, "include_fileless": True}


# --------------------------------------------------------------------------------------------------------- triage
def triage(app, keys=None):
    """The demo's 'AI preview': the pre-written previews of the cards on the page, written into the sandbox's summaries
    (model="demo"). No model is called and nothing is billed. Same item shape as the real triage."""
    cards = app.cards(project_id=PROJECT_ID)
    if keys is not None:
        if not isinstance(keys, list) or not keys or any(not isinstance(k, str) for k in keys):
            raise ValueError("请选择 1 到 5 篇论文" if not app.english() else "Choose 1 to 5 papers")
        wanted = set(keys)
        if not wanted <= {card["key"] for card in cards}:
            raise ValueError("这些论文不在当前推荐里" if not app.english() else "Those papers are not in today's picks")
        cards = [card for card in cards if card["key"] in wanted]
    lang = "en" if app.english() else "zh"
    by_key = {fixture.key_of(p): fixture.PREVIEWS[p["arxiv_id"]][lang] for p in fixture.PAPERS}
    items = []
    for card in cards:
        preview = by_key.get(card["key"])
        if preview is None:
            continue
        app.store.save_summary(card["key"], preview["one_liner"], preview["why_relevant"], preview["caution"], DEMO_MODEL)
        items.append({"paper_id": card["key"], **preview})
    return {"ok": True, "items": items, "mode": "demo", "demo": True, "usage": None, "usd": 0, "usage_unknown": False,
            "usage_reserved": False, "reservation": None}
