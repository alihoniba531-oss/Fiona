"use client";

import { useState } from "react";
import Glaze from "@/components/Glaze";
import { EmptyState, ErrorNotice } from "@/components/novel/NovelStates";
import { castingJobInflight, castingJobStatusLabel, castingRealismLabel, castingRealismOptions, type CastingRealism, type CastingState, type CastingStyleProposal, type CastingStyleUpdate } from "@/lib/studio-casting";

const fieldLabels: Record<keyof CastingStyleProposal, string> = { name: "名称", visual_style: "视觉风格", palette: "配色", camera: "镜头", lighting: "光线", rationale: "理由" };
const fieldsOf = (style: CastingStyleProposal): CastingStyleProposal => ({ name: style.name, visual_style: style.visual_style, palette: style.palette, camera: style.camera, lighting: style.lighting, rationale: style.rationale });

export default function StyleCard({ state, busy, onQuote, onSave, onRelease }: { state: CastingState; busy: boolean; onQuote: () => Promise<void>; onSave: (update: CastingStyleUpdate) => Promise<void>; onRelease: (jobId: string) => Promise<void> }) {
  const job = state.style.proposal_job;
  const proposals = state.style.proposals;
  const [draft, setDraft] = useState<{ index: number | null; fields: CastingStyleProposal; realism: CastingRealism; dirty: boolean } | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const chosen = state.style.chosen;
  const active = draft ?? (chosen ? { index: chosen.proposal_index, fields: fieldsOf(chosen), realism: chosen.realism, dirty: false } : null);
  const generating = castingJobInflight(job);
  const blocked = busy || saving;
  const incomplete = !!active && (!active.fields.name.trim() || !active.fields.visual_style.trim());
  const update = (key: keyof CastingStyleProposal, value: string) => { if (active) setDraft({ ...active, fields: { ...active.fields, [key]: value }, dirty: true }); };
  const save = async () => {
    if (!active || blocked || incomplete) return;
    setSaving(true); setError("");
    try {
      await onSave(active.dirty || active.index === null ? { custom: active.fields, realism: active.realism } : { proposal_index: active.index, realism: active.realism });
      setDraft(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "风格未保存，请重试。"); }
    finally { setSaving(false); }
  };
  const requestQuote = async () => {
    if (blocked || generating) return;
    setError("");
    try { await onQuote(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "报价未完成，请重试。"); }
  };
  return <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5">
    <div className="mb-4 flex min-w-0 flex-wrap items-center justify-between gap-2">
      <h2 className="text-fs-22 tracking-[.2em]">风格</h2>
      <button type="button" className="btn btn-quiet min-h-10" disabled={blocked || generating} onClick={() => void requestQuote()}>{chosen || proposals.length ? "重新生成提案" : "生成风格提案"}</button>
    </div>
    {generating && <p role="status" className="text-fs-13 text-[color:var(--ink2)]">正在生成风格提案（每 5 秒自动刷新，完成后自动停止）…</p>}
    {job && !generating && job.status !== "succeeded" && <div className="min-w-0 space-y-2">
      <ErrorNotice message={job.error_message ?? `风格提案任务${castingJobStatusLabel(job.status)}`} />
      {job.status === "uncertain" && <div className="min-w-0 space-y-2"><p role="status" className="text-fs-13">可能已扣费，请先到供应商控制台核对再释放。</p><button type="button" className="btn btn-quiet min-h-10" disabled={blocked} onClick={() => void onRelease(job.id)}>释放预留</button></div>}
    </div>}
    {!proposals.length && !chosen && !job && <EmptyState>还没有风格提案，先「生成风格提案」。确认报价后由导演模型给出 2–3 种方案。</EmptyState>}
    {!!proposals.length && <ul className="mb-4 min-w-0 space-y-3">{proposals.map((proposal, index) => <li key={`${proposal.name}-${index}`} className="ceramic-card min-w-0 space-y-2 p-3">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2"><p className="min-w-0 break-words">{proposal.name}{chosen?.source === "proposal" && chosen.proposal_index === index && <span className="tag ml-2">当前方案</span>}</p><button type="button" className="btn btn-quiet min-h-10" disabled={blocked} onClick={() => { setDraft({ index, fields: fieldsOf(proposal), realism: active?.realism ?? "photoreal", dirty: false }); setError(""); }}>选这个</button></div>
      <p className="readout min-w-0 break-words">视觉风格 {proposal.visual_style} · 配色 {proposal.palette} · 镜头 {proposal.camera} · 光线 {proposal.lighting}</p>
      <p className="min-w-0 break-words text-fs-13 text-[color:var(--ink2)]">{proposal.rationale}</p>
    </li>)}</ul>}
    {active ? <div className="min-w-0 space-y-3">
      <p className="text-fs-13 text-[color:var(--ink2)]">可以再微调文字，选定写实度后保存。</p>
      <div className="grid min-w-0 grid-cols-1 gap-3 @[640px]:grid-cols-2">{(Object.keys(fieldLabels) as (keyof CastingStyleProposal)[]).map(key => <label key={key} className="block min-w-0 space-y-1 text-fs-13"><span>{fieldLabels[key]}</span><textarea id={`style-${key}`} rows={key === "rationale" ? 3 : 2} disabled={blocked} value={active.fields[key]} className="w-full min-w-0 rounded-lg border border-[color:var(--carve)] bg-[color:var(--paper)] p-2 text-fs-16.5 text-[color:var(--ink)]" onChange={event => update(key, event.target.value)} /></label>)}</div>
      <fieldset disabled={blocked} className="min-w-0 space-y-2"><legend className="text-fs-13 text-[color:var(--ink2)]">写实度</legend><div className="flex min-w-0 flex-wrap gap-3">{castingRealismOptions.map(value => <label key={value} className="flex min-h-10 items-center gap-2 text-fs-13"><input type="radio" name="casting-realism" checked={active.realism === value} onChange={() => setDraft({ ...active, realism: value })} />{castingRealismLabel(value)}</label>)}</div></fieldset>
      {error && <p role="alert" className="text-fs-13">{error}</p>}
      {incomplete && <p role="status" className="text-fs-13">名称与视觉风格不能为空，填好之后才能保存风格。</p>}
      <button type="button" className="btn btn-primary min-h-10" disabled={blocked || incomplete} onClick={() => void save()}>{saving ? "保存中…" : "保存风格"}</button>
    </div> : null}
  </Glaze>;
}
