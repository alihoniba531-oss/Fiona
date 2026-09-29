import { API_BASE as API } from "@/lib/config";

const USER_KEY    = "fiona_user";
const BALANCE_KEY = "fiona_balance";
let authRedirectStarted = false;
let identityRecoveryAttempted = false;
let identityRecovery: Promise<string> | null = null;
let identityVersion = 0;
const DIRECT_IDENTITY_ROUTES = new Set(["/history", "/match", "/profile"]);
const RELOAD_IDENTITY_ROUTES = new Set(["/match", "/profile"]);
const IDENTITY_RELOAD_KEY = "fiona_identity_reload";

function isDirectIdentityRoute(): boolean {
  return typeof window !== "undefined"
    && DIRECT_IDENTITY_ROUTES.has(window.location.pathname)
    && new URLSearchParams(window.location.search).get("embed") !== "1";
}

function reloadDirectIdentityRoute(username: string) {
  if (!isDirectIdentityRoute()) return;
  if (window.location.pathname === "/history") {
    const url = new URL(window.location.href);
    if (url.searchParams.has("user") && url.searchParams.get("user") !== username) {
      url.searchParams.delete("user");
      window.location.replace(url.toString());
    }
    return;
  }
  if (!RELOAD_IDENTITY_ROUTES.has(window.location.pathname)) return;
  try {
    if (sessionStorage.getItem(IDENTITY_RELOAD_KEY) === username) return;
    sessionStorage.setItem(IDENTITY_RELOAD_KEY, username);
  } catch { /* Local storage is already confirmed available; a reload remains safe. */ }
  window.location.reload();
}

function redirectExpiredSession() {
  if (typeof window === "undefined" || authRedirectStarted) return;
  authRedirectStarted = true;
  clearAuth();
  const target = window.top ?? window;
  try {
    target.location.replace("/login?reason=expired");
  } catch {
    window.location.replace("/login?reason=expired");
  }
}

export function ensureAccountIdentity(): Promise<string> {
  if (typeof window === "undefined") return Promise.resolve("");
  const stored = localStorage.getItem(USER_KEY) || "";
  if (stored) return Promise.resolve(stored);
  if (identityRecovery) return identityRecovery;
  if (identityRecoveryAttempted || window.location.pathname === "/login") return Promise.resolve("");
  identityRecoveryAttempted = true;
  const version = identityVersion;
  identityRecovery = fetch(`${API}/profile`, { credentials: "include" })
    .then(async response => {
      if (version !== identityVersion) return "";
      if (response.status === 401) {
        redirectExpiredSession();
        return "";
      }
      if (!response.ok) return "";
      const data = await response.json();
      if (version !== identityVersion) return "";
      const username = typeof data.username === "string" ? data.username.trim() : "";
      if (username && !localStorage.getItem(USER_KEY) && !authRedirectStarted) {
        localStorage.setItem(USER_KEY, username);
        window.dispatchEvent(new Event("fiona-user-changed"));
        reloadDirectIdentityRoute(username);
      }
      return localStorage.getItem(USER_KEY) || "";
    })
    .catch(() => "")
    .finally(() => { identityRecovery = null; });
  return identityRecovery;
}

export function getUsername(): string {
  if (typeof window === "undefined") return "";
  const username = localStorage.getItem(USER_KEY) || "";
  if (username && !identityRecoveryAttempted) {
    try { sessionStorage.removeItem(IDENTITY_RELOAD_KEY); } catch {}
  }
  if (!username && !identityRecoveryAttempted) {
    queueMicrotask(() => { void ensureAccountIdentity(); });
  }
  return username;
}

export function getBalance(): number {
  if (typeof window === "undefined") return 0;
  return parseInt(localStorage.getItem(BALANCE_KEY) || "0", 10);
}

export function setAuth(username: string, balance: number) {
  identityVersion += 1;
  try { sessionStorage.removeItem(IDENTITY_RELOAD_KEY); } catch {}
  localStorage.setItem(USER_KEY,    username);
  localStorage.setItem(BALANCE_KEY, String(balance));
  authRedirectStarted = false;
  identityRecoveryAttempted = false;
  // JWT 由后端写入 HttpOnly Cookie，前端 JavaScript 不再读取或持久化 token。
  // 通知监听者（TopBar 等）身份变了
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("fiona-user-changed"));
  }
}

export function updateBalance(balance: number) {
  localStorage.setItem(BALANCE_KEY, String(balance));
}

export function clearAuth() {
  if (typeof window === "undefined") return;
  identityVersion += 1;
  identityRecoveryAttempted = true;
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(BALANCE_KEY);
  // 清理由旧版本前端写入的非 HttpOnly cookie；新会话 Cookie 必须由后端
  // /auth/logout、/account 或 401 响应清除。
  document.cookie = "fiona_token=; path=/; max-age=0";
  window.dispatchEvent(new Event("fiona-user-changed"));
}

export function isLoggedIn(): boolean {
  return !!getUsername();
}

// ── 带鉴权头的 fetch ─────────────────────────────────────────────
// 浏览器自动携带后端设置的 HttpOnly Cookie；dev 无 Cookie 时才退化为 X-Dev-User。
export async function apiFetch(
  input: string,
  init: RequestInit = {},
  options: { redirectOnUnauthorized?: boolean } = {},
): Promise<Response> {
  // Legacy direct routes read localStorage only at mount. Recover the cookie
  // identity before their data request, then reload them with that identity.
  if (isDirectIdentityRoute() && !localStorage.getItem(USER_KEY)) {
    await ensureAccountIdentity();
  }
  const headers = new Headers(init.headers || {});
  if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
    // dev 兜底：未登录但 localStorage 里有 fiona_user，给后端走 DEV_MODE 通道
    // HTTP header 值只能是 ISO-8859-1，中文用户名必须 encodeURIComponent；后端 unquote 还原
    const user = getUsername();
    if (user) headers.set("X-Dev-User", encodeURIComponent(user));
  }
  const response = await fetch(input, { ...init, headers, credentials: "include" });

  // Cookie 门禁只能判断 token 是否存在；真正的过期/撤销结果以后端 401 为准。
  // 抽屉页面运行在同源 iframe 中，因此需要让顶层窗口回到登录页，避免只在
  // 不可见的 iframe 内跳转。replace 也防止“后退”再次进入已失效的受保护页。
  if (response.status === 401 && options.redirectOnUnauthorized !== false) {
    redirectExpiredSession();
  }

  return response;
}
