// 跨环境打开外部 URL —— web 用 window.open，Tauri 走 plugin-opener。
//
// Tauri WebView 没有"新 tab"概念，<a target="_blank"> 默认被吞。
// Tauri 2 通过 plugin-opener 的内置 invoke 调系统默认浏览器打开。
// 不依赖 npm 包：用全局 __TAURI_INTERNALS__ 直接发 IPC，前端无需 install。

export async function openExternal(url: string): Promise<void> {
  if (typeof window === "undefined" || !url) return;

  // Tauri 环境检测：__TAURI_INTERNALS__ 是 webview 注入的内部桥
  const internals = (window as any).__TAURI_INTERNALS__;
  if (internals && typeof internals.invoke === "function") {
    try {
      await internals.invoke("plugin:opener|open_url", { url });
      return;
    } catch (e) {
      // 没接 plugin / 权限缺失 → 静默 fallback 到 window.open
      console.warn("[openExternal] tauri invoke failed, fallback:", e);
    }
  }

  // 浏览器：标准新窗口/新标签
  window.open(url, "_blank", "noopener,noreferrer");
}
