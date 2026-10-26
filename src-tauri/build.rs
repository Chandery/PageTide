fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["save_export", "complete_quit", "pick_folder", "relaunch",
                                                   "cnki_start", "cnki_poll", "cnki_cancel", "cnki_next", "cnki_report",
                                                   "pdf_window_open", "pdf_window_poll", "pdf_window_take", "pdf_window_cancel",
                                                   "pdf_window_chunk"])
    )).expect("failed to build desktop permissions");
}
