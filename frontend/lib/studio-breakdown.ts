import { ApiError, apiJson } from "@/lib/agents";
import { apiFetch } from "@/lib/auth";
import { API_BASE } from "@/lib/config";
import type { BrainCost, BrainProviderId } from "./studio";

export type BreakdownTask = "novel_complete" | "text_map" | "synopsis" | "episode_plan";
export type BreakdownStatus = "draft" | "running" | "partial" | "done" | "cancelled";
export type ChunkStatus = "blocked" | "queued" | "running" | "succeeded" | "failed" | "uncertain" | "rejected" | "invalid_output" | "released" | "cancelled";
export interface BreakdownChunk {
  id: string; no: number; task: BreakdownTask; status: ChunkStatus; provider: BrainProviderId; job_id: string | null;
  source: { label?: string; chapter_from?: number; chapter_to?: number; block_no?: number; start?: number; end?: number };
  warnings: string[]; cost?: BrainCost | null; totals?: Partial<Record<"CNY" | "USD", number>>; reserved_amount?: number; error_message?: string | null;
}
export interface BreakdownQuote {
  id: string; provider: BrainProviderId; expires_at: string; total_min: number; total_max: number;
  currency: "CNY" | "USD"; task_counts: Partial<Record<BreakdownTask, number>>; total_chunks: number;
}
export interface StudioBreakdown {
  id: string; status: BreakdownStatus; snapshot_no: number; outdated: boolean | number; chunks: BreakdownChunk[];
  retry_needed?: { label: string; status: ChunkStatus }[]; blocked_segments?: string[];
  synopsis: Record<string, unknown> | null; units_count: number; total_cost?: number | BrainCost | null;
  totals?: Partial<Record<"CNY" | "USD", number>>; settings?: Record<string, unknown>;
}
export type BibleKind = "character" | "location" | "prop";
export interface StudioBibleEntry {
  id: string; kind: BibleKind; name: string; aliases: string[]; role: string; description: string; appearance: string;
  appearance_source: "workshop" | "excerpt" | "author" | "none"; excerpt: string; needs_author: boolean | number;
  first_unit: number | null; first_appearance?: string; episodes: number[];
}
export type BibleFields = Pick<StudioBibleEntry, "name" | "aliases" | "role" | "description" | "appearance" | "needs_author">;
export interface StudioUnit { seq: number; label: string; summary?: string; start?: number; end?: number }
export interface StudioEpisode {
  id: string; no: number; title: string; unit_from: number; unit_to: number; change: string; hook: string; notes: string;
  target_min: number | null; target_max: number | null; effective_target_min?: number; effective_target_max?: number; est_seconds: number; est_shots: number;
  source_range: string; characters: string[]; warnings: string[];
}
export interface UnassignedUnits { unit_from: number; unit_to: number; source_range?: string; label?: string; units?: StudioUnit[] }
export interface StudioEpisodePlan {
  episodes: StudioEpisode[]; units: StudioUnit[]; unassigned: UnassignedUnits[]; uncovered?: UnassignedUnits[];
  plan_revision: number; plan_approved_revision: number | null; g0_approved: boolean; total_seconds: number;
  status?: BreakdownStatus; breakdown_id?: string | null; active_breakdown_id?: string | null; active_breakdown_status?: BreakdownStatus | null; rebreakdown_pending?: boolean; settings?: { episode_seconds_min?: number; episode_seconds_max?: number; target_min?: number; target_max?: number };
}
export interface EpisodeFields { title?: string; change?: string; hook?: string; notes?: string; target_min?: number | null; target_max?: number | null }
export type EpisodeOperation = { expected_revision: number } & (
  { op: "edit"; no: number; fields: EpisodeFields } | { op: "merge" | "delete"; no: number }
  | { op: "split"; no: number; at_unit: number } | { op: "move_boundary"; no: number; delta: -1 | 1 }
  | { op: "insert"; unit_from: number; unit_to: number; title?: string }
);
const root = `${API_BASE}/studio`;
const project = (id: string) => `${root}/projects/${encodeURIComponent(id)}`;
const breakdown = (id: string) => `${root}/breakdowns/${encodeURIComponent(id)}`;
const chunk = (bid: string, cid: string) => `${breakdown(bid)}/chunks/${encodeURIComponent(cid)}`;
const post = (body: unknown, signal?: AbortSignal): RequestInit => ({ method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const getStudioBreakdown = (id: string, signal?: AbortSignal) => apiJson<StudioBreakdown | null>(`${project(id)}/breakdown`, { signal, cache: "no-store" });
export const patchStudioSynopsis = (id: string, synopsis: Record<string, unknown>, signal?: AbortSignal) => apiJson(`${project(id)}/breakdown/synopsis`, { ...post({ synopsis }, signal), method: "PATCH" });
export const patchEpisodeSettings = (id: string, input: { episode_seconds_min: number; episode_seconds_max: number }, signal?: AbortSignal) => apiJson(`${project(id)}`, { ...post(input, signal), method: "PATCH" });
export const quoteStudioBreakdown = (id: string, targetEpisodes?: number, signal?: AbortSignal, settings?: { episode_seconds_min: number; episode_seconds_max: number }) => apiJson<BreakdownQuote>(`${project(id)}/breakdown/quote`, post({ ...(targetEpisodes === undefined ? {} : { target_episodes: targetEpisodes }), ...settings }, signal));
export const startStudioBreakdown = (id: string, quoteId: string, signal?: AbortSignal) => apiJson<StudioBreakdown>(`${project(id)}/breakdown/start`, post({ quote_id: quoteId }, signal));
export const quoteBreakdownRetry = (bid: string, cid: string, provider: BrainProviderId, signal?: AbortSignal) => apiJson<BreakdownQuote>(`${chunk(bid, cid)}/retry/quote`, post({ provider }, signal));
export const retryBreakdownChunk = (bid: string, cid: string, quoteId: string, signal?: AbortSignal) => apiJson(`${chunk(bid, cid)}/retry`, post({ quote_id: quoteId }, signal));
export const cancelStudioBreakdown = (bid: string, signal?: AbortSignal) => apiJson(`${breakdown(bid)}/cancel`, post({}, signal));
export const getStudioBible = (id: string, signal?: AbortSignal) => apiJson<StudioBibleEntry[]>(`${project(id)}/bible`, { signal, cache: "no-store" });
export const patchStudioBible = (id: string, fields: Partial<BibleFields>, signal?: AbortSignal) => apiJson<StudioBibleEntry>(`${root}/bible/${encodeURIComponent(id)}`, { ...post(fields, signal), method: "PATCH" });
export const addStudioBible = (pid: string, kind: BibleKind, fields: BibleFields, signal?: AbortSignal) => apiJson<StudioBibleEntry>(`${root}/bible`, post({ project_id: pid, kind, ...fields }, signal));
export const archiveStudioBible = (id: string, signal?: AbortSignal) => apiJson(`${root}/bible/${encodeURIComponent(id)}`, { method: "DELETE", signal });
export const mergeStudioBible = (keepId: string, mergeIds: string[], signal?: AbortSignal) => apiJson(`${root}/bible/merge`, post({ keep_id: keepId, merge_ids: mergeIds }, signal));
export const getStudioEpisodes = (id: string, signal?: AbortSignal) => apiJson<StudioEpisodePlan>(`${project(id)}/episodes`, { signal, cache: "no-store" });
export const operateStudioEpisodes = (id: string, input: EpisodeOperation, signal?: AbortSignal) => apiJson<StudioEpisodePlan>(`${project(id)}/episodes/ops`, post(input, signal));
export const approveStudioEpisodes = (id: string, revision: number, signal?: AbortSignal) => apiJson<StudioEpisodePlan>(`${project(id)}/episodes/approve`, post({ expected_revision: revision }, signal));
export async function downloadStudioBreakdown(id: string, signal?: AbortSignal): Promise<void> {
  const response = await apiFetch(`${project(id)}/breakdown/export`, { signal, cache: "no-store" });
  if (!response.ok) throw new ApiError("导出未完成，请重试。", response.status);
  const blob = await response.blob();
  if (signal?.aborted) return;
  const header = response.headers.get("Content-Disposition") ?? "";
  const encodedName = /filename\*=UTF-8''([^;]+)/i.exec(header)?.[1];
  let filename = "拆解与分集.md";
  if (encodedName) { try { filename = decodeURIComponent(encodedName); } catch { /* Keep the readable fallback. */ } }
  const url = URL.createObjectURL(blob);
  try { const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); }
  finally { URL.revokeObjectURL(url); }
}
export const breakdownTaskLabel = (task: BreakdownTask) => ({ novel_complete: "补全", text_map: "通读", synopsis: "梗概", episode_plan: "分集" })[task];
export const chunkStatusLabel = (status: ChunkStatus) => ({ blocked: "等待前置批次", queued: "排队中", running: "进行中", succeeded: "已完成", failed: "失败", uncertain: "结果不确定", rejected: "被拒绝", invalid_output: "输出不合格", released: "已释放", cancelled: "已取消" })[status];
export const brainProviderName = (provider: BrainProviderId) => ({ claude: "Claude", qwen: "千问", deepseek: "DeepSeek" })[provider];
export const breakdownInflight = (value: StudioBreakdown | null) => !!value?.chunks.some(item => ["queued", "running"].includes(item.status));
export const formatEpisodeDuration = (seconds: number) => `${Math.floor(seconds / 60)} 分 ${Math.round(seconds % 60)} 秒`;
export const formatBreakdownMoney = (amount: number, currency: "CNY" | "USD") => `${currency === "CNY" ? "¥" : "$"}${Number(amount).toFixed(4)}`;

export const roleLabel = (role: string) => ({ main: "主要人物", supporting: "配角", major: "重要", minor: "次要" } as Record<string, string>)[role] ?? role;
export function formatEpisodeRanges(nos: number[]): string {
  const sorted = [...new Set(nos)].sort((left, right) => left - right);
  if (!sorted.length) return "未纳入";
  const ranges: string[] = [];
  let start = sorted[0], end = start;
  for (const no of sorted.slice(1)) { if (no === end + 1) end = no; else { ranges.push(start === end ? String(start) : `${start}–${end}`); start = end = no; } }
  ranges.push(start === end ? String(start) : `${start}–${end}`);
  return `第 ${ranges.join("、")} 集`;
}
