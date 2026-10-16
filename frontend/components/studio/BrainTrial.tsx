"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { novelFieldClass } from "@/components/novel/NovelModelFields";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { brainStatusLabel, brainTaskLabel, getBrainGroup, hasBrainInflightJobs, quoteBrainTrial, releaseStudioJob, startBrainTrial, studioErrorMessage, type BrainGroup, type BrainJob, type BrainProvider, type BrainProviderId, type BrainQuote, type BrainTask, type BrainTrialInput } from "@/lib/studio";

const tasks: BrainTask[] = ["read_through", "style_proposals", "bible_extract"];
const providerLabels = { claude: "Claude", qwen: "千问", deepseek: "DeepSeek" };
const dialogClass = "m-auto max-h-[85dvh] w-[min(620px,calc(100vw-32px))] max-w-full overflow-y-auto rounded-2xl border border-[color:var(--carve)] bg-[color:var(--paper)] p-6 text-[color:var(--ink)] backdrop:bg-[color:var(--scrim)] mobile:p-4";

export function BrainProviderPicker({ providers, current, busy, onChange }: { providers: BrainProvider[]; current: BrainProviderId; busy: boolean; onChange: (id: BrainProviderId) => Promise<void> }) {
  return <fieldset disabled={busy} className="mt-4 min-w-0"><legend className="mb-2 text-sm">导演模型</legend>
    <div className="flex min-w-0 flex-wrap gap-2">{providers.map(provider => <div key={provider.id} className="min-w-0 max-w-full">
      <button type="button" aria-pressed={current === provider.id} disabled={busy || !provider.available} aria-describedby={!provider.available ? `brain-unavailable-${provider.id}` : undefined} title={provider.reason} onClick={() => { void onChange(provider.id); }} className={`chip min-h-10 max-w-full whitespace-normal break-words px-3 py-2 text-left ${current === provider.id ? "chip-on" : ""} disabled:opacity-50`}>
        {providerLabels[provider.id]}{provider.id === "claude" && provider.model ? `（${provider.model}）` : ""}
      </button>
      {!provider.available && <p id={`brain-unavailable-${provider.id}`} className="mt-1 max-w-[280px] text-xs leading-relaxed text-[color:var(--ink2)]">{provider.reason || "暂不可用"}</p>}
    </div>)}</div>
  </fieldset>;
}

interface TrialProps {
  projectId: string; owner: string; provider: BrainProviderId; providers: BrainProvider[]; busy?: boolean;
  onProviderChange: (provider: BrainProviderId) => Promise<void>; onBusyChange: (busy: boolean) => void;
  onChanged: () => Promise<void>; onPoll: () => Promise<void>;
}

export default function BrainTrial(props: TrialProps) {
  return <AccountBrainTrial key={`${props.owner}:${props.projectId}`} {...props} />;
}

export function AccountBrainTrial({ projectId, owner, provider, providers, busy = false, onProviderChange, onBusyChange, onChanged, onPoll }: TrialProps) {
  const [text, setText] = useState("");
  const [selected, setSelected] = useState<BrainTask[]>(tasks);
  const [group, setGroup] = useState<BrainGroup | null>(null);
  const [quote, setQuote] = useState<{ value: BrainQuote; input: BrainTrialInput } | null>(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [releaseJob, setReleaseJob] = useState<BrainJob | null>(null);
  const [releaseError, setReleaseError] = useState("");
  const [attemptFailure, setAttemptFailure] = useState({ provider, failed: false });
  // Keep trial data when switching models, but forget the previous selection's failure.
  if (attemptFailure.provider !== provider) setAttemptFailure({ provider, failed: false });
  const lock = useRef(false);
  const reading = useRef(false);
  const active = useRef(false);
  const groupId = useRef<string | null>(null);
  const busyRef = useRef(busy);
  useEffect(() => { busyRef.current = busy; }, [busy]);
  const textId = useId();
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);
  const disabled = busy || working;
  const running = !!group && hasBrainInflightJobs(group.jobs);
  const refresh = useCallback(async () => {
    if (!groupId.current || lock.current || busyRef.current || reading.current) return;
    const request = beginRead();
    if (!request) return;
    reading.current = true;
    try {
      const next = await getBrainGroup(projectId, groupId.current, request.signal);
      if (!request.isCurrent()) return;
      active.current = hasBrainInflightJobs(next.jobs);
      setGroup(next); setError("");
      await onPoll();
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { reading.current = false; }
  }, [beginRead, onPoll, projectId]);
  useEffect(() => {
    if (!running) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => { clearTimeout(timer); if (!stopped && !document.hidden && active.current) timer = setTimeout(tick, 3000); };
    const tick = async () => { if (stopped || document.hidden || !active.current) return; await refresh(); schedule(); };
    const visibility = () => { clearTimeout(timer); if (!document.hidden) void tick(); };
    schedule(); document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [refresh, running]);

  const getQuote = async (mode: BrainTrialInput["providers"]) => {
    if (lock.current || disabled) return;
    if (!text.trim() || Array.from(text).length > 20000 || selected.length === 0) { setError("请填写 1–20000 字素材，并至少选择一项任务。"); return; }
    const request = beginMutation();
    if (!request) return;
    const input: BrainTrialInput = { text, tasks: [...selected], providers: mode };
    lock.current = true; setWorking(true); onBusyChange(true); setError(""); setAttemptFailure({ provider, failed: false });
    try {
      const value = await quoteBrainTrial(projectId, input, request.signal);
      if (request.isCurrent()) setQuote({ value, input });
    } catch (cause) {
      if (request.isCurrent()) {
        setError(studioErrorMessage(cause));
        if (provider === "claude") setAttemptFailure({ provider, failed: true });
      }
    }
    finally { lock.current = false; if (request.isCurrent()) { setWorking(false); onBusyChange(false); } }
  };
  const submit = async () => {
    if (!quote || lock.current || disabled) return;
    const request = beginMutation();
    if (!request) return;
    lock.current = true; setWorking(true); onBusyChange(true);
    try {
      const next = await startBrainTrial(projectId, quote.input, request.signal);
      if (!request.isCurrent()) return;
      groupId.current = next.group_id; active.current = hasBrainInflightJobs(next.jobs);
      setGroup(next); setQuote(null); setError("");
      await onChanged();
    } catch (cause) {
      if (request.isCurrent() && provider === "claude") setAttemptFailure({ provider, failed: true });
      throw cause;
    } finally { lock.current = false; if (request.isCurrent()) { setWorking(false); onBusyChange(false); } }
  };
  const release = async () => {
    if (!releaseJob || lock.current || disabled) return;
    const request = beginMutation();
    if (!request) return;
    lock.current = true; setWorking(true); onBusyChange(true); setReleaseError("");
    try {
      await releaseStudioJob(releaseJob.id, request.signal);
      if (!request.isCurrent()) return;
      if (groupId.current) {
        const next = await getBrainGroup(projectId, groupId.current, request.signal);
        if (!request.isCurrent()) return;
        setGroup(next); active.current = hasBrainInflightJobs(next.jobs);
      }
      setReleaseJob(null); await onChanged();
    } catch (cause) { if (request.isCurrent()) setReleaseError(studioErrorMessage(cause)); }
    finally { lock.current = false; if (request.isCurrent()) { setWorking(false); onBusyChange(false); } }
  };
  const claudeUnavailable = provider === "claude" && (attemptFailure.provider === provider && attemptFailure.failed
    || providers.some(item => item.id === "claude" && !item.available)
    || !!group?.jobs.some(job => job.provider === "claude" && ["failed", "rejected", "uncertain", "invalid_output"].includes(job.status)));
  return <div className="min-w-0 space-y-5 [&_.tag]:h-auto [&_.tag]:min-h-[22px] [&_.tag]:whitespace-normal [&_.tag]:py-1 [&_.tag]:leading-relaxed">
    <p className="text-sm leading-relaxed text-[color:var(--ink2)]">这是拆解功能的预览，正式拆解在后续版本</p>
    <div className="ceramic-card min-w-0 space-y-4 rounded-2xl p-5">
      <h2 className="text-xl tracking-[.24em]">剧本试读</h2>
      <label htmlFor={textId} className="block text-sm">粘贴剧本或小说</label>
      <textarea id={textId} value={text} maxLength={40000} rows={10} disabled={disabled} className={`${novelFieldClass} min-h-48 resize-y`} onChange={event => setText(Array.from(event.target.value).slice(0, 20000).join(""))} aria-describedby={`${textId}-count`} />
      <p id={`${textId}-count`} className="readout text-right">{Array.from(text).length} / 20000 字</p>
      <fieldset disabled={disabled}><legend className="mb-2 text-sm">试读任务</legend><div className="flex flex-wrap gap-x-5 gap-y-2">{tasks.map(task => <label key={task} className="inline-flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" checked={selected.includes(task)} onChange={event => setSelected(previous => event.target.checked ? tasks.filter(item => item === task || previous.includes(item)) : previous.filter(item => item !== task))} className="h-5 w-5 accent-[color:var(--ink)]" />{brainTaskLabel(task)}</label>)}</div></fieldset>
      <div className="flex flex-wrap gap-3"><button type="button" disabled={disabled || !text.trim() || selected.length === 0} className="btn btn-primary min-h-10 max-w-full whitespace-normal" onClick={() => void getQuote("current")}>用当前导演模型试读</button><button type="button" disabled={disabled || !text.trim() || selected.length === 0} className="btn btn-quiet min-h-10 max-w-full whitespace-normal" onClick={() => void getQuote("all")}>三家都跑（对比）</button></div>
      {working && <LoadingState>正在处理…</LoadingState>}
      {error && <ErrorNotice message={error} />}
      {claudeUnavailable && <div className="space-y-2"><p className="text-sm">本次试读未完成，可手动更换导演模型后再试读</p><div className="flex flex-wrap gap-2">{providers.filter(item => item.id !== "claude").map(item => <button key={item.id} type="button" className="btn btn-quiet min-h-10" disabled={disabled || !item.available} onClick={() => { void onProviderChange(item.id); }}>改用{item.id === "deepseek" ? " DeepSeek" : providerLabels[item.id]}</button>)}</div></div>}
    </div>
    {group ? <BrainResults group={group} busy={disabled} onRelease={job => { setReleaseError(""); setReleaseJob(job); }} /> : <EmptyState>试读结果会显示在这里。</EmptyState>}
    {quote && <BrainQuoteDialog quote={quote.value} busy={disabled} onClose={() => setQuote(null)} onConfirm={submit} />}
    {releaseJob && <BrainReleaseDialog busy={disabled} error={releaseError} onClose={() => setReleaseJob(null)} onConfirm={release} />}
  </div>;
}

export function BrainQuoteDialog({ quote, busy, onClose, onConfirm }: { quote: BrainQuote; busy: boolean; onClose: () => void; onConfirm: () => Promise<void> }) {
  const ref = useRef<HTMLDialogElement>(null);
  const locked = useRef(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const titleId = useId();
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  const confirm = async () => {
    if (locked.current || busy) return;
    locked.current = true; setConfirming(true); setError("");
    try { await onConfirm(); } catch (cause) { setError(studioErrorMessage(cause)); }
    finally { locked.current = false; setConfirming(false); }
  };
  return <dialog ref={ref} aria-labelledby={titleId} onCancel={event => { if (busy || confirming) event.preventDefault(); else onClose(); }} className={dialogClass}>
    <h2 id={titleId} className="mb-5 text-xl tracking-[.24em]">确认剧本试读</h2>
    <p className="text-sm leading-relaxed">预估最高花费（包含最多一次输出修正）：</p>
    <div className="ceramic-card my-4 space-y-2 p-4"><p>人民币 <span className="readout">¥{quote.totals.CNY.toFixed(2)}</span></p><p>美元 <span className="readout">${quote.totals.USD.toFixed(2)}</span></p></div>
    <ul className="space-y-1 text-sm">{quote.items.map((item, index) => <li key={`${item.provider}:${item.task}:${index}`}>{providerLabels[item.provider]} · {brainTaskLabel(item.task)} · {item.model}</li>)}</ul>
    {error && <div className="mt-4"><ErrorNotice message={error} /></div>}
    <div className="mt-6 flex flex-wrap justify-end gap-3"><button type="button" disabled={busy || confirming} className="btn btn-quiet min-h-10" onClick={onClose}>取消</button><button type="button" disabled={busy || confirming} className="btn btn-primary min-h-10" onClick={() => void confirm()}>{confirming ? "正在提交…" : "确认花费，开始试读"}</button></div>
  </dialog>;
}

function BrainReleaseDialog({ busy, error, onClose, onConfirm }: { busy: boolean; error: string; onClose: () => void; onConfirm: () => Promise<void> }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} aria-labelledby={titleId} className={dialogClass} onCancel={event => { if (busy) event.preventDefault(); else onClose(); }}>
    <h2 id={titleId} className="text-xl tracking-[.24em]">释放额度前再次确认</h2><p className="my-5 text-sm leading-relaxed">可能已扣费。请先在供应商控制台核对，只有确认这次调用未扣费后才能释放预留额度。</p>
    {error && <ErrorNotice message={error} />}
    <div className="mt-5 flex flex-wrap justify-end gap-3"><button type="button" disabled={busy} className="btn btn-quiet min-h-10" onClick={onClose}>取消</button><button type="button" disabled={busy} className="btn btn-danger min-h-10 max-w-full whitespace-normal" onClick={() => void onConfirm()}>我已核实未扣费，释放额度</button></div>
  </dialog>;
}

export function BrainResults({ group, busy, onRelease }: { group: BrainGroup; busy: boolean; onRelease: (job: BrainJob) => void }) {
  const providers = (["claude", "qwen", "deepseek"] as const).filter(provider => group.jobs.some(job => job.provider === provider));
  return <div aria-label="试读结果对比" className={`grid min-w-0 grid-cols-1 items-start gap-4 ${providers.length > 1 ? "@[960px]:grid-cols-3" : ""}`}>{providers.map(provider => <section key={provider} className="min-w-0 space-y-4" aria-label={providerLabels[provider]}>
    <h2 className="text-lg tracking-[.24em]">{providerLabels[provider]}</h2>
    {group.jobs.filter(job => job.provider === provider && !job.parent_job_id).map(job => <BrainResultCard key={job.id} attempts={[job, ...group.jobs.filter(attempt => attempt.parent_job_id === job.id)]} busy={busy} onRelease={onRelease} />)}
  </section>)}</div>;
}

export function BrainResultCard({ attempts, busy, onRelease }: { attempts: BrainJob[]; busy: boolean; onRelease: (job: BrainJob) => void }) {
  const job = attempts[attempts.length - 1];
  return <article className="ceramic-card min-w-0 space-y-4 rounded-2xl p-4 [overflow-wrap:anywhere] [&_.tag]:h-auto [&_.tag]:min-h-[22px] [&_.tag]:whitespace-normal [&_.tag]:py-1 [&_.tag]:leading-relaxed">
    <div className="flex flex-wrap items-center gap-2"><h3 className="text-base tracking-[.24em]">{brainTaskLabel(job.task)}</h3><span className="tag">{brainStatusLabel(job.status)}</span>{job.repaired && <span className="tag">已修正</span>}</div>
    {(job.status === "queued" || job.status === "running") && <p className="text-xs leading-relaxed text-[color:var(--ink2)]">长任务可能需要数分钟</p>}
    {job.output && <BrainOutput task={job.task} output={job.output} />}
    {attempts.map((attempt, index) => <div key={attempt.id} className="space-y-2 border-t border-[color:var(--carve)] pt-3 text-xs leading-relaxed">
      <p className="break-words">{attempts.length > 1 ? `${index === 0 ? "原始" : "修正"}调用 · ` : ""}{attempt.model}</p>
      <p className="readout">{brainCallCost(attempt)}{attempt.latency_s != null ? ` · ${attempt.latency_s.toFixed(1)} 秒` : ""}</p>
      {attempt.warnings?.map((warning, warningIndex) => <p key={warningIndex} className="tag tag-rec block">警告：{warning}</p>)}
      {attempt.status === "uncertain" ? <><p className="tag tag-rec block">可能已扣费，请先核对供应商控制台。</p>{attempt.error_message && <p>{attempt.error_message}</p>}<button type="button" disabled={busy} className="btn btn-danger min-h-10 max-w-full whitespace-normal" onClick={() => onRelease(attempt)}>确认未扣费后释放</button></> : ["rejected", "failed", "invalid_output"].includes(attempt.status) && <p>{attempt.error_message || "调用未完成，请查看提供方配置后重新试读。"}</p>}
    </div>)}
  </article>;
}

function brainCallCost(job: BrainJob) {
  const actual = job.cost?.amount;
  const reserved = job.reserved_amount == null ? null : Number(job.reserved_amount);
  const amount = actual ?? reserved;
  if (amount == null || !Number.isFinite(amount)) return "费用待结算";
  return `${actual == null ? "预留" : "费用"} ${job.cost?.currency === "USD" ? "$" : "¥"}${amount.toFixed(4)}`;
}

const string = (value: unknown) => typeof value === "string" ? value : "";
const rows = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object" && !Array.isArray(item)) : [];

export function BrainOutput({ task, output }: { task: BrainTask; output: Record<string, unknown> }) {
  if (task === "read_through") return <div className="space-y-3 text-sm leading-relaxed">{([ ["logline", "一句话梗概"], ["synopsis", "梗概"], ["genre", "类型"], ["tone", "基调"], ["theme", "主题"], ["pacing", "节奏"] ] as const).map(([field, label]) => <div key={field}><h4 className="mb-1 text-[color:var(--ink2)]">{label}</h4><p className="whitespace-pre-wrap">{string(output[field])}</p></div>)}<div><h4 className="mb-1 text-[color:var(--ink2)]">改编风险</h4><ul className="space-y-1">{(Array.isArray(output.adaptation_risks) ? output.adaptation_risks : []).map((risk, index) => <li key={index}>{string(risk)}</li>)}</ul></div></div>;
  if (task === "style_proposals") return <div className="space-y-3">{rows(output.proposals).map((proposal, index) => <section key={index} className="ceramic-card min-w-0 space-y-2 p-3 text-sm leading-relaxed"><h4 className="tracking-[.24em]">{string(proposal.name)}</h4>{([ ["visual_style", "视觉"], ["palette", "配色"], ["camera", "镜头"], ["lighting", "光线"], ["rationale", "提案理由"] ] as const).map(([field, label]) => <p key={field}><span className="text-[color:var(--ink2)]">{label}：</span>{string(proposal[field])}</p>)}</section>)}</div>;
  return <div className="min-w-0 space-y-4">{([ ["characters", "人物"], ["locations", "场景"], ["props", "道具"] ] as const).map(([field, label]) => <section key={field} className="min-w-0"><h4 className="mb-2 text-sm tracking-[.24em]">{label}</h4><table className="w-full table-fixed border-collapse text-left text-xs leading-relaxed"><thead><tr><th className="w-[28%] border-b border-[color:var(--carve)] px-1 py-2 font-normal">名称</th><th className="border-b border-[color:var(--carve)] px-1 py-2 font-normal">{field === "characters" ? "人物与外形" : "描述"}</th></tr></thead><tbody>{rows(output[field]).map((item, index) => <tr key={index}><td className="break-words border-b border-[color:var(--carve)] px-1 py-2 align-top">{string(item.name)}</td><td className="space-y-1 break-words border-b border-[color:var(--carve)] px-1 py-2 align-top">{field === "characters" && <p>{string(item.role)}</p>}<p>{string(item.description)}</p>{field === "characters" && (item.appearance_status === "needs_author" ? <span className="tag">待作者补充</span> : <p>外形原文：{string(item.appearance_excerpt)}</p>)}</td></tr>)}</tbody></table></section>)}</div>;
}
