const TOKEN_KEY   = "fiona_token";
const USER_KEY    = "fiona_user";
const BALANCE_KEY = "fiona_balance";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUsername(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(USER_KEY) || "";
}

export function getBalance(): number {
  if (typeof window === "undefined") return 0;
  return parseInt(localStorage.getItem(BALANCE_KEY) || "0", 10);
}

export function setAuth(token: string, username: string, balance: number) {
  localStorage.setItem(TOKEN_KEY,   token);
  localStorage.setItem(USER_KEY,    username);
  localStorage.setItem(BALANCE_KEY, String(balance));
  // cookie 供 middleware 读取。寿命对齐后端 JWT（30 天），否则 cookie 提前过期会
  // 让 proxy 路由门禁误判未登录、同源 <img>/<audio> 媒体鉴权失效，而 localStorage
  // 里的 token 仍有效。HTTPS 下加 Secure（dev 走 http 不能加，否则浏览器丢弃 cookie）。
  const secure =
    typeof window !== "undefined" && window.location.protocol === "https:"
      ? "; Secure"
      : "";
  document.cookie = `fiona_token=${token}; path=/; max-age=${60 * 60 * 24 * 30}; SameSite=Lax${secure}`;
  // 通知监听者（TopBar 等）身份变了
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("fiona-user-changed"));
  }
}

export function updateBalance(balance: number) {
  localStorage.setItem(BALANCE_KEY, String(balance));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(BALANCE_KEY);
  document.cookie = "fiona_token=; path=/; max-age=0";
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

// ── 带鉴权头的 fetch ─────────────────────────────────────────────
// 优先发 Authorization: Bearer <jwt>；dev（无 token）退化为 X-Dev-User
// 后端 auth_dep.get_current_user 也对称：JWT > X-Dev-User（DEV_MODE=1）> 401
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers || {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else if (typeof window !== "undefined") {
    // dev 兜底：未登录但 localStorage 里有 fiona_user，给后端走 DEV_MODE 通道
    // HTTP header 值只能是 ISO-8859-1，中文用户名必须 encodeURIComponent；后端 unquote 还原
    const user = getUsername();
    if (user) headers.set("X-Dev-User", encodeURIComponent(user));
  }
  return fetch(input, { ...init, headers });
}
