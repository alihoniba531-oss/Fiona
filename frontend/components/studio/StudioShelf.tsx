"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Plus } from "lucide-react";
import Glaze from "@/components/Glaze";
import { novelFieldClass } from "@/components/novel/NovelModelFields";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { ApiError } from "@/lib/agents";
import { createStudioProject, formatStudioDate, getStudioAccess, listStudioProjects, studioErrorMessage, studioHref, type StudioAccess, type StudioProject } from "@/lib/studio";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";
import StudioShell from "./StudioShell";
import StudioBudget from "./StudioBudget";

export default function StudioShelf() {
  const owner = useAccountIdentity();
  const embedded = useSearchParams().get("embed") === "1";
  return <Shelf key={owner} owner={owner} embedded={embedded} />;
}
function Shelf({ owner, embedded }: { owner: string; embedded: boolean }) {
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
  const create = async (title: string, aspect: StudioProject["aspect"]) => {
    if (busyRef.current) return;
    const request = beginMutation();
    if (!request) return;
    busyRef.current = true; setBusy(true);
    try {
      const project = await createStudioProject({ title, aspect }, request.signal);
      if (!request.isCurrent()) return;
      setCreating(false);
      await refresh();
      if (request.isCurrent()) router.push(studioHref(`/studio/${encodeURIComponent(project.id)}`, embedded));
    } finally { busyRef.current = false; if (request.isCurrent()) setBusy(false); }
  };
  return <StudioShell embedded={embedded}>
    <header className="mb-6">
      {!embedded && <Link href="/" className="mb-2 inline-flex min-h-10 items-center gap-1 text-sm text-[color:var(--ink2)]"><ArrowLeft size={14} />回到对话</Link>}
      <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-[28px] tracking-[.24em]">短片工作室</h1>
        {access && !unavailable && <button type="button" className="btn btn-primary min-h-10" onClick={() => setCreating(true)}><Plus size={15} />新建项目</button>}
      </div>
      {embedded && <a href="/studio" target="_blank" rel="noopener noreferrer" className="btn btn-quiet mt-3 min-h-10">在新页面打开</a>}
      {access && <StudioBudget access={access} />}
    </header>
    {!owner ? <EmptyState>请登录后打开工作室。<Link href="/login" className="ml-2 underline">前往登录</Link></EmptyState>
      : loading ? <LoadingState>正在整理你的项目…</LoadingState>
      : unavailable ? <EmptyState>暂未开放</EmptyState>
      : error ? <ErrorNotice message={error} retry={() => void refresh()} />
      : projects.length === 0 ? <Glaze variant="panel" lens={false} backdrop={!embedded} className="rounded-2xl p-6"><EmptyState>还没有项目，点击「新建项目」开始试拍。</EmptyState></Glaze>
      : <div className="grid min-w-0 grid-cols-1 gap-4 @[640px]:grid-cols-2 @[1050px]:grid-cols-3">{projects.map(project => <Link key={project.id} href={studioHref(`/studio/${encodeURIComponent(project.id)}`, embedded)} className="ceramic-card block min-w-0 rounded-2xl p-5">
        <h2 className="break-words text-xl tracking-[.24em]">{project.title}</h2><span className="chip mt-4">{project.aspect}</span>
        <p className="readout mt-4 text-xs text-[color:var(--ink2)]">最近更新 {formatStudioDate(project.updated_at)}</p>
      </Link>)}</div>}
    {creating && <CreateProjectDialog busy={busy} onCreate={create} onClose={() => setCreating(false)} />}
  </StudioShell>;
}
export function CreateProjectDialog({ busy, onCreate, onClose }: { busy: boolean; onCreate: (title: string, aspect: StudioProject["aspect"]) => Promise<void>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState("");
  const [aspect, setAspect] = useState<StudioProject["aspect"]>("16:9");
  const [error, setError] = useState("");
  const lock = useRef(false);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  const submit = async () => {
    if (lock.current || busy) return;
    if (!title.trim()) { setError("请填写项目标题。"); return; }
    lock.current = true; setError("");
    try { await onCreate(title.trim(), aspect); }
    catch (cause) { setError(studioErrorMessage(cause)); }
    finally { lock.current = false; }
  };
  return <dialog ref={ref} aria-labelledby="studio-create-title" onCancel={event => { if (busy || lock.current) event.preventDefault(); else onClose(); }} className="m-auto max-h-[85dvh] w-[min(560px,calc(100vw-32px))] max-w-full overflow-y-auto rounded-2xl border border-[color:var(--carve)] bg-[color:var(--paper)] p-5 text-[color:var(--ink)] backdrop:bg-[color:var(--scrim)]">
    <h2 id="studio-create-title" className="mb-5 text-xl tracking-[.24em]">新建项目</h2>
    {error && <ErrorNotice message={error} />}
    <label className="mt-4 block space-y-2"><span>项目标题</span><input autoFocus maxLength={200} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} className={novelFieldClass} /></label>
    <fieldset className="my-5" disabled={busy}><legend className="mb-2">画幅</legend><div className="flex flex-wrap gap-2">{(["16:9", "9:16"] as const).map(value => <button key={value} type="button" aria-pressed={aspect === value} className={`chip min-h-10 min-w-10 ${aspect === value ? "chip-on" : ""}`} onClick={() => setAspect(value)}>{value}</button>)}</div></fieldset>
    <div className="flex flex-wrap gap-3"><button type="button" className="btn btn-primary min-h-10" disabled={busy || !title.trim()} onClick={() => void submit()}>{busy ? "创建中…" : "创建项目"}</button><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onClose}>取消</button></div>
  </dialog>;
}
