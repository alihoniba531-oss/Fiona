// 桌面壳 + 嵌入式 SSH 隧道。
// 启动流程：
//   1. 读 desktop/fiona.config.json（云 IP / 用户 / 转发规则）
//   2. spawn `ssh -N -L ...` 子进程做端口转发
//   3. 轮询 localhost:<主端口> 直到通（最长 15 秒）
//   4. 启动 Tauri 窗口，加载 devUrl
//   5. 关窗时 kill 隧道子进程
// 配置缺失时跳过隧道，直接加载 localhost:3000（兼容已手动转发的场景）。

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;

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
    // prod：可执行文件同级或上一级
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
