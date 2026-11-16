"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Plus, RefreshCw } from "lucide-react";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { listDiscussGroups, type DiscussSummary } from "@/lib/discuss";
import { discussErrorMessage, discussHref, discussIsActive, discussNeedsAuthor, discussStatusLabel } from "@/lib/discussLogic";
import { formatNovelDate } from "@/lib/novels";
import { useAccountIdentity, useAccountIdentityPending, useAccountRequest } from "@/lib/useAccountIdentity";

export default function DiscussShelf({ embedded }: { embedded: boolean }) {
  const owner = useAccountIdentity();
  const identityPending = useAccountIdentityPending();
  return <Shelf key={owner} owner={owner} identityPending={identityPending} embedded={embedded} />;
}

function Shelf({ owner, embedded, identityPending = false }: { owner: string; embedded: boolean; identityPending?: boolean }) {
  const [groups, setGroups] = useState<DiscussSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [blocked, setBlocked] = useState(false);
  const { beginRequest } = useAccountRequest(owner);
  const refresh = useCallback(async () => {
    const request = beginRequest();
    if (!request) return;
    try {
      const next = await listDiscussGroups(request.signal);
      if (request.isCurrent()) { setGroups(next); setError(""); setBlocked(false); }
    } catch (cause) {
      if (request.isCurrent()) {
        const status = errorStatus(cause);
        setError(discussErrorMessage(cause));
        setBlocked(status === 404 || status === 403);
      }
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [beginRequest]);
  const running = groups.some(group => discussIsActive(group.status));
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
  const newGroupHref = discussHref("/discuss/new", embedded);
  const showCreate = !!owner && !loading && !error && groups.length > 0;
  return <div className={embedded ? "[&_header_h1]:sr-only" : ""}>
    <header className="mb-6">
      {!embedded && <Link href="/" className="mb-2 inline-flex min-h-10 items-center gap-1 text-fs-13 text-[color:var(--ink2)]"><ArrowLeft size={14} />回到对话</Link>}
      <div className="flex min-h-10 flex-wrap items-center justify-between gap-3">
        <h1 className="text-fs-30 tracking-[.24em]">讨论群</h1>
        {showCreate && <Link href={newGroupHref} className={`btn btn-primary min-h-10${embedded ? " ml-auto" : ""}`}><Plus size={15} />新建讨论群</Link>}
      </div>
      <p className="mt-3 text-fs-15 text-pretty leading-[1.9] text-[color:var(--ink2)]">提一个诉求，一组智能体分工调研、互相质疑，写出带来源的成果。</p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" disabled={loading || !owner} className="btn btn-quiet min-h-10" onClick={() => { setLoading(true); void refresh(); }}><RefreshCw size={14} className={loading && owner ? "animate-spin" : ""} />刷新</button>
        {embedded && <a href="/discuss" target="_blank" rel="noopener noreferrer" className="btn btn-quiet min-h-10 mobile:hidden">在新页面打开</a>}
      </div>
    </header>
    {!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : <EmptyState>请登录后使用讨论群。<Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">前往登录</Link></EmptyState>)
      : error ? <ErrorNotice message={error} retry={blocked ? undefined : () => void refresh()} />
      : loading ? <LoadingState>正在加载讨论群…</LoadingState>
      : groups.length === 0 ? <div className="ceramic-card rounded-2xl p-8 mobile:p-5"><EmptyState>
          <h2 className="text-fs-22 leading-[inherit] tracking-[.12em] text-[color:var(--ink)]">建你的第一个讨论群</h2>
          <p className="my-4 text-fs-15 text-pretty">写下想查清或想做成的事，剩下的交给他们。</p>
          <Link href={newGroupHref} className="btn btn-primary min-h-10">新建讨论群</Link>
        </EmptyState></div>
      : <div className="grid min-w-0 grid-cols-1 gap-4 @[640px]:grid-cols-2">
          {groups.map(group => <Link key={group.id} href={discussHref(`/discuss/${encodeURIComponent(group.id)}`, embedded)} className="ceramic-card block min-w-0 rounded-2xl p-5 outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)]">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h2 className="min-w-0 break-words text-fs-22 leading-[inherit] tracking-[.12em]">{group.title}</h2>
              <span className="tag">{discussStatusLabel(group)}</span>
            </div>
            {discussNeedsAuthor(group) && <p className="mt-3 inline-flex min-h-10 items-center gap-2 border-b border-[color:var(--ink)] text-fs-15">待你处理</p>}
            <div className="mt-5 space-y-2 text-fs-13 text-[color:var(--ink2)]">
              <p>进度 <span className="readout text-[color:var(--ink)]">{group.round === 0 ? "立项" : `第 ${group.round} / ${group.max_rounds} 轮`}</span></p>
              <p>草莓 <span className="readout text-[color:var(--ink)]">{group.spent_strawberries} / {group.budget_strawberries}</span></p>
              <p>成果 <span className="readout text-[color:var(--ink)]">{group.output_version >= 1 ? `第 ${group.output_version} 版` : "还没有成果"}</span></p>
            </div>
            <p className="readout mt-5 break-words text-fs-12 text-[color:var(--ink2)]">最近更新 {formatNovelDate(group.updated_at)}</p>
          </Link>)}
        </div>}
  </div>;
}

function errorStatus(error: unknown): number | undefined {
  return error !== null && typeof error === "object"
    ? (error as { status?: number }).status
    : undefined;
}
