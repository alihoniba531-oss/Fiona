"use client";

import { useState, useEffect, useRef, useMemo, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Search, X, Download, Calendar, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/auth";
import GeneratedImage from "@/components/GeneratedImage";
import Glaze from "@/components/Glaze";
import InkLandscape from "@/components/InkLandscape";
import { generatedImagePath, storedReferenceImagePaths } from "@/lib/generatedImages";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";
import { formatChineseDate } from "@/lib/chineseDate";

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

function HistoryForAccount({ username }: { username: string }) {
  const { beginRequest, isCurrentOwner } = useAccountRequest(username);
  const [allMsgs, setAllMsgs] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [quick, setQuick] = useState<QuickRange>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const request = beginRequest();
    if (!request) return;
    apiFetch(`${API}/history`, { signal: request.signal })
      .then(r => r.json())
      .then(d => { if (request.isCurrent()) setAllMsgs(d.messages || []); })
      .catch(() => {})
      .finally(() => { if (request.isCurrent()) setLoading(false); });
  }, [beginRequest]);

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
    if (!isCurrentOwner()) return;
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
    <div className="relative flex min-h-screen flex-col text-[color:var(--ink)] max-md:min-h-dvh max-md:min-w-0">
      <InkLandscape variant="page" />

      {/* 顶栏 */}
      <Glaze as="header" variant="strip" className="sticky top-3 z-20 m-3 flex items-center gap-4 rounded-[16px] px-[22px] py-3 max-md:flex-wrap max-md:gap-2 max-md:px-4">
        <div className="flex shrink-0 items-center gap-2 max-md:min-w-0 max-md:max-w-[60vw]">
          <div className="max-md:min-w-0">
            <p className="text-[18px] font-medium leading-tight tracking-[0.08em]">历史记录</p>
            <p className="mt-0.5 text-xs text-muted-foreground max-md:truncate">
              {username} <span aria-hidden="true" className="mx-1 inline-block h-2.5 w-px bg-[color:var(--rule2)]" /> <span className="readout"><b>{loading ? "…" : allMsgs.length}</b> 条</span>
            </p>
          </div>
        </div>

        {/* 搜索 */}
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-[8px] border border-[color:var(--rule2)] bg-[color:var(--mount)] px-3 py-[9px] focus-within:border-[color:var(--ink)] max-md:order-3 max-md:basis-full">
          <Search size={13} className="text-muted-foreground shrink-0" />
          <input
            ref={searchRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索消息内容…"
            aria-label="搜索消息内容"
            className="min-w-0 flex-1 bg-transparent text-base text-[color:var(--ink)] outline-none placeholder:text-[color:var(--ink2)]"
          />
          {query && (
            <button aria-label="清除搜索内容" onClick={() => setQuery("")} className="btn btn-quiet h-8 w-8 shrink-0 px-0 max-md:h-10 max-md:w-10">
              <X size={12} />
            </button>
          )}
        </div>

        {/* 导出 */}
        <button
          onClick={handleExport}
          className="btn min-h-10 shrink-0 max-md:ml-auto"
        >
          <Download size={12} />
          导出
          {filtered.length < allMsgs.length && <span className="readout max-md:hidden">({filtered.length}条)</span>}
        </button>
      </Glaze>

      <div className="relative z-[1] flex min-h-0 flex-1 gap-3 max-md:min-w-0 max-md:flex-col max-md:gap-0">

        {/* 左侧：日期导航 */}
        <Glaze as="aside" variant="panel" fur className="mb-3 ml-3 flex w-56 shrink-0 flex-col rounded-[18px] max-md:mr-3 max-md:w-auto">
          {/* 快捷筛选 */}
          <div className="px-3 pt-4 pb-2 max-md:pt-3">
            <p className="mb-2 px-1 text-xs font-medium text-muted-foreground">快捷筛选</p>
            <div className="flex flex-col gap-0.5 max-md:grid max-md:grid-cols-4 max-md:gap-1">
              {quickLabels.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => applyQuick(key)}
                  className={cn(
                    "chip h-auto min-h-10 w-full justify-start px-3 py-1.5 text-left max-md:justify-center max-md:px-1",
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
          <div className="border-t px-3 py-3 max-md:py-2" style={{ borderColor: "var(--carve)" }}>
            <p className="mb-2 flex items-center gap-1 px-1 text-xs font-medium text-muted-foreground">
              <Calendar size={12} style={{ color: "var(--ink)" }} />
              自定义区间
            </p>
            <div className="space-y-1.5 max-md:grid max-md:grid-cols-1 max-md:gap-1.5 max-md:space-y-0">
              <input
                type="date"
                aria-label="开始日期"
                value={dateFrom}
                onChange={e => { setDateFrom(e.target.value); setQuick("all"); }}
                className="readout min-w-0 max-w-full rounded-[8px] border border-[color:var(--rule2)] bg-[color:var(--mount)] px-3 py-[9px] text-base text-[color:var(--ink)] outline-none focus:border-[color:var(--ink)] max-md:w-full max-md:px-1.5"
              />
              <div className="text-center text-[10px] text-muted-foreground">至</div>
              <input
                type="date"
                aria-label="结束日期"
                value={dateTo}
                onChange={e => { setDateTo(e.target.value); setQuick("all"); }}
                className="readout min-w-0 max-w-full rounded-[8px] border border-[color:var(--rule2)] bg-[color:var(--mount)] px-3 py-[9px] text-base text-[color:var(--ink)] outline-none focus:border-[color:var(--ink)] max-md:w-full max-md:px-1.5"
              />
              {(dateFrom || dateTo) && (
                <button
                  onClick={() => { setDateFrom(""); setDateTo(""); setQuick("all"); }}
                  className="btn btn-quiet min-h-10 w-full px-2.5 text-xs"
                >
                  清除筛选
                </button>
              )}
            </div>
          </div>

          {/* 日期列表 */}
          <div className="flex-1 overflow-y-auto border-t px-3 pb-4 pt-3 max-md:flex-none max-md:overflow-x-auto max-md:overflow-y-hidden max-md:pb-2 max-md:pt-2 mobile-scrollbar-none" style={{ borderColor: "var(--carve)" }}>
            <p className="mb-2 px-1 text-xs font-medium text-muted-foreground">按日期跳转</p>
            <div className="flex flex-col gap-0.5 max-md:flex-row max-md:gap-1">
              {dateStats.map(([day, count]) => {
                const isActive = dateFrom === day && dateTo === day;
                return (
                  <button
                    key={day}
                    onClick={() => selectDay(day)}
                    className={cn(
                      "chip h-auto min-h-10 w-full justify-between px-3 py-1.5 text-left max-md:w-auto max-md:shrink-0 max-md:gap-2",
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
        </Glaze>

        {/* 右侧：消息内容 */}
        <main className="min-w-0 flex-1 overflow-y-auto px-8 py-5 max-md:overflow-visible max-md:px-[18px] max-md:py-4">
          <div className="mx-auto w-full max-w-[760px] space-y-7">
          {/* 筛选结果摘要 */}
          {(query || dateFrom || dateTo) && (
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground pb-1 max-md:flex-wrap">
              <span>筛选结果：<span className="readout"><b>{filtered.length}</b> 条</span></span>
              {query && <span className="chip h-6 px-2 text-[11px] max-md:h-auto max-md:max-w-full max-md:break-all max-md:whitespace-normal">含「{query}」</span>}
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
                  className="btn btn-quiet mt-1 min-h-10 px-2.5 text-xs"
                >
                  清除所有筛选
                </button>
              )}
            </div>
          ) : groups.map(([day, msgs]) => {
            const open = !collapsed[day];
            return (
              <section key={day} className="min-w-0">
                <button
                  onClick={() => setCollapsed(p => ({ ...p, [day]: !p[day] }))}
                  aria-expanded={open}
                  className="flex min-h-10 w-full items-center gap-[18px] py-3 text-left text-[color:var(--ink2)]"
                >
                  {open
                    ? <ChevronDown size={13} className="text-muted-foreground shrink-0" />
                    : <ChevronRight size={13} className="text-muted-foreground shrink-0" />
                  }
                  <span aria-hidden="true" className="h-px min-w-4 flex-1 bg-[color:var(--rule)]" />
                  <span className="text-xs tracking-[0.2em] max-md:tracking-[0.08em]">{formatChineseDate(new Date(day + "T00:00:00"), true)}</span>
                  <span aria-hidden="true" className="h-px min-w-4 flex-1 bg-[color:var(--rule)]" />
                  <span className="readout text-xs">{msgs.length} 条</span>
                </button>

                {open && (
                  <div className="space-y-7 pt-5">
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
                        <div key={msg.id} className={cn("flex min-w-0", isUser ? "justify-end" : "justify-start")}>
                          <div className={cn("flex min-w-0 flex-col gap-2", isUser ? "max-w-[72%] items-end max-md:max-w-[82%]" : "w-full max-w-[600px] items-start")}>
                            {!isUser && (
                              <div className="text-[13px] tracking-[0.1em] text-[color:var(--ink2)]">
                                Chloe
                              </div>
                            )}
                            {!isUser && generatedPath && <GeneratedImage key={`${username}:${generatedPath}`} imageUrl={`${API}${generatedPath}`} />}
                            {referencePaths.length > 0 && <div className="flex max-w-full flex-wrap justify-end gap-2" aria-label="本次修改的参考图片">
                              {referencePaths.map((path, index) => <GeneratedImage key={`${username}:${path}`} imageUrl={`${API}${path}`} variant="reference" referenceIndex={index + 1} />)}
                            </div>}
                            <div className={cn("max-w-full break-words whitespace-pre-wrap", isUser ? "bubble-user" : "bubble-ai")}>
                              {highlight(msg.content)}
                            </div>
                            <span className="readout text-xs text-[color:var(--ink2)]">{time}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            );
          })}
          </div>
        </main>
      </div>
    </div>
  );
}

function HistoryContent() {
  const params = useSearchParams();
  const router = useRouter();
  const identity = useAccountIdentity();
  const requestedUser = params.get("user");

  useEffect(() => {
    if (!identity || requestedUser === null || requestedUser === identity) return;
    const url = new URL(window.location.href);
    url.searchParams.delete("user");
    router.replace(`${url.pathname}${url.search}${url.hash}`, { scroll: false });
  }, [identity, requestedUser, router]);

  if (!identity) {
    return <div role="status" className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">加载中…</div>;
  }
  const username = requestedUser === identity ? requestedUser : identity;
  return <HistoryForAccount key={username} username={username} />;
}

export default function HistoryPage() {
  return (
    <Suspense fallback={
      <div role="status" className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        加载中…
      </div>
    }>
      <HistoryContent />
    </Suspense>
  );
}
