"""Opening-time upkeep: refresh the candidate pool and build today's batch.

Zero model tokens. Written to keep the no-debt rules (R-NODEBT, E-NO-DEBT, E-OFFLINE):
- at most one refresh per interval and one batch per calendar day, never a catch-up for days that were skipped;
- nothing is counted as unread or pending, and a failure is shown, bounded and does not block the batch;
- it never triggers an AI summary: the batch is only the five papers, summaries stay the user's choice.
"""
import datetime
import json
import threading
from pathlib import Path
from . import user_settings

FREQUENCIES = ("daily", "weekly", "manual")
RETRY_AFTER_SECONDS = 1800   # a failed refresh is retried at most every 30 minutes
BATCH_LIMIT = 5
LOCAL_TZ = None              # None means the machine's time zone; tests pin it
_RUNNING = set()
_LOCK = threading.Lock()


def normalize_frequency(value):
    return value if value in FREQUENCIES else "daily"


def frequency(data_dir):
    """The 更新频率 chosen on the settings page (settings.json); daily when unset or unreadable."""
    try:
        value = json.loads((Path(data_dir) / "settings.json").read_text(encoding="utf-8")).get("updateFrequency")
    except (OSError, ValueError, AttributeError):
        return "daily"
    return normalize_frequency(value)


def _now(now):
    return now or datetime.datetime.now(datetime.timezone.utc)


def _zone(now, tz=None):
    return tz or LOCAL_TZ or now.astimezone().tzinfo


def _parse(iso):
    try:
        moment = datetime.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=datetime.timezone.utc)


def refresh_due(last_iso, freq, now, tz=None):
    """daily = once per local calendar day, weekly = seven days; a bad or future timestamp counts as due."""
    if freq == "manual":
        return False
    last = _parse(last_iso)
    if last is None or last > now:
        return True
    if freq == "weekly":
        return now - last >= datetime.timedelta(days=7)
    zone = _zone(now, tz)
    return last.astimezone(zone).date() != now.astimezone(zone).date()


def _key(name, project_id):
    return f"{name}_{project_id}"


def refresh_ok(result):
    """The success rule: no errors, or at least one paper fetched despite them."""
    errors = result.get("errors") or []
    return not errors or result.get("fetched", 0) > 0


def record_success(app, project_id, result, now=None):
    """Remember a successful refresh: `last_refresh` (drives refresh_due) and, for a real fetch, its time and counts.
    A skipped refresh (it carries a reason_code, e.g. every source switched off) fetched nothing and leaves no counts."""
    now = _now(now)
    app.store.set_setting(_key("last_refresh", project_id), now.isoformat())
    app.store.set_setting(_key("last_error", project_id), "")
    if not result.get("reason_code"):
        app.store.set_setting(_key("last_refresh_result", project_id), {
            "at": now.isoformat(), "fetched": int(result.get("fetched", 0)),
            "new_to_project": int(result.get("new_to_project", 0))})


def _claim(project_id):
    with _LOCK:
        if project_id in _RUNNING:
            return False
        _RUNNING.add(project_id)
        return True


def _release(project_id):
    with _LOCK:
        _RUNNING.discard(project_id)


def manual_refresh(app, project_id=None, now=None, **options):
    """The 抓取新论文 button (and the first-launch fetch): the same refresh under the same per-project guard as the
    automatic one, so the two never run together. A successful one is recorded at its completion time like the
    automatic one (a manual fetch counts as the day's fetch); a failed one leaves the last success untouched; an
    include_distractors run is an experiment and is not recorded."""
    project_id = project_id or app.get_default_project_id()
    if not _claim(project_id):
        return {"fetched": 0, "added": 0, "new_to_project": 0, "new_recommendable": 0, "field": 0,
                "errors": [{"kind": "busy", "error": "Refresh is already running"}], "reason_code": "refresh_running"}
    try:
        result = app.refresh_candidates(project_id=project_id, **options)
        if refresh_ok(result) and not options.get("include_distractors"):
            record_success(app, project_id, result, _now(now))
        return result
    finally:
        _release(project_id)


def _recently_attempted(app, project_id, now):
    attempt = _parse(app.store.get_setting(_key("last_attempt", project_id)))
    return attempt is not None and attempt <= now and (now - attempt).total_seconds() < RETRY_AFTER_SECONDS


def _has_batch_today(app, project_id, now):
    return bool(app.store.conn.execute('SELECT 1 FROM batches WHERE project_id=? AND run_date=? LIMIT 1',
                                      (project_id,_today(now))).fetchone())


def _today(now):
    return now.astimezone(_zone(now)).date().isoformat()


def _has_unseen(app, project_id):
    from . import eligibility
    verification_budget={'remaining':eligibility.MAX_VERIFY_BYTES,'deferred':False}
    seen = {r[0] for r in app.store.conn.execute('''SELECT e.paper_key FROM exposures e
        JOIN batches b ON b.id=e.batch_id WHERE b.project_id=?''', (project_id,))}
    answered = set(app.latest_feedback(project_id)) | app.saved_keys(project_id)   # the library is not "unseen" news
    route=app._route_state(project_id,verification_budget=verification_budget)
    if route and (route['goal_status']=='needs_review' or route.get('progress_verification_deferred')):return False
    if route and route['goal_status']=='completed' and app._completed_batch(project_id,app.batch_day()):return False
    eligible=[p for p in app.recommendation_pool(project_id,verification_budget=verification_budget) if p['_eligibility']['eligible'] and p['key'] not in answered and user_settings.source_allowed(app.data,p) and str(p.get('published') or '')<=app.batch_day()]
    if route and route['goal_status']=='learning':
        from . import pathgrowth
        active={**route['graph'],'concepts':[c for c in route['graph']['concepts'] if c.get('state','active')=='active']}
        matches=pathgrowth.assign(active,eligible)
        if any(ids and ids[0] in route['frontier'] for ids in matches.values()):return True
    seeds=set(app.seed_keys(project_id))
    since=user_settings.since(app.data)
    return any(p['key'] not in seen and p['key'] not in seeds and str(p.get('published') or '')<=app.batch_day() and (not since or str(p.get('published') or '')>=since) for p in eligible)


def plan(app, project_id, now=None):
    """What would run now. Local only: no network, no model."""
    now = _now(now)
    freq = frequency(app.data)
    if freq == "manual" or app.projects.get_project(project_id)['language_policy']['status'] != 'ready':
        return {"frequency": freq, "refresh": False, "batch": False}
    refresh = (refresh_due(app.store.get_setting(_key("last_refresh", project_id)), freq, now)
               and not _recently_attempted(app, project_id, now))
    batch = not _has_batch_today(app, project_id, now) and (_has_unseen(app, project_id) or refresh)
    return {"frequency": freq, "refresh": refresh, "batch": batch}


def status(app, project_id, now=None):
    """Times and the chosen frequency only: no unread, backlog or pool counts by design."""
    return {"frequency": frequency(app.data),
            "last_refresh": app.store.get_setting(_key("last_refresh", project_id)),
            "last_attempt": app.store.get_setting(_key("last_attempt", project_id)),
            "last_error": app.store.get_setting(_key("last_error", project_id)) or None,
            "batch_today": _has_batch_today(app, project_id, _now(now)),
            "last_refresh_result": app.store.get_setting(_key("last_refresh_result", project_id)) or None}


def run(app, project_id, now=None):
    """Refresh if due, then build today's batch if there is none. Blocking; call it from a job."""
    injected = now is not None   # a test clock stays; otherwise the record carries the time the refresh finished
    now = _now(now)
    if not _claim(project_id):
        return {"skipped": "already running", "refreshed": False, "batch": False}
    try:
        wanted = plan(app, project_id, now)
        out = {"frequency": wanted["frequency"], "refreshed": False, "added": 0, "batch": False, "errors": []}
        if wanted["refresh"]:
            app.store.set_setting(_key("last_attempt", project_id), now.isoformat())
            try:
                result = app.refresh_candidates(project_id=project_id)
                errors = result.get("errors") or []
                ok = refresh_ok(result)
                detail = (errors[0].get("error") or errors[0].get("kind") or "refresh failed") if errors else ""
            except Exception as exc:  # the batch and the app must not depend on the network being up
                result, ok, errors, detail = {}, False, [], f"{type(exc).__name__}: {exc}"
            if ok:
                record_success(app, project_id, result, now if injected else _now(None))
                out.update(refreshed=True, added=result.get("added", 0), errors=errors)
            else:
                app.store.set_setting(_key("last_error", project_id), str(detail)[:200])
                out["errors"] = errors or [{"error": detail}]
        if wanted["frequency"] != "manual" and not _has_batch_today(app, project_id, now) and _has_unseen(app, project_id):
            built = app.build_batch(limit=user_settings.count(app.data), run_date=_today(now), project_id=project_id)
            out["batch"] = bool(built.get("batch_id"))
        return out
    finally:
        _release(project_id)
