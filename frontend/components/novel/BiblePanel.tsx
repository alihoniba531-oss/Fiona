"use client";

import { useId, useState, type ReactNode } from "react";
import { novelErrorMessage, type NovelBible, type NovelCharacterEdit, type NovelStatus } from "@/lib/novels";
import { ContentValue, record, records, text } from "./NovelContent";
import { EmptyState, ErrorNotice, LoadingState } from "./NovelStates";
import { novelFieldClass } from "./NovelModelFields";

const editableStatuses: NovelStatus[] = ["awaiting_review", "awaiting_plan", "awaiting_end", "paused", "completed"];
// Match schemas.compact(), including Python whitespace and Unicode code points.
const appearanceLength = (appearance: string) => Array.from(appearance.replace(/[\p{White_Space}\u001c-\u001f“”‘’「」『』"']+/gu, "").replace(/(?:…+|\.{3,})+/g, "…")).length;
type SaveCharacter = (id: string, patch: NovelCharacterEdit) => Promise<boolean>;

function CharacterCard({ character, state, editable, busy, onSave }: {
  character: Record<string, unknown>; state: unknown; editable: boolean; busy: boolean; onSave: SaveCharacter;
}) {
  const fieldId = useId();
  const [draft, setDraft] = useState<{ appearance: string; personality: string; motivation: string } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [previousEditable, setPreviousEditable] = useState(editable);
  if (previousEditable !== editable) {
    setPreviousEditable(editable);
    if (!editable) setDraft(null);
  }
  const id = text(character.id);
  const currentState = record(state);
  const visibleState = Object.fromEntries(["location", "condition", "knows", "relationships"].filter(key => key in currentState).map(key => [key, currentState[key]]));
  const save = async () => {
    if (!draft || busy || saving) return;
    const patch: NovelCharacterEdit = {};
    for (const field of ["appearance", "personality", "motivation"] as const) {
      if (draft[field].trim() !== text(character[field]).trim()) patch[field] = draft[field].trim();
    }
    if (!Object.keys(patch).length) { setDraft(null); return "没有改动"; }
    if (patch.appearance !== undefined && appearanceLength(patch.appearance) < 20) { setError("外形至少写 20 个字"); return; }
    if (patch.personality !== undefined && !patch.personality || patch.motivation !== undefined && !patch.motivation) { setError("性格和动机都不能为空"); return; }
    setSaving(true); setError("");
    try {
      if (await onSave(id, patch)) setDraft(null);
    } catch (cause) { setError(novelErrorMessage(cause)); }
    finally { setSaving(false); }
  };
  return <section className="ceramic-card min-w-0 space-y-3 p-3">
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2"><h4 className="min-w-0 break-words font-medium">{text(character.name)} <span className="readout text-fs-12 text-[color:var(--ink2)]">{id}</span></h4>{editable && !draft && <button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => { setDraft({ appearance: text(character.appearance), personality: text(character.personality), motivation: text(character.motivation) }); setError(""); setNotice(""); }}>修改</button>}</div>
    {appearanceLength(text(character.appearance)) < 20 && <p className="text-fs-13 text-[color:var(--ink2)]">外形未写全，改编时需要补</p>}
    {editable && draft ? <form className="min-w-0 space-y-3" onSubmit={event => { event.preventDefault(); setNotice(""); void save().then(message => { if (message) setNotice(message); }); }}>
      <fieldset disabled={busy || saving} className="min-w-0 space-y-3">
        {([{ key: "appearance", label: "外形", rows: 5 }, { key: "personality", label: "性格", rows: 3 }, { key: "motivation", label: "动机", rows: 3 }] as const).map(field => <div key={field.key} className="min-w-0"><label htmlFor={`${fieldId}-${field.key}`} className="mb-1 block text-fs-16.5">{field.label}</label><textarea id={`${fieldId}-${field.key}`} rows={field.rows} value={draft[field.key]} onChange={event => { setDraft({ ...draft, [field.key]: event.target.value }); setError(""); }} aria-describedby={field.key === "appearance" ? `${fieldId}-count` : undefined} className={`${novelFieldClass} resize-y`} />{field.key === "appearance" && <p id={`${fieldId}-count`} className="readout mt-1 text-fs-13 text-[color:var(--ink2)]">{appearanceLength(draft.appearance)} 字（至少 20 字；不计空白和引号，省略号计一字）</p>}</div>)}
        <div className="flex flex-wrap gap-2"><button type="submit" className="btn btn-primary min-h-10">{saving ? "保存中…" : "保存"}</button><button type="button" className="btn btn-quiet min-h-10" onClick={() => { setDraft(null); setError(""); }}>取消</button></div>
      </fieldset>
    </form> : <ContentValue value={Object.fromEntries(["appearance", "personality", "motivation"].map(key => [key, character[key]]))} />}
    {error && <ErrorNotice message={error} />}
    {notice && <p role="status" className="text-fs-13 text-[color:var(--ink2)]">{notice}</p>}
    <div><p className="text-fs-12 text-[color:var(--ink2)]">当前状态</p><ContentValue value={Object.keys(visibleState).length ? visibleState : null} />{currentState.last_seen_chapter != null && <p>最近出场：第 <span className="readout">{text(currentState.last_seen_chapter)}</span> 章</p>}</div>
  </section>;
}

function BibleSection({ title, open = false, children }: { title: string; open?: boolean; children: ReactNode }) {
  return <details open={open} className="min-w-0 border-b border-[color:var(--carve)] py-2 last:border-0"><summary className="min-h-10 cursor-pointer py-2 font-medium tracking-[.12em]">{title}</summary><div className="space-y-4 pb-4 pt-2">{children}</div></details>;
}

export default function BiblePanel({ bible, loading, status, busy, onSaveCharacter }: {
  bible: NovelBible | null; loading: boolean; status: NovelStatus; busy: boolean; onSaveCharacter: SaveCharacter;
}) {
  if (loading && !bible) return <LoadingState>正在加载完整圣经…</LoadingState>;
  if (!bible) return <EmptyState>立项完成后，罗盘和故事圣经会保存在这里。</EmptyState>;
  const root = record(bible), compass = record(root.compass), locked = record(root.locked), dynamic = record(root.dynamic);
  const states = record(dynamic.character_states);
  const foreshadowing = records(dynamic.foreshadowing);
  return <div className="min-w-0 break-words text-fs-15 leading-[1.9]">
    {loading && <LoadingState>正在加载完整圣经…</LoadingState>}
    <BibleSection title="罗盘" open><ContentValue value={Object.fromEntries(["logline", "theme", "core_conflict", "protagonist", "candidate_endings", "main_threads"].map(key => [key, compass[key]]))} /></BibleSection>
    <BibleSection title="人物卡">{records(locked.characters).map((character, index) => <CharacterCard key={text(character.id) || index} character={character} state={states[text(character.id)]} editable={editableStatuses.includes(status)} busy={busy} onSave={onSaveCharacter} />)}</BibleSection>
    <BibleSection title="伏笔账本">{["open", "resolved"].map(status => <section key={status} className="space-y-3"><h4 className="font-medium">{status === "open" ? "未回收" : "已回收"}</h4>{foreshadowing.filter(item => status === "open" ? item.status === "open" : item.status !== "open").map((item, index) => <div key={text(item.id) || index} className="space-y-1 border-l border-[color:var(--carve)] pl-3"><p><span className="readout">{text(item.id)}</span> {text(item.description)}</p><p className="text-fs-12 text-[color:var(--ink2)]">埋下：{item.planted_chapter === 0 ? "立项时" : <>第 <span className="readout">{text(item.planted_chapter)}</span> 章</>}{item.resolved_chapter != null && <>；回收：第 <span className="readout">{text(item.resolved_chapter)}</span> 章</>}</p>{!!item.note && <p>{text(item.note)}</p>}</div>)}</section>)}</BibleSection>
    <BibleSection title="卷摘要和章节摘要"><h4 className="font-medium">卷摘要</h4><ContentValue value={dynamic.arc_summaries} /><h4 className="font-medium">章节摘要</h4><ContentValue value={dynamic.chapter_summaries} /></BibleSection>
    <BibleSection title="时间线"><ContentValue value={dynamic.timeline} /></BibleSection>
    <BibleSection title="世界规则与文风指南"><ContentValue value={locked.world_rules} /><ContentValue value={locked.style_guide} /></BibleSection>
    <BibleSection title="已用桥段"><ContentValue value={dynamic.used_beats} /></BibleSection>
  </div>;
}
