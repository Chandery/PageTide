// "Download in the app" (ADR 0047): some publishers refuse PDFs to programs (a bot check, robots.txt) but give them to a
// browser, and the person can download them there. This window is that browser: visible, opened only when the person
// clicks the button on the reader's failure screen, at the paper's own link. When the window shows a PDF, the page
// script in pdf_window.js reads it with the window's own session (as the person's browser would) and hands it over in
// chunks; a PDF the site offers as a download is caught as well (Windows' PDF viewer runs no page script, its save
// button downloads). The main page then takes the bytes and attaches them like a dropped file: the server validates the
// PDF and keeps it in the library.
//
// Commands, each refused outside its own window:
// - the main page (same check as every other app command): pdf_window_open, pdf_window_poll, pdf_window_take,
//   pdf_window_cancel;
// - the download window, through a capability granted only to the window labelled "pdfdl" on https pages: pdf_window_chunk.
//   Any page shown in that window can call it, so it only ever adds bytes to the one open job, capped in size, and the
//   result must start like a PDF; the server checks the whole file again. Nothing in the window can read the app's data.
//
// The window never solves a verification for the person, never runs in the background and goes only to https addresses
// on public hosts.

use std::{
    path::PathBuf,
    sync::Mutex,
    time::{Duration, Instant},
};
use serde_json::{json, Value};
use tauri::{ipc::Response, AppHandle, Manager, State, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::{owned_page, DesktopSession, RELEASE_BUILD};

pub const LABEL: &str = "pdfdl";
const SCRIPT: &str = include_str!("pdf_window.js");
const MAX_BYTES: usize = 60 * 1024 * 1024;             // the server's PDF limit
const MAX_CHUNK_CHARS: usize = 2 * 1024 * 1024;        // base64 per chunk (the page sends 1 MB of bytes at a time)
const OPEN_LIMIT: Duration = Duration::from_secs(30 * 60);
const STORE_RELEASE: [u8; 16] = *b"pagetide-pdfw-01";
const STORE_DEV: [u8; 16] = *b"pagetide-pdfw-dv";

#[derive(Default)]
pub struct PdfWindowState(Mutex<Option<Job>>);

pub struct Job {
    key: String,
    state: &'static str,              // open, received, closed, failed
    bytes: Vec<u8>,
    expected: usize,                  // total announced by the page for the current transfer
    started: Instant,
    download_to: Option<PathBuf>,     // where a caught download is written (macOS reports no path when it finishes)
    from: Option<String>,             // the host the PDF came from, for the page to show
}

fn trace(message: &str) {
    if !RELEASE_BUILD { eprintln!("[pdf-window] {message}"); }
}

/// https on a public host (no loopback, private or local names), or an about: frame. Everything else is refused.
pub fn allowed_navigation(url: &Url) -> bool {
    if url.scheme() == "about" { return true; }
    if url.scheme() != "https" { return false; }
    let Some(host) = url.host_str() else { return false };
    let host = host.trim_start_matches('[').trim_end_matches(']').trim_end_matches('.').to_ascii_lowercase();
    if let Ok(ip) = host.parse::<std::net::IpAddr>() {
        return match ip {
            std::net::IpAddr::V4(ip) => !(ip.is_loopback() || ip.is_private() || ip.is_link_local() || ip.is_unspecified()),
            std::net::IpAddr::V6(ip) => !(ip.is_loopback() || ip.is_unspecified() || (ip.segments()[0] & 0xfe00) == 0xfc00
                                          || (ip.segments()[0] & 0xffc0) == 0xfe80),
        };
    }
    host.contains('.') && host != "localhost" && !host.ends_with(".local") && !host.ends_with(".localhost")
        && !host.ends_with(".internal")
}

/// Standard base64 (the page's btoa); None for anything else.
fn decode_base64(text: &str) -> Option<Vec<u8>> {
    let value = |c: u8| -> Option<u32> {
        Some(match c { b'A'..=b'Z' => c - b'A', b'a'..=b'z' => c - b'a' + 26, b'0'..=b'9' => c - b'0' + 52, b'+' => 62, b'/' => 63,
                       _ => return None } as u32)
    };
    let bytes = text.as_bytes();
    if bytes.len() % 4 != 0 { return None; }
    let mut out = Vec::with_capacity(bytes.len() / 4 * 3);
    for (i, quad) in bytes.chunks(4).enumerate() {
        let last = i == bytes.len() / 4 - 1;
        let pad = quad.iter().rev().take_while(|&&c| c == b'=').count();
        if pad > 2 || (pad > 0 && !last) { return None; }
        let mut n = 0u32;
        for &c in &quad[..4 - pad] { n = (n << 6) | value(c)?; }
        n <<= 6 * pad as u32;
        out.push((n >> 16) as u8);
        if pad < 2 { out.push((n >> 8) as u8); }
        if pad < 1 { out.push(n as u8); }
    }
    Some(out)
}

fn download_path() -> PathBuf {
    std::env::temp_dir().join(format!("pagetide-pdf-{}-{}.pdf", std::process::id(),
        Instant::now().elapsed().as_nanos() ^ (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos()).unwrap_or(0))))
}

/// A finished transfer is accepted only if it looks like a PDF and fits; the server checks the whole file again.
fn accept(job: &mut Job, bytes: Vec<u8>, from: Option<String>) -> bool {
    if bytes.len() > MAX_BYTES || !bytes.starts_with(b"%PDF-") {
        trace(&format!("refused a transfer of {} bytes", bytes.len()));
        return false;
    }
    job.bytes = bytes;
    job.state = "received";
    job.from = from;
    true
}

fn download_window(app: &AppHandle) -> Result<WebviewWindow, String> {
    if let Some(window) = app.get_webview_window(LABEL) {
        return Ok(window);
    }
    let blank: Url = "about:blank".parse().map_err(|_| "Invalid address")?;
    let builder = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::External(blank))
        .title("PageTide · 在应用里下载 PDF")
        .inner_size(1100.0, 860.0)
        .initialization_script(SCRIPT)
        .data_store_identifier(if RELEASE_BUILD { STORE_RELEASE } else { STORE_DEV })
        .on_navigation(|url: &Url| {
            let ok = allowed_navigation(url);
            if !ok { trace(&format!("navigation refused: {}", url.as_str().chars().take(160).collect::<String>())); }
            ok
        })
        // A link that opens a new tab (most PDF buttons) opens in this window instead.
        .on_new_window({
            let app = app.clone();
            move |url, _| {
                if allowed_navigation(&url) {
                    let app = app.clone();
                    let _ = app.clone().run_on_main_thread(move || {
                        if let Some(window) = app.get_webview_window(LABEL) { let _ = window.navigate(url); }
                    });
                }
                tauri::webview::NewWindowResponse::Deny
            }
        })
        .on_download({
            let app = app.clone();
            move |_, event| match event {
                tauri::webview::DownloadEvent::Requested { url, destination } => {
                    let path = download_path();
                    trace(&format!("download requested from {}", url.host_str().unwrap_or("-")));
                    *destination = path.clone();
                    if let Ok(mut job) = app.state::<PdfWindowState>().0.lock() {
                        match job.as_mut() {
                            Some(job) if job.state == "open" => job.download_to = Some(path),
                            _ => return false,      // no job: nothing is downloaded
                        }
                    }
                    true
                }
                tauri::webview::DownloadEvent::Finished { url, path, success } => {
                    let state = app.state::<PdfWindowState>();
                    let Ok(mut guard) = state.0.lock() else { return true };
                    let Some(job) = guard.as_mut() else { return true };
                    let file = path.or_else(|| job.download_to.take());
                    if let Some(file) = file {
                        let read = if success { std::fs::read(&file).ok() } else { None };
                        let _ = std::fs::remove_file(&file);
                        if let Some(bytes) = read {
                            accept(job, bytes, url.host_str().map(str::to_string));
                        }
                    }
                    true
                }
                _ => true,
            }
        });
    #[cfg(windows)]
    let builder = {
        let base = app.path().app_local_data_dir().map_err(|e| e.to_string())?;
        builder.data_directory(base.join(if RELEASE_BUILD { "pdf-webview" } else { "pdf-webview-dev" }))
    };
    builder.build().map_err(|e| e.to_string())
}

fn close_window(app: &AppHandle) {
    let app = app.clone();
    let _ = app.clone().run_on_main_thread(move || {
        if let Some(window) = app.get_webview_window(LABEL) { let _ = window.close(); }
    });
}

/// Async: building a window from a synchronous command deadlocks on Windows (Tauri's documented WebView2 issue).
#[tauri::command]
pub async fn pdf_window_open(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, PdfWindowState>,
                             app: AppHandle, key: String, url: String) -> Result<Value, String> {
    owned_page(&window, &session)?;
    let start: Url = url.parse().map_err(|_| "Invalid paper address")?;
    if !allowed_navigation(&start) || start.scheme() != "https" || key.is_empty() || key.len() > 300 {
        return Err("Invalid paper address".into());
    }
    {
        let mut job = state.0.lock().map_err(|_| "Download window unavailable")?;
        *job = Some(Job { key, state: "open", bytes: Vec::new(), expected: 0, started: Instant::now(), download_to: None,
                          from: None });
    }
    let download = download_window(&app)?;
    download.navigate(start).map_err(|e| e.to_string())?;
    let _ = download.show();
    let _ = download.unminimize();
    let _ = download.set_focus();
    Ok(json!({"opened": true}))
}

/// The job's state, never the bytes: open (waiting for the person), received, closed (the person closed the window),
/// failed, or idle.
#[tauri::command]
pub fn pdf_window_poll(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, PdfWindowState>,
                       app: AppHandle) -> Result<Value, String> {
    owned_page(&window, &session)?;
    let (reply, close) = {
        let mut guard = state.0.lock().map_err(|_| "Download window unavailable")?;
        let Some(job) = guard.as_mut() else { return Ok(json!({"state": "idle"})) };
        let mut close = false;
        if job.state == "open" && job.started.elapsed() > OPEN_LIMIT {
            job.state = "failed";
            close = true;
        }
        (json!({"state": job.state, "key": job.key, "bytes": job.bytes.len(), "from": job.from}), close)
    };
    if close { close_window(&app); }
    Ok(reply)
}

/// The received PDF, as raw bytes (an ArrayBuffer on the page); the job ends and the window closes.
#[tauri::command]
pub fn pdf_window_take(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, PdfWindowState>,
                       app: AppHandle, key: String) -> Result<Response, String> {
    owned_page(&window, &session)?;
    let bytes = {
        let mut guard = state.0.lock().map_err(|_| "Download window unavailable")?;
        match guard.as_ref() {
            Some(job) if job.state == "received" && job.key == key => {}
            _ => return Err("No downloaded PDF for this paper".into()),
        }
        guard.take().map(|job| job.bytes).unwrap_or_default()
    };
    close_window(&app);
    Ok(Response::new(bytes))
}

#[tauri::command]
pub fn pdf_window_cancel(window: WebviewWindow, session: State<'_, DesktopSession>, state: State<'_, PdfWindowState>,
                         app: AppHandle) -> Result<(), String> {
    owned_page(&window, &session)?;
    if let Ok(mut job) = state.0.lock() { *job = None; }
    close_window(&app);
    Ok(())
}

/// The page script in the download window: one chunk of a PDF it read with the window's own session. `index` 0 starts a
/// transfer of `total` bytes; the last chunk completes it. Untrusted: sizes are capped and the result must look like a PDF.
#[tauri::command]
pub fn pdf_window_chunk(window: WebviewWindow, state: State<'_, PdfWindowState>, index: u32, total: u64, data: String)
                        -> Result<Value, String> {
    let url = window.url().map_err(|e| e.to_string())?;
    if window.label() != LABEL || url.scheme() != "https" {
        return Err("Download command denied for this window".into());
    }
    if data.len() > MAX_CHUNK_CHARS || total as usize > MAX_BYTES {
        return Err("Too large".into());
    }
    let bytes = decode_base64(&data).ok_or("Invalid chunk")?;
    let mut guard = state.0.lock().map_err(|_| "Download window unavailable")?;
    let Some(job) = guard.as_mut() else { return Ok(json!({"accepted": false})) };
    if job.state != "open" {
        return Ok(json!({"accepted": false}));
    }
    if index == 0 {
        job.bytes = Vec::with_capacity(total as usize);
        job.expected = total as usize;
    }
    if job.bytes.len() + bytes.len() > job.expected {
        job.bytes.clear();
        return Err("More bytes than announced".into());
    }
    job.bytes.extend_from_slice(&bytes);
    if job.bytes.len() == job.expected {
        let all = std::mem::take(&mut job.bytes);
        let ok = accept(job, all, url.host_str().map(str::to_string));
        trace(&format!("transfer complete from {}: {}", url.host_str().unwrap_or("-"), if ok { "accepted" } else { "refused" }));
        return Ok(json!({"accepted": ok, "done": true}));
    }
    Ok(json!({"accepted": true}))
}

/// The person closed the window without a PDF: the main page stops waiting.
pub fn on_closed(app: &AppHandle) {
    if let Ok(mut job) = app.state::<PdfWindowState>().0.lock() {
        if let Some(job) = job.as_mut() {
            if job.state == "open" { job.state = "closed"; }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn job() -> Job {
        Job { key: "k".into(), state: "open", bytes: Vec::new(), expected: 0, started: Instant::now(), download_to: None, from: None }
    }

    #[test]
    fn only_https_on_public_hosts_is_allowed() {
        for ok in ["https://iopscience.iop.org/article/x/pdf", "https://doi.org/10.1/x", "about:blank", "https://8.8.8.8/a.pdf"] {
            assert!(allowed_navigation(&ok.parse().unwrap()), "{ok}");
        }
        for bad in ["http://iopscience.iop.org/x", "https://localhost/x", "https://127.0.0.1:5000/api", "https://192.168.1.2/x",
                    "https://10.0.0.1/x", "https://nas/x", "https://printer.local/x", "file:///etc/passwd", "https://[::1]/x",
                    "javascript:alert(1)", "tauri://localhost/x"] {
            assert!(!allowed_navigation(&bad.parse().unwrap()), "{bad}");
        }
    }

    #[test]
    fn only_something_that_starts_like_a_pdf_is_received() {
        let mut j = job();
        assert!(!accept(&mut j, b"<html>bot check</html>".to_vec(), None));
        assert_eq!(j.state, "open");
        assert!(accept(&mut j, b"%PDF-1.7 ...".to_vec(), Some("iopscience.iop.org".into())));
        assert_eq!((j.state, j.from.as_deref()), ("received", Some("iopscience.iop.org")));
    }

    #[test]
    fn base64_from_the_page_decodes() {
        assert_eq!(decode_base64("JVBERi0xLjc=").unwrap(), b"%PDF-1.7");
        assert_eq!(decode_base64("JVBERi0=").unwrap(), b"%PDF-");
        assert_eq!(decode_base64("").unwrap(), b"");
        assert!(decode_base64("JVB").is_none());
        assert!(decode_base64("JV=E").is_none());
        assert!(decode_base64("JVBE*i0=").is_none());
    }

    #[test]
    fn an_oversized_transfer_is_refused() {
        let mut j = job();
        let mut big = b"%PDF-".to_vec();
        big.resize(MAX_BYTES + 1, b' ');
        assert!(!accept(&mut j, big, None));
    }
}
