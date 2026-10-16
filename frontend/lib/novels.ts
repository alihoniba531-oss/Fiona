import { ApiError, apiJson } from "@/lib/agents";
import { apiFetch } from "@/lib/auth";
import { API_BASE } from "@/lib/config";

export type NovelStatus = "setup_running" | "awaiting_setup" | "running" | "awaiting_review" | "awaiting_plan" | "awaiting_end" | "completed" | "paused" | "failed";
export type NovelAutomation = "per_batch" | "per_chapter" | "full_auto";
export type NovelPanelMode = "critique" | "solo";
export interface NovelTarget { min_chapters: number; max_chapters: number; chapter_words: number }
export interface NovelCreateInput {
  seed_idea: string; agents: Record<string, string>; panel_mode: NovelPanelMode;
  automation: NovelAutomation; batch_size: number; target: NovelTarget;
  adaptation: { max_main_characters: number; max_scenes_per_chapter: number };
  budget_strawberries: number;
}
export interface NovelPatchInput { budget_strawberries?: number; automation?: NovelAutomation; batch_size?: number; agents?: Record<string, string> }
export interface NovelSummary {
  id: string; title: string | null; status: NovelStatus; pause_reason: string | null;
  bible_version: number; chapters_done: number; max_chapters: number; words_done: number;
  budget_strawberries: number; spent_strawberries: number; reserved_strawberries: number;
  created_at: string; updated_at: string; completed_at: string | null;
}
export interface NovelCharacter {
  id: string; name: string; role: string; age: string; appearance: string; personality: string; motivation: string;
  [key: string]: unknown;
}
export interface NovelCompass {
  title: string; logline: string; theme: string; core_conflict: string;
  protagonist: { name: string; want: string; need: string };
  candidate_endings: { summary: string; [key: string]: unknown }[];
  main_threads: { id: string; name: string; description: string; [key: string]: unknown }[];
  target: NovelTarget; seed_idea?: string;
  [key: string]: unknown;
}
export interface NovelBible {
  version: number; compass?: NovelCompass | null;
  locked: {
    characters: NovelCharacter[]; world_rules: string[];
    style_guide: { pov: string; tense: string; voice: string; banned_phrases: string[]; [key: string]: unknown };
    adaptation: NovelCreateInput["adaptation"]; [key: string]: unknown;
  };
  dynamic: {
    character_states: Record<string, { location: string; condition: string; knows: string[]; relationships: Record<string, string>; [key: string]: unknown }>;
    foreshadowing: { id: string; description: string; importance: string; status: string; planted_chapter: number; resolved_chapter?: number; note?: string; [key: string]: unknown }[];
    chapter_summaries: { chapter: number; title: string; summary: string; [key: string]: unknown }[];
    arc_summaries?: { start_chapter?: number; end_chapter?: number; summary?: string; [key: string]: unknown }[];
    timeline: string[]; used_beats: string[]; [key: string]: unknown;
  };
  [key: string]: unknown;
}
export interface NovelChapterSummary { chapter: number; title: string | null; status: string; words: number; flags: string[]; edited_by_user: boolean }
export interface NovelBeatSheet {
  title: string; chapter_goal: string; advances_threads: string[]; characters: string[];
  scenes: { location: string; summary: string; [key: string]: unknown }[]; beats: string[];
  opening_hook: string; ending_hook: string;
  foreshadowing_plant: { description: string; importance: string; [key: string]: unknown }[];
  foreshadowing_resolve: string[]; [key: string]: unknown;
}
export interface NovelDecision {
  beat_sheet: NovelBeatSheet; rationale: string; ending_status: string;
  objection_responses: { objection_id: string; response: string; decision?: string; [key: string]: unknown }[];
  alternative_responses?: { alternative_id: string; decision: "adopt" | "partial" | "reject"; response: string; [key: string]: unknown }[];
  user_note_responses: { note_id: string; response: string; adopted: boolean; [key: string]: unknown }[];
  [key: string]: unknown;
}
export interface NovelMeeting {
  mode?: string; plan?: NovelDecision; decision?: NovelDecision;
  brief?: { user_notes?: { id: string; text: string; [key: string]: unknown }[]; [key: string]: unknown };
  critiques?: { author: string; author_name: string; keep: string; alternative?: string; objections: { severity: string; target: string; problem: string; suggestion: string; [key: string]: unknown }[]; [key: string]: unknown }[];
  objections?: { id: string; author: string; author_name: string; alternative?: string; severity?: string; target?: string; problem?: string; suggestion?: string; objection?: string; [key: string]: unknown }[];
  proposals?: Record<string, unknown>[]; [key: string]: unknown;
}
export interface NovelReviewIssue { category: string; problem: string; evidence: string; fix: string; blocking: boolean; [key: string]: unknown }
export interface NovelChapter extends Omit<NovelChapterSummary, "edited_by_user"> {
  novel_id: string; body: string | null; meeting: NovelMeeting;
  review: { issues: NovelReviewIssue[]; dropped_issues: Record<string, unknown>[]; passed?: boolean; [key: string]: unknown }[];
  review_summary: { retained: number; discarded: number }; archive: Record<string, unknown>;
  edited_by_user: number | boolean; created_at: string; updated_at: string;
}
export interface NovelDetail extends NovelSummary {
  config: NovelCreateInput & Record<string, unknown>; compass: NovelCompass | null; bible: NovelBible | null;
  chapters: NovelChapterSummary[]; pending_gate: string | null; pending_notes: number; last_error: string | null;
}
export interface NovelNote { id: number; text: string; status: "pending" | "delivered"; delivered_chapter: number | null; created_at: string; adopted: boolean | null; response: string | null }
export interface NovelCatalog {
  agents: { id: string; name: string; category: string; required: boolean; description: string }[];
  models: { id: string; price: { input: number; output: number } }[];
  allowed_models: Record<string, string[]>;
  byok: { provider: string; model: string; model_spec?: string } | null; notice: string;
}
export interface NovelEstimate { per_chapter: { min: number; max: number }; total: { min: number; max: number }; method: string }
export interface NovelSetupPatch { compass?: Partial<NovelCompass>; locked?: Partial<NovelBible["locked"]> }
export type NovelAction = "setup/approve" | "plan/approve" | "plan/redo" | "continue" | "pause" | "resume" | "end/confirm" | "end/reject";
type Options = { signal?: AbortSignal };
const bookPath = (id: string) => `${API_BASE}/novels/${encodeURIComponent(id)}`;
const json = (method: string, body: unknown, signal?: AbortSignal): RequestInit => ({ method, signal, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

export const listNovels = (signal?: AbortSignal) => apiJson<NovelSummary[]>(`${API_BASE}/novels`, { signal });
export const getNovel = (id: string, signal?: AbortSignal) => apiJson<NovelDetail>(bookPath(id), { signal });
export const getNovelChapter = (id: string, chapter: number, signal?: AbortSignal) => apiJson<NovelChapter>(`${bookPath(id)}/chapters/${chapter}`, { signal });
export async function getNovelBible(id: string, signal?: AbortSignal): Promise<NovelBible | null> {
  // A book still generating its setup legitimately has no bible yet.
  const response = await apiFetch(`${bookPath(id)}/bible`, { signal });
  const data = await response.json();
  if (!response.ok) throw new ApiError(typeof data?.detail === "string" ? data.detail : "故事圣经暂不可用，请稍后重试。", response.status);
  return data as NovelBible | null;
}
export const getNovelNotes = (id: string, signal?: AbortSignal) => apiJson<NovelNote[]>(`${bookPath(id)}/notes`, { signal });
export const getNovelCatalog = (signal?: AbortSignal) => apiJson<NovelCatalog>(`${API_BASE}/novels/catalog`, { signal });
export const getNovelBalance = (signal?: AbortSignal) => apiJson<{ username: string; balance: number }>(`${API_BASE}/strawberry`, { signal });
export const estimateNovel = (input: NovelCreateInput, signal?: AbortSignal) => apiJson<NovelEstimate>(`${API_BASE}/novels/estimate`, json("POST", input, signal));
export const createNovel = (input: NovelCreateInput, signal?: AbortSignal) => apiJson<NovelDetail>(`${API_BASE}/novels`, json("POST", input, signal));
export const patchNovel = (id: string, input: NovelPatchInput, signal?: AbortSignal) => apiJson<NovelDetail>(bookPath(id), json("PATCH", input, signal));
const action = (id: string, path: NovelAction, body?: unknown, signal?: AbortSignal) => apiJson<NovelDetail>(`${bookPath(id)}/${path}`, json("POST", body, signal));
export const approveNovelSetup = (id: string, input: NovelSetupPatch, signal?: AbortSignal) => action(id, "setup/approve", input, signal);
export const approveNovelPlan = (id: string, beat_sheet?: NovelBeatSheet, signal?: AbortSignal) => action(id, "plan/approve", beat_sheet ? { beat_sheet } : {}, signal);
export const redoNovelPlan = (id: string, text: string, signal?: AbortSignal) => action(id, "plan/redo", { text }, signal);
export const continueNovel = (id: string, signal?: AbortSignal) => action(id, "continue", undefined, signal);
export const pauseNovel = (id: string, signal?: AbortSignal) => action(id, "pause", undefined, signal);
export const resumeNovel = (id: string, signal?: AbortSignal) => action(id, "resume", undefined, signal);
export const confirmNovelEnd = (id: string, signal?: AbortSignal) => action(id, "end/confirm", undefined, signal);
export const rejectNovelEnd = (id: string, body: { extend_chapters: number; text?: string }, signal?: AbortSignal) => action(id, "end/reject", body, signal);
export const addNovelNote = (id: string, text: string, signal?: AbortSignal) => apiJson<{ status: "pending" }>(`${bookPath(id)}/notes`, json("POST", { text }, signal));
export const updateNovelChapter = (id: string, chapter: number, body: string, signal?: AbortSignal) => apiJson<{ rearchiving: boolean; message: string }>(`${bookPath(id)}/chapters/${chapter}`, json("PUT", { body }, signal));
export const deleteNovel = (id: string, signal?: AbortSignal) => apiJson<{ deleted: boolean }>(bookPath(id), { method: "DELETE", signal });
export async function exportNovel(id: string, signal?: AbortSignal): Promise<Blob> {
  const response = await apiFetch(`${bookPath(id)}/export`, { signal });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(typeof data?.detail === "string" ? data.detail : "导出失败，请稍后重试。", response.status);
  }
  if (!response.headers.get("Content-Type")?.toLowerCase().includes("text/markdown")) throw new Error("导出内容格式不正确，请稍后重试。");
  return response.blob();
}
export const novelApi = {
  detail: (id: string, options?: Options) => getNovel(id, options?.signal),
  chapter: (id: string, number: number, options?: Options) => getNovelChapter(id, number, options?.signal),
  bible: (id: string, options?: Options) => getNovelBible(id, options?.signal),
  notes: (id: string, options?: Options) => getNovelNotes(id, options?.signal),
  catalog: (options?: Options) => getNovelCatalog(options?.signal),
  action: (id: string, path: NovelAction, body?: unknown, options?: Options) => action(id, path, body, options?.signal),
  patch: (id: string, input: NovelPatchInput, options?: Options) => patchNovel(id, input, options?.signal),
  remove: (id: string, options?: Options) => deleteNovel(id, options?.signal),
  export: (id: string, options?: Options) => exportNovel(id, options?.signal),
};
export function novelStatusLabel(book: Pick<NovelSummary, "status" | "pause_reason">): string {
  if (book.status === "paused") return ({ user: "已暂停", budget_80: "预算快用完", insufficient_strawberries: "草莓不足", byok_unavailable: "自带模型不可用", decision_invalid: "推演卡住了", step_failed: "推演卡住了", locked_conflict: "与设定冲突", daily_cap: "今日额度已用完", server_restart_failed: "恢复失败" } as Record<string, string>)[book.pause_reason ?? "user"] ?? "已暂停";
  return ({ setup_running: "立项中", awaiting_setup: "等你确认立项", running: "写作中", awaiting_review: "等你审阅", awaiting_plan: "等你确认细纲", awaiting_end: "等你确认完结", completed: "已完结", failed: "出错了" } as Record<string, string>)[book.status] ?? book.status;
}
export function novelErrorMessage(error: unknown, access = false): string {
  // Keep the former access argument compatible; HTTP detail now determines
  // the same workshop-wide mapping on every page and operation.
  void access;
  if (error instanceof ApiError && error.status === 404 && error.message.trim() === "Not Found") return "小说工坊尚未开放";
  if (error instanceof ApiError && error.status === 403) return "你的账号暂未开通小说工坊";
  const message = error instanceof Error ? error.message : "连接失败，请稍后重试。";
  return /[\u3400-\u9fff]/.test(message) ? message : "请求未完成，请稍后重试。";
}
export const novelHref = (path: string, embedded: boolean) => embedded ? `${path}${path.includes("?") ? "&" : "?"}embed=1` : path;
export const novelModelLabel = (id: string) => ({ "dashscope:qwen3.8-max": "千问 3.8 Max", "deepseek:deepseek-flash": "DeepSeek Flash", "ark:doubao-seed-2-1-pro-260915": "豆包 Seed 2.1 Pro", "byok:self": "我的模型" } as Record<string, string>)[id] ?? id;
export function novelModelOptions(catalog: NovelCatalog, role: string) {
  const allowed = catalog.allowed_models[role] ?? [...catalog.models.map(model => model.id), "byok:self"];
  return allowed.flatMap(id => {
    if (id === "byok:self") return catalog.byok ? [{ value: id, label: `我的模型（${({ anthropic: "Anthropic", dashscope: "千问", deepseek: "DeepSeek" } as Record<string, string>)[catalog.byok.provider] ?? catalog.byok.provider}·${catalog.byok.model}）· 不扣草莓` }] : [];
    const model = catalog.models.find(item => item.id === id);
    return model ? [{ value: id, label: `${novelModelLabel(id)} · 每千 token 输入/输出约 ${model.price.input}/${model.price.output} 草莓` }] : [];
  });
}

export function displayNovelChapterTitle(title: string | null | undefined): string {
  const original = title ?? "";
  const stripped = original.replace(/^\s*第\s*[0-9一二三四五六七八九十百零〇两]+\s*章(?=[\s\p{P}]|$)[\s\p{P}]*/u, "");
  return stripped || original;
}

export function formatNovelDate(value: string): string {
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value) ? `${value.replace(" ", "T")}Z` : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}
