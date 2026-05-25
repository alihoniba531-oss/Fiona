// Tauri 2 入口 — release 模式下 windows_subsystem = "windows" 关掉 Windows 后台的黑底控制台
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    fiona_desktop_lib::run()
}
