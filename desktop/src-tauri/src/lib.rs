// 桌面壳 + 嵌入式 SSH 隧道 + 自定义 open_url 命令。
//
// 启动流程：
//   1. 读 desktop/fiona.config.json（云 IP / 用户 / 转发规则）
//   2. spawn `ssh -N -L ...` 子进程做端口转发
//   3. 轮询 localhost:<主端口> 直到通（最长 15 秒）
//   4. 启动 Tauri 窗口，加载 devUrl
//   5. 关窗时 kill 隧道子进程
//
// 自定义 open_url 命令（绕过 plugin-opener 的 ACL 配置坑）：
// 自定义 command 用 invoke_handler 注册，默认不走 capability ACL，
// 前端直接 invoke("open_url", { url }) 即可。

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::Manager;

#[derive(Deserialize)]
struct CloudConfig {
    host: String,
    user: String,
    #[serde(default)]
    port: Option<u16>,
    /// 例如 ["3000:127.0.0.1:3000", "8000:127.0.0.1:8000"]
    forwards: Vec<String>,
}

fn find_config() -> Option<PathBuf> {
    // dev：CARGO_MANIFEST_DIR/../fiona.config.json（desktop/fiona.config.json）
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let dev_path = manifest.parent().map(|d| d.join("fiona.config.json"));
    if let Some(p) = dev_path {
        if p.exists() {
            return Some(p);
        }
    }
    // .msi 安装版的标准位置：%APPDATA%\fiona\config.json
    #[cfg(windows)]
    if let Ok(appdata) = std::env::var("APPDATA") {
        let c = PathBuf::from(appdata).join("fiona").join("config.json");
        if c.exists() {
            return Some(c);
        }
    }
    // 兜底：可执行文件同级或上几级
    if let Ok(exe) = std::env::current_exe() {
        for parent in exe.ancestors().take(4) {
            let c = parent.join("fiona.config.json");
            if c.exists() {
                return Some(c);
            }
        }
    }
    None
}

fn load_config() -> Option<CloudConfig> {
    let p = find_config()?;
    let txt = std::fs::read_to_string(&p).ok()?;
    serde_json::from_str(&txt).ok()
}

fn spawn_tunnel(cfg: &CloudConfig) -> Option<Child> {
    let mut cmd = Command::new("ssh");
    cmd.arg("-N")
        .arg("-o").arg("BatchMode=yes")            // 不交互问密码——必须配过免密
        .arg("-o").arg("ServerAliveInterval=30")
        .arg("-o").arg("ExitOnForwardFailure=yes")
        .arg("-o").arg("StrictHostKeyChecking=accept-new");
    if let Some(port) = cfg.port {
        cmd.arg("-p").arg(port.to_string());
    }
    for fwd in &cfg.forwards {
        cmd.arg("-L").arg(fwd);
    }
    cmd.arg(format!("{}@{}", cfg.user, cfg.host));
    cmd.stdout(Stdio::null()).stderr(Stdio::null());
    cmd.spawn().ok()
}

fn wait_for_port(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect_timeout(
            &format!("127.0.0.1:{}", port).parse().unwrap(),
            Duration::from_secs(1),
        )
        .is_ok()
        {
            return true;
        }
        thread::sleep(Duration::from_millis(300));
    }
    false
}

fn primary_port(cfg: &CloudConfig) -> u16 {
    cfg.forwards
        .iter()
        .filter_map(|s| s.split(':').next().and_then(|p| p.parse().ok()))
        .next()
        .unwrap_or(3000)
}

/// 用系统默认应用打开 URL（绕过 plugin-opener 的 ACL 配置）
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        // cmd /C start "" <url> ——空标题避免 start 把 url 当窗口标题
        Command::new("cmd")
            .args(["/C", "start", "", &url])
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&url)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(&url)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let cfg = load_config();
    let tunnel: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));

    if let Some(c) = cfg.as_ref() {
        if let Some(child) = spawn_tunnel(c) {
            *tunnel.lock().unwrap() = Some(child);
            let port = primary_port(c);
            let _ = wait_for_port(port, Duration::from_secs(15));
        }
    }

    let tunnel_for_event = tunnel.clone();

    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![open_url])
        .setup(|app| {
            // 启动自动弹 DevTools。tauri crate 的 devtools feature 已启用，
            // open_devtools() 方法在 release build 也可用。
            // (之前用 #[cfg(feature = "devtools")] 是错的——那是 tauri crate
            //  的 feature，不是 fiona-desktop crate 的，cfg 永远 false。)
            if let Some(window) = app.get_webview_window("main") {
                window.open_devtools();
            }
            Ok(())
        })
        .on_window_event(move |_window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                if let Ok(mut guard) = tunnel_for_event.lock() {
                    if let Some(c) = guard.as_mut() {
                        let _ = c.kill();
                        let _ = c.wait();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
