// 跨环境打开外部 URL。
//
// Tauri WebView 没有"新 tab"概念，<a target="_blank"> 默认被吞，
// 且 window.open(url, "_blank") 会被解释成 location.replace 替换主界面。
// 改成调 Rust 端的自定义 open_url 命令（lib.rs 里定义，cmd/open/xdg-open 调系统打开）。

function isTauri(): boolean {
  const w = window as any;
  return !!(w.__TAURI_INTERNALS__?.invoke || w.__TAURI__?.core?.invoke || w.__TAURI__?.invoke);
}

async function tauriInvoke(cmd: string, args: Record<string, unknown>): Promise<{ ok: true } | { ok: false; errors: string[] }> {
  const w = window as any;
  const bridges: Array<{ name: string; fn: any }> = [];
  if (w.__TAURI_INTERNALS__?.invoke) bridges.push({ name: "INTERNALS", fn: w.__TAURI_INTERNALS__.invoke.bind(w.__TAURI_INTERNALS__) });
  if (w.__TAURI__?.core?.invoke) bridges.push({ name: "TAURI.core", fn: w.__TAURI__.core.invoke.bind(w.__TAURI__.core) });
  if (w.__TAURI__?.invoke) bridges.push({ name: "TAURI", fn: w.__TAURI__.invoke.bind(w.__TAURI__) });

  const errors: string[] = [];
  for (const b of bridges) {
    try {
      await b.fn(cmd, args);
      return { ok: true };
    } catch (e) {
      errors.push(`${b.name}: ${String(e).slice(0, 300)}`);
    }
  }
  return { ok: false, errors };
}

export async function openExternal(url: string): Promise<void> {
  if (typeof window === "undefined" || !url) return;

  if (!isTauri()) {
    // 浏览器环境：标准新窗口
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }

  // Tauri 环境：调 Rust 端 open_url（自定义命令，不走 plugin ACL）
  const r = await tauriInvoke("open_url", { url });
  if (!r.ok) {
    // 失败时绝对不能 fallback 到 window.open（Tauri webview 里会 location.replace 主界面）
    console.error(
      "[openExternal] open_url failed.\nErrors:\n  " +
      r.errors.join("\n  ") +
      "\nURL: " + url,
    );
  }
}
