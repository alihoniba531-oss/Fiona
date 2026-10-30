"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Plus, RefreshCw } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import InkLandscape from "@/components/InkLandscape";
import Glaze from "@/components/Glaze";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { useNovelEmbedClose } from "@/components/novel/NovelShell";
import { formatNovelDate, listNovels, novelErrorMessage, novelHref, novelStatusLabel, type NovelSummary } from "@/lib/novels";
import { useAccountIdentity, useAccountIdentityPending, useAccountRequest } from "@/lib/useAccountIdentity";

export default function NovelShelf() {
  const embedded = useSearchParams().get("embed") === "1";
  const owner = useAccountIdentity();
  const identityPending = useAccountIdentityPending();
  return <Shelf key={owner} owner={owner} identityPending={identityPending} embedded={embedded} />;
}
function Shelf({ owner, embedded, identityPending = false }: { owner: string; embedded: boolean; identityPending?: boolean }) {
  useNovelEmbedClose(embedded);
  const [books, setBooks] = useState<NovelSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { beginRequest } = useAccountRequest(owner);
  const refresh = useCallback(async () => {
    const request = beginRequest();
    if (!request) return;
    try {
      const summaries = await listNovels(request.signal);
      if (request.isCurrent()) { setBooks(summaries); setError(""); }
    } catch (cause) {
      if (request.isCurrent()) setError(novelErrorMessage(cause, true));
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [beginRequest]);
  const running = books.some(book => book.status === "setup_running" || book.status === "running");
  useEffect(() => { void Promise.resolve().then(() => { if (!document.hidden) return refresh(); }); }, [refresh]);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const tick = async () => {
      if (document.hidden || stopped) return;
      await refresh();
      if (!stopped && running) timer = setTimeout(tick, 3000);
    };
    const visibility = () => { clearTimeout(timer); if (!document.hidden) void tick(); };
    if (running && !document.hidden) timer = setTimeout(tick, 3000);
    document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [refresh, running]);
  const newBookHref = novelHref("/novels/new", embedded);
  return <div className={`relative flex min-w-0 ${embedded ? "min-h-full" : "h-dvh"} overflow-hidden`}>
    {!embedded && <><InkLandscape variant="page" /><Sidebar /></>}
    <main className={`relative z-[1] min-w-0 flex-1 overflow-y-auto text-[color:var(--ink)] ${embedded ? "" : "mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]"}`}>
      <header className="mx-auto max-w-[1200px] px-10 pb-7 pt-7 mobile:px-4 mobile:pt-4">
        {!embedded && <Link href="/" className="mb-2 inline-flex min-h-10 items-center gap-1 text-fs-13 text-[color:var(--ink2)]"><ArrowLeft size={14} />回到对话</Link>}
        <div className="flex min-h-10 flex-wrap items-center justify-between gap-3"><h1 className="text-fs-30 tracking-[.24em]">书斋</h1>{!(owner && !error && !loading && books.length === 0) && <Link href={newBookHref} className="btn btn-primary min-h-10"><Plus size={15} />新建一本</Link>}</div>
        <p className="mt-3 text-fs-15 text-pretty leading-[1.9] text-[color:var(--ink2)]">留一个故事思路，在这里和智能体一起把它写完。</p>
        <div className="mt-3 flex flex-wrap items-center gap-3"><button type="button" disabled={loading || !owner} className="btn btn-quiet min-h-10" onClick={() => { setLoading(true); void refresh(); }}><RefreshCw size={14} className={loading && owner ? "animate-spin" : ""} />{loading && owner ? "刷新中…" : "刷新"}</button>{embedded && <a href="/novels" target="_blank" rel="noopener noreferrer" className="btn btn-quiet min-h-10 mobile:hidden">在新页面打开</a>}</div>
      </header>
      <div className="mx-auto max-w-[1200px] px-10 pb-10 mobile:px-4">
        {!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : <EmptyState>请登录后查看你的书架。<Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">前往登录</Link></EmptyState>) : error ? <ErrorNotice message={error} retry={() => void refresh()} /> : loading ? <LoadingState>正在整理你的书架…</LoadingState> : books.length === 0 ? <Glaze variant="panel" lens={false} backdrop={!embedded} className="rounded-[18px] p-8 mobile:p-5"><EmptyState><h2 className="text-fs-22 leading-[inherit] tracking-[.12em] text-[color:var(--ink)]">开始你的第一本书</h2><p className="my-4 text-fs-15 text-pretty">只给一个思路，几位智能体替你推演整本书。</p><Link href={newBookHref} className="btn btn-primary min-h-10">新建一本</Link></EmptyState></Glaze> : <div className="grid grid-cols-2 gap-5 mobile:grid-cols-1 mobile:gap-3">
          {books.map(book => <Link key={book.id} href={novelHref(`/novels/${book.id}`, embedded)} className="ceramic-card min-w-0 rounded-[16px] p-6 outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] mobile:p-5">
            <div className="flex flex-wrap items-start justify-between gap-2"><h2 className="min-w-0 break-words text-fs-22 leading-[inherit] tracking-[.12em]">{book.title || "立项中"}</h2><span className="tag">{novelStatusLabel(book)}</span></div>
            {(book.status.startsWith("awaiting_") || book.status === "paused") && <p className="mt-3 inline-flex min-h-10 items-center gap-2 border-b border-[color:var(--ink)] text-fs-15 font-medium">待你处理</p>}
            <div className="mt-5 space-y-2 text-fs-13 text-[color:var(--ink2)]"><p>进度 <span className="readout text-[color:var(--ink)]">第 {book.chapters_done} / {book.max_chapters} 章</span></p><p>草莓 <span className="readout text-[color:var(--ink)]">{book.spent_strawberries} / {book.budget_strawberries}</span></p></div>
            <p className="readout mt-5 break-words text-fs-12 text-[color:var(--ink2)]">最近更新 {formatNovelDate(book.updated_at)}</p>
          </Link>)}
        </div>}
      </div>
    </main>
  </div>;
}
