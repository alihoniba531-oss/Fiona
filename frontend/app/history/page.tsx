"use client";

import { useState, useEffect, useRef, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Search, X, Download, Calendar, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/auth";
import GeneratedImage from "@/components/GeneratedImage";
import { generatedImagePath, storedReferenceImagePaths } from "@/lib/generatedImages";

import { API_BASE as API } from "@/lib/config";

interface Msg {
  id: number;
  role: "user" | "assistant";
  content: string;
  image_path: string | null;
  reference_image_paths?: string[];
  created_at: string;
}

type QuickRange = "all" | "today" | "week" | "month";

function toDateStr(d: Date) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseUtcTimestamp(timestamp: string) {
  return new Date(timestamp.replace(" ", "T") + "Z");
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
      const day = toDateStr(parseUtcTimestamp(m.created_at));
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
      const day = toDateStr(parseUtcTimestamp(m.created_at));
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
      const day = toDateStr(parseUtcTimestamp(m.created_at));
      if (!map[day]) map[day] = [];
      map[day].push(m);
    });
    return Object.entries(map).sort((a, b) => b[0].localeCompare(a[0]));
  }, [filtered]);

  const handleExport = () => {
    const lines = filtered.map(m =>
      `[${parseUtcTimestamp(m.created_at).toLocaleString("zh-CN", { hour12: false })}] ${m.role === "user" ? username : "Chloe"}: ${m.content}`
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
    <div className="flex min-h-screen flex-col text-foreground">

      {/* 顶栏 */}
      <header className="glass sticky top-0 z-20 flex items-center gap-3 border-b px-5 py-2.5" style={{ borderColor: "var(--glass-border)" }}>
        <div className="flex shrink-0 items-center gap-2">
          <div>
            <p className="text-sm font-medium leading-tight">历史记录</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {username} · <span className="readout"><b>{allMsgs.length}</b> 条</span>
            </p>
          </div>
        </div>

        {/* 搜索 */}
        <div className="flex flex-1 items-center gap-2 rounded-[6px] border bg-card px-3 py-[9px] focus-within:border-[color:var(--amber-ink)]">
          <Search size={13} className="text-muted-foreground shrink-0" />
          <input
            ref={searchRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索消息内容…"
            className="flex-1 bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground min-w-0"
          />
          {query && (
            <button onClick={() => setQuery("")} className="btn btn-quiet h-7 w-7 shrink-0 px-0">
              <X size={12} />
            </button>
          )}
        </div>

        {/* 导出 */}
        <button
          onClick={handleExport}
          className="btn shrink-0"
        >
          <Download size={12} />
          导出
          {filtered.length < allMsgs.length && <span className="readout">({filtered.length}条)</span>}
        </button>
      </header>

      <div className="flex flex-1 min-h-0">

        {/* 左侧：日期导航 */}
        <aside className="glass flex w-56 shrink-0 flex-col border-r" style={{ borderColor: "var(--glass-border)" }}>
          {/* 快捷筛选 */}
          <div className="px-3 pt-4 pb-2">
            <p className="mb-2 px-1 text-xs font-medium text-muted-foreground">快捷筛选</p>
            <div className="flex flex-col gap-0.5">
              {quickLabels.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => applyQuick(key)}
                  className={cn(
                    "chip h-auto w-full justify-start px-3 py-1.5 text-left",
                    quick === key && dateFrom === (key === "all" ? "" : dateFrom)
                      ? "chip-on"
                      : ""
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* 日期区间 */}
          <div className="border-t px-3 py-3" style={{ borderColor: "var(--glass-border)" }}>
            <p className="mb-2 flex items-center gap-1 px-1 text-xs font-medium text-muted-foreground">
              <Calendar size={12} style={{ color: "var(--amber-ink)" }} />
              自定义区间
            </p>
            <div className="space-y-1.5">
              <input
                type="date"
                value={dateFrom}
                onChange={e => { setDateFrom(e.target.value); setQuick("all"); }}
                className="readout w-full rounded-[6px] border bg-card px-3 py-[9px] text-foreground outline-none focus:border-[color:var(--amber-ink)]"
              />
              <div className="text-center text-[10px] text-muted-foreground">至</div>
              <input
                type="date"
                value={dateTo}
                onChange={e => { setDateTo(e.target.value); setQuick("all"); }}
                className="readout w-full rounded-[6px] border bg-card px-3 py-[9px] text-foreground outline-none focus:border-[color:var(--amber-ink)]"
              />
              {(dateFrom || dateTo) && (
                <button
                  onClick={() => { setDateFrom(""); setDateTo(""); setQuick("all"); }}
                  className="btn btn-quiet h-7 w-full px-2.5 text-xs"
                >
                  清除筛选
                </button>
              )}
            </div>
          </div>

          {/* 日期列表 */}
          <div className="flex-1 overflow-y-auto border-t px-3 pb-4 pt-3" style={{ borderColor: "var(--glass-border)" }}>
            <p className="mb-2 px-1 text-xs font-medium text-muted-foreground">按日期跳转</p>
            <div className="flex flex-col gap-0.5">
              {dateStats.map(([day, count]) => {
                const isActive = dateFrom === day && dateTo === day;
                return (
                  <button
                    key={day}
                    onClick={() => selectDay(day)}
                    className={cn(
                      "chip h-auto w-full justify-between px-3 py-1.5 text-left",
                      isActive && "chip-on"
                    )}
                  >
                    <span className="readout text-[11px]">{day.slice(5)}</span>
                    <span className="readout text-[10px]">{count}</span>
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
              <span>筛选结果：<span className="readout"><b>{filtered.length}</b> 条</span></span>
              {query && <span className="chip h-6 px-2 text-[11px]">含「{query}」</span>}
              {(dateFrom || dateTo) && (
                <span className="chip h-6 px-2 text-[11px]">
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
                  className="btn btn-quiet mt-1 h-7 px-2.5 text-xs"
                >
                  清除所有筛选
                </button>
              )}
            </div>
          ) : groups.map(([day, msgs]) => {
            const open = !collapsed[day];
            return (
              <div key={day} className="glass-card overflow-hidden">
                <button
                  onClick={() => setCollapsed(p => ({ ...p, [day]: !p[day] }))}
                  className="w-full flex items-center gap-2 px-4 py-3 hover:bg-secondary/40 transition-all text-left"
                >
                  {open
                    ? <ChevronDown size={13} className="text-muted-foreground shrink-0" />
                    : <ChevronRight size={13} className="text-muted-foreground shrink-0" />
                  }
                  <span className="text-[13px] font-medium text-muted-foreground">{formatDisplayDate(day)}</span>
                  <span className="readout ml-auto text-[11px]">{msgs.length} 条</span>
                </button>

                {open && (
                  <div className="divide-y divide-[color:var(--glass-border)] border-t" style={{ borderColor: "var(--glass-border)" }}>
                    {msgs.map(msg => {
                      const isUser = msg.role === "user";
                      const generatedPath = generatedImagePath(msg.image_path ?? undefined);
                      const referencePaths = isUser ? storedReferenceImagePaths(msg.reference_image_paths, msg.image_path) : [];
                      const time = parseUtcTimestamp(msg.created_at).toLocaleTimeString("zh-CN", {
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
                            ? <mark key={i} className="bg-[color:var(--accent)] text-foreground rounded-[3px] px-0.5">{p}</mark>
                            : p
                        );
                      };
                      return (
                        <div key={msg.id} className={cn("flex px-4 py-3", isUser ? "justify-end" : "justify-start")}>
                          <div className={cn("flex flex-col gap-1.5", isUser ? "max-w-[520px] items-end" : "max-w-[640px] items-start")}>
                            {!isUser && (
                              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                <span className="inline-block h-1.5 w-1.5" style={{ background: "var(--amber-ink)" }} />
                                Chloe
                              </div>
                            )}
                            {!isUser && generatedPath && <GeneratedImage key={`${username}:${generatedPath}`} imageUrl={`${API}${generatedPath}`} />}
                            {referencePaths.length > 0 && <div className="flex max-w-full flex-wrap justify-end gap-2" aria-label="本次修改的参考图片">
                              {referencePaths.map((path, index) => <GeneratedImage key={`${username}:${path}`} imageUrl={`${API}${path}`} variant="reference" referenceIndex={index + 1} />)}
                            </div>}
                            <div className={cn("break-words whitespace-pre-wrap text-sm", isUser ? "bubble-user" : "bubble-ai")}>
                              {highlight(msg.content)}
                            </div>
                            <span className="readout px-1 text-[11px]">{time}</span>
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
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        加载中…
      </div>
    }>
      <HistoryContent />
    </Suspense>
  );
}
