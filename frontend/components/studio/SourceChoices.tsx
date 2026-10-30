"use client";

import Link from "next/link";
import { novelStatusLabel, type NovelDetail } from "@/lib/novels";
import { studioHref, studioSourceFlagLabel, type StudioFlaggedChapter, type StudioNovelCandidate } from "@/lib/studio";

export function SourceFlags({ chapters }: { chapters: StudioFlaggedChapter[] }) {
  if (!chapters.length) return null;
  return <details className="min-w-0 break-words text-fs-13 text-[color:var(--ink2)]"><summary className="min-h-10 cursor-pointer py-2">{chapters.length} 章带有标记</summary><ul className="space-y-2 pl-4">{chapters.map(item => <li key={item.chapter}>第 {item.chapter} 章 {item.title}：{item.flags.map(studioSourceFlagLabel).join("、")}</li>)}</ul></details>;
}
export function sourceProjectCreatedDate(value: string): string {
  const normalized = /[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value.replace(" ", "T")}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (number: number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
export function ExistingSourceProjects({ projects, embedded, primary = false }: { projects: StudioNovelCandidate["projects"]; embedded: boolean; primary?: boolean }) {
  if (!projects.length) return null;
  const ordered = [...projects].sort((left, right) => right.created_at.localeCompare(left.created_at));
  return <div className="mt-2 space-y-2 text-fs-13"><p className="text-[color:var(--ink2)]">已有工作室项目</p>{ordered.map((project, index) => <div key={project.id} className="flex min-w-0 flex-wrap items-center gap-2"><span className="min-w-0 break-words">{project.title} · <time dateTime={project.created_at} suppressHydrationWarning>{sourceProjectCreatedDate(project.created_at)}</time> · 快照第 {project.snapshot_no ?? 0} 版</span><Link className={`btn ${primary && index === 0 ? "btn-primary" : "btn-quiet"} min-h-10`} href={studioHref(`/studio/${encodeURIComponent(project.id)}`, embedded)}>打开</Link></div>)}</div>;
}
export function NovelSourceChoice({ book, selected = false, disabled = false, embedded, onSelect }: { book: StudioNovelCandidate; selected?: boolean; disabled?: boolean; embedded: boolean; onSelect?: () => void }) {
  return <article className={`ceramic-card min-w-0 rounded-xl p-3 ${book.eligible ? "" : "text-[color:var(--ink2)]"} ${selected ? "ring-1 ring-[color:var(--ink)]" : ""}`}>
    <div className="flex min-w-0 flex-wrap items-start gap-2"><button type="button" className={`chip h-auto min-h-10 max-w-full whitespace-normal break-words py-2 text-left leading-relaxed ${selected ? "chip-on" : ""}`} aria-pressed={selected} disabled={disabled || !book.eligible || !onSelect} onClick={onSelect}>{book.title}</button>{book.drama_adaptation && <span className="tag">改编短剧</span>}</div>
    <p className="readout mt-2 text-fs-13">{novelStatusLabel({ status: book.status as NovelDetail["status"], pause_reason: null })} · {book.chapters_done} 章 · {book.words_done.toLocaleString()} 字</p>
    <p className="mt-2 text-fs-13">{book.eligible ? "可以建立快照" : book.reason || "暂时不能导入"}</p>
    <SourceFlags chapters={book.flagged} /><ExistingSourceProjects projects={book.projects} embedded={embedded} />
  </article>;
}
export function SourceAspectPicker({ aspect, disabled, onChange }: { aspect: "16:9" | "9:16"; disabled: boolean; onChange: (value: "16:9" | "9:16") => void }) {
  return <fieldset className="my-5" disabled={disabled}><legend className="mb-2">画幅</legend><div className="flex flex-wrap gap-2">{(["16:9", "9:16"] as const).map(value => <button key={value} type="button" aria-pressed={aspect === value} className={`chip min-h-10 min-w-10 ${aspect === value ? "chip-on" : ""}`} onClick={() => onChange(value)}>{value}</button>)}</div></fieldset>;
}
export const sourceDialogClass = "m-auto max-h-[85dvh] w-[min(620px,calc(100vw-32px))] max-w-full overflow-y-auto rounded-2xl border border-[color:var(--carve)] bg-[color:var(--paper)] p-5 text-[color:var(--ink)] backdrop:bg-[color:var(--scrim)]";
