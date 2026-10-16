"use client";

import { useState } from "react";
import type { NovelChapter } from "@/lib/novels";
import { displayNovelChapterTitle, novelErrorMessage } from "@/lib/novels";
import { EmptyState, ErrorNotice, LoadingState } from "./NovelStates";
import { record, records, text } from "./NovelContent";

export function chapterReadingBody(body: string): string {
  return body.replace(/^\uFEFF?\s*#\s+第\s*[^\n]*章[^\n]*(?:\r?\n|$)/, "").replace(/^\r?\n/, "");
}

export default function ChapterReader({ chapter, loading, busy, onSave }: {
  chapter: NovelChapter | null; loading: boolean; busy: boolean; onSave: (body: string) => Promise<string | null>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  if (loading) return <LoadingState>正在加载正文…</LoadingState>;
  if (!chapter) return <EmptyState>章节正文写好后，可以在这里阅读和改稿。</EmptyState>;
  const value = record(chapter);
  const summary = record(value.review_summary);
  const issues = records(value.review).flatMap(review => records(review.issues)).filter(issue => issue.blocking === true);
  const save = async () => {
    if (busy || saving || !draft.trim() || draft.length > 30000) return;
    setSaving(true); setError(""); setMessage("");
    try { const result = await onSave(draft); if (result !== null) { setMessage(result); setEditing(false); } }
    catch (cause) { setError(novelErrorMessage(cause)); }
    finally { setSaving(false); }
  };
  return <article className="mx-auto min-w-0 max-w-[38em] space-y-6 text-[var(--ink)]">
    <header className="flex flex-wrap items-start justify-between gap-3"><h2 className="min-w-0 break-words text-xl leading-relaxed">第 <span className="readout">{chapter.chapter}</span> 章　{displayNovelChapterTitle(chapter.title)}</h2>
      {!editing && chapter.body && <button type="button" className="btn btn-quiet min-h-10" disabled={busy || saving} onClick={() => { setDraft(chapter.body ?? ""); setEditing(true); setError(""); setMessage(""); }}>改稿</button>}</header>
    {error && <ErrorNotice message={error} />}
    {message && <p role="status" className="ceramic-card p-3 text-sm leading-relaxed">{message}</p>}
    {editing ? <div className="space-y-3"><label htmlFor="novel-manuscript" className="text-sm">正文（含章节标题）</label>
      <textarea id="novel-manuscript" value={draft} maxLength={30000} onChange={event => setDraft(event.target.value)} disabled={busy || saving} className="min-h-[60dvh] w-full min-w-0 rounded-xl border border-[var(--carve)] bg-transparent p-4 text-base leading-[1.95] outline-none focus:border-[var(--ink2)]" />
      <p className="readout text-right text-xs text-[var(--ink2)]">{draft.length} / 30000</p>
      <div className="flex flex-wrap gap-2"><button type="button" className="btn btn-primary min-h-10" disabled={busy || saving || !draft.trim()} onClick={() => void save()}>{saving ? "保存中…" : "保存改稿"}</button><button type="button" className="btn min-h-10" disabled={busy || saving} onClick={() => setEditing(false)}>取消</button></div></div>
      : <div className="whitespace-pre-wrap break-words text-base leading-[1.95]">{chapterReadingBody(chapter.body ?? "") || "正文正在写作中…"}</div>}
    <footer className="border-t border-[var(--carve)] pt-4 text-sm leading-relaxed"><details><summary className="min-h-10 cursor-pointer py-2">审校摘要：保留 <span className="readout">{text(summary.retained) || "0"}</span> 条意见 · 丢弃 <span className="readout">{text(summary.discarded) || "0"}</span> 条</summary>
      <div className="mt-3 space-y-4">{issues.length ? issues.map((issue, index) => <div key={index} className="ceramic-card space-y-2 p-3"><p><span className="tag">阻断问题</span> {text(issue.problem)}</p><p className="whitespace-pre-wrap break-words text-[var(--ink2)]">证据：{text(issue.evidence)}</p></div>) : <p className="text-[var(--ink2)]">没有保留下来的阻断问题。</p>}</div></details></footer>
  </article>;
}
