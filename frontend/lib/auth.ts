const USER_KEY    = "fiona_user";
const BALANCE_KEY = "fiona_balance";
let authRedirectStarted = false;

export function getUsername(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(USER_KEY) || "";
}

export function getBalance(): number {
  if (typeof window === "undefined") return 0;
  return parseInt(localStorage.getItem(BALANCE_KEY) || "0", 10);
}

export function setAuth(username: string, balance: number) {
  localStorage.setItem(USER_KEY,    username);
  localStorage.setItem(BALANCE_KEY, String(balance));
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
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
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
  if (response.status === 401 && typeof window !== "undefined" && !authRedirectStarted) {
    authRedirectStarted = true;
    clearAuth();
    const target = window.top ?? window;
    try {
      target.location.replace("/login?reason=expired");
    } catch {
      window.location.replace("/login?reason=expired");
    }
  }

  return response;
}
