// 跨环境打开外部 URL —— web 用 window.open，Tauri 走 plugin-opener。
//
// Tauri WebView 没有"新 tab"概念，<a target="_blank"> 默认被吞。
// Tauri 2 通过 plugin-opener 的内置 invoke 调系统默认浏览器打开。
// 不依赖 npm 包：用 webview 注入的全局桥直接发 IPC。

function bridgeStatus(): Record<string, boolean> {
  const w = window as any;
  return {
    __TAURI_INTERNALS__: !!w.__TAURI_INTERNALS__,
    "__TAURI_INTERNALS__.invoke": !!w.__TAURI_INTERNALS__?.invoke,
    __TAURI__: !!w.__TAURI__,
    "__TAURI__.core.invoke": !!w.__TAURI__?.core?.invoke,
    "__TAURI__.invoke": !!w.__TAURI__?.invoke,
  };
}

async function tryInvoke(
  bridge: any,
  cmd: string,
  args: Record<string, unknown>,
): Promise<{ ok: true } | { ok: false; err: unknown }> {
  try {
    await bridge(cmd, args);
    return { ok: true };
  } catch (err) {
    return { ok: false, err };
  }
}

function isTauri(): boolean {
  const s = bridgeStatus();
  return s["__TAURI_INTERNALS__.invoke"] || s["__TAURI__.core.invoke"] || s["__TAURI__.invoke"];
}

export async function openExternal(url: string): Promise<void> {
  if (typeof window === "undefined" || !url) return;

  if (!isTauri()) {
    // 浏览器环境：标准新窗口
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }

  // Tauri 环境：试多个桥 + 多个命令名
  const w = window as any;
  const bridges: Array<{ name: string; fn: any }> = [];
  if (w.__TAURI_INTERNALS__?.invoke) {
    bridges.push({ name: "__TAURI_INTERNALS__", fn: w.__TAURI_INTERNALS__.invoke.bind(w.__TAURI_INTERNALS__) });
  }
  if (w.__TAURI__?.core?.invoke) {
    bridges.push({ name: "__TAURI__.core", fn: w.__TAURI__.core.invoke.bind(w.__TAURI__.core) });
  }
  if (w.__TAURI__?.invoke) {
    bridges.push({ name: "__TAURI__", fn: w.__TAURI__.invoke.bind(w.__TAURI__) });
  }

  // plugin-opener 的命令名在 Tauri 2 各版本里可能略有差异，都试
  const cmdVariants: Array<{ cmd: string; args: Record<string, unknown> }> = [
    { cmd: "plugin:opener|open_url", args: { url } },
    { cmd: "plugin:opener|open_url", args: { url, with: null } },
    { cmd: "plugin:opener|openUrl", args: { url } },
  ];

  const attempts: string[] = [];
  for (const b of bridges) {
    for (const v of cmdVariants) {
      const r = await tryInvoke(b.fn, v.cmd, v.args);
      if (r.ok) return;
      attempts.push(`${b.name} ${v.cmd}: ${String(r.err).slice(0, 200)}`);
    }
  }

  // 全失败，给完整诊断（绝对不 fallback 到 window.open，会替换主界面）
  console.error(
    "[openExternal] all Tauri invoke attempts failed.\n" +
    "Bridges available: " + JSON.stringify(bridgeStatus()) + "\n" +
    "Attempts:\n  " + attempts.join("\n  ") + "\n" +
    "URL: " + url,
  );
}
