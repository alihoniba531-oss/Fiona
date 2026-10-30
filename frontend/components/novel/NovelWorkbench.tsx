"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import InkLandscape from "@/components/InkLandscape";
import Glaze from "@/components/Glaze";
import ChapterList from "./ChapterList";
import ChapterReader from "./ChapterReader";
import DeliberationTimeline from "./DeliberationTimeline";
import BiblePanel from "./BiblePanel";
import NotesPanel from "./NotesPanel";
import GateBanner from "./GateBanner";
import NovelFilmDialog from "./NovelFilmDialog";
import { checkStudioAccess } from "@/lib/studio";
import SetupEditor from "./SetupEditor";
import PlanEditor from "./PlanEditor";
import NovelSettingsDialog from "./NovelSettingsDialog";
import { useNovelEmbedClose } from "./NovelShell";
import { EmptyState, ErrorNotice, LoadingState } from "./NovelStates";
import { ApiError } from "@/lib/agents";
import { useAccountIdentity, useAccountIdentityPending, useAccountRequest } from "@/lib/useAccountIdentity";
import { useConfirm } from "@/components/ConfirmDialog";
import { addNovelNote, novelApi, novelErrorMessage, novelHref, novelStatusLabel, updateNovelCharacter, updateNovelChapter, type NovelAction, type NovelBible, type NovelCatalog, type NovelChapter, type NovelCharacterEdit, type NovelDetail, type NovelNote, type NovelPatchInput } from "@/lib/novels";

const active = (status?: string) => status === "setup_running" || status === "running";
const signature = (chapter: NovelDetail["chapters"][number]) => JSON.stringify([chapter.status, chapter.words, chapter.flags, chapter.edited_by_user]);
type RefreshOptions = { chapter?: number; notes?: boolean };
type MutationOptions = RefreshOptions & { refresh?: boolean; errorTarget?: "page" | "local" };

export default function NovelWorkbench({ id, embedded = false }: { id: string; embedded?: boolean }) {
  const owner = useAccountIdentity();
  const identityPending = useAccountIdentityPending();
  return <AccountWorkbench key={`${owner}:${id}`} owner={owner} identityPending={identityPending} id={id} embedded={embedded} />;
}

function AccountWorkbench({ owner, id, embedded, identityPending = false }: { owner: string; id: string; embedded: boolean; identityPending?: boolean }) {
  useNovelEmbedClose(embedded);
  const router = useRouter();
  const [{ book, chapterRefreshes, notesRefresh }, setBookState] = useState<{ book: NovelDetail | null; chapterRefreshes: Record<number, number>; notesRefresh: number }>({ book: null, chapterRefreshes: {}, notesRefresh: 0 });
  const [bible, setBible] = useState<NovelBible | null>(null);
  const [notes, setNotes] = useState<NovelNote[]>([]);
  const [catalog, setCatalog] = useState<NovelCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [selectedChapter, setSelectedChapter] = useState<number | null>(null);
  const [chapter, setChapter] = useState<NovelChapter | null>(null);
  const [loading, setLoading] = useState(true);
  const [chapterLoading, setChapterLoading] = useState(false);
  const [bibleLoading, setBibleLoading] = useState(false);
  const [notesLoading, setNotesLoading] = useState(false);
  const [readError, setReadError] = useState("");
  const [chapterError, setChapterError] = useState("");
  const [bibleError, setBibleError] = useState("");
  const [notesError, setNotesError] = useState("");
  const [operationError, setOperationError] = useState("");
  const [busy, setBusy] = useState("");
  const [mobileTab, setMobileTab] = useState<"directory" | "reader" | "details">("reader");
  const [wideLayout, setWideLayout] = useState(false);
  const [rightTab, setRightTab] = useState<"meeting" | "bible" | "notes">("meeting");
  const [settings, setSettings] = useState<{ resumeAfter: boolean } | null>(null);
  const [studioAllowed, setStudioAllowed] = useState(false);
  const [filmDialog, setFilmDialog] = useState(false);
  const studioChecked = useRef(false);
  const status = useRef<string>("");
  const mutating = useRef(false);
  const chapterValue = useRef<NovelChapter | null>(null);
  const bibleVersion = useRef<number | null>(null);
  const bibleOpened = useRef(false);
  const notesTrigger = useRef<{ status?: string; chapters?: number; refresh: number }>({ refresh: -1 });
  const columnsRef = useRef<HTMLDivElement>(null);
  const readerRef = useRef<HTMLElement>(null);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginChapter } = useAccountRequest(owner);
  const { beginRequest: beginBible } = useAccountRequest(owner);
  const { beginRequest: beginNotes } = useAccountRequest(owner);
  const { beginRequest: beginMutation, isCurrentOwner } = useAccountRequest(owner);
  const { beginRequest: beginCatalog } = useAccountRequest(owner);
  const { beginRequest: beginStudio } = useAccountRequest(owner);
  const confirm = useConfirm();
  const completed = book?.status === "completed";
  useEffect(() => {
    if (!completed) return;
    void Promise.resolve().then(async () => {
      if (studioChecked.current) return;
      const request = beginStudio(); if (!request) return;
      studioChecked.current = true;
      try { const allowed = await checkStudioAccess(request.signal); if (request.isCurrent()) setStudioAllowed(allowed); }
      catch { if (request.isCurrent()) setStudioAllowed(false); }
    });
  }, [beginStudio, completed]);

  const load = useCallback(async (force = false, refresh: RefreshOptions = {}) => {
    if (mutating.current && !force) return;
    const request = beginRead();
    if (!request) return;
    try {
      const nextBook = await novelApi.detail(id, { signal: request.signal });
      if (!request.isCurrent()) return;
      if (nextBook.id !== id) throw new Error("书籍信息不匹配，请重新打开这本书。");
      const enteringPlan = nextBook.status === "awaiting_plan" && status.current !== "awaiting_plan";
      status.current = nextBook.status;
      // A save publishes its summary and explicit refresh token together, so
      // changes to both never produce two requests for the same manuscript.
      setBookState(current => ({
        book: nextBook,
        chapterRefreshes: refresh.chapter == null ? current.chapterRefreshes : { ...current.chapterRefreshes, [refresh.chapter]: (current.chapterRefreshes[refresh.chapter] ?? 0) + 1 },
        notesRefresh: current.notesRefresh + (refresh.notes ? 1 : 0),
      }));
      setSelectedChapter(current => enteringPlan ? nextBook.chapters.find(item => item.status === "awaiting_plan_approval")?.chapter ?? nextBook.chapters.at(-1)?.chapter ?? null : current != null && nextBook.chapters.some(item => item.chapter === current) ? current : nextBook.chapters.at(-1)?.chapter ?? null);
      setReadError("");
    } catch (cause) { if (request.isCurrent()) setReadError(novelErrorMessage(cause)); }
    finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead, id]);

  useEffect(() => { void Promise.resolve().then(() => load()); }, [load]);
  useEffect(() => {
    if (!active(book?.status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      if (!cancelled && !document.hidden && active(status.current)) timer = setTimeout(poll, 3000);
    };
    const poll = async () => {
      if (cancelled || document.hidden || !active(status.current)) return;
      await load(); schedule();
    };
    const onVisibility = () => {
      clearTimeout(timer);
      if (!document.hidden) void poll();
    };
    schedule(); document.addEventListener("visibilitychange", onVisibility);
    return () => { cancelled = true; clearTimeout(timer); document.removeEventListener("visibilitychange", onVisibility); };
  }, [book?.status, load]);

  const selectedSummary = book?.chapters.find(item => item.chapter === selectedChapter);
  const selectedSignature = selectedSummary ? signature(selectedSummary) : null;
  const selectedRefresh = selectedChapter == null ? 0 : chapterRefreshes[selectedChapter] ?? 0;
  const loadChapter = useCallback(async () => {
    if (selectedChapter == null) return;
    const request = beginChapter();
    if (!request) return;
    setChapterLoading(chapterValue.current?.chapter !== selectedChapter);
    try {
      const result = await novelApi.chapter(id, selectedChapter, { signal: request.signal });
      if (request.isCurrent()) { chapterValue.current = result; setChapter(result); setChapterError(""); }
    } catch (cause) { if (request.isCurrent()) setChapterError(novelErrorMessage(cause)); }
    finally { if (request.isCurrent()) setChapterLoading(false); }
  }, [beginChapter, id, selectedChapter]);
  useEffect(() => { if (selectedSignature != null) void Promise.resolve().then(loadChapter); }, [loadChapter, selectedSignature, selectedRefresh]);

  const loadBible = useCallback(async (version: number) => {
    if (version < 1) return;
    const request = beginBible();
    if (!request) return;
    setBibleLoading(true);
    try {
      const result = await novelApi.bible(id, { signal: request.signal });
      if (request.isCurrent()) { bibleVersion.current = version; setBible(result); setBibleError(""); }
    } catch (cause) { if (request.isCurrent()) setBibleError(novelErrorMessage(cause)); }
    finally { if (request.isCurrent()) setBibleLoading(false); }
  }, [beginBible, id]);
  useEffect(() => {
    const version = book?.bible_version;
    if (version == null || version < 1) return;
    const firstOpen = rightTab === "bible" && !bibleOpened.current;
    if (rightTab === "bible") bibleOpened.current = true;
    if (bibleVersion.current !== version || firstOpen) void Promise.resolve().then(() => loadBible(version));
  }, [book?.bible_version, loadBible, rightTab]);

  const bookPresent = book !== null;
  useEffect(() => {
    const container = columnsRef.current;
    if (!container) return;
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) setWideLayout(entry.contentRect.width >= 1040);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [bookPresent]);
  const notesVisible = rightTab === "notes" && (wideLayout || mobileTab === "details");
  const loadNotes = useCallback(async () => {
    const request = beginNotes();
    if (!request) return;
    setNotesLoading(true);
    try {
      const result = await novelApi.notes(id, { signal: request.signal });
      if (request.isCurrent()) { setNotes(result); setNotesError(""); }
    } catch (cause) { if (request.isCurrent()) setNotesError(novelErrorMessage(cause)); }
    finally { if (request.isCurrent()) setNotesLoading(false); }
  }, [beginNotes, id]);
  useEffect(() => {
    if (!bookPresent) return;
    const previous = notesTrigger.current;
    const changed = previous.status !== book?.status || previous.chapters !== book?.chapters_done || previous.refresh !== notesRefresh;
    notesTrigger.current = { status: book?.status, chapters: book?.chapters_done, refresh: notesRefresh };
    if (notesVisible || changed) void Promise.resolve().then(loadNotes);
  }, [book, bookPresent, loadNotes, notesVisible, notesRefresh]);

  useEffect(() => {
    if (!settings || catalog) return;
    const request = beginCatalog();
    if (!request) return;
    novelApi.catalog({ signal: request.signal }).then(result => { if (request.isCurrent()) { setCatalog(result); setCatalogError(""); } }).catch(cause => { if (request.isCurrent()) setCatalogError(novelErrorMessage(cause)); });
  }, [beginCatalog, catalog, settings]);

  const mutate = async <T,>(label: string, operation: (signal: AbortSignal) => Promise<T>, options: MutationOptions = {}): Promise<T | null> => {
    const refresh = options.refresh !== false;
    if (mutating.current || !isCurrentOwner()) return null;
    const request = beginMutation();
    if (!request) return null;
    if (refresh) beginRead();
    mutating.current = true; setBusy(label); setOperationError("");
    try {
      const result = await operation(request.signal);
      if (!request.isCurrent()) return null;
      if (refresh) await load(true, options);
      return request.isCurrent() ? result : null;
    } catch (cause) {
      if (!request.isCurrent()) return null;
      const message = novelErrorMessage(cause);
      if (refresh) await load(true);
      if (options.errorTarget !== "local") setOperationError(message);
      throw cause instanceof ApiError ? new ApiError(message, cause.status) : new Error(message);
    } finally { mutating.current = false; if (request.isCurrent()) setBusy(""); }
  };
  const act = async (action: NovelAction, body?: unknown, errorTarget: "page" | "local" = "page") => { await mutate(action, signal => novelApi.action(id, action, body, { signal }), { errorTarget }); };
  const showReader = () => {
    if (book?.status === "awaiting_plan") setSelectedChapter(book.chapters.find(item => item.status === "awaiting_plan_approval")?.chapter ?? book.chapters.at(-1)?.chapter ?? null);
    else if (book?.pause_reason === "locked_conflict") setSelectedChapter(book.chapters.findLast(item => item.flags.includes("locked_conflict"))?.chapter ?? book.chapters_done);
    setMobileTab("reader"); readerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const download = async () => {
    try {
      const blob = await mutate("export", signal => novelApi.export(id, { signal }), { refresh: false });
      if (!blob || !isCurrentOwner()) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      try { link.href = url; link.download = `${book?.title || "小说"}.md`; link.hidden = true; document.body.appendChild(link); link.click(); }
      finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch { /* The common ErrorNotice shows the translated reason. */ }
  };
  const remove = async () => {
    if (!isCurrentOwner()) return;
    if (!(await confirm({
      body: `确定删除「${book?.title || "这本书"}」？章节、推演和留言都会删除，无法恢复。`,
      confirmLabel: "删除",
      danger: true,
    }))) return;
    // The account can change while the confirmation dialog is open.
    if (!isCurrentOwner()) return;
    try { const result = await mutate("delete", signal => novelApi.remove(id, { signal }), { refresh: false }); if (result && isCurrentOwner()) router.push(novelHref("/novels", embedded)); } catch { /* Shown above the workbench. */ }
  };
  const saveSettings = async (patch: NovelPatchInput, resume: boolean) => {
    await mutate("patch", async signal => { await novelApi.patch(id, patch, { signal }); if (resume) await novelApi.action(id, "resume", undefined, { signal }); }, { errorTarget: "local" });
  };
  const saveCharacter = async (characterId: string, patch: NovelCharacterEdit) => {
    const result = await mutate("character", signal => updateNovelCharacter(id, characterId, patch, signal), { errorTarget: "local" });
    if (!result || !isCurrentOwner()) return false;
    // Cancel older reads before publishing the complete bible returned by PATCH.
    beginBible(); bibleVersion.current = result.version;
    setBible(result); setBibleError(""); setBibleLoading(false);
    return true;
  };
  const currentChapter = chapter?.chapter === selectedChapter ? chapter : null;
  const beatSheet = book?.status === "awaiting_plan" && currentChapter?.status === "awaiting_plan_approval" ? currentChapter.meeting.decision?.beat_sheet : null;
  const writingChapter = book?.status === "running" ? book.chapters.findLast(item => ["planning", "writing", "reviewing", "archiving"].includes(item.status))?.chapter ?? book.chapters_done + 1 : null;

  return <div className={`relative flex flex-col ${embedded ? "min-h-screen mobile:min-h-dvh" : "h-dvh overflow-hidden"}`} data-novel-workbench>
    {!embedded && <InkLandscape variant="page" />}
    <div className="relative z-[1] flex min-h-0 flex-1">{!embedded && <Sidebar />}
      <main className={`min-w-0 flex-1 px-8 pb-10 pt-5 mobile:px-4 mobile:pt-3 ${embedded ? "mobile:pb-6" : "overflow-y-auto mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom)+24px)]"}`}>
        <div className="mx-auto max-w-[1560px] space-y-5">
          <Link href={novelHref("/novels", embedded)} className="inline-flex min-h-10 items-center gap-2 text-fs-13 text-[color:var(--ink2)]"><ArrowLeft size={14} />回到书架</Link>
          {!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : <EmptyState>请登录后打开你的书斋。<Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">前往登录</Link></EmptyState>) : <>
            {readError && <ErrorNotice message={readError} retry={() => void load()} />}
            {operationError && <div className="space-y-2"><ErrorNotice message={operationError} /><button type="button" className="btn btn-quiet min-h-10" onClick={() => setOperationError("")}>关闭提示</button></div>}
            {chapterError && <ErrorNotice message={chapterError} retry={() => void loadChapter()} />}
            {bibleError && <ErrorNotice message={`圣经暂未更新：${bibleError}`} retry={() => { if (book) void loadBible(book.bible_version); }} />}
            {notesError && <ErrorNotice message={`留言暂未更新：${notesError}`} retry={() => void loadNotes()} />}
            {loading ? <LoadingState>正在打开这本书…</LoadingState> : !book ? <EmptyState>暂时无法打开这本书，请重新加载。</EmptyState> : <>
              <Glaze variant="strip" as="header" className="rounded-xl p-5 mobile:p-4"><div className="relative flex flex-wrap items-start justify-between gap-5">
                <div className="min-w-0 flex-1 basis-72"><div className="flex flex-wrap items-center gap-3"><h1 className="min-w-0 break-words text-fs-30 font-medium tracking-[.24em] mobile:text-fs-22">{book.title || "立项中"}</h1><span className="tag">{novelStatusLabel(book)}</span>{book.config.drama_adaptation && <span className="tag">改编短剧</span>}</div>
                  {book.compass?.logline && <p className="mt-3 whitespace-pre-wrap break-words text-fs-15 leading-[1.9] text-[color:var(--ink2)]">{book.compass.logline}</p>}
                  <p className="readout mt-4 text-fs-13 leading-[1.9]">第 {book.chapters_done} / {book.config.target.max_chapters} 章 · 共 {book.words_done} 字</p>
                  <div className="mt-2 max-w-[320px]"><p className="readout text-fs-13">草莓 {book.spent_strawberries} / {book.budget_strawberries}</p><div role="progressbar" aria-label="草莓预算使用进度" aria-valuemin={0} aria-valuemax={book.budget_strawberries} aria-valuenow={book.spent_strawberries} className="mt-2 h-[3px] overflow-hidden bg-[color:var(--carve)]"><div className="h-full bg-[color:var(--ink2)]" style={{ width: `${Math.min(100, book.spent_strawberries / Math.max(1, book.budget_strawberries) * 100)}%` }} /></div></div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {(["setup_running", "running", "awaiting_plan", "awaiting_review"] as string[]).includes(book.status) && <button type="button" className="btn min-h-10" disabled={!!busy} onClick={() => { void act("pause").catch(() => undefined); }}>{busy === "pause" ? "暂停中…" : "暂停"}</button>}
                  {book.status === "paused" && <button type="button" className="btn min-h-10" disabled={!!busy} onClick={() => { void act("resume").catch(() => undefined); }}>{busy === "resume" ? "继续中…" : "继续"}</button>}
                  <button type="button" className="btn min-h-10" disabled={!!busy} onClick={() => setSettings({ resumeAfter: false })}>调整</button>
                  <button type="button" className="btn min-h-10" disabled={!!busy} onClick={() => void download()}>{busy === "export" ? "导出中…" : "导出"}</button>
                  {completed && studioAllowed && <button type="button" className="btn min-h-10" disabled={!!busy} onClick={() => setFilmDialog(true)}>做成片</button>}
                  <details className="relative"><summary className="btn min-h-10 cursor-pointer list-none">更多</summary><div className="ceramic-card absolute right-0 z-20 mt-2 w-40 p-2"><button type="button" className="btn btn-danger min-h-10 w-full" disabled={!!busy} onClick={() => void remove()}>{busy === "delete" ? "删除中…" : "删除这本书"}</button></div></details>
                  {embedded && <a href={`/novels/${encodeURIComponent(id)}`} target="_blank" rel="noopener noreferrer" className="btn btn-quiet min-h-10">在新页面打开</a>}
                </div>
              </div></Glaze>
              {book.status === "setup_running" && <p role="status" className="py-2 text-fs-13 text-[color:var(--ink2)]">主编正在生成罗盘和设定…</p>}
              <GateBanner book={book} busy={!!busy} onMakeFilm={completed && studioAllowed ? () => setFilmDialog(true) : undefined} onAction={act} onNotes={() => { setRightTab("notes"); setMobileTab("details"); }} onSettings={resumeAfter => setSettings({ resumeAfter: !!resumeAfter })} onView={showReader} onExport={() => void download()} onOpenSettings={() => { if (embedded) window.parent.postMessage({ type: "fiona-novel-open-settings" }, window.location.origin); else router.push("/settings"); }} />
              <div ref={columnsRef} className="@container min-w-0 [overflow-wrap:anywhere]" data-novel-columns>
              <nav className="mb-5 flex min-w-0 border-b @[1040px]:hidden" style={{ borderColor: "var(--carve)" }} aria-label="工作台栏目" role="tablist">{([{ id: "directory", label: "目录" }, { id: "reader", label: "正文" }, { id: "details", label: "推演·圣经·留言" }] as const).map(tab => <button key={tab.id} id={`novel-tab-${tab.id}`} type="button" role="tab" aria-controls={`novel-${tab.id}`} aria-selected={mobileTab === tab.id} onClick={() => setMobileTab(tab.id)} className={`min-h-10 min-w-0 flex-1 border-b px-1 py-3 text-fs-13 ${mobileTab === tab.id ? "border-[color:var(--ink)] text-[color:var(--ink)]" : "border-transparent text-[color:var(--ink2)]"}`}>{tab.label}</button>)}</nav>
              <div className="min-w-0 items-start gap-5 @[1040px]:grid @[1040px]:grid-cols-[minmax(180px,.65fr)_minmax(480px,2fr)_minmax(300px,1fr)]">
                <aside id="novel-directory" role="tabpanel" aria-labelledby="novel-tab-directory" className={`ceramic-card min-w-0 break-words p-4 ${mobileTab !== "directory" ? "hidden @[1040px]:block" : ""}`}><ChapterList chapters={book.chapters} selectedChapter={selectedChapter} writingChapter={writingChapter} onSelect={number => { setSelectedChapter(number); setMobileTab("reader"); }} /></aside>
                <section ref={readerRef} id="novel-reader" role="tabpanel" aria-labelledby="novel-tab-reader" className={`ceramic-card min-w-0 break-words p-6 mobile:p-4 ${mobileTab !== "reader" ? "hidden @[1040px]:block" : ""}`} aria-label="正文与关卡编辑">
                  {book.status === "awaiting_setup" ? bible ? <SetupEditor key={bible.version} bible={bible} busy={!!busy} onApprove={patch => act("setup/approve", patch, "local")} /> : <LoadingState>正在加载立项卡…</LoadingState> : beatSheet && currentChapter ? <PlanEditor key={`${currentChapter.chapter}:${currentChapter.updated_at}`} chapter={currentChapter.chapter} beatSheet={beatSheet} maxScenes={book.config.adaptation.max_scenes_per_chapter} busy={!!busy} onApprove={beat => act("plan/approve", beat ? { beat_sheet: beat } : {}, "local")} onRedo={text => act("plan/redo", { text }, "local")} /> : <ChapterReader key={`${id}:${selectedChapter}`} chapter={currentChapter} loading={chapterLoading || (selectedChapter != null && !currentChapter)} busy={!!busy} onSave={async body => {
                    if (selectedChapter == null) return null;
                    const number = selectedChapter;
                    const result = await mutate("edit", signal => updateNovelChapter(id, number, body, signal), { errorTarget: "local", chapter: number });
                    if (!result) return null;
                    return result.message;
                  }} />}
                </section>
                <aside id="novel-details" role="tabpanel" aria-labelledby="novel-tab-details" className={`ceramic-card min-w-0 break-words p-4 ${mobileTab !== "details" ? "hidden @[1040px]:block" : ""}`} aria-label="推演、圣经与留言">
                  <nav role="tablist" aria-label="书籍资料" className="mb-5 flex min-w-0 border-b" style={{ borderColor: "var(--carve)" }}>{([{ id: "meeting", label: "推演" }, { id: "bible", label: "圣经" }, { id: "notes", label: "留言" }] as const).map(tab => <button key={tab.id} id={`novel-detail-tab-${tab.id}`} role="tab" type="button" aria-selected={rightTab === tab.id} aria-controls={`novel-detail-${tab.id}`} onClick={() => setRightTab(tab.id)} className={`min-h-10 min-w-0 flex-1 border-b px-2 py-3 text-fs-15 ${rightTab === tab.id ? "border-[color:var(--ink)]" : "border-transparent text-[color:var(--ink2)]"}`}>{tab.label}</button>)}</nav>
                  <div id="novel-detail-meeting" role="tabpanel" aria-labelledby="novel-detail-tab-meeting" hidden={rightTab !== "meeting"}>{rightTab === "meeting" && (chapterLoading ? <LoadingState>正在加载推演记录…</LoadingState> : <DeliberationTimeline meeting={currentChapter?.meeting ?? null} panelMode={book.config.panel_mode} />)}</div>
                  <div id="novel-detail-bible" role="tabpanel" aria-labelledby="novel-detail-tab-bible" hidden={rightTab !== "bible"}>{rightTab === "bible" && <BiblePanel bible={bible ? { ...bible, compass: bible.compass ?? book.compass } : null} loading={bibleLoading} status={book.status} busy={!!busy} onSaveCharacter={saveCharacter} />}</div>
                  <div id="novel-detail-notes" role="tabpanel" aria-labelledby="novel-detail-tab-notes" hidden={rightTab !== "notes"}>{rightTab === "notes" && <NotesPanel notes={notes} loading={notesLoading} busy={!!busy} onSubmit={async text => { await mutate("note", signal => addNovelNote(id, text, signal), { errorTarget: "local", notes: true }); }} />}</div>
                </aside>
              </div>
              </div>
              {filmDialog && completed && studioAllowed && <NovelFilmDialog owner={owner} bookId={id} bookTitle={book.title || "未命名作品"} embedded={embedded} onClose={() => setFilmDialog(false)} />}
              {settings && <NovelSettingsDialog book={book} catalog={catalog} catalogError={catalogError} busy={!!busy} resumeAfter={settings.resumeAfter} onSave={saveSettings} onClose={() => setSettings(null)} />}
            </>}
          </>}
        </div>
      </main>
    </div>
  </div>;
}
