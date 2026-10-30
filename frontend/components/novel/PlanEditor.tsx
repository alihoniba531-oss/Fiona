"use client";

import { useState } from "react";
import type { NovelBeatSheet } from "@/lib/novels";
import { ErrorNotice } from "@/components/novel/NovelStates";

const fieldClass = "ceramic-card w-full min-w-0 rounded-[10px] border-0 px-4 py-3 text-fs-16.5 leading-[1.9] text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";
export default function PlanEditor({ beatSheet, chapter, maxScenes = 10, busy, onApprove, onRedo }: { beatSheet: NovelBeatSheet; chapter: number; maxScenes?: number; busy: boolean; onApprove: (beat?: NovelBeatSheet) => Promise<void>; onRedo: (text: string) => Promise<void> }) {
  const [draft, setDraft] = useState(() => structuredClone(beatSheet));
  const [beats, setBeats] = useState(() => beatSheet.beats.join("\n"));
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const update = (key: string, value: unknown) => setDraft(current => ({ ...current, [key]: value }));
  const run = async (action: () => Promise<void>) => { setError(""); try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : "细纲操作未完成，请重试。"); } };
  const approveEdited = () => {
    const nextBeats = beats.split("\n").map(line => line.trim()).filter(Boolean);
    if (![draft.title, draft.chapter_goal, draft.opening_hook, draft.ending_hook].every(value => value.trim()) || draft.scenes.some(scene => !scene.location.trim() || !scene.summary.trim())) { setError("请填写章名、目标、场景和钩子。"); return; }
    if (nextBeats.length < 3 || nextBeats.length > 8) { setError("节拍须为 3–8 条，每行一条。"); return; }
    void run(() => onApprove({ ...draft, beats: nextBeats }));
  };
  const field = (key: "title" | "chapter_goal" | "opening_hook" | "ending_hook", label: string) => <label className="block space-y-2" key={key}><span className="text-fs-13 text-[color:var(--ink2)]">{label}</span><textarea className={fieldClass} rows={key === "title" ? 1 : 3} value={draft[key]} disabled={busy} onChange={event => update(key, event.target.value)} /></label>;
  return <section className="min-w-0 space-y-5" aria-label="细纲编辑器">
    <h2 className="text-fs-22 font-medium tracking-[.24em]">第 <span className="readout">{chapter}</span> 章细纲</h2>
    {error && <ErrorNotice message={error} />}
    {field("title", "章名")}{field("chapter_goal", "本章目标")}
    <fieldset className="space-y-4" disabled={busy}><legend className="mb-3 text-fs-13 text-[color:var(--ink2)]">场景</legend>
      {draft.scenes.map((scene, index) => <div key={index} className="space-y-2 border-t pt-3" style={{ borderColor: "var(--carve)" }}>
        <label className="block space-y-2"><span className="text-fs-13">场景 {index + 1} 地点</span><input className={fieldClass} value={scene.location} onChange={event => update("scenes", draft.scenes.map((item, i) => i === index ? { ...item, location: event.target.value } : item))} /></label>
        <label className="block space-y-2"><span className="text-fs-13">场景内容</span><textarea className={fieldClass} rows={3} value={scene.summary} onChange={event => update("scenes", draft.scenes.map((item, i) => i === index ? { ...item, summary: event.target.value } : item))} /></label>
        {draft.scenes.length > 1 && <button type="button" className="btn btn-quiet min-h-10" onClick={() => update("scenes", draft.scenes.filter((_, i) => i !== index))}>移除这个场景</button>}
      </div>)}
      {draft.scenes.length < maxScenes && <button type="button" className="btn min-h-10" onClick={() => update("scenes", [...draft.scenes, { location: "", summary: "" }])}>增加场景</button>}
    </fieldset>
    <label className="block space-y-2"><span className="text-fs-13 text-[color:var(--ink2)]">节拍（每行一条，3–8 条）</span><textarea className={fieldClass} rows={7} value={beats} disabled={busy} onChange={event => setBeats(event.target.value)} /></label>
    {field("opening_hook", "开头钩子")}{field("ending_hook", "结尾钩子")}
    <div className="flex flex-wrap gap-3"><button type="button" className="btn min-h-10" disabled={busy} onClick={() => void run(() => onApprove())}>{busy ? "正在处理…" : "批准（原样）"}</button><button type="button" className="btn btn-primary min-h-10" disabled={busy} onClick={approveEdited}>{busy ? "正在处理…" : "改完批准"}</button></div>
    <div className="space-y-3 border-t pt-5" style={{ borderColor: "var(--carve)" }}><label className="block space-y-2"><span className="text-fs-13">附一句话重新定稿</span><textarea className={fieldClass} rows={3} maxLength={500} value={note} disabled={busy} onChange={event => setNote(event.target.value)} /></label><p className="text-fs-15 leading-[1.9] text-[color:var(--ink2)]">重新定稿会再次扣除草莓。<span className="readout">{note.length} / 500</span></p><button type="button" className="btn min-h-10" disabled={busy || !note.trim()} onClick={() => void run(() => onRedo(note.trim()))}>{busy ? "正在重新定稿…" : "附一句话重新定稿"}</button></div>
  </section>;
}
