// 知网 (CNKI) window, ADR 0045. CNKI has no public interface and sends plain HTTP clients to a puzzle a person must slide,
// so the app searches it in a window of its own: hidden, its own website data store, allowed to navigate only to
// https://kns.cnki.net. The page script in cnki_driver.js does the searching; this module holds the one running job and
// passes what the script read to the main page, which hands it to the Python server for validation and storage.
//
// Two sets of commands, each refused outside its own window:
// - the main page (same check as every other app command): cnki_start, cnki_poll, cnki_cancel;
// - the CNKI window, through a capability granted only to the window labelled "cnki" on https://kns.cnki.net/*: cnki_next
//   (the job and where the script left off) and cnki_report (items, the script's cursor, events). CNKI's own scripts run in
//   that page too and can call these two, so the page only ever gets the search words and limits (never the library's ids or
//   the project), and everything it reports is untrusted: shapes and sizes are capped here, new papers are counted and capped
//   here, and the server validates every field again (app/cnki.py).
//
// The puzzle is never solved automatically: on "verification" the window is shown for the person; after five minutes
// without a pass the job ends with verification_needed.

use std::{
    collections::HashSet,
    sync::Mutex,
    time::{Duration, Instant},
};
use serde_json::{json, Value};
use tauri::{AppHandle, Manager, State, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::{owned_page, DesktopSession, RELEASE_BUILD};

pub const LABEL: &str = "cnki";
pub const HOST: &str = "kns.cnki.net";
const SEARCH_URL: &str = "https://kns.cnki.net/kns8s/search";
const DRIVER: &str = include_str!("cnki_driver.js");

const VERIFY_WAIT: Duration = Duration::from_secs(300);      // the person has five minutes to slide the puzzle
const STALL: Duration = Duration::from_secs(120);            // no word from the page for this long: CNKI changed or hung
const RUN_LIMIT: Duration = Duration::from_secs(20 * 60);    // a refresh reads a few results pages; this is far beyond it
const LEFT_PUZZLE: Duration = Duration::from_secs(5);        // past the puzzle page with no word from the script for this long

const MAX_QUERIES: usize = 3;
const MAX_QUERY_CHARS: usize = 80;
const MAX_KNOWN: usize = 5000;
const MAX_NEW: u64 = 100;
const MAX_ITEMS_PER_REPORT: usize = 30;
const MAX_ITEM_BYTES: usize = 32 * 1024;
const MAX_CURSOR_BYTES: usize = 64 * 1024;
const MAX_BUFFERED: usize = 600;
const MAX_UPGRADES: u32 = 6;                                 // http pages on kns.cnki.net reopened over https, per minute

// Each build has its own CNKI data store (cookies, the puzzle pass), apart from the main window's: macOS 14+ by identifier,
// Windows by folder. Older macOS falls back to the app's default store (wry), which the main window also uses.
const STORE_RELEASE: [u8; 16] = *b"pagetide-cnki-01";
const STORE_DEV: [u8; 16] = *b"pagetide-cnki-dv";

#[derive(Default)]
pub struct CnkiState(Mutex<Option<Run>>);

struct Run {
    job: Value,                   // what the page script may see: mode, queries, limits, targets
    tag: Option<String>,          // the main page's label for the run (e.g. "refresh:<project>"); never shown to the page
    known: HashSet<String>,       // "<dbname>:<filename>" already in the library; never shown to the page
    seen: HashSet<String>,        // ids reported in this run
    fresh: u64,                   // new papers reported in this run (not known, not seen before)
    max_new: u64,
    cursor: Value,
    items: Vec<Value>,
    state: &'static str,          // running | verification | done | failed
    problem: Option<&'static str>,
    started: Instant,
    last_seen: Instant,
    verify_since: Option<Instant>,
    was_on_puzzle_page: bool,     // the last "verification" came from CNKI's /verify page (not an in-page slider)
    dropped: u64,
}

/// What a run's clock says should happen now. Pure, so the timing rules are unit-tested.
#[derive(Debug, PartialEq)]
enum Decision { Keep, Restart, Fail(&'static str) }

fn decide(state: &str, now: Instant, started: Instant, last_seen: Instant, verify_since: Option<Instant>,
          was_on_puzzle_page: bool, on_puzzle_page_now: bool) -> Decision {
    if state != "running" && state != "verification" {
        return Decision::Keep;
    }
    if now.duration_since(started) > RUN_LIMIT {
        return Decision::Fail("unavailable");
    }
    if state == "verification" {
        if verify_since.is_some_and(|t| now.duration_since(t) > VERIFY_WAIT) {
            return Decision::Fail("verification_needed");
        }
        // CNKI's /verify page leaves by itself once the person passes it. Only then, if the page script stays silent, the
        // shell starts the step again; an in-page slider keeps waiting for the person.
        if was_on_puzzle_page && !on_puzzle_page_now && now.duration_since(last_seen) > LEFT_PUZZLE {
            return Decision::Restart;
        }
        return Decision::Keep;
    }
    if now.duration_since(last_seen) > STALL {
        return Decision::Fail("unavailable");
    }
    Decision::Keep
}

/// A navigation the CNKI window may make: https on kns.cnki.net, or an about: frame. Anything else (another host, a
/// download, a custom scheme) is cancelled, and never handed to the system browser.
pub fn allowed_navigation(url: &Url) -> bool {
    let allowed = (url.scheme() == "https" && url.host_str() == Some(HOST) && url.port().is_none()) || url.scheme() == "about";
    if !allowed { trace(&format!("navigation refused: {}", url.as_str().chars().take(160).collect::<String>())); }
    allowed
}

/// Development builds print what the CNKI window does to stderr; release builds print nothing.
fn trace(message: &str) {
    if !RELEASE_BUILD { eprintln!("[cnki] {message}"); }
}

fn on_puzzle_page(window: &WebviewWindow) -> bool {
    window.url().map(|u| u.host_str() == Some(HOST) && u.path().starts_with("/verify")).unwrap_or(true)
}

fn cnki_page(window: &WebviewWindow) -> Result<(), String> {
    let url = window.url().map_err(|e| e.to_string())?;
    if window.label() != LABEL || url.scheme() != "https" || url.host_str() != Some(HOST) {
        return Err("CNKI command denied for this window".into());
    }
    Ok(())
}

fn text(value: Option<&Value>, limit: usize) -> Option<String> {
    let s = value?.as_str()?.trim();
    if s.is_empty() || s.chars().count() > limit || s.chars().any(|c| c.is_control()) {
        return None;
    }
    Some(s.to_string())
}

/// The job the main page asked for, rebuilt from checked fields only: (what the page script sees, tag, known ids, max new).
fn checked_job(job: &Value) -> Result<(Value, Option<String>, HashSet<String>, u64), String> {
    let job = job.as_object().ok_or("Invalid CNKI job")?;
    let mode = text(job.get("mode"), 16).ok_or("Invalid CNKI mode")?;
    if !["refresh", "guidance", "seed", "detail"].contains(&mode.as_str()) {
        return Err("Invalid CNKI mode".into());
    }
    let queries: Vec<String> = job.get("queries").and_then(Value::as_array).map(|a| a.iter()
        .filter_map(|q| text(Some(q), MAX_QUERY_CHARS)).take(MAX_QUERIES).collect()).unwrap_or_default();
    let known: HashSet<String> = job.get("known").and_then(Value::as_array).map(|a| a.iter()
        .filter_map(|k| text(Some(k), 80)).take(MAX_KNOWN).collect()).unwrap_or_default();
    let since = text(job.get("since"), 10).filter(|s| s.len() == 10 && s.chars().all(|c| c.is_ascii_digit() || c == '-'));
    let max_new = match mode.as_str() {
        "refresh" => job.get("max_new").and_then(Value::as_u64).unwrap_or(MAX_NEW).clamp(1, MAX_NEW),
        "guidance" => 10,
        "seed" => 8,
        _ => 1,
    };
    let mut targets = Vec::new();
    if mode == "detail" {
        let target = job.get("targets").and_then(Value::as_array).and_then(|a| a.first()).and_then(Value::as_object)
            .ok_or("Missing CNKI detail target")?;
        let url = text(target.get("url"), 2000).ok_or("Invalid CNKI detail link")?;
        let parsed = Url::parse(&url).map_err(|_| "Invalid CNKI detail link")?;
        if !allowed_navigation(&parsed) || parsed.scheme() != "https" {
            return Err("Invalid CNKI detail link".into());
        }
        targets.push(json!({"url": parsed.as_str(), "dbname": text(target.get("dbname"), 8), "filename": text(target.get("filename"), 64),
                            "title": text(target.get("title"), 500)}));
    } else if queries.is_empty() {
        return Err("No CNKI query".into());
    }
    let tag = text(job.get("tag"), 120);
    let page_job = json!({"mode": mode, "queries": queries, "since": since, "max_new": max_new,
                          "categories": ["JOURNAL", "DISSERTATION"], "targets": targets});
    Ok((page_job, tag, known, max_new))
}

/// Counts one reported item: true when it is a new paper (not in the library, not reported before in this run). An item
/// with no usable id is not counted (the server drops it anyway).
fn count_item(run: &mut Run, item: &Value) -> bool {
    let id = match (item.get("dbname").and_then(Value::as_str), item.get("filename").and_then(Value::as_str)) {
        (Some(db), Some(file)) if db.len() <= 8 && file.len() <= 64 => format!("{}:{}", db.to_uppercase(), file),
        _ => return false,
    };
    if !run.seen.insert(id.clone()) || run.known.contains(&id) {
        return false;
    }
    run.fresh += 1;
    true
}

fn cnki_window(app: &AppHandle) -> Result<WebviewWindow, String> {
    if let Some(window) = app.get_webview_window(LABEL) {
        return Ok(window);
    }
    let start: Url = SEARCH_URL.parse().map_err(|_| "Invalid CNKI address")?;
    let upgraded: std::sync::Arc<Mutex<Vec<Instant>>> = Default::default();
    let builder = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::External(start))
        .title("知网 / CNKI")
        .inner_size(1100.0, 800.0)
        .visible(false)
        .initialization_script(DRIVER)
        .data_store_identifier(if RELEASE_BUILD { STORE_RELEASE } else { STORE_DEV })
        .on_navigation({
            // CNKI's puzzle page sends a person who passed it to http://kns.cnki.net/...?captchaId=… (seen 2026-10-26). That
            // address completes the pass, so it is opened over https instead of being refused; an http page would get no
            // IPC (the capability is https only). At most MAX_UPGRADES such reopenings a minute, so http and https addresses
            // bouncing between each other end instead of looping. Every other address is checked as usual.
            let app = app.clone();
            move |url: &Url| {
                if url.scheme() == "http" && url.host_str() == Some(HOST) && url.port().is_none() {
                    let mut secure = url.clone();
                    let allowed = upgraded.lock().map(|mut times| {
                        let now = Instant::now();
                        times.retain(|t| now.duration_since(*t) < Duration::from_secs(60));
                        times.push(now);
                        times.len() as u32 <= MAX_UPGRADES
                    }).unwrap_or(false);
                    if allowed && secure.set_scheme("https").is_ok() {
                        trace("http page on kns.cnki.net: opening it over https");
                        let app = app.clone();
                        let _ = app.clone().run_on_main_thread(move || {
                            if let Some(cnki) = app.get_webview_window(LABEL) { let _ = cnki.navigate(secure); }
                        });
                    } else {
                        trace("http page on kns.cnki.net keeps coming back: refused");
                    }
                    return false;
                }
                allowed_navigation(url)
            }
        })
        .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny);
    #[cfg(windows)]
    let builder = {
        let base = app.path().app_local_data_dir().map_err(|e| e.to_string())?;
        builder.data_directory(base.join(if RELEASE_BUILD { "cnki-webview" } else { "cnki-webview-dev" }))
    };
    let window = builder.build().map_err(|e| e.to_string())?;
    #[cfg(target_os = "macos")]
    keep_running_when_hidden(&window);
    Ok(window)
}

/// WebKit suspends or throttles a web view that is not on screen; the hidden CNKI window then stalls between steps (seen
/// 2026-10-26: about 20 s per detail page, then no progress at all). WKPreferences.inactiveSchedulingPolicy = None (macOS 14+)
/// keeps it running. Older macOS has no such switch; the run then only goes slower, and the stall limit still ends it.
#[cfg(target_os = "macos")]
fn keep_running_when_hidden(window: &WebviewWindow) {
    let _ = window.with_webview(|webview| unsafe {
        use objc2::{msg_send, runtime::{AnyObject, Bool}, sel};
        let view = webview.inner() as *mut AnyObject;
        if view.is_null() { return; }
        let config: *mut AnyObject = msg_send![view, configuration];
        if config.is_null() { return; }
        let preferences: *mut AnyObject = msg_send![config, preferences];
        if preferences.is_null() { return; }
        let available: Bool = msg_send![preferences, respondsToSelector: sel!(setInactiveSchedulingPolicy:)];
        if available.as_bool() {
            let _: () = msg_send![preferences, setInactiveSchedulingPolicy: 2isize];      // WKInactiveSchedulingPolicyNone
            trace("inactive scheduling policy: none");
        } else {
            trace("inactive scheduling policy not available on this macOS");
        }
    });
}

fn show(window: &WebviewWindow) {
    let _ = window.show();
    let _ = window.unminimize();
    let _ = window.set_focus();
}

// One rule for the run lock: no window call (url, show, hide, navigate) is ever made while it is held. A window call from a
// thread other than the main one waits for the main thread, and the main thread may itself be waiting for this lock in
// cnki_next/cnki_report: the app would hang. Window state is read before taking the lock; window actions are done after
// releasing it (`act`).

/// Whether the CNKI window shows CNKI's puzzle page. Read without holding the run lock.
fn puzzle_now(app: &AppHandle) -> bool {
    app.get_webview_window(LABEL).map(|w| on_puzzle_page(&w)).unwrap_or(true)
}

/// Applies the run's clock (see `decide`) to the run only. On a restart it returns where the window should go.
fn apply_clock(run: &mut Run, on_puzzle: bool) -> Option<String> {
    let now = Instant::now();
    match decide(run.state, now, run.started, run.last_seen, run.verify_since, run.was_on_puzzle_page, on_puzzle) {
        Decision::Keep => None,
        Decision::Fail(problem) => { run.state = "failed"; run.problem = Some(problem); None }
        Decision::Restart => {
            trace("past the puzzle without word from the page: restarting the step");
            run.state = "running"; run.verify_since = None; run.was_on_puzzle_page = false; run.last_seen = now;
            let detail = run.cursor.get("phase").and_then(Value::as_str) == Some("detail");
            Some(run.cursor.get("queue").and_then(|q| q.get(0)).and_then(|t| t.get("url")).and_then(Value::as_str)
                .filter(|_| detail).unwrap_or(SEARCH_URL).to_string())
        }
    }
}

/// A window action decided under the lock and done after it is released.
enum After { Nothing, Hide, Show, Restart(String) }

fn act(app: &AppHandle, after: After) {
    let Some(cnki) = app.get_webview_window(LABEL) else { return };
    match after {
        After::Nothing => {}
        After::Hide => { let _ = cnki.hide(); }
        After::Show => show(&cnki),
        After::Restart(target) => {
            let _ = cnki.hide();
            if let Ok(url) = target.parse::<Url>() { if allowed_navigation(&url) { let _ = cnki.navigate(url); } }
        }
    }
}

/// Async: building a window from a synchronous command deadlocks on Windows (Tauri's documented WebView2 issue).
#[tauri::command]
pub async fn cnki_start(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, CnkiState>, app: AppHandle,
                        job: Value) -> Result<Value, String> {
    owned_page(&window, &session)?;
    let (job, tag, known, max_new) = checked_job(&job)?;
    let on_puzzle = puzzle_now(&app);
    let (after, first) = {
        let mut run = state.0.lock().map_err(|_| "CNKI state unavailable")?;
        let restart = run.as_mut().and_then(|current| apply_clock(current, on_puzzle));
        if run.as_ref().is_some_and(|r| r.state == "running" || r.state == "verification") {
            (restart.map_or(After::Nothing, After::Restart), None)
        } else {
            let detail = job["mode"] == "detail";
            let first = if detail { job["targets"][0]["url"].as_str().unwrap_or(SEARCH_URL).to_string() } else { SEARCH_URL.to_string() };
            let cursor = if detail { json!({"phase": "detail", "q": 0, "queue": job["targets"]}) }
                         else { json!({"phase": "search", "q": 0, "queue": []}) };
            let now = Instant::now();
            *run = Some(Run { job, tag, known, seen: HashSet::new(), fresh: 0, max_new, cursor, items: Vec::new(), state: "running",
                              problem: None, started: now, last_seen: now, verify_since: None, was_on_puzzle_page: false, dropped: 0 });
            (After::Nothing, Some(first))
        }
    };
    act(&app, after);
    let Some(first) = first else { return Err("CNKI is busy".into()) };
    let cnki = cnki_window(&app).map_err(|error| {
        if let Ok(mut run) = state.0.lock() {
            if let Some(run) = run.as_mut() { run.state = "failed"; run.problem = Some("unavailable"); }
        }
        error
    })?;
    let url: Url = first.parse().map_err(|_| "Invalid CNKI address")?;
    cnki.navigate(url).map_err(|e| e.to_string())?;
    Ok(json!({"started": true}))
}

/// The running job's state and the items read since the last poll. With `peek` the items stay and a finished run is kept,
/// so a page can look for a run it may pick up without taking anything from it.
#[tauri::command]
pub fn cnki_poll(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, CnkiState>, app: AppHandle,
                 peek: Option<bool>) -> Result<Value, String> {
    owned_page(&window, &session)?;
    let on_puzzle = puzzle_now(&app);
    let (reply, after) = {
        let mut guard = state.0.lock().map_err(|_| "CNKI state unavailable")?;
        let Some(run) = guard.as_mut() else { return Ok(json!({"state": "idle", "items": []})) };
        let mut after = apply_clock(run, on_puzzle).map_or(After::Nothing, After::Restart);
        if peek == Some(true) {
            (json!({"state": run.state, "tag": run.tag, "mode": run.job.get("mode"), "items": [], "pending": run.items.len()}), after)
        } else {
            let items = std::mem::take(&mut run.items);
            let reply = json!({"state": run.state, "problem": run.problem, "items": items, "dropped": run.dropped,
                               "tag": run.tag, "mode": run.job.get("mode"), "progress": {"new": run.fresh}});
            if run.state == "done" || run.state == "failed" {
                *guard = None;
                after = After::Hide;
            }
            (reply, after)
        }
    };
    act(&app, after);
    Ok(reply)
}

#[tauri::command]
pub fn cnki_cancel(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, CnkiState>, app: AppHandle)
                   -> Result<(), String> {
    owned_page(&window, &session)?;
    if let Ok(mut run) = state.0.lock() { *run = None; }
    if let Some(cnki) = app.get_webview_window(LABEL) { let _ = cnki.hide(); }
    Ok(())
}

/// The CNKI page asks what to do: the job (search words and limits only) and the cursor it left, or nothing.
#[tauri::command]
pub fn cnki_next(window: WebviewWindow, state: State<'_, CnkiState>) -> Result<Value, String> {
    cnki_page(&window)?;
    trace(&format!("next asked at {}", window.url().map(|u| u.path().to_string()).unwrap_or_default()));
    let mut guard = state.0.lock().map_err(|_| "CNKI state unavailable")?;
    match guard.as_mut() {
        Some(run) if run.state == "running" || run.state == "verification" => {
            run.last_seen = Instant::now();
            Ok(json!({"job": run.job, "cursor": run.cursor, "fresh": run.fresh}))
        }
        _ => Ok(json!({"job": null})),
    }
}

/// The CNKI page reports: items it read, its new cursor, and an event (verification, verified, done, error). The answer
/// says how many new papers the run has so far and whether the cap is reached; past the cap new papers are dropped.
#[tauri::command]
pub fn cnki_report(window: WebviewWindow, state: State<'_, CnkiState>, payload: Value) -> Result<Value, String> {
    cnki_page(&window)?;
    let payload = payload.as_object().ok_or("Invalid CNKI report")?;
    let path = window.url().map(|u| u.path().to_string()).unwrap_or_default();      // read before the lock (see `act`)
    let from_puzzle_page = on_puzzle_page(&window);
    trace(&format!("report {} at {} ({} items) {}", payload.get("event").and_then(Value::as_str).unwrap_or("-"), path,
                   payload.get("items").and_then(Value::as_array).map_or(0, |a| a.len()),
                   payload.get("message").and_then(Value::as_str).unwrap_or("").chars().take(200).collect::<String>()));
    let (reply, after) = {
        let mut guard = state.0.lock().map_err(|_| "CNKI state unavailable")?;
        let Some(run) = guard.as_mut() else { return Ok(json!({"job": null})) };
        if run.state != "running" && run.state != "verification" {
            return Ok(json!({"job": null}));
        }
        record_report(run, payload, from_puzzle_page)
    };
    act(window.app_handle(), after);
    Ok(reply)
}

/// What a report changes in the run, under the lock; the window action comes back for `act`.
fn record_report(run: &mut Run, payload: &serde_json::Map<String, Value>, from_puzzle_page: bool) -> (Value, After) {
    run.last_seen = Instant::now();
    let mut after = After::Nothing;
    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items.iter().take(MAX_ITEMS_PER_REPORT) {
            let size = serde_json::to_vec(item).map(|b| b.len()).unwrap_or(usize::MAX);
            if !item.is_object() || size > MAX_ITEM_BYTES || run.items.len() >= MAX_BUFFERED {
                run.dropped += 1;
                continue;
            }
            let full = run.fresh >= run.max_new;
            let is_new = count_item(run, item);
            if is_new && full {
                run.fresh -= 1;              // past the cap: not kept, not counted
                run.dropped += 1;
                continue;
            }
            run.items.push(item.clone());
        }
    }
    if let Some(cursor) = payload.get("cursor").filter(|c| c.is_object()) {
        if serde_json::to_vec(cursor).map(|b| b.len()).unwrap_or(usize::MAX) <= MAX_CURSOR_BYTES {
            run.cursor = cursor.clone();
        }
    }
    match payload.get("event").and_then(Value::as_str) {
        Some("verification") => {
            run.was_on_puzzle_page = from_puzzle_page;
            if run.state != "verification" {            // shown once per puzzle, so repeated reports cannot keep taking focus
                run.verify_since = Some(Instant::now());
                run.state = "verification";
                after = After::Show;
            }
        }
        Some("verified") | Some("progress") if run.state == "verification" => {
            run.state = "running"; run.verify_since = None; run.was_on_puzzle_page = false;
            after = After::Hide;
        }
        Some("done") => { run.state = "done"; }
        Some("error") => {
            run.state = "failed";
            let kind = payload.get("kind").and_then(Value::as_str).unwrap_or("unavailable");
            run.problem = Some(if kind == "network_error" { "network_error" } else { "unavailable" });
        }
        _ => {}
    }
    (json!({"ok": true, "fresh": run.fresh, "full": run.fresh >= run.max_new}), after)
}

/// Closing the CNKI window hides it; a run waiting for the puzzle then ends at its five-minute limit.
pub fn on_close_requested(window: &WebviewWindow) {
    let _ = window.hide();
}

#[cfg(test)]
mod tests {
    use super::*;

    fn at(start: Instant, secs: u64) -> Instant { start + Duration::from_secs(secs) }

    #[test]
    fn a_silent_running_page_fails_after_the_stall_limit() {
        let t = Instant::now();
        assert_eq!(decide("running", at(t, 100), t, t, None, false, false), Decision::Keep);
        assert_eq!(decide("running", at(t, 121), t, t, None, false, false), Decision::Fail("unavailable"));
    }

    #[test]
    fn an_in_page_slider_waits_for_the_person_and_never_restarts() {
        let t = Instant::now();
        // reported from a search page (not /verify): the window is not on /verify, yet nothing restarts
        assert_eq!(decide("verification", at(t, 60), t, t, Some(t), false, false), Decision::Keep);
        assert_eq!(decide("verification", at(t, 301), t, t, Some(t), false, false), Decision::Fail("verification_needed"));
    }

    #[test]
    fn leaving_the_puzzle_page_restarts_only_after_the_script_stays_silent() {
        let t = Instant::now();
        assert_eq!(decide("verification", at(t, 3), t, t, Some(t), true, false), Decision::Keep);
        assert_eq!(decide("verification", at(t, 6), t, t, Some(t), true, false), Decision::Restart);
        assert_eq!(decide("verification", at(t, 60), t, t, Some(t), true, true), Decision::Keep);     // still on /verify
    }

    #[test]
    fn every_run_ends_at_the_run_limit_even_while_waiting_for_the_puzzle() {
        let t = Instant::now();
        let late = at(t, 20 * 60 + 1);
        assert_eq!(decide("verification", late, t, late, Some(late), false, true), Decision::Fail("unavailable"));
        assert_eq!(decide("running", late, t, late, None, false, false), Decision::Fail("unavailable"));
        assert_eq!(decide("done", late, t, t, None, false, false), Decision::Keep);
    }

    #[test]
    fn the_page_never_gets_the_library_ids_or_the_tag() {
        let (page, tag, known, max_new) = checked_job(&json!({"mode": "refresh", "queries": ["世界模型", "a", "b", "c"],
            "known": ["CJFQ:X1", "CJFQ:X2"], "tag": "refresh:project-1", "max_new": 500, "since": "2026-01-01"})).unwrap();
        assert!(page.get("known").is_none() && page.get("tag").is_none());
        assert_eq!(page["queries"].as_array().unwrap().len(), 3);
        assert_eq!((tag.as_deref(), known.len(), max_new), (Some("refresh:project-1"), 2, 100));
    }

    fn run_for(mode: &str, max_new: u64) -> Run {
        let (job, tag, known, _) = checked_job(&json!({"mode": mode, "queries": ["q"], "known": ["CJFQ:K"]})).unwrap();
        let now = Instant::now();
        Run { job, tag, known, seen: HashSet::new(), fresh: 0, max_new, cursor: json!({}), items: vec![], state: "running",
              problem: None, started: now, last_seen: now, verify_since: None, was_on_puzzle_page: false, dropped: 0 }
    }

    fn report(run: &mut Run, payload: Value, from_puzzle_page: bool) -> (Value, After) {
        record_report(run, payload.as_object().unwrap(), from_puzzle_page)
    }

    #[test]
    fn the_window_is_shown_once_per_puzzle_and_hidden_after_it() {
        let mut run = run_for("refresh", 100);
        assert!(matches!(report(&mut run, json!({"event": "verification"}), true).1, After::Show));
        assert!(matches!(report(&mut run, json!({"event": "verification"}), true).1, After::Nothing));   // no second pop-up
        assert!(run.was_on_puzzle_page);
        assert!(matches!(report(&mut run, json!({"event": "progress"}), false).1, After::Hide));
        assert_eq!(run.state, "running");
    }

    #[test]
    fn past_the_cap_new_papers_are_dropped_and_known_ones_kept() {
        let mut run = run_for("refresh", 2);
        let items = json!([{"dbname": "CJFQ", "filename": "A"}, {"dbname": "CJFQ", "filename": "B"},
                           {"dbname": "CJFQ", "filename": "C"}, {"dbname": "CJFQ", "filename": "K"}]);
        let (answer, _) = report(&mut run, json!({"items": items, "event": "progress"}), false);
        assert_eq!((answer["fresh"].as_u64(), answer["full"].as_bool()), (Some(2), Some(true)));
        let kept: Vec<_> = run.items.iter().map(|i| i["filename"].as_str().unwrap().to_string()).collect();
        assert_eq!(kept, vec!["A", "B", "K"]);
        assert_eq!(run.dropped, 1);
    }

    #[test]
    fn new_papers_are_counted_once_and_known_ones_not_at_all() {
        let (job, tag, known, max_new) = checked_job(&json!({"mode": "refresh", "queries": ["q"], "known": ["CJFQ:K"]})).unwrap();
        let now = Instant::now();
        let mut run = Run { job, tag, known, seen: HashSet::new(), fresh: 0, max_new, cursor: json!({}), items: vec![],
                            state: "running", problem: None, started: now, last_seen: now, verify_since: None,
                            was_on_puzzle_page: false, dropped: 0 };
        assert!(count_item(&mut run, &json!({"dbname": "CJFQ", "filename": "A"})));
        assert!(!count_item(&mut run, &json!({"dbname": "cjfq", "filename": "A"})));     // the same paper again
        assert!(!count_item(&mut run, &json!({"dbname": "CJFQ", "filename": "K"})));     // already in the library
        assert!(!count_item(&mut run, &json!({"title": "no ids"})));
        assert_eq!(run.fresh, 1);
    }
}
