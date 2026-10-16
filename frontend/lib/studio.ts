import { ApiError, apiJson } from "@/lib/agents";
import { apiFetch } from "@/lib/auth";
import { API_BASE } from "@/lib/config";
import type { Message } from "@/components/ChatBubble";

export type StudioJobStatus = "queued" | "submitting" | "submitted" | "running" | "succeeded" | "downloaded" | "rejected" | "uncertain" | "failed" | "filtered" | "expired" | "cancelled" | "released";
export type BrainProviderId = "claude" | "qwen" | "deepseek";
export type StudioSourceKind = "novel" | "upload" | "paste" | "exchange";
export interface StudioProject { id: string; owner: string; title: string; aspect: "16:9" | "9:16"; brain_provider: BrainProviderId; created_at: string; updated_at: string; source_kind?: StudioSourceKind | null; source_ref?: string | null; snapshot_no?: number; episode_seconds_min?: number; episode_seconds_max?: number; plan_revision?: number; plan_approved_revision?: number | null; breakdown_id?: string | null }
export interface StudioFlaggedChapter { chapter: number; title: string; flags: string[] }
export interface StudioNovelCandidate {
  id: string; title: string; status: string; chapters_done: number; words_done: number;
  completed_at: string | null; updated_at: string; drama_adaptation: boolean; eligible: boolean; reason: string | null;
  flagged: StudioFlaggedChapter[]; projects: Pick<StudioProject, "id" | "title" | "snapshot_no" | "created_at">[];
}
export interface StudioNovelSources { enabled: boolean; books: StudioNovelCandidate[] }
export interface StudioExchangeSource { id: string; title: string; completed_at: string; chars: number; artifact_status: string }
export interface StudioSourceStatus {
  kind: StudioSourceKind | null; title?: string;
  snapshot?: { no: number; title?: string; created_at: string; chapters: number; chars: number; flagged?: StudioFlaggedChapter[] };
  flagged?: StudioFlaggedChapter[];
  drift?: { state: "not_applicable" | "unchanged" | "changed" | "unavailable"; changed?: number[]; added?: number[]; removed?: number[]; bible_changed?: boolean; book_status?: string; eligible?: boolean; reason?: string | null };
}
export type StudioCreateInput = { title: string; aspect: StudioProject["aspect"] } & (
  { kind: "blank" } | { kind: "novel"; book_id: string } | { kind: "exchange"; exchange_id: string }
  | { kind: "upload"; file: File } | { kind: "paste"; text: string }
);
export interface StudioToday { committed_cny: number; remaining_cny: number }
export interface StudioAccess { enabled: boolean; caps: { daily_cny: number; max_quote_cny: number; brain_monthly_usd: number; brain_month_used_usd: number; inflight: { wan: number; seedance: number } }; today: StudioToday }
export interface StudioClipParams {
  first_frame_asset_id: string; prompt: string; provider: "wan" | "seedance"; model?: string;
  resolution: string; duration: number; audio: boolean; duration_min_s?: number; duration_max_s?: number;
}
export type StudioParams = StudioClipParams;
export interface StudioAsset {
  id: string; project_id: string; owner: string; kind: "image" | "video" | "audio"; source: "upload" | "generated";
  bytes: number; width: number | null; height: number | null; duration_s: number | null; fps: number | null;
  has_audio: number | boolean | null; meta: Record<string, unknown>; created_at: string;
}
export interface StudioQuoteItem {
  id: string; quote_item_id: string; params: StudioClipParams; provider: string; model: string;
  est_min_cny: number; est_max_cny: number; duration_min_s: number; duration_max_s: number;
}
export interface StudioQuote {
  id: string; project_id: string; items: StudioQuoteItem[]; total_min_cny: number; total_max_cny: number;
  status: "open" | "confirmed"; created_at: string; expires_at: string; today: StudioToday;
}
export interface StudioJob {
  id: string; project_id: string; owner: string; provider: "wan" | "seedance"; model: string;
  params: StudioClipParams; status: StudioJobStatus; task_id: string | null;
  est_min_cny: number; est_max_cny: number; reserved_cny: number; actual_cny: number | null;
  usage: Record<string, unknown> | null; result_asset_id: string | null; error_code: string | null;
  error_message: string | null; needs_recheck: number | boolean; created_at: string; updated_at: string;
}
export interface StudioNotice {
  id: number; project_id: string; project_title: string; job_id: string; summary: string;
  created_at: string; conversation_id: string; message_id: number; content: string;
}
const root = `${API_BASE}/studio`;
const projectPath = (id: string) => `${root}/projects/${encodeURIComponent(id)}`;
const jobPath = (id: string) => `${root}/jobs/${encodeURIComponent(id)}`;
const json = (body: unknown, signal?: AbortSignal): RequestInit => ({ method: "POST", signal, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
export const getStudioAccess = (signal?: AbortSignal) => apiJson<StudioAccess>(`${root}/access`, { signal, cache: "no-store" });
export async function checkStudioAccess(signal?: AbortSignal): Promise<boolean> {
  const response = await apiFetch(`${root}/access`, { signal, cache: "no-store" });
  return response.status === 200;
}
export const listStudioProjects = (signal?: AbortSignal) => apiJson<StudioProject[]>(`${root}/projects`, { signal, cache: "no-store" });
export const createStudioProject = (input: Pick<StudioProject, "title" | "aspect">, signal?: AbortSignal) => apiJson<StudioProject>(`${root}/projects`, json(input, signal));
export const listStudioNovelSources = (signal?: AbortSignal) => apiJson<StudioNovelSources>(`${root}/sources/novels`, { signal, cache: "no-store" });
export const listStudioExchangeSources = (signal?: AbortSignal) => apiJson<StudioExchangeSource[]>(`${root}/sources/exchanges`, { signal, cache: "no-store" });
export const createStudioFromNovel = (input: { book_id: string; title?: string; aspect: StudioProject["aspect"] }, signal?: AbortSignal) => apiJson<StudioProject>(`${root}/projects/from-novel`, json(input, signal));
export const createStudioFromExchange = (input: { exchange_id: string; title?: string; aspect: StudioProject["aspect"] }, signal?: AbortSignal) => apiJson<StudioProject>(`${root}/projects/from-exchange`, json(input, signal));
export const getStudioSource = (id: string, signal?: AbortSignal) => apiJson<StudioSourceStatus>(`${projectPath(id)}/source`, { signal, cache: "no-store" });
export const syncStudioSource = (id: string, expectedNo: number, signal?: AbortSignal) => apiJson<StudioSourceStatus>(`${projectPath(id)}/source/sync`, json({ expected_no: expectedNo }, signal));
export function createStudioFromSource(input: StudioCreateInput, signal?: AbortSignal): Promise<StudioProject> {
  const { title, aspect } = input;
  if (input.kind === "blank") return createStudioProject({ title, aspect }, signal);
  if (input.kind === "novel") return createStudioFromNovel({ title, aspect, book_id: input.book_id }, signal);
  if (input.kind === "exchange") return createStudioFromExchange({ title, aspect, exchange_id: input.exchange_id }, signal);
  const body = new FormData(); body.append("title", title); body.append("aspect", aspect); body.append("kind", input.kind);
  if (input.kind === "upload") body.append("file", input.file); else body.append("text", input.text);
  return apiJson<StudioProject>(`${root}/projects/from-text`, { method: "POST", body, signal });
}
export const studioSourceKindLabel = (kind: StudioSourceKind) => ({ novel: "小说工坊", upload: "上传文件", paste: "粘贴文本", exchange: "创意搭档成稿" })[kind];
export const studioSourceFlagLabel = (flag: string) => ({ length_out_of_range: "字数超出范围", review_degraded: "审阅降级", review_unresolved: "审阅问题待处理", locked_conflict: "锁定设定冲突", deviation: "偏离细纲" } as Record<string, string>)[flag] ?? flag;
export const getStudioProject = (id: string, signal?: AbortSignal) => apiJson<StudioProject>(projectPath(id), { signal, cache: "no-store" });
export const patchStudioProject = (id: string, brainProvider: BrainProviderId, signal?: AbortSignal) => apiJson<StudioProject>(projectPath(id), { ...json({ brain_provider: brainProvider }, signal), method: "PATCH" });
export const listStudioAssets = (id: string, signal?: AbortSignal) => apiJson<StudioAsset[]>(`${projectPath(id)}/assets`, { signal, cache: "no-store" });
export const listStudioJobs = (id: string, signal?: AbortSignal) => apiJson<StudioJob[]>(`${projectPath(id)}/jobs`, { signal, cache: "no-store" });
export const getStudioJob = (id: string, signal?: AbortSignal) => apiJson<StudioJob>(jobPath(id), { signal, cache: "no-store" });
export const quoteStudioClip = (id: string, input: StudioClipParams, signal?: AbortSignal) => {
  // Only writable parameters go back to the strict request schema.
  const { first_frame_asset_id, prompt, provider, model, resolution, duration, audio } = input;
  return apiJson<StudioQuote>(`${projectPath(id)}/clips/quote`, json({ first_frame_asset_id, prompt, provider, model, resolution, duration, audio }, signal));
};
export const confirmStudioQuote = (id: string, signal?: AbortSignal) => apiJson<StudioJob[]>(`${root}/quotes/${encodeURIComponent(id)}/confirm`, json(undefined, signal));
export const cancelStudioJob = (id: string, signal?: AbortSignal) => apiJson<StudioJob>(`${jobPath(id)}/cancel`, json(undefined, signal));
export const recheckStudioJob = (id: string, signal?: AbortSignal) => apiJson<StudioJob>(`${jobPath(id)}/recheck`, json(undefined, signal));
export const linkStudioTask = (id: string, taskId: string, signal?: AbortSignal) => apiJson<StudioJob>(`${jobPath(id)}/link-task`, json({ task_id: taskId }, signal));
export const releaseStudioJob = (id: string, signal?: AbortSignal) => apiJson<StudioJob>(`${jobPath(id)}/release`, json({ not_charged: true }, signal));
export const getStudioNotices = (after: number, signal?: AbortSignal) => apiJson<StudioNotice[]>(`${root}/notices?after=${encodeURIComponent(after)}`, { signal, cache: "no-store" });
export async function uploadStudioAsset(id: string, file: File, signal?: AbortSignal): Promise<StudioAsset> {
  const body = new FormData(); body.append("file", file);
  return apiJson<StudioAsset>(`${projectPath(id)}/assets`, { method: "POST", body, signal });
}
export const studioAssetUrl = (id: string) => `${root}/assets/${encodeURIComponent(id)}/file`;
export const studioAssetHref = studioAssetUrl;
export async function getStudioAssetBlob(id: string, signal?: AbortSignal): Promise<Blob> {
  const response = await apiFetch(studioAssetUrl(id), { signal, cache: "no-store" });
  if (!response.ok) throw new ApiError("素材加载失败，请重试。", response.status);
  return response.blob();
}
export const studioHref = (path: string, embedded: boolean) => embedded ? `${path}${path.includes("?") ? "&" : "?"}embed=1` : path;
const statusLabels: Record<StudioJobStatus, string> = {
  queued: "排队中", submitting: "提交中", submitted: "已提交", running: "生成中", succeeded: "下载中", downloaded: "已完成",
  rejected: "被拒绝（未扣费）", uncertain: "结果不确定", failed: "失败", filtered: "被内容审核拦截（未扣费）", expired: "结果已过期", cancelled: "已取消", released: "已释放（确认未扣费）",
};
export const studioStatusLabel = (status: StudioJobStatus) => statusLabels[status] ?? status;
export const studioJobStatusLabel = studioStatusLabel;
export const studioErrorCodeLabel = (code: string | null | undefined): string => code ? ({
  restart_during_submission: "提交时服务重启，请核对是否已扣费", submission_interrupted: "提交中断，请核对是否已扣费",
  submission_error: "提交发生错误，请核对是否已扣费", poll_timeout: "查询超时，请重新查询", short_output: "成片时长不足", not_charged: "已确认未扣费",
} as Record<string, string>)[code] ?? code : "";
export const studioErrorCodeMessage = studioErrorCodeLabel;
export const studioModelLabel = (model: string) => ({ wan: "万相 3.0", "wan3.0-video": "万相 3.0", "wan3.0-video-prime": "万相 3.0", seedance: "Seedance 2.5", "doubao-seedance-2-5-260628": "Seedance 2.5" } as Record<string, string>)[model] ?? model;
export function studioErrorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "操作未完成，请稍后重试。";
}
export function formatStudioDate(value: string): string {
  const normalized = /[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value.replace(" ", "T")}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}
export const hasStudioInflightJobs = (jobs: Pick<StudioJob, "status">[]) => jobs.some(job => ["queued", "submitting", "submitted", "running", "succeeded"].includes(job.status));

export type BrainTask = "read_through" | "style_proposals" | "bible_extract";
export interface BrainProvider { id: BrainProviderId; label: string; available: boolean; reason?: string; model?: string; vision_via?: string }
export interface BrainTrialInput { text: string; tasks: BrainTask[]; providers: "current" | "all" }
export interface BrainCost { currency: "CNY" | "USD"; amount: number | null }
export interface BrainJob {
  id: string; provider: BrainProviderId; task: BrainTask; model: string;
  status: "queued" | "running" | "succeeded" | "uncertain" | "rejected" | "failed" | "invalid_output" | "released";
  output: Record<string, unknown> | null; warnings: string[]; usage: Record<string, unknown> | null;
  cost: BrainCost | null; latency_s: number | null; repaired?: boolean; stop_reason?: string | null;
  reserved_amount?: number | string;
  attempt?: number; parent_job_id?: string | null; error_code: string | null; error_message: string | null;
}
export interface BrainGroup { group_id: string; jobs: BrainJob[]; totals?: { CNY: number; USD: number } }
export interface BrainQuote { totals: { CNY: number; USD: number }; items: { provider: BrainProviderId; task: BrainTask; model: string; currency: "CNY" | "USD"; amount: number }[] }
export const getBrainProviders = (signal?: AbortSignal) => apiJson<BrainProvider[]>(`${root}/brain/providers`, { signal, cache: "no-store" });
export const quoteBrainTrial = (id: string, input: BrainTrialInput, signal?: AbortSignal) => apiJson<BrainQuote>(`${projectPath(id)}/brain/quote`, json(input, signal));
export const startBrainTrial = (id: string, input: BrainTrialInput, signal?: AbortSignal) => apiJson<BrainGroup>(`${projectPath(id)}/brain/trial`, json(input, signal));
export const getBrainGroup = (id: string, groupId: string, signal?: AbortSignal) => apiJson<BrainGroup>(`${projectPath(id)}/brain/groups/${encodeURIComponent(groupId)}`, { signal, cache: "no-store" });
export const hasBrainInflightJobs = (jobs: BrainJob[]) => jobs.some(job => job.status === "queued" || job.status === "running");
export const brainTaskLabel = (task: BrainTask) => ({ read_through: "通读结论", style_proposals: "风格提案", bible_extract: "人物、场景、道具表" })[task] ?? task;
export const brainStatusLabel = (status: BrainJob["status"]) => ({ queued: "排队中", running: "试读中", succeeded: "已完成", uncertain: "结果不确定", rejected: "被拒绝（未扣费）", failed: "失败", invalid_output: "输出不合格", released: "已释放（确认未扣费）" })[status] ?? status;

export interface StudioNoticePollOptions {
  isVisible: () => boolean;
  fetchPage: (after: number, signal: AbortSignal) => Promise<{ status: number; notices: StudioNotice[] }>;
  onNotices: (notices: StudioNotice[]) => void;
}
// Establish the entire baseline before delivering any new notices. A failed
// page never advances the accepted cursor, matching the local-watch poller.
export function createStudioNoticePoller(options: StudioNoticePollOptions) {
  let cursor = 0, initialized = false, stopped = false, pending = false;
  let active: AbortController | null = null;
  async function tick() {
    if (stopped || pending || !options.isVisible()) return;
    pending = true;
    const request = new AbortController(); active = request;
    try {
      let after = cursor;
      while (!stopped && options.isVisible() && !request.signal.aborted) {
        const result = await options.fetchPage(after, request.signal);
        if (stopped || !options.isVisible() || request.signal.aborted) return;
        if (result.status === 404) { stopped = true; return; }
        if (result.status !== 200) return;
        const fresh = result.notices.filter(notice => notice.id > after);
        const latest = fresh.reduce((maximum, notice) => Math.max(maximum, notice.id), after);
        if (initialized) {
          if (fresh.length) options.onNotices(fresh);
          cursor = latest; return;
        }
        if (result.notices.length < 50 || latest === after) { cursor = latest; initialized = true; return; }
        after = latest;
      }
    } catch { /* Retry with the accepted cursor on the next visible tick. */ }
    finally { if (active === request) active = null; pending = false; }
  }
  return { tick, pause: () => active?.abort(), dispose: () => { stopped = true; active?.abort(); } };
}
export function mergeStudioNotices(messages: Message[], notices: StudioNotice[], conversationId: string | undefined): Message[] {
  if (!conversationId) return messages;
  const seen = new Set(messages.flatMap(message => [message.id, message.dbId == null ? "" : `db-${message.dbId}`]));
  const additions: Message[] = [];
  for (const notice of notices) {
    const id = `db-${notice.message_id}`;
    if (notice.conversation_id !== conversationId || seen.has(id)) continue;
    seen.add(id);
    additions.push({ id, dbId: notice.message_id, role: "assistant", content: notice.content,
      timestamp: new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(notice.created_at) ? notice.created_at : `${notice.created_at.replace(" ", "T")}Z`) });
  }
  return additions.length ? [...messages, ...additions] : messages;
}
