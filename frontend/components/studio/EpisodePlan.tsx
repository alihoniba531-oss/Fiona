"use client";

import { useEffect, useId, useRef, useState } from "react";
import Glaze from "@/components/Glaze";
import { EmptyState } from "@/components/novel/NovelStates";
import { formatEpisodeDuration, type EpisodeFields, type EpisodeOperation, type StudioEpisode, type StudioEpisodePlan, type UnassignedUnits } from "@/lib/studio-breakdown";
import BreakdownDialog, { breakdownFieldClass } from "./BreakdownDialog";
import { sourceDialogClass } from "./SourceChoices";

type PlanOperation = EpisodeOperation extends infer Operation ? Operation extends EpisodeOperation ? Omit<Operation, "expected_revision"> : never : never;
export function episodeTiming(episode: StudioEpisode, defaultMin: number, defaultMax: number) {
  const min = episode.effective_target_min ?? episode.target_min ?? defaultMin, max = episode.effective_target_max ?? episode.target_max ?? defaultMax;
  return { min, max, outside: episode.est_seconds < min * .85 || episode.est_seconds > max * 1.15 };
}
export function EpisodeMoreMenu({ episode, next, busy, onEdit, onSplit, onDelete, onOperate }: { episode: StudioEpisode; next?: StudioEpisode; busy: boolean; onEdit: () => void; onSplit: () => void; onDelete: () => void; onOperate: (op: PlanOperation) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const adjacent = !!next && next.unit_from === episode.unit_to + 1;
  useEffect(() => { if (!open) return; const node = dialog.current; node?.showModal(); return () => node?.close(); }, [open]);
  const close = () => { dialog.current?.close(); setOpen(false); trigger.current?.focus?.({ preventScroll: true }); };
  const perform = (action: () => void) => { close(); action(); };
  return <><button ref={trigger} type="button" className="btn btn-quiet min-h-10" disabled={busy} aria-label={`第 ${episode.no} 集更多操作`} onClick={() => setOpen(true)}>更多</button>
    {open && <dialog ref={dialog} aria-labelledby={titleId} className={sourceDialogClass} onCancel={event => { event.preventDefault(); close(); }}>
      <h3 id={titleId} className="mb-4 text-xl tracking-[.16em]">第 {episode.no} 集 · 操作</h3>
      <div className="min-w-0 space-y-2">{[
        { label: "修改", action: onEdit, disabled: false },
        { label: "与下一集合并", action: () => void onOperate({ op: "merge", no: episode.no }).catch(() => {}), disabled: !next },
        { label: "拆分", action: onSplit, disabled: episode.unit_from === episode.unit_to },
        { label: "边界前移一场", action: () => void onOperate({ op: "move_boundary", no: episode.no, delta: -1 }).catch(() => {}), disabled: !adjacent || episode.unit_from === episode.unit_to },
        { label: "边界后移一场", action: () => void onOperate({ op: "move_boundary", no: episode.no, delta: 1 }).catch(() => {}), disabled: !adjacent || next?.unit_from === next?.unit_to },
        { label: "删除（变为未纳入）", action: onDelete, disabled: false },
      ].map(item => <button key={item.label} type="button" className="btn btn-quiet min-h-10 w-full whitespace-normal text-left" disabled={busy || item.disabled} onClick={() => perform(item.action)}>{item.label}</button>)}</div>
      <div className="mt-4 flex justify-end"><button type="button" className="btn btn-quiet min-h-10" onClick={close}>关闭</button></div>
    </dialog>}
  </>;
}
export function EpisodeEditDialog({ episode, busy, onSave, onClose }: { episode: StudioEpisode; busy: boolean; onSave: (fields: EpisodeFields) => Promise<void>; onClose: () => void }) {
  const id = useId();
  const [fields, setFields] = useState({ title: episode.title, change: episode.change, hook: episode.hook, notes: episode.notes, target_min: episode.target_min == null ? "" : String(episode.target_min), target_max: episode.target_max == null ? "" : String(episode.target_max) });
  const noTargets = !fields.target_min && !fields.target_max;
  const valid = !!fields.title.trim() && (noTargets || Number.isInteger(Number(fields.target_min)) && Number.isInteger(Number(fields.target_max)) && Number(fields.target_min) >= 60 && Number(fields.target_max) <= 900 && Number(fields.target_min) <= Number(fields.target_max));
  return <BreakdownDialog title={`修改第 ${episode.no} 集`} confirmLabel="保存" busy={busy} disabled={!valid} onClose={onClose} onConfirm={async () => { await onSave({ title: fields.title.trim(), change: fields.change, hook: fields.hook, notes: fields.notes, target_min: noTargets ? null : Number(fields.target_min), target_max: noTargets ? null : Number(fields.target_max) }); onClose(); }}>
    {([{ key: "title", label: "标题" }, { key: "change", label: "这集发生的变化" }, { key: "hook", label: "终点 / 钩子" }, { key: "notes", label: "备注" }] as const).map(({ key, label }) => <label key={key} htmlFor={`${id}-${key}`} className="block min-w-0 space-y-1 text-sm"><span>{label}</span>{key === "title" ? <input id={`${id}-${key}`} value={fields[key]} required className={breakdownFieldClass} onChange={event => setFields({ ...fields, [key]: event.target.value })} /> : <textarea id={`${id}-${key}`} value={fields[key]} rows={3} className={breakdownFieldClass} onChange={event => setFields({ ...fields, [key]: event.target.value })} />}</label>)}
    <p className="text-sm text-[color:var(--ink2)]">单集目标时长：两个都留空表示沿用项目默认。</p><div className="flex min-w-0 gap-3">{([{ key: "target_min", label: "最短秒数" }, { key: "target_max", label: "最长秒数" }] as const).map(({ key, label }) => <label key={key} htmlFor={`${id}-${key}`} className="min-w-0 flex-1 space-y-1 text-sm"><span>{label}</span><input id={`${id}-${key}`} type="number" min={60} max={900} step={1} value={fields[key]} className={breakdownFieldClass} onChange={event => setFields({ ...fields, [key]: event.target.value })} /></label>)}</div>{!valid && <p role="status" className="text-sm">请填写标题；目标时长需同时填写，且满足 60 ≤ 最短 ≤ 最长 ≤ 900 秒。</p>}
  </BreakdownDialog>;
}
export default function EpisodePlan({ plan, defaultMin = 180, defaultMax = 240, partial = false, busy, onOperate, onApprove, onExport }: { plan: StudioEpisodePlan; defaultMin?: number; defaultMax?: number; partial?: boolean; busy: boolean; onOperate: (op: EpisodeOperation) => Promise<void>; onApprove: (revision: number) => Promise<void>; onExport: () => Promise<void> }) {
  const planMin = plan.settings?.episode_seconds_min ?? defaultMin, planMax = plan.settings?.episode_seconds_max ?? defaultMax;
  const activeStatus = plan.active_breakdown_status ?? plan.status;
  const regenerating = partial || activeStatus === "running" || activeStatus === "partial";
  const editsBlocked = regenerating || !!plan.rebreakdown_pending;
  const approvalBlocked = editsBlocked || plan.status !== undefined && plan.status !== "done";
  const [edit, setEdit] = useState<StudioEpisode | null>(null);
  const [split, setSplit] = useState<StudioEpisode | null>(null);
  const [atUnit, setAtUnit] = useState(0);
  const [deleting, setDeleting] = useState<StudioEpisode | null>(null);
  const [insert, setInsert] = useState<UnassignedUnits | null>(null);
  const [insertTitle, setInsertTitle] = useState("");
  const [approving, setApproving] = useState(false);
  const operate = (op: PlanOperation) => editsBlocked ? Promise.reject(new Error("拆解未全部完成，暂不能修改分集方案。")) : onOperate({ ...op, expected_revision: plan.plan_revision } as EpisodeOperation);
  const menu = (episode: StudioEpisode, index: number) => <EpisodeMoreMenu episode={episode} next={plan.episodes[index + 1]} busy={busy || editsBlocked} onEdit={() => setEdit(episode)} onSplit={() => { setSplit(episode); setAtUnit(episode.unit_from + 1); }} onDelete={() => setDeleting(episode)} onOperate={operate} />;
  const timing = (episode: StudioEpisode) => {
    const value = episodeTiming(episode, planMin, planMax);
    return <span className={value.outside ? "font-medium text-[color:var(--seal)]" : ""}>{formatEpisodeDuration(episode.est_seconds)}{value.outside && <small className="mt-1 block">超出目标区间 ±15%</small>}</span>;
  };
  const uncovered = plan.unassigned ?? plan.uncovered ?? [];
  return <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5"><h2 className="mb-3 text-xl tracking-[.2em]">分集方案</h2>
    <div className="mb-4 flex min-w-0 flex-wrap items-center justify-between gap-3"><div className="min-w-0 space-y-1"><p role="status">方案第 {plan.plan_revision} 版 · {plan.g0_approved ? `已批准（第 ${plan.plan_approved_revision} 版）` : "待批准"}</p><p className="readout text-sm">共 {plan.episodes.length} 集 · 总预估时长 {formatEpisodeDuration(plan.total_seconds ?? plan.episodes.reduce((sum, item) => sum + item.est_seconds, 0))}</p></div><div className="flex min-w-0 flex-wrap gap-2"><button type="button" className="btn btn-primary min-h-10" disabled={busy || approvalBlocked || !plan.episodes.length || plan.g0_approved} onClick={() => setApproving(true)}>{plan.g0_approved ? "G0 已批准" : "批准分集方案"}</button><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => void onExport()}>导出 Markdown</button></div></div>
    {plan.rebreakdown_pending ? <p role="status" className="mb-3 text-sm">新的拆解进行中，完成后会替换此方案。当前保留的是上一次已发布的分集方案与 G0 状态；新方案发布后需要重新批准，等待期间暂不能修改或批准。</p> : regenerating ? <p role="status" className="mb-3 text-sm">拆解尚未全部完成，补跑完成后分集方案会按新结果重新生成。完成前暂不能修改或批准分集方案。</p> : approvalBlocked && <p role="status" className="mb-3 text-sm">{activeStatus === "cancelled" ? "本次拆解已取消，重新拆解完成后才能批准 G0。" : "分集尚有分段未完成，全部完成后才能批准 G0。"}</p>}
    {!plan.episodes.length ? <EmptyState>分集方案还未生成。已完成的分段会先显示在这里。</EmptyState> : <>
      <div data-testid="episode-table" className="hidden max-w-full overflow-x-auto rounded-lg border border-[color:var(--carve)] @[640px]:block"><table className="w-full min-w-[1040px] table-fixed break-words text-left text-sm leading-relaxed"><thead className="border-b border-[color:var(--carve)] text-[color:var(--ink2)]"><tr>{["集号", "标题", "原文范围", "这集发生的变化", "终点 / 钩子", "预估镜头数", "预估时长", "目标时长", "出场人物", "操作"].map((label, index) => <th key={label} scope="col" className={`p-3 font-normal ${index === 0 ? "w-16" : index === 9 ? "sticky right-0 z-10 w-20 border-l border-[color:var(--carve)] bg-[color:var(--paper)]" : index === 3 || index === 4 ? "w-[200px]" : ""}`}>{label}</th>)}</tr></thead><tbody>{plan.episodes.map((episode, index) => { const target = episodeTiming(episode, planMin, planMax); return <tr key={episode.id || episode.no} className="border-b border-[color:var(--carve)] align-top last:border-0"><td className="readout p-3">{episode.no}</td><td className="p-3">{episode.title}{episode.notes && <small className="mt-1 block text-[color:var(--ink2)]">备注：{episode.notes}</small>}</td><td className="p-3">{episode.source_range}</td><td className="whitespace-pre-wrap p-3">{episode.change}</td><td className="whitespace-pre-wrap p-3">{episode.hook}{episode.warnings.length > 0 && <details className="mt-2 text-[color:var(--ink2)]"><summary className="min-h-10 cursor-pointer">{episode.warnings.length} 条提示</summary><ul>{episode.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}</td><td className="readout p-3">{episode.est_shots}</td><td className="p-3">{timing(episode)}</td><td className="readout p-3">{target.min}–{target.max} 秒{episode.target_min == null && <small className="block">项目默认</small>}</td><td className="p-3">{episode.characters.join("、") || "—"}</td><td className="sticky right-0 z-10 w-20 border-l border-[color:var(--carve)] bg-[color:var(--paper)] p-3">{menu(episode, index)}</td></tr>; })}</tbody></table></div>
      <div data-testid="episode-cards" className="min-w-0 space-y-3 @[640px]:hidden">{plan.episodes.map((episode, index) => { const target = episodeTiming(episode, planMin, planMax); return <article key={episode.id || episode.no} className="ceramic-card min-w-0 space-y-3 rounded-xl p-3 text-sm"><h3 className="break-words font-medium">第 {episode.no} 集 · {episode.title}</h3><dl className="min-w-0 space-y-2 break-words"><div><dt className="text-[color:var(--ink2)]">原文范围</dt><dd>{episode.source_range}</dd></div><div><dt className="text-[color:var(--ink2)]">这集发生的变化</dt><dd className="whitespace-pre-wrap">{episode.change || "—"}</dd></div><div><dt className="text-[color:var(--ink2)]">终点 / 钩子</dt><dd className="whitespace-pre-wrap">{episode.hook || "—"}</dd></div><div><dt className="text-[color:var(--ink2)]">预估镜头数 / 时长</dt><dd>{episode.est_shots} 镜 · {timing(episode)}</dd></div><div><dt className="text-[color:var(--ink2)]">目标时长</dt><dd>{target.min}–{target.max} 秒{episode.target_min == null ? "（项目默认）" : ""}</dd></div><div><dt className="text-[color:var(--ink2)]">出场人物</dt><dd>{episode.characters.join("、") || "—"}</dd></div>{episode.notes && <div><dt className="text-[color:var(--ink2)]">备注</dt><dd>{episode.notes}</dd></div>}</dl>{episode.warnings.length > 0 && <details><summary className="min-h-10 cursor-pointer">{episode.warnings.length} 条提示</summary><ul>{episode.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}{menu(episode, index)}</article>; })}</div>
    </>}
    {uncovered.length > 0 && <section className="mt-4 min-w-0 space-y-2"><h3 className="text-sm text-[color:var(--ink2)]">未纳入的单元</h3>{uncovered.map(range => <div key={range.unit_from} className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-lg bg-[color:var(--slip)] p-3 text-sm text-[color:var(--ink2)]"><span className="min-w-0 break-words">未纳入 · {range.source_range || range.label || `场景 ${range.unit_from}–${range.unit_to}`}</span><button type="button" className="btn btn-quiet min-h-10" disabled={busy || editsBlocked} onClick={() => { setInsert(range); setInsertTitle(""); }}>建成一集</button></div>)}</section>}
    {edit && <EpisodeEditDialog key={plan.plan_revision} episode={edit} busy={busy || editsBlocked} onSave={fields => operate({ op: "edit", no: edit.no, fields })} onClose={() => setEdit(null)} />}
    {split && <BreakdownDialog title={`拆分第 ${split.no} 集`} confirmLabel="确认拆分" busy={busy || editsBlocked} onClose={() => setSplit(null)} disabled={!atUnit} onConfirm={async () => { await operate({ op: "split", no: split.no, at_unit: atUnit }); setSplit(null); }}><p>选择从哪一场开始作为新一集，新集标题为「{split.title}（下）」。</p><label className="block space-y-1 text-sm"><span>新一集起点</span><select aria-label="拆分点" className={breakdownFieldClass} value={atUnit} onChange={event => setAtUnit(Number(event.target.value))}>{Array.from({ length: split.unit_to - split.unit_from }, (_, i) => split.unit_from + 1 + i).map(seq => <option key={seq} value={seq}>{plan.units.find(unit => unit.seq === seq)?.label || `场景 ${seq}`}</option>)}</select></label></BreakdownDialog>}
    {deleting && <BreakdownDialog title={`删除第 ${deleting.no} 集`} confirmLabel="确认删除" busy={busy || editsBlocked} onClose={() => setDeleting(null)} onConfirm={async () => { await operate({ op: "delete", no: deleting.no }); setDeleting(null); }}><p>该集的原文场景将变为「未纳入」，之后可以重新建成一集。</p></BreakdownDialog>}
    {insert && <BreakdownDialog title="把未纳入单元建成一集" confirmLabel="建成一集" busy={busy || editsBlocked} onClose={() => setInsert(null)} onConfirm={async () => { await operate({ op: "insert", unit_from: insert.unit_from, unit_to: insert.unit_to, ...(insertTitle.trim() ? { title: insertTitle.trim() } : {}) }); setInsert(null); }}><p>{insert.source_range || insert.label || `场景 ${insert.unit_from}–${insert.unit_to}`}</p><label className="block space-y-1 text-sm"><span>标题（可选）</span><input className={breakdownFieldClass} value={insertTitle} onChange={event => setInsertTitle(event.target.value)} /></label></BreakdownDialog>}
    {approving && <BreakdownDialog title="批准分集方案" confirmLabel="确认批准" busy={busy || approvalBlocked} onClose={() => setApproving(false)} onConfirm={async () => { await onApprove(plan.plan_revision); setApproving(false); }}><p>即将批准方案第 {plan.plan_revision} 版。批准后再改会生成新版本、需要重新批准。</p></BreakdownDialog>}
  </Glaze>;
}
