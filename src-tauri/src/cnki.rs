// 知网 (CNKI) window, ADR 0045. CNKI has no public interface and sends plain HTTP clients to a puzzle a person must slide,
// so the app searches it in a window of its own: hidden, its own website data store, allowed to navigate only to
// https://kns.cnki.net. The page script in cnki_driver.js does the searching; this module holds the one running job and
// passes what the script read to the main page, which hands it to the Python server for validation and storage.
//
// Two sets of commands, each refused outside its own window:
// - the main page (same check as every other app command): cnki_start, cnki_poll, cnki_cancel;
// - the CNKI window, through a capability granted only to the window labelled "cnki" on https://kns.cnki.net/*: cnki_next
//   (the job and where the script left off) and cnki_report (items, the script's cursor, events). CNKI's own scripts run in
//   that page too and can call these two, so everything they carry is untrusted: shapes and sizes are capped here, and the
//   server validates every field again (app/cnki.py).
//
// The puzzle is never solved automatically: on "verification" the window is shown for the person; after five minutes
// without a pass the job ends with verification_needed.

use std::{
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
const RUN_LIMIT: Duration = Duration::from_secs(45 * 60);    // a hundred detail pages take about 12 minutes

const MAX_QUERIES: usize = 3;
const MAX_QUERY_CHARS: usize = 80;
const MAX_KNOWN: usize = 5000;
const MAX_NEW: u64 = 100;
const MAX_ITEMS_PER_REPORT: usize = 30;
const MAX_ITEM_BYTES: usize = 32 * 1024;
const MAX_CURSOR_BYTES: usize = 256 * 1024;
const MAX_BUFFERED: usize = 600;

// Each build has its own CNKI data store (cookies, the puzzle pass), apart from the main window's: macOS 14+ by identifier,
// Windows by folder. Older macOS falls back to the app's default store (wry), which the main window also uses.
const STORE_RELEASE: [u8; 16] = *b"pagetide-cnki-01";
const STORE_DEV: [u8; 16] = *b"pagetide-cnki-dv";

#[derive(Default)]
pub struct CnkiState(Mutex<Option<Run>>);

struct Run {
    job: Value,
    cursor: Value,
    items: Vec<Value>,
    state: &'static str,          // running | verification | done | failed
    problem: Option<&'static str>,
    started: Instant,
    last_seen: Instant,
    verify_since: Option<Instant>,
    dropped: u64,
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

fn on_verify_page(window: &WebviewWindow) -> bool {
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

/// The job the main page asked for, rebuilt from checked fields only.
fn checked_job(job: &Value) -> Result<Value, String> {
    let job = job.as_object().ok_or("Invalid CNKI job")?;
    let mode = text(job.get("mode"), 16).ok_or("Invalid CNKI mode")?;
    if !["refresh", "guidance", "seed", "detail"].contains(&mode.as_str()) {
        return Err("Invalid CNKI mode".into());
    }
    let queries: Vec<String> = job.get("queries").and_then(Value::as_array).map(|a| a.iter()
        .filter_map(|q| text(Some(q), MAX_QUERY_CHARS)).take(MAX_QUERIES).collect()).unwrap_or_default();
    let known: Vec<String> = job.get("known").and_then(Value::as_array).map(|a| a.iter()
        .filter_map(|k| text(Some(k), 80)).take(MAX_KNOWN).collect()).unwrap_or_default();
    let since = text(job.get("since"), 10).filter(|s| s.len() == 10 && s.chars().all(|c| c.is_ascii_digit() || c == '-'));
    let limit = |name: &str, default: u64, max: u64| job.get(name).and_then(Value::as_u64).unwrap_or(default).clamp(1, max);
    let (max_new, per_query) = match mode.as_str() {
        "refresh" => (limit("max_new", MAX_NEW, MAX_NEW), MAX_NEW),
        "guidance" => (10, 10),
        "seed" => (8, 8),
        _ => (1, 1),
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
    // An opaque label the page chooses (e.g. "refresh:<project>"), echoed by cnki_poll so a reloaded page can pick the run up.
    let tag = text(job.get("tag"), 120);
    Ok(json!({"mode": mode, "queries": queries, "known": known, "since": since, "max_new": max_new, "per_query": per_query,
              "categories": ["JOURNAL", "DISSERTATION"], "targets": targets, "tag": tag}))
}

fn window(app: &AppHandle) -> Result<WebviewWindow, String> {
    if let Some(window) = app.get_webview_window(LABEL) {
        return Ok(window);
    }
    let start: Url = SEARCH_URL.parse().map_err(|_| "Invalid CNKI address")?;
    let builder = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::External(start))
        .title("知网 / CNKI")
        .inner_size(1100.0, 800.0)
        .visible(false)
        .initialization_script(DRIVER)
        .data_store_identifier(if RELEASE_BUILD { STORE_RELEASE } else { STORE_DEV })
        .on_navigation({
            // CNKI's puzzle page sends a person who passed it to http://kns.cnki.net/...?captchaId=… (seen 2026-10-26). That
            // address completes the pass, so it is opened over https instead of being refused; an http page would get no
            // IPC (the capability is https only). Every other address is checked as usual.
            let app = app.clone();
            move |url: &Url| {
                if url.scheme() == "http" && url.host_str() == Some(HOST) && url.port().is_none() {
                    let mut secure = url.clone();
                    if secure.set_scheme("https").is_ok() {
                        trace("http page on kns.cnki.net: opening it over https");
                        let app = app.clone();
                        let _ = app.clone().run_on_main_thread(move || {
                            if let Some(cnki) = app.get_webview_window(LABEL) { let _ = cnki.navigate(secure); }
                        });
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

#[tauri::command]
pub fn cnki_start(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, CnkiState>, app: AppHandle,
                  job: Value) -> Result<Value, String> {
    owned_page(&window, &session)?;
    let job = checked_job(&job)?;
    let mut run = state.0.lock().map_err(|_| "CNKI state unavailable")?;
    if run.as_ref().is_some_and(|r| r.state == "running" || r.state == "verification") {
        return Err("CNKI is busy".into());
    }
    let detail = job["mode"] == "detail";
    let cursor = if detail { json!({"phase": "detail", "q": 0, "queue": job["targets"], "new": 0}) }
                 else { json!({"phase": "search", "q": 0, "cat": 0, "queue": [], "new": 0}) };
    let first = if detail { job["targets"][0]["url"].as_str().unwrap_or(SEARCH_URL).to_string() } else { SEARCH_URL.to_string() };
    let now = Instant::now();
    *run = Some(Run { job, cursor, items: Vec::new(), state: "running", problem: None, started: now, last_seen: now,
                      verify_since: None, dropped: 0 });
    drop(run);
    let cnki = window_or_fail(&app, &state)?;
    let url: Url = first.parse().map_err(|_| "Invalid CNKI address")?;
    cnki.navigate(url).map_err(|e| e.to_string())?;
    Ok(json!({"started": true}))
}

fn window_or_fail(app: &AppHandle, state: &State<'_, CnkiState>) -> Result<WebviewWindow, String> {
    window(app).map_err(|error| {
        if let Ok(mut run) = state.0.lock() {
            if let Some(run) = run.as_mut() { run.state = "failed"; run.problem = Some("unavailable"); }
        }
        error
    })
}

/// The running job's state and the items read since the last poll. With `peek` the items stay and a finished run is kept,
/// so a page can look for a run it may pick up without taking anything from it.
#[tauri::command]
pub fn cnki_poll(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, CnkiState>, app: AppHandle,
                 peek: Option<bool>) -> Result<Value, String> {
    owned_page(&window, &session)?;
    let mut guard = state.0.lock().map_err(|_| "CNKI state unavailable")?;
    let Some(run) = guard.as_mut() else { return Ok(json!({"state": "idle", "items": []})) };
    if peek == Some(true) {
        return Ok(json!({"state": run.state, "tag": run.job.get("tag"), "mode": run.job.get("mode"), "items": [],
                         "pending": run.items.len()}));
    }
    let now = Instant::now();
    // The puzzle page leaves by itself once the person passes it. If the window is past it but the page script has not
    // spoken for a few seconds, start the current step again from here.
    if run.state == "verification" && now - run.last_seen > Duration::from_secs(5) {
        if let Some(cnki) = app.get_webview_window(LABEL) {
            if !on_verify_page(&cnki) {
                trace("past the puzzle without word from the page: restarting the step");
                run.state = "running"; run.verify_since = None; run.last_seen = now;
                let detail = run.cursor.get("phase").and_then(Value::as_str) == Some("detail");
                let target = run.cursor.get("queue").and_then(|q| q.get(0)).and_then(|t| t.get("url")).and_then(Value::as_str)
                    .filter(|_| detail).unwrap_or(SEARCH_URL).to_string();
                let _ = cnki.hide();
                if let Ok(url) = target.parse::<Url>() { if allowed_navigation(&url) { let _ = cnki.navigate(url); } }
            }
        }
    }
    if run.state == "verification" && run.verify_since.is_some_and(|t| now - t > VERIFY_WAIT) {
        run.state = "failed"; run.problem = Some("verification_needed");
    } else if run.state == "running" && (now - run.last_seen > STALL || now - run.started > RUN_LIMIT) {
        run.state = "failed"; run.problem = Some("unavailable");
    }
    let items = std::mem::take(&mut run.items);
    let reply = json!({"state": run.state, "problem": run.problem, "items": items, "dropped": run.dropped,
                       "tag": run.job.get("tag"), "mode": run.job.get("mode"),
                       "progress": {"q": run.cursor.get("q"), "phase": run.cursor.get("phase"), "new": run.cursor.get("new")}});
    if run.state == "done" || run.state == "failed" {
        *guard = None;
        if let Some(cnki) = app.get_webview_window(LABEL) { let _ = cnki.hide(); }
    }
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

/// The CNKI page asks what to do: the job and the cursor it left, or nothing when no job runs.
#[tauri::command]
pub fn cnki_next(window: WebviewWindow, state: State<'_, CnkiState>) -> Result<Value, String> {
    cnki_page(&window)?;
    let mut guard = state.0.lock().map_err(|_| "CNKI state unavailable")?;
    match guard.as_mut() {
        Some(run) if run.state == "running" || run.state == "verification" => {
            run.last_seen = Instant::now();
            trace(&format!("next asked at {}", window.url().map(|u| u.path().to_string()).unwrap_or_default()));
            Ok(json!({"job": run.job, "cursor": run.cursor}))
        }
        _ => Ok(json!({"job": null})),
    }
}

/// The CNKI page reports: items it read, its new cursor, and an event (verification, verified, done, error).
#[tauri::command]
pub fn cnki_report(window: WebviewWindow, state: State<'_, CnkiState>, payload: Value) -> Result<Value, String> {
    cnki_page(&window)?;
    let payload = payload.as_object().ok_or("Invalid CNKI report")?;
    let mut guard = state.0.lock().map_err(|_| "CNKI state unavailable")?;
    let Some(run) = guard.as_mut() else { return Ok(json!({"job": null})) };
    if run.state != "running" && run.state != "verification" {
        return Ok(json!({"job": null}));
    }
    run.last_seen = Instant::now();
    trace(&format!("report {} at {} ({} items) {}", payload.get("event").and_then(Value::as_str).unwrap_or("-"),
                   window.url().map(|u| u.path().to_string()).unwrap_or_default(),
                   payload.get("items").and_then(Value::as_array).map_or(0, |a| a.len()),
                   payload.get("message").and_then(Value::as_str).unwrap_or("").chars().take(200).collect::<String>()));
    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items.iter().take(MAX_ITEMS_PER_REPORT) {
            let size = serde_json::to_vec(item).map(|b| b.len()).unwrap_or(usize::MAX);
            if item.is_object() && size <= MAX_ITEM_BYTES && run.items.len() < MAX_BUFFERED {
                run.items.push(item.clone());
            } else {
                run.dropped += 1;
            }
        }
    }
    if let Some(cursor) = payload.get("cursor").filter(|c| c.is_object()) {
        if serde_json::to_vec(cursor).map(|b| b.len()).unwrap_or(usize::MAX) <= MAX_CURSOR_BYTES {
            run.cursor = cursor.clone();
        }
    }
    match payload.get("event").and_then(Value::as_str) {
        Some("verification") => {
            if run.state != "verification" { run.verify_since = Some(Instant::now()); }
            run.state = "verification";
            show(&window);
        }
        Some("verified") | Some("progress") if run.state == "verification" => {
            run.state = "running"; run.verify_since = None;
            let _ = window.hide();
        }
        Some("done") => { run.state = "done"; }
        Some("error") => {
            run.state = "failed";
            let kind = payload.get("kind").and_then(Value::as_str).unwrap_or("unavailable");
            run.problem = Some(if kind == "network_error" { "network_error" } else { "unavailable" });
        }
        _ => {}
    }
    Ok(json!({"ok": true}))
}

/// Closing the CNKI window hides it; a run waiting for the puzzle then ends at its five-minute limit.
pub fn on_close_requested(window: &WebviewWindow) {
    let _ = window.hide();
}
