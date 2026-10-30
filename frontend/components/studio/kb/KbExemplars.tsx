"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { novelFieldClass } from "@/components/novel/NovelModelFields";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { formatStudioDate, studioErrorMessage } from "@/lib/studio";
import {
  kbExemplarKindLabel, kbExemplarKindOptions, kbSceneTypeLabel, kbSceneTypeOptions, listKbExemplars,
  parseKbJson, patchKbExemplar, type KbExemplar, type KbExemplarKind, type KbExemplarPatch,
} from "@/lib/studio-kb";

function archivedValue(value: KbExemplar["archived"]): boolean {
  return value === true || value === 1;
}
function shotSummary(exemplar: KbExemplar): string {
  const value = exemplar.shot ?? parseKbJson<Record<string, unknown> | null>(exemplar.shot_json, null);
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  const parts = [value.shot_size, value.angle, value.camera, value.action]
    .filter((item): item is string => typeof item === "string" && item.trim() !== "");
  const duration = typeof value.duration_s === "number" ? `${value.duration_s} 秒` : "";
  return [...parts, duration].join(" · ");
}

export function KbExemplarRow({ exemplar, busy, onSave, onArchive }: {
  exemplar: KbExemplar; busy: boolean;
  onSave: (patch: KbExemplarPatch) => Promise<void>;
  onArchive: () => Promise<void>;
}) {
  const [kind, setKind] = useState<KbExemplarKind>(exemplar.kind);
  const [reason, setReason] = useState(exemplar.reason ?? "");
  const [saved, setSaved] = useState(false);
  const archived = archivedValue(exemplar.archived);
  const shot = shotSummary(exemplar);
  const save = async () => {
    if (busy) return;
    setSaved(false);
    try { await onSave({ kind, reason }); setSaved(true); }
    catch { /* The parent shows the request error above the list. */ }
  };
  const archive = async () => {
    if (busy || archived) return;
    try { await onArchive(); }
    catch { /* The parent shows the request error above the list. */ }
  };
  return <article className="ceramic-card min-w-0 space-y-3 rounded-2xl p-4">
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      {kbExemplarKindOptions.map(value => <button key={value} type="button" aria-pressed={kind === value} disabled={busy || archived} onClick={() => { setKind(value); setSaved(false); }} className={`chip min-h-10 ${kind === value ? "chip-on" : ""}`}>{kbExemplarKindLabel(value)}</button>)}
      <span className="tag">{kbSceneTypeLabel(exemplar.scene_type)}</span>
      {archived && <span className="tag">已归档</span>}
      <span className="readout break-words">{exemplar.source} · {formatStudioDate(exemplar.created_at)}</span>
    </div>
    {shot && <p className="break-words text-fs-15 leading-relaxed">{shot}</p>}
    <label className="block min-w-0"><span className="mb-1 block text-fs-12 text-[color:var(--ink2)]">原因</span><textarea value={reason} rows={2} disabled={busy || archived} onChange={event => { setReason(event.target.value); setSaved(false); }} className={`${novelFieldClass} min-h-16 resize-y`} /></label>
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <button type="button" className="btn btn-primary min-h-10" disabled={busy || archived} onClick={() => { void save(); }}>{busy ? "保存中…" : "保存"}</button>
      <button type="button" className="btn btn-quiet min-h-10" disabled={busy || archived} onClick={() => { void archive(); }}>{archived ? "已归档" : "归档"}</button>
      {saved && <span role="status" className="text-fs-13 text-[color:var(--ink2)]">已保存</span>}
    </div>
  </article>;
}

export default function KbExemplars({ owner }: { owner: string }) {
  const [exemplars, setExemplars] = useState<KbExemplar[]>([]);
  const [sceneType, setSceneType] = useState("");
  const [kind, setKind] = useState<KbExemplarKind | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [savingId, setSavingId] = useState("");
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);

  const load = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    setLoading(true);
    try {
      const next = await listKbExemplars({ scene_type: sceneType || undefined, kind: kind || undefined }, request.signal);
      if (!request.isCurrent()) return;
      setExemplars(Array.isArray(next) ? next : []); setError("");
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead, kind, sceneType]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const patch = async (id: string, value: KbExemplarPatch) => {
    const request = beginMutation();
    if (!request) return;
    setSavingId(id); setActionError("");
    try {
      const updated = await patchKbExemplar(id, value, request.signal);
      if (!request.isCurrent()) return;
      setSavingId("");
      setExemplars(previous => value.archived
        ? previous.filter(item => item.id !== id)
        : previous.map(item => item.id === id ? { ...item, ...updated } : item));
    } catch (cause) {
      setSavingId("");
      if (request.isCurrent()) setActionError(studioErrorMessage(cause));
      throw cause;
    }
  };

  return <div className="min-w-0 space-y-4">
    <div className="flex min-w-0 flex-wrap items-end gap-3">
      <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">场景类型</span><select value={sceneType} onChange={event => setSceneType(event.target.value)} className={`${novelFieldClass} min-h-10 py-2`}><option value="">全部场景</option>{kbSceneTypeOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
      <label className="min-w-0 text-fs-13"><span className="mb-1 block text-[color:var(--ink2)]">类型</span><select value={kind} onChange={event => setKind(event.target.value as KbExemplarKind | "")} className={`${novelFieldClass} min-h-10 py-2`}><option value="">全部案例</option>{kbExemplarKindOptions.map(value => <option key={value} value={value}>{kbExemplarKindLabel(value)}</option>)}</select></label>
    </div>
    {actionError && <ErrorNotice message={actionError} />}
    {loading ? <LoadingState>正在读取案例…</LoadingState>
      : error ? <ErrorNotice message={error} retry={() => { void load(); }} />
      : exemplars.length === 0 ? <EmptyState>还没有符合条件的案例。拆镜完成后，好例和反例会出现在这里。</EmptyState>
      : <div className="grid min-w-0 grid-cols-1 gap-3 @[1000px]:grid-cols-2">{exemplars.map(exemplar => <KbExemplarRow key={exemplar.id} exemplar={exemplar} busy={savingId === exemplar.id} onSave={value => patch(exemplar.id, value)} onArchive={() => patch(exemplar.id, { archived: true })} />)}</div>}
  </div>;
}
