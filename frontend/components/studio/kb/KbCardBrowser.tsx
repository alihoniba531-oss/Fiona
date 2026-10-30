"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { studioErrorMessage } from "@/lib/studio";
import { getKbCard, kbCardTypeLabel, listKbCards, type KbCard, type KbCardSummary, type KbCardType } from "@/lib/studio-kb";
import KbCardDetail from "./KbCardDetail";

export default function KbCardBrowser({ type, owner }: { type: KbCardType; owner: string }) {
  const [cards, setCards] = useState<KbCardSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [card, setCard] = useState<KbCard | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const { beginRequest: beginRead } = useAccountRequest(owner);

  const load = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    setLoading(true);
    try {
      const next = await listKbCards(type, undefined, request.signal);
      if (!request.isCurrent()) return;
      const list = Array.isArray(next) ? next : [];
      setCards(list);
      setSelectedId(previous => list.some(item => item.id === previous) ? previous : list[0]?.id ?? "");
      setError("");
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead, type]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const loadDetail = useCallback(async () => {
    if (!selectedId) return;
    const request = beginRead();
    if (!request) return;
    setDetailLoading(true); setDetailError("");
    try {
      const next = await getKbCard(selectedId, request.signal);
      if (request.isCurrent()) setCard(next);
    } catch (cause) { if (request.isCurrent()) { setCard(null); setDetailError(studioErrorMessage(cause)); } }
    finally { if (request.isCurrent()) setDetailLoading(false); }
  }, [beginRead, selectedId]);
  useEffect(() => { void Promise.resolve().then(loadDetail); }, [loadDetail]);

  const allTags = Array.from(new Set(cards.flatMap(item => item.tags ?? []))).sort((left, right) => left.localeCompare(right));
  const needle = query.trim().toLowerCase();
  const filtered = cards.filter(item => {
    if (tag && !(item.tags ?? []).includes(tag)) return false;
    if (!needle) return true;
    return [item.id, item.title, item.summary, ...(item.tags ?? [])].join(" ").toLowerCase().includes(needle);
  });

  return <div className="min-w-0 space-y-4">
    <div className="min-w-0 space-y-3">
      <label className="block min-w-0"><span className="sr-only">搜索卡片</span><input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索卡片 id、标题或摘要" className="ceramic-card w-full min-w-0 rounded-[10px] border-0 px-3 py-3 text-fs-16.5 leading-[1.8] text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)]" /></label>
      {allTags.length > 0 && <div className="flex min-w-0 flex-wrap gap-1" aria-label="标签筛选">
        <button type="button" aria-pressed={tag === ""} onClick={() => setTag("")} className={`chip min-h-10 ${tag === "" ? "chip-on" : ""}`}>全部</button>
        {allTags.map(value => <button key={value} type="button" aria-pressed={tag === value} onClick={() => setTag(previous => previous === value ? "" : value)} className={`chip min-h-10 max-w-full whitespace-normal break-words text-left ${tag === value ? "chip-on" : ""}`}>{value}</button>)}
      </div>}
    </div>
    {loading ? <LoadingState>正在读取{kbCardTypeLabel(type)}卡片…</LoadingState>
      : error ? <ErrorNotice message={error} retry={() => { void load(); }} />
      : cards.length === 0 ? <EmptyState>还没有{kbCardTypeLabel(type)}卡片。</EmptyState>
      : <div className="grid min-w-0 grid-cols-1 items-start gap-4 @[900px]:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-2" aria-label={`${kbCardTypeLabel(type)}卡片列表`}>
          {filtered.length === 0 ? <EmptyState>没有匹配的卡片，换个关键词或标签试试。</EmptyState> : filtered.map(item => <button key={item.id} type="button" aria-pressed={selectedId === item.id} onClick={() => setSelectedId(item.id)} className={`ceramic-card block w-full min-w-0 rounded-xl p-3 text-left ${selectedId === item.id ? "ring-1 ring-[color:var(--ink)]" : ""}`}>
            <span className="block break-words text-fs-15">{item.title}</span>
            <span className="readout mt-1 block break-words">{item.id}</span>
            <span className="mt-1 block break-words text-fs-12 leading-relaxed text-[color:var(--ink2)]">{item.summary}</span>
            {Array.isArray(item.tags) && item.tags.length > 0 && <span className="mt-2 flex flex-wrap gap-1">{item.tags.map(value => <span key={value} className="tag whitespace-normal break-words">{value}</span>)}</span>}
          </button>)}
        </div>
        <div className="min-w-0">
          {detailLoading ? <LoadingState>正在读取卡片详情…</LoadingState>
            : detailError ? <ErrorNotice message={detailError} retry={() => { void loadDetail(); }} />
            : card ? <KbCardDetail card={card} />
            : <EmptyState>从左侧选择一张卡片查看详情。</EmptyState>}
        </div>
      </div>}
  </div>;
}
