import type { ReactNode } from "react";

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}

export function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

const fieldLabels: Record<string, string> = {
  title: "标题", logline: "梗概", theme: "主题", core_conflict: "核心冲突", protagonist: "主角",
  name: "姓名", want: "想要什么", need: "真正需要什么", candidate_endings: "候选结局", main_threads: "主线",
  summary: "摘要", description: "描述", role: "角色", age: "年龄", appearance: "外形", personality: "性格", motivation: "动机",
  location: "地点", condition: "状态", knows: "已知信息", relationships: "人物关系", pov: "视角", tense: "时态", voice: "叙述语气",
  banned_phrases: "禁用表达", max_main_characters: "主要人物上限", max_scenes_per_chapter: "每章场景上限",
  chapter: "章节", from_chapter: "起始章节", to_chapter: "结束章节", start_chapter: "起始章节", end_chapter: "结束章节",
  event: "事件", time: "时间", beat: "桥段", note: "说明", importance: "重要程度", planted_chapter: "埋下章节", resolved_chapter: "回收章节",
  chapter_goal: "本章目标", scenes: "场景", beats: "节拍", opening_hook: "开头钩子", ending_hook: "结尾钩子", rationale: "裁决理由",
};

// Render provider JSON as text and structured lists, never HTML or Markdown.
export function ContentValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="text-[var(--ink2)]">暂无</span>;
  if (Array.isArray(value)) return value.length ? <ul className="space-y-2">{value.map((item, i) => <li key={i}><ContentValue value={item} /></li>)}</ul> : <span className="text-[var(--ink2)]">暂无</span>;
  if (typeof value === "object") return <dl className="space-y-2">{Object.entries(record(value)).filter(([key]) => key !== "id").map(([key, item]) => <div key={key} className="min-w-0"><dt className="text-xs text-[var(--ink2)]">{fieldLabels[key] ?? key}</dt><dd className="whitespace-pre-wrap break-words"><ContentValue value={item} /></dd></div>)}</dl>;
  if (typeof value === "boolean") return <>{value ? "是" : "否"}</>;
  const labels: Record<string, string> = { main: "主要人物", supporting: "配角", major: "重要", minor: "次要", open: "未回收", resolved: "已回收" };
  return <>{labels[String(value)] ?? String(value)}</>;
}

export function ContentSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="min-w-0 space-y-3 border-b border-[var(--carve)] pb-5 last:border-0"><h3 className="font-medium tracking-[.12em]">{title}</h3>{children}</section>;
}
