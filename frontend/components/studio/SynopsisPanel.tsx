"use client";

import { useId, useState } from "react";
import Glaze from "@/components/Glaze";
import { record } from "@/components/novel/NovelContent";
import { ErrorNotice } from "@/components/novel/NovelStates";
import { studioErrorMessage } from "@/lib/studio";
import { breakdownFieldClass } from "./BreakdownDialog";

const scalar = (value: unknown): string => value == null ? "" : typeof value === "object" ? Object.values(record(value)).map(scalar).filter(Boolean).join("；") : String(value);
const items = (value: unknown): unknown[] => Array.isArray(value) ? value : value && typeof value === "object" ? Object.values(record(value)) : value ? [value] : [];
const keyFor = (item: Record<string, unknown>, keys: string[], fallback: string) => keys.find(key => key in item) ?? fallback;
function threadParts(value: unknown) {
  const item = record(value);
  return Object.keys(item).length ? { name: scalar(item.name ?? item.title), description: scalar(item.description ?? item.summary) } : { name: scalar(value), description: "" };
}
function arcParts(value: unknown) {
  const item = record(value);
  return { from: scalar(item.from ?? item.start_chapter ?? item.from_chapter), to: scalar(item.to ?? item.end_chapter ?? item.to_chapter), summary: Object.keys(item).length ? scalar(item.summary ?? item.description) : scalar(value) };
}
export function synopsisItemText(key: string, value: unknown): string {
  if (key === "main_threads") { const { name, description } = threadParts(value); return name && description ? `${name} —— ${description}` : name || description; }
  if (key === "arc_summaries") { const { from, to, summary } = arcParts(value); return from && to ? `第 ${from}–${to} 章：${summary}` : summary; }
  return scalar(value);
}
export function synopsisFieldDraft(key: string, value: unknown): string {
  if (key === "main_threads") return items(value).map(item => { const { name, description } = threadParts(item); return `${name}｜${description}`; }).join("\n");
  if (key === "arc_summaries") return items(value).map(item => { const { from, to, summary } = arcParts(item); return `${from && to ? `${from}–${to}` : ""}｜${summary}`; }).join("\n");
  if (key === "themes") return items(value).map(scalar).join("、");
  return scalar(value);
}
export function parseSynopsisField(key: string, draft: string, previous: unknown): unknown {
  if (key === "themes") return Array.isArray(previous) ? draft.split(/[、\n]/).map(value => value.trim()).filter(Boolean) : draft;
  if (!["main_threads", "arc_summaries"].includes(key)) return draft;
  // Preserve uncommon scalar forms as scalars; the normal snapshot form is an array.
  if (previous != null && typeof previous !== "object") return draft;
  const original = items(previous);
  const lines = draft.split("\n").map(line => line.trim()).filter(Boolean);
  const parsed = lines.map((line, index) => {
    const separator = line.indexOf("｜") >= 0 ? line.indexOf("｜") : line.indexOf("|");
    if (separator < 0) throw new Error(`第 ${index + 1} 行缺少「｜」。`);
    const left = line.slice(0, separator).trim(), right = line.slice(separator + 1).trim();
    const existing = original[index], result = { ...record(existing) };
    if (key === "main_threads") {
      if (!left && !right) throw new Error(`第 ${index + 1} 行需填写名称或描述。`);
      if (typeof existing === "string" && !right) return left;
      const nameKey = keyFor(result, ["name", "title"], "name"), descriptionKey = keyFor(result, ["description", "summary"], "description");
      if (left || nameKey in result) result[nameKey] = left;
      if (right || descriptionKey in result) result[descriptionKey] = right;
    } else {
      if (!right) throw new Error(`第 ${index + 1} 行需填写摘要。`);
      if (typeof existing === "string" && !left) return right;
      const range = left ? /^(\d+)\s*[–—-]\s*(\d+)$/.exec(left) : null;
      if (left && (!range || Number(range[1]) < 1 || Number(range[1]) > Number(range[2]))) throw new Error(`第 ${index + 1} 行章号需为「a–b」。`);
      const fromKey = keyFor(result, ["from", "start_chapter", "from_chapter"], "from"), toKey = keyFor(result, ["to", "end_chapter", "to_chapter"], "to");
      if (range) { result[fromKey] = Number(range[1]); result[toKey] = Number(range[2]); }
      else { delete result[fromKey]; delete result[toKey]; }
      result[keyFor(result, ["summary", "description"], "summary")] = right;
    }
    return result;
  });
  if (previous && !Array.isArray(previous) && typeof previous === "object") {
    const keys = Object.keys(record(previous));
    return Object.fromEntries(parsed.map((value, index) => [keys[index] ?? String(index + 1), value]));
  }
  return parsed;
}
function SynopsisValue({ field, value }: { field: string; value: unknown }) {
  if (value == null || value === "" || Array.isArray(value) && !value.length) return <span className="text-[color:var(--ink2)]">暂无</span>;
  if (field === "main_threads" || field === "arc_summaries") return <ul className="list-disc space-y-2 pl-5">{items(value).map((item, index) => <li key={index}>{synopsisItemText(field, item)}</li>)}</ul>;
  return <p className="whitespace-pre-wrap">{field === "themes" ? items(value).map(scalar).join("、") : scalar(value)}</p>;
}
export default function SynopsisPanel({ synopsis, novel, busy = false, onSave }: { synopsis: Record<string, unknown>; novel: boolean; busy?: boolean; onSave?: (value: Record<string, unknown>) => Promise<void> }) {
  const hasCompass = Object.keys(record(synopsis.compass)).length > 0;
  const source = hasCompass ? { ...synopsis, ...record(synopsis.compass) } : synopsis;
  const fields = novel ? [["logline", "一句话梗概"], ["theme", "主题"], ["core_conflict", "核心冲突"], ["main_threads", "主线"], ["arc_summaries", "分段梗概"]] : [["logline", "一句话梗概"], ["synopsis", "梗概"], ["genre", "类型"], ["tone", "基调"], ["themes", "主题"]];
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const id = useId();
  const save = async () => {
    if (!draft || !onSave || busy || saving) return;
    const next = { ...synopsis }, compass = hasCompass ? { ...record(synopsis.compass) } : null;
    const issues: Record<string, string> = {};
    for (const [key, label] of fields) {
      try { const value = parseSynopsisField(key, draft[key], source[key]); if (compass && key in compass) compass[key] = value; else next[key] = value; }
      catch (cause) { issues[key] = `${label}格式不正确：${studioErrorMessage(cause)}`; }
    }
    setErrors(issues); if (Object.keys(issues).length) return;
    if (compass) next.compass = compass;
    setSaving(true); setError("");
    try { await onSave(next); setDraft(null); }
    catch (cause) { setError(studioErrorMessage(cause)); }
    finally { setSaving(false); }
  };
  return <Glaze variant="panel" lens={false} className="min-w-0 space-y-4 rounded-2xl p-4 @[640px]:p-5"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-fs-22 tracking-[.2em]">故事梗概</h2>{onSave && !draft && <button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={() => { setDraft(Object.fromEntries(fields.map(([key]) => [key, synopsisFieldDraft(key, source[key])]))); setErrors({}); setError(""); }}>修改梗概</button>}</div>
    {draft ? <form className="min-w-0 space-y-3" onSubmit={event => { event.preventDefault(); void save(); }}><fieldset disabled={busy || saving} className="min-w-0 space-y-3">{fields.map(([key, label]) => <label key={key} htmlFor={`${id}-${key}`} className="block min-w-0 space-y-1 text-fs-13"><span>{label}</span>{(key === "main_threads" || key === "arc_summaries") && <span className="block text-[color:var(--ink2)]">一行一项：{key === "main_threads" ? "名称｜描述" : "a–b｜摘要（无章号可留空）"}</span>}<textarea id={`${id}-${key}`} rows={key === "main_threads" || key === "arc_summaries" ? 6 : 3} className={breakdownFieldClass} value={draft[key]} aria-invalid={!!errors[key]} aria-describedby={errors[key] ? `${id}-${key}-error` : undefined} onChange={event => { setDraft({ ...draft, [key]: event.target.value }); setErrors({ ...errors, [key]: "" }); }} />{errors[key] && <span id={`${id}-${key}-error`} role="alert" className="block text-[color:var(--seal)]">{errors[key]}</span>}</label>)}<div className="flex flex-wrap gap-2"><button type="submit" className="btn btn-primary min-h-10">保存梗概</button><button type="button" className="btn btn-quiet min-h-10" onClick={() => setDraft(null)}>取消</button></div></fieldset></form> : fields.map(([key, label]) => <div key={key} className="min-w-0 break-words text-fs-15 leading-relaxed"><h3 className="mb-1 text-[color:var(--ink2)]">{label}</h3><SynopsisValue field={key} value={source[key]} /></div>)}
    {error && <ErrorNotice message={error} />}
  </Glaze>;
}
