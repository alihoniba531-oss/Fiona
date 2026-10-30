"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Plus } from "lucide-react";
import Glaze from "@/components/Glaze";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { ApiError } from "@/lib/agents";
import { createStudioFromSource, formatStudioDate, getStudioAccess, listStudioProjects, studioErrorMessage, studioHref, type StudioAccess, type StudioProject, type StudioCreateInput } from "@/lib/studio";
import { useAccountIdentity, useAccountIdentityPending, useAccountRequest } from "@/lib/useAccountIdentity";
import StudioShell from "./StudioShell";
import StudioBudget from "./StudioBudget";
import { CreateProjectDialog } from "./CreateProjectDialog";
export { CreateProjectDialog } from "./CreateProjectDialog";

export default function StudioShelf() {
  const owner = useAccountIdentity();
  const identityPending = useAccountIdentityPending();
  const embedded = useSearchParams().get("embed") === "1";
  return <Shelf key={owner} owner={owner} embedded={embedded} identityPending={identityPending} />;
}
function Shelf({ owner, embedded, identityPending = false }: { owner: string; embedded: boolean; identityPending?: boolean }) {
  const router = useRouter();
  const [projects, setProjects] = useState<StudioProject[]>([]);
  const [access, setAccess] = useState<StudioAccess | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);
  const refresh = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    try {
      let gate: StudioAccess;
      try { gate = await getStudioAccess(request.signal); }
      catch (cause) {
        if (cause instanceof ApiError && cause.status === 404) {
          if (request.isCurrent()) { setUnavailable(true); setAccess(null); setProjects([]); setError(""); }
          return;
        }
        throw cause;
      }
      const next = await listStudioProjects(request.signal);
      if (request.isCurrent()) { setAccess(gate); setProjects(next); setUnavailable(false); setError(""); }
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead]);
  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  const create = async (input: StudioCreateInput) => {
    if (busyRef.current) return;
    const request = beginMutation();
    if (!request) return;
    busyRef.current = true; setBusy(true);
    try {
      const project = await createStudioFromSource(input, request.signal);
      if (!request.isCurrent()) return;
      setCreating(false);
      await refresh();
      if (request.isCurrent()) router.push(studioHref(`/studio/${encodeURIComponent(project.id)}`, embedded));
    } finally { busyRef.current = false; if (request.isCurrent()) setBusy(false); }
  };
  return <StudioShell embedded={embedded}>
    <header className="mb-6">
      {!embedded && <Link href="/" className="mb-2 inline-flex min-h-10 items-center gap-1 text-fs-13 text-[color:var(--ink2)]"><ArrowLeft size={14} />回到对话</Link>}
      <div className="flex min-h-10 flex-wrap items-center justify-between gap-3"><h1 className={`text-fs-30 tracking-[.24em]${embedded ? " sr-only" : ""}`}>短片工作室</h1>
        {access && !unavailable && <button type="button" className={`btn btn-primary min-h-10${embedded ? " ml-auto" : ""}`} onClick={() => setCreating(true)}><Plus size={15} />新建项目</button>}
      </div>
      {embedded && <a href="/studio" target="_blank" rel="noopener noreferrer" className="btn btn-quiet mt-3 min-h-10">在新页面打开</a>}
      {access && <StudioBudget access={access} />}
    </header>
    {!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : <EmptyState>请登录后打开工作室。<Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">前往登录</Link></EmptyState>)
      : loading ? <LoadingState>正在整理你的项目…</LoadingState>
      : unavailable ? <EmptyState>暂未开放</EmptyState>
      : error ? <ErrorNotice message={error} retry={() => void refresh()} />
      : projects.length === 0 ? <Glaze variant="panel" lens={false} backdrop={!embedded} className="rounded-2xl p-6"><EmptyState>还没有项目，点击「新建项目」开始试拍。</EmptyState></Glaze>
      : <div className="grid min-w-0 grid-cols-1 gap-4 @[640px]:grid-cols-2 @[1050px]:grid-cols-3">{projects.map(project => <Link key={project.id} href={studioHref(`/studio/${encodeURIComponent(project.id)}`, embedded)} className="ceramic-card block min-w-0 rounded-2xl p-5">
        <h2 className="break-words text-fs-22 tracking-[.24em]">{project.title}</h2><span className="chip mt-4">{project.aspect}</span>
        <p className="readout mt-4 text-fs-12 text-[color:var(--ink2)]">最近更新 {formatStudioDate(project.updated_at)}</p>
      </Link>)}</div>}
    {creating && <CreateProjectDialog owner={owner} embedded={embedded} busy={busy} onCreate={create} onClose={() => setCreating(false)} />}
  </StudioShell>;
}
