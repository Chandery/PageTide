#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    io::{BufRead, BufReader},
    process::{Child, Command, Stdio},
    sync::{mpsc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{App, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};

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
    let server = app.path().resource_dir()?.join("backend/paperdighelper-server");
    let mut child = Command::new(server)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .env_remove("PDH_DEV")
        .env_remove("DEEPSEEK_API_KEY")
        .spawn()?;
    let stdout = child.stdout.take().ok_or("missing server stdout")?;
    let process = PythonProcess(Mutex::new(Some(child)));
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let _ = sender.send(BufReader::new(stdout).lines().next());
    });
    let line = receiver.recv_timeout(Duration::from_secs(30))?
        .ok_or("Python server exited before startup")??;
    let url: Url = line.strip_prefix("PDH_READY ")
        .ok_or("invalid Python startup message")?.parse()?;
    if url.scheme() != "http" || url.host_str() != Some("127.0.0.1") || url.port().is_none() {
        return Err("invalid local server address".into());
    }
    Ok((process, url))
}

fn open_external(url: &Url) {
    if matches!(url.scheme(), "http" | "https") {
        let _ = Command::new("/usr/bin/open").arg(url.as_str()).spawn();
    }
}

fn main() {
    let result = tauri::Builder::default()
        .setup(|app| {
            let (process, url) = start_server(app)?;
            let origin = url.origin();
            app.manage(process);
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("PaperDigHelper")
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
            if matches!(event, RunEvent::Exit) {
                if let Some(process) = handle.try_state::<PythonProcess>() {
                    process.stop();
                }
            }
        }),
        Err(error) => {
            eprintln!("PaperDigHelper startup failed: {error}");
            std::process::exit(1);
        }
    }
}
