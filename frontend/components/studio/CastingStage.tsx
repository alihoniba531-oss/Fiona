"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Glaze from "@/components/Glaze";
import { ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { ApiError } from "@/lib/agents";
import { brainProviderName } from "@/lib/studio-breakdown";
import { releaseStudioJob, studioErrorMessage, type StudioProject } from "@/lib/studio";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { castingInflight, getCastingVoiceCatalog, getStudioCasting, putStudioCastingSetup, putStudioCastingStyle, quoteCastingLooks, quoteCastingSheets, quoteStudioCastingStyle, startCastingLooks, startCastingSheets, startStudioCastingStyle, type CastingQuote, type CastingSheetRequest, type CastingState, type CastingStyleUpdate, type CastingVoiceCatalog } from "@/lib/studio-casting";
import CastingItems from "./CastingItems";
import CastingQuoteDialog from "./CastingQuoteDialog";
import SetupCard from "./SetupCard";
import StyleCard from "./StyleCard";
import VoicePanel from "./VoicePanel";

export default function CastingStage({ project, owner, busy: outerBusy = false, onBusyChange, onChanged }: { project: StudioProject; owner: string; busy?: boolean; onBusyChange: (busy: boolean) => void; onChanged: () => Promise<void> }) {
  const [state, setState] = useState<CastingState | null>(null);
  const [catalog, setCatalog] = useState<CastingVoiceCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [loading, setLoading] = useState(true);
  const [readError, setReadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [quote, setQuote] = useState<{ value: CastingQuote; kind: "style" | "sheets" | "looks"; requests: CastingSheetRequest[] } | null>(null);
  const locked = useRef(false);
  const reading = useRef(false);
  const catalogLoaded = useRef(false);
  const currentState = useRef<CastingState | null>(null);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);
  const id = project.id;
  const refresh = useCallback(async (force = false) => {
    if (!force && (locked.current || reading.current)) return;
    const request = beginRead(); if (!request) return;
    reading.current = true;
    try {
      // Reading the casting state settles finished jobs and publishes their results.
      const next = await getStudioCasting(id, request.signal);
      if (!request.isCurrent()) return;
      currentState.current = next; setState(next); setReadError("");
      // The voice catalog is a one-off read; it only matters once setup is confirmed.
      if (!catalogLoaded.current && next.g0_approved && next.setup) {
        try { const voices = await getCastingVoiceCatalog(request.signal); if (request.isCurrent()) { catalogLoaded.current = true; setCatalog(voices); setCatalogError(""); } }
        catch (cause) { if (request.isCurrent()) setCatalogError(studioErrorMessage(cause)); }
      }
    } catch (cause) { if (request.isCurrent()) setReadError(studioErrorMessage(cause)); }
    finally { reading.current = false; if (request.isCurrent()) setLoading(false); }
  }, [id, beginRead]);
  useEffect(() => { void Promise.resolve().then(() => refresh(true)); }, [refresh, project.snapshot_no]);
  const running = castingInflight(state);
  useEffect(() => {
    if (!running) return;
    let stopped = false, pending = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => { clearTimeout(timer); if (!stopped && !document.hidden && castingInflight(currentState.current)) timer = setTimeout(tick, 5000); };
    const tick = async () => { if (stopped || pending || document.hidden || !castingInflight(currentState.current)) return; pending = true; try { await refresh(); } finally { pending = false; schedule(); } };
    const visibility = () => { clearTimeout(timer); if (!document.hidden) void tick(); };
    schedule(); document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [refresh, running]);
  useEffect(() => () => onBusyChange(false), [onBusyChange]);
  const mutate = async (action: (signal: AbortSignal) => Promise<unknown>, message?: string) => {
    if (locked.current || outerBusy && !busy) return;
    const request = beginMutation(); if (!request) return;
    locked.current = true; setBusy(true); onBusyChange(true); setError(""); setNotice("");
    try {
      await action(request.signal);
      if (request.isCurrent()) { await refresh(true); await onChanged(); if (request.isCurrent() && message) setNotice(message); }
    } catch (cause) {
      if (request.isCurrent()) {
        if (cause instanceof ApiError && cause.status === 409) await refresh(true);
        setError(studioErrorMessage(cause));
      }
    } finally { locked.current = false; if (request.isCurrent()) { setBusy(false); onBusyChange(false); } }
  };
  const requestStyleQuote = async () => {
    await mutate(async signal => { const value = await quoteStudioCastingStyle(id, signal); if (!signal.aborted) setQuote({ value, kind: "style", requests: [] }); }, "报价已就绪，请核对后确认。");
  };
  const requestSheetsQuote = async (requests: CastingSheetRequest[]) => {
    if (!requests.length) return;
    await mutate(async signal => { const value = await quoteCastingSheets(id, requests, signal); if (!signal.aborted) setQuote({ value, kind: "sheets", requests }); }, "报价已就绪，请核对后确认。");
  };
  const requestLooksQuote = async (itemIds: string[]) => {
    if (!itemIds.length) return;
    await mutate(async signal => { const value = await quoteCastingLooks(id, itemIds, signal); if (!signal.aborted) setQuote({ value, kind: "looks", requests: [] }); }, "报价已就绪，请核对后确认。");
  };
  const disabled = busy || outerBusy;
  const gate = <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5"><p role="status" className="text-sm">请先在①拆解批准分集方案。</p></Glaze>;
  if (state && !state.g0_approved) return <div className="min-w-0 space-y-5">{loading && <LoadingState>正在读取定妆设置…</LoadingState>}{readError && <ErrorNotice message={readError} retry={() => void refresh(true)} />}{gate}</div>;
  return <div className="min-w-0 space-y-5">
    {loading && <LoadingState>正在读取定妆设置…</LoadingState>}
    {readError && <ErrorNotice message={readError} retry={() => void refresh(true)} />}
    {error && <ErrorNotice message={error} />}
    {notice && <p role="status" className="text-sm text-[color:var(--ink2)]">{notice}</p>}
    {!state && !loading && !readError && <ErrorNotice message="定妆数据尚未就绪，请重新加载。" retry={() => void refresh(true)} />}
    {state && !state.setup && <p className="text-sm text-[color:var(--ink2)]">开工确认之后，才能生成风格提案、出定妆图和试听声线。</p>}
    {state && <SetupCard aspect={project.aspect} setup={state.setup} busy={disabled} onSave={input => mutate(signal => putStudioCastingSetup(id, input, signal), "开工设置已保存。")} />}
    {state?.setup && <StyleCard state={state} busy={disabled} onQuote={requestStyleQuote} onSave={(update: CastingStyleUpdate) => mutate(signal => putStudioCastingStyle(id, update, signal), "风格已保存。")} onRelease={jobId => mutate(signal => releaseStudioJob(jobId, signal), "已释放预留。")} />}
    {state?.setup && (state.style.chosen
      ? <CastingItems projectId={id} items={state.items} jobs={state.jobs} g1={state.g1} busy={disabled} styleChosen={!!state.style.chosen} mutate={mutate} onQuoteSheets={requestSheetsQuote} onQuoteLooks={requestLooksQuote} />
      : <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5"><p role="status" className="text-sm">选定风格之后，才能报价出定妆图。</p></Glaze>)}
    {state?.setup && state.items.some(item => item.kind === "character") && <VoicePanel projectId={id} items={state.items.filter(item => item.kind === "character")} language={state.setup.language} prices={state.prices} catalog={catalog} catalogError={catalogError} busy={disabled} mutate={mutate} onChanged={onChanged} />}
    {quote && <CastingQuoteDialog quote={quote.value} model={quote.kind === "sheets" ? "Seedream 5.0 · 2560×1440" : brainProviderName(project.brain_provider)} busy={disabled} onClose={() => setQuote(null)} onConfirm={async () => { const chosen = quote; await mutate(signal => chosen.kind === "style" ? startStudioCastingStyle(id, chosen.value.id, signal) : chosen.kind === "sheets" ? startCastingSheets(id, chosen.value.id, signal) : startCastingLooks(id, chosen.value.id, signal), chosen.kind === "style" ? "风格提案已开始生成。" : chosen.kind === "sheets" ? "定妆图已开始生成。" : "造型说明补全已开始。"); setQuote(null); }} />}
  </div>;
}
