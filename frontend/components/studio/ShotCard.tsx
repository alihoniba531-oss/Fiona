"use client";

import { useEffect, useId, useRef, useState } from "react";
import { novelFieldClass } from "@/components/novel/NovelModelFields";
import { ErrorNotice } from "@/components/novel/NovelStates";
import { formatStudioDate, studioAssetUrl, studioErrorCodeLabel, studioErrorMessage, studioModelLabel, studioStatusLabel, type StudioClipParams, type StudioJob } from "@/lib/studio";
import StudioAssetImage from "./StudioAssetImage";

export interface ShotActions {
  busy?: boolean;
  onCancel: (job: StudioJob) => Promise<void>;
  onRecheck: (job: StudioJob) => Promise<void>;
  onLinkTask: (job: StudioJob, taskId: string) => Promise<void>;
  onRelease: (job: StudioJob) => Promise<void>;
  onRefill: (params: StudioClipParams) => void;
}

const retryStatuses = new Set(["failed", "rejected", "filtered", "expired", "cancelled", "released"]);

export default function ShotCard({ job, busy = false, onCancel, onRecheck, onLinkTask, onRelease, onRefill }: ShotActions & { job: StudioJob }) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [taskId, setTaskId] = useState("");
  const [releaseOpen, setReleaseOpen] = useState(false);
  const locked = useRef(false);
  const taskInputId = useId();
  const disabled = busy || working;
  const uncertain = job.status === "uncertain";
  const canRecheck = job.status === "submitted" || job.status === "running" || !!job.needs_recheck || uncertain && !!job.task_id;
  const canRetry = retryStatuses.has(job.status);
  const errorDescription = job.error_code ? studioErrorCodeLabel(job.error_code) : job.error_message || (canRetry ? studioStatusLabel(job.status) : "");
  const run = async (operation: () => Promise<void>): Promise<boolean> => {
    if (locked.current || busy) return false;
    locked.current = true;
    setWorking(true);
    setError("");
    try { await operation(); return true; }
    catch (cause) { setError(studioErrorMessage(cause)); return false; }
    finally { locked.current = false; setWorking(false); }
  };
  return <article className="ceramic-card min-w-0 space-y-4 rounded-[16px] p-4 [overflow-wrap:anywhere]" aria-label={`镜头：${studioStatusLabel(job.status)}`}>
    {job.params.first_frame_asset_id && <div className="mount-frame overflow-hidden rounded-[10px] p-2"><StudioAssetImage assetId={job.params.first_frame_asset_id} alt="镜头首帧" className="max-h-56" /></div>}
    <div className="flex min-w-0 flex-wrap gap-2"><span className="chip">{studioModelLabel(job.model || job.provider)}</span><span className="chip">{job.params.resolution.toUpperCase()}</span><span className="chip">{job.params.duration === -1 ? `${job.params.duration_min_s}–${job.params.duration_max_s}` : job.params.duration} 秒</span></div>
    <p className="text-[14px] leading-[1.9]">{job.actual_cny != null ? <>实付 <span className="readout">¥{job.actual_cny.toFixed(2)}</span></> : <>预估 <span className="readout">¥{job.est_min_cny.toFixed(2)}–¥{job.est_max_cny.toFixed(2)}</span>（预留 <span className="readout">¥{job.reserved_cny.toFixed(2)}</span>）</>}</p>
    <div className="flex min-w-0 flex-wrap items-center gap-2"><span className="tag">{studioStatusLabel(job.status)}</span><time dateTime={job.created_at} className="readout break-words">{formatStudioDate(job.created_at)}</time></div>
    {job.status === "downloaded" && job.result_asset_id && <video controls preload="metadata" src={studioAssetUrl(job.result_asset_id)} className="block max-h-[420px] w-full min-w-0 rounded-[10px]" aria-label="生成的镜头" />}
    {uncertain && <p className="tag tag-rec block whitespace-normal break-words leading-[1.9]">可能已扣费，请勿直接重试，去控制台核对</p>}
    {canRetry && errorDescription && <p className="text-[13px] leading-[1.9] text-[color:var(--ink2)]">{errorDescription}</p>}
    <div className="flex min-w-0 flex-wrap gap-2">
      {job.status === "queued" && <button type="button" className="btn btn-quiet min-h-10" disabled={disabled} onClick={() => void run(() => onCancel(job))}>取消</button>}
      {canRecheck && <button type="button" className="btn btn-quiet min-h-10" disabled={disabled} onClick={() => void run(() => onRecheck(job))}>重新查询</button>}
      {canRetry && <button type="button" className="btn btn-quiet min-h-10 max-w-full whitespace-normal" disabled={disabled} onClick={() => onRefill({ ...job.params })}>用同样参数重新报价</button>}
    </div>
    {uncertain && !job.task_id && <form className="min-w-0 space-y-2" onSubmit={event => { event.preventDefault(); if (taskId.trim()) void run(() => onLinkTask(job, taskId.trim())); }}><label htmlFor={taskInputId} className="block text-[14px]">控制台任务号</label><input id={taskInputId} value={taskId} maxLength={512} disabled={disabled} className={novelFieldClass} onChange={event => setTaskId(event.target.value)} /><button type="submit" disabled={disabled || !taskId.trim()} className="btn btn-quiet min-h-10">关联任务号</button></form>}
    {uncertain && <button type="button" className="btn btn-danger min-h-10 max-w-full whitespace-normal" disabled={disabled} onClick={() => setReleaseOpen(true)}>确认未扣费，释放额度</button>}
    {error && <ErrorNotice message={error} />}
    {releaseOpen && uncertain && <ReleaseDialog busy={disabled} error={error} onClose={() => setReleaseOpen(false)} onConfirm={async () => { if (await run(() => onRelease(job))) setReleaseOpen(false); }} />}
  </article>;
}

function ReleaseDialog({ busy, error, onClose, onConfirm }: { busy: boolean; error: string; onClose: () => void; onConfirm: () => Promise<void> }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => { dialog?.close(); }; }, []);
  return <dialog ref={ref} aria-labelledby={titleId} onCancel={event => { if (busy) event.preventDefault(); else onClose(); }} className="m-auto max-h-[85dvh] w-[min(520px,calc(100vw-32px))] max-w-full overflow-y-auto rounded-2xl border border-[color:var(--carve)] bg-[color:var(--paper)] p-6 text-[color:var(--ink)] backdrop:bg-[color:var(--scrim)] mobile:p-4">
    <h2 id={titleId} className="text-xl tracking-[.24em]">释放额度前再次确认</h2>
    <p className="my-5 text-[14px] leading-[1.9]">请先在供应商控制台核对，确认这次任务没有扣费。释放额度后将结束这条不确定任务。</p>
    {error && <ErrorNotice message={error} />}
    <div className="flex min-w-0 flex-wrap justify-end gap-3"><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onClose}>取消</button><button type="button" className="btn btn-danger min-h-10 max-w-full whitespace-normal" disabled={busy} onClick={() => void onConfirm()}>我已核实未扣费，释放额度</button></div>
  </dialog>;
}
