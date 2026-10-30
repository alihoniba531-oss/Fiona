"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { ErrorNotice } from "@/components/novel/NovelStates";
import { studioErrorMessage } from "@/lib/studio";
import { sourceDialogClass } from "./SourceChoices";

export const breakdownFieldClass = "w-full min-w-0 rounded-lg border border-[color:var(--carve)] bg-[color:var(--paper)] p-2 text-fs-16.5 text-[color:var(--ink)]";
export default function BreakdownDialog({ title, children, confirmLabel = "确认", busy = false, disabled = false, onConfirm, onClose }: { title: string; children: ReactNode; confirmLabel?: string; busy?: boolean; disabled?: boolean; onConfirm: () => Promise<void>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const locked = useRef(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  const blocked = busy || saving;
  const confirm = async () => {
    if (blocked || disabled || locked.current) return;
    locked.current = true; setSaving(true); setError("");
    try { await onConfirm(); }
    catch (cause) { setError(studioErrorMessage(cause)); }
    finally { locked.current = false; setSaving(false); }
  };
  return <dialog ref={ref} aria-labelledby={titleId} className={sourceDialogClass} onCancel={event => { if (blocked) event.preventDefault(); else onClose(); }}>
    <h3 id={titleId} className="mb-4 text-fs-22 tracking-[.16em]">{title}</h3>
    <form className="min-w-0 space-y-4" onSubmit={event => { event.preventDefault(); void confirm(); }}>
      <fieldset disabled={blocked} className="min-w-0 space-y-3">{children}</fieldset>
      {error && <ErrorNotice message={error} />}
      <div className="flex min-w-0 flex-wrap justify-end gap-2"><button type="button" className="btn btn-quiet min-h-10" disabled={blocked} onClick={onClose}>取消</button><button type="submit" className="btn btn-primary min-h-10" disabled={blocked || disabled}>{saving ? "处理中…" : confirmLabel}</button></div>
    </form>
  </dialog>;
}
