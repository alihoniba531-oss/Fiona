"use client";

import { useId, useState } from "react";
import Glaze from "@/components/Glaze";
import { EmptyState, ErrorNotice } from "@/components/novel/NovelStates";
import { studioErrorMessage } from "@/lib/studio";
import { useRovingTabs } from "@/lib/useRovingTabs";
import { formatEpisodeRanges, roleLabel, type BibleFields, type BibleKind, type StudioBibleEntry } from "@/lib/studio-breakdown";
import BreakdownDialog, { breakdownFieldClass } from "./BreakdownDialog";

const kinds = ["character", "location", "prop"] as const;
const kindLabels = ["人物", "场景", "道具"];
const blank: BibleFields = { name: "", aliases: [], role: "", description: "", appearance: "", needs_author: false };
function fieldsFor(entry: StudioBibleEntry): BibleFields { return { name: entry.name, aliases: entry.aliases, role: entry.role, description: entry.description, appearance: entry.appearance, needs_author: !!entry.needs_author }; }
export function BibleFieldsEditor({ fields, onChange, kind }: { fields: BibleFields; onChange: (value: BibleFields) => void; kind: BibleKind }) {
  const id = useId();
  return <div className="grid min-w-0 gap-3 @[640px]:grid-cols-2">{([{ key: "name", label: "名字" }, { key: "role", label: "定位" }, { key: "description", label: "描述" }, { key: "appearance", label: "外形" }] as const).map(({ key, label }) => <label key={key} htmlFor={`${id}-${key}`} className="block min-w-0 space-y-1 text-sm"><span>{label}</span>{key === "description" || key === "appearance" ? <textarea id={`${id}-${key}`} rows={3} value={fields[key]} className={breakdownFieldClass} onChange={event => onChange({ ...fields, [key]: event.target.value })} /> : <input id={`${id}-${key}`} required={key === "name"} value={fields[key]} className={breakdownFieldClass} onChange={event => onChange({ ...fields, [key]: event.target.value })} />}</label>)}<label htmlFor={`${id}-aliases`} className="block min-w-0 space-y-1 text-sm"><span>别名（用顿号或逗号分隔）</span><input id={`${id}-aliases`} value={fields.aliases.join("、")} className={breakdownFieldClass} onChange={event => onChange({ ...fields, aliases: event.target.value.split(/[、,，]/).map(item => item.trim()) })} /></label>{kind === "character" && <label className="flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" checked={!!fields.needs_author} onChange={event => onChange({ ...fields, needs_author: event.target.checked })} />待作者补充</label>}</div>;
}
export function BibleTableRow({ entry, selected, busy, onSelect, onSave, onArchive }: { entry: StudioBibleEntry; selected: boolean; busy: boolean; onSelect: () => void; onSave: (fields: Partial<BibleFields>) => Promise<void>; onArchive: () => void }) {
  const [draft, setDraft] = useState<BibleFields | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!draft || busy || saving) return;
    if (!draft.name.trim()) { setError("名字不能为空。"); return; }
    setSaving(true); setError("");
    const patch: Partial<BibleFields> = {};
    const previous = fieldsFor(entry);
    for (const key of ["name", "role", "description", "appearance"] as const) if (draft[key].trim() !== previous[key]) patch[key] = draft[key].trim();
    const aliases = draft.aliases.map(item => item.trim()).filter(Boolean);
    if (JSON.stringify(aliases) !== JSON.stringify(previous.aliases)) patch.aliases = aliases;
    if (!!draft.needs_author !== !!previous.needs_author) patch.needs_author = !!draft.needs_author;
    try { if (Object.keys(patch).length) await onSave(patch); setDraft(null); }
    catch (cause) { setError(studioErrorMessage(cause)); }
    finally { setSaving(false); }
  };
  if (draft) return <tr className="border-b border-[color:var(--carve)]"><td colSpan={7} className="p-3"><form className="min-w-0 space-y-3" onSubmit={event => { event.preventDefault(); void save(); }}><fieldset disabled={busy || saving} className="min-w-0 space-y-3"><BibleFieldsEditor fields={draft} onChange={setDraft} kind={entry.kind} /><p className="text-sm text-[color:var(--ink2)]">原文摘录只读；作者填写外形后标为「作者补充」。</p><div className="flex flex-wrap gap-2"><button type="submit" className="btn btn-primary min-h-10">保存</button><button type="button" className="btn btn-quiet min-h-10" onClick={() => { setDraft(null); setError(""); }}>取消</button></div></fieldset>{error && <ErrorNotice message={error} />}</form></td></tr>;
  return <tr className="border-b border-[color:var(--carve)] align-top last:border-0"><td className="p-3"><label className="flex min-h-10 items-start gap-2"><input type="checkbox" aria-label={`选择${entry.name}`} checked={selected} disabled={busy} onChange={onSelect} className="mt-1" /><span>{entry.name}{entry.aliases.length > 0 && <small className="block text-[color:var(--ink2)]">{entry.aliases.join("、")}</small>}{!!entry.needs_author && <span className="tag mt-1">待作者补充</span>}</span></label></td><td className="p-3">{roleLabel(entry.role) || "—"}</td><td className="max-w-64 whitespace-pre-wrap p-3">{entry.appearance || entry.description || "—"}{entry.appearance_source !== "none" && <small className="mt-1 block text-[color:var(--ink2)]">{({ workshop: "小说工坊设定", excerpt: "原文摘录", author: "作者补充" })[entry.appearance_source]}</small>}</td><td className="max-w-64 p-3">{entry.excerpt ? <details><summary className="min-h-10 cursor-pointer">展开原文摘录</summary><p className="whitespace-pre-wrap">{entry.excerpt}</p></details> : "无原文外形摘录"}</td><td className="p-3">{entry.first_appearance || (entry.first_unit ? `第 ${entry.first_unit} 场` : "待确定")}</td><td className="p-3">{formatEpisodeRanges(entry.episodes)}</td><td className="p-3"><div className="flex flex-wrap gap-1"><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => { setDraft(fieldsFor(entry)); setError(""); }}>修改</button><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onArchive}>归档</button></div></td></tr>;
}
export default function BibleTable({ entries, busy, onSave, onAdd, onMerge, onArchive }: { entries: StudioBibleEntry[]; busy: boolean; onSave: (id: string, fields: Partial<BibleFields>) => Promise<void>; onAdd: (kind: BibleKind, fields: BibleFields) => Promise<void>; onMerge: (keepId: string, mergeIds: string[]) => Promise<void>; onArchive: (id: string) => Promise<void> }) {
  const [tab, setTab] = useState(0);
  const [onlyMissing, setOnlyMissing] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [newFields, setNewFields] = useState<BibleFields>(blank);
  const [merging, setMerging] = useState(false);
  const [keepId, setKeepId] = useState("");
  const [archive, setArchive] = useState<StudioBibleEntry | null>(null);
  const prefix = useId();
  const chooseTab = (value: number) => { setTab(value); setSelected([]); };
  const tabProps = useRovingTabs(3, tab, chooseTab);
  const kind = kinds[tab];
  const visible = entries.filter(entry => entry.kind === kind && (!onlyMissing || !!entry.needs_author));
  const selectedEntries = entries.filter(entry => selected.includes(entry.id) && entry.kind === kind);
  return <Glaze variant="panel" lens={false} className="min-w-0 rounded-2xl p-4 @[640px]:p-5">
    <h2 className="mb-4 text-xl tracking-[.2em]">人物、场景、道具总表</h2><div role="tablist" aria-label="总表类型" className="mb-3 flex min-w-0 gap-2">{kindLabels.map((label, index) => <button key={label} type="button" id={`${prefix}-tab-${index}`} role="tab" aria-selected={tab === index} aria-controls={`${prefix}-panel-${index}`} {...tabProps(index)} className={`chip min-h-10 ${tab === index ? "chip-on" : ""}`} onClick={() => chooseTab(index)}>{label}</button>)}</div>
    <div className="mb-3 flex min-w-0 flex-wrap items-center gap-3"><label className="flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" checked={onlyMissing} onChange={event => setOnlyMissing(event.target.checked)} />只看待补充</label><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => { setNewFields({ ...blank, needs_author: kind === "character" }); setAdding(true); }}>新增{kindLabels[tab]}</button><button type="button" className="btn btn-quiet min-h-10" disabled={busy || selectedEntries.length < 2} onClick={() => { setKeepId(selectedEntries[0].id); setMerging(true); }}>合并所选（{selectedEntries.length}）</button></div>
    <div role="tabpanel" id={`${prefix}-panel-${tab}`} aria-labelledby={`${prefix}-tab-${tab}`} className="min-w-0">{visible.length ? <div className="max-w-full overflow-x-auto rounded-lg border border-[color:var(--carve)]"><table className="w-full min-w-[800px] table-fixed break-words text-left text-sm leading-relaxed"><thead className="border-b border-[color:var(--carve)] text-[color:var(--ink2)]"><tr>{["名字（含别名）", "定位", "外形或描述", "原文摘录", "首次出场", "出场的集", "操作"].map(label => <th key={label} scope="col" className="p-3 font-normal">{label}</th>)}</tr></thead><tbody>{visible.map(entry => <BibleTableRow key={entry.id} entry={entry} selected={selected.includes(entry.id)} busy={busy} onSelect={() => setSelected(value => value.includes(entry.id) ? value.filter(id => id !== entry.id) : [...value, entry.id])} onSave={fields => onSave(entry.id, fields)} onArchive={() => setArchive(entry)} />)}</tbody></table></div> : <EmptyState>{onlyMissing ? "没有待作者补充的条目。" : "这一类还没有条目，可以手动新增。"}</EmptyState>}</div>
    {adding && <BreakdownDialog title={`新增${kindLabels[tab]}`} confirmLabel="新增" busy={busy} disabled={!newFields.name.trim()} onClose={() => setAdding(false)} onConfirm={async () => { await onAdd(kind, { ...newFields, name: newFields.name.trim(), aliases: newFields.aliases.map(value => value.trim()).filter(Boolean) }); setAdding(false); }}><BibleFieldsEditor fields={newFields} onChange={setNewFields} kind={kind} /></BreakdownDialog>}
    {merging && <BreakdownDialog title="合并总表条目" confirmLabel="确认合并" busy={busy} onClose={() => setMerging(false)} onConfirm={async () => { await onMerge(keepId, selectedEntries.filter(entry => entry.id !== keepId).map(entry => entry.id)); setSelected([]); setMerging(false); }}><p>选择保留的条目。其余条目标记为已合并，别名和出场记录会汇入保留项。</p>{selectedEntries.map(entry => <label key={entry.id} className="flex min-h-10 items-center gap-2"><input type="radio" name="bible-keep" checked={keepId === entry.id} onChange={() => setKeepId(entry.id)} />{entry.name}</label>)}</BreakdownDialog>}
    {archive && <BreakdownDialog title="归档总表条目" confirmLabel="确认归档" busy={busy} onClose={() => setArchive(null)} onConfirm={async () => { await onArchive(archive.id); setSelected(value => value.filter(id => id !== archive.id)); setArchive(null); }}><p>将「{archive.name}」移出当前总表，历史记录仍会保留。</p></BreakdownDialog>}
  </Glaze>;
}
