"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { ApiError } from "@/lib/agents";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { releaseStudioJob, studioErrorMessage, type BrainProvider, type BrainProviderId, type StudioProject } from "@/lib/studio";
import { addStudioBible, approveStudioEpisodes, archiveStudioBible, breakdownInflight, cancelStudioBreakdown, downloadStudioBreakdown, getStudioBible, getStudioBreakdown, getStudioEpisodes, mergeStudioBible, operateStudioEpisodes, patchEpisodeSettings, patchStudioBible, patchStudioSynopsis, quoteBreakdownRetry, quoteStudioBreakdown, retryBreakdownChunk, startStudioBreakdown, type BreakdownChunk, type BreakdownQuote, type EpisodeOperation, type StudioBibleEntry, type StudioBreakdown, type StudioEpisodePlan } from "@/lib/studio-breakdown";
import BreakdownPanel from "./BreakdownPanel";
import BreakdownQuoteDialog from "./BreakdownQuoteDialog";
import BibleTable from "./BibleTable";
import EpisodePlan from "./EpisodePlan";
import SynopsisPanel from "./SynopsisPanel";
import BreakdownDialog from "./BreakdownDialog";

export default function BreakdownStage({ project, owner, providers, busy: outerBusy = false, onBusyChange, onChanged }: { project: StudioProject; owner: string; providers: BrainProvider[]; busy?: boolean; onBusyChange: (busy: boolean) => void; onChanged: () => Promise<void> }) {
  const [breakdown, setBreakdown] = useState<StudioBreakdown | null>(null);
  const [bible, setBible] = useState<StudioBibleEntry[]>([]);
  const [plan, setPlan] = useState<StudioEpisodePlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [readError, setReadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingSettings, setPendingSettings] = useState<{ min: number; max: number } | null>(null);
  const [quote, setQuote] = useState<{ value: BreakdownQuote; settings?: { min: number; max: number }; affectsApproved?: boolean; replacesPartial?: boolean; retry?: { chunk: BreakdownChunk; provider: BrainProviderId; breakdownId: string } } | null>(null);
  const locked = useRef(false);
  const reading = useRef(false);
  const currentBreakdown = useRef<StudioBreakdown | null>(null);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);
  const id = project.id;
  const refresh = useCallback(async (force = false) => {
    if (!force && (locked.current || reading.current)) return;
    const request = beginRead(); if (!request) return;
    reading.current = true;
    try {
      // Reading the breakdown settles completed jobs and publishes their results.
      // Read its derived tables only after that publication has finished.
      const next = await getStudioBreakdown(id, request.signal);
      if (!request.isCurrent()) return;
      const [entries, episodes] = await Promise.all([getStudioBible(id, request.signal), getStudioEpisodes(id, request.signal)]);
      if (!request.isCurrent()) return;
      currentBreakdown.current = next; setBreakdown(next); setBible(entries); setPlan(episodes); setReadError("");
    } catch (cause) { if (request.isCurrent()) setReadError(studioErrorMessage(cause)); }
    finally { reading.current = false; if (request.isCurrent()) setLoading(false); }
  }, [id, beginRead]);
  useEffect(() => { void Promise.resolve().then(() => refresh(true)); }, [refresh, project.snapshot_no]);
  const running = breakdownInflight(breakdown);
  useEffect(() => {
    if (!running) return;
    let stopped = false, pending = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => { clearTimeout(timer); if (!stopped && !document.hidden && breakdownInflight(currentBreakdown.current)) timer = setTimeout(tick, 5000); };
    const tick = async () => { if (stopped || pending || document.hidden || !breakdownInflight(currentBreakdown.current)) return; pending = true; try { await refresh(); } finally { pending = false; schedule(); } };
    const visibility = () => { clearTimeout(timer); if (!document.hidden) void tick(); };
    schedule(); document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [refresh, running]);
  useEffect(() => () => onBusyChange(false), [onBusyChange]);
  const mutate = async (action: (signal: AbortSignal) => Promise<unknown>, message: string, planConflict = false) => {
    if (locked.current || outerBusy && !busy) return;
    const request = beginMutation(); if (!request) return;
    locked.current = true; setBusy(true); onBusyChange(true); setError(""); setNotice("");
    try {
      await action(request.signal);
      if (request.isCurrent()) { await refresh(true); await onChanged(); if (request.isCurrent()) setNotice(message); }
    } catch (cause) {
      if (request.isCurrent()) {
        if (cause instanceof ApiError && cause.status === 409) { await refresh(true); setError(planConflict ? `分集方案已被更新，请核对刷新后的方案。${studioErrorMessage(cause)}` : studioErrorMessage(cause)); }
        else setError(studioErrorMessage(cause));
      }
      throw cause;
    } finally { locked.current = false; if (request.isCurrent()) { setBusy(false); onBusyChange(false); } }
  };
  // Direct actions report errors here; dialogs retain thrown errors for their own inline feedback.
  const direct = async (action: () => Promise<unknown>) => { try { await action(); } catch { /* The mutation already supplied a visible error. */ } };
  const changesApprovedTiming = (min: number, max: number) => !!plan?.g0_approved && plan.episodes.some(episode => episode.target_min == null && min !== (plan.settings?.episode_seconds_min ?? project.episode_seconds_min ?? 180) || episode.target_max == null && max !== (plan.settings?.episode_seconds_max ?? project.episode_seconds_max ?? 240));
  const saveSettings = (min: number, max: number) => mutate(signal => patchEpisodeSettings(id, { episode_seconds_min: min, episode_seconds_max: max }, signal), "每集目标时长已保存。");
  const requestSettings = async (min: number, max: number) => { if (changesApprovedTiming(min, max)) setPendingSettings({ min, max }); else await direct(() => saveSettings(min, max)); };
  const requestQuote = async (min: number, max: number, target?: number) => direct(() => mutate(async signal => {
    const result = await quoteStudioBreakdown(id, target, signal, { episode_seconds_min: min, episode_seconds_max: max });
    if (!signal.aborted) setQuote({ value: result, settings: { min, max }, affectsApproved: changesApprovedTiming(min, max), replacesPartial: breakdown?.status === "partial" });
  }, "报价已就绪，请核对后确认。"));
  const requestRetry = async (chunk: BreakdownChunk, provider: BrainProviderId) => {
    if (!breakdown) return;
    const bid = breakdown.id;
    await direct(() => mutate(async signal => { const result = await quoteBreakdownRetry(bid, chunk.id, provider, signal); if (!signal.aborted) setQuote({ value: result, retry: { chunk, provider, breakdownId: bid } }); }, "单批报价已就绪。"));
  };
  if (!project.source_kind) return <EmptyState>先关联作品才能拆解</EmptyState>;
  const disabled = busy || outerBusy;
  return <div className="min-w-0 space-y-5">
    {loading && <LoadingState>正在读取拆解与分集…</LoadingState>}
    {readError && <ErrorNotice message={readError} retry={() => void refresh(true)} />}
    {error && <ErrorNotice message={error} />}{notice && <p role="status" className="text-fs-13 text-[color:var(--ink2)]">{notice}</p>}
    <BreakdownPanel key={id} project={project} breakdown={breakdown} providers={providers} busy={disabled || loading} onQuote={requestQuote} onSettings={requestSettings} onRetry={requestRetry} onRelease={chunk => chunk.job_id ? mutate(signal => releaseStudioJob(chunk.job_id!, signal), "已释放预留，可以重新报价重跑。") : Promise.resolve()} onCancel={() => breakdown ? mutate(signal => cancelStudioBreakdown(breakdown.id, signal), "拆解已取消，正在执行的批次仍将结算。") : Promise.resolve()} />
    {breakdown && <>
      {breakdown.synopsis && <SynopsisPanel key={`${breakdown.id}:synopsis`} synopsis={breakdown.synopsis} novel={project.source_kind === "novel"} busy={disabled} onSave={value => mutate(signal => patchStudioSynopsis(id, value, signal), "梗概已保存。")} />}
      <BibleTable entries={bible} busy={disabled} onSave={(entryId, fields) => mutate(signal => patchStudioBible(entryId, fields, signal), "总表条目已保存。")} onAdd={(kind, fields) => mutate(signal => addStudioBible(id, kind, fields, signal), "总表条目已新增。")} onMerge={(keepId, mergeIds) => mutate(signal => mergeStudioBible(keepId, mergeIds, signal), "所选条目已合并。")} onArchive={entryId => mutate(signal => archiveStudioBible(entryId, signal), "条目已归档。")} />
      {plan && <EpisodePlan plan={plan} defaultMin={plan.settings?.episode_seconds_min ?? project.episode_seconds_min} defaultMax={plan.settings?.episode_seconds_max ?? project.episode_seconds_max} partial={breakdown.status === "partial" || breakdown.status === "running"} busy={disabled} onOperate={(operation: EpisodeOperation) => mutate(signal => operateStudioEpisodes(id, operation, signal), "分集方案已保存，已生成新版本。", true)} onApprove={revision => mutate(signal => approveStudioEpisodes(id, revision, signal), "G0 已批准。", true)} onExport={() => direct(() => mutate(signal => downloadStudioBreakdown(id, signal), "Markdown 已导出。"))} />}
    </>}
    {pendingSettings && <BreakdownDialog title="保存每集目标时长" confirmLabel="确认保存" busy={disabled} onClose={() => setPendingSettings(null)} onConfirm={async () => { await saveSettings(pendingSettings.min, pendingSettings.max); setPendingSettings(null); }}><p>每集目标时长将保存为 {pendingSettings.min}–{pendingSettings.max} 秒。当前已批准的分集方案使用了项目默认时长，保存后将生成新版本并退回待批准。</p></BreakdownDialog>}
    {quote && <BreakdownQuoteDialog quote={quote.value} retry={!!quote.retry} targetMin={quote.settings?.min} targetMax={quote.settings?.max} affectsApproved={quote.affectsApproved} replacesPartial={quote.replacesPartial} busy={disabled} onClose={() => setQuote(null)} onConfirm={async () => { const chosen = quote; await mutate(signal => chosen.retry ? retryBreakdownChunk(chosen.retry.breakdownId, chosen.retry.chunk.id, chosen.value.id, signal) : startStudioBreakdown(id, chosen.value.id, signal), chosen.retry ? "重跑已开始。" : "拆解已开始。"); setQuote(null); }} />}
  </div>;
}
