// 跨环境打开外部 URL —— web 用 window.open，Tauri 走 plugin-opener。
//
// Tauri WebView 没有"新 tab"概念，<a target="_blank"> 默认被吞。
// Tauri 2 通过 plugin-opener 的内置 invoke 调系统默认浏览器打开。
// 不依赖 npm 包：用 webview 注入的全局桥直接发 IPC。
//
// Tauri 2 桥的命名因版本/配置有差异，试多个路径兜底。

async function tauriInvoke(cmd: string, args: Record<string, unknown>): Promise<boolean> {
  const w = window as any;
  // Tauri 2 internal bridge（最常见）
  if (w.__TAURI_INTERNALS__?.invoke) {
    try {
      await w.__TAURI_INTERNALS__.invoke(cmd, args);
      return true;
    } catch (e) {
      console.warn(`[openExternal] __TAURI_INTERNALS__.invoke ${cmd} failed:`, e);
    }
  }
  // Tauri 2 with globalTauri=true
  if (w.__TAURI__?.core?.invoke) {
    try {
      await w.__TAURI__.core.invoke(cmd, args);
      return true;
    } catch (e) {
      console.warn(`[openExternal] __TAURI__.core.invoke ${cmd} failed:`, e);
    }
  }
  // Tauri 1 legacy
  if (w.__TAURI__?.invoke) {
    try {
      await w.__TAURI__.invoke(cmd, args);
      return true;
    } catch (e) {
      console.warn(`[openExternal] __TAURI__.invoke ${cmd} failed:`, e);
    }
  }
  return false;
}

export async function openExternal(url: string): Promise<void> {
  if (typeof window === "undefined" || !url) return;
  const ok = await tauriInvoke("plugin:opener|open_url", { url });
  if (ok) return;
  // 浏览器或 Tauri 调用失败：fallback 到 window.open
  window.open(url, "_blank", "noopener,noreferrer");
}
