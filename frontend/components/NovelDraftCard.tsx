"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/agents";
import { getNovelDraft, type NovelDraft } from "@/lib/novels";

export interface NovelDraftCardProps {
  draftId: string;
  onOpenNovel?: (path: string) => void;
}

type DraftView =
  | { status: "loading" }
  | { status: "ready"; draft: NovelDraft }
  | { status: "missing" }
  | { status: "error" };

interface DraftResult {
  draftId: string;
  view: DraftView;
}

export default function NovelDraftCard({ draftId, onOpenNovel }: NovelDraftCardProps) {
  const [result, setResult] = useState<DraftResult>(() => ({ draftId, view: { status: "loading" } }));

  useEffect(() => {
    const controller = new AbortController();
    getNovelDraft(draftId, controller.signal)
      .then(draft => {
        if (controller.signal.aborted) return;
        setResult({ draftId, view: { status: "ready", draft } });
      })
      .catch(error => {
        if (controller.signal.aborted) return;
        const missing = error instanceof ApiError && (error.status === 404 || error.status === 403);
        setResult({ draftId, view: { status: missing ? "missing" : "error" } });
      });
    return () => controller.abort();
  }, [draftId]);

  const view: DraftView = result.draftId === draftId ? result.view : { status: "loading" };
  if (view.status !== "ready") {
    const text = view.status === "loading" ? "正在读取草稿…"
      : view.status === "missing" ? "草稿已不存在"
      : "草稿暂时读不到";
    return <p role="status" className="ceramic-card w-[340px] max-w-full break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">{text}</p>;
  }

  const draft = view.draft;
  const title = draft.title.trim() || "未命名小说";
  if (draft.novel_id) {
    return <div className="ceramic-card w-[340px] max-w-full overflow-hidden">
      <div className="border-b px-4 py-3 text-fs-15 font-medium" style={{ borderColor: "var(--carve)" }}>已建书《{title}》</div>
      {onOpenNovel && <div className="px-4 pb-4 pt-3">
        <button type="button" onClick={() => onOpenNovel("/novels/" + draft.novel_id + "?embed=1")} className="btn btn-primary min-h-10">打开</button>
      </div>}
    </div>;
  }

  const excerpt = draft.seed_idea.length > 80 ? `${draft.seed_idea.slice(0, 80)}…` : draft.seed_idea;
  return <div className="ceramic-card w-[340px] max-w-full overflow-hidden">
    <div className="border-b px-4 py-3 text-fs-15 font-medium" style={{ borderColor: "var(--carve)" }}>书斋草稿 · 《{title}》</div>
    {excerpt && <p className="break-words px-4 py-3 text-fs-13 text-[color:var(--ink2)]">{excerpt}</p>}
    {onOpenNovel && <div className="px-4 pb-4">
      <button type="button" onClick={() => onOpenNovel("/novels/new?embed=1&draft=" + draft.id)} className="btn btn-primary min-h-10">去书斋建书</button>
    </div>}
  </div>;
}
