"use client";

import { useEffect, useRef, useState } from "react";
import NovelModelFields from "@/components/novel/NovelModelFields";
import { ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import type { NovelAutomation, NovelCatalog, NovelDetail, NovelPatchInput } from "@/lib/novels";

const fieldClass = "ceramic-card min-h-10 w-full min-w-0 rounded-[10px] px-4 py-3 text-[16px] text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";

export function minimumNovelResumeBudget(originalBudget: number, spent: number, budgetAtPause?: number): number {
  const pauseMinimum = typeof budgetAtPause === "number" && Number.isFinite(budgetAtPause) && budgetAtPause >= 0 ? budgetAtPause + 1 : 0;
  return Math.max(originalBudget + 1, Math.ceil(spent * 1.25) + 1, pauseMinimum);
}

export default function NovelSettingsDialog({ book, catalog, catalogError = "", busy, resumeAfter, onSave, onClose }: { book: NovelDetail; catalog: NovelCatalog | null; catalogError?: string; busy: boolean; resumeAfter: boolean; onSave: (patch: NovelPatchInput, resume: boolean) => Promise<void>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [budget, setBudget] = useState(String(book.budget_strawberries));
  const [automation, setAutomation] = useState<NovelAutomation>(book.config.automation);
  const [batch, setBatch] = useState(book.config.batch_size);
  const [agents, setAgents] = useState(() => ({ ...book.config.agents }));
  const [error, setError] = useState("");
  const [budgetError, setBudgetError] = useState("");
  const [batchError, setBatchError] = useState("");
  const budgetAtPause = resumeAfter && book.pause_reason === "budget_80" && typeof book.config._budget_at_pause === "number" ? book.config._budget_at_pause : undefined;
  const minimumBudget = resumeAfter ? minimumNovelResumeBudget(book.budget_strawberries, book.spent_strawberries, budgetAtPause) : Math.max(1, book.spent_strawberries);
  const canChangeModels = book.status === "paused" || book.status.startsWith("awaiting_");
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => { dialog?.close(); }; }, []);
  const save = async () => {
    const nextBudget = Number(budget);
    setError(""); setBudgetError(""); setBatchError("");
    if (!Number.isInteger(nextBudget) || nextBudget < 1 || nextBudget > 10000000) { setBudgetError("预算须为不低于已花草莓的整数，最多 10000000。"); return; }
    if (resumeAfter && nextBudget < minimumBudget) { setBudgetError(`预算至少要 ${minimumBudget} 草莓才能继续`); return; }
    if (nextBudget < book.spent_strawberries) { setBudgetError("预算须为不低于已花草莓的整数，最多 10000000。"); return; }
    if (!Number.isInteger(batch) || batch < 1 || batch > 10) { setBatchError("每批章数须为 1–10 的整数。"); return; }
    const patch: NovelPatchInput = {};
    if (nextBudget !== book.budget_strawberries) patch.budget_strawberries = nextBudget;
    if (automation !== book.config.automation) patch.automation = automation;
    if (batch !== book.config.batch_size) patch.batch_size = batch;
    if (canChangeModels && JSON.stringify(agents) !== JSON.stringify(book.config.agents)) patch.agents = agents;
    try { await onSave(patch, resumeAfter); onClose(); } catch (cause) { setError(cause instanceof Error ? cause.message : "调整未保存，请重试。"); }
  };
  return <dialog ref={ref} onCancel={event => { if (busy) event.preventDefault(); else onClose(); }} className="m-auto max-h-[85dvh] w-[min(720px,calc(100vw-32px))] max-w-full overflow-y-auto rounded-2xl border border-[color:var(--carve)] bg-[color:var(--paper)] p-6 text-[color:var(--ink)] backdrop:bg-[color:var(--scrim)] mobile:p-4" aria-labelledby="novel-adjust-title">
    <div className="mb-5 flex items-center justify-between gap-4"><h2 id="novel-adjust-title" className="text-xl tracking-[.24em]">调整写作</h2><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onClose}>关闭</button></div>
    <div className="space-y-5">{error && <ErrorNotice message={error} />}
      <label className="block space-y-2"><span className="text-sm">草莓预算</span><input className={fieldClass} type="number" min={minimumBudget} max={10000000} step={1} value={budget} disabled={busy} aria-invalid={!!budgetError} aria-describedby={budgetError ? "novel-adjust-budget-error" : undefined} onChange={event => setBudget(event.target.value)} />{budgetError && <span id="novel-adjust-budget-error" role="alert" className="block text-sm">{budgetError}</span>}</label>
      <label className="block space-y-2"><span className="text-sm">自动化方式</span><select className={fieldClass} value={automation} disabled={busy} onChange={event => setAutomation(event.target.value as NovelAutomation)}><option value="per_batch">每写 N 章停下来给我看</option><option value="per_chapter">每章先给我看细纲</option><option value="full_auto">全自动写到完结</option></select></label>
      {automation === "per_batch" && <label className="block space-y-2"><span className="text-sm">每批章数（1–10）</span><input className={fieldClass} type="number" min={1} max={10} step={1} value={batch} disabled={busy} aria-invalid={!!batchError} aria-describedby={batchError ? "novel-adjust-batch-error" : undefined} onChange={event => setBatch(Number(event.target.value))} />{batchError && <span id="novel-adjust-batch-error" role="alert" className="block text-sm">{batchError}</span>}</label>}
      {canChangeModels ? <section className="space-y-3 border-t pt-5" style={{ borderColor: "var(--carve)" }}><h3 className="tracking-[.12em]">智能体模型</h3>{catalog ? <NovelModelFields catalog={catalog} agents={agents} onChange={setAgents} disabled={busy} panelMode={book.config.panel_mode} /> : catalogError ? <ErrorNotice message={catalogError} /> : <LoadingState>正在加载可用模型…</LoadingState>}</section> : <p className="text-sm leading-[1.9] text-[color:var(--ink2)]">暂停或等待确认时，可以在这里调整各位智能体的模型。</p>}
      <button type="button" className="btn btn-primary min-h-10" disabled={busy} onClick={() => void save()}>{busy ? "正在保存…" : resumeAfter ? "保存并继续" : "保存调整"}</button>
    </div>
  </dialog>;
}
