"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import Glaze from "@/components/Glaze";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { ApiError } from "@/lib/agents";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";
import { useRovingTabs } from "@/lib/useRovingTabs";
import { cancelStudioJob, confirmStudioQuote, getBrainProviders, getStudioAccess, getStudioProject, hasStudioInflightJobs, linkStudioTask, listStudioJobs, patchStudioProject, recheckStudioJob, releaseStudioJob, studioErrorMessage, studioHref, type BrainProvider, type BrainProviderId, type StudioAccess, type StudioClipParams, type StudioJob, type StudioProject, type StudioQuote } from "@/lib/studio";
import StudioShell from "./StudioShell";
import StudioBudget from "./StudioBudget";
import ClipComposer from "./ClipComposer";
import QuoteDialog from "./QuoteDialog";
import ShotWall from "./ShotWall";
import BrainTrial, { BrainProviderPicker } from "./BrainTrial";
import SourcePanel from "./SourcePanel";
import BreakdownStage from "./BreakdownStage";
import CastingStage from "./CastingStage";

const stages = ["①拆解", "②定妆", "③分镜", "④镜头", "⑤成片"] as const;

export default function StudioWorkbench({ id, embedded = false }: { id: string; embedded?: boolean }) {
  const owner = useAccountIdentity();
  return <AccountStudioWorkbench key={`${owner}:${id}`} id={id} owner={owner} embedded={embedded} />;
}
export function AccountStudioWorkbench({ id, owner, embedded }: { id: string; owner: string; embedded: boolean }) {
  const [project, setProject] = useState<StudioProject | null>(null);
  const [access, setAccess] = useState<StudioAccess | null>(null);
  const [jobs, setJobs] = useState<StudioJob[]>([]);
  const [providers, setProviders] = useState<BrainProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState("");
  const [stage, setStage] = useState(3);
  const stageTouched = useRef(false);
  const stageInitialized = useRef(false);
  const selectStage = useCallback((index: number) => { stageTouched.current = true; setStage(index); }, []);
  const tabProps = useRovingTabs(stages.length, stage, selectStage);
  const [busy, setBusy] = useState(false);
  const [quote, setQuote] = useState<StudioQuote | null>(null);
  const [refill, setRefill] = useState<{ token: number; params: StudioClipParams }>();
  const mutating = useRef(false);
  const inFlight = useRef(false);
  const reading = useRef(0);
  const readVersion = useRef(0);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);
  const refresh = useCallback(async (force = false, includeProject = true) => {
    if (!force && (mutating.current || reading.current)) return;
    const request = beginRead();
    if (!request) return;
    const version = ++readVersion.current;
    reading.current = version;
    try {
      let gate: StudioAccess;
      try { gate = await getStudioAccess(request.signal); }
      catch (cause) {
        if (cause instanceof ApiError && cause.status === 404) {
          if (request.isCurrent()) { setUnavailable(true); setProject(null); setAccess(null); setJobs([]); inFlight.current = false; setError(""); }
          return;
        }
        throw cause;
      }
      const [nextProject, nextJobs, nextProviders] = await Promise.all([
        includeProject ? getStudioProject(id, request.signal) : null,
        listStudioJobs(id, request.signal),
        includeProject ? getBrainProviders(request.signal) : null,
      ]);
      if (!request.isCurrent()) return;
      if (nextProject && nextProject.id !== id) throw new Error("项目信息不匹配，请重新打开项目。");
      // Video polling and rendering remain separate from synchronous brain jobs.
      const videoJobs = nextJobs.filter(job => !("kind" in job) || job.kind === "i2v");
      inFlight.current = hasStudioInflightJobs(videoJobs);
      if (nextProject) {
        setProject(nextProject);
        // Choose the landing stage once; refreshes must preserve the author's
        // later mouse or keyboard choice, even if source metadata changes.
        if (!stageInitialized.current) {
          stageInitialized.current = true;
          if (!stageTouched.current && nextProject.source_kind) setStage(0);
        }
      }
      if (Array.isArray(nextProviders)) setProviders(nextProviders);
      setJobs(videoJobs); setAccess(gate); setUnavailable(false); setError("");
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (reading.current === version) reading.current = 0; if (request.isCurrent()) setLoading(false); }
  }, [beginRead, id]);
  useEffect(() => { void Promise.resolve().then(() => refresh()); }, [refresh]);
  const running = hasStudioInflightJobs(jobs);
  useEffect(() => {
    if (!running) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      clearTimeout(timer);
      if (!stopped && !document.hidden && inFlight.current) timer = setTimeout(tick, 5000);
    };
    const tick = async () => {
      if (stopped || document.hidden || !inFlight.current) return;
      await refresh(false, false); schedule();
    };
    const visibility = () => { clearTimeout(timer); if (!document.hidden) void tick(); };
    schedule(); document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [refresh, running]);
  const setComposerBusy = useCallback((next: boolean) => { mutating.current = next; setBusy(next); }, []);
  const changed = useCallback(() => refresh(true), [refresh]);
  const polled = useCallback(() => refresh(false, false), [refresh]);
  const mutate = async (action: (signal: AbortSignal) => Promise<unknown>) => {
    if (mutating.current) return;
    const request = beginMutation();
    if (!request) return;
    mutating.current = true; setBusy(true);
    try { await action(request.signal); }
    finally {
      // Mutations may have reached the server even when their response failed.
      if (request.isCurrent()) await refresh(true);
      mutating.current = false;
      if (request.isCurrent()) setBusy(false);
    }
  };
  const changeProvider = async (provider: BrainProviderId) => {
    try { await mutate(signal => patchStudioProject(id, provider, signal)); }
    catch (cause) { setError(studioErrorMessage(cause)); }
  };
  return <StudioShell embedded={embedded}>
    <header className="mb-5">
      <Link href={studioHref("/studio", embedded)} className="mb-2 inline-flex min-h-10 items-center gap-1 text-sm text-[color:var(--ink2)]"><ArrowLeft size={14} />全部项目</Link>
      <Glaze variant="panel" lens={false} backdrop={!embedded} className="min-w-0 rounded-2xl p-5">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3"><h1 className="min-w-0 break-words text-[26px] tracking-[.24em]">{project?.title ?? "短片工作室"}</h1>{project && <span className="chip">{project.aspect}</span>}</div>
        {embedded && <a href={`/studio/${encodeURIComponent(id)}`} target="_blank" rel="noopener noreferrer" className="btn btn-quiet mt-3 min-h-10">在新页面打开</a>}
        {access && <StudioBudget access={access} />}
        {project && <BrainProviderPicker providers={providers} current={project.brain_provider ?? "claude"} busy={busy} onChange={changeProvider} />}
      </Glaze>
    </header>
    {!owner ? <EmptyState>请登录后打开工作室。</EmptyState> : loading ? <LoadingState>正在打开项目…</LoadingState> : unavailable ? <EmptyState>暂未开放</EmptyState> : <>
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      {project && <>
        <nav role="tablist" aria-label="短片制作阶段" className="mb-5 flex min-w-0 border-b border-[color:var(--carve)]">{stages.map((label, index) => <button key={label} id={`studio-stage-${index}`} type="button" role="tab" aria-selected={stage === index} aria-controls={`studio-panel-${index}`} {...tabProps(index)} onClick={() => selectStage(index)} className={`min-h-10 min-w-0 flex-1 border-b px-1 py-3 text-[13px] @[640px]:text-base ${stage === index ? "border-[color:var(--ink)] text-[color:var(--ink)]" : "border-transparent text-[color:var(--ink2)]"}`}>{label}</button>)}</nav>
        {stages.map((label, index) => <section key={label} role="tabpanel" id={`studio-panel-${index}`} aria-labelledby={`studio-stage-${index}`} hidden={stage !== index} className="min-w-0">
          {index === 0 ? <>{stage === 0 && <SourcePanel projectId={id} owner={owner} busy={busy} onChanged={changed} />}<div className="min-w-0 space-y-5">{stage === 0 && (project.source_kind ? <BreakdownStage project={project} owner={owner} providers={providers} busy={busy} onBusyChange={setComposerBusy} onChanged={changed} /> : <EmptyState>先关联作品才能拆解</EmptyState>)}<details className="min-w-0 rounded-2xl border border-[color:var(--carve)] p-4"><summary className="min-h-10 cursor-pointer py-2 tracking-[.12em]">试读与三家对比</summary><div className="min-w-0 pt-3">{project.brain_provider ? <BrainTrial projectId={id} owner={owner} provider={project.brain_provider} providers={providers} busy={busy} onBusyChange={setComposerBusy} onChanged={changed} onPoll={polled} onProviderChange={changeProvider} /> : <EmptyState>请先选择导演模型</EmptyState>}</div></details></div></> : index === 1 ? <>{stage === 1 && <CastingStage project={project} owner={owner} busy={busy} onBusyChange={setComposerBusy} onChanged={changed} />}</> : index === 3 ? <div className="grid min-w-0 grid-cols-1 items-start gap-5 @[1120px]:grid-cols-[minmax(300px,.8fr)_minmax(0,1.5fr)]">
            <ClipComposer projectId={id} owner={owner} busy={busy} refill={refill} onQuote={setQuote} onBusyChange={setComposerBusy} onChanged={changed} />
            <ShotWall jobs={jobs} busy={busy} onCancel={job => mutate(signal => cancelStudioJob(job.id, signal))} onRecheck={job => mutate(signal => recheckStudioJob(job.id, signal))} onLinkTask={(job, taskId) => mutate(signal => linkStudioTask(job.id, taskId, signal))} onRelease={job => mutate(signal => releaseStudioJob(job.id, signal))} onRefill={params => { setRefill(previous => ({ token: (previous?.token ?? 0) + 1, params })); selectStage(3); }} />
          </div> : <EmptyState>这一阶段将在后续版本开放</EmptyState>}
        </section>)}
      </>}
    </>}
    {quote && <QuoteDialog quote={quote} busy={busy} onClose={() => setQuote(null)} onConfirm={async () => {
      await mutate(async signal => { await confirmStudioQuote(quote.id, signal); if (!signal.aborted) setQuote(null); });
    }} />}
  </StudioShell>;
}
