"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import GateBanner from "@/components/novel/GateBanner";
import { EmptyState, ErrorNotice } from "@/components/novel/NovelStates";
import { chapterTag, currentChapterNumber, deskAskPrefix } from "@/lib/desk";
import { displayNovelChapterTitle, novelErrorMessage, type NovelAction, type NovelDetail } from "@/lib/novels";

type DeskChaptersViewProps = {
  book: NovelDetail;
  busy: boolean;
  gateError: string | null;
  onAction: (action: NovelAction, body?: unknown) => Promise<void>;
  onAddNote: (text: string) => Promise<void>;
  onAsk: (prefix: string) => void;
  onExport: () => void | Promise<void>;
  onOpenNovel: (path: string) => void;
  onOpenPlan: () => void;
  onOpenBody: (chapter: number) => void;
  onOpenSettings: () => void;
  initialExpanded?: number | null;
};

type NoteFeedback = { ok: boolean; message: string } | null;

export default function DeskChaptersView({ book, busy, gateError, onAction, onAddNote, onAsk, onExport, onOpenNovel, onOpenPlan, onOpenBody, onOpenSettings, initialExpanded = null }: DeskChaptersViewProps) {
  const noteId = useId();
  const notesInputRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef(new Map<number, HTMLDivElement>());
  const scrolledBookRef = useRef<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(initialExpanded);
  const [note, setNote] = useState("");
  const [noteBusy, setNoteBusy] = useState(false);
  const [feedback, setFeedback] = useState<NoteFeedback>(null);

  const chapters = useMemo(() => [...book.chapters].sort((left, right) => left.chapter - right.chapter), [book.chapters]);
  const summaries = useMemo(() => {
    const map = new Map<number, string>();
    for (const item of book.bible?.dynamic.chapter_summaries ?? []) {
      if (item.summary) map.set(item.chapter, item.summary);
    }
    return map;
  }, [book.bible]);
  const notesFull = book.pending_notes >= 5;

  useEffect(() => {
    if (scrolledBookRef.current === book.id) return;
    const target = currentChapterNumber(book);
    if (target === null) return;
    scrolledBookRef.current = book.id;
    rowRefs.current.get(target)?.scrollIntoView({ block: "nearest" });
  }, [book]);

  const focusNotes = () => {
    notesInputRef.current?.focus();
  };

  const submitNote = async () => {
    const text = note.trim();
    if (!text || noteBusy || notesFull) return;
    setNoteBusy(true);
    setFeedback(null);
    try {
      await onAddNote(text);
      setNote("");
      setFeedback({ ok: true, message: "已留言。" });
    } catch (error) {
      setFeedback({ ok: false, message: novelErrorMessage(error) });
    } finally {
      setNoteBusy(false);
    }
  };

  return <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
    <div className="shrink-0 space-y-3">
      <GateBanner
        book={book}
        busy={busy}
        onAction={onAction}
        onNotes={focusNotes}
        onSettings={() => onOpenNovel(`/novels/${book.id}?embed=1`)}
        onView={book.status === "awaiting_plan" ? onOpenPlan : () => onOpenNovel(`/novels/${book.id}?embed=1`)}
        onExport={onExport}
        onOpenSettings={onOpenSettings}
      />
      {gateError && <ErrorNotice message={gateError} />}
    </div>

    {chapters.length === 0 ? (
      <div className="min-h-0 flex-1 overflow-y-auto">
        <EmptyState>第一章写好后会出现在这里。</EmptyState>
      </div>
    ) : (
    <div className="min-h-0 flex-1 overflow-y-auto" role="list" aria-label="章回">
      {chapters.map(chapter => {
        const title = displayNovelChapterTitle(chapter.title) || "待定章名";
        const summary = summaries.get(chapter.chapter);
        const tag = chapterTag(chapter, book.chapters_done);
        const isExpanded = expanded === chapter.chapter;
        return <div
          key={chapter.chapter}
          role="listitem"
          ref={node => {
            if (node) rowRefs.current.set(chapter.chapter, node);
            else rowRefs.current.delete(chapter.chapter);
          }}
          className="grid grid-cols-[36px_minmax(0,1fr)_auto] items-start gap-3 border-b border-[color:var(--rule)] py-3 last:border-b-0"
        >
          <span aria-hidden="true" className="readout text-fs-18 text-[color:var(--ink2)]">{chapter.chapter}</span>
          <div className="min-w-0">
            <button type="button" className="flex min-h-10 w-full min-w-0 items-center text-left text-fs-15" aria-label={`第 ${chapter.chapter} 章　${title}`} aria-expanded={isExpanded} onClick={() => setExpanded(current => current === chapter.chapter ? null : chapter.chapter)}>{title}</button>
            {summary && <p className={`break-words text-fs-13 text-[color:var(--ink2)] ${isExpanded ? "" : "line-clamp-2"}`}>{summary}</p>}
            {isExpanded && <div className="mt-2 flex flex-wrap items-center gap-2">
              {chapter.chapter <= book.chapters_done && <button type="button" className="btn btn-quiet min-h-10" onClick={() => onOpenBody(chapter.chapter)}>读正文</button>}
              <button type="button" className="btn btn-quiet min-h-10" onClick={() => onAsk(deskAskPrefix({ title: book.title, chapter: chapter.chapter }))}>问分身</button>
            </div>}
          </div>
          <div className="flex flex-col items-end gap-1.5">
            {chapter.words > 0 && <span className="readout">{`${chapter.words} 字`}</span>}
            <span className={tag.settled ? "tag text-[color:var(--seal)] border-[color:var(--seal)]" : "tag"}>{tag.label}</span>
          </div>
        </div>;
      })}
    </div>
    )}

    {book.status !== "completed" && <div className="shrink-0 border-t border-[color:var(--rule)] pt-3">
      <label htmlFor={noteId} className="block text-fs-13">给编辑部留一句话</label>
      <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2">
        <input ref={notesInputRef} id={noteId} type="text" maxLength={500} value={note} disabled={noteBusy || notesFull} placeholder="下一章定稿时会看到" onChange={event => { setNote(event.target.value); if (feedback) setFeedback(null); }} className="min-h-10 min-w-0 flex-1 basis-48 rounded-lg border border-[color:var(--rule2)] bg-transparent px-3 text-fs-13 text-[color:var(--ink)] outline-none focus-visible:border-[color:var(--ink)] disabled:opacity-50" />
        <button type="button" className="btn min-h-10" disabled={noteBusy || notesFull || !note.trim()} onClick={() => void submitNote()}>留言</button>
      </div>
      <p className="mt-2 text-fs-12 text-[color:var(--ink2)]">{`待处理留言 ${book.pending_notes} / 5`}</p>
      {notesFull && <p className="mt-1 text-fs-13 text-[color:var(--ink2)]">待处理留言已满 5 条，等编辑部处理后再留。</p>}
      {feedback && (feedback.ok
        ? <p role="status" className="mt-1 text-fs-13 text-[color:var(--ink2)]">{feedback.message}</p>
        : <p role="alert" className="mt-1 break-words text-fs-13 text-[color:var(--ink)]">{feedback.message}</p>)}
    </div>}
  </div>;
}
