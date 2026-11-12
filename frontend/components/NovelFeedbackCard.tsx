"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ApiError } from "@/lib/agents";
import { useConfirm } from "@/components/ConfirmDialog";
import { displayNovelChapterTitle, novelErrorMessage } from "@/lib/novels";
import {
  getNovelFeedback,
  redoNovelFeedbackPlan,
  sendNovelFeedbackNote,
  type NovelFeedbackView,
} from "@/lib/novelFeedback";

export interface NovelFeedbackCardProps {
  feedbackId: string;
  onOpenNovel?: (path: string) => void;
  initialView?: NovelFeedbackView;
}

type FeedbackRead =
  | { kind: "ready"; feedbackId: string; attempt: number; view: NovelFeedbackView }
  | { kind: "missing"; feedbackId: string; attempt: number }
  | { kind: "error"; feedbackId: string; attempt: number; message: string };

type BusyKind = "note" | "confirm" | "redo";

interface ActionError {
  section: "plan" | "chapters";
  message: string;
}

type RedoCost = NonNullable<NovelFeedbackView["book"]>["redo_cost"];

function redoCostSentence(cost: RedoCost | undefined) {
  if (cost === "own_model") {
    return "这本书的主编用的是你自己的模型，重新定稿不扣草莓，但会用掉你自己的模型额度。";
  }
  if (cost === "free") {
    return "这次重新定稿不扣草莓。";
  }
  return "重新定稿会再调用一次编辑部，按实际用量扣草莓。";
}

function redoAvailable(view: NovelFeedbackView) {
  const book = view.book;
  return Boolean(
    view.current_plan.trim()
    && view.plan_chapter !== null
    && !view.redo_started_at
    && book !== null
    && book.status === "awaiting_plan"
    && book.awaiting_chapter === view.plan_chapter
    && book.automation === "per_chapter",
  );
}

export default function NovelFeedbackCard({
  feedbackId,
  onOpenNovel,
  initialView,
}: NovelFeedbackCardProps) {
  const confirm = useConfirm();
  const notesFullId = useId();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<FeedbackRead | null>(() => (
    initialView ? { kind: "ready", feedbackId, attempt: 0, view: initialView } : null
  ));
  const [busy, setBusy] = useState<BusyKind | null>(null);
  const [actionError, setActionError] = useState<ActionError | null>(null);
  const busyRef = useRef(false);
  const actionRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    actionRef.current = controller;
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (initialView) return;
    const controller = new AbortController();
    getNovelFeedback(feedbackId, controller.signal)
      .then(view => {
        if (controller.signal.aborted) return;
        setResult({ kind: "ready", feedbackId, attempt, view });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404 && error.message === "修改意见不存在") {
          setResult({ kind: "missing", feedbackId, attempt });
          return;
        }
        const message = error instanceof ApiError ? novelErrorMessage(error) : "修改意见暂时读不到";
        setResult({ kind: "error", feedbackId, attempt, message });
      });
    return () => controller.abort();
  }, [attempt, feedbackId, initialView]);

  const current = result && result.feedbackId === feedbackId && result.attempt === attempt
    ? result
    : null;

  if (current === null) {
    return <p role="status" className="ceramic-card w-[420px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">正在读取修改意见…</p>;
  }

  if (current.kind === "missing") {
    return <p role="status" className="ceramic-card w-[420px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">修改意见已不存在</p>;
  }

  if (current.kind === "error") {
    return <div role="status" className="ceramic-card w-[420px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">
      <p>{current.message}</p>
      <button type="button" className="btn btn-quiet mt-2 min-h-10" onClick={() => setAttempt(value => value + 1)}>重新读取</button>
    </div>;
  }

  const view = current.view;
  const book = view.book;
  const note = view.note;
  const title = view.book_title.trim() || "未命名小说";

  const openNovelAt = (novelId: string) => {
    onOpenNovel?.("/novels/" + novelId + "?embed=1");
  };

  const sendNote = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setActionError(null);
    setBusy("note");
    const signal = actionRef.current?.signal;
    try {
      const next = await sendNovelFeedbackNote(feedbackId, signal);
      if (signal?.aborted) return;
      setResult({ kind: "ready", feedbackId, attempt, view: next });
      if (next.note !== null) setActionError(null);
      busyRef.current = false;
      setBusy(null);
    } catch (error) {
      if (signal?.aborted) return;
      setActionError({ section: "chapters", message: novelErrorMessage(error) });
      try {
        const refreshed = await getNovelFeedback(feedbackId, signal);
        if (signal?.aborted) return;
        setResult({ kind: "ready", feedbackId, attempt, view: refreshed });
        if (refreshed.note !== null) setActionError(null);
      } catch {
        if (signal?.aborted) return;
      }
      busyRef.current = false;
      setBusy(null);
    }
  };

  const sendRedo = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setActionError(null);
    setBusy("confirm");
    const signal = actionRef.current?.signal;
    let refreshed: NovelFeedbackView;
    try {
      refreshed = await getNovelFeedback(feedbackId, signal);
    } catch (error) {
      if (signal?.aborted) return;
      setActionError({ section: "plan", message: novelErrorMessage(error) });
      busyRef.current = false;
      setBusy(null);
      return;
    }
    if (signal?.aborted) return;
    setResult({ kind: "ready", feedbackId, attempt, view: refreshed });
    const chapter = refreshed.plan_chapter;
    if (!redoAvailable(refreshed) || chapter === null) {
      busyRef.current = false;
      setBusy(null);
      return;
    }
    const confirmed = await confirm({ title: `重新定稿第 ${chapter} 章细纲`, body: `编辑部会拿原来的讨论材料加上这张卡上的要求，重新写一版第 ${chapter} 章细纲（看不到现在这一版，是否照改由编辑部判断）。${redoCostSentence(refreshed.book?.redo_cost)}完成后新细纲仍会停下来等你确认。`, confirmLabel: "重新定稿" });
    if (signal?.aborted) return;
    if (!confirmed) {
      busyRef.current = false;
      setBusy(null);
      return;
    }
    setBusy("redo");
    try {
      const next = await redoNovelFeedbackPlan(feedbackId, signal);
      if (signal?.aborted) return;
      setResult({ kind: "ready", feedbackId, attempt, view: next });
      if (next.redo_started_at) setActionError(null);
      busyRef.current = false;
      setBusy(null);
    } catch (error) {
      if (signal?.aborted) return;
      setActionError({ section: "plan", message: novelErrorMessage(error) });
      try {
        const after = await getNovelFeedback(feedbackId, signal);
        if (signal?.aborted) return;
        setResult({ kind: "ready", feedbackId, attempt, view: after });
        if (after.redo_started_at) setActionError(null);
      } catch {
        if (signal?.aborted) return;
      }
      busyRef.current = false;
      setBusy(null);
    }
  };

  const planChapter = view.plan_chapter;
  let planTag = "";
  let planDescription = "";
  let planActionable = false;
  if (view.current_plan.trim() && planChapter !== null) {
    const chapter = planChapter;
    if (view.redo_started_at) {
      planTag = "已发起重新定稿";
      if (!book) {
        planDescription = "这本书已经删除。";
      } else if (book.redo_pending && (book.status === "running" || book.status === "setup_running")) {
        planDescription = `编辑部正在带着这些要求重新定稿第 ${chapter} 章细纲，完成后会停下来等你确认。卡片不会自动更新，刷新页面可以看到最新进展。`;
      } else if (book.redo_pending && book.status === "paused") {
        planDescription = "重新定稿还没有完成：这本书暂停了，请到书斋查看原因；恢复写作后会接着重新定稿。";
      } else if (book.redo_pending && book.status === "failed") {
        planDescription = "重新定稿没有完成：这本书处于失败状态，不能再继续写。";
      } else {
        planDescription = `已经带着这些要求重新定稿过第 ${chapter} 章细纲。`;
        if (book.status === "awaiting_plan" && book.awaiting_chapter === chapter) {
          planDescription += "新细纲在书斋里等你确认。";
        }
      }
    } else if (!book) {
      planDescription = "这本书已经删除。";
    } else if (redoAvailable(view)) {
      planActionable = true;
      planDescription = `重新定稿会让编辑部拿原来的讨论材料加上这些要求，重新写一版第 ${chapter} 章细纲；它看不到你现在看到的这一版，是否照改由编辑部判断。${redoCostSentence(view.book?.redo_cost)}只想改几处的话，也可以在书斋里直接改细纲，再点「改完批准」（批准后照常开始写这一章）。`;
    } else if (book.status === "awaiting_plan" && book.awaiting_chapter === chapter) {
      planDescription = "这本书现在不是逐章确认，重新定稿后会直接开始写正文、不会停下来等你确认；这一项请到书斋里处理。";
    } else if (book.status === "failed") {
      planDescription = "这本书处于失败状态，不能再继续写，这一项不能再用。";
    } else if (book.plan_row_status === "awaiting_plan_approval" && book.status === "paused") {
      planDescription = `第 ${chapter} 章细纲还在等你确认，但这本书暂停了；恢复写作、回到等你确认后可以再用这一项。`;
    } else if (book.plan_row_status === "awaiting_plan_approval" && (book.status === "running" || book.status === "setup_running")) {
      planDescription = `第 ${chapter} 章细纲还在等你确认，但书斋正在处理这本书；处理完、回到等你确认后可以再用这一项。`;
    } else if (book.plan_row_status === "planning" && (book.status === "running" || book.status === "setup_running")) {
      planDescription = `书斋正在重新定稿第 ${chapter} 章细纲；完成后如果仍在等你确认这一章，可以再用这一项。`;
    } else if (book.plan_row_status === "planning" && book.status === "paused") {
      planDescription = `书斋重新定稿第 ${chapter} 章细纲时暂停了；恢复写作、回到等你确认后可以再用这一项。`;
    } else {
      planDescription = `第 ${chapter} 章细纲已经不在等你确认了，这一项不能再用。`;
    }
  }

  const awaitingChapter = book?.awaiting_chapter ?? null;
  const maxChapters = book?.max_chapters ?? null;
  const finalChapter = awaitingChapter !== null && (
    Boolean(book?.awaiting_is_final)
    || (maxChapters !== null && awaitingChapter >= maxChapters)
  );
  const responseOf = (value: string | null | undefined) => value || "（没有写回应）";

  let chaptersTag = "";
  let chaptersDescription = "";
  let chaptersDescriptionId: string | undefined;
  let chaptersResponse = "";
  let chaptersButton: "note" | "full" | null = null;
  if (view.next_chapters.trim()) {
    if (note && note.status === "delivered") {
      chaptersTag = note.delivered_chapter !== null ? `已下发到第 ${note.delivered_chapter} 章` : "编辑部已回应";
      chaptersResponse = note.adopted === true
        ? `编辑部采纳：${responseOf(note.response)}`
        : note.adopted === false
          ? `编辑部没有采纳：${responseOf(note.response)}`
          : `编辑部的回应：${responseOf(note.response)}`;
    } else if (note && note.status === "pending" && note.planned_chapter !== null && book) {
      chaptersTag = "待下发";
      chaptersDescription = book.status === "failed"
        ? `编辑部已经在第 ${note.planned_chapter} 章细纲里读到这条要求，但这本书处于失败状态，不能再继续写，这条留言不会被下发。`
        : `编辑部已经在第 ${note.planned_chapter} 章细纲里读到这条要求；这一章写完后，这里会记为已下发。`;
      if (note.planned_adopted !== null || Boolean(note.planned_response)) {
        chaptersResponse = note.planned_adopted === true
          ? `编辑部采纳：${responseOf(note.planned_response)}`
          : note.planned_adopted === false
            ? `编辑部没有采纳：${responseOf(note.planned_response)}`
            : `编辑部的回应：${responseOf(note.planned_response)}`;
      }
    } else if (note) {
      chaptersTag = "待下发";
      if (!book) {
        chaptersDescription = "这本书已经删除。";
      } else if (book.status === "completed") {
        chaptersDescription = "这本书已经完结，这条留言不会再被读到。";
      } else if (book.status === "failed") {
        chaptersDescription = "这本书处于失败状态，这条留言不会再被读到。";
      } else if (book.status === "awaiting_end") {
        chaptersDescription = "这本书在等你确认完结；只有选择再写几章，编辑部才会读到这条要求。";
      } else if (book.status === "awaiting_plan" && awaitingChapter !== null && finalChapter) {
        chaptersDescription = `第 ${awaitingChapter} 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。`;
      } else if (book.status === "awaiting_plan" && awaitingChapter !== null) {
        chaptersDescription = `第 ${awaitingChapter + 1} 章规划细纲时，编辑部会读到这条要求。`;
      } else {
        chaptersDescription = "编辑部会在下一次为新的一章规划细纲时读到这条要求；那一章写完后，这里会显示编辑部的回应。";
      }
    } else if (!book) {
      chaptersDescription = "这本书已经删除。";
    } else if (book.status === "completed") {
      chaptersDescription = "这本书已经完结，编辑部不会再读留言。";
    } else if (book.status === "failed") {
      chaptersDescription = "这本书处于失败状态，编辑部不会再读留言。";
    } else if (book.pending_notes >= 5) {
      chaptersDescription = "这本书的待下发留言已满 5 条，等编辑部用掉一些再交。";
      chaptersDescriptionId = notesFullId;
      chaptersButton = "full";
    } else {
      if (book.pending_notes > 0) {
        chaptersDescription = `这本书现在有 ${book.pending_notes} 条待下发留言（最多 5 条，包括书斋里留的和别的卡片交出的）。`;
      }
      if (book.status === "awaiting_end") {
        chaptersDescription += "这本书在等你确认完结；只有选择再写几章，编辑部才会读到这条要求。";
      } else if (book.status === "awaiting_plan" && awaitingChapter !== null && finalChapter) {
        chaptersDescription += `第 ${awaitingChapter} 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。`;
      } else if (book.status === "awaiting_plan" && awaitingChapter !== null) {
        chaptersDescription += `第 ${awaitingChapter} 章细纲已经出来了，这条要求要到第 ${awaitingChapter + 1} 章规划细纲时编辑部才会读到；想让第 ${awaitingChapter} 章就照做，可以在书斋里直接改第 ${awaitingChapter} 章细纲。`;
      } else {
        chaptersDescription += "编辑部只在下一次为新的一章规划细纲时参考一次（正在规划、正在重新定稿或已经出了细纲的那一章读不到），不会长期生效。";
      }
      chaptersDescription += "交出后不能撤回。";
      chaptersButton = "note";
    }
  }

  const showBottom = Boolean(view.novel_id && book && onOpenNovel);
  const showBottomHint = note !== null || Boolean(view.redo_started_at) || planActionable;

  return <div className="ceramic-card w-[420px] max-w-full overflow-hidden">
    <div className="px-4 py-3 text-fs-15">修改意见 · 《{title}》</div>

    {view.current_plan.trim() && planChapter !== null && <section className="border-t px-4 py-3" style={{ borderColor: "var(--carve)" }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-fs-12 text-[color:var(--ink2)]">第 {planChapter} 章细纲</span>
        {planTag && <span className="tag">{planTag}</span>}
      </div>
      <p className="mt-1 whitespace-pre-wrap break-words text-fs-13">{view.current_plan}</p>
      <p className="mt-2 break-words text-fs-12 text-[color:var(--ink2)]">{planDescription}</p>
      {planActionable && <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn min-h-10"
          disabled={busy !== null}
          onClick={() => void sendRedo()}
        >
          {busy === "redo" ? "正在发起重新定稿…" : "带着这些要求重新定稿"}
        </button>
        {onOpenNovel && view.novel_id && <button
          type="button"
          className="btn btn-quiet min-h-10"
          onClick={() => openNovelAt(view.novel_id as string)}
        >
          去书斋改细纲
        </button>}
      </div>}
      {actionError?.section === "plan" && <p role="alert" className="mt-2 break-words text-fs-13 text-[color:var(--seal)]">{actionError.message}</p>}
    </section>}

    {view.next_chapters.trim() && <section className="border-t px-4 py-3" style={{ borderColor: "var(--carve)" }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-fs-12 text-[color:var(--ink2)]">以后的章节</span>
        {chaptersTag && <span className="tag">{chaptersTag}</span>}
      </div>
      <p className="mt-1 whitespace-pre-wrap break-words text-fs-13">{view.next_chapters}</p>
      {chaptersDescription && <p id={chaptersDescriptionId} className="mt-2 break-words text-fs-12 text-[color:var(--ink2)]">{chaptersDescription}</p>}
      {chaptersResponse && <p className="mt-1 break-words text-fs-12 text-[color:var(--ink2)]">{chaptersResponse}</p>}
      {chaptersButton && <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn btn-primary min-h-10"
          disabled={chaptersButton === "full" || busy !== null}
          aria-describedby={chaptersButton === "full" ? chaptersDescriptionId : undefined}
          onClick={() => void sendNote()}
        >
          {busy === "note" ? "正在交给编辑部…" : "交给编辑部"}
        </button>
      </div>}
      {actionError?.section === "chapters" && <p role="alert" className="mt-2 break-words text-fs-13 text-[color:var(--seal)]">{actionError.message}</p>}
    </section>}

    {view.written.length > 0 && <section className="border-t px-4 py-3" style={{ borderColor: "var(--carve)" }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-fs-12 text-[color:var(--ink2)]">已写好的章节</span>
      </div>
      <ol className="mt-1 space-y-1 text-fs-13">
        {view.written.map((item, index) => (
          <li key={index} className="break-words">第 {item.chapter} 章 {displayNovelChapterTitle(item.title) || "待定章名"}：{item.issue}</li>
        ))}
      </ol>
      <p className="mt-2 break-words text-fs-12 text-[color:var(--ink2)]">这些章节不会自动修改，要改就在书斋里打开这一章，点「改稿」自己改。改最新写好的一章会重新归档（再调用一次档案员，可能扣草莓），完成前不会开始下一章，已经出来、等你确认的下一章细纲也不会跟着重做。改较早的章节会把它后面已写好的章永久标成「待复核」，有待复核章节的书不能做成片；故事圣经和章节摘要也不会重算，编辑部之后仍按旧记录规划。可以再交一条留言说明改了什么，但留言只在下一次规划细纲时参考一次。</p>
    </section>}

    {showBottom && <div className="border-t px-4 py-3" style={{ borderColor: "var(--carve)" }}>
      {showBottomHint && <p className="mb-2 break-words text-fs-12 text-[color:var(--ink2)]">书斋如果之前已经开着这本书，要回到书架重新打开它，才会看到最新的细纲和留言。{view.redo_started_at ? "在旧页面上点「批准（原样）」会直接批准你还没看过的新细纲，点「改完批准」会用旧页面里的内容覆盖新细纲。" : ""}</p>}
      <button
        type="button"
        className="btn btn-quiet min-h-10"
        onClick={() => openNovelAt(view.novel_id as string)}
      >
        在书斋打开
      </button>
    </div>}
  </div>;
}
