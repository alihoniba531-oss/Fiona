"use client";

import { useId, useState } from "react";
import Glaze from "@/components/Glaze";
import { EmptyState } from "@/components/novel/NovelStates";
import { useRovingTabs } from "@/lib/useRovingTabs";
import { patchStudioBible } from "@/lib/studio-breakdown";
import { releaseStudioJob, uploadStudioAsset } from "@/lib/studio";
import { approveCastingItem, archiveCastingAsset, castingJobStatusLabel, castingLookInflight, castingLookProblem, castingNeedsAppearance, patchCastingItem, reopenCastingItem, skipCastingItem, type CastingG1, type CastingItem, type CastingItemKind, type CastingItemPatch, type CastingJob, type CastingMutate, type CastingSheetRequest } from "@/lib/studio-casting";
import { breakdownFieldClass } from "./BreakdownDialog";
import CastingItemCard from "./CastingItemCard";

const kinds: CastingItemKind[] = ["character", "location", "prop"];
const kindLabels = ["人物", "场景", "道具"];
const maxSheets = 60;

export default function CastingItems({ projectId, items, jobs, g1, busy, styleChosen, mutate, onQuoteSheets, onQuoteLooks }: {
  projectId: string; items: CastingItem[]; jobs: CastingJob[]; g1: CastingG1; busy: boolean; styleChosen: boolean;
  mutate: CastingMutate; onQuoteSheets: (requests: CastingSheetRequest[]) => Promise<void>; onQuoteLooks: (itemIds: string[]) => Promise<void>;
}) {
  const [tab, setTab] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [versions, setVersions] = useState("1");
  const [derive, setDerive] = useState(false);
  const [extra, setExtra] = useState("");
  const [references, setReferences] = useState<string[]>([]);
  const [referenceError, setReferenceError] = useState("");
  const [uploading, setUploading] = useState(false);
  const prefix = useId();
  const chooseTab = (value: number) => { setTab(value); setSelected([]); };
  const tabProps = useRovingTabs(kinds.length, tab, chooseTab);
  const kind = kinds[tab];
  const visible = items.filter(item => item.kind === kind);
  const selectedItems = items.filter(item => selected.includes(item.id) && !item.orphaned);
  const lookTargets = selectedItems.filter(item => item.kind !== "location" && !castingLookInflight(jobs, item.id).length);
  const lookProblem = castingLookProblem(jobs);
  const lookOverLimit = lookTargets.length > 30;
  const deriveBlocked = selectedItems.some(item => !item.approved_asset_id);
  const useDerive = derive && !deriveBlocked;
  const needsAuthor = selectedItems.filter(item => item.kind === "character" && item.needs_author).map(item => item.name);
  const missingAppearance = castingNeedsAppearance(items, selected);
  const perItem = Math.min(4, Math.max(1, Number(versions) || 1));
  const overLimit = selectedItems.length * perItem > maxSheets;
  const total = g1.total;
  const percent = total > 0 ? Math.round((g1.done / total) * 100) : 0;
  const toggle = (id: string, checked: boolean) => setSelected(list => checked ? [...list, id] : list.filter(value => value !== id));
  const pickReference = async (file: File | undefined) => {
    if (!file || uploading || busy) return;
    if (!["image/png", "image/jpeg"].includes(file.type)) { setReferenceError("参考图仅支持 PNG、JPEG。"); return; }
    setUploading(true); setReferenceError("");
    try { const asset = await uploadStudioAsset(projectId, file); setReferences(list => [...list, asset.id]); }
    catch (cause) { setReferenceError(cause instanceof Error ? cause.message : "参考图上传失败，请重试。"); }
    finally { setUploading(false); }
  };
  const requests: CastingSheetRequest[] = selectedItems.map(item => ({
    item_id: item.id,
    versions: perItem,
    ...(extra.trim() ? { extra_prompt: extra.trim() } : {}),
    ...(references.length ? { reference_asset_ids: references.slice(0, 4) } : {}),
    ...(useDerive ? { derive_from_approved: true } : {}),
  }));
  const patch = (item: CastingItem, input: CastingItemPatch) => mutate(signal => patchCastingItem(item.id, input, signal), "条目已保存。");
  const card = (item: CastingItem) => <CastingItemCard key={item.id} item={item} jobs={jobs} selected={selected.includes(item.id)} busy={busy} onSelect={checked => toggle(item.id, checked)}
    onPatch={input => patch(item, input)}
    onApprove={assetId => mutate(signal => approveCastingItem(item.id, assetId, signal), "版本已选定并确认该条目。")}
    onSkip={() => mutate(signal => skipCastingItem(item.id, signal), "已标为不需要定妆。")}
    onReopen={() => mutate(signal => reopenCastingItem(item.id, signal), "条目已重新打开。")}
    onArchive={assetId => mutate(signal => archiveCastingAsset(assetId, signal), "版本已归档。")}
    onRelease={jobId => mutate(signal => releaseStudioJob(jobId, signal), "已释放预留。")}
    onSaveAppearance={appearance => mutate(signal => patchStudioBible(item.bible_id, { appearance, needs_author: false }, signal), "外形已保存，可以出图了。")} />;
  return <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5">
    <h2 className="mb-4 text-xl tracking-[.2em]">定妆</h2>
    <div className="mb-4 min-w-0 space-y-2">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <p role="status" className="text-sm">已确认 <span className="readout"><b>{g1.done}</b></span> / 共 {g1.total}（跳过 {g1.skipped}）</p>
        {g1.approved && <span className="tag tag-rec">G1 定妆通过</span>}
      </div>
      <div role="progressbar" aria-label="G1 定妆进度" aria-valuemin={0} aria-valuemax={g1.total} aria-valuenow={g1.done} className="h-1.5 w-full overflow-hidden rounded-full bg-[color:var(--slip)]"><div className="h-full rounded-full bg-[color:var(--ink2)] transition-[width]" style={{ width: `${percent}%` }} /></div>
    </div>
    {lookProblem && <div className="ceramic-card mb-3 min-w-0 space-y-2 p-3">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <p className="text-sm">最近一次造型说明任务：{castingJobStatusLabel(lookProblem.status)}</p>
        {lookProblem.status === "uncertain" && <span className="tag">可能已扣费</span>}
      </div>
      {!!lookProblem.error_message && <p className="min-w-0 break-words text-sm text-[color:var(--ink2)]">{lookProblem.error_message}</p>}
      {lookProblem.status === "uncertain" && <div className="flex min-w-0 flex-wrap items-center gap-2">
        <p role="status" className="text-sm">可能已扣费，请先到供应商控制台核对再释放。</p>
        <button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => void mutate(signal => releaseStudioJob(lookProblem.id, signal), "已释放预留。")}>释放预留</button>
      </div>}
    </div>}
    <div role="tablist" aria-label="定妆类型" className="mb-3 flex min-w-0 gap-2">{kindLabels.map((label, index) => <button key={label} type="button" id={`${prefix}-tab-${index}`} role="tab" aria-selected={tab === index} aria-controls={`${prefix}-panel-${index}`} {...tabProps(index)} className={`chip min-h-10 ${tab === index ? "chip-on" : ""}`} onClick={() => chooseTab(index)}>{label} {items.filter(item => item.kind === kinds[index]).length}</button>)}</div>
    <div role="tabpanel" id={`${prefix}-panel-${tab}`} aria-labelledby={`${prefix}-tab-${tab}`} className="min-w-0 space-y-3">
      {visible.length ? visible.map(card) : <EmptyState>这一类还没有条目，先在①拆解里补进总表。</EmptyState>}
    </div>
    {selectedItems.length > 0 && <div className="ceramic-card mt-4 min-w-0 space-y-3 p-3">
      <p className="text-sm">已勾选 {selectedItems.length} 个条目（合计 {selectedItems.length * perItem} 张）</p>
      <div className="flex min-w-0 flex-wrap items-end gap-3">
        <label className="block w-24 min-w-0 space-y-1 text-sm"><span>每项版本</span><input id="casting-versions" type="number" min={1} max={4} step={1} value={versions} disabled={busy} className={breakdownFieldClass} onChange={event => setVersions(event.target.value)} /></label>
        <label className="flex min-h-10 items-center gap-2 text-sm"><input id="casting-derive" type="checkbox" checked={derive} disabled={busy || deriveBlocked} title={deriveBlocked ? "所选条目里还有条目没有已选定版本。" : undefined} onChange={event => setDerive(event.target.checked)} />以选定版为参考派生</label>
        <label className="block min-w-0 flex-1 space-y-1 text-sm"><span>补充提示词（只对本批生效，追加在条目自己的补充提示词之后）</span><input id="casting-extra" maxLength={500} value={extra} disabled={busy} className={breakdownFieldClass} onChange={event => setExtra(event.target.value)} /></label>
      </div>
      {deriveBlocked && <p role="status" className="text-sm">所选条目里有条目还没有已选定版本，要先给这些条目「选定」一个版本才能派生。</p>}
      <label className="block min-w-0 space-y-1 text-sm"><span>参考图（PNG / JPEG，最多 4 张）</span><input id="casting-reference" type="file" accept="image/png,image/jpeg" disabled={busy || uploading} className={breakdownFieldClass} onChange={event => void pickReference(event.target.files?.[0])} /></label>
      {!!references.length && <ul className="flex min-w-0 flex-wrap gap-2">{references.map((assetId, index) => <li key={assetId} title={assetId} className="chip min-w-0 max-w-full"><span className="min-w-0 truncate">参考图 {index + 1} · {assetId.slice(0, 8)}</span><button type="button" className="btn btn-quiet min-h-0 h-7" aria-label={`移除参考图 ${index + 1}`} disabled={busy} onClick={() => setReferences(list => list.filter(value => value !== assetId))}>移除</button></li>)}</ul>}
      {needsAuthor.length > 0 && <p role="status" className="text-sm">以下人物需要先补写外形：{needsAuthor.join("、")}。</p>}
      {overLimit && <p role="status" className="text-sm">一次最多 {maxSheets} 张，请减少条目或版本数。</p>}
      <p role="status" className="text-sm">出定妆图前建议先补全造型说明，图里的服装与妆造细节以它为准。</p>
      {!styleChosen && <p role="status" className="text-sm">先选定风格</p>}
      {lookOverLimit && <p role="status" className="text-sm">一次最多补全 30 个条目，请减少勾选。</p>}
      {referenceError && <p role="alert" className="text-sm">{referenceError}</p>}
      <div className="flex min-w-0 flex-wrap gap-2">
        <button type="button" className="btn btn-quiet min-h-10" disabled={busy || !styleChosen || !lookTargets.length || lookOverLimit} title={!styleChosen ? "先选定风格" : lookOverLimit ? "一次最多补全 30 个条目" : undefined} onClick={() => void onQuoteLooks(lookTargets.map(item => item.id))}>补全造型说明</button>
        <button type="button" className="btn btn-primary min-h-10" disabled={busy || uploading || missingAppearance || overLimit} onClick={() => void onQuoteSheets(requests)}>报价出图</button>
        <button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => { setSelected([]); setReferences([]); setExtra(""); setDerive(false); setReferenceError(""); }}>取消选择</button>
      </div>
    </div>}
  </Glaze>;
}
