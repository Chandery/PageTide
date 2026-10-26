fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["save_export", "complete_quit", "pick_folder", "relaunch",
                                                   "cnki_start", "cnki_poll", "cnki_cancel", "cnki_next", "cnki_report"])
    )).expect("failed to build desktop permissions");
}
