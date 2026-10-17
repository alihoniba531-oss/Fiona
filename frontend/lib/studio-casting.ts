import { apiJson } from "@/lib/agents";
import { API_BASE } from "@/lib/config";

export type CastingResolution = "480P" | "720P" | "1080P";
export type CastingVideoModel = "wan" | "seedance";
export type CastingLanguage = "zh" | "en";
export type CastingRealism = "photoreal" | "anime" | "3d";
export type CastingItemKind = "character" | "location" | "prop";
export type CastingItemStatus = "pending" | "approved" | "skipped";
export type CastingVoiceEngine = "cosyvoice" | "edge-tts";
export type CastingVoiceRole = "dialogue" | "narration";
export type CastingJobKind = "image" | "tts" | "brain";
export type CastingQuoteKind = "casting_style" | "casting_sheets";
export type CastingCurrency = "CNY" | "USD";

export interface CastingSetup {
  aspect: "16:9" | "9:16"; resolution: CastingResolution; video_model: CastingVideoModel;
  language: CastingLanguage; sheet_size: "2560x1440"; confirmed_at: string;
}
export type CastingSetupInput = Pick<CastingSetup, "resolution" | "video_model" | "language">;
export interface CastingStyleProposal { name: string; visual_style: string; palette: string; camera: string; lighting: string; rationale: string }
export interface CastingStyleChoice extends CastingStyleProposal { realism: CastingRealism; source: "proposal" | "custom"; proposal_index: number | null }
export type CastingStyleUpdate = { realism: CastingRealism } & ({ proposal_index: number } | { custom: CastingStyleProposal });
export interface CastingJob {
  id: string; kind: CastingJobKind; item_id: string | null; status: string; error_code: string | null; error_message: string | null;
  reserved_amount: number; actual_amount: number | null; currency: CastingCurrency; created_at: string;
}
export interface CastingVersion { asset_id: string; version_no: number; created_at: string; archived: boolean; prompt: string }
export interface CastingVoiceSpec { engine: CastingVoiceEngine; voice: string; rate: number | string; pitch: number | string; fx: string | null; role: CastingVoiceRole }
export interface CastingAudition { asset_id: string; spec: CastingVoiceSpec; text: string; duration_s: number; measured_lufs: number; created_at: string; archived: boolean }
export interface CastingVoice { spec: CastingVoiceSpec | null; approved_asset_id: string | null; auditions: CastingAudition[] }
export interface CastingItem {
  id: string; bible_id: string; kind: CastingItemKind; name: string; role: string; appearance: string; description: string;
  needs_author: boolean; orphaned: boolean; status: CastingItemStatus; locked_features: string; extra_prompt: string;
  reference_asset_ids: string[]; approved_asset_id: string | null; versions: CastingVersion[]; voice: CastingVoice | null;
}
export interface CastingItemPatch { locked_features?: string; extra_prompt?: string; reference_asset_ids?: string[] }
export interface CastingStyleState { chosen: CastingStyleChoice | null; proposals: CastingStyleProposal[]; proposal_job: CastingJob | null }
export interface CastingG1 { approved: boolean; total: number; done: number; skipped: number }
export interface CastingPrices { seedream_cny: number; cosyvoice_cny_per_10k_chars: number }
export interface CastingState {
  g0_approved: boolean; setup: CastingSetup | null; style: CastingStyleState; items: CastingItem[];
  g1: CastingG1; jobs: CastingJob[]; prices: CastingPrices;
}
export interface CastingQuoteLine { item_id: string | null; name: string; versions: number; unit: number; est: number }
export interface CastingQuote { id: string; kind: CastingQuoteKind; items: CastingQuoteLine[]; total: number; currency: CastingCurrency; expires_at: string }
export interface CastingVoiceOption { engine: CastingVoiceEngine; voice: string; label: string; lang: CastingLanguage; gender: "male" | "female"; note: string }
export interface CastingVoiceCatalog { voices: CastingVoiceOption[]; fx: Record<string, string[]> }
export interface CastingSheetRequest { item_id: string; versions: number; extra_prompt?: string; reference_asset_ids?: string[]; derive_from_approved?: boolean }
export interface CastingAuditionVariant { engine: CastingVoiceEngine; voice: string; rate: number | string; pitch: number | string; fx: string | null; role: CastingVoiceRole }
export interface CastingAuditionRequest { item_id: string; text: string; variants: CastingAuditionVariant[] }
export type CastingMutate = (action: (signal: AbortSignal) => Promise<unknown>, message?: string) => Promise<void>;

const root = `${API_BASE}/studio`;
const projectPath = (id: string) => `${root}/projects/${encodeURIComponent(id)}`;
const itemPath = (id: string) => `${root}/casting/items/${encodeURIComponent(id)}`;
const post = (body: unknown, signal?: AbortSignal): RequestInit => ({ method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const write = (body: unknown, method: "PUT" | "PATCH", signal?: AbortSignal): RequestInit => ({ ...post(body, signal), method });

export const getStudioCasting = (id: string, signal?: AbortSignal) => apiJson<CastingState>(`${projectPath(id)}/casting`, { signal, cache: "no-store" });
export const putStudioCastingSetup = (id: string, input: CastingSetupInput, signal?: AbortSignal) => apiJson<CastingState>(`${projectPath(id)}/casting/setup`, write(input, "PUT", signal));
export const quoteStudioCastingStyle = (id: string, signal?: AbortSignal) => apiJson<CastingQuote>(`${projectPath(id)}/casting/style/quote`, post({}, signal));
export const startStudioCastingStyle = (id: string, quoteId: string, signal?: AbortSignal) => apiJson<CastingState>(`${projectPath(id)}/casting/style/start`, post({ quote_id: quoteId }, signal));
export const putStudioCastingStyle = (id: string, input: CastingStyleUpdate, signal?: AbortSignal) => apiJson<CastingState>(`${projectPath(id)}/casting/style`, write(input, "PUT", signal));
export const patchCastingItem = (itemId: string, input: CastingItemPatch, signal?: AbortSignal) => apiJson<CastingItem>(itemPath(itemId), write(input, "PATCH", signal));
export const approveCastingItem = (itemId: string, assetId: string, signal?: AbortSignal) => apiJson<CastingItem>(`${itemPath(itemId)}/approve`, post({ asset_id: assetId }, signal));
export const skipCastingItem = (itemId: string, signal?: AbortSignal) => apiJson<CastingItem>(`${itemPath(itemId)}/skip`, post({}, signal));
export const reopenCastingItem = (itemId: string, signal?: AbortSignal) => apiJson<CastingItem>(`${itemPath(itemId)}/reopen`, post({}, signal));
export const archiveCastingAsset = (assetId: string, signal?: AbortSignal) => apiJson<{ ok: true }>(`${root}/casting/assets/${encodeURIComponent(assetId)}/archive`, post({}, signal));
export const quoteCastingSheets = (id: string, items: CastingSheetRequest[], signal?: AbortSignal) => apiJson<CastingQuote>(`${projectPath(id)}/casting/sheets/quote`, post({ items }, signal));
export const startCastingSheets = (id: string, quoteId: string, signal?: AbortSignal) => apiJson<CastingState>(`${projectPath(id)}/casting/sheets/start`, post({ quote_id: quoteId }, signal));
export const auditionCastingVoices = (id: string, input: CastingAuditionRequest, signal?: AbortSignal) => apiJson<CastingState>(`${projectPath(id)}/casting/voices/audition`, post(input, signal));
export const approveCastingVoice = (itemId: string, assetId: string, signal?: AbortSignal) => apiJson<CastingItem>(`${itemPath(itemId)}/voice/approve`, post({ asset_id: assetId }, signal));
export const getCastingVoiceCatalog = (signal?: AbortSignal) => apiJson<CastingVoiceCatalog>(`${root}/casting/voice-catalog`, { signal, cache: "no-store" });

export const castingResolutionOptions: CastingResolution[] = ["480P", "720P", "1080P"];
export const castingResolutionPrices: Record<CastingResolution, number> = { "480P": 0.3, "720P": 0.6, "1080P": 1.2 };
export const castingResolutionPriceNote = "万相 ¥0.3 / ¥0.6 / ¥1.2 每秒";
export const castingSheetSize = "2560x1440";
export const castingVideoModelLabel = (model: CastingVideoModel) => ({ wan: "万相", seedance: "Seedance" })[model];
export const castingLanguageLabel = (language: CastingLanguage) => ({ zh: "中文", en: "英文" })[language];
export const castingRealismLabel = (realism: CastingRealism) => ({ photoreal: "写实", anime: "动漫", "3d": "3D" })[realism];
export const castingRealismOptions: CastingRealism[] = ["photoreal", "anime", "3d"];
export const castingItemKindLabel = (kind: CastingItemKind) => ({ character: "人物", location: "场景", prop: "道具" })[kind];
export const castingItemStatusLabel = (status: CastingItemStatus) => ({ pending: "待定妆", approved: "已确认", skipped: "不需要定妆" })[status];
export const castingVoiceEngineLabel = (engine: CastingVoiceEngine) => ({ cosyvoice: "CosyVoice", "edge-tts": "edge-tts" })[engine];
export const castingVoiceRoleLabel = (role: CastingVoiceRole) => ({ dialogue: "对白", narration: "旁白" })[role];
export const castingFxLabel = (fx: string | null) => (!fx ? "无特效" : ({ robot: "机器人", beast: "巨兽", inner: "内心独白" } as Record<string, string>)[fx.split(":")[0]] + " " + fx.split(":")[1]);
export const castingQuoteKindLabel = (kind: CastingQuoteKind) => ({ casting_style: "风格提案", casting_sheets: "定妆出图" })[kind];
export const castingJobStatusLabel = (status: string) => ({
  queued: "排队中", submitting: "提交中", submitted: "已提交", running: "进行中", succeeded: "已完成", downloaded: "已完成",
  rejected: "被拒绝（未扣费）", uncertain: "结果不确定", failed: "失败", filtered: "被内容审核拦截（未扣费）", cancelled: "已取消", released: "已释放（确认未扣费）",
} as Record<string, string>)[status] ?? status;
export const castingInflightStatuses = ["queued", "submitting", "submitted", "running"];
export const castingJobInflight = (job: CastingJob | null | undefined) => !!job && castingInflightStatuses.includes(job.status);
export const castingItemInflight = (jobs: CastingJob[], itemId: string) => jobs.filter(job => job.kind === "image" && job.item_id === itemId && castingInflightStatuses.includes(job.status));
export const castingItemFinished = (jobs: CastingJob[], itemId: string) => jobs.filter(job => job.kind === "image" && job.item_id === itemId && ["uncertain", "rejected", "failed", "filtered"].includes(job.status));
export const castingInflight = (state: CastingState | null) => !!state && (castingJobInflight(state.style.proposal_job) || state.jobs.some(castingJobInflight));
export const formatCastingMoney = (amount: number, currency: CastingCurrency) => `${currency === "CNY" ? "¥" : "$"}${Number(amount).toFixed(4)}`;

export function formatCastingTime(value: string): string {
  const normalized = /[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value.replace(" ", "T")}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (number: number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function castingAuditionCost(text: string, language: CastingLanguage, prices: CastingPrices): { free: boolean; amount: number } {
  if (language === "en") return { free: true, amount: 0 };
  const chars = Array.from(text).length;
  return { free: false, amount: Math.max(0.01, Number(((chars / 10000) * prices.cosyvoice_cny_per_10k_chars).toFixed(4))) };
}
export const castingAuditionCostLabel = (text: string, language: CastingLanguage, prices: CastingPrices) => {
  const cost = castingAuditionCost(text, language, prices);
  return cost.free ? "免费" : `约 ¥${cost.amount.toFixed(2)}`;
};
export function castingDefaultAuditionText(item: CastingItem): string {
  const appearance = item.appearance.trim();
  const first = appearance.split(/[。！？!?\n]/).map(part => part.trim()).filter(Boolean)[0];
  if (first) return first.length > 40 ? `${first.slice(0, 40)}。` : `${first}。`;
  return `我是${item.name}。`;
}
export const castingVoiceSpecLabel = (spec: CastingVoiceSpec) => [castingVoiceEngineLabel(spec.engine), spec.voice, `语速 ${spec.rate}`, `音高 ${spec.pitch}`, castingFxLabel(spec.fx), castingVoiceRoleLabel(spec.role)].join(" · ");
export const castingItemVersions = (item: CastingItem) => item.versions.filter(version => !version.archived);
export const castingNeedsAppearance = (items: CastingItem[], ids: string[]) => items.some(item => ids.includes(item.id) && item.kind === "character" && item.needs_author);
