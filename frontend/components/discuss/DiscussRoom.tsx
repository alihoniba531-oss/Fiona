"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useConfirm } from "@/components/ConfirmDialog";
import DiscussComposer from "@/components/discuss/DiscussComposer";
import { DiscussBudgetDialog, DiscussContinueDialog } from "@/components/discuss/DiscussDialogs";
import DiscussOutputPanel from "@/components/discuss/DiscussOutputPanel";
import DiscussPlanPanel from "@/components/discuss/DiscussPlanPanel";
import DiscussSourcesPanel from "@/components/discuss/DiscussSourcesPanel";
import DiscussTimeline from "@/components/discuss/DiscussTimeline";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import {
  acceptDiscussGroup,
  addDiscussNote,
  closeDiscussGroup,
  continueDiscussGroup,
  deleteDiscussGroup,
  exportDiscussGroupFile,
  getDiscussCatalog,
  getDiscussGroup,
  listDiscussSources,
  pauseDiscussGroup,
  resumeDiscussGroup,
  startDiscussGroup,
  type DiscussAction,
  type DiscussCatalog,
  type DiscussContinueInput,
  type DiscussDetail,
  type DiscussMessage,
  type DiscussSource,
  type DiscussTab,
} from "@/lib/discuss";
import {
  advanceDiscussCursor,
  applyPendingNotes,
  discussActions,
  discussDefaultTab,
  discussErrorMessage,
  discussHref,
  discussIsActive,
  discussStatusLabel,
  discussStopHint,
  mergeDiscussMessages,
  splitDiscussCitations,
} from "@/lib/discussLogic";
import { useAccountIdentity, useAccountIdentityPending, useAccountRequest } from "@/lib/useAccountIdentity";
import { useRovingTabs } from "@/lib/useRovingTabs";

const PAGE_SIZE = 200;
const POLL_MS = 3000;
const WIDE_MIN = 1080;

const ACTION_LABELS: Record<DiscussAction, string> = {
  start: "开工",
  pause: "暂停",
  resume: "继续",
  continue: "追加轮数",
  rework: "按意见返工",
  accept: "接受成果",
  close: "结束",
  export: "导出",
  delete: "删除",
};

const BUSY_LABELS: Partial<Record<DiscussAction, string>> = {
  start: "开工中",
  pause: "暂停中",
  resume: "继续中",
  continue: "追加轮数中",
  rework: "返工中",
  accept: "接受中",
  close: "结束中",
  export: "导出中",
  delete: "删除中",
};

const MAIN_ACTIONS: DiscussAction[] = ["start", "pause", "resume", "continue", "rework", "accept"];

type Busy = DiscussAction | "note" | "";
type RightTab = Exclude<DiscussTab, "chat">;
type TabDef = { id: DiscussTab; label: string };

const ALL_TABS: TabDef[] = [
  { id: "chat", label: "群聊" },
  { id: "plan", label: "方案" },
  { id: "output", label: "成果" },
  { id: "sources", label: "来源" },
];

const RIGHT_TABS: TabDef[] = [
  { id: "plan", label: "方案" },
  { id: "output", label: "成果" },
  { id: "sources", label: "来源" },
];

type ReadFailure = {
  message: string;
  status?: number;
  missing: boolean;
  blocked: boolean;
};

type DialogState = { kind: "budget" } | { kind: "continue"; title: string };

function errorStatus(error: unknown): number | undefined {
  return error !== null && typeof error === "object"
    ? (error as { status?: number }).status
    : undefined;
}

export default function DiscussRoom({ id, embedded }: { id: string; embedded: boolean }) {
  const owner = useAccountIdentity();
  const identityPending = useAccountIdentityPending();
  if (!owner) {
    return identityPending
      ? <LoadingState>正在加载身份…</LoadingState>
      : <EmptyState>
          请登录后使用讨论群。
          <Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">前往登录</Link>
        </EmptyState>;
  }
  return <Room key={`${owner}:${id}`} owner={owner} id={id} embedded={embedded} />;
}

function Room({ owner, id, embedded }: { owner: string; id: string; embedded: boolean }) {
  const router = useRouter();
  const confirm = useConfirm();
  const [detail, setDetail] = useState<DiscussDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [readFailure, setReadFailure] = useState<ReadFailure | null>(null);
  const [tab, setTab] = useState<DiscussTab>("chat");
  const [rightTab, setRightTab] = useState<RightTab>("plan");
  const [wide, setWide] = useState(false);
  const [planDirty, setPlanDirty] = useState(false);
  const [planKey, setPlanKey] = useState(0);
  const [catalog, setCatalog] = useState<DiscussCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [sources, setSources] = useState<DiscussSource[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState("");
  const [outputContent, setOutputContent] = useState<string | null>(null);
  const [draftVersion, setDraftVersion] = useState<number | undefined>(undefined);
  const [draftNonce, setDraftNonce] = useState(0);
  const [busy, setBusy] = useState<Busy>("");
  const [operationError, setOperationError] = useState("");
  const [pollError, setPollError] = useState("");
  const [planReloadOffered, setPlanReloadOffered] = useState(false);
  const [dialog, setDialog] = useState<DialogState | null>(null);

  const detailRef = useRef<DiscussDetail | null>(null);
  const cursorRef = useRef(0);
  const mutating = useRef(false);
  const sourcesInFlight = useRef(false);
  const unknownCheck = useRef("");
  const defaultTabApplied = useRef(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const { beginRequest: beginRead } = useAccountRequest(owner);
  const { beginRequest: beginMutation, isCurrentOwner } = useAccountRequest(owner);
  const { beginRequest: beginCatalog } = useAccountRequest(owner);
  const { beginRequest: beginSources } = useAccountRequest(owner);

  const publishDetail = useCallback((next: DiscussDetail, mode: "merge" | "replace" = "merge") => {
    const current = mode === "replace" ? null : detailRef.current;
    // 游标只随服务器读回的消息推进；本地并入的插话不在这里传入。
    cursorRef.current = advanceDiscussCursor(cursorRef.current, next.messages);
    const merged = current
      ? mergeDiscussMessages(current.messages, next.messages)
      : next.messages;
    const messages = applyPendingNotes(merged, next.pending_notes);
    const value: DiscussDetail = { ...next, messages };
    detailRef.current = value;
    setDetail(value);
  }, []);

  const loadInitial = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    setLoading(true);
    setReadFailure(null);
    try {
      let after = 0;
      let messages: DiscussMessage[] = [];
      let last: DiscussDetail | null = null;
      for (let page = 0; page < 100; page += 1) {
        const next = await getDiscussGroup(id, after, request.signal);
        if (!request.isCurrent()) return;
        last = next;
        messages = mergeDiscussMessages(messages, next.messages);
        if (next.messages.length < PAGE_SIZE) break;
        const lastId = next.messages[next.messages.length - 1]?.id ?? 0;
        if (lastId <= after) break;
        after = lastId;
      }
      if (!last || !request.isCurrent()) return;
      publishDetail({ ...last, messages }, "replace");
      setPollError("");
      if (!defaultTabApplied.current) {
        defaultTabApplied.current = true;
        const initialTab = discussDefaultTab(last);
        setTab(initialTab);
        if (initialTab !== "chat") setRightTab(initialTab);
      }
    } catch (cause) {
      if (!request.isCurrent()) return;
      const status = errorStatus(cause);
      const message = discussErrorMessage(cause);
      setReadFailure({
        message,
        status,
        missing: status === 404 && message.trim() === "讨论群不存在",
        blocked: status === 403 || status === 404,
      });
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [beginRead, id, publishDetail]);

  useEffect(() => {
    void Promise.resolve().then(() => loadInitial());
  }, [loadInitial]);

  const refreshDetail = useCallback(async (): Promise<boolean> => {
    const request = beginRead();
    if (!request) return false;
    try {
      const next = await getDiscussGroup(id, cursorRef.current, request.signal);
      if (!request.isCurrent()) return false;
      publishDetail(next);
      setPollError("");
      return true;
    } catch (cause) {
      if (request.isCurrent()) setPollError(discussErrorMessage(cause));
      return false;
    }
  }, [beginRead, id, publishDetail]);

  const poll = useCallback(async () => {
    if (mutating.current) return;
    const current = detailRef.current;
    if (!current || !discussIsActive(current.status)) return;
    const request = beginRead();
    if (!request) return;
    try {
      const next = await getDiscussGroup(id, cursorRef.current, request.signal);
      if (!request.isCurrent() || mutating.current) return;
      publishDetail(next);
      setPollError("");
    } catch (cause) {
      if (request.isCurrent() && !mutating.current) {
        setPollError(discussErrorMessage(cause));
      }
    }
  }, [beginRead, id, publishDetail]);

  const status = detail?.status;
  useEffect(() => {
    if (!discussIsActive(status ?? "")) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      if (stopped || document.hidden) return;
      timer = setTimeout(tick, POLL_MS);
    };
    const tick = async () => {
      if (stopped || document.hidden) return;
      await poll();
      if (stopped || document.hidden) return;
      if (discussIsActive(detailRef.current?.status ?? "")) schedule();
    };
    const onVisibility = () => {
      clearTimeout(timer);
      if (!document.hidden) void tick();
    };
    schedule();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [poll, status]);

  const loadCatalog = useCallback(async () => {
    const request = beginCatalog();
    if (!request) return;
    setCatalogError("");
    try {
      const next = await getDiscussCatalog(request.signal);
      if (request.isCurrent()) {
        setCatalog(next);
        setCatalogError("");
      }
    } catch (cause) {
      if (request.isCurrent()) setCatalogError(discussErrorMessage(cause));
    }
  }, [beginCatalog]);

  useEffect(() => {
    void Promise.resolve().then(() => loadCatalog());
  }, [loadCatalog]);

  const loadSources = useCallback(async () => {
    if (sourcesInFlight.current) return;
    const request = beginSources();
    if (!request) return;
    sourcesInFlight.current = true;
    setSourcesLoading(true);
    setSourcesError("");
    try {
      const next = await listDiscussSources(id, request.signal);
      if (!request.isCurrent()) return;
      setSources(Array.isArray(next) ? next : []);
      setSourcesError("");
    } catch (cause) {
      if (request.isCurrent()) setSourcesError(discussErrorMessage(cause));
    } finally {
      sourcesInFlight.current = false;
      setSourcesLoading(false);
    }
  }, [beginSources, id]);

  useEffect(() => {
    void Promise.resolve().then(() => loadSources());
  }, [loadSources]);

  const sourceMap = useMemo(
    () => Object.fromEntries(sources.map(source => [source.id, source])),
    [sources],
  );

  const selectTab = useCallback((next: DiscussTab) => {
    setTab(next);
    if (next !== "chat") setRightTab(next);
    if (next === "sources") {
      const current = detailRef.current;
      if (current && discussIsActive(current.status)) void loadSources();
    }
  }, [loadSources]);

  // 轮询消息或已加载的成果正文里出现来源表没有的编号时，再请求一次来源；
  // 同一组未知编号只补请求一次，请求在途时不重复发。
  useEffect(() => {
    if (!detail || sourcesLoading || sourcesInFlight.current) return;
    const known = new Set(sources.map(source => source.id));
    const unknown = new Set<string>();
    const collect = (text: string) => {
      for (const block of splitDiscussCitations(text)) {
        if (block.kind === "cite" && !known.has(block.id)) unknown.add(block.id);
      }
    };
    for (const message of detail.messages) collect(message.content);
    if (outputContent) collect(outputContent);
    if (unknown.size === 0) return;
    const signature = `${[...unknown].sort().join(",")}|${[...known].sort().join(",")}`;
    if (unknownCheck.current === signature) return;
    unknownCheck.current = signature;
    void Promise.resolve().then(() => loadSources());
  }, [detail, loadSources, outputContent, sources, sourcesLoading]);

  const hasDetail = detail !== null;
  useEffect(() => {
    if (!hasDetail) return;
    const element = contentRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) setWide(entry.contentRect.width >= WIDE_MIN);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasDetail]);

  const mutate = useCallback(async <T,>(
    label: Busy,
    operation: (signal: AbortSignal) => Promise<T>,
    options: { action: DiscussAction; refresh?: boolean },
  ): Promise<T | null> => {
    if (mutating.current || !isCurrentOwner()) return null;
    const request = beginMutation();
    if (!request) return null;
    const refresh = options.refresh !== false;
    // 停掉在途的轮询读取，避免旧响应在操作完成后覆盖页面。
    beginRead();
    mutating.current = true;
    setBusy(label);
    setOperationError("");
    setPlanReloadOffered(false);
    try {
      const result = await operation(request.signal);
      if (!request.isCurrent()) return null;
      if (refresh) await refreshDetail();
      return result;
    } catch (cause) {
      if (!request.isCurrent()) return null;
      const message = discussErrorMessage(cause);
      setOperationError(message);
      if (options.action === "start" && errorStatus(cause) === 409) {
        setPlanReloadOffered(true);
      }
      throw new Error(message);
    } finally {
      mutating.current = false;
      if (request.isCurrent()) setBusy("");
    }
  }, [beginMutation, beginRead, isCurrentOwner, refreshDetail]);

  const exportGroup = useCallback(async () => {
    try {
      const result = await mutate(
        "export",
        signal => exportDiscussGroupFile(id, signal),
        { action: "export", refresh: false },
      );
      if (!result) return;
      const filename = result.filename || "讨论群成果.md";
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      try {
        link.href = url;
        link.download = filename;
        link.hidden = true;
        document.body.appendChild(link);
        link.click();
      } finally {
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch {
      // mutate 已把中文文案放到顶栏下方。
    }
  }, [id, mutate]);

  const reloadPlan = async () => {
    const request = beginRead();
    if (!request) return;
    setPlanReloadOffered(false);
    try {
      const next = await getDiscussGroup(id, cursorRef.current, request.signal);
      if (!request.isCurrent()) return;
      publishDetail(next);
      setPlanDirty(false);
      setPlanKey(key => key + 1);
      setOperationError("");
      setPollError("");
      selectTab("plan");
    } catch (cause) {
      if (request.isCurrent()) {
        setOperationError(discussErrorMessage(cause));
        setPlanReloadOffered(true);
      }
    }
  };

  const focusComposer = () => {
    window.setTimeout(() => {
      document.querySelector<HTMLTextAreaElement>("[data-discuss-composer]")?.focus();
    }, 0);
  };

  const handlePlanDirty = useCallback((dirty: boolean) => {
    setPlanDirty(dirty);
    if (!dirty) {
      setOperationError(current => (current === "先保存或放弃修改" ? "" : current));
    }
  }, []);

  const handleAction = async (action: DiscussAction) => {
    const current = detailRef.current;
    if (!current || mutating.current) return;
    try {
      switch (action) {
        case "start": {
          if (planDirty) {
            setPlanReloadOffered(false);
            setOperationError("先保存或放弃修改");
            selectTab("plan");
            return;
          }
          await mutate(
            "start",
            signal => startDiscussGroup(id, { expected_revision: current.plan_revision }, signal),
            { action: "start" },
          );
          return;
        }
        case "pause":
          await mutate("pause", signal => pauseDiscussGroup(id, signal), { action: "pause" });
          return;
        case "resume":
          if (current.stop_reason === "budget") {
            setDialog({ kind: "budget" });
            return;
          }
          await mutate(
            "resume",
            signal => resumeDiscussGroup(id, { add_budget: 0 }, signal),
            { action: "resume" },
          );
          return;
        case "continue":
          setDialog({ kind: "continue", title: "追加轮数" });
          return;
        case "rework": {
          if (current.pending_notes === 0) {
            setOperationError("先在群聊里写下你的意见，再点按意见返工");
            selectTab("chat");
            focusComposer();
            return;
          }
          setDialog({ kind: "continue", title: "按意见返工" });
          return;
        }
        case "accept": {
          const version = current.output?.version ?? current.output_version;
          if (!(await confirm({
            body: `接受第 ${version} 版成果，讨论到此结束？`,
            confirmLabel: "接受",
          }))) return;
          if (!isCurrentOwner()) return;
          await mutate("accept", signal => acceptDiscussGroup(id, signal), { action: "accept" });
          return;
        }
        case "close": {
          if (!(await confirm({
            body: "结束这个讨论群？结束后不能再继续。",
            confirmLabel: "结束",
          }))) return;
          if (!isCurrentOwner()) return;
          await mutate("close", signal => closeDiscussGroup(id, signal), { action: "close" });
          return;
        }
        case "export":
          await exportGroup();
          return;
        case "delete": {
          if (!(await confirm({
            body: "删除这个讨论群？讨论记录、成果与来源都会删掉，不能恢复。",
            confirmLabel: "删除",
            danger: true,
          }))) return;
          if (!isCurrentOwner()) return;
          const result = await mutate(
            "delete",
            signal => deleteDiscussGroup(id, signal),
            { action: "delete", refresh: false },
          );
          if (result) router.push(discussHref("/discuss", embedded));
          return;
        }
      }
    } catch {
      // mutate 已把中文文案放到顶栏下方；确认框取消不进入这里。
    }
  };

  const sendNote = useCallback(async (text: string) => {
    if (mutating.current || !isCurrentOwner()) {
      throw new Error("正在处理，请稍后再试。");
    }
    const request = beginMutation();
    if (!request) throw new Error("正在处理，请稍后再试。");
    beginRead();
    mutating.current = true;
    setBusy("note");
    try {
      const message = await addDiscussNote(id, { text }, request.signal);
      if (!request.isCurrent()) throw new Error("请求已取消，请重试。");
      const current = detailRef.current;
      if (current) {
        const pendingNotes = current.pending_notes + 1;
        const messages = applyPendingNotes(
          mergeDiscussMessages(current.messages, [message]),
          pendingNotes,
        );
        const value: DiscussDetail = { ...current, pending_notes: pendingNotes, messages };
        detailRef.current = value;
        setDetail(value);
      }
      setPollError("");
    } catch (cause) {
      if (!request.isCurrent()) throw new Error("请求已取消，请重试。");
      throw new Error(discussErrorMessage(cause));
    } finally {
      mutating.current = false;
      if (request.isCurrent()) setBusy("");
    }
  }, [beginMutation, beginRead, id, isCurrentOwner]);

  const tabs = wide ? RIGHT_TABS : ALL_TABS;
  const selectedTab = wide ? rightTab : tab;
  const selectedIndex = Math.max(0, tabs.findIndex(item => item.id === selectedTab));
  const tabProps = useRovingTabs(tabs.length, selectedIndex, (index) => {
    const next = tabs[index];
    if (next) selectTab(next.id);
  });

  if (loading && !detail) {
    return <LoadingState>正在打开讨论群…</LoadingState>;
  }

  if (!detail) {
    const back = <Link href={discussHref("/discuss", embedded)} className="inline-flex min-h-10 items-center gap-1 text-fs-13 text-[color:var(--ink2)]">
      <ArrowLeft size={14} />返回列表
    </Link>;
    if (readFailure?.missing) {
      return (
        <div className="space-y-4">
          <h1 className="text-fs-22 tracking-[.12em]">讨论群不存在</h1>
          {back}
        </div>
      );
    }
    if (readFailure?.blocked) {
      return (
        <div className="space-y-4">
          <p role="alert" className="text-fs-15 leading-[1.9] text-[color:var(--ink)]">
            {readFailure.message}
          </p>
          {back}
        </div>
      );
    }
    return (
      <ErrorNotice
        message={readFailure?.message ?? "暂时无法打开这个讨论群，请重新加载。"}
        retry={() => void loadInitial()}
      />
    );
  }

  const stopHint = discussStopHint(detail);
  const actions = discussActions(detail);
  const mainActions = actions.filter(action => MAIN_ACTIONS.includes(action));
  const sideActions = actions.filter(action => !MAIN_ACTIONS.includes(action));
  const hasOutput = detail.output_version >= 1;
  const readout = [
    detail.round === 0 ? "立项" : `第 ${detail.round} / ${detail.max_rounds} 轮`,
    `草莓 ${detail.spent_strawberries} / ${detail.budget_strawberries}`,
    hasOutput ? `成果第 ${detail.output_version} 版` : "",
  ].filter(Boolean).join(" · ");
  const actionText = (action: DiscussAction) =>
    busy === action ? BUSY_LABELS[action] ?? ACTION_LABELS[action] : ACTION_LABELS[action];

  return (
    <div className="flex flex-[1_0_auto] min-w-0 flex-col" data-discuss-room>
      <header className="min-w-0 shrink-0">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
          <Link
            href={discussHref("/discuss", embedded)}
            className="inline-flex min-h-10 shrink-0 items-center gap-1 text-fs-13 text-[color:var(--ink2)]"
          >
            <ArrowLeft size={14} />返回列表
          </Link>
          <h1 className="min-w-0 break-words text-fs-22 tracking-[.12em]">
            {detail.title || "讨论群"}
          </h1>
          <span className="tag">{discussStatusLabel(detail)}</span>
        </div>
        <p className="readout mt-1 break-words text-fs-13">{readout}</p>
        <div className="mt-4 flex min-w-0 flex-wrap items-center gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            {mainActions.map((action, index) => (
              <button
                key={action}
                type="button"
                className={`btn min-h-10 ${index === 0 ? "btn-primary" : ""}`}
                disabled={!!busy}
                onClick={() => void handleAction(action)}
              >
                {actionText(action)}
              </button>
            ))}
          </div>
          <div className="ml-auto flex min-w-0 flex-wrap items-center gap-2">
            {sideActions.map(action => (
              <button
                key={action}
                type="button"
                className={`btn min-h-10 ${action === "delete" ? "btn-danger" : "btn-quiet"}`}
                disabled={!!busy}
                onClick={() => void handleAction(action)}
              >
                {actionText(action)}
              </button>
            ))}
          </div>
        </div>
      </header>

      {operationError && (
        <div
          role="alert"
          className="mt-3 flex min-w-0 shrink-0 flex-col gap-2 border-l-2 border-[color:var(--seal)] pl-3 text-fs-13"
        >
          <p className="whitespace-pre-wrap break-words">{operationError}</p>
          {planReloadOffered && (
            <button
              type="button"
              className="btn btn-quiet min-h-10 self-start"
              disabled={!!busy}
              onClick={() => void reloadPlan()}
            >
              重新加载方案
            </button>
          )}
        </div>
      )}
      {pollError && (
        <p role="status" className="mt-2 shrink-0 break-words text-fs-12 text-[color:var(--ink2)]">{pollError}</p>
      )}
      {stopHint && (
        <p className="mt-3 shrink-0 border-l border-[color:var(--rule)] pl-3 text-fs-13 leading-[1.9] text-[color:var(--ink2)]">
          {stopHint}
        </p>
      )}
      {detail.last_error && (
        <p role="alert" className="mt-2 shrink-0 whitespace-pre-wrap break-words text-fs-12 text-[color:var(--seal)]">
          {detail.last_error}
        </p>
      )}

      <div ref={contentRef} className="mt-4 flex min-w-0 flex-[1_0_auto] flex-col">
        <div className={wide
          ? "grid flex-[1_1_0px] min-h-[320px] grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] gap-x-5"
          : "flex flex-[1_0_auto] flex-col"}
        >
          <nav
            role="tablist"
            aria-label="讨论群栏目"
            className={`flex min-w-0 border-b border-[color:var(--carve)]${wide ? " col-start-2 row-start-1" : ""}`}
          >
            {tabs.map((item, index) => {
              const selected = selectedTab === item.id;
              return (
                <button
                  key={item.id}
                  id={`discuss-tab-${item.id}`}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  aria-controls={`discuss-panel-${item.id}`}
                  {...tabProps(index)}
                  onClick={() => selectTab(item.id)}
                  className={`min-h-10 min-w-0 flex-1 border-b px-1 py-3 text-fs-13 ${selected
                    ? "border-[color:var(--ink)] text-[color:var(--ink)]"
                    : "border-transparent text-[color:var(--ink2)]"}`}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>

          <section
            id="discuss-panel-chat"
            aria-label="群聊"
            role={wide ? undefined : "tabpanel"}
            aria-labelledby={wide ? undefined : "discuss-tab-chat"}
            hidden={!wide && tab !== "chat"}
            className={wide
              ? "col-start-1 row-start-1 row-span-2 flex min-h-0 min-w-0 flex-col"
              : "mt-4 flex min-w-0 flex-[1_0_auto] flex-col"}
          >
            <div className="flex min-w-0 flex-[1_0_auto] flex-col">
              <DiscussTimeline
                messages={detail.messages}
                members={detail.members}
                status={detail.status}
                sources={sourceMap}
                active={wide || tab === "chat"}
                onOpenDraft={(version) => {
                  setDraftVersion(version);
                  setDraftNonce(value => value + 1);
                  selectTab("output");
                }}
              />
              <DiscussComposer
                status={detail.status}
                pendingNotes={detail.pending_notes}
                busy={!!busy}
                onSend={sendNote}
              />
            </div>
          </section>

          <div
            className={`min-h-0 flex-[1_0_auto]${wide ? " col-start-2 row-start-2 overflow-y-auto pt-4" : " mt-4"}`}
            hidden={!wide && tab === "chat"}
          >
            <div
              id="discuss-panel-plan"
              role="tabpanel"
              aria-labelledby="discuss-tab-plan"
              hidden={wide ? rightTab !== "plan" : tab !== "plan"}
              className="min-w-0"
            >
              <DiscussPlanPanel
                key={`plan-${planKey}`}
                owner={owner}
                detail={detail}
                catalog={catalog}
                catalogError={catalogError}
                busy={!!busy}
                onReloadCatalog={() => void loadCatalog()}
                onUpdated={next => publishDetail(next)}
                onDirtyChange={handlePlanDirty}
              />
            </div>

            <div
              id="discuss-panel-output"
              role="tabpanel"
              aria-labelledby="discuss-tab-output"
              hidden={wide ? rightTab !== "output" : tab !== "output"}
              className="min-w-0"
            >
              <DiscussOutputPanel
                key={`output-${draftNonce}`}
                owner={owner}
                groupId={id}
                detail={detail}
                sources={sourceMap}
                requestedVersion={draftVersion}
                onExport={() => void exportGroup()}
                exportBusy={!!busy}
                onContentLoaded={setOutputContent}
              />
            </div>

            <div
              id="discuss-panel-sources"
              role="tabpanel"
              aria-labelledby="discuss-tab-sources"
              hidden={wide ? rightTab !== "sources" : tab !== "sources"}
              className="min-w-0"
            >
              <DiscussSourcesPanel
                sources={sources}
                loading={sourcesLoading}
                error={sourcesError}
                onRetry={() => void loadSources()}
                selectedOutputContent={outputContent}
                hasOutput={hasOutput}
              />
            </div>
          </div>
        </div>
      </div>

      {dialog?.kind === "budget" && (
        <DiscussBudgetDialog
          detail={detail}
          onClose={() => setDialog(null)}
          onConfirm={async (addBudget) => {
            await mutate(
              "resume",
              signal => resumeDiscussGroup(id, { add_budget: addBudget }, signal),
              { action: "resume" },
            );
          }}
        />
      )}
      {dialog?.kind === "continue" && (
        <DiscussContinueDialog
          detail={detail}
          title={dialog.title}
          onClose={() => setDialog(null)}
          onConfirm={async (input: DiscussContinueInput) => {
            if (dialog.title === "按意见返工") {
              await mutate(
                "rework",
                signal => continueDiscussGroup(id, input, signal),
                { action: "rework" },
              );
            } else {
              await mutate(
                "continue",
                signal => continueDiscussGroup(id, input, signal),
                { action: "continue" },
              );
            }
          }}
        />
      )}
    </div>
  );
}
