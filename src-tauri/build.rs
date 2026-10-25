fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["save_export", "complete_quit", "pick_folder", "relaunch"])
    )).expect("failed to build desktop permissions");
}
