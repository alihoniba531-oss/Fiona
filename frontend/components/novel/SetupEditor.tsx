"use client";

import { useState } from "react";
import { ApiError } from "@/lib/agents";
import type { NovelBible, NovelSetupPatch } from "@/lib/novels";
import { ErrorNotice } from "@/components/novel/NovelStates";

const fieldClass = "ceramic-card w-full min-w-0 rounded-[10px] border-0 px-4 py-3 text-fs-16.5 leading-[1.9] text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";
type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
const items = (value: unknown): RecordValue[] => Array.isArray(value) ? value.map(record) : [];
const text = (value: unknown) => typeof value === "string" ? value : "";
const lines = (value: unknown) => Array.isArray(value) ? value.map(text).join("\n") : "";
const nonemptyLines = (value: string) => value.split("\n").map(line => line.trim()).filter(Boolean);

// Python re's Unicode whitespace includes U+001C–001F and U+0085, and excludes
// U+FEFF. Keep this identical to backend/novel/schemas.py:compact, then count
// code points rather than JavaScript's UTF-16 units.
export function compactSetupText(value: string): string {
  return value.replace(/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000“”‘’「」『』"']+/g, "").replace(/(?:…+|\.{3,})+/g, "…");
}

export function validateSetupFields(compass: RecordValue, locked: RecordValue): Record<string, string> {
  const errors: Record<string, string> = {};
  const size = (value: unknown) => Array.from(compactSetupText(text(value))).length;
  for (const key of ["title", "logline", "theme"]) if (size(compass[key]) < 1) errors[key] = "请填写至少 1 个有效字（空白和引号不计入）。";
  const endings = items(compass.candidate_endings);
  if (!Array.isArray(compass.candidate_endings) || endings.length < 2 || endings.length > 3) errors["candidate-endings"] = "候选结局须为 2–3 条。";
  endings.forEach((ending, index) => { if (size(ending.summary) < 1) errors[`ending-${index}`] = "请填写候选结局，空白和引号不计入字数。"; });
  const threads = items(compass.main_threads);
  if (!Array.isArray(compass.main_threads) || threads.length < 1 || threads.length > 4) errors["main-threads"] = "主线须为 1–4 条。";
  threads.forEach((thread, index) => { for (const key of ["name", "description"]) if (size(thread[key]) < 1) errors[`thread-${index}-${key}`] = "请填写主线内容，空白和引号不计入字数。"; });
  items(locked.characters).forEach((character, index) => { if (size(character.appearance) < 20) errors[`character-${index}-appearance`] = "外形描述至少需要 20 个有效字（空白和引号不计入，连续省略号计 1 字）。"; });
  if (!Array.isArray(locked.world_rules) || locked.world_rules.some(rule => typeof rule !== "string" || size(rule) < 1)) errors["world-rules"] = "每条世界规则须至少有 1 个有效字，空白和引号不计入。";
  const style = record(locked.style_guide);
  for (const key of ["pov", "tense", "voice"]) if (size(style[key]) < 1) errors[`style-${key}`] = "请填写文风指南，空白和引号不计入字数。";
  if (!Array.isArray(style.banned_phrases) || style.banned_phrases.length < 5 || style.banned_phrases.some(phrase => typeof phrase !== "string" || size(phrase) < 1)) errors["style-banned"] = "禁用表达至少需要 5 条，每行一条；每条至少 1 个有效字，空白和引号不计入。";
  return errors;
}

function changedFieldPaths(originalCompass: RecordValue, compass: RecordValue, originalLocked: RecordValue, locked: RecordValue): string[] {
  const paths: string[] = [];
  const changed = (before: unknown, after: unknown) => JSON.stringify(before) !== JSON.stringify(after);
  for (const key of ["title", "logline", "theme"]) if (changed(originalCompass[key], compass[key])) paths.push(key);
  items(compass.candidate_endings).forEach((ending, index) => { if (changed(items(originalCompass.candidate_endings)[index]?.summary, ending.summary)) paths.push(`ending-${index}`); });
  items(compass.main_threads).forEach((thread, index) => { for (const key of ["name", "description"]) if (changed(items(originalCompass.main_threads)[index]?.[key], thread[key])) paths.push(`thread-${index}-${key}`); });
  items(locked.characters).forEach((character, index) => { for (const key of ["appearance", "personality", "motivation"]) if (changed(items(originalLocked.characters)[index]?.[key], character[key])) paths.push(`character-${index}-${key}`); });
  if (changed(originalLocked.world_rules, locked.world_rules)) paths.push("world-rules");
  const style = record(locked.style_guide), originalStyle = record(originalLocked.style_guide);
  for (const key of ["pov", "tense", "voice", "banned_phrases"]) if (changed(originalStyle[key], style[key])) paths.push(key === "banned_phrases" ? "style-banned" : `style-${key}`);
  return paths;
}

function serverFieldPaths(message: string): string[] {
  const paths: string[] = [];
  for (const key of ["title", "logline", "theme"]) if (new RegExp(`(?:setup|compass)\\.${key}\\b`).test(message)) paths.push(key);
  for (const match of message.matchAll(/candidate_endings\[(\d+)\]/g)) paths.push(`ending-${match[1]}`);
  for (const match of message.matchAll(/main_threads\[(\d+)\]\.(name|description)/g)) paths.push(`thread-${match[1]}-${match[2]}`);
  for (const match of message.matchAll(/characters\[(\d+)\]\.(appearance|personality|motivation)/g)) paths.push(`character-${match[1]}-${match[2]}`);
  if (message.includes("world_rules")) paths.push("world-rules");
  for (const match of message.matchAll(/style_guide\.(pov|tense|voice|banned_phrases)/g)) paths.push(match[1] === "banned_phrases" ? "style-banned" : `style-${match[1]}`);
  return [...new Set(paths)];
}

export default function SetupEditor({ bible, busy, onApprove }: { bible: NovelBible; busy: boolean; onApprove: (patch: NovelSetupPatch) => Promise<void> }) {
  const originalCompass = record(bible.compass);
  const originalLocked = record(bible.locked);
  const [compass, setCompass] = useState<RecordValue>(() => structuredClone(originalCompass));
  const [locked, setLocked] = useState<RecordValue>(() => structuredClone(originalLocked));
  const [worldRules, setWorldRules] = useState(() => lines(originalLocked.world_rules));
  const [bannedPhrases, setBannedPhrases] = useState(() => lines(record(originalLocked.style_guide).banned_phrases));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const changeCompass = (field: string, value: unknown) => setCompass(current => ({ ...current, [field]: value }));
  const changeLocked = (field: string, value: unknown) => setLocked(current => ({ ...current, [field]: value }));
  const changeItem = (field: string, index: number, key: string, value: string, isLocked = false) => {
    const source = isLocked ? locked : compass;
    const updated = items(source[field]).map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item);
    if (isLocked) changeLocked(field, updated); else changeCompass(field, updated);
  };
  const field = (label: string, path: string, value: string, onChange: (value: string) => void, rows = 3) => <label className="block space-y-2" key={path}>
    <span className="text-fs-13 text-[color:var(--ink2)]">{label}</span>
    <textarea className={fieldClass} rows={rows} value={value} onChange={event => onChange(event.target.value)} disabled={busy} aria-invalid={!!errors[path]} aria-describedby={errors[path] ? `setup-${path}` : undefined} />
    {errors[path] && <span id={`setup-${path}`} role="alert" className="block text-fs-13 text-[color:var(--ink2)]">{errors[path]}</span>}
  </label>;

  const approve = async () => {
    const currentLocked = {
      ...locked,
      world_rules: worldRules === lines(originalLocked.world_rules) ? originalLocked.world_rules : nonemptyLines(worldRules),
      style_guide: { ...record(locked.style_guide), banned_phrases: bannedPhrases === lines(record(originalLocked.style_guide).banned_phrases) ? record(originalLocked.style_guide).banned_phrases : nonemptyLines(bannedPhrases) },
    };
    const nextErrors = validateSetupFields(compass, currentLocked);
    setErrors(nextErrors); setError("");
    if (Object.keys(nextErrors).length) return;
    const changed = (original: RecordValue, current: RecordValue, keys: string[]) => Object.fromEntries(keys.filter(key => JSON.stringify(original[key]) !== JSON.stringify(current[key])).map(key => [key, current[key]]));
    const compassPatch = changed(originalCompass, compass, ["title", "logline", "theme", "candidate_endings", "main_threads"]);
    const lockedPatch = changed(originalLocked, currentLocked, ["characters", "world_rules", "style_guide"]);
    const patch: NovelSetupPatch = {};
    if (Object.keys(compassPatch).length) patch.compass = compassPatch;
    if (Object.keys(lockedPatch).length) patch.locked = lockedPatch;
    try { await onApprove(patch); }
    catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        const located = serverFieldPaths(cause.message);
        const paths = located.length ? located : changedFieldPaths(originalCompass, compass, originalLocked, currentLocked);
        if (paths.length) setErrors(Object.fromEntries(paths.map(path => [path, "立项修改不符合设定格式，请检查这一项。"])));
        else setError("立项修改不符合设定格式，请检查各项内容、人物外形与文风指南。");
      } else setError(cause instanceof Error ? cause.message : "立项确认未完成，请重试。");
    }
  };

  return <section className="min-w-0 space-y-6" aria-label="立项卡编辑器">
    <div><h2 className="text-fs-22 font-medium tracking-[.24em]">立项卡</h2><p className="mt-2 text-fs-15 leading-[1.9] text-[color:var(--ink2)]">可以修改以下设定。确认后，智能体会以这份设定开始写作。</p></div>
    {error && <ErrorNotice message={error} />}
    <fieldset className="space-y-4" disabled={busy}><legend className="mb-3 tracking-[.12em]">罗盘</legend>
      {field("书名", "title", text(compass.title), value => changeCompass("title", value), 1)}
      {field("一句话梗概", "logline", text(compass.logline), value => changeCompass("logline", value))}
      {field("主题", "theme", text(compass.theme), value => changeCompass("theme", value), 2)}
      {errors["candidate-endings"] && <p role="alert" className="text-fs-13">{errors["candidate-endings"]}</p>}
      {items(compass.candidate_endings).map((ending, index) => field(`候选结局 ${index + 1}`, `ending-${index}`, text(ending.summary), value => changeItem("candidate_endings", index, "summary", value)))}
      {errors["main-threads"] && <p role="alert" className="text-fs-13">{errors["main-threads"]}</p>}
      {items(compass.main_threads).map((thread, index) => <div key={text(thread.id) || index} className="space-y-3 border-t pt-4" style={{ borderColor: "var(--carve)" }}>
        {field(`主线 ${index + 1} 名称`, `thread-${index}-name`, text(thread.name), value => changeItem("main_threads", index, "name", value), 1)}
        {field("主线说明", `thread-${index}-description`, text(thread.description), value => changeItem("main_threads", index, "description", value))}
      </div>)}
    </fieldset>
    <fieldset className="space-y-4" disabled={busy}><legend className="mb-3 tracking-[.12em]">锁定设定</legend>
      {items(locked.characters).map((character, index) => <section key={text(character.id) || index} className="space-y-3 border-t pt-4" style={{ borderColor: "var(--carve)" }}><h3 className="font-medium">{text(character.name)}</h3>
        {([ ["appearance", "外形"], ["personality", "性格"], ["motivation", "动机"] ] as const).map(([key, label]) => field(label, `character-${index}-${key}`, text(character[key]), value => changeItem("characters", index, key, value, true)))}
      </section>)}
      {field("世界规则（每行一条）", "world-rules", worldRules, setWorldRules, 5)}
      {([ ["pov", "叙事视角"], ["tense", "叙事时态"], ["voice", "语言风格"] ] as const).map(([key, label]) => field(label, `style-${key}`, text(record(locked.style_guide)[key]), value => changeLocked("style_guide", { ...record(locked.style_guide), [key]: value }), 2))}
      {field("禁用表达（每行一条，至少 5 条）", "style-banned", bannedPhrases, setBannedPhrases, 5)}
    </fieldset>
    <button type="button" className="btn btn-primary min-h-10" disabled={busy} onClick={() => void approve()}>{busy ? "正在确认…" : "确认立项"}</button>
  </section>;
}
