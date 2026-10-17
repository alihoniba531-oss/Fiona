"use client";

import { useState } from "react";
import { LoadingState } from "@/components/novel/NovelStates";
import { CASTING_LOOK_FIELDS, CASTING_LOOK_MAX_CHARS, castingItemFinished, castingItemInflight, castingItemStatusLabel, castingJobStatusLabel, castingLookInflight, castingLookSourceLabel, type CastingItem, type CastingItemPatch, type CastingJob, type CastingLook, type CastingVersion } from "@/lib/studio-casting";
import BreakdownDialog, { breakdownFieldClass } from "./BreakdownDialog";
import StudioAssetImage from "./StudioAssetImage";

export default function CastingItemCard({ item, jobs, selected, busy, onSelect, onPatch, onApprove, onSkip, onReopen, onArchive, onRelease, onSaveAppearance }: {
  item: CastingItem; jobs: CastingJob[]; selected: boolean; busy: boolean;
  onSelect: (selected: boolean) => void;
  onPatch: (patch: CastingItemPatch) => Promise<void>;
  onApprove: (assetId: string) => Promise<void>;
  onSkip: () => Promise<void>;
  onReopen: () => Promise<void>;
  onArchive: (assetId: string) => Promise<void>;
  onRelease: (jobId: string) => Promise<void>;
  onSaveAppearance: (appearance: string) => Promise<void>;
}) {
  const [appearanceDraft, setAppearanceDraft] = useState<string | null>(null);
  const [lockedDraft, setLockedDraft] = useState<string | null>(null);
  const [extraDraft, setExtraDraft] = useState<string | null>(null);
  const [lookDraft, setLookDraft] = useState<CastingLook | null>(null);
  const [lookBase, setLookBase] = useState<CastingLook | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<CastingVersion | null>(null);
  const blocked = busy || saving || item.orphaned;
  const versions = item.versions.filter(version => !version.archived);
  const inflight = castingItemInflight(jobs, item.id);
  const problems = castingItemFinished(jobs, item.id);
  const lookInflight = castingLookInflight(jobs, item.id);
  const lookFields = item.kind === "location" ? null : CASTING_LOOK_FIELDS[item.kind];
  const lookSource = castingLookSourceLabel(item.look_source);
  const lookValues = item.look ?? {};
  const hasLook = !!lookFields?.some(([key]) => (lookValues[key] ?? "").trim());
  const run = async (action: () => Promise<void>) => {
    if (blocked) return;
    setSaving(true); setError("");
    try { await action(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "操作未完成，请重试。"); }
    finally { setSaving(false); }
  };
  const saveAppearance = () => run(async () => { await onSaveAppearance((appearanceDraft ?? "").trim()); setAppearanceDraft(null); });
  const saveLocked = () => run(async () => { await onPatch({ locked_features: lockedDraft ?? "" }); setLockedDraft(null); });
  const saveExtra = () => run(async () => { await onPatch({ extra_prompt: extraDraft ?? "" }); setExtraDraft(null); });
  const startLookEdit = () => {
    if (!lookFields) return;
    const base: CastingLook = {};
    for (const [key] of lookFields) base[key] = (lookValues[key] ?? "").trim();
    setLookBase(base); setLookDraft(base); setError("");
  };
  const saveLook = () => {
    if (!lookFields || !lookDraft || !lookBase) return;
    const changes: CastingLook = {};
    for (const [key] of lookFields) {
      const value = (lookDraft[key] ?? "").trim();
      if (value !== (lookBase[key] ?? "")) changes[key] = value;
    }
    if (!Object.keys(changes).length) return;
    void run(async () => { await onPatch({ look: changes }); setLookDraft(null); setLookBase(null); });
  };
  const lookChanged = !!lookFields && !!lookDraft && !!lookBase && lookFields.some(([key]) => (lookDraft[key] ?? "").trim() !== (lookBase[key] ?? ""));
  return <div className="ceramic-card min-w-0 space-y-3 p-3">
    <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
      <label className="flex min-h-10 min-w-0 items-start gap-2">
        <input type="checkbox" aria-label={`选择${item.name}`} className="mt-1" checked={selected} disabled={blocked} onChange={event => onSelect(event.target.checked)} />
        <span className="min-w-0 break-words text-sm">{item.name}{item.orphaned && <span className="tag ml-2">已不在当前总表</span>}{!!item.needs_author && <span className="tag ml-2">待作者补充</span>}</span>
      </label>
      <span className="tag">{castingItemStatusLabel(item.status)}</span>
    </div>
    {item.needs_author ? <div className="ceramic-card min-w-0 space-y-2 p-3">
      <p className="text-sm">原文没有外形描述，先补外形才能出图。</p>
      {appearanceDraft === null ? <button type="button" className="btn btn-quiet min-h-10" disabled={blocked} onClick={() => { setAppearanceDraft(item.appearance); setError(""); }}>先补外形</button>
        : <form className="min-w-0 space-y-2" onSubmit={event => { event.preventDefault(); void saveAppearance(); }}>
          <label htmlFor={`appearance-${item.id}`} className="block min-w-0 space-y-1 text-sm"><span>外形（面部、发型、体型、服装）</span><textarea id={`appearance-${item.id}`} rows={3} disabled={busy || saving} value={appearanceDraft} className={breakdownFieldClass} onChange={event => setAppearanceDraft(event.target.value)} /></label>
          <div className="flex flex-wrap gap-2"><button type="submit" className="btn btn-primary min-h-10" disabled={busy || saving || !appearanceDraft.trim()}>{saving ? "保存中…" : "保存外形"}</button><button type="button" className="btn btn-quiet min-h-10" disabled={busy || saving} onClick={() => { setAppearanceDraft(null); setError(""); }}>取消</button></div>
        </form>}
    </div> : <p className="min-w-0 whitespace-pre-wrap break-words text-sm">{item.appearance || item.description || "—"}</p>}
    {lookFields && <div className="min-w-0 space-y-2 text-sm">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <p className="text-[color:var(--ink2)]">造型说明</p>
        {lookSource && <span className="tag">{lookSource}</span>}
        {!!lookInflight.length && <p role="status" className="text-[color:var(--ink2)]">导演正在补全造型…</p>}
        {lookDraft === null && <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || !!lookInflight.length} onClick={startLookEdit}>编辑</button>}
        {!!lookInflight.length && <span className="tag">导演补全中</span>}
      </div>
      {lookDraft === null ? (hasLook
        ? <ul className="min-w-0 space-y-1">{lookFields.map(([key, label]) => <li key={key} className="grid min-w-0 grid-cols-[6.5rem_minmax(0,1fr)] gap-2">
          <span className="text-[color:var(--ink2)]">{label}</span><span className="min-w-0 whitespace-pre-wrap break-words">{lookValues[key]?.trim() || "—"}</span>
        </li>)}</ul>
        : <p className="text-[color:var(--ink2)]">还没有造型说明。勾选条目后点『补全造型说明』，或直接手写。</p>)
        : <div className="min-w-0 space-y-2">
          {lookFields.map(([key, label]) => <label key={key} htmlFor={`look-${item.id}-${key}`} className="block min-w-0 space-y-1">
            <span className="text-[color:var(--ink2)]">{label}</span>
            <textarea id={`look-${item.id}-${key}`} rows={2} maxLength={CASTING_LOOK_MAX_CHARS} disabled={busy || saving} value={lookDraft[key] ?? ""} className={breakdownFieldClass} onChange={event => setLookDraft(current => ({ ...(current ?? {}), [key]: event.target.value.slice(0, CASTING_LOOK_MAX_CHARS) }))} />
          </label>)}
          <div className="flex min-w-0 flex-wrap gap-2">
            <button type="button" className="btn btn-primary min-h-10" disabled={busy || saving || !lookChanged} onClick={saveLook}>{saving ? "保存中…" : "保存造型说明"}</button>
            <button type="button" className="btn btn-quiet min-h-10" disabled={busy || saving} onClick={() => { setLookDraft(null); setLookBase(null); setError(""); }}>取消</button>
          </div>
        </div>}
    </div>}
    <div className="min-w-0 space-y-2 text-sm">
      <label htmlFor={`locked-${item.id}`} className="block text-[color:var(--ink2)]">锁定特征（出图提示词会带上，之后不得改动）</label>
      <textarea id={`locked-${item.id}`} rows={2} disabled={blocked} value={lockedDraft ?? item.locked_features} className={breakdownFieldClass} onChange={event => setLockedDraft(event.target.value)} />
      <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || lockedDraft === null || lockedDraft === item.locked_features} onClick={() => void saveLocked()}>保存锁定特征</button>
    </div>
    <div className="min-w-0 space-y-2 text-sm">
      <label htmlFor={`extra-${item.id}`} className="block text-[color:var(--ink2)]">补充提示词（之后每次出图都会带上）</label>
      <textarea id={`extra-${item.id}`} rows={2} maxLength={500} disabled={blocked} value={extraDraft ?? item.extra_prompt} className={breakdownFieldClass} onChange={event => setExtraDraft(event.target.value)} />
      <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || extraDraft === null || extraDraft === item.extra_prompt} onClick={() => void saveExtra()}>保存补充提示词</button>
    </div>
    {!!item.reference_asset_ids.length && <div className="min-w-0 space-y-2">
      <p className="text-sm text-[color:var(--ink2)]">参考图</p>
      <ul className="flex min-w-0 flex-wrap gap-2">{item.reference_asset_ids.map(assetId => <li key={assetId} className="w-24 min-w-0 space-y-1">
        <StudioAssetImage assetId={assetId} alt={`${item.name} 参考图`} loading="lazy" decoding="async" />
        <button type="button" className="btn btn-quiet min-h-10 w-full" disabled={blocked} onClick={() => void run(async () => { await onPatch({ reference_asset_ids: item.reference_asset_ids.filter(value => value !== assetId) }); })}>移除</button>
      </li>)}</ul>
    </div>}
    <div className="min-w-0 space-y-2">
      <p className="text-sm text-[color:var(--ink2)]">版本（{versions.length}）</p>
      {!versions.length && !inflight.length && !problems.length && <p className="text-sm text-[color:var(--ink2)]">还没有版本，勾选条目后「报价出图」。</p>}
      <ul className="grid min-w-0 grid-cols-1 gap-2 @[480px]:grid-cols-2">
        {versions.map(version => <li key={version.asset_id} className="ceramic-card min-w-0 space-y-2 p-2">
          <button type="button" className="block w-full min-w-0" aria-label={`查看${item.name}第 ${version.version_no} 版大图`} onClick={() => setPreview(version)}><StudioAssetImage assetId={version.asset_id} alt={`${item.name} 第 ${version.version_no} 版`} loading="lazy" decoding="async" /></button>
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-1"><span className="readout">第 {version.version_no} 版</span>{item.approved_asset_id === version.asset_id && <span className="tag">已选定</span>}</div>
          <div className="flex min-w-0 flex-wrap gap-1">
            <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || item.approved_asset_id === version.asset_id} onClick={() => void run(async () => { await onApprove(version.asset_id); })}>选定</button>
            <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || item.approved_asset_id === version.asset_id} title={item.approved_asset_id === version.asset_id ? "先换选定" : undefined} onClick={() => void run(async () => { await onArchive(version.asset_id); })}>归档</button>
          </div>
        </li>)}
        {inflight.map(job => <li key={job.id} className="ceramic-card min-w-0 space-y-1 p-2"><LoadingState>正在出图…</LoadingState><span className="readout">{castingJobStatusLabel(job.status)}</span></li>)}
        {problems.map(job => <li key={job.id} className="ceramic-card min-w-0 space-y-2 p-2">
          <span className="tag">{castingJobStatusLabel(job.status)}</span>
          {job.status === "uncertain"
            ? <div className="min-w-0 space-y-2">
              <p role="status" className="text-sm">可能已扣费，请勿直接重试，去控制台核对</p>
              {!!job.error_message && !job.error_message.includes("可能已扣费") && <p className="min-w-0 break-words text-sm text-[color:var(--ink2)]">{job.error_message}</p>}
              <button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => void run(async () => { await onRelease(job.id); })}>释放</button>
            </div>
            : <p className="min-w-0 break-words text-sm">{job.error_message ?? "这一张没有出图成功。"}</p>}
        </li>)}
      </ul>
    </div>
    {error && <p role="alert" className="text-sm">{error}</p>}
    <div className="flex min-w-0 flex-wrap gap-1">
      {item.approved_asset_id && item.status !== "approved" && <button type="button" className="btn btn-quiet min-h-10" disabled={blocked} onClick={() => void run(async () => { await onApprove(item.approved_asset_id!); })}>确认此条</button>}
      {item.status !== "skipped" && <button type="button" className="btn btn-quiet min-h-10" disabled={blocked} onClick={() => void run(async () => { await onSkip(); })}>标为不需要</button>}
      {item.status !== "pending" && <button type="button" className="btn btn-quiet min-h-10" disabled={busy || saving} onClick={() => void run(async () => { await onReopen(); })}>重新打开</button>}
    </div>
    {preview && <BreakdownDialog title={`${item.name} · 第 ${preview.version_no} 版`} confirmLabel="关闭" busy={busy} onClose={() => setPreview(null)} onConfirm={async () => setPreview(null)}>
      <div className="min-w-0"><StudioAssetImage assetId={preview.asset_id} alt={`${item.name} 第 ${preview.version_no} 版大图`} loading="lazy" decoding="async" /></div>
      <p className="readout min-w-0 break-words">{preview.prompt}</p>
    </BreakdownDialog>}
  </div>;
}
