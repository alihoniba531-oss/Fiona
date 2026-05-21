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
  // cookie 供 middleware 读取（7天）
  document.cookie = `fiona_token=${token}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
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
