"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { chapterReadingBody } from "@/components/novel/ChapterReader";
import PlanEditor from "@/components/novel/PlanEditor";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { sourceDialogClass } from "@/components/studio/SourceChoices";
import { displayNovelChapterTitle, type NovelBeatSheet, type NovelChapter, type NovelDetail } from "@/lib/novels";

type DeskPlanDialogProps = {
  book: NovelDetail;
  chapter: number;
  data: NovelChapter | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  onApprove: (beat?: NovelBeatSheet) => Promise<void>;
  onRedo: (text: string) => Promise<void>;
  onClose: () => void;
  onOpenNovel: (path: string) => void;
};

type DeskReaderDialogProps = {
  book: NovelDetail;
  chapter: number;
  data: NovelChapter | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onOpenNovel: (path: string) => void;
};

function DeskDialog({ labelledBy, onClose, busy = false, children }: { labelledBy: string; onClose: () => void; busy?: boolean; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    return () => { dialog.close(); };
  }, []);
  return <dialog
    ref={ref}
    aria-labelledby={labelledBy}
    className={sourceDialogClass}
    onCancel={event => {
      event.preventDefault();
      if (!busy) onClose();
    }}
  >
    {children}
  </dialog>;
}

export function DeskPlanDialog({ book, chapter, data, loading, error, busy, onApprove, onRedo, onClose }: DeskPlanDialogProps) {
  const beatSheet = data?.meeting?.decision?.beat_sheet ?? null;
  let content: ReactNode;
  if (loading) content = <LoadingState>正在取回细纲…</LoadingState>;
  else if (error) content = <ErrorNotice message={error} />;
  else if (!data || !beatSheet) content = <EmptyState>细纲还没准备好，请稍后刷新。</EmptyState>;
  else content = <PlanEditor
    key={`${chapter}:${data.updated_at}`}
    chapter={chapter}
    beatSheet={beatSheet}
    maxScenes={book.config.adaptation.max_scenes_per_chapter}
    busy={busy}
    onApprove={beat => onApprove(beat)}
    onRedo={text => onRedo(text)}
  />;
  return <DeskDialog labelledBy="desk-plan-dialog-title" onClose={onClose} busy={busy}>
    <div className="min-w-0">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 id="desk-plan-dialog-title" className="text-fs-22 tracking-[.24em]">细纲</h2>
        <button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onClose}>关闭</button>
      </div>
      {content}
    </div>
  </DeskDialog>;
}

export function DeskReaderDialog({ book, chapter, data, loading, error, onClose, onOpenNovel }: DeskReaderDialogProps) {
  const summaryTitle = book.bible?.dynamic.chapter_summaries.find(item => item.chapter === chapter)?.title;
  const chapterTitle = displayNovelChapterTitle(data?.title ?? summaryTitle) || "待定章名";
  const body = data?.body ? chapterReadingBody(data.body) : "";
  let content: ReactNode;
  if (loading) content = <LoadingState>正在取回正文…</LoadingState>;
  else if (error) content = <ErrorNotice message={error} />;
  else if (body) content = <div className="whitespace-pre-wrap break-words text-fs-16.5 leading-[1.9]">{body}</div>;
  else content = <EmptyState>这一章还没有正文。</EmptyState>;
  return <DeskDialog labelledBy="desk-reader-dialog-title" onClose={onClose}>
    <div className="min-w-0">
      <h2 id="desk-reader-dialog-title" className="mb-4 break-words text-fs-22 tracking-[.24em]">{`第 ${chapter} 章　${chapterTitle}`}</h2>
      {content}
      <div className="mt-5 flex flex-wrap gap-3">
        <button type="button" className="btn btn-quiet min-h-10" onClick={() => { onClose(); onOpenNovel(`/novels/${book.id}?embed=1`); }}>在书斋打开</button>
        <button type="button" className="btn min-h-10" onClick={onClose}>关闭</button>
      </div>
    </div>
  </DeskDialog>;
}
