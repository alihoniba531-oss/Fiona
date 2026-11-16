"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/agents";
import { getDiscussTaskCard, type DiscussTaskCardView } from "@/lib/discuss";
import { discussStatusLabel } from "@/lib/discussLogic";

export interface DiscussTaskCardProps {
  taskId: string;
  onOpenDiscuss?: (path: string) => void;
}

type TaskView =
  | { status: "loading" }
  | { status: "ready"; card: DiscussTaskCardView }
  | { status: "missing" }
  | { status: "error" };

interface TaskResult {
  taskId: string;
  attempt: number;
  view: TaskView;
}

/** 建议行：两项都有时用分隔符连成一行，只有一项时只写一项。 */
function suggestionText(maxRounds: number | null, budget: number | null): string {
  if (maxRounds !== null && budget !== null) {
    return `建议 ${maxRounds} 轮 · 预算 ${budget} 颗`;
  }
  if (maxRounds !== null) return `建议 ${maxRounds} 轮`;
  if (budget !== null) return `预算 ${budget} 颗`;
  return "";
}

export default function DiscussTaskCard({ taskId, onOpenDiscuss }: DiscussTaskCardProps) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<TaskResult>(() => ({
    taskId,
    attempt: 0,
    view: { status: "loading" },
  }));

  useEffect(() => {
    const controller = new AbortController();
    getDiscussTaskCard(taskId, controller.signal)
      .then(card => {
        if (controller.signal.aborted) return;
        setResult({ taskId, attempt, view: { status: "ready", card } });
      })
      .catch(error => {
        if (controller.signal.aborted) return;
        const missing = error instanceof ApiError && (error.status === 404 || error.status === 403);
        setResult({ taskId, attempt, view: { status: missing ? "missing" : "error" } });
      });
    return () => controller.abort();
  }, [attempt, taskId]);

  const view: TaskView = result.taskId === taskId && result.attempt === attempt
    ? result.view
    : { status: "loading" };

  if (view.status !== "ready") {
    const text = view.status === "loading" ? "正在读取任务卡…"
      : view.status === "missing" ? "任务卡已不存在"
      : "任务卡暂时读不到";
    if (view.status === "error") {
      return <div role="status" className="ceramic-card w-[340px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">
        <p>{text}</p>
        <button
          type="button"
          className="btn btn-quiet mt-2 min-h-10"
          onClick={() => setAttempt(value => value + 1)}
        >
          重新读取
        </button>
      </div>;
    }
    return <p role="status" className="ceramic-card w-[340px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">{text}</p>;
  }

  const card = view.card;
  const group = card.group;

  if (group) {
    return <div className="ceramic-card w-[340px] max-w-full overflow-hidden">
      <div className="border-b px-4 py-3 text-fs-15" style={{ borderColor: "var(--carve)" }}>
        已建群《{group.title}》 · {discussStatusLabel(group)}
      </div>
      {onOpenDiscuss && <div className="px-4 pb-4 pt-3">
        <button
          type="button"
          onClick={() => onOpenDiscuss("/discuss/" + group.id + "?embed=1")}
          className="btn btn-primary min-h-10"
        >
          打开
        </button>
      </div>}
    </div>;
  }

  const excerpt = card.request.length > 80 ? `${card.request.slice(0, 80)}……` : card.request;
  const suggestion = suggestionText(card.max_rounds, card.budget_strawberries);

  return <div className="ceramic-card w-[340px] max-w-full overflow-hidden">
    <div className="border-b px-4 py-3 text-fs-15" style={{ borderColor: "var(--carve)" }}>讨论群任务</div>
    {excerpt && <p className="whitespace-pre-wrap break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">{excerpt}</p>}
    {suggestion && <p className="px-4 pb-3 text-fs-13 text-[color:var(--ink2)]">{suggestion}</p>}
    {onOpenDiscuss && <div className="px-4 pb-4">
      <button
        type="button"
        onClick={() => onOpenDiscuss("/discuss/new?embed=1&task=" + card.id)}
        className="btn btn-primary min-h-10"
      >
        去讨论群建群
      </button>
      <p className="mt-2 break-words text-fs-12 text-[color:var(--ink2)]">建群后主持人立项会调用模型并扣草莓。</p>
    </div>}
  </div>;
}
