"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowUpRight, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import type { CardData } from "@/components/ChatBubble";
import { apiFetch } from "@/lib/auth";
import { API_BASE } from "@/lib/config";
import { openExternal } from "@/lib/open";

interface NewsDetail {
  title: string;
  summary: string;
  whats_happening: string;
  key_facts: string[];
  background: string;
  sources: { title: string; url: string; site_name?: string; index?: number }[];
}

function safeUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password
      && url.href.length <= 2048 ? url.href : null;
  } catch { return null; }
}

function detailFromResponse(value: unknown): NewsDetail {
  if (!value || typeof value !== "object") throw new Error("详情暂时无法读取，请重试");
  const data = value as Record<string, unknown>;
  if (data.error) throw new Error(typeof data.error === "string" ? data.error : "详情暂时无法读取，请重试");
  const text = (key: string) => typeof data[key] === "string" ? data[key] as string : "";
  const sources = Array.isArray(data.sources) ? data.sources.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const url = safeUrl(item.url);
    return url ? [{ title: typeof item.title === "string" ? item.title : "查看来源原文", url,
      site_name: typeof item.site_name === "string" ? item.site_name : undefined,
      index: typeof item.index === "number" && Number.isInteger(item.index) && item.index >= 0 ? item.index : undefined }] : [];
  }) : [];
  if (!sources.length) throw new Error("暂未找到可核实的来源，请稍后重试");
  return { title: text("title"), summary: text("summary"), whats_happening: text("whats_happening"),
    key_facts: Array.isArray(data.key_facts) ? data.key_facts.filter((item): item is string => typeof item === "string") : [],
    background: text("background"), sources };
}

export default function NewsCardContent({ card }: { card: CardData }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<NewsDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const cacheRef = useRef(new Map<number, { detail: NewsDetail; at: number }>());
  const headingRef = useRef<HTMLHeadingElement>(null);
  const rowRefs = useRef(new Map<number, HTMLButtonElement>());
  const lastSelected = useRef<number | null>(null);

  useEffect(() => () => { requestRef.current?.abort(); requestRef.current = null; }, []);
  useEffect(() => {
    if (selected !== null) headingRef.current?.focus();
    else if (lastSelected.current !== null) rowRefs.current.get(lastSelected.current)?.focus();
  }, [selected]);

  const openDetail = useCallback(async (index: number, force = false) => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    lastSelected.current = index;
    setSelected(index);
    setError(null);
    const cached = cacheRef.current.get(index);
    if (!force && cached && Date.now() - cached.at < 300_000) {
      setDetail(cached.detail);
      setLoading(false);
      return;
    }
    setDetail(null);
    setLoading(true);
    let timedOut = false;
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 50_000);
    try {
      const title = (card.items?.[index]?.title || card.points[index]).trim().slice(0, 1000);
      const response = await apiFetch(`${API_BASE}/cards/detail`, {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify({ title, context: card.source.slice(0, 200) }),
      });
      if (!response.ok) throw new Error(response.status === 429
        ? "查看较频繁，请稍后重试" : "详情暂时无法加载，请重试");
      const next = detailFromResponse(await response.json());
      if (requestRef.current !== controller || controller.signal.aborted) return;
      cacheRef.current.set(index, { detail: next, at: Date.now() });
      setDetail(next);
    } catch (failure) {
      if (requestRef.current !== controller || (controller.signal.aborted && !timedOut)) return;
      setError(timedOut ? "加载超时，请重试" : failure instanceof Error && !(failure instanceof TypeError)
        ? failure.message : "连接失败，请重试");
    } finally {
      window.clearTimeout(timeout);
      if (requestRef.current === controller) setLoading(false);
    }
  }, [card]);

  function backToList() {
    requestRef.current?.abort();
    requestRef.current = null;
    setSelected(null);
    setDetail(null);
    setError(null);
    setLoading(false);
  }

  const cardUrl = safeUrl(card.url);
  return (
    <div className="glass-card flex max-h-[88vh] flex-col overflow-hidden rounded-[10px] border" style={{ borderColor: "var(--glass-border)" }}>
      <div className="shrink-0 border-b px-5 py-4 sm:px-8" style={{ borderColor: "var(--glass-border)" }}>
        {selected === null ? (
          <>
            <h2 className="text-xs font-medium text-muted-foreground">{card.source || "卡片"}</h2>
            {!card.error && <p className="mt-2 text-xs text-muted-foreground">点击任一条，查看详情与来源</p>}
          </>
        ) : (
          <button type="button" onClick={backToList} className="btn btn-quiet h-7 px-2.5 text-xs">
            <ArrowLeft size={16} /> 返回新闻列表
          </button>
        )}
      </div>
      <div className="min-h-0 overflow-y-auto px-5 py-5 sm:px-8" aria-busy={loading}>
        {selected === null ? (
          card.points.length ? <ul className="space-y-3">
            {card.points.map((point, index) => <li key={index}>
              {card.error ? <p className="text-sm leading-relaxed">{point}</p> : (
                <button type="button" ref={(node) => { if (node) rowRefs.current.set(index, node); else rowRefs.current.delete(index); }}
                  onClick={() => void openDetail(index)}
                  aria-label={`查看详情：${card.items?.[index]?.title || point}`}
                  className="group flex w-full items-start gap-3 rounded-[10px] border p-4 text-left hover:bg-secondary focus-visible:outline-2 focus-visible:outline-[color:var(--ring)]"
                  style={{ borderColor: "var(--glass-border)" }}>
                  <span className="readout mt-0.5 shrink-0 text-[11px]">{String(index + 1).padStart(2, "0")}</span>
                  <span className="min-w-0 flex-1 break-words text-[15px] leading-relaxed">
                    {point}<span className="mt-2 flex items-center gap-1 text-xs text-[color:var(--amber-ink)]">查看详情 <ChevronRight size={12} /></span>
                  </span>
                </button>
              )}
            </li>)}
          </ul> : <p className="text-sm text-muted-foreground">无可展示内容</p>
        ) : (
          <article className="space-y-5 break-words">
            <h2 ref={headingRef} tabIndex={-1} className="text-lg font-medium leading-relaxed outline-none">
              {card.items?.[selected]?.title || card.points[selected]}
            </h2>
            {loading && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 size={16} className="animate-spin" /> 正在查找来源并整理详情…</p>}
            {error && <div role="alert" className="rounded-[10px] border p-4" style={{ borderColor: "var(--glass-border)" }}>
              <p className="text-sm leading-relaxed">{error}</p>
              <button type="button" onClick={() => void openDetail(selected, true)} className="btn btn-quiet mt-3 h-7 px-2.5 text-xs"><RefreshCw size={14} /> 重新加载详情</button>
            </div>}
            {detail && <>
              <p className="text-xs text-muted-foreground">联网整理 · 请结合来源原文核实</p>
              {detail.summary && <p className="text-base leading-relaxed">{detail.summary}</p>}
              {detail.whats_happening && <section><h3 className="mb-2 text-sm font-medium text-[color:var(--amber-ink)]">详细内容</h3><p className="whitespace-pre-wrap text-sm leading-7">{detail.whats_happening}</p></section>}
              {detail.key_facts.length > 0 && <section><h3 className="mb-2 text-sm font-medium text-[color:var(--amber-ink)]">关键信息</h3><ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed">{detail.key_facts.map((fact, index) => <li key={index}>{fact}</li>)}</ul></section>}
              {detail.background && <section><h3 className="mb-2 text-sm font-medium text-[color:var(--amber-ink)]">背景</h3><p className="whitespace-pre-wrap text-sm leading-7">{detail.background}</p></section>}
              <section className="border-t pt-4" style={{ borderColor: "var(--glass-border)" }}>
                <h3 className="mb-3 text-sm font-medium text-[color:var(--amber-ink)]">来源原文</h3>
                <ul className="space-y-3">{detail.sources.map((source, index) => <li key={`${source.url}-${index}`}>
                  <button type="button" onClick={() => void openExternal(source.url)} className="flex w-full items-start gap-2 text-left text-sm text-foreground/90 hover:text-[color:var(--amber-ink)] hover:underline">
                    <ArrowUpRight size={15} className="mt-0.5 shrink-0" /><span>{source.index !== undefined && <span className="mr-1.5 text-[color:var(--amber-ink)]">[{source.index}]</span>}{source.title || "查看来源原文"}<span className="mt-1 block text-xs text-muted-foreground">{source.site_name || new URL(source.url).hostname}</span></span>
                  </button>
                </li>)}</ul>
              </section>
            </>}
          </article>
        )}
      </div>
      {selected === null && cardUrl && <div className="shrink-0 border-t px-5 py-4 sm:px-8" style={{ borderColor: "var(--glass-border)" }}>
        <button type="button" onClick={() => void openExternal(cardUrl)} className="btn btn-quiet h-7 px-2.5 text-xs">查看卡片来源 <ArrowUpRight size={14} /></button>
      </div>}
    </div>
  );
}
