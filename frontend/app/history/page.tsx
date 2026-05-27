"use client";

import { useState, useEffect, useRef, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Search, X, Download, Calendar, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/auth";

import { API_BASE as API } from "@/lib/config";

interface Msg {
  id: number;
  role: "user" | "assistant";
  content: string;
  image_path: string | null;
  created_at: string;
}

type QuickRange = "all" | "today" | "week" | "month";

function toDateStr(d: Date) {
  return d.toISOString().slice(0, 10); // "YYYY-MM-DD"
}

function formatDisplayDate(isoDate: string) {
  return new Date(isoDate + "T00:00:00").toLocaleDateString("zh-CN", {
    year: "numeric", month: "long", day: "numeric",
  });
}

function HistoryContent() {
  const params = useSearchParams();
  const username = params.get("user") || (typeof window !== "undefined" ? localStorage.getItem("fiona_user") : null) || "默认用户";

  const [allMsgs, setAllMsgs] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [quick, setQuick] = useState<QuickRange>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // 历史记录端点已收紧为"当前登录用户"，路径里的 ?user= 参数已无意义但保留 UI 不变。
    // 后端通过鉴权头识别用户。
    apiFetch(`${API}/history`)
      .then(r => r.json())
      .then(d => setAllMsgs(d.messages || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [username]);

  // 计算每天的消息数，生成日期列表（降序）
  const dateStats = useMemo(() => {
    const map: Record<string, number> = {};
    allMsgs.forEach(m => {
      const day = m.created_at.slice(0, 10);
      map[day] = (map[day] || 0) + 1;
    });
    return Object.entries(map).sort((a, b) => b[0].localeCompare(a[0]));
  }, [allMsgs]);

  // 快捷日期范围
  const applyQuick = (range: QuickRange) => {
    setQuick(range);
    setDateFrom("");
    setDateTo("");
    const now = new Date();
    if (range === "today") {
      setDateFrom(toDateStr(now));
      setDateTo(toDateStr(now));
    } else if (range === "week") {
      const start = new Date(now);
      start.setDate(now.getDate() - 6);
      setDateFrom(toDateStr(start));
      setDateTo(toDateStr(now));
    } else if (range === "month") {
      const start = new Date(now.getFullYear(), now.getMonth(), 1);
      setDateFrom(toDateStr(start));
      setDateTo(toDateStr(now));
    }
  };

  // 点击左侧某一天
  const selectDay = (day: string) => {
    setQuick("all");
    setDateFrom(day);
    setDateTo(day);
  };

  // 过滤消息
  const filtered = useMemo(() => {
    return allMsgs.filter(m => {
      const day = m.created_at.slice(0, 10);
      if (dateFrom && day < dateFrom) return false;
      if (dateTo && day > dateTo) return false;
      if (query.trim() && !m.content.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
  }, [allMsgs, dateFrom, dateTo, query]);

  // 按日期分组
  const groups = useMemo(() => {
    const map: Record<string, Msg[]> = {};
    filtered.forEach(m => {
      const day = m.created_at.slice(0, 10);
      if (!map[day]) map[day] = [];
      map[day].push(m);
    });
    return Object.entries(map).sort((a, b) => b[0].localeCompare(a[0]));
  }, [filtered]);

  const handleExport = () => {
    const lines = filtered.map(m =>
      `[${m.created_at}] ${m.role === "user" ? username : "Chloe"}: ${m.content}`
    );
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Chloe_${username}_${toDateStr(new Date())}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const quickLabels: { key: QuickRange; label: string }[] = [
    { key: "all", label: "全部" },
    { key: "today", label: "今天" },
    { key: "week", label: "近7天" },
    { key: "month", label: "本月" },
  ];

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">

      {/* 顶栏 */}
      <header className="sticky top-0 z-20 glass border-b border-border px-5 py-2.5 flex items-center gap-3">
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
            <span className="text-white text-xs font-semibold">C</span>
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight">历史记录</p>
            <p className="text-[10px] text-muted-foreground">{username} · {allMsgs.length} 条</p>
          </div>
        </div>

        {/* 搜索 */}
        <div className="flex-1 flex items-center gap-2 bg-secondary rounded-xl px-3 py-1.5">
          <Search size={13} className="text-muted-foreground shrink-0" />
          <input
            ref={searchRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索消息内容…"
            className="flex-1 bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground min-w-0"
          />
          {query && (
            <button onClick={() => setQuery("")} className="text-muted-foreground hover:text-foreground shrink-0">
              <X size={12} />
            </button>
          )}
        </div>

        {/* 导出 */}
        <button
          onClick={handleExport}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-secondary text-xs text-muted-foreground hover:text-foreground transition-all shrink-0"
        >
          <Download size={12} />
          导出{filtered.length < allMsgs.length ? `(${filtered.length}条)` : ""}
        </button>
      </header>

      <div className="flex flex-1 min-h-0">

        {/* 左侧：日期导航 */}
        <aside className="w-56 shrink-0 border-r border-border flex flex-col glass">
          {/* 快捷筛选 */}
          <div className="px-3 pt-4 pb-2">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-1 mb-2">快捷筛选</p>
            <div className="flex flex-col gap-0.5">
              {quickLabels.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => applyQuick(key)}
                  className={cn(
                    "w-full text-left px-3 py-1.5 rounded-lg text-xs transition-all",
                    quick === key && dateFrom === (key === "all" ? "" : dateFrom)
                      ? "bg-primary text-white font-medium"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* 日期区间 */}
          <div className="px-3 py-3 border-t border-border">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-1 mb-2 flex items-center gap-1">
              <Calendar size={10} />
              自定义区间
            </p>
            <div className="space-y-1.5">
              <input
                type="date"
                value={dateFrom}
                onChange={e => { setDateFrom(e.target.value); setQuick("all"); }}
                className="w-full bg-secondary text-foreground text-[11px] rounded-lg px-2 py-1.5 outline-none border border-border focus:border-primary transition-colors"
              />
              <div className="text-center text-[10px] text-muted-foreground">至</div>
              <input
                type="date"
                value={dateTo}
                onChange={e => { setDateTo(e.target.value); setQuick("all"); }}
                className="w-full bg-secondary text-foreground text-[11px] rounded-lg px-2 py-1.5 outline-none border border-border focus:border-primary transition-colors"
              />
              {(dateFrom || dateTo) && (
                <button
                  onClick={() => { setDateFrom(""); setDateTo(""); setQuick("all"); }}
                  className="w-full text-[11px] text-muted-foreground hover:text-foreground py-1 transition-colors"
                >
                  清除筛选
                </button>
              )}
            </div>
          </div>

          {/* 日期列表 */}
          <div className="flex-1 overflow-y-auto px-3 pb-4 border-t border-border pt-3">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-1 mb-2">按日期跳转</p>
            <div className="flex flex-col gap-0.5">
              {dateStats.map(([day, count]) => {
                const isActive = dateFrom === day && dateTo === day;
                return (
                  <button
                    key={day}
                    onClick={() => selectDay(day)}
                    className={cn(
                      "w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-left transition-all",
                      isActive
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                    )}
                  >
                    <span className="text-[11px]">{day.slice(5)}</span>
                    <span className="text-[10px] opacity-60">{count}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        {/* 右侧：消息内容 */}
        <main className="flex-1 overflow-y-auto px-6 py-5 space-y-3">
          {/* 筛选结果摘要 */}
          {(query || dateFrom || dateTo) && (
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground pb-1">
              <span>筛选结果：{filtered.length} 条</span>
              {query && <span className="bg-secondary px-2 py-0.5 rounded-full">含「{query}」</span>}
              {(dateFrom || dateTo) && (
                <span className="bg-secondary px-2 py-0.5 rounded-full">
                  {dateFrom || "—"} 至 {dateTo || "—"}
                </span>
              )}
            </div>
          )}

          {loading ? (
            <div className="flex justify-center pt-20 text-sm text-muted-foreground">加载中…</div>
          ) : groups.length === 0 ? (
            <div className="flex flex-col items-center pt-24 gap-2 text-center">
              <p className="text-sm text-muted-foreground">
                {query || dateFrom || dateTo ? "没有符合条件的记录" : "还没有聊天记录"}
              </p>
              {(query || dateFrom || dateTo) && (
                <button
                  onClick={() => { setQuery(""); setDateFrom(""); setDateTo(""); setQuick("all"); }}
                  className="text-xs text-primary hover:underline mt-1"
                >
                  清除所有筛选
                </button>
              )}
            </div>
          ) : groups.map(([day, msgs]) => {
            const open = !collapsed[day];
            return (
              <div key={day} className="bg-card border border-border rounded-2xl overflow-hidden">
                <button
                  onClick={() => setCollapsed(p => ({ ...p, [day]: !p[day] }))}
                  className="w-full flex items-center gap-2 px-4 py-3 hover:bg-secondary/40 transition-all text-left"
                >
                  {open
                    ? <ChevronDown size={13} className="text-muted-foreground shrink-0" />
                    : <ChevronRight size={13} className="text-muted-foreground shrink-0" />
                  }
                  <span className="text-[11px] font-semibold text-muted-foreground">{formatDisplayDate(day)}</span>
                  <span className="text-[10px] text-muted-foreground/50 ml-auto">{msgs.length} 条</span>
                </button>

                {open && (
                  <div className="border-t border-border divide-y divide-border/50">
                    {msgs.map(msg => {
                      const isUser = msg.role === "user";
                      const time = new Date(msg.created_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit", minute: "2-digit",
                      });
                      // 高亮搜索词。query 是用户输入，必须 escape 才能塞进 RegExp，
                      // 否则输入 ( / [ / \ 等 regex 元字符会抛 SyntaxError 白屏整页。
                      const highlight = (text: string) => {
                        if (!query.trim()) return text;
                        const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
                        const parts = text.split(new RegExp(`(${escaped})`, "gi"));
                        return parts.map((p, i) =>
                          p.toLowerCase() === query.toLowerCase()
                            ? <mark key={i} className="bg-yellow-400/40 text-foreground rounded px-0.5">{p}</mark>
                            : p
                        );
                      };
                      return (
                        <div key={msg.id} className={cn("px-4 py-3 flex gap-3", isUser && "flex-row-reverse")}>
                          <div className={cn(
                            "w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 mt-0.5",
                            isUser ? "bg-primary text-white" : "bg-accent text-accent-foreground"
                          )}>
                            {isUser ? username[0] : "C"}
                          </div>
                          <div className={cn("flex flex-col gap-0.5 max-w-[80%]", isUser && "items-end")}>
                            <div className={cn(
                              "px-3 py-2 rounded-2xl text-sm leading-relaxed break-words whitespace-pre-wrap",
                              isUser ? "bg-primary text-white rounded-br-sm" : "bg-secondary text-foreground rounded-bl-sm"
                            )}>
                              {highlight(msg.content)}
                            </div>
                            <span className="text-[9px] text-muted-foreground px-1">{time}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </main>
      </div>
    </div>
  );
}

export default function HistoryPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center text-muted-foreground text-sm">
        加载中…
      </div>
    }>
      <HistoryContent />
    </Suspense>
  );
}
