"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { novelFieldClass } from "./NovelModelFields";
import { EmptyState, ErrorNotice, LoadingState } from "./NovelStates";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { createStudioFromNovel, listStudioNovelSources, studioErrorMessage, studioHref, type StudioNovelCandidate, type StudioProject } from "@/lib/studio";
import { ExistingSourceProjects, SourceAspectPicker, SourceFlags, sourceDialogClass } from "@/components/studio/SourceChoices";

export default function NovelFilmDialog({ owner, bookId, bookTitle, embedded, onClose }: { owner: string; bookId: string; bookTitle: string; embedded: boolean; onClose: () => void }) {
  const router = useRouter();
  const ref = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState(bookTitle.slice(0, 200));
  const [aspect, setAspect] = useState<StudioProject["aspect"]>("16:9");
  const [book, setBook] = useState<StudioNovelCandidate | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);
  const load = useCallback(async () => {
    const request = beginRead(); if (!request) return;
    setLoading(true); setError("");
    try {
      const result = await listStudioNovelSources(request.signal);
      if (request.isCurrent()) setBook(result.enabled ? result.books.find(candidate => candidate.id === bookId) ?? null : null);
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead, bookId]);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  const create = async () => {
    if (lock.current || busy || !title.trim() || !book?.eligible) return;
    const request = beginMutation(); if (!request) return;
    lock.current = true; setBusy(true); setError("");
    try {
      const project = await createStudioFromNovel({ book_id: bookId, title: title.trim(), aspect }, request.signal);
      if (request.isCurrent()) router.push(studioHref(`/studio/${encodeURIComponent(project.id)}`, embedded));
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { lock.current = false; if (request.isCurrent()) setBusy(false); }
  };
  return <dialog ref={ref} aria-labelledby="novel-film-title" onCancel={event => { if (busy || lock.current) event.preventDefault(); else onClose(); }} className={sourceDialogClass}>
    <h2 id="novel-film-title" className="mb-4 text-xl tracking-[.24em]">做成片</h2><p className="mb-4 break-words">为《{bookTitle}》建立工作室项目，并保存原文快照。</p>
    {loading && <LoadingState>正在检查作品…</LoadingState>}{error && <ErrorNotice message={error} retry={() => void load()} />}
    {!loading && !error && !book && <EmptyState>作品不存在或无权访问。</EmptyState>}
    {book && <><ExistingSourceProjects projects={book.projects} embedded={embedded} primary /><SourceFlags chapters={book.flagged} />{!book.eligible && <p role="status" className="mt-3 text-sm text-[color:var(--seal)]">{book.reason || "作品暂不满足导入条件"}</p>}</>}
    <label className="mt-4 block space-y-2"><span>项目标题</span><input id="novel-film-project-title" maxLength={200} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} className={novelFieldClass} /></label>
    <SourceAspectPicker aspect={aspect} disabled={busy} onChange={setAspect} />
    <p className="mb-4 text-sm text-[color:var(--ink2)]">建立项目和快照不花费草莓。</p>
    <div className="flex flex-wrap gap-3"><button type="button" className={book?.projects.length ? "btn min-h-10" : "btn btn-primary min-h-10"} disabled={busy || loading || !book?.eligible || !title.trim()} onClick={() => void create()}>{busy ? "正在建立快照…" : book?.projects.length ? "再建一个" : "创建项目"}</button><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onClose}>取消</button></div>
  </dialog>;
}
