"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { canCloseNovelDrawer } from "@/components/novel/NovelShell";
import { ApiError } from "@/lib/agents";
import {
  DESK_STAGES,
  deskMode,
  episodeLocks,
  isRevisionConflict,
  latestProject,
  readDeskPrefs,
  updateDeskPrefs,
  type DeskMode,
  type DeskStage,
  type DeskSubject,
} from "@/lib/desk";
import {
  addNovelNote,
  exportNovel,
  getNovel,
  getNovelChapter,
  getNovelDraft,
  listNovels,
  novelApi,
  novelErrorMessage,
  type NovelAction,
  type NovelBeatSheet,
  type NovelChapter,
  type NovelDetail,
  type NovelSummary,
} from "@/lib/novels";
import { listStudioNovelSources, studioErrorMessage, type StudioNovelCandidate } from "@/lib/studio";
import {
  approveStudioEpisodes,
  getStudioEpisodes,
  operateStudioEpisodes,
  type EpisodeFields,
  type StudioEpisodePlan,
} from "@/lib/studio-breakdown";
import { useAccountRequest } from "@/lib/useAccountIdentity";

import DeskChaptersView from "./DeskChaptersView";
import { DeskPlanDialog, DeskReaderDialog } from "./DeskDialogs";
import DeskEpisodesView from "./DeskEpisodesView";
import DeskFrame from "./DeskFrame";
import DeskIdeaView from "./DeskIdeaView";

export type DeskDockProps = {
  owner: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  studioAllowed: boolean;
  composerHeight: number;
  focus: { subject: DeskSubject; nonce: number } | null;
  onAsk: (prefix: string) => void;
  onOpenNovel: (path: string) => void;
  onOpenNovelShelf: () => void;
  onOpenStudio: (projectId: string | null) => void;
  onOpenSettings: () => void;
};

type ChapterDialogState = {
  chapter: number;
  data: NovelChapter | null;
  loading: boolean;
  error: string | null;
};

type DraftNotice = { draftId: string; title: string };

type DeskEpisodeOperation =
  | { op: "edit"; no: number; fields: EpisodeFields }
  | { op: "merge"; no: number };

type LoadOptions = { showLoading: boolean; reportError: boolean };

const EMPTY_BOOKS_TEXT = "案头空着。对分身说想写什么，或者到书斋新建一本。";
const PLAN_CONFLICT_TEXT = "分集方案已在别处改动，已为你刷新，请再试一次。";
const PANEL_TRIGGER_SELECTOR = 'button[aria-controls="desk-panel"]';

function focusVisibleDeskToggle() {
  const buttons = Array.from(document.querySelectorAll<HTMLElement>(PANEL_TRIGGER_SELECTOR));
  buttons.find(button => button.getClientRects().length > 0)?.focus();
}

function deskStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function planChapterNumber(book: NovelDetail): number {
  return book.chapters.find(chapter => chapter.status === "awaiting_plan_approval")?.chapter
    ?? book.chapters_done + 1;
}

function isRunningBook(book: NovelDetail | null): boolean {
  return book?.status === "running" || book?.status === "setup_running";
}

function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 403 || error.status === 404);
}

export default function DeskDock(props: DeskDockProps) {
  return <DeskDockAccount key={props.owner} {...props} />;
}

function DeskDockAccount({
  owner,
  open,
  onOpenChange,
  studioAllowed,
  composerHeight,
  focus,
  onAsk,
  onOpenNovel,
  onOpenNovelShelf,
  onOpenStudio,
  onOpenSettings,
}: DeskDockProps) {
  const [mode, setMode] = useState<DeskMode | null>(null);
  const modeReady = mode !== null;
  const [stage, setStage] = useState<DeskStage>("chapters");
  const [sheetExpanded, setSheetExpanded] = useState(false);

  const [books, setBooks] = useState<NovelSummary[] | null>(null);
  const [book, setBook] = useState<NovelDetail | null>(null);
  const [booksLoading, setBooksLoading] = useState(false);
  const [bookLoading, setBookLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [accessError, setAccessError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);
  const [draftNotice, setDraftNotice] = useState<DraftNotice | null>(null);

  const [planDialog, setPlanDialog] = useState<ChapterDialogState | null>(null);
  const [readerDialog, setReaderDialog] = useState<ChapterDialogState | null>(null);

  const [candidate, setCandidate] = useState<StudioNovelCandidate | null | undefined>(undefined);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [plan, setPlan] = useState<StudioEpisodePlan | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [planNotice, setPlanNotice] = useState<string | null>(null);

  const panelRef = useRef<HTMLElement>(null);
  const busyRef = useRef(false);
  const bookRef = useRef<NovelDetail | null>(null);
  const selectedBookRef = useRef<string | null>(null);
  const desiredBookRef = useRef<string | null>(null);
  const stageOverrideRef = useRef(false);
  const projectIdRef = useRef<string | null>(null);
  const chatProjectRef = useRef<string | null>(null);
  const handledFocusNonceRef = useRef<number | null>(null);
  const focusRequestRef = useRef<{ nonce: number; request: { isCurrent: () => boolean } | null } | null>(null);
  const returnFocusRef = useRef<Element | null>(null);
  const planTokenRef = useRef(0);
  const readerTokenRef = useRef(0);
  const planEpochRef = useRef(0);
  const panelFocusedRef = useRef(false);
  const openRef = useRef(open);
  const dialogOpenRef = useRef(false);
  const episodeDialogOpenRef = useRef(false);

  useEffect(() => {
    openRef.current = open;
  }, [open]);

  useEffect(() => {
    dialogOpenRef.current = planDialog !== null || readerDialog !== null || episodeDialogOpenRef.current;
  }, [planDialog, readerDialog]);

  const handleEpisodeDialogOpenChange = useCallback((value: boolean) => {
    episodeDialogOpenRef.current = value;
    dialogOpenRef.current = planDialog !== null || readerDialog !== null || value;
  }, [planDialog, readerDialog]);

  // 每种读用途各用一个作用域，写请求单独一个，避免轮询取消其他读请求或写请求。
  const { beginRequest: beginDetailRead } = useAccountRequest(owner);
  const { beginRequest: beginListRead } = useAccountRequest(owner);
  const { beginRequest: beginCandidateRead } = useAccountRequest(owner);
  const { beginRequest: beginEpisodeRead } = useAccountRequest(owner);
  const { beginRequest: beginFocusRead } = useAccountRequest(owner);
  const { beginRequest: beginDialogRead } = useAccountRequest(owner);
  const { beginRequest: beginExportRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation } = useAccountRequest(owner);

  const cancelReadScopes = useCallback(() => {
    beginDetailRead();
    beginListRead();
    beginCandidateRead();
    beginEpisodeRead();
    beginFocusRead();
    beginDialogRead();
    beginExportRead();
  }, [
    beginCandidateRead,
    beginDetailRead,
    beginDialogRead,
    beginEpisodeRead,
    beginExportRead,
    beginFocusRead,
    beginListRead,
  ]);

  useEffect(() => {
    if (!open) return;
    const updateMode = () => setMode(deskMode(window.innerWidth));
    const frame = window.requestAnimationFrame(updateMode);
    window.addEventListener("resize", updateMode);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updateMode);
    };
  }, [open]);

  const focusDialogTrigger = useCallback(() => {
    const trigger = returnFocusRef.current;
    returnFocusRef.current = null;
    window.requestAnimationFrame(() => {
      if (trigger instanceof HTMLElement && trigger !== document.body && trigger.isConnected) {
        trigger.focus();
        return;
      }
      focusVisibleDeskToggle();
    });
  }, []);

  const focusDeskPanel = useCallback(() => {
    window.requestAnimationFrame(() => {
      panelRef.current?.focus();
      panelFocusedRef.current = true;
    });
  }, []);

  const dismissDialogs = useCallback(() => {
    planTokenRef.current += 1;
    readerTokenRef.current += 1;
    returnFocusRef.current = null;
    setPlanDialog(null);
    setReaderDialog(null);
  }, []);

  const closeFromPanel = useCallback(() => {
    onOpenChange(false);
    window.requestAnimationFrame(focusVisibleDeskToggle);
  }, [onOpenChange]);

  const closePlanDialog = useCallback((restoreFocus = true) => {
    planTokenRef.current += 1;
    setPlanDialog(null);
    if (restoreFocus) focusDialogTrigger();
  }, [focusDialogTrigger]);

  const closeReaderDialog = useCallback(() => {
    readerTokenRef.current += 1;
    setReaderDialog(null);
    focusDialogTrigger();
  }, [focusDialogTrigger]);

  const resetEpisodes = useCallback(() => {
    setCandidate(undefined);
    setCandidateLoading(false);
    setCandidateError(null);
    projectIdRef.current = null;
    setProjectId(null);
    setPlan(null);
    setPlanLoading(false);
    setPlanError(null);
    setPlanNotice(null);
  }, []);

  const loadBookDetail = useCallback(async (id: string, options: LoadOptions) => {
    if (selectedBookRef.current !== id || !openRef.current) return;
    const request = beginDetailRead();
    if (!request) {
      if (options.showLoading) setBookLoading(false);
      return;
    }
    if (options.showLoading) setBookLoading(true);
    if (options.reportError) setDetailError(null);
    try {
      const detail = await getNovel(id, request.signal);
      if (!request.isCurrent() || selectedBookRef.current !== id || !openRef.current) return;
      bookRef.current = detail;
      setBook(detail);
      setDetailError(null);
    } catch (cause) {
      if (!request.isCurrent() || selectedBookRef.current !== id || !openRef.current) return;
      if (options.reportError) setDetailError(novelErrorMessage(cause));
    } finally {
      if (request.isCurrent() && selectedBookRef.current === id) setBookLoading(false);
    }
  }, [beginDetailRead]);

  const selectBook = useCallback((id: string, options?: { clearDraft?: boolean }) => {
    if (!openRef.current) return;
    desiredBookRef.current = id;
    selectedBookRef.current = id;
    updateDeskPrefs(deskStorage(), owner, { novelId: id });
    dismissDialogs();
    if (options?.clearDraft) setDraftNotice(null);
    setGateError(null);
    setDetailError(null);
    bookRef.current = null;
    setBook(null);
    resetEpisodes();
    void loadBookDetail(id, { showLoading: true, reportError: true });
  }, [dismissDialogs, loadBookDetail, owner, resetEpisodes]);

  const selectBookFromList = useCallback((id: string) => {
    chatProjectRef.current = null;
    selectBook(id, { clearDraft: true });
  }, [selectBook]);

  const loadBooks = useCallback(async (rememberedNovelId: string | null) => {
    if (!openRef.current) return;
    const request = beginListRead();
    if (!request) return;
    setBooksLoading(true);
    setListError(null);
    setAccessError(null);
    try {
      const list = await listNovels(request.signal);
      if (!request.isCurrent() || !openRef.current) return;
      setBooks(list);
      if (list.length === 0) {
        selectedBookRef.current = null;
        bookRef.current = null;
        setBook(null);
        setBooksLoading(false);
        setBookLoading(false);
        setDetailError(null);
        setGateError(null);
        return;
      }
      const remembered = rememberedNovelId && list.some(item => item.id === rememberedNovelId)
        ? rememberedNovelId
        : null;
      const desiredId = desiredBookRef.current;
      const desired = desiredId && list.some(item => item.id === desiredId) ? desiredId : null;
      const chosenId = desired ?? remembered ?? list.reduce((latest, item) => item.updated_at > latest.updated_at ? item : latest).id;
      setBooksLoading(false);
      selectBook(chosenId);
    } catch (cause) {
      if (!request.isCurrent()) return;
      setBooksLoading(false);
      setBookLoading(false);
      if (isForbiddenError(cause)) {
        selectedBookRef.current = null;
        bookRef.current = null;
        setBook(null);
        setBooks([]);
        setDetailError(null);
        setGateError(null);
        setAccessError(novelErrorMessage(cause));
      } else {
        setListError(novelErrorMessage(cause));
      }
    }
  }, [beginListRead, selectBook]);

  const applyStage = useCallback((next: DeskStage) => {
    if (!DESK_STAGES.some(item => item.id === next && item.enabled)) return;
    stageOverrideRef.current = true;
    setStage(next);
    updateDeskPrefs(deskStorage(), owner, { stage: next });
  }, [owner]);

  const loadPlan = useCallback(async (targetProjectId: string, options: LoadOptions) => {
    if (!openRef.current) return;
    const request = beginEpisodeRead();
    if (!request) {
      if (options.showLoading) setPlanLoading(false);
      return;
    }
    const epoch = planEpochRef.current;
    if (options.showLoading) {
      setPlanLoading(true);
      setPlanError(null);
    }
    try {
      const next = await getStudioEpisodes(targetProjectId, request.signal);
      if (!request.isCurrent() || !openRef.current || projectIdRef.current !== targetProjectId || epoch !== planEpochRef.current) return;
      setPlan(next);
      setPlanError(null);
    } catch (cause) {
      if (!request.isCurrent() || !openRef.current || projectIdRef.current !== targetProjectId || epoch !== planEpochRef.current) return;
      if (options.reportError) setPlanError(studioErrorMessage(cause));
    } finally {
      if (request.isCurrent() && projectIdRef.current === targetProjectId) setPlanLoading(false);
    }
  }, [beginEpisodeRead]);

  const loadCandidate = useCallback(async (bookId: string) => {
    if (!studioAllowed || !openRef.current) return;
    const request = beginCandidateRead();
    if (!request) return;
    setCandidateLoading(true);
    setCandidateError(null);
    try {
      const sources = await listStudioNovelSources(request.signal);
      if (!request.isCurrent() || !openRef.current || selectedBookRef.current !== bookId) return;
      const found = sources.books.find(item => item.id === bookId) ?? null;
      setCandidate(found);
      setCandidateLoading(false);
      if (!found || found.projects.length === 0) {
        projectIdRef.current = null;
        setProjectId(null);
        setPlan(null);
        setPlanLoading(false);
        setPlanError(null);
        return;
      }
      const rememberedProject = chatProjectRef.current ?? projectIdRef.current;
      const chosen = rememberedProject && found.projects.some(item => item.id === rememberedProject)
        ? rememberedProject
        : latestProject(found.projects)?.id ?? null;
      chatProjectRef.current = null;
      projectIdRef.current = chosen;
      setProjectId(chosen);
      if (chosen) void loadPlan(chosen, { showLoading: true, reportError: true });
    } catch (cause) {
      if (!request.isCurrent() || !openRef.current || selectedBookRef.current !== bookId) return;
      setCandidateLoading(false);
      setCandidateError(studioErrorMessage(cause));
      setCandidate(null);
      setPlan(null);
      setPlanError(null);
    }
  }, [beginCandidateRead, loadPlan, studioAllowed]);

  const refreshPlanAfterConflict = useCallback(async (targetProjectId: string): Promise<StudioEpisodePlan | null> => {
    if (!openRef.current) return null;
    planEpochRef.current += 1;
    const epoch = planEpochRef.current;
    const request = beginEpisodeRead();
    if (!request) return null;
    try {
      const next = await getStudioEpisodes(targetProjectId, request.signal);
      if (!request.isCurrent() || !openRef.current || projectIdRef.current !== targetProjectId || epoch !== planEpochRef.current) return null;
      setPlan(next);
      setPlanLoading(false);
      setPlanError(null);
      return next;
    } catch {
      // 版本冲突的刷新失败不再覆盖给用户的提示。
      return null;
    } finally {
      if (epoch === planEpochRef.current) setPlanLoading(false);
    }
  }, [beginEpisodeRead]);

  const runNovelAction = useCallback(async (action: NovelAction, body?: unknown) => {
    if (!bookRef.current || busyRef.current) return;
    const targetBookId = bookRef.current.id;
    const request = beginMutation();
    if (!request) return;
    busyRef.current = true;
    setBusy(true);
    setGateError(null);
    try {
      await novelApi.action(targetBookId, action, body, { signal: request.signal });
      if (!request.isCurrent() || !openRef.current || selectedBookRef.current !== targetBookId) return;
      await loadBookDetail(targetBookId, { showLoading: false, reportError: true });
    } catch (cause) {
      if (request.isCurrent() && openRef.current && selectedBookRef.current === targetBookId) setGateError(novelErrorMessage(cause));
      throw cause;
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [beginMutation, loadBookDetail]);

  const planAct = useCallback(async (path: "plan/approve" | "plan/redo", body: unknown) => {
    if (!bookRef.current) return;
    if (busyRef.current) throw new Error("正在处理，请稍后重试。");
    const targetBookId = bookRef.current.id;
    const request = beginMutation();
    if (!request) return;
    busyRef.current = true;
    setBusy(true);
    try {
      await novelApi.action(targetBookId, path, body, { signal: request.signal });
      if (!request.isCurrent() || !openRef.current || selectedBookRef.current !== targetBookId) return;
      await loadBookDetail(targetBookId, { showLoading: false, reportError: true });
      if (!request.isCurrent() || !openRef.current || selectedBookRef.current !== targetBookId) return;
      closePlanDialog(false);
      focusDeskPanel();
    } catch (cause) {
      throw new Error(novelErrorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [beginMutation, closePlanDialog, focusDeskPanel, loadBookDetail]);

  const addNote = useCallback(async (text: string) => {
    const targetBookId = bookRef.current?.id;
    if (!targetBookId) throw new Error("请先选择作品。");
    if (busyRef.current) throw new Error("正在处理，请稍后重试。");
    const request = beginMutation();
    if (!request) throw new Error("请求未完成，请稍后重试。");
    busyRef.current = true;
    setBusy(true);
    try {
      await addNovelNote(targetBookId, text, request.signal);
      if (!request.isCurrent() || !openRef.current || selectedBookRef.current !== targetBookId) return;
      await loadBookDetail(targetBookId, { showLoading: false, reportError: true });
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [beginMutation, loadBookDetail]);

  const exportBook = useCallback(async () => {
    const target = bookRef.current;
    if (!target || busyRef.current || !openRef.current) return;
    const request = beginExportRead();
    if (!request) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const blob = await exportNovel(target.id, request.signal);
      if (!request.isCurrent() || !openRef.current) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      try {
        link.href = url;
        link.download = `${target.title?.trim() || "小说"}.md`;
        link.hidden = true;
        document.body.appendChild(link);
        link.click();
      } finally {
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (cause) {
      if (request.isCurrent() && openRef.current && selectedBookRef.current === target.id) setGateError(novelErrorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [beginExportRead]);

  const openPlanDialog = useCallback(() => {
    if (!bookRef.current || !openRef.current) return;
    const target = bookRef.current;
    const chapter = planChapterNumber(target);
    returnFocusRef.current = document.activeElement;
    planTokenRef.current += 1;
    const token = planTokenRef.current;
    setPlanDialog({ chapter, data: null, loading: true, error: null });
    const request = beginDialogRead();
    if (!request) {
      setPlanDialog({ chapter, data: null, loading: false, error: "请求未完成，请稍后重试。" });
      return;
    }
    void (async () => {
      try {
        const data = await getNovelChapter(target.id, chapter, request.signal);
        if (!request.isCurrent() || !openRef.current || planTokenRef.current !== token) return;
        setPlanDialog({ chapter, data, loading: false, error: null });
      } catch (cause) {
        if (!request.isCurrent() || !openRef.current || planTokenRef.current !== token) return;
        setPlanDialog({ chapter, data: null, loading: false, error: novelErrorMessage(cause) });
      }
    })();
  }, [beginDialogRead]);

  const openReaderDialog = useCallback((chapter: number) => {
    if (!bookRef.current || !openRef.current) return;
    const target = bookRef.current;
    returnFocusRef.current = document.activeElement;
    readerTokenRef.current += 1;
    const token = readerTokenRef.current;
    setReaderDialog({ chapter, data: null, loading: true, error: null });
    const request = beginDialogRead();
    if (!request) {
      setReaderDialog({ chapter, data: null, loading: false, error: "请求未完成，请稍后重试。" });
      return;
    }
    void (async () => {
      try {
        const data = await getNovelChapter(target.id, chapter, request.signal);
        if (!request.isCurrent() || !openRef.current || readerTokenRef.current !== token) return;
        setReaderDialog({ chapter, data, loading: false, error: null });
      } catch (cause) {
        if (!request.isCurrent() || !openRef.current || readerTokenRef.current !== token) return;
        setReaderDialog({ chapter, data: null, loading: false, error: novelErrorMessage(cause) });
      }
    })();
  }, [beginDialogRead]);

  const selectProject = useCallback((id: string) => {
    if (!openRef.current) return;
    if (!candidate || !candidate.projects.some(item => item.id === id)) return;
    if (projectIdRef.current === id) return;
    chatProjectRef.current = null;
    projectIdRef.current = id;
    setProjectId(id);
    setPlan(null);
    setPlanError(null);
    setPlanNotice(null);
    void loadPlan(id, { showLoading: true, reportError: true });
  }, [candidate, loadPlan]);

  const operatePlan = useCallback(async (operation: DeskEpisodeOperation) => {
    const targetProjectId = projectIdRef.current;
    const currentPlan = plan;
    if (!targetProjectId || !currentPlan) return;
    if (busyRef.current) throw new Error("正在处理，请稍后重试。");
    const request = beginMutation();
    if (!request) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const next = await operateStudioEpisodes(
        targetProjectId,
        { ...operation, expected_revision: currentPlan.plan_revision },
        request.signal,
      );
      if (!request.isCurrent() || projectIdRef.current !== targetProjectId) return;
      planEpochRef.current += 1;
      setPlan(next);
      setPlanLoading(false);
      setPlanError(null);
      setPlanNotice(null);
    } catch (cause) {
      if (request.isCurrent() && projectIdRef.current === targetProjectId && cause instanceof ApiError && cause.status === 409) {
        const refreshed = await refreshPlanAfterConflict(targetProjectId);
        if (request.isCurrent() && isRevisionConflict(currentPlan.plan_revision, refreshed)) {
          setPlanNotice(PLAN_CONFLICT_TEXT);
          return;
        }
      }
      throw cause;
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [beginMutation, plan, refreshPlanAfterConflict]);

  const approvePlan = useCallback(async () => {
    const targetProjectId = projectIdRef.current;
    const currentPlan = plan;
    if (!targetProjectId || !currentPlan) return;
    if (busyRef.current) throw new Error("正在处理，请稍后重试。");
    const request = beginMutation();
    if (!request) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const next = await approveStudioEpisodes(targetProjectId, currentPlan.plan_revision, request.signal);
      if (!request.isCurrent() || projectIdRef.current !== targetProjectId) return;
      planEpochRef.current += 1;
      setPlan(next);
      setPlanLoading(false);
      setPlanError(null);
      setPlanNotice(null);
    } catch (cause) {
      if (request.isCurrent() && projectIdRef.current === targetProjectId && cause instanceof ApiError && cause.status === 409) {
        const refreshed = await refreshPlanAfterConflict(targetProjectId);
        if (request.isCurrent() && isRevisionConflict(currentPlan.plan_revision, refreshed)) {
          setPlanNotice(PLAN_CONFLICT_TEXT);
          return;
        }
      }
      throw cause;
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [beginMutation, plan, refreshPlanAfterConflict]);

  const refreshAll = useCallback(() => {
    if (!openRef.current) return;
    setPlanNotice(null);
    const id = selectedBookRef.current;
    if (id) void loadBookDetail(id, { showLoading: false, reportError: true });
    const currentBook = bookRef.current;
    if (open && stage === "episodes" && studioAllowed && currentBook) {
      void loadCandidate(currentBook.id);
    }
  }, [loadBookDetail, loadCandidate, open, stage, studioAllowed]);

  const retry = useCallback(() => {
    if (!openRef.current) return;
    if (listError) {
      const remembered = readDeskPrefs(deskStorage(), owner).novelId;
      void loadBooks(remembered);
      return;
    }
    const id = selectedBookRef.current;
    if (id) void loadBookDetail(id, { showLoading: true, reportError: true });
  }, [listError, loadBookDetail, loadBooks, owner]);

  useEffect(() => {
    if (!open || !owner || !modeReady) return;
    const frame = window.requestAnimationFrame(() => {
      const prefs = readDeskPrefs(deskStorage(), owner);
      if (!stageOverrideRef.current) setStage(prefs.stage);
      void loadBooks(prefs.novelId);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [loadBooks, modeReady, open, owner]);

  useEffect(() => {
    if (open) return;
    cancelReadScopes();
    const frame = window.requestAnimationFrame(() => {
      planTokenRef.current += 1;
      readerTokenRef.current += 1;
      returnFocusRef.current = null;
      stageOverrideRef.current = false;
      desiredBookRef.current = null;
      chatProjectRef.current = null;
      setPlanDialog(null);
      setReaderDialog(null);
      setDraftNotice(null);
      setGateError(null);
      setPlanNotice(null);
      setMode(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [cancelReadScopes, open]);

  useEffect(() => {
    if (!open || !modeReady || accessError || !focus) return;
    if (handledFocusNonceRef.current === focus.nonce) return;
    if (dialogOpenRef.current) {
      // 作者正在改细纲、读正文或编辑分集时，忽略这一次聊天定位，不关对话框。
      beginFocusRead();
      handledFocusNonceRef.current = focus.nonce;
      focusRequestRef.current = { nonce: focus.nonce, request: null };
      return;
    }
    const previous = focusRequestRef.current;
    if (previous?.nonce === focus.nonce && previous.request?.isCurrent()) return;
    const subject = focus.subject;
    if (subject.kind === "project" && !studioAllowed) {
      handledFocusNonceRef.current = focus.nonce;
      focusRequestRef.current = { nonce: focus.nonce, request: null };
      return;
    }
    const request = beginFocusRead();
    if (!request) {
      handledFocusNonceRef.current = focus.nonce;
      focusRequestRef.current = { nonce: focus.nonce, request: null };
      return;
    }
    focusRequestRef.current = { nonce: focus.nonce, request };
    void (async () => {
      try {
        if (subject.kind === "draft") {
          const draft = await getNovelDraft(subject.draftId, request.signal);
          if (!request.isCurrent() || !openRef.current) return;
          if (dialogOpenRef.current) {
            handledFocusNonceRef.current = focus.nonce;
            return;
          }
          if (!draft.novel_id) {
            setDraftNotice({
              draftId: subject.draftId,
              title: draft.title?.trim() || "未命名",
            });
            handledFocusNonceRef.current = focus.nonce;
            return;
          }
          chatProjectRef.current = null;
          applyStage("chapters");
          selectBook(draft.novel_id, { clearDraft: true });
          handledFocusNonceRef.current = focus.nonce;
          return;
        }
        const sources = await listStudioNovelSources(request.signal);
        if (!request.isCurrent() || !openRef.current) return;
        if (dialogOpenRef.current) {
          handledFocusNonceRef.current = focus.nonce;
          return;
        }
        const found = sources.books.find(item => item.projects.some(project => project.id === subject.projectId));
        if (!found) {
          handledFocusNonceRef.current = focus.nonce;
          return;
        }
        applyStage("episodes");
        if (bookRef.current?.id === found.id) {
          dismissDialogs();
          updateDeskPrefs(deskStorage(), owner, { novelId: found.id });
          setCandidate(found);
          setCandidateError(null);
          setCandidateLoading(false);
          setPlanNotice(null);
          chatProjectRef.current = subject.projectId;
          projectIdRef.current = subject.projectId;
          setProjectId(subject.projectId);
          setPlan(null);
          void loadPlan(subject.projectId, { showLoading: true, reportError: true });
        } else {
          selectBook(found.id, { clearDraft: true });
          chatProjectRef.current = subject.projectId;
        }
        handledFocusNonceRef.current = focus.nonce;
      } catch {
        if (request.isCurrent() && openRef.current) {
          handledFocusNonceRef.current = focus.nonce;
        }
      }
    })();
  }, [
    accessError,
    applyStage,
    beginFocusRead,
    dismissDialogs,
    focus,
    loadPlan,
    modeReady,
    open,
    owner,
    planDialog,
    readerDialog,
    selectBook,
    studioAllowed,
  ]);

  const activeBookRunning = isRunningBook(book);
  useEffect(() => {
    if (!open || !modeReady || !activeBookRunning || planDialog || readerDialog) return;
    let stopped = false;
    let timer: number | undefined;
    const schedule = () => {
      if (!stopped && !document.hidden) timer = window.setTimeout(tick, 3000);
    };
    const tick = async () => {
      if (stopped || document.hidden) return;
      const id = selectedBookRef.current;
      if (id) await loadBookDetail(id, { showLoading: false, reportError: false });
      schedule();
    };
    const onVisibility = () => {
      if (timer !== undefined) window.clearTimeout(timer);
      if (!document.hidden) void tick();
    };
    schedule();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [activeBookRunning, loadBookDetail, modeReady, open, planDialog, readerDialog]);

  useEffect(() => {
    if (!open || !modeReady || !book || activeBookRunning) return;
    const id = book.id;
    const onVisibility = () => {
      if (document.hidden) return;
      void loadBookDetail(id, { showLoading: false, reportError: false });
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [activeBookRunning, book, loadBookDetail, modeReady, open]);

  const episodeBookId = modeReady && open && stage === "episodes" && studioAllowed ? book?.id ?? null : null;
  useEffect(() => {
    if (!episodeBookId) return;
    const frame = window.requestAnimationFrame(() => { void loadCandidate(episodeBookId); });
    return () => window.cancelAnimationFrame(frame);
  }, [episodeBookId, loadCandidate]);

  const episodeEditsBlocked = plan ? episodeLocks(plan).editsBlocked : false;
  useEffect(() => {
    if (!open || !modeReady || stage !== "episodes" || !projectId || !episodeEditsBlocked || planDialog || readerDialog) return;
    const targetProjectId = projectId;
    let stopped = false;
    let timer: number | undefined;
    const schedule = () => {
      if (!stopped && !document.hidden) timer = window.setTimeout(tick, 5000);
    };
    const tick = async () => {
      if (stopped || document.hidden) return;
      await loadPlan(targetProjectId, { showLoading: false, reportError: false });
      schedule();
    };
    const onVisibility = () => {
      if (timer !== undefined) window.clearTimeout(timer);
      if (!document.hidden) void tick();
    };
    schedule();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [episodeEditsBlocked, loadPlan, modeReady, open, planDialog, projectId, readerDialog, stage]);

  useEffect(() => {
    if (!open) {
      if (!panelFocusedRef.current) return;
      const frame = window.requestAnimationFrame(() => {
        panelFocusedRef.current = false;
        focusVisibleDeskToggle();
      });
      return () => window.cancelAnimationFrame(frame);
    }
    if (!mode || panelFocusedRef.current) return;
    const active = document.activeElement;
    if (!(active instanceof HTMLElement) || !active.matches(PANEL_TRIGGER_SELECTOR)) return;
    const frame = window.requestAnimationFrame(() => {
      if (!panelRef.current) return;
      panelRef.current.focus();
      panelFocusedRef.current = true;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [mode, open]);

  useEffect(() => {
    if (!open || (mode !== "drawer" && mode !== "sheet")) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const focused = document.activeElement;
      if (!panelRef.current?.contains(focused)) return;
      if (!canCloseNovelDrawer(event, focused, !!document.querySelector("dialog[open]"))) return;
      onOpenChange(false);
      window.requestAnimationFrame(focusVisibleDeskToggle);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mode, onOpenChange, open]);

  if (!open || !owner || !mode) return null;

  const frameLoading = booksLoading || bookLoading;
  const frameError = listError ?? detailError;

  let stageView: ReactNode = null;
  if (book) {
    if (stage === "idea") {
      stageView = <DeskIdeaView book={book} onOpenNovel={onOpenNovel} />;
    } else if (stage === "chapters") {
      stageView = <DeskChaptersView
        key={book.id}
        book={book}
        busy={busy}
        gateError={gateError}
        onAction={runNovelAction}
        onAddNote={addNote}
        onAsk={onAsk}
        onExport={exportBook}
        onOpenNovel={onOpenNovel}
        onOpenPlan={openPlanDialog}
        onOpenBody={openReaderDialog}
        onOpenSettings={onOpenSettings}
      />;
    } else if (stage === "episodes") {
      stageView = <DeskEpisodesView
        key={`${book.id}:${projectId ?? ""}`}
        studioAllowed={studioAllowed}
        bookTitle={book.title}
        candidate={candidate}
        candidateError={candidateError}
        candidateLoading={candidateLoading}
        projectId={projectId}
        onSelectProject={selectProject}
        plan={plan}
        planLoading={planLoading}
        planError={planError}
        busy={busy}
        onOperate={operatePlan}
        onApprove={approvePlan}
        onOpenStudio={onOpenStudio}
        onAsk={onAsk}
        onRefresh={refreshAll}
        notice={planNotice}
        onDialogOpenChange={handleEpisodeDialogOpenChange}
      />;
    }
  }

  const draftBlock = draftNotice ? <div className="shrink-0 space-y-3 border-b border-[color:var(--rule)] py-3">
    <p className="break-words text-fs-13 leading-relaxed text-[color:var(--ink)]">
      {`草稿《${draftNotice.title}》还没建书。`}
    </p>
    <button
      type="button"
      className="btn min-h-10"
      onClick={() => onOpenNovel(`/novels/new?embed=1&draft=${draftNotice.draftId}`)}
    >
      去书斋建书
    </button>
  </div> : null;

  let content: ReactNode = null;
  if (accessError) {
    content = <p role="alert" className="break-words py-3 text-fs-13 leading-relaxed text-[color:var(--ink2)]">{accessError}</p>;
  } else if (draftNotice) {
    content = <>{draftBlock}{stageView}</>;
  } else if (books !== null && books.length === 0) {
    content = <div className="space-y-3 py-3">
      <p className="break-words text-fs-13 leading-relaxed text-[color:var(--ink2)]">{EMPTY_BOOKS_TEXT}</p>
      <button type="button" className="btn min-h-10" onClick={onOpenNovelShelf}>去书斋</button>
    </div>;
  } else {
    content = stageView;
  }

  return <>
    <DeskFrame
      mode={mode}
      stage={stage}
      onStageChange={applyStage}
      books={books}
      book={book}
      loading={frameLoading}
      error={frameError}
      onRetry={retry}
      onSelectBook={selectBookFromList}
      onRefresh={refreshAll}
      onClose={closeFromPanel}
      onOpenNovel={onOpenNovel}
      onOpenStudio={onOpenStudio}
      studioProjectId={projectId}
      composerHeight={composerHeight}
      sheetExpanded={sheetExpanded}
      onToggleSheet={() => setSheetExpanded(current => !current)}
      panelRef={panelRef}
    >
      {content}
    </DeskFrame>
    {planDialog && book && <DeskPlanDialog
      key={`plan-${planDialog.chapter}`}
      book={book}
      chapter={planDialog.chapter}
      data={planDialog.data}
      loading={planDialog.loading}
      error={planDialog.error}
      busy={busy}
      onApprove={(beat?: NovelBeatSheet) => planAct("plan/approve", beat ? { beat_sheet: beat } : {})}
      onRedo={(text: string) => planAct("plan/redo", { text })}
      onClose={closePlanDialog}
      onOpenNovel={onOpenNovel}
    />}
    {readerDialog && book && <DeskReaderDialog
      key={`reader-${readerDialog.chapter}`}
      book={book}
      chapter={readerDialog.chapter}
      data={readerDialog.data}
      loading={readerDialog.loading}
      error={readerDialog.error}
      onClose={closeReaderDialog}
      onOpenNovel={onOpenNovel}
    />}
  </>;
}
