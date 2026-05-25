// 桌面壳本体——dev 加载 http://localhost:3000（SSH 转发的云端 next dev），
// prod 用 frontendDist 静态资源。两条路径都不需要 Rust 端额外逻辑，纯壳子。
// 以后需要 OS keychain / 托盘 / 通知再在这里加 plugin。

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
