"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { formatStudioDate, getStudioSource, studioErrorMessage, studioSourceKindLabel, syncStudioSource, type StudioSourceStatus } from "@/lib/studio";
import { SourceFlags, sourceDialogClass } from "./SourceChoices";

export function studioDriftSummary(drift: NonNullable<StudioSourceStatus["drift"]>): string {
  const parts: string[] = [];
  if (drift.changed?.length) parts.push(`第 ${drift.changed.join("、")} 章内容变化`);
  if (drift.added?.length) parts.push(`新增第 ${drift.added.join("、")} 章`);
  if (drift.removed?.length) parts.push(`移除第 ${drift.removed.join("、")} 章`);
  if (drift.bible_changed) parts.push("故事圣经已更新");
  return `原作有改动：${parts.join("，") || "作品信息已更新"}`;
}
export default function SourcePanel({ projectId, owner, busy: externalBusy = false, onChanged }: { projectId: string; owner: string; busy?: boolean; onChanged: () => Promise<unknown> }) {
  const [source, setSource] = useState<StudioSourceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const lock = useRef(false);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);
  const load = useCallback(async () => {
    const request = beginRead(); if (!request) return;
    setLoading(true); setError("");
    try { const result = await getStudioSource(projectId, request.signal); if (request.isCurrent()) setSource(result); }
    catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead, projectId]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  const sync = async () => {
    if (lock.current || externalBusy || !source?.snapshot || source.drift?.eligible === false) return;
    const request = beginMutation(); if (!request) return;
    lock.current = true; setSyncing(true); setError("");
    try {
      const result = await syncStudioSource(projectId, source.snapshot.no, request.signal);
      if (request.isCurrent()) { setSource(result); setConfirm(false); await onChanged(); }
    } catch (cause) { if (request.isCurrent()) { setError(studioErrorMessage(cause)); setConfirm(false); } }
    finally { lock.current = false; if (request.isCurrent()) setSyncing(false); }
  };
  const drift = source?.drift;
  const busy = externalBusy || syncing;
  return <section aria-label="作品来源" className="ceramic-card mb-5 min-w-0 rounded-2xl p-5">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h2 className="text-fs-22 tracking-[.16em]">作品来源</h2><button type="button" className="btn btn-quiet min-h-10" disabled={loading || busy} onClick={() => void load()}>重新检查</button></div>
    {loading && <LoadingState>正在检查作品来源…</LoadingState>}
    {error && <ErrorNotice message={error} retry={() => void load()} />}
    {source?.kind === null && <EmptyState>这个项目没有关联作品</EmptyState>}
    {source?.kind && <div className="min-w-0 space-y-3 break-words"><div className="flex flex-wrap items-center gap-2"><span className="tag">{studioSourceKindLabel(source.kind)}</span><h3 className="text-fs-18">{source.title || source.snapshot?.title}</h3></div>
      {source.snapshot && <><p className="readout text-fs-13">快照第 {source.snapshot.no} 版 · {formatStudioDate(source.snapshot.created_at)}</p><p className="readout text-fs-13">{source.snapshot.chapters} {source.kind === "novel" ? "章" : "块"} · {source.snapshot.chars.toLocaleString()} 字</p></>}
      {source.kind === "novel" && <SourceFlags chapters={source.snapshot?.flagged ?? source.flagged ?? []} />}
      {drift?.state === "unchanged" && <p role="status" className="text-fs-13 text-[color:var(--ink2)]">原作与快照一致。</p>}
      {drift?.state === "unavailable" && <p role="status" className="text-fs-13 text-[color:var(--ink2)]">原作已无法访问，快照仍可正常使用</p>}
      {drift?.state === "changed" && <div className="ceramic-card space-y-3 rounded-xl p-3"><p role="status">{studioDriftSummary(drift)}</p><button type="button" className="btn min-h-10" disabled={busy || drift.eligible === false} onClick={() => setConfirm(true)}>同步</button></div>}
      {drift?.eligible === false && drift.state !== "unavailable" && <p role="status" className="text-fs-13 text-[color:var(--seal)]">原作当前不能同步：{drift.reason || "暂不满足导入条件"}</p>}
    </div>}
    {confirm && <SyncSourceDialog busy={syncing} onClose={() => setConfirm(false)} onConfirm={sync} />}
  </section>;
}
export function SyncSourceDialog({ busy, onClose, onConfirm }: { busy: boolean; onClose: () => void; onConfirm: () => Promise<void> }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} aria-labelledby="studio-sync-title" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }} className={sourceDialogClass}>
    <h2 id="studio-sync-title" className="mb-4 text-fs-22">同步原作</h2><p className="mb-5 leading-relaxed">同步将重新快照；旧快照归档保留；后续拆解、分集以新快照为准。</p>
    <div className="flex flex-wrap gap-3"><button type="button" className="btn btn-primary min-h-10" disabled={busy} onClick={() => void onConfirm()}>{busy ? "正在建立快照…" : "确认同步"}</button><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onClose}>取消</button></div>
  </dialog>;
}
