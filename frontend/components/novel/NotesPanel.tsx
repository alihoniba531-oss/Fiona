"use client";

import { useState } from "react";
import type { NovelNote } from "@/lib/novels";
import { formatNovelDate, novelErrorMessage } from "@/lib/novels";
import { EmptyState, ErrorNotice, LoadingState } from "./NovelStates";

export default function NotesPanel({ notes, loading, busy, onSubmit }: {
  notes: NovelNote[]; loading: boolean; busy: boolean; onSubmit: (text: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const pending = notes.filter(note => note.status === "pending").length;
  const submit = async () => {
    if (loading || busy || sending || pending >= 5 || !draft.trim()) return;
    setSending(true); setError("");
    try { await onSubmit(draft.trim()); setDraft(""); }
    catch (cause) { setError(novelErrorMessage(cause)); }
    finally { setSending(false); }
  };
  return <div className="min-w-0 space-y-5 text-sm leading-[1.9]">
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); void submit(); }}><label htmlFor="novel-note">给主编留一句话</label>
      <textarea id="novel-note" value={draft} onChange={event => setDraft(event.target.value)} maxLength={500} rows={4} disabled={loading || busy || sending || pending >= 5} placeholder="例如：下一章让她主动说出那封信的来历。" className="w-full min-w-0 rounded-xl border border-[var(--carve)] bg-transparent p-3 text-base outline-none focus:border-[var(--ink2)]" />
      <div className="flex flex-wrap items-center justify-between gap-3"><span className="readout text-xs text-[var(--ink2)]">{draft.length} / 500</span><button type="submit" disabled={loading || busy || sending || pending >= 5 || !draft.trim()} className="btn btn-primary min-h-10">{sending ? "留言中…" : "留言"}</button></div>
      {pending >= 5 && <p role="status" className="text-[var(--ink2)]">已有 5 条待下发留言，等主编处理后再留一句。</p>}
    </form>
    {error && <ErrorNotice message={error} />}
    {loading ? <LoadingState>正在加载留言…</LoadingState> : !notes.length ? <EmptyState>你留的话，会在下一次推演时交给主编。</EmptyState> : <ol className="space-y-5">{notes.map(note => <li key={note.id} className="ceramic-card space-y-3 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="tag">{note.status === "pending" ? "待下发" : <>已下发到第 <span className="readout">{note.delivered_chapter ?? "—"}</span> 章</>}</span><time dateTime={/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(note.created_at) ? `${note.created_at.replace(" ", "T")}Z` : note.created_at} className="readout break-words text-xs text-[var(--ink2)]">{formatNovelDate(note.created_at)}</time></div>
      <p className="whitespace-pre-wrap break-words">{note.text}</p>
      {note.status === "delivered" && <div className="space-y-2 border-t border-[var(--carve)] pt-3"><span className="tag">{note.adopted === null ? "待主编回应" : note.adopted ? "采纳" : "不采纳"}</span><p className="whitespace-pre-wrap break-words">{note.response ?? "主编回应尚未生成。"}</p></div>}
    </li>)}</ol>}
  </div>;
}
