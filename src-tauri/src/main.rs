#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    io::{BufRead, BufReader},
    process::{Child, Command, Stdio},
    sync::{mpsc, Mutex, atomic::{AtomicBool, Ordering}},
    thread,
    time::{Duration, Instant},
};
use tauri::{App, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder, WebviewWindow, State, WindowEvent};

const GUARDED_QUIT: &str = "pagetide-prepare-quit";

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[cfg(target_os = "macos")]
static NATIVE_QUIT_APP: std::sync::OnceLock<tauri::AppHandle> = std::sync::OnceLock::new();

#[cfg(target_os = "macos")]
static NATIVE_QUIT_ENCODING: std::sync::OnceLock<std::ffi::CString> = std::sync::OnceLock::new();

#[cfg(target_os = "macos")]
fn native_termination_reply(quitting: bool, dispatch: impl FnOnce()) -> objc2_app_kit::NSApplicationTerminateReply {
    use objc2_app_kit::NSApplicationTerminateReply;
    if quitting {
        return NSApplicationTerminateReply::TerminateNow;
    }
    // Cancel this Cocoa termination synchronously. The page can later acknowledge
    // through complete_quit/app.exit; Cancel/Escape and a failed dispatch need no
    // replyToApplicationShouldTerminate call or pending Cocoa termination state.
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(dispatch)) {
        Ok(()) => {}
        Err(payload) => {
            // A panic payload may itself panic in Drop. Preserve this exceptional
            // allocation rather than release it across the native callback boundary.
            std::mem::forget(payload);
            eprintln!("PageTide native quit guard failed; application remains open");
        }
    }
    NSApplicationTerminateReply::TerminateCancel
}

#[cfg(target_os = "macos")]
fn native_callback_reply(dispatch: impl FnOnce() -> objc2_app_kit::NSApplicationTerminateReply) -> objc2_app_kit::NSApplicationTerminateReply {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(dispatch)) {
        Ok(reply) => reply,
        Err(payload) => {
            // No Rust destructor or logging runs after this final native boundary.
            std::mem::forget(payload);
            objc2_app_kit::NSApplicationTerminateReply::TerminateCancel
        }
    }
}

#[cfg(target_os = "macos")]
extern "C-unwind" fn application_should_terminate(
    _delegate: *mut objc2::runtime::AnyObject,
    _selector: objc2::runtime::Sel,
    _application: *mut objc2_app_kit::NSApplication,
) -> objc2_app_kit::NSApplicationTerminateReply {
    use objc2_app_kit::NSApplicationTerminateReply;
    // Never unwind Rust state access or dispatch across the Objective-C callback.
    native_callback_reply(|| {
        let Some(handle) = NATIVE_QUIT_APP.get() else {
            return NSApplicationTerminateReply::TerminateCancel;
        };
        let quitting = handle.try_state::<DesktopSession>()
            .map(|session| session.quitting.load(Ordering::SeqCst)).unwrap_or(false);
        native_termination_reply(quitting, || prepare_quit(handle))
    })
}

#[cfg(target_os = "macos")]
fn install_native_quit_guard(app: &App) -> Result<(), Box<dyn std::error::Error>> {
    use objc2::{Encode, MainThreadMarker, runtime::{AnyClass, AnyObject, Imp, Sel}, sel};
    use objc2_app_kit::{NSApplication, NSApplicationTerminateReply};
    let main = MainThreadMarker::new().ok_or("Native quit guard requires the main thread")?;
    let application = NSApplication::sharedApplication(main);
    let delegate = application.delegate().ok_or("Missing macOS application delegate")?;
    let object: &AnyObject = (&*delegate).as_ref();
    let class = object.class();
    let selector = sel!(applicationShouldTerminate:);
    // This narrow patch is for our pinned Tao delegate only. Refuse startup if a
    // future Tao version supplies its own policy; never replace an existing method.
    if class.name().to_bytes() != b"TaoAppDelegateParent" || class.instance_method(selector).is_some() {
        return Err("Unexpected macOS termination delegate; refusing an unverified override".into());
    }
    NATIVE_QUIT_APP.set(app.handle().clone()).map_err(|_| "Native quit guard already registered")?;
    let encoding = std::ffi::CString::new(format!("{}@:@", NSApplicationTerminateReply::ENCODING))?;
    NATIVE_QUIT_ENCODING.set(encoding).map_err(|_| "Native quit guard encoding already registered")?;
    let encoding = NATIVE_QUIT_ENCODING.get().ok_or("Missing native quit guard encoding")?;
    type Callback = extern "C-unwind" fn(*mut AnyObject, Sel, *mut NSApplication) -> NSApplicationTerminateReply;
    // SAFETY: The existing delegate/class remains retained by Tao and by `delegate`
    // here. Only an absent selector is added, with the AppKit return/argument ABI;
    // neither its object identity, ivars nor other callbacks are replaced. The
    // callback and encoding have process lifetime, and its panics are contained.
    let added = unsafe {
        let implementation = std::mem::transmute::<Callback, Imp>(application_should_terminate as Callback);
        objc2::ffi::class_addMethod(class as *const AnyClass as *mut AnyClass, selector, implementation, encoding.as_ptr()).as_bool()
    };
    if !added {
        return Err("Could not install macOS termination guard".into());
    }
    // Re-register this same retained object so AppKit sees its new optional method.
    // setDelegate is weak; Tao retains the original delegate for the event loop.
    application.setDelegate(None);
    application.setDelegate(Some(&delegate));
    Ok(())
}

#[cfg(target_os = "macos")]
fn install_guarded_quit_menu(app: &App) -> Result<(), Box<dyn std::error::Error>> {
    use tauri::menu::{Menu, MenuItem, MenuItemKind};
    // muda's predefined macOS Quit sends terminate: directly to NSApplication.
    // It bypasses the cancellable event loop exit request. Keep the default
    // menus, but dispatch its Cmd+Q through the page's durable-draft guard.
    let menu = Menu::default(app.handle())?;
    let items = menu.items()?;
    let application = items.first().and_then(MenuItemKind::as_submenu)
        .ok_or("Missing macOS application menu")?;
    let application_items = application.items()?;
    let quit = application_items.last().and_then(MenuItemKind::as_predefined_menuitem)
        .ok_or("Missing macOS predefined Quit")?;
    let label = quit.text()?;
    if !label.starts_with("Quit ") {
        return Err("Unexpected macOS default Quit; refusing an unguarded menu".into());
    }
    application.remove(quit)?;
    application.append(&MenuItem::with_id(app, GUARDED_QUIT, label, true, Some("CmdOrCtrl+Q"))?)?;
    app.set_menu(menu)?;
    Ok(())
}

struct DesktopSession { origin: String, quitting: AtomicBool }

fn owned_page(window: &WebviewWindow, session: &DesktopSession) -> Result<(), String> {
    if window.label() != "main" || window.url().map_err(|e| e.to_string())?.origin().ascii_serialization() != session.origin {
        return Err("Desktop command denied for this origin".into());
    }
    Ok(())
}

#[cfg(not(windows))]
#[tauri::command]
fn save_export(window: WebviewWindow, session: State<'_, DesktopSession>, filename: String, content: String) -> Result<String, String> {
    owned_page(&window, &session)?;
    if filename.is_empty() || filename.len() > 200 || filename.contains('/') || filename.contains('\\') || content.len() > 512 * 1024 * 1024 {
        return Err("Invalid export filename or export exceeds 512 MB".into());
    }
    #[cfg(target_os = "macos")]
    {
        use objc2::MainThreadMarker;
        use objc2_app_kit::{NSSavePanel, NSModalResponseOK, NSModalResponseCancel};
        use objc2_foundation::NSString;
        let main = MainThreadMarker::new().ok_or("Save dialog requires the main thread")?;
        let panel = NSSavePanel::savePanel(main);
        panel.setNameFieldStringValue(&NSString::from_str(&filename));
        let response = panel.runModal();
        if response == NSModalResponseCancel { return Ok("{\"status\":\"cancelled\"}".into()); }
        if response != NSModalResponseOK { return Err("Save dialog failed to open".into()); }
        let path = panel.URL().and_then(|url| url.path()).ok_or("Missing export destination")?.to_string();
        let destination = std::path::Path::new(&path);
        let parent = destination.parent().ok_or("Invalid export destination")?;
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
        let temporary = parent.join(format!(".pagetide-export-{}-{}.tmp", std::process::id(), stamp));
        let result = (|| -> std::io::Result<()> {
            use std::io::Write;
            use std::os::unix::fs::OpenOptionsExt;
            let mut file = std::fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&temporary)?;
            file.write_all(content.as_bytes())?; file.sync_all()?;
            std::fs::rename(&temporary, destination)?;
            Ok(())
        })();
        if let Err(error) = result { let _ = std::fs::remove_file(&temporary); return Err(error.to_string()); }
        return Ok(serde_json::json!({"status":"saved", "path":path, "bytes":content.len()}).to_string());
    }
    #[cfg(not(any(target_os = "macos", windows)))]
    Err("Native export is currently supported on macOS and Windows".into())
}

/// Windows: the modal "Save as" dialog runs on a blocking worker thread (never the main/UI thread, so the
/// webview keeps painting and the quit guard keeps working) and is parented to the app window. Then the same
/// temp-file + rename write as on macOS; std::fs::rename replaces an existing destination on Windows.
#[cfg(windows)]
#[tauri::command]
async fn save_export(window: WebviewWindow, session: State<'_, DesktopSession>, filename: String, content: String) -> Result<String, String> {
    owned_page(&window, &session)?;
    if filename.is_empty() || filename.len() > 200 || filename.contains('/') || filename.contains('\\') || content.len() > 512 * 1024 * 1024 {
        return Err("Invalid export filename or export exceeds 512 MB".into());
    }
    tauri::async_runtime::spawn_blocking(move || -> Result<String, String> {
        let destination = rfd::FileDialog::new().set_parent(&window).set_file_name(filename.as_str()).save_file();
        let Some(destination) = destination else { return Ok("{\"status\":\"cancelled\"}".into()); };
        let parent = destination.parent().ok_or("Invalid export destination")?;
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
        let temporary = parent.join(format!(".pagetide-export-{}-{}.tmp", std::process::id(), stamp));
        let result = (|| -> std::io::Result<()> {
            use std::io::Write;
            // The per-user profile ACL protects the file; there is no POSIX mode to set.
            let mut file = std::fs::OpenOptions::new().write(true).create_new(true).open(&temporary)?;
            file.write_all(content.as_bytes())?; file.sync_all()?;
            drop(file);
            std::fs::rename(&temporary, &destination)?;
            Ok(())
        })();
        if let Err(error) = result { let _ = std::fs::remove_file(&temporary); return Err(error.to_string()); }
        let path = destination.to_string_lossy().to_string();
        Ok(serde_json::json!({"status":"saved", "path":path, "bytes":content.len()}).to_string())
    }).await.map_err(|e| e.to_string())?
}

#[tauri::command]
fn complete_quit(window: WebviewWindow, session: State<'_, DesktopSession>, app: tauri::AppHandle) -> Result<(), String> {
    owned_page(&window, &session)?;
    session.quitting.store(true, Ordering::SeqCst);
    app.exit(0);
    Ok(())
}

fn prepare_quit(handle: &tauri::AppHandle) {
    if let Some(window) = handle.get_webview_window("main") {
        // The page flushes recoverable drafts before acknowledging; a failure keeps the app open.
        let _ = window.show();
        let _ = window.set_focus();
        if let Err(error) = window.eval("window.PDHPrepareQuit ? window.PDHPrepareQuit() : window.__TAURI_INTERNALS__.invoke('complete_quit');") {
            eprintln!("PageTide quit guard could not reach the page; application remains open: {error}");
        }
    }
}

struct PythonProcess(Mutex<Option<Child>>);

impl PythonProcess {
    fn stop(&self) {
        if let Ok(mut process) = self.0.lock() {
            if let Some(mut child) = process.take() {
                drop(child.stdin.take());
                let deadline = Instant::now() + Duration::from_secs(2);
                while Instant::now() < deadline {
                    if matches!(child.try_wait(), Ok(Some(_))) {
                        return;
                    }
                    thread::sleep(Duration::from_millis(25));
                }
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

impl Drop for PythonProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

fn start_server(app: &App) -> Result<(PythonProcess, Url), Box<dyn std::error::Error>> {
    let name = if cfg!(windows) { "pagetide-server.exe" } else { "pagetide-server" };
    let server = app.path().resource_dir()?.join("backend").join(name);
    let mut command = Command::new(server);
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .env_remove("PAGETIDE_DEV")
        .env_remove("DEEPSEEK_API_KEY")
        // The packaged version, for the update check. A source run has no such variable and never checks.
        .env("PAGETIDE_APP_VERSION", app.package_info().version.to_string());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // A GUI-subsystem parent has no valid stderr to inherit, which would leave Python without
        // sys.stderr; give it NUL and have the backend write <data dir>/logs/backend.log itself
        // (PAGETIDE_LOG_STDERR, size-capped, app/desktop.py). No console window for the backend; UTF-8 for
        // files with Chinese text.
        command.stderr(Stdio::null()).env("PYTHONUTF8", "1").env("PAGETIDE_LOG_STDERR", "1").creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    command.stderr(Stdio::inherit());
    let mut child = command.spawn()?;
    let stdout = child.stdout.take().ok_or("missing server stdout")?;
    let process = PythonProcess(Mutex::new(Some(child)));
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let _ = sender.send(BufReader::new(stdout).lines().next());
    });
    let line = receiver.recv_timeout(Duration::from_secs(30))?
        .ok_or("Python server exited before startup")??;
    let url: Url = line.strip_prefix("PAGETIDE_READY ")
        .ok_or("invalid Python startup message")?.parse()?;
    if url.scheme() != "http" || url.host_str() != Some("127.0.0.1") || url.port().is_none() {
        return Err("invalid local server address".into());
    }
    Ok((process, url))
}

fn open_external(url: &Url) {
    if matches!(url.scheme(), "http" | "https") {
        #[cfg(target_os = "macos")]
        let _ = Command::new("/usr/bin/open").arg(url.as_str()).spawn();
        #[cfg(windows)]
        {
            // No shell: the already-validated, ASCII-serialized http(s) URL is a single argv entry,
            // so `&`, `^` or `%` in it are never interpreted (unlike `cmd /C start`).
            use std::os::windows::process::CommandExt;
            // Absolute path: never resolved through PATH or the current directory.
            let system = std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into());
            let rundll = std::path::Path::new(&system).join("System32").join("rundll32.exe");
            let _ = Command::new(rundll).arg("url.dll,FileProtocolHandler").arg(url.as_str())
                .creation_flags(CREATE_NO_WINDOW).spawn();
        }
    }
}

fn main() {
    let builder = tauri::Builder::default();
    // Windows: a second launch focuses the running window instead of racing it for the data directory
    // lock (the second backend would exit with "already running" and nobody would see why). The plugin must
    // be registered first. macOS keeps its LaunchServices behaviour.
    #[cfg(windows)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.unminimize();
            let _ = window.show();
            let _ = window.set_focus();
        }
    }));
    let result = builder
        .invoke_handler(tauri::generate_handler![save_export, complete_quit])
        .on_menu_event(|handle, event| {
            if event.id().as_ref() == GUARDED_QUIT {
                prepare_quit(handle);
            }
        })
        .setup(|app| {
            let (process, url) = start_server(app)?;
            let origin = url.origin();
            let exact_origin = origin.ascii_serialization();
            app.manage(DesktopSession { origin: exact_origin.clone(), quitting: AtomicBool::new(false) });
            #[cfg(target_os = "macos")]
            install_guarded_quit_menu(app)?;
            #[cfg(target_os = "macos")]
            install_native_quit_guard(app)?;
            // Grant only our two app commands, only to this instance's random loopback origin.
            let capability = serde_json::json!({"identifier":"owned-desktop-session", "local":false,
                "windows":["main"], "remote":{"urls":[format!("{}/*", exact_origin)]},
                "permissions":["allow-save-export", "allow-complete-quit"]}).to_string();
            app.add_capability(capability.as_str())?;
            app.manage(process);
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("PageTide")
                .inner_size(1120.0, 760.0)
                .min_inner_size(640.0, 480.0)
                .resizable(true)
                // Let the page receive dropped files (a PDF dragged onto project creation); without
                // this Tauri swallows the drop. A drop that navigates the window is still refused by
                // on_navigation below.
                .disable_drag_drop_handler()
                .on_navigation(move |url| {
                    if url.origin() == origin {
                        true
                    } else {
                        open_external(url);
                        false
                    }
                })
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!());
    match result {
        Ok(app) => app.run(|handle, event| {
            match &event {
                RunEvent::ExitRequested { api, .. } if !handle.state::<DesktopSession>().quitting.load(Ordering::SeqCst) => {
                    api.prevent_exit(); prepare_quit(handle);
                }
                RunEvent::WindowEvent { event: WindowEvent::CloseRequested { api, .. }, .. }
                    if !handle.state::<DesktopSession>().quitting.load(Ordering::SeqCst) => {
                    api.prevent_close(); prepare_quit(handle);
                }
                _ => {}
            }
            if matches!(event, RunEvent::Exit) {
                if let Some(process) = handle.try_state::<PythonProcess>() {
                    process.stop();
                }
            }
        }),
        Err(error) => {
            eprintln!("PageTide startup failed: {error}");
            // A GUI-subsystem Windows process has no console: without a dialog the user sees nothing.
            #[cfg(windows)]
            {
                let _ = rfd::MessageDialog::new()
                    .set_level(rfd::MessageLevel::Error)
                    .set_title("PageTide")
                    .set_description(format!("PageTide could not start.\n\n{error}\n\nDetails may be in the logs folder inside the PageTideData folder under %LOCALAPPDATA%."))
                    .set_buttons(rfd::MessageButtons::Ok)
                    .show();
            }
            std::process::exit(1);
        }
    }
}

#[cfg(all(test, target_os = "macos"))]
mod native_quit_policy_tests {
    use super::*;
    use objc2_app_kit::NSApplicationTerminateReply;
    use std::cell::Cell;
    use std::sync::{Arc, atomic::AtomicUsize};

    struct ReentrantPanicPayload(Arc<AtomicUsize>);

    impl Drop for ReentrantPanicPayload {
        fn drop(&mut self) {
            if self.0.fetch_add(1, Ordering::SeqCst) < 2 {
                std::panic::panic_any(ReentrantPanicPayload(self.0.clone()));
            }
        }
    }

    fn checked_reply(dispatch: impl FnOnce() -> NSApplicationTerminateReply) -> Option<NSApplicationTerminateReply> {
        // The regression harness must also avoid dropping an escaped synthetic
        // payload, so it can report a failure without a second test-harness panic.
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(dispatch)) {
            Ok(reply) => Some(reply),
            Err(payload) => { std::mem::forget(payload); None }
        }
    }

    #[test]
    fn native_quit_policy_cancels_system_termination_until_page_acknowledges() {
        let requests = Cell::new(0);
        let reply = native_termination_reply(false, || requests.set(requests.get() + 1));
        assert_eq!(reply, NSApplicationTerminateReply::TerminateCancel);
        assert_eq!(requests.get(), 1);
        let acknowledged = native_termination_reply(true, || requests.set(requests.get() + 1));
        assert_eq!(acknowledged, NSApplicationTerminateReply::TerminateNow);
        assert_eq!(requests.get(), 1);
    }

    #[test]
    fn native_quit_policy_panic_does_not_approve_or_poison_next_request() {
        let failed = native_termination_reply(false, || panic!("synthetic guard dispatch failure"));
        assert_eq!(failed, NSApplicationTerminateReply::TerminateCancel);
        let retried = Cell::new(false);
        let reply = native_termination_reply(false, || retried.set(true));
        assert_eq!(reply, NSApplicationTerminateReply::TerminateCancel);
        assert!(retried.get());
    }

    #[test]
    fn native_quit_policy_callback_without_registered_app_stays_open() {
        // A startup-time request cannot acknowledge by default. Raw arguments are
        // deliberately unused; no application/window or Objective-C UI is created.
        let reply = application_should_terminate(
            std::ptr::null_mut(), objc2::sel!(applicationShouldTerminate:), std::ptr::null_mut(),
        );
        assert_eq!(reply, NSApplicationTerminateReply::TerminateCancel);
    }

    #[test]
    fn native_quit_policy_does_not_drop_a_panicking_dispatch_payload() {
        let drops = Arc::new(AtomicUsize::new(0));
        let payload = ReentrantPanicPayload(drops.clone());
        let reply = checked_reply(|| native_termination_reply(false, || std::panic::panic_any(payload)));
        assert_eq!(reply, Some(NSApplicationTerminateReply::TerminateCancel));
        assert_eq!(drops.load(Ordering::SeqCst), 0);
    }

    #[test]
    fn native_quit_policy_callback_boundary_does_not_drop_a_panicking_payload() {
        let drops = Arc::new(AtomicUsize::new(0));
        let payload = ReentrantPanicPayload(drops.clone());
        let reply = checked_reply(|| native_callback_reply(|| std::panic::panic_any(payload)));
        assert_eq!(reply, Some(NSApplicationTerminateReply::TerminateCancel));
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        assert_eq!(native_callback_reply(|| native_termination_reply(true, || panic!("acknowledged quit must not dispatch"))), NSApplicationTerminateReply::TerminateNow);
    }

    #[test]
    fn native_quit_policy_nested_callback_keeps_both_layers_safe_and_retriable() {
        let drops = Arc::new(AtomicUsize::new(0));
        let payload = ReentrantPanicPayload(drops.clone());
        let reply = checked_reply(|| native_callback_reply(|| native_termination_reply(false, || std::panic::panic_any(payload))));
        assert_eq!(reply, Some(NSApplicationTerminateReply::TerminateCancel));
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        let retried = Cell::new(false);
        assert_eq!(native_callback_reply(|| native_termination_reply(false, || retried.set(true))), NSApplicationTerminateReply::TerminateCancel);
        assert!(retried.get());
    }
}
