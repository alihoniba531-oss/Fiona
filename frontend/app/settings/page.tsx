"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import { Trash2, User, Info } from "lucide-react";
import { apiFetch } from "@/lib/auth";

const API = "/api";

export default function SettingsPage() {
  const sp = useSearchParams();
  const embedded = sp?.get("embed") === "1";
  const [username, setUsername] = useState("默认用户");
  const [allUsers, setAllUsers] = useState<string[]>([]);
  const [cleared, setCleared] = useState(false);

  useEffect(() => {
    const u = localStorage.getItem("fiona_user");
    if (u) setUsername(u);
    // /users 端点仅在后端 DEV_MODE=1 时开放；prod 直接 404，前端把列表留空即可。
    fetch(`${API}/users`).then(r => r.ok ? r.json() : { users: [] }).then(d => setAllUsers(d.users || [])).catch(() => {});
  }, []);

  const switchUser = (u: string) => {
    setUsername(u);
    localStorage.setItem("fiona_user", u);
    // 通知 TopBar 等组件:身份变了,重新拉余额 / 状态
    window.dispatchEvent(new Event("fiona-user-changed"));
  };

  const clearHistory = async () => {
    if (!confirm(`确定清空「${username}」的所有聊天记录？此操作不可恢复。`)) return;
    await apiFetch(`${API}/history`, { method: "DELETE" }).catch(() => {});
    setCleared(true);
    setTimeout(() => setCleared(false), 3000);
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
                        ? "bg-primary text-white"
                        : "bg-secondary text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {u}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground/60">
                切换身份后，聊天、画像、匹配均独立。正式登录系统上线前临时使用。
              </p>
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
            </div>

            {/* 关于 */}
            <div className="bg-card border border-border rounded-2xl p-5 space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <Info size={13} />
                关于
              </div>
              <div className="space-y-1 text-[11px] text-muted-foreground">
                <p>Chloe AI 助理 · 内测版</p>
                <p>后端：FastAPI + DeepSeek · 前端：Next.js</p>
                <p className="text-muted-foreground/50">数据存储在本地 SQLite，不上传任何服务器</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
