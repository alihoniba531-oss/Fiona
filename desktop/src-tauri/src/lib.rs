// 桌面壳 + 嵌入式 SSH 隧道 + 自定义 open_url 命令。
//
// 启动流程：
//   1. 读 desktop/fiona.config.json（云 IP / 用户 / 转发规则）
//   2. spawn `ssh -N -L ...` 子进程做端口转发；stderr 重定向到 ssh.log
//   3. 轮询 localhost:<主端口> 直到通（最长 15 秒）
//   4. 启动 Tauri 窗口，加载 devUrl
//   5. 关窗时 kill 隧道子进程
//
// 全程把诊断（config 路径 / ssh pid / 端口就绪 / 耗时 / 备注）写进全局 StartupReport
// 和 %APPDATA%\fiona\startup.log，前端可 invoke("startup_diagnostics") 拿来展示。

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
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

#[derive(Clone, Default, Serialize)]
struct StartupReport {
    config_path: Option<String>,
    config_loaded: bool,
    primary_port: u16,
    ssh_pid: Option<u32>,
    ssh_log_path: Option<String>,
    port_ready: bool,
    elapsed_ms: u128,
    notes: Vec<String>,
}

static STARTUP_REPORT: OnceLock<Mutex<StartupReport>> = OnceLock::new();

fn report() -> &'static Mutex<StartupReport> {
    STARTUP_REPORT.get_or_init(|| Mutex::new(StartupReport::default()))
}

fn add_note(s: impl Into<String>) {
    if let Ok(mut r) = report().lock() {
        r.notes.push(s.into());
    }
}

fn fiona_data_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            return Some(PathBuf::from(appdata).join("fiona"));
        }
    }
    #[cfg(not(windows))]
    {
        if let Some(home) = std::env::var_os("HOME") {
            return Some(PathBuf::from(home).join(".config").join("fiona"));
        }
    }
    None
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

fn load_config_from(p: &PathBuf) -> Option<CloudConfig> {
    let txt = match std::fs::read_to_string(p) {
        Ok(t) => t,
        Err(e) => {
            add_note(format!("config 读取失败: {}", e));
            return None;
        }
    };
    match serde_json::from_str::<CloudConfig>(&txt) {
        Ok(c) => Some(c),
        Err(e) => {
            add_note(format!("config 解析失败: {}", e));
            None
        }
    }
}

fn spawn_tunnel(cfg: &CloudConfig) -> Option<Child> {
    // stderr 接到 ssh.log，下次启动覆盖。Truncate 是故意的——只关心本次故障原因。
    let log_path = fiona_data_dir().map(|d| d.join("ssh.log"));
    if let Some(ref p) = log_path {
        if let Some(parent) = p.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        if let Ok(mut r) = report().lock() {
            r.ssh_log_path = Some(p.display().to_string());
        }
    }
    let stderr_target: Stdio = match log_path.as_ref().and_then(|p| std::fs::File::create(p).ok()) {
        Some(f) => Stdio::from(f),
        None => {
            add_note("ssh.log 无法创建，stderr 将被丢弃");
            Stdio::null()
        }
    };

    let mut cmd = Command::new("ssh");
    cmd.arg("-N")
        .arg("-v")                                  // verbose，让 ssh.log 信息更足
        .arg("-o").arg("BatchMode=yes")             // 不交互问密码——必须配过免密
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
    cmd.stdout(Stdio::null()).stderr(stderr_target);
    match cmd.spawn() {
        Ok(c) => Some(c),
        Err(e) => {
            add_note(format!("ssh 进程启动失败（系统是否装了 ssh？）: {}", e));
            None
        }
    }
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

fn write_startup_log() {
    let Some(dir) = fiona_data_dir() else { return };
    let _ = std::fs::create_dir_all(&dir);
    let Ok(r) = report().lock() else { return };
    let text = format!(
        "config_path:   {}\n\
         config_loaded: {}\n\
         primary_port:  {}\n\
         ssh_pid:       {}\n\
         ssh_log_path:  {}\n\
         port_ready:    {}\n\
         elapsed_ms:    {}\n\
         notes:\n  {}\n",
        r.config_path.as_deref().unwrap_or("(none)"),
        r.config_loaded,
        r.primary_port,
        r.ssh_pid.map(|p| p.to_string()).unwrap_or_else(|| "(none)".into()),
        r.ssh_log_path.as_deref().unwrap_or("(none)"),
        r.port_ready,
        r.elapsed_ms,
        if r.notes.is_empty() { "(none)".to_string() } else { r.notes.join("\n  ") },
    );
    let _ = std::fs::write(dir.join("startup.log"), text);
}

/// 用系统默认应用打开 URL（备用：用户想跳外部浏览器时用）
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

/// 在 Chloe 内置子窗口打开 URL（不是 iframe，不受 X-Frame-Options 拦截）
/// 体验：弹一个独立窗口仍属于 Chloe 应用，用户关掉就回主窗口
#[tauri::command]
async fn open_url_in_app(app: tauri::AppHandle, url: String) -> Result<(), String> {
    use tauri::{WebviewWindowBuilder, WebviewUrl, Url};

    let parsed: Url = url.parse().map_err(|e: url::ParseError| format!("invalid URL: {}", e))?;

    // label 必须唯一且只含 ASCII 字符
    // 用时间戳保证唯一（同一 URL 多次打开也独立窗口）
    let label = format!("ext_{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0)
    );

    WebviewWindowBuilder::new(&app, &label, WebviewUrl::External(parsed))
        .title("外部页面 · Chloe")
        .inner_size(1100.0, 750.0)
        .min_inner_size(600.0, 400.0)
        .resizable(true)
        .build()
        .map_err(|e| format!("build window: {}", e))?;

    Ok(())
}

/// 把启动诊断给前端，用于"加载菲欧娜中..."卡住时展示故障原因
#[tauri::command]
fn startup_diagnostics() -> StartupReport {
    report().lock().map(|r| r.clone()).unwrap_or_default()
}

/// 实时 TCP 探测 127.0.0.1:port——前端轮询，比 fetch 更轻、不会被 Service Worker 缓存搅扰
#[tauri::command]
fn probe_backend(port: u16) -> bool {
    let addr = match format!("127.0.0.1:{}", port).parse() {
        Ok(a) => a,
        Err(_) => return false,
    };
    TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok()
}

/// 用资源管理器/Finder 打开 fiona 数据目录（startup.log + ssh.log 都在里面）
#[tauri::command]
fn open_logs_dir() -> Result<String, String> {
    let dir = fiona_data_dir().ok_or_else(|| "无法确定数据目录（APPDATA / HOME 都没有）".to_string())?;
    let _ = std::fs::create_dir_all(&dir);
    let path_str = dir.display().to_string();
    #[cfg(target_os = "windows")]
    Command::new("explorer").arg(&path_str).spawn().map_err(|e| e.to_string())?;
    #[cfg(target_os = "macos")]
    Command::new("open").arg(&path_str).spawn().map_err(|e| e.to_string())?;
    #[cfg(target_os = "linux")]
    Command::new("xdg-open").arg(&path_str).spawn().map_err(|e| e.to_string())?;
    Ok(path_str)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let start_time = Instant::now();

    let cfg_path = find_config();
    if let Ok(mut r) = report().lock() {
        r.config_path = cfg_path.as_ref().map(|p| p.display().to_string());
    }
    if cfg_path.is_none() {
        add_note("未找到 fiona.config.json（请放到 %APPDATA%\\fiona\\config.json，或可执行文件同级）");
    }

    let cfg = cfg_path.as_ref().and_then(load_config_from);
    if let Some(ref c) = cfg {
        if let Ok(mut r) = report().lock() {
            r.config_loaded = true;
            r.primary_port = primary_port(c);
        }
    }

    let tunnel: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));

    if let Some(ref c) = cfg {
        if let Some(child) = spawn_tunnel(c) {
            if let Ok(mut r) = report().lock() {
                r.ssh_pid = Some(child.id());
            }
            *tunnel.lock().unwrap() = Some(child);
            let port = primary_port(c);
            let ok = wait_for_port(port, Duration::from_secs(15));
            if let Ok(mut r) = report().lock() {
                r.port_ready = ok;
            }
            if !ok {
                add_note(format!(
                    "15s 内 localhost:{} 仍未就绪——隧道可能已退出（看 ssh.log），\
                     或云端 3000 没真的起在 127.0.0.1",
                    port
                ));
            }
        }
    }

    if let Ok(mut r) = report().lock() {
        r.elapsed_ms = start_time.elapsed().as_millis();
    }
    write_startup_log();

    let tunnel_for_event = tunnel.clone();

    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            open_url,
            open_url_in_app,
            startup_diagnostics,
            probe_backend,
            open_logs_dir
        ])
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
