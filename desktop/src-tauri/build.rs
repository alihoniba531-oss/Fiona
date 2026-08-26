fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(
            tauri_build::AppManifest::new().commands(&[
                "open_url",
                "open_url_in_app",
                "startup_diagnostics",
                "probe_backend",
                "open_logs_dir",
            ]),
        ),
    )
    .expect("failed to build Tauri command manifest")
}
