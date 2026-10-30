"use client";

import { useState } from "react";
import Glaze from "@/components/Glaze";
import type { NovelAction, NovelDetail } from "@/lib/novels";

interface Props {
  book: NovelDetail; busy: boolean;
  onAction: (action: NovelAction, body?: unknown) => Promise<void>;
  onNotes: () => void; onSettings: (resumeAfter?: boolean) => void;
  onView: () => void; onExport: () => void; onOpenSettings: () => void; onMakeFilm?: () => void;
}
export default function GateBanner({ book, busy, onAction, onNotes, onSettings, onView, onExport, onOpenSettings, onMakeFilm }: Props) {
  const [extend, setExtend] = useState(3);
  const [note, setNote] = useState("");
  if (book.status === "running" || book.status === "setup_running") return null;
  const action = (path: NovelAction, label: string, body?: unknown) => <button type="button" className="btn min-h-10" disabled={busy} onClick={() => { void onAction(path, body).catch(() => undefined); }}>{busy ? "正在处理…" : label}</button>;
  let content;
  if (book.status === "awaiting_setup") content = <><p>设定已生成，看看合不合意。</p><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onView}>查看立项卡</button></>;
  else if (book.status === "awaiting_review") {
    const end = book.chapters_done;
    const start = Math.max(1, end - book.config.batch_size + 1);
    content = <><p>已写完第 <span className="readout">{start}–{end}</span> 章，看完再继续。</p><div className="flex flex-wrap gap-2"><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onNotes}>插一句话</button>{action("continue", `继续写下 ${book.config.batch_size} 章`)}</div></>;
  } else if (book.status === "awaiting_plan") {
    const number = book.chapters.find(chapter => chapter.status === "awaiting_plan_approval")?.chapter ?? book.chapters_done + 1;
    content = <><p>第 <span className="readout">{number}</span> 章细纲已定稿。</p><button type="button" className="btn min-h-10" disabled={busy} onClick={onView}>查看并批准细纲</button></>;
  } else if (book.status === "awaiting_end") content = <><p>智能体判断故事可以收尾了。</p><div className="flex flex-wrap gap-2">{action("end/confirm", "确认完结")}</div><div className="flex flex-wrap items-end gap-3"><label className="space-y-2 text-fs-13"><span className="block">再写章数（1–10）</span><input type="number" min={1} max={10} step={1} value={extend} disabled={busy} className="ceramic-card min-h-10 w-24 rounded-lg px-3 py-2 text-fs-16.5" onChange={event => setExtend(Number(event.target.value))} /></label><label className="min-w-0 flex-1 basis-48 space-y-2 text-fs-13"><span className="block">附一句话（可选）</span><input value={note} maxLength={500} disabled={busy} className="ceramic-card min-h-10 w-full min-w-0 rounded-lg px-3 py-2 text-fs-16.5" onChange={event => setNote(event.target.value)} /></label><button type="button" className="btn min-h-10" disabled={busy || !Number.isInteger(extend) || extend < 1 || extend > 10} onClick={() => { void onAction("end/reject", { extend_chapters: extend, ...(note.trim() ? { text: note.trim() } : {}) }).catch(() => undefined); }}>{busy ? "正在处理…" : `还没完，再写 ${extend || "N"} 章`}</button></div></>;
  else if (book.status === "completed") content = <><p>全书完结，共 <span className="readout">{book.chapters_done}</span> 章 <span className="readout">{book.words_done}</span> 字。</p><button type="button" className="btn min-h-10" disabled={busy} onClick={onExport}>{busy ? "正在导出…" : "导出"}</button>{onMakeFilm && <button type="button" className="btn min-h-10 ml-2" disabled={busy} onClick={onMakeFilm}>做成片</button>}</>;
  else if (book.status === "failed") content = <p className="whitespace-pre-wrap break-words">{book.last_error || "写作出错了，请查看原因后稍后重试。"}</p>;
  else if (book.status === "paused") {
    switch (book.pause_reason) {
      case "budget_80": content = <><p>本书已花掉预算的 80%。</p><button type="button" className="btn min-h-10" disabled={busy} onClick={() => onSettings(true)}>调高预算并继续</button></>; break;
      case "insufficient_strawberries": content = <><p>草莓余额不足，充值后继续。</p>{action("resume", "继续")}</>; break;
      case "byok_unavailable": content = <><p className="whitespace-pre-wrap break-words">{book.last_error || "自带模型不可用，请在设置中启用或改用平台模型。"}</p><div className="flex flex-wrap gap-2"><button type="button" className="btn min-h-10" disabled={busy} onClick={onOpenSettings}>去设置启用</button><button type="button" className="btn min-h-10" disabled={busy} onClick={() => onSettings()}>改用平台模型</button></div></>; break;
      case "decision_invalid":
      case "step_failed": content = <><p>{book.pause_reason === "decision_invalid" ? "主编这一章没能给出合格的定稿，可以重试。重试会再次计费。" : "某一步失败，可以重试。重试会再次计费。"}</p>{book.last_error && <p className="whitespace-pre-wrap break-words text-fs-15 text-[color:var(--ink2)]">{book.last_error}</p>}{action("resume", "重试")}</>; break;
      case "locked_conflict": content = <><p>档案员发现正文与锁定设定冲突，请先查看再继续。</p><div className="flex flex-wrap gap-2"><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onView}>查看</button>{action("resume", "继续")}</div></>; break;
      case "daily_cap": content = <><p>今天的章节额度已用完，北京时间零点后可继续。</p>{action("resume", "继续")}</>; break;
      case "server_restart_failed": content = <><p>服务重启后没能自动恢复。</p>{action("resume", "继续")}</>; break;
      default: content = <><p>已暂停。</p>{action("resume", "继续")}</>;
    }
  }
  if (!content) return null;
  return <Glaze variant="strip" className="min-w-0 rounded-xl p-5 mobile:p-4" aria-label="当前关卡"><div className="relative space-y-3 text-fs-15 leading-[1.9]">{content}</div></Glaze>;
}
