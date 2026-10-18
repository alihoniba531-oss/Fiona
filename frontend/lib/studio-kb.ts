import { apiJson } from "@/lib/agents";
import { API_BASE } from "@/lib/config";

export type KbCardType = "grammar" | "scene" | "model" | "negative";
export type KbSceneType =
  | "dialogue" | "establishing" | "confrontation" | "fight" | "chase" | "reveal" | "monologue"
  | "flashback" | "ensemble" | "montage" | "twist" | "intimacy" | "phone-call" | "process-closeup"
  | "explainer" | "scare" | "investigation";
export type KbPosition = "opening" | "body" | "ending";
export type KbPace = "fast" | "mid" | "slow";
export type KbRealism = "photoreal" | "anime" | "3d";
export type KbSetting = "interior" | "exterior" | "mixed";
export type KbSensitive = "face_closeup" | "structure" | "material" | "giant_offscreen" | "ip_risk";
export type KbVideoModel = "wan" | "seedance";
export type KbMode = "with_kb" | "without_kb";
export type KbReviewProvider = "claude" | "qwen" | "deepseek" | "off";
export type KbExemplarKind = "good" | "bad";

export interface KbSceneTags {
  scene_type: KbSceneType;
  position: KbPosition;
  pace: KbPace;
  emotion: string;
  cast_count: number;
  realism: KbRealism;
  setting: KbSetting;
  sensitive: KbSensitive[];
}

export interface KbSource { name: string; license: string; ref?: string | null }
export interface KbCardSummary { id: string; type: KbCardType; title: string; summary: string; tags?: string[] }
export interface KbGrammarEntry { name: string; definition?: string; safe_prompt?: string }
export interface KbPacingBand { shots_per_min?: number[]; shot_seconds?: number[] }
export interface KbPacing { fast?: KbPacingBand; mid?: KbPacingBand; slow?: KbPacingBand }
export interface KbRisk { risk: string; fallback: string }
export interface KbLintRule { id?: string; when?: Record<string, unknown>; pattern?: string; level?: string; message?: string }
export interface KbCard extends KbCardSummary {
  sources?: KbSource[];
  version?: number;
  definition?: string;
  narrative_use?: string;
  safe_prompt?: string;
  avoid?: string[];
  entries?: KbGrammarEntry[];
  related?: string[];
  scene_type?: KbSceneType;
  position?: "opening" | "ending";
  signals?: string[];
  beats?: string[];
  coverage?: string[];
  pacing?: KbPacing;
  camera?: string[];
  sound?: string[];
  ai_risks?: KbRisk[];
  example?: string;
  related_grammar?: string[];
  related_negative?: string[];
  model?: string;
  style?: string;
  facts?: string[];
  portrait_gate?: string;
  copyright?: string;
  motion_risks?: string[];
  prompt_syntax?: string[];
  max_characters?: number;
  lint_rules?: KbLintRule[];
  wrong?: string;
  right?: string;
  why?: string;
  evidence?: string;
  applies_to?: { scene_type?: string[]; model?: string[] };
  lint_pattern?: string;
}

export interface KbExemplarShot {
  shot_size?: string; angle?: string; camera?: string; action?: string;
  video_prompt?: string; first_frame_prompt?: string; duration_s?: number;
  [key: string]: unknown;
}
export interface KbExemplar {
  id: string;
  project_id?: string | null;
  source: string;
  scene_type: string;
  kind: KbExemplarKind;
  reason: string;
  shot?: KbExemplarShot | null;
  shot_json?: string | null;
  keyframe_asset_id?: string | null;
  video_model?: string | null;
  qc_json?: string | null;
  cost_cny?: number | string | null;
  tags?: string[];
  tags_json?: string | null;
  created_at: string;
  archived?: boolean | number;
}
export interface KbExemplarPatch { kind?: KbExemplarKind; reason?: string; archived?: boolean }

export interface KbStatRow {
  scene_type: string;
  episodes?: number;
  shots?: number;
  avg_shot_s?: number;
  shot_size_json?: string;
  camera_json?: string;
  shot_size?: Record<string, number>;
  camera?: Record<string, number>;
  updated_at?: string;
}
export interface KbStats {
  ready: boolean;
  episodes: number;
  shots?: number;
  avg_shot_s?: number;
  scene_types?: KbStatRow[];
  rows?: KbStatRow[];
  by_scene_type?: KbStatRow[];
  stats?: KbStatRow[];
}

export type KbCurrency = "CNY" | "USD";
export interface KbQuoteLine {
  item_id?: string | null; name: string; versions?: number; unit?: number; est: number; currency: KbCurrency;
}
export interface KbQuote {
  id: string;
  kind: "kb_trial" | string;
  items: KbQuoteLine[];
  total: number | null;
  currency: KbCurrency | "mixed";
  totals: { CNY: number; USD: number };
  expires_at: string;
}

export interface KbTrialInput {
  scene_text: string;
  tags: KbSceneTags;
  target_seconds: number;
  video_model: KbVideoModel;
  modes: KbMode[];
}

export interface KbShot {
  no?: number; beat?: string; shot_size?: string; angle?: string; camera?: string; action?: string;
  first_frame_prompt?: string; video_prompt?: string; dialogue?: string; sound_intent?: string;
  duration_s?: number; sensitive?: string[]; basis?: string[];
}
export interface KbLint { shot_no?: number; rule_id?: string; level?: "warn" | "info"; message?: string }
export interface KbReviewIssue {
  severity?: "must" | "should" | string; kind?: string; where?: string; source_ref?: string | null;
  problem?: string; suggestion?: string;
}
export interface KbReview {
  provider?: string; model?: string; status?: string; verdict?: string;
  summary?: string; issues?: KbReviewIssue[];
}
export interface KbTrialMode {
  mode?: KbMode;
  status?: string;
  shots?: KbShot[];
  template_id?: string | null;
  deviations?: string;
  card_ids?: string[];
  lint?: KbLint[];
  lint_warnings?: KbLint[];
  chars?: number;
  injected_chars?: number;
  kb_chars?: number;
  review?: KbReview | null;
  error_code?: string | null;
  error_message?: string | null;
  model_card_missing?: boolean;
}
export interface KbTrial {
  id: string;
  status?: string;
  scene_text?: string;
  modes?: Partial<Record<KbMode, KbTrialMode>> | KbMode[];
  results?: Partial<Record<KbMode, KbTrialMode>>;
  review?: Partial<Record<KbMode, KbReview | null>>;
  with_kb?: KbTrialMode;
  without_kb?: KbTrialMode;
  error_code?: string | null;
  error_message?: string | null;
}
export interface KbStartedTrial extends KbTrial { trial_id?: string }
export interface KbReviewProviderState { review_provider: KbReviewProvider; brain_provider: string; same_as_director: boolean }

const root = `${API_BASE}/studio`;
const projectPath = (id: string) => `${root}/projects/${encodeURIComponent(id)}`;
const json = (body: unknown, signal?: AbortSignal): RequestInit => ({ method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const write = (body: unknown, method: "PATCH", signal?: AbortSignal): RequestInit => ({ ...json(body, signal), method });
function query(values: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) search.set(key, value);
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const listKbCards = (type?: KbCardType | "", q?: string, signal?: AbortSignal) =>
  apiJson<KbCardSummary[]>(`${root}/kb/cards${query({ type, q })}`, { signal, cache: "no-store" });
export const getKbCard = (id: string, signal?: AbortSignal) =>
  apiJson<KbCard>(`${root}/kb/cards/${encodeURIComponent(id)}`, { signal, cache: "no-store" });
export const listKbExemplars = (filters: { scene_type?: string; kind?: KbExemplarKind | "" }, signal?: AbortSignal) =>
  apiJson<KbExemplar[]>(`${root}/kb/exemplars${query(filters)}`, { signal, cache: "no-store" });
export const patchKbExemplar = (id: string, patch: KbExemplarPatch, signal?: AbortSignal) =>
  apiJson<KbExemplar>(`${root}/kb/exemplars/${encodeURIComponent(id)}`, write(patch, "PATCH", signal));
export const getKbStats = (signal?: AbortSignal) => apiJson<KbStats>(`${root}/kb/stats`, { signal, cache: "no-store" });

export const quoteKbTrial = (projectId: string, input: KbTrialInput, signal?: AbortSignal) =>
  apiJson<KbQuote>(`${projectPath(projectId)}/kb/trial/quote`, json({
    scene_text: input.scene_text, tags: input.tags, target_seconds: input.target_seconds,
    video_model: input.video_model, modes: input.modes,
  }, signal));
export const startKbTrial = (projectId: string, quoteId: string, signal?: AbortSignal) =>
  apiJson<KbStartedTrial>(`${projectPath(projectId)}/kb/trial/start`, json({ quote_id: quoteId }, signal));
export const getKbTrial = (projectId: string, trialId: string, signal?: AbortSignal) =>
  apiJson<KbTrial>(`${projectPath(projectId)}/kb/trials/${encodeURIComponent(trialId)}`, { signal, cache: "no-store" });
export const getKbReviewProvider = (projectId: string, signal?: AbortSignal) =>
  apiJson<KbReviewProviderState>(`${projectPath(projectId)}/review-provider`, { signal, cache: "no-store" });
export const setKbReviewProvider = (projectId: string, provider: KbReviewProvider, signal?: AbortSignal) =>
  apiJson<KbReviewProviderState>(`${projectPath(projectId)}/review-provider`, write({ review_provider: provider }, "PATCH", signal));

export const kbCardTypes: KbCardType[] = ["grammar", "scene", "model", "negative"];
export const kbCardTypeLabel = (type: KbCardType) => ({ grammar: "语法", scene: "场景模板", model: "模型能力", negative: "反例" })[type];
export const kbModeLabel = (mode: KbMode) => mode === "with_kb" ? "带知识库" : "不带知识库";
export const kbExemplarKindLabel = (kind: KbExemplarKind) => kind === "good" ? "好例" : "反例";
export const kbExemplarKindOptions: KbExemplarKind[] = ["good", "bad"];

export const kbSceneTypeOptions: { id: KbSceneType; label: string }[] = [
  { id: "dialogue", label: "对话（两人静态）" },
  { id: "establishing", label: "环境建立 / 定场" },
  { id: "confrontation", label: "争执对峙" },
  { id: "fight", label: "打斗" },
  { id: "chase", label: "追逐" },
  { id: "reveal", label: "悬疑揭示" },
  { id: "monologue", label: "情感独白 / 内心戏" },
  { id: "flashback", label: "回忆闪回" },
  { id: "ensemble", label: "群戏" },
  { id: "montage", label: "过场蒙太奇" },
  { id: "twist", label: "反转" },
  { id: "intimacy", label: "告白 / 亲密" },
  { id: "phone-call", label: "电话 / 远程对话" },
  { id: "process-closeup", label: "工艺操作 / 动作特写" },
  { id: "explainer", label: "讲解科普（竖屏）" },
  { id: "scare", label: "惊吓 / 恐怖" },
  { id: "investigation", label: "调查 / 搜索" },
];
export const kbSceneTypeLabel = (value: string) => kbSceneTypeOptions.find(option => option.id === value)?.label ?? value;

export const kbPositionOptions: { id: KbPosition; label: string }[] = [
  { id: "body", label: "片中（默认）" }, { id: "opening", label: "开场钩子" }, { id: "ending", label: "结尾悬念" },
];
export const kbPositionLabel = (value: string) => kbPositionOptions.find(option => option.id === value)?.label ?? value;
export const kbPaceOptions: { id: KbPace; label: string }[] = [
  { id: "fast", label: "快" }, { id: "mid", label: "中" }, { id: "slow", label: "慢" },
];
export const kbPaceLabel = (value: string) => kbPaceOptions.find(option => option.id === value)?.label ?? value;
export const kbRealismOptions: { id: KbRealism; label: string }[] = [
  { id: "photoreal", label: "写实" }, { id: "anime", label: "动漫" }, { id: "3d", label: "3D" },
];
export const kbRealismLabel = (value: string) => kbRealismOptions.find(option => option.id === value)?.label ?? value;
export const kbSettingOptions: { id: KbSetting; label: string }[] = [
  { id: "interior", label: "室内" }, { id: "exterior", label: "室外" }, { id: "mixed", label: "室内外混合" },
];
export const kbSettingLabel = (value: string) => kbSettingOptions.find(option => option.id === value)?.label ?? value;
export const kbSensitiveOptions: { id: KbSensitive; label: string }[] = [
  { id: "face_closeup", label: "近脸" }, { id: "structure", label: "结构" }, { id: "material", label: "材质" },
  { id: "giant_offscreen", label: "画外巨物" }, { id: "ip_risk", label: "IP 风险" },
];
export const kbSensitiveLabel = (value: string) => kbSensitiveOptions.find(option => option.id === value)?.label ?? value;
export const kbVideoModelOptions: { id: KbVideoModel; label: string }[] = [
  { id: "wan", label: "万相" }, { id: "seedance", label: "Seedance" },
];

export const kbReviewProviderOptions: { id: KbReviewProvider; label: string }[] = [
  { id: "claude", label: "Claude" }, { id: "qwen", label: "千问 3.8 Max" },
  { id: "deepseek", label: "DeepSeek" }, { id: "off", label: "关闭" },
];
export const kbReviewProviderLabel = (value: string) => kbReviewProviderOptions.find(option => option.id === value)?.label ?? value;
export const kbReviewStatusLabel = (value: string | undefined) => ({
  queued: "审核排队中", running: "审核中", succeeded: "审核已完成", failed: "审核失败",
  uncertain: "审核结果不确定", rejected: "审核被拒绝", invalid_output: "审核输出不合格",
} as Record<string, string>)[value ?? ""] ?? (value || "审核状态未知");
export const kbTrialStatusLabel = (value: string | undefined) => ({
  queued: "排队中", running: "拆镜中", submitting: "提交中", succeeded: "已完成", done: "已完成",
  partial: "部分完成", failed: "失败", cancelled: "已取消", rejected: "被拒绝", expired: "已过期",
  not_started: "尚未开始", open: "待确认",
} as Record<string, string>)[value ?? ""] ?? (value || "状态未知");

export function kbTrialMode(trial: KbTrial | null, mode: KbMode): KbTrialMode | null {
  if (!trial) return null;
  const modes = trial.modes;
  const nested = (Array.isArray(modes) ? null : modes?.[mode]) ?? trial.results?.[mode] ?? trial[mode] ?? null;
  if (!nested) return null;
  const review = nested.review ?? trial.review?.[mode] ?? null;
  return review === nested.review ? nested : { ...nested, review };
}
export function kbInjectedChars(mode: KbTrialMode | null): number | null {
  if (!mode) return null;
  const value = mode.injected_chars ?? mode.kb_chars ?? mode.chars;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
export function kbLintWarnings(mode: KbTrialMode | null): KbLint[] {
  if (!mode) return [];
  return Array.isArray(mode.lint) ? mode.lint : Array.isArray(mode.lint_warnings) ? mode.lint_warnings : [];
}
export function kbShotBasis(shot: KbShot): string[] {
  return Array.isArray(shot.basis) ? shot.basis.filter((value): value is string => typeof value === "string") : [];
}
export function kbTrialInFlight(trial: KbTrial | null): boolean {
  if (!trial) return false;
  const inflight = ["queued", "running", "submitting", "pending"];
  const modes = [kbTrialMode(trial, "with_kb"), kbTrialMode(trial, "without_kb")];
  if (modes.some(mode => mode && inflight.includes(mode.status ?? ""))) return true;
  if (inflight.includes(trial.status ?? "")) return true;
  if (modes.every(Boolean)) return false;
  return !["done", "partial", "failed", "cancelled", "expired", "rejected"].includes(trial.status ?? "");
}
export function kbRange(values: number[] | undefined, unit: string): string {
  if (!Array.isArray(values) || values.length === 0) return "—";
  if (values.length === 1) return `${values[0]} ${unit}`;
  return `${values[0]}–${values[values.length - 1]} ${unit}`;
}
export function parseKbJson<T>(value: string | T | null | undefined, fallback: T): T {
  if (value == null) return fallback;
  if (typeof value !== "string") return value as T;
  try { return JSON.parse(value) as T; } catch { return fallback; }
}
