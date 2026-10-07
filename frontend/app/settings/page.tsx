"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { Trash2, LogOut } from "lucide-react";
import Glaze from "@/components/Glaze";
import InkLandscape from "@/components/InkLandscape";
import { useTheme } from "@/lib/useTheme";
import { apiFetch, clearAuth, setAuth } from "@/lib/auth";
import { useAccountIdentity } from "@/lib/useAccountIdentity";

import { API_BASE as API } from "@/lib/config";

const appearanceOptions = [
  { value: "system", label: "跟随系统" },
  { value: "day", label: "昼　天青" },
  { value: "night", label: "夜　建盏" },
] as const;

function SettingsContent() {
  const sp = useSearchParams();
  const embedded = sp?.get("embed") === "1";
  const username = useAccountIdentity();
  const { appearance, setAppearance, solid, effectiveSolid, systemSolid, setSolid } = useTheme();
  const [allUsers, setAllUsers] = useState<string[]>([]);
  const [cleared, setCleared] = useState(false);
  const [clearError, setClearError] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");

  useEffect(() => {
    // /users 端点仅在后端 DEV_MODE=1 时开放；prod 直接 404，前端把列表留空即可。
    apiFetch(`${API}/users`).then(r => r.ok ? r.json() : { users: [] }).then(d => setAllUsers(d.users || [])).catch(() => {});
  }, []);

  const switchUser = async (u: string) => {
    if (u === username || process.env.NODE_ENV === "production") return;
    const response = await fetch(`${API}/auth/test-login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u }),
    });
    if (!response.ok) return;
    const data = await response.json();
    setAuth(data.username, data.balance ?? 200);
  };

  const clearHistory = async () => {
    if (!username) return;
    if (!confirm(`确定清空「${username}」的所有聊天记录？此操作不可恢复。`)) return;
    setClearError("");
    try {
      const response = await apiFetch(`${API}/history`, { method: "DELETE" });
      if (!response.ok) {
        setClearError("清空失败，请重试");
        return;
      }
      setCleared(true);
      setTimeout(() => setCleared(false), 3000);
    } catch {
      setClearError("网络错误，请重试");
    }
  };

  const redirectTop = (path: string) => {
    const target = window.top ?? window;
    try {
      target.location.replace(path);
    } catch {
      window.location.replace(path);
    }
  };

  const logout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    setLogoutError("");
    try {
      const response = await apiFetch(
        `${API}/auth/logout`,
        { method: "POST" },
        { redirectOnUnauthorized: false },
      );
      if (response.status === 401) {
        // The server has already rejected this session; there is nothing left
        // to revoke, so remove the stale local identity and show login.
        clearAuth();
        redirectTop("/login?reason=logout");
        return;
      }
      if (!response.ok) {
        setLogoutError("退出失败，会话仍可能有效。请重试。");
        return;
      }
      clearAuth();
      redirectTop("/login?reason=logout");
    } catch {
      setLogoutError("网络错误，退出未完成。请重试。");
    } finally {
      setLoggingOut(false);
    }
  };

  const deleteAccount = async () => {
    if (!username || deleteConfirmation !== username || deleting) return;
    if (!confirm(`将永久删除「${username}」的账号、聊天、画像、匹配、帖子和上传文件。确定继续？`)) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const response = await apiFetch(`${API}/account`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmation: deleteConfirmation }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setDeleteError(data.detail || "删除失败，请重试");
        return;
      }
      if (!data.file_cleanup_complete) {
        alert("账号数据已删除，但有媒体文件需要管理员继续清理。");
      }
      clearAuth();
      redirectTop("/login?reason=deleted");
    } catch {
      setDeleteError("网络错误，请重试");
    } finally {
      setDeleting(false);
    }
  };

  const sectionClass = "grid min-w-0 grid-cols-[160px_minmax(0,1fr)] gap-6 border-t border-[color:var(--carve)] py-[22px] shadow-[inset_0_1px_0_var(--etch)] mobile:grid-cols-1 mobile:gap-3";
  const headingClass = "text-base font-medium tracking-[0.14em]";

  return (
    <div className={`relative flex h-dvh flex-col overflow-hidden ${!embedded ? "mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]" : ""}`}>
      <InkLandscape variant="page" />
      <div className="relative flex min-h-0 flex-1">
        {!embedded && <Sidebar />}
        <main className="flex min-w-0 flex-1 justify-center overflow-x-hidden overflow-y-auto p-3 mobile:p-3">
          <Glaze variant="panel" fur className="relative z-[1] box-border min-h-full w-full max-w-[712px] self-start rounded-[18px] px-12 pb-8 pt-7 mobile:px-6 mobile:pb-6 mobile:pt-5">
            <header>
              <h1 className="mt-[18px] text-[30px] font-medium tracking-[0.24em]">设置</h1>
              <p className="mt-2 text-sm tracking-[0.04em] text-[color:var(--ink2)]">账号、外观与数据。</p>
            </header>

            <section className={`${sectionClass} mt-7`}>
              <h2 className={headingClass}>当前身份</h2>
              <div className="min-w-0 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {(allUsers.length ? allUsers : username ? [username] : []).map(u => (
                    <button key={u} onClick={() => switchUser(u)}
                      className={`chip text-[18px] mobile:h-auto mobile:min-h-10 mobile:max-w-full mobile:break-all mobile:whitespace-normal ${u === username ? "chip-on" : ""}`}>
                      {u}
                    </button>
                  ))}
                  {!username && <span className="text-xs text-[color:var(--ink2)]">正在加载身份…</span>}
                </div>
                <p className="text-[13px] leading-[1.85] text-[color:var(--ink2)]">当前使用服务端 HttpOnly 会话；开发环境仍可切换测试身份。</p>
                <button onClick={logout} disabled={loggingOut}
                  className="btn h-[38px] px-[18px] mobile:h-auto mobile:min-h-10 mobile:max-w-full mobile:break-all mobile:whitespace-normal">
                  <LogOut size={14} />{loggingOut ? "正在退出…" : "退出登录并撤销现有会话"}
                </button>
                {logoutError && <p role="alert" className="text-xs text-[color:var(--seal)]">{logoutError}</p>}
              </div>
            </section>

            <section className={sectionClass}>
              <h2 className={headingClass}>外观</h2>
              <div className="min-w-0">
                <div role="radiogroup" aria-label="外观" className="inline-grid max-w-full grid-cols-3 overflow-hidden rounded-[8px] border border-[color:var(--rule2)]"
                  onKeyDown={event => {
                    const currentIndex = appearanceOptions.findIndex(option => option.value === appearance);
                    const nextIndex = event.key === "ArrowRight" || event.key === "ArrowDown" ? (currentIndex + 1) % 3
                      : event.key === "ArrowLeft" || event.key === "ArrowUp" ? (currentIndex + 2) % 3
                      : event.key === "Home" ? 0 : event.key === "End" ? 2 : -1;
                    if (nextIndex < 0) return;
                    event.preventDefault();
                    setAppearance(appearanceOptions[nextIndex].value);
                    (event.currentTarget.querySelectorAll<HTMLButtonElement>('button[role="radio"]')[nextIndex])?.focus();
                  }}>
                  {appearanceOptions.map((option, index) => <button key={option.value} type="button" role="radio"
                    aria-checked={appearance === option.value} tabIndex={appearance === option.value ? 0 : -1}
                    onClick={() => setAppearance(option.value)}
                    className="min-h-[38px] whitespace-nowrap px-[18px] text-[13px] tracking-[0.08em] outline-offset-[-3px] mobile:min-h-10 mobile:px-2 mobile:tracking-normal"
                    style={{ borderLeft: index ? "1px solid var(--rule2)" : undefined, background: appearance === option.value ? "var(--chip)" : "transparent", color: appearance === option.value ? "var(--ink)" : "var(--ink2)", boxShadow: appearance === option.value ? "inset 0 1px 0 var(--lip), inset 0 -1px 0 var(--lipdk)" : undefined }}>
                    {option.label}
                  </button>)}
                </div>
                <p className="mt-2.5 text-[13px] leading-[1.85] text-[color:var(--ink2)]">白天是汝窑的天青，夜里是建盏的黑釉。选择会记在这台设备上。</p>
                <div className="mt-3.5 border-t border-[color:var(--carve)] pt-3.5 shadow-[inset_0_1px_0_var(--etch)]">
                  <div className="flex items-center justify-between gap-4">
                    <span id="solid-name" className="text-sm tracking-[0.06em]">素瓷（减少透明度）</span>
                    <button type="button" role="switch" aria-checked={effectiveSolid} aria-labelledby="solid-name" aria-describedby="solid-note" disabled={systemSolid}
                      onClick={() => setSolid(!solid)} className="relative flex h-10 w-11 shrink-0 items-center justify-center rounded-[12px] disabled:cursor-default">
                      <span aria-hidden="true" className="relative block h-6 w-11 rounded-full border border-[color:var(--rule2)] shadow-[inset_0_1px_2px_var(--pool)]"
                        style={{ background: effectiveSolid ? "var(--btn)" : "transparent" }}>
                        <span className="absolute left-[3px] top-[3px] h-4 w-4 rounded-full transition-transform"
                          style={{ transform: effectiveSolid ? "translateX(20px)" : "translateX(0)", background: effectiveSolid ? "var(--btnink)" : "var(--ink2)" }} />
                      </span>
                    </button>
                  </div>
                  <p id="solid-note" className="mt-1.5 text-[13px] leading-[1.85] text-[color:var(--ink2)]">关掉透明与模糊，界面改用不透明的底色，文字看得更清楚。{systemSolid && "系统已开启减少透明度或增强对比度，素瓷由系统接管。"}</p>
                </div>
              </div>
            </section>

            <section className={sectionClass}>
              <h2 className={headingClass}>数据管理</h2>
              <div className="min-w-0">
                <button onClick={clearHistory} disabled={!username}
                  className="btn btn-danger min-h-10 max-w-full justify-start px-0 text-sm mobile:h-auto mobile:break-all mobile:whitespace-normal">
                  <Trash2 size={14} />{username ? `清空「${username}」的所有聊天记录` : "正在加载身份…"}
                </button>
                {cleared && <p className="text-xs text-[color:var(--ink)]">已清空</p>}
                {clearError && <p role="alert" className="text-xs text-[color:var(--seal)]">{clearError}</p>}
                <div className="mt-[22px] space-y-2 border-t border-[color:var(--carve)] pt-[18px] shadow-[inset_0_1px_0_var(--etch)]">
                  <p className="text-[15px] tracking-[0.06em] text-[color:var(--seal)]">永久删除账号</p>
                  <label htmlFor="delete-confirmation" className="block text-[13px] leading-[1.85] text-[color:var(--ink2)]">
                    {username ? <>输入当前用户名 <span className="readout break-all text-[color:var(--ink)]">{username}</span> 确认。此操作不可恢复。</> : "正在加载身份，加载完成后才能删除账号。"}
                  </label>
                  <input id="delete-confirmation" value={deleteConfirmation} onChange={event => setDeleteConfirmation(event.target.value)}
                    placeholder={username || "正在加载身份…"} disabled={!username}
                    className="h-[42px] w-full max-w-[360px] rounded-[8px] border border-[color:var(--rule2)] bg-[color:var(--mount)] px-3 text-base shadow-[inset_0_1px_2px_var(--pool)] outline-none placeholder:text-[color:var(--ink2)] focus:border-[color:var(--ink)]" />
                  <button onClick={deleteAccount} disabled={!username || deleteConfirmation !== username || deleting}
                    className="btn btn-danger min-h-10 max-w-full px-0 mobile:h-auto mobile:whitespace-normal">
                    <Trash2 size={14} />{deleting ? "正在删除…" : "永久删除账号及全部数据"}
                  </button>
                  {deleteError && <p role="alert" className="text-xs text-[color:var(--seal)]">{deleteError}</p>}
                </div>
              </div>
            </section>

            <section className={`${sectionClass} border-b`}>
              <h2 className={headingClass}>关于</h2>
              <div className="space-y-1 text-[13px] leading-[1.85] text-[color:var(--ink2)]">
                <p>Chloe AI 助理 · 内测版</p>
                <p>账号数据保存在部署服务器的 SQLite 与 uploads 目录</p>
              </div>
            </section>
          </Glaze>
        </main>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <SettingsContent />
    </Suspense>
  );
}
