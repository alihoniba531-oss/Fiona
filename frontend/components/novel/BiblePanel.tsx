"use client";

import type { ReactNode } from "react";
import type { NovelBible } from "@/lib/novels";
import { ContentValue, record, records, text } from "./NovelContent";
import { EmptyState, LoadingState } from "./NovelStates";

function BibleSection({ title, open = false, children }: { title: string; open?: boolean; children: ReactNode }) {
  return <details open={open} className="min-w-0 border-b border-[var(--carve)] py-2 last:border-0"><summary className="min-h-10 cursor-pointer py-2 font-medium tracking-[.12em]">{title}</summary><div className="space-y-4 pb-4 pt-2">{children}</div></details>;
}

export default function BiblePanel({ bible, loading }: { bible: NovelBible | null; loading: boolean }) {
  if (loading) return <LoadingState>正在加载完整圣经…</LoadingState>;
  if (!bible) return <EmptyState>立项完成后，罗盘和故事圣经会保存在这里。</EmptyState>;
  const root = record(bible), compass = record(root.compass), locked = record(root.locked), dynamic = record(root.dynamic);
  const states = record(dynamic.character_states);
  const foreshadowing = records(dynamic.foreshadowing);
  return <div className="min-w-0 break-words text-sm leading-[1.9]">
    <BibleSection title="罗盘" open><ContentValue value={Object.fromEntries(["logline", "theme", "core_conflict", "protagonist", "candidate_endings", "main_threads"].map(key => [key, compass[key]]))} /></BibleSection>
    <BibleSection title="人物卡">{records(locked.characters).map((character, index) => <section key={text(character.id) || index} className="ceramic-card space-y-3 p-3"><h4 className="font-medium">{text(character.name)} <span className="readout text-xs text-[var(--ink2)]">{text(character.id)}</span></h4><ContentValue value={Object.fromEntries(["appearance", "personality", "motivation"].map(key => [key, character[key]]))} /><div><p className="text-xs text-[var(--ink2)]">当前状态</p><ContentValue value={states[text(character.id)]} /></div></section>)}</BibleSection>
    <BibleSection title="伏笔账本">{["open", "resolved"].map(status => <section key={status} className="space-y-3"><h4 className="font-medium">{status === "open" ? "未回收" : "已回收"}</h4>{foreshadowing.filter(item => status === "open" ? item.status === "open" : item.status !== "open").map((item, index) => <div key={text(item.id) || index} className="space-y-1 border-l border-[var(--carve)] pl-3"><p><span className="readout">{text(item.id)}</span> {text(item.description)}</p><p className="text-xs text-[var(--ink2)]">埋下：{item.planted_chapter === 0 ? "立项时" : <>第 <span className="readout">{text(item.planted_chapter)}</span> 章</>}{item.resolved_chapter != null && <>；回收：第 <span className="readout">{text(item.resolved_chapter)}</span> 章</>}</p>{!!item.note && <p>{text(item.note)}</p>}</div>)}</section>)}</BibleSection>
    <BibleSection title="卷摘要和章节摘要"><h4 className="font-medium">卷摘要</h4><ContentValue value={dynamic.arc_summaries} /><h4 className="font-medium">章节摘要</h4><ContentValue value={dynamic.chapter_summaries} /></BibleSection>
    <BibleSection title="时间线"><ContentValue value={dynamic.timeline} /></BibleSection>
    <BibleSection title="世界规则与文风指南"><ContentValue value={locked.world_rules} /><ContentValue value={locked.style_guide} /></BibleSection>
    <BibleSection title="已用桥段"><ContentValue value={dynamic.used_beats} /></BibleSection>
  </div>;
}
