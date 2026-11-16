"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ApiError } from "@/lib/agents";
import {
  getDiscussNoteCard,
  sendDiscussNoteCard,
  type DiscussNoteCardView,
} from "@/lib/discuss";
import { discussStatusLabel } from "@/lib/discussLogic";

export interface DiscussNoteCardProps {
  noteId: string;
  onOpenDiscuss?: (path: string) => void;
}

type NoteRead =
  | { kind: "ready"; noteId: string; attempt: number; view: DiscussNoteCardView }
  | { kind: "missing"; noteId: string; attempt: number }
  | { kind: "error"; noteId: string; attempt: number };

export default function DiscussNoteCard({ noteId, onOpenDiscuss }: DiscussNoteCardProps) {
  const pendingHintId = useId();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<NoteRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const actionRef = useRef<AbortController | null>(null);

  useEffect(() => () => actionRef.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    getDiscussNoteCard(noteId, controller.signal)
      .then(view => {
        if (controller.signal.aborted) return;
        setResult({ kind: "ready", noteId, attempt, view });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && (error.status === 404 || error.status === 403)) {
          setResult({ kind: "missing", noteId, attempt });
          return;
        }
        setResult({ kind: "error", noteId, attempt });
      });
    return () => controller.abort();
  }, [attempt, noteId]);

  const current = result && result.noteId === noteId && result.attempt === attempt
    ? result
    : null;

  if (current === null) {
    return <p role="status" className="ceramic-card w-[420px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">正在读取意见卡…</p>;
  }

  if (current.kind === "missing") {
    return <p role="status" className="ceramic-card w-[420px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">意见卡已不存在</p>;
  }

  if (current.kind === "error") {
    return <div role="status" className="ceramic-card w-[420px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">
      <p>意见卡暂时读不到</p>
      <button
        type="button"
        className="btn btn-quiet mt-2 min-h-10"
        onClick={() => setAttempt(value => value + 1)}
      >
        重新读取
      </button>
    </div>;
  }

  const view = current.view;
  const group = view.group;
  const title = (group ? group.title : view.group_title).trim() || "未命名讨论群";
  const sent = view.sent_at !== null || view.message !== null;
  const message = view.message;
  const ended = group !== null && (group.status === "closed" || group.status === "failed");
  const pendingFull = group !== null && group.pending_notes >= 5;

  const openGroup = () => {
    if (group && onOpenDiscuss) onOpenDiscuss("/discuss/" + group.id + "?embed=1");
  };

  const send = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    const controller = new AbortController();
    actionRef.current = controller;
    const signal = controller.signal;
    try {
      const next = await sendDiscussNoteCard(noteId, signal);
      if (signal.aborted) return;
      setResult({ kind: "ready", noteId, attempt, view: next });
    } catch (error) {
      if (signal.aborted) return;
      const message = error instanceof ApiError && error.message
        ? error.message
        : "送进群失败，请稍后再试。";
      setActionError(message);
      try {
        const next = await getDiscussNoteCard(noteId, signal);
        if (signal.aborted) return;
        setResult({ kind: "ready", noteId, attempt, view: next });
      } catch {
        if (signal.aborted) return;
      }
    } finally {
      busyRef.current = false;
      if (!signal.aborted) setBusy(false);
    }
  };

  return <div className="ceramic-card w-[420px] max-w-full overflow-hidden">
    <div className="border-b px-4 py-3" style={{ borderColor: "var(--carve)" }}>
      <p className="text-fs-15">给《{title}》的意见</p>
      {group && <p className="mt-1 text-fs-12 text-[color:var(--ink2)]">{discussStatusLabel(group)}</p>}
    </div>

    <p className="whitespace-pre-wrap break-words px-4 py-3 text-fs-13">{view.text}</p>

    <div className="border-t px-4 py-3" style={{ borderColor: "var(--carve)" }}>
      {sent ? (
        <p className="break-words text-fs-13">
          已送进群{message ? (message.consumed ? "，主持人已读到" : "，主持人还没读到") : ""}
        </p>
      ) : group === null ? (
        <p className="break-words text-fs-13 text-[color:var(--ink2)]">这个讨论群已经删除。</p>
      ) : ended ? (
        <p className="break-words text-fs-13 text-[color:var(--ink2)]">这个群已经结束，不能再插话。</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn btn-primary min-h-10"
              disabled={busy || pendingFull}
              aria-describedby={pendingFull ? pendingHintId : undefined}
              onClick={() => void send()}
            >
              {busy ? "正在送进群…" : "送进群"}
            </button>
            {pendingFull && <span id={pendingHintId} className="break-words text-fs-12 text-[color:var(--ink2)]">
              还有 5 条插话没被读到，等主持人回应后再送。
            </span>}
          </div>
          {group.status === "done" && <p className="mt-2 break-words text-fs-12 text-[color:var(--ink2)]">
            送出后还要到群里点『按意见返工』才会继续。
          </p>}
        </>
      )}
      {actionError && <p role="alert" className="mt-2 break-words text-fs-13 text-[color:var(--seal)]">{actionError}</p>}
    </div>

    {group && onOpenDiscuss && <div className="border-t px-4 py-3" style={{ borderColor: "var(--carve)" }}>
      <button type="button" className="btn btn-quiet min-h-10" onClick={openGroup}>
        打开讨论群
      </button>
    </div>}
  </div>;
}
