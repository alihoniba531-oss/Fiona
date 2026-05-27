// 后端地址统一来源。
//
// 开发（next dev）：不设 NEXT_PUBLIC_API_BASE，API_BASE 回退到相对 "/api"，
//   走 next.config 的 rewrite 代理到 localhost:8000，本机行为完全不变。
// 打包（next build）：设 NEXT_PUBLIC_API_BASE=https://api.madchloechat.online，
//   build 时内联成绝对地址，桌面静态包直连公网后端。
//
// 注意：NEXT_PUBLIC_ 变量在 build 时内联，必须直接引用 process.env.NEXT_PUBLIC_API_BASE，
// 不能动态取键（process.env[x] / 解构都不会被内联）。

const RAW_BASE = (process.env.NEXT_PUBLIC_API_BASE || "").trim().replace(/\/+$/, "");

// HTTP / fetch 用
export const API_BASE = RAW_BASE || "/api";

// WebSocket 用：有绝对地址就 http→ws / https→wss；否则按当前页面 host 推（保持 dev 行为）
export const WS_BASE = RAW_BASE
  ? RAW_BASE.replace(/^http/, "ws")
  : typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/api`
    : "";
