"use client";

import { useCallback, useEffect, useState, type CSSProperties, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { X } from "lucide-react";
import Glaze from "@/components/Glaze";
import { ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { DESK_STAGES, deskStageByKey, type DeskMode, type DeskStage } from "@/lib/desk";
import { novelStatusLabel, type NovelDetail, type NovelSummary } from "@/lib/novels";

export type DeskFrameProps = {
  mode: DeskMode;
  stage: DeskStage;
  onStageChange: (stage: DeskStage) => void;
  books: NovelSummary[] | null;
  book: NovelDetail | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onSelectBook: (id: string) => void;
  onRefresh: () => void;
  onClose: () => void;
  onOpenNovel: (path: string) => void;
  onOpenStudio: (projectId: string | null) => void;
  studioProjectId: string | null;
  composerHeight: number;
  sheetExpanded: boolean;
  onToggleSheet: () => void;
  panelRef: Ref<HTMLElement>;
  children: ReactNode;
};

const HEADER_BUTTON = "btn btn-quiet px-2 text-fs-12 max-md:min-h-10";

export default function DeskFrame({
  mode,
  stage,
  onStageChange,
  books,
  book,
  loading,
  error,
  onRetry,
  onSelectBook,
  onRefresh,
  onClose,
  onOpenNovel,
  onOpenStudio,
  studioProjectId,
  composerHeight,
  sheetExpanded,
  onToggleSheet,
  panelRef,
  children,
}: DeskFrameProps) {
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setEntered(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const stageIndex = DESK_STAGES.findIndex(item => item.id === stage);
  const handleStageKey = useCallback((event: KeyboardEvent<HTMLButtonElement>, orientation: "vertical" | "horizontal") => {
    const next = deskStageByKey(stage, event.key, orientation);
    if (!next) return;
    event.preventDefault();
    onStageChange(next);
    event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-stage="${next}"]`)?.focus();
  }, [onStageChange, stage]);

  const bookTitle = book?.title?.trim() || null;
  const bookLabel = book ? (bookTitle ? `《${bookTitle}》` : "未命名") : "";
  const currentBookId = book?.id ?? "";
  const meta = book ? [novelStatusLabel(book), `已写 ${book.chapters_done} 章`, `${book.words_done} 字`].join("　") : null;
  const novelPath = book ? `/novels/${book.id}?embed=1` : null;

  const motionStyle: CSSProperties | undefined = mode === "dock" ? undefined : {
    transform: entered ? "translateX(0)" : "translateX(105%)",
    transition: "transform 360ms cubic-bezier(.22,.61,.36,1)",
    willChange: "transform",
  };

  const panelStyle: CSSProperties | undefined = mode === "drawer"
    ? { boxShadow: "-12px 0 32px var(--drop)" }
    : mode === "sheet"
      ? { boxShadow: "0 -8px 24px var(--drop)" }
      : { boxShadow: "none" };

  const sheetStyle: CSSProperties | undefined = mode === "sheet" ? {
    ...(motionStyle ?? {}),
    bottom: `calc(var(--tabbar-h) + env(safe-area-inset-bottom) + ${composerHeight}px)`,
    ...(sheetExpanded
      ? { top: "calc(94px + env(safe-area-inset-top))" }
      : { height: `min(45dvh, calc(100dvh - 94px - env(safe-area-inset-top) - var(--tabbar-h) - env(safe-area-inset-bottom) - ${composerHeight}px))` }),
  } : undefined;

  const panelClass = mode === "sheet"
    ? "flex h-full min-h-0 w-full flex-col overflow-hidden rounded-t-[14px] rounded-b-none border-t border-[color:var(--rule)] bg-[color:var(--paper)] outline-none"
    : `flex h-full min-h-0 w-[448px] shrink-0 flex-col overflow-hidden border-l border-[color:var(--rule)] outline-none${mode === "drawer" ? " bg-[color:var(--paper)]" : ""}`;

  const headerClass = mode === "sheet"
    ? "shrink-0 px-4 pb-2.5 pt-4"
    : "shrink-0 border-b border-[color:var(--rule)] px-5 pb-2.5 pt-4";
  const contentClass = mode === "sheet"
    ? "flex min-h-0 flex-1 flex-col overflow-y-auto px-4 pb-5"
    : "flex min-h-0 flex-1 flex-col overflow-y-auto px-5 pb-5";

  const verticalTabs = (
    <nav role="tablist" aria-label="创作阶段" aria-orientation="vertical" className="flex shrink-0 flex-col gap-2 pt-[72px]">
      {DESK_STAGES.map((item, index) => {
        const selected = index === stageIndex;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={selected}
            disabled={!item.enabled}
            title={item.enabled ? undefined : "后续开放"}
            data-stage={item.id}
            tabIndex={item.enabled && selected ? 0 : -1}
            onKeyDown={item.enabled ? event => handleStageKey(event, "vertical") : undefined}
            onClick={() => { if (item.enabled) onStageChange(item.id); }}
            className={`flex h-[92px] w-7 shrink-0 items-center justify-center rounded-r-[6px] border border-[color:var(--rule)] text-fs-12 tracking-[.28em] [writing-mode:vertical-rl] disabled:cursor-not-allowed disabled:opacity-50 enabled:hover:text-[color:var(--ink)] ${
              selected
                ? "border-l-2 border-l-[color:var(--seal)] bg-[color:var(--hi)] text-[color:var(--ink)]"
                : "border-l-0 text-[color:var(--ink2)]"
            }`}
          >
            {item.label}
          </button>
        );
      })}
    </nav>
  );

  const horizontalTabs = (
    <nav role="tablist" aria-label="创作阶段" className="flex shrink-0 border-b border-[color:var(--rule)] px-4">
      {DESK_STAGES.map((item, index) => {
        const selected = index === stageIndex;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={selected}
            disabled={!item.enabled}
            title={item.enabled ? undefined : "后续开放"}
            data-stage={item.id}
            tabIndex={item.enabled && selected ? 0 : -1}
            onKeyDown={item.enabled ? event => handleStageKey(event, "horizontal") : undefined}
            onClick={() => { if (item.enabled) onStageChange(item.id); }}
            className={`min-h-10 min-w-0 flex-1 px-1 py-2 text-fs-13 disabled:cursor-not-allowed disabled:opacity-50 ${
              selected
                ? "border-b border-[color:var(--seal)] bg-[color:var(--hi)] text-[color:var(--ink)]"
                : "border-b-0 text-[color:var(--ink2)]"
            }`}
          >
            {item.label}
          </button>
        );
      })}
    </nav>
  );

  const panel = (
    <Glaze
      as="aside"
      variant="panel"
      lens={false}
      backdrop={false}
      id="desk-panel"
      aria-label="案头"
      tabIndex={-1}
      ref={panelRef}
      className={`drawer-panel ${panelClass}`}
      style={panelStyle}
    >
      <div className={headerClass}>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-fs-12 text-[color:var(--ink2)]">案头</span>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-1">
            {mode === "sheet" && (
              <button
                type="button"
                aria-expanded={sheetExpanded}
                className={HEADER_BUTTON}
                onClick={onToggleSheet}
              >
                {sheetExpanded ? "收起一半" : "展开"}
              </button>
            )}
            <button type="button" className={HEADER_BUTTON} onClick={onRefresh}>刷新</button>
            {(stage === "idea" || stage === "chapters") && novelPath && (
              <button type="button" className={HEADER_BUTTON} onClick={() => onOpenNovel(novelPath)}>在书斋打开</button>
            )}
            {stage === "episodes" && studioProjectId && (
              <button type="button" className={HEADER_BUTTON} onClick={() => onOpenStudio(studioProjectId)}>在工作室打开</button>
            )}
            <button
              type="button"
              aria-label="收起案头"
              title="收起案头"
              onClick={onClose}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded text-[color:var(--ink2)] hover:text-[color:var(--ink)] max-md:h-10 max-md:w-10"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className="min-w-0 break-words text-fs-22 leading-[1.3]">{bookLabel}</h2>
          {books && books.length > 1 && (
            <select
              aria-label="作品"
              value={currentBookId}
              onChange={event => onSelectBook(event.target.value)}
              className="h-8 max-w-full shrink-0 rounded border border-[color:var(--rule)] bg-transparent px-1 text-fs-12 text-[color:var(--ink2)] max-md:min-h-10"
            >
              {books.map(item => (
                <option key={item.id} value={item.id}>{item.title?.trim() || "未命名"}</option>
              ))}
            </select>
          )}
        </div>
        {meta && <p className="mt-0.5 text-fs-13 text-[color:var(--ink2)]">{meta}</p>}
      </div>
      {mode === "sheet" && horizontalTabs}
      <div className={contentClass}>
        {loading ? <LoadingState>正在取回作品…</LoadingState>
          : error ? <ErrorNotice message={error} retry={onRetry} />
          : children}
      </div>
    </Glaze>
  );

  if (mode === "sheet") {
    return <div className="fixed left-0 right-0 z-[50]" style={sheetStyle}>{panel}</div>;
  }

  return (
    <div
      className={mode === "dock"
        ? "flex flex-none w-[488px] py-3 pr-3"
        : "fixed top-3 bottom-3 right-3 z-[50] w-[476px] flex"}
      style={mode === "drawer" ? motionStyle : undefined}
    >
      {panel}
      {verticalTabs}
    </div>
  );
}
