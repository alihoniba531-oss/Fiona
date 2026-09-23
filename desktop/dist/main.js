// 隧道由 Rust 端在窗口出现前已建好；这里先 probe，通了就跳，
// 没通就展示诊断（避免 webview 一直黑屏 + ERR_CONNECTION_REFUSED）。
const PUBLIC_TARGET = "https://madchloechat.online";
const POLL_INTERVAL = 500;
const POLL_TIMEOUT = 15000;

function getInvoke() {
  const w = window;
  if (w.__TAURI_INTERNALS__ && w.__TAURI_INTERNALS__.invoke) {
    return w.__TAURI_INTERNALS__.invoke.bind(w.__TAURI_INTERNALS__);
  }
  if (w.__TAURI__ && w.__TAURI__.core && w.__TAURI__.core.invoke) {
    return w.__TAURI__.core.invoke.bind(w.__TAURI__.core);
  }
  if (w.__TAURI__ && w.__TAURI__.invoke) {
    return w.__TAURI__.invoke.bind(w.__TAURI__);
  }
  return null;
}

async function probeReady(port, localTarget) {
  // 优先用 Rust 的 HTTP probe（更可靠）；没桥就 fallback fetch
  const invoke = getInvoke();
  if (invoke) {
    try { return await invoke("probe_backend", { port }); }
    catch (_) { /* fall through */ }
  }
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const res = await fetch(localTarget + "/", { method: "GET", cache: "no-store", signal: ctrl.signal });
    clearTimeout(t);
    return res.status < 500;
  } catch { return false; }
}

async function getDiag() {
  const invoke = getInvoke();
  if (!invoke) return null;
  try { return await invoke("startup_diagnostics"); } catch (_) { return null; }
}

async function waitAndRedirect() {
  const diag = await getDiag();

  // 用户模式：不给内测者发 fiona.config.json。无配置时不建 SSH 隧道，
  // 直接进入公网同源部署；有配置才按开发者模式等 localhost 隧道。
  if (diag && !diag.config_path && !diag.config_loaded) {
    window.location.replace(PUBLIC_TARGET);
    return;
  }

  const port = (diag && diag.primary_port) || 3000;
  const localTarget = "http://localhost:" + port;

  const start = Date.now();
  while (Date.now() - start < POLL_TIMEOUT) {
    if (await probeReady(port, localTarget)) {
      window.location.replace(localTarget);
      return;
    }
    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL));
  }
  await showError();
}

function formatDiag(d) {
  if (!d) return "（无法读取诊断——Tauri invoke 不可用）";
  const lines = [
    "config 路径:     " + (d.config_path || "(未找到)"),
    "config 已加载:   " + (d.config_loaded ? "是" : "否"),
    "本地转发端口:    " + (d.primary_port || 3000),
    "SSH 隧道 PID:    " + (d.ssh_pid != null ? d.ssh_pid : "(未启动)"),
    "端口就绪:        " + (d.port_ready ? "是" : "否"),
    "启动耗时:        " + (d.elapsed_ms || 0) + " ms",
    "ssh.log 路径:    " + (d.ssh_log_path || "(无)"),
  ];
  if (d.notes && d.notes.length) {
    lines.push("");
    lines.push("备注:");
    d.notes.forEach(note => lines.push("  • " + note));
  }
  return lines.join("\n");
}

function inferReason(d) {
  if (!d) return "无法连接到云端（127.0.0.1:3000），且诊断不可读。";
  if (!d.config_loaded) {
    return "检测到配置文件但无法解析 fiona.config.json——请检查 JSON 格式，或删除配置文件进入公网用户模式。";
  }
  if (d.ssh_pid == null) {
    return "SSH 进程未能启动——这台机器可能没装 ssh，或 PATH 里找不到。";
  }
  if (!d.port_ready) {
    return "SSH 已启动但 15 秒内 127.0.0.1:" + d.primary_port + " 仍未就绪——\n隧道很可能立即退出了（看 ssh.log），常见原因：免密钥失效 / host key 变化 / 本机端口被占。";
  }
  return "未知原因——请把 startup.log 和 ssh.log 发出来。";
}

async function showError() {
  const d = await getDiag();
  document.getElementById("loading").hidden = true;
  document.getElementById("err").hidden = false;
  document.getElementById("reason").textContent = inferReason(d);
  document.getElementById("diag").textContent = formatDiag(d);
}

async function retry() {
  document.getElementById("err").hidden = true;
  document.getElementById("loading").hidden = false;
  await waitAndRedirect();
}

async function openLogs() {
  const invoke = getInvoke();
  if (!invoke) { alert("Tauri invoke 不可用"); return; }
  try { await invoke("open_logs_dir"); }
  catch (error) { alert("打开失败: " + error); }
}

document.getElementById("retry-btn").addEventListener("click", retry);
document.getElementById("open-logs-btn").addEventListener("click", openLogs);
waitAndRedirect();
