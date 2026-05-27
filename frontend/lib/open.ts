// 跨环境打开外部 URL。
//
// Tauri WebView 没有"新 tab"概念，<a target="_blank"> 默认被吞，
// 且 window.open(url, "_blank") 会被解释成 location.replace 替换主界面。
//
// 默认行为：openExternal(url) → Tauri 弹子窗口（内置 webview 浏览，不跳系统浏览器）
// 备用：openInBrowser(url) → 调系统默认浏览器（旧 open_url 命令保留）

type TauriInvoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
type TauriWindow = Window & {
  __TAURI_INTERNALS__?: { invoke?: TauriInvoke };
  __TAURI__?: {
    core?: { invoke?: TauriInvoke };
    invoke?: TauriInvoke;
  };
};

function isTauri(): boolean {
  const w = window as TauriWindow;
  return !!(w.__TAURI_INTERNALS__?.invoke || w.__TAURI__?.core?.invoke || w.__TAURI__?.invoke);
}

async function tauriInvoke(cmd: string, args: Record<string, unknown>): Promise<{ ok: true } | { ok: false; errors: string[] }> {
  const w = window as TauriWindow;
  const bridges: Array<{ name: string; fn: TauriInvoke }> = [];
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

/**
 * 在 Chloe 内置子窗口打开 URL（默认行为）。
 * Tauri 子窗口不是 iframe，不受 X-Frame-Options 拦截，能加载几乎所有网站。
 */
export async function openExternal(url: string): Promise<void> {
  if (typeof window === "undefined" || !url) return;

  if (!isTauri()) {
    // 浏览器环境（PWA 或网页直接打开）：标准新标签
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }

  const r = await tauriInvoke("open_url_in_app", { url });
  if (!r.ok) {
    console.error(
      "[openExternal] open_url_in_app failed.\nErrors:\n  " +
      r.errors.join("\n  ") +
      "\nURL: " + url,
    );
  }
}

/**
 * 在系统默认浏览器打开 URL（备用，如果某场景明确要跳外部时调）。
 */
export async function openInBrowser(url: string): Promise<void> {
  if (typeof window === "undefined" || !url) return;
  if (!isTauri()) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  const r = await tauriInvoke("open_url", { url });
  if (!r.ok) {
    console.error("[openInBrowser] open_url failed: " + r.errors.join(" | "));
  }
}
