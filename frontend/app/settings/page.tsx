"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import { Trash2, User, Info, LogOut } from "lucide-react";
import { apiFetch, clearAuth, setAuth } from "@/lib/auth";

import { API_BASE as API } from "@/lib/config";

function SettingsContent() {
  const sp = useSearchParams();
  const embedded = sp?.get("embed") === "1";
  const [username, setUsername] = useState("默认用户");
  const [allUsers, setAllUsers] = useState<string[]>([]);
  const [cleared, setCleared] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    const u = localStorage.getItem("fiona_user");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (u) setUsername(u);
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
    setUsername(data.username);
  };

  const clearHistory = async () => {
    if (!confirm(`确定清空「${username}」的所有聊天记录？此操作不可恢复。`)) return;
    await apiFetch(`${API}/history`, { method: "DELETE" }).catch(() => {});
    setCleared(true);
    setTimeout(() => setCleared(false), 3000);
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
    await apiFetch(`${API}/auth/logout`, { method: "POST" }).catch(() => null);
    clearAuth();
    redirectTop("/login?reason=logout");
  };

  const deleteAccount = async () => {
    if (deleteConfirmation !== username || deleting) return;
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

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      {!embedded && <TopBar />}
      <div className="flex flex-1 min-h-0">
        {!embedded && <Sidebar />}
        <div className="flex flex-col flex-1 min-w-0">
          <header className="glass border-b border-border px-6 py-4 shrink-0">
            <h1 className="text-base font-semibold">设置</h1>
            <p className="text-[11px] text-muted-foreground mt-0.5">账号与数据管理</p>
          </header>

          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-3 max-w-lg">
            {/* 当前身份 */}
            <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <User size={13} />
                当前身份
              </div>
              <div className="flex flex-wrap gap-2">
                {(allUsers.length ? allUsers : [username]).map(u => (
                  <button
                    key={u}
                    onClick={() => switchUser(u)}
                    className={`px-4 py-1.5 rounded-full text-sm transition-all ${
                      u === username
                        ? "bg-primary text-primary-foreground"
                        : "bg-secondary text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {u}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground/60">
                当前使用服务端 HttpOnly 会话；开发环境仍可切换测试身份。
              </p>
              <button
                onClick={logout}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-all border border-border w-full"
              >
                <LogOut size={14} />
                退出登录并撤销现有会话
              </button>
            </div>

            {/* 数据管理 */}
            <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <Trash2 size={13} />
                数据管理
              </div>
              <button
                onClick={clearHistory}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm text-destructive/80 hover:text-destructive hover:bg-destructive/10 transition-all border border-destructive/20 w-full"
              >
                <Trash2 size={14} />
                清空「{username}」的所有聊天记录
              </button>
              {cleared && (
                <p className="text-xs text-green-500">已清空</p>
              )}
              <div className="pt-3 border-t border-border space-y-2">
                <p className="text-xs text-destructive">永久删除账号</p>
                <p className="text-[11px] text-muted-foreground">
                  输入当前用户名 <span className="font-mono text-foreground">{username}</span> 确认。此操作不可恢复。
                </p>
                <input
                  value={deleteConfirmation}
                  onChange={event => setDeleteConfirmation(event.target.value)}
                  placeholder={username}
                  className="w-full bg-secondary rounded-xl px-4 py-2 text-sm outline-none placeholder:text-muted-foreground"
                />
                <button
                  onClick={deleteAccount}
                  disabled={deleteConfirmation !== username || deleting}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm text-destructive hover:bg-destructive/10 transition-all border border-destructive/30 w-full disabled:opacity-40"
                >
                  <Trash2 size={14} />
                  {deleting ? "正在删除…" : "永久删除账号及全部数据"}
                </button>
                {deleteError && <p className="text-xs text-destructive">{deleteError}</p>}
              </div>
            </div>

            {/* 关于 */}
            <div className="bg-card border border-border rounded-2xl p-5 space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <Info size={13} />
                关于
              </div>
              <div className="space-y-1 text-[11px] text-muted-foreground">
                <p>Chloe AI 助理 · 内测版</p>
                <p className="text-muted-foreground/50">账号数据保存在部署服务器的 SQLite 与 uploads 目录</p>
              </div>
            </div>
          </div>
        </div>
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
