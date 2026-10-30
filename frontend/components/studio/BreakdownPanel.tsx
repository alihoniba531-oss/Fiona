"use client";

import { useState } from "react";
import Glaze from "@/components/Glaze";
import { type BrainProvider, type BrainProviderId, type StudioProject } from "@/lib/studio";
import { brainProviderName, breakdownTaskLabel, chunkStatusLabel, formatBreakdownMoney, type BreakdownChunk, type StudioBreakdown } from "@/lib/studio-breakdown";
import BreakdownDialog, { breakdownFieldClass } from "./BreakdownDialog";

export function BreakdownChunkRow({ chunk, providers, busy, onRetry, onRelease }: { chunk: BreakdownChunk; providers: BrainProvider[]; busy: boolean; onRetry: (chunk: BreakdownChunk, provider: BrainProviderId) => Promise<void>; onRelease: (chunk: BreakdownChunk) => Promise<void> }) {
  const [provider, setProvider] = useState(chunk.provider);
  const [releasing, setReleasing] = useState(false);
  const problem = ["failed", "rejected", "invalid_output", "released", "uncertain"].includes(chunk.status) || chunk.warnings.length > 0;
  const retryable = ["failed", "rejected", "invalid_output", "released"].includes(chunk.status);
  const settled = Object.entries(chunk.totals ?? {}).filter(([, amount]) => Number(amount) > 0);
  const cost = settled.length ? `累计已结算 ${settled.map(([currency, amount]) => formatBreakdownMoney(Number(amount), currency as "CNY" | "USD")).join(" / ")}` : chunk.cost?.amount != null ? formatBreakdownMoney(chunk.cost.amount, chunk.cost.currency) : "待结算";
  return <details open={problem} className="ceramic-card min-w-0 rounded-xl px-3 py-1">
    <summary className="min-h-10 cursor-pointer py-2 text-fs-13"><span>{chunk.source?.label || `第 ${chunk.no} 批 · ${breakdownTaskLabel(chunk.task)}`}</span> · {chunkStatusLabel(chunk.status)} · {brainProviderName(chunk.provider)} · {cost} · {chunk.warnings.length} 条提示</summary>
    <div className="min-w-0 space-y-2 pb-3 text-fs-13">{chunk.error_message && <p>{chunk.error_message}</p>}{chunk.warnings.length > 0 && <ul className="list-disc space-y-1 pl-5">{chunk.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
      {retryable && <div className="flex min-w-0 flex-wrap gap-2"><label className="flex min-w-0 items-center gap-2">重跑模型<select aria-label={`第 ${chunk.no} 批重跑模型`} value={provider} disabled={busy} className={breakdownFieldClass} onChange={event => setProvider(event.target.value as BrainProviderId)}>{(["claude", "qwen", "deepseek"] as BrainProviderId[]).map(value => { const info = providers.find(item => item.id === value); return <option key={value} value={value} disabled={info ? !info.available : false}>{brainProviderName(value)}{info && !info.available ? "（不可用）" : ""}</option>; })}</select></label><button type="button" className="btn btn-quiet min-h-10" disabled={busy || providers.find(item => item.id === provider)?.available === false} onClick={() => void onRetry(chunk, provider)}>重跑（先报价）</button></div>}
      {chunk.status === "uncertain" && <><p>请求可能已扣费。请先核对账单，确认未扣费后才能释放预留并重跑。</p><button type="button" className="btn btn-quiet min-h-10" disabled={busy || !chunk.job_id} onClick={() => setReleasing(true)}>释放</button></>}
    </div>
    {releasing && <BreakdownDialog title="释放不确定批次" confirmLabel="确认未扣费，释放" busy={busy} onClose={() => setReleasing(false)} onConfirm={async () => { await onRelease(chunk); setReleasing(false); }}><p>这次请求可能已扣费。请核对服务商账单，只有确认未扣费后才能释放本批预留。</p></BreakdownDialog>}
  </details>;
}
export default function BreakdownPanel({ project, breakdown, providers, busy, onQuote, onSettings, onRetry, onRelease, onCancel }: {
  project: StudioProject; breakdown: StudioBreakdown | null; providers: BrainProvider[]; busy: boolean;
  onQuote: (min: number, max: number, target?: number) => Promise<void>; onSettings?: (min: number, max: number) => Promise<void>;
  onRetry: (chunk: BreakdownChunk, provider: BrainProviderId) => Promise<void>;
  onRelease: (chunk: BreakdownChunk) => Promise<void>; onCancel: () => Promise<void>;
}) {
  const [min, setMin] = useState(String(project.episode_seconds_min ?? 180));
  const [max, setMax] = useState(String(project.episode_seconds_max ?? 240));
  const [target, setTarget] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const validTimes = Number.isInteger(Number(min)) && Number.isInteger(Number(max)) && Number(min) >= 60 && Number(max) <= 900 && Number(min) <= Number(max);
  const valid = validTimes && (!target || Number.isInteger(Number(target)) && Number(target) >= 1 && Number(target) <= 300);
  const active = breakdown?.status === "running";
  const chunks = breakdown?.chunks ?? [];
  const canCancel = breakdown?.status !== "cancelled" && chunks.some(item => ["queued", "blocked", "running"].includes(item.status));
  const complete = chunks.filter(item => item.status === "succeeded").length;
  const retryNeeded = breakdown?.retry_needed ?? chunks.filter(item => ["failed", "rejected", "invalid_output", "released", "uncertain"].includes(item.status)).map(item => ({ label: item.source?.label || `第 ${item.no} 批`, status: item.status }));
  const blockedSegments = breakdown?.blocked_segments ?? chunks.filter(item => item.task === "episode_plan" && item.status === "blocked").map(item => item.source?.label || `第 ${item.no} 批`);
  const percent = chunks.length ? complete / chunks.length * 100 : 0;
  return <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5">
    <h2 className="mb-4 text-fs-22 tracking-[.2em]">拆解</h2>
    {breakdown?.outdated ? <div role="status" className="ceramic-card mb-4 min-w-0 space-y-2 rounded-xl p-3"><p>拆解基于快照第 {breakdown.snapshot_no} 版，作品已同步到第 {project.snapshot_no ?? breakdown.snapshot_no} 版。</p><button type="button" className="btn btn-quiet min-h-10" disabled={busy || active || !valid} onClick={() => void onQuote(Number(min), Number(max), target ? Number(target) : undefined)}>重新拆解</button></div> : null}
    <fieldset disabled={busy || active} className="min-w-0 space-y-3">
      <legend className="mb-2 text-fs-13 text-[color:var(--ink2)]">每集目标时长</legend>
      <div className="flex min-w-0 flex-wrap items-end gap-3"><label className="block w-28 min-w-0 space-y-1 text-fs-13"><span className="whitespace-nowrap">最短秒数</span><input type="number" min={60} max={900} step={1} value={min} className={breakdownFieldClass} onChange={event => setMin(event.target.value)} /></label><label className="block w-28 min-w-0 space-y-1 text-fs-13"><span className="whitespace-nowrap">最长秒数</span><input type="number" min={60} max={900} step={1} value={max} className={breakdownFieldClass} onChange={event => setMax(event.target.value)} /></label><label className="block w-28 min-w-0 space-y-1 text-fs-13"><span className="whitespace-nowrap">大约几集</span><input type="number" min={1} max={300} step={1} placeholder="可不填" value={target} className={breakdownFieldClass} onChange={event => setTarget(event.target.value)} /></label><p className="readout pb-2 text-fs-13 text-[color:var(--ink2)]">约 {(Number(min) / 60).toFixed(1)}–{(Number(max) / 60).toFixed(1)} 分钟</p></div>
      <p className="text-fs-13 text-[color:var(--ink2)]">60–900 秒，最短不能大于最长。</p>
      {onSettings && <button type="button" className="btn btn-quiet min-h-10" disabled={busy || active || !validTimes || Number(min) === (project.episode_seconds_min ?? 180) && Number(max) === (project.episode_seconds_max ?? 240)} onClick={() => void onSettings(Number(min), Number(max))}>保存时长</button>}
      <p className="text-fs-13">当前导演模型：{brainProviderName(project.brain_provider)} <span className="text-[color:var(--ink2)]">（在页面顶部更换）</span></p>
      {!valid && <p role="status" className="text-fs-13">请填写有效的时长区间与集数（1–300）。</p>}
      <button type="button" className="btn btn-primary min-h-10" disabled={busy || active || !valid || providers.find(item => item.id === project.brain_provider)?.available === false} onClick={() => void onQuote(Number(min), Number(max), target ? Number(target) : undefined)}>{busy ? "处理中…" : breakdown ? "重新报价拆解" : "报价"}</button>
    </fieldset>
    {breakdown && <div className="mt-5 min-w-0 space-y-3"><div className="flex min-w-0 flex-wrap items-center justify-between gap-2"><p role="status">{({ draft: "待开始", running: "正在拆解", partial: "部分完成", done: "拆解完成", cancelled: "已取消" })[breakdown.status]} · {complete}/{chunks.length} 批完成 · {breakdown.units_count} 个场景单元</p>{canCancel && <button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => setCancelling(true)}>取消拆解</button>}</div><div role="progressbar" aria-label="拆解总进度" aria-valuemin={0} aria-valuemax={chunks.length} aria-valuenow={complete} className="h-1.5 w-full overflow-hidden rounded-full bg-[color:var(--slip)]"><div className="h-full rounded-full bg-[color:var(--ink2)] transition-[width]" style={{ width: `${percent}%` }} /></div>
      {breakdown.status === "partial" && <p role="status" className="text-fs-13">以下批次需要重跑：{retryNeeded.map(item => `${item.label}（${chunkStatusLabel(item.status)}${item.status === "uncertain" ? "，需先核账释放" : ""}）`).join("、") || "请检查失败的前置批次"}；{blockedSegments.length ? `完成后「${blockedSegments.join("、")}」会自动继续。` : ""}完成前不能批准分集方案。</p>}
      {breakdown.totals && <p className="readout text-fs-13">已结算：{Object.entries(breakdown.totals).map(([currency, amount]) => formatBreakdownMoney(Number(amount), currency as "CNY" | "USD")).join(" / ")}</p>}
      <div className="min-w-0 space-y-2">{chunks.map(chunk => <BreakdownChunkRow key={`${chunk.id}:${chunk.status}`} chunk={chunk} providers={providers} busy={busy} onRetry={onRetry} onRelease={onRelease} />)}</div>
    </div>}
    {cancelling && <BreakdownDialog title="取消本次拆解" confirmLabel="确认取消" busy={busy} onClose={() => setCancelling(false)} onConfirm={async () => { await onCancel(); setCancelling(false); }}><p>未执行的批次将取消并释放预留。正在执行的批次会完成并按实际用量结算。</p></BreakdownDialog>}
  </Glaze>;
}
