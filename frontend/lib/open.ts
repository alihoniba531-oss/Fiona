// 跨环境打开外部 URL。
//
// Tauri WebView 没有"新 tab"概念，<a target="_blank"> 默认被吞，
// 且 window.open(url, "_blank") 会被解释成 location.replace 替换主界面。
// 改成调 Rust 端的自定义 open_url 命令（lib.rs 里定义，cmd/open/xdg-open 调系统打开）。

function isTauri(): boolean {
  const w = window as any;
  return !!(w.__TAURI_INTERNALS__?.invoke || w.__TAURI__?.core?.invoke || w.__TAURI__?.invoke);
}

async function tauriInvoke(cmd: string, args: Record<string, unknown>): Promise<boolean> {
  const w = window as any;
  const bridges: any[] = [
    w.__TAURI_INTERNALS__?.invoke?.bind(w.__TAURI_INTERNALS__),
    w.__TAURI__?.core?.invoke?.bind(w.__TAURI__.core),
    w.__TAURI__?.invoke?.bind(w.__TAURI__),
  ].filter(Boolean);

  for (const invoke of bridges) {
    try {
      await invoke(cmd, args);
      return true;
    } catch (e) {
      console.warn(`[openExternal] invoke ${cmd} failed:`, e);
    }
  }
  return false;
}

export async function openExternal(url: string): Promise<void> {
  if (typeof window === "undefined" || !url) return;

  if (!isTauri()) {
    // 浏览器环境：标准新窗口
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }

  // Tauri 环境：调 Rust 端 open_url（自定义命令，不走 plugin ACL）
  const ok = await tauriInvoke("open_url", { url });
  if (!ok) {
    // 失败时绝对不能 fallback 到 window.open（Tauri webview 里会 location.replace 主界面）
    console.error("[openExternal] open_url command failed. URL:", url);
  }
}
