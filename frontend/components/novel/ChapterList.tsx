"use client";

import { CircleAlert, Clock3, Flag, MoveHorizontal, Pencil, TrendingUp, type LucideIcon } from "lucide-react";
import { displayNovelChapterTitle, type NovelChapterSummary } from "@/lib/novels";
import { EmptyState } from "./NovelStates";

const flagLabels: Record<string, { icon: LucideIcon; label: string }> = {
  review_unresolved: { icon: CircleAlert, label: "审校两轮未通过" },
  length_out_of_range: { icon: MoveHorizontal, label: "长度超出" },
  deviation: { icon: TrendingUp, label: "偏离细纲" },
  locked_conflict: { icon: Flag, label: "与锁定设定冲突" },
  edited_by_user: { icon: Pencil, label: "你改过" },
  stale: { icon: Clock3, label: "待复核" },
};

export default function ChapterList({ chapters, selectedChapter, writingChapter, onSelect }: {
  chapters: NovelChapterSummary[]; selectedChapter: number | null; writingChapter?: number | null; onSelect: (chapter: number) => void;
}) {
  return <div className="min-w-0"><h2 className="mb-4 tracking-[.24em]">目录</h2>
    {!chapters.length && <EmptyState>第一章写好后会出现在这里。</EmptyState>}
    <ol className="space-y-1">{chapters.map(chapter => {
      const flags = new Set(chapter.flags ?? []);
      if (chapter.status === "stale") flags.add("stale");
      if (chapter.edited_by_user) flags.add("edited_by_user");
      return <li key={chapter.chapter}><button type="button" onClick={() => onSelect(chapter.chapter)} aria-current={selectedChapter === chapter.chapter ? "true" : undefined}
        className={`min-h-10 w-full min-w-0 border-l px-3 py-3 text-left text-sm ${selectedChapter === chapter.chapter ? "border-[var(--ink)] text-[var(--ink)]" : "border-transparent text-[var(--ink2)]"}`}>
        <span className="block break-words"><span className="readout">第 {chapter.chapter} 章</span>　{displayNovelChapterTitle(chapter.title) || "待定章名"}</span>
        {flags.size > 0 && <span className="mt-1 flex flex-wrap gap-2">{[...flags].filter(flag => flagLabels[flag]).map(flag => {
          const Icon = flagLabels[flag].icon;
          return <span key={flag} title={flagLabels[flag].label} aria-label={flagLabels[flag].label} className="inline-flex min-w-0 items-center gap-1 break-words text-xs"><Icon aria-hidden="true" size={13} className="shrink-0" /><span>{flagLabels[flag].label}</span></span>;
        })}</span>}
      </button></li>;
    })}</ol>
    {writingChapter != null && <p role="status" className="mt-4 break-words text-sm text-[var(--ink2)]">正在写第 <span className="readout">{writingChapter}</span> 章…</p>}
  </div>;
}
