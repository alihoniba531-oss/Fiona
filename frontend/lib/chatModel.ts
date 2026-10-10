import { apiFetch } from "@/lib/auth";
import { API_BASE as API } from "@/lib/config";

export const CHAT_MODEL_REV_KEY = "fiona_chat_model_rev";
export const CLAUDE_EFFORTS = ["low", "medium", "high"] as const;
export type ChatModelEffort = typeof CLAUDE_EFFORTS[number];
export const CHAT_MODEL_EFFORT_LABELS: Record<ChatModelEffort, string> = { low: "低", medium: "中", high: "高" };
export const CHAT_MODEL_EFFORT_TITLES: Record<ChatModelEffort, string> = {
  low: "低：最快，适合闲聊",
  medium: "中：更周全，稍慢",
  high: "高：最周全，最慢、最费你的额度，单条最长约 3 分钟",
};

export interface ChatModelOptions {
  enabled?: boolean;
  effort?: ChatModelEffort;
}

export interface ChatModelProvider {
  id: string;
  name: string;
  kind: "openai" | "anthropic";
  base_url: string | null;
  recommended_models: string[];
  allowed_models: string[] | null;
  default_model: string | null;
  efforts: ChatModelEffort[] | null;
  default_effort: ChatModelEffort | null;
}

export interface ChatModelConfig {
  provider: string;
  base_url: string | null;
  model: string;
  key_last4: string;
  enabled: boolean;
  status: "ok" | "needs_reentry";
  updated_at: string;
  effort: ChatModelEffort;
}

export interface ChatModelSettings {
  available: boolean;
  unavailable_reason?: string;
  providers: ChatModelProvider[];
  config: ChatModelConfig | null;
}

export interface ChatModelDraft {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
}

export interface ReplyModel {
  source: "byok";
  label: string;
}

// Only errors validated by this module may expose an interface message.
class ChatModelInterfaceError extends Error {}

export function chatModelErrorMessage(error: unknown): string {
  return error instanceof ChatModelInterfaceError ? error.message : "网络错误，请重试";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item: unknown) => typeof item === "string");
}

function isEffort(value: unknown): value is ChatModelEffort {
  return value === "low" || value === "medium" || value === "high";
}

function isEffortArray(value: unknown): value is ChatModelEffort[] {
  return Array.isArray(value) && value.every(isEffort);
}

function invalidResponse(): never {
  throw new ChatModelInterfaceError("聊天模型响应格式不正确，请重试");
}

function parseProvider(value: unknown): ChatModelProvider {
  if (!isRecord(value) || typeof value.id !== "string" || typeof value.name !== "string"
    || (value.kind !== "openai" && value.kind !== "anthropic")
    || (value.base_url !== null && typeof value.base_url !== "string")
    || !isStringArray(value.recommended_models)
    || (value.allowed_models !== null && !isStringArray(value.allowed_models))
    || (value.default_model !== null && typeof value.default_model !== "string")
    || (value.efforts !== null && !isEffortArray(value.efforts))
    || (value.default_effort !== null && !isEffort(value.default_effort))) invalidResponse();
  return {
    id: value.id, name: value.name, kind: value.kind, base_url: value.base_url,
    recommended_models: [...value.recommended_models],
    allowed_models: value.allowed_models === null ? null : [...value.allowed_models],
    default_model: value.default_model,
    efforts: value.efforts === null ? null : [...value.efforts],
    default_effort: value.default_effort,
  };
}

function parseConfig(value: unknown): ChatModelConfig {
  if (!isRecord(value) || typeof value.provider !== "string" || typeof value.model !== "string"
    || (value.base_url !== null && typeof value.base_url !== "string")
    || typeof value.key_last4 !== "string" || typeof value.enabled !== "boolean"
    || (value.status !== "ok" && value.status !== "needs_reentry")
    || typeof value.updated_at !== "string" || !isEffort(value.effort)) invalidResponse();
  return {
    provider: value.provider, model: value.model, base_url: value.base_url,
    key_last4: value.key_last4, enabled: value.enabled, status: value.status, updated_at: value.updated_at,
    effort: value.effort,
  };
}

async function readResponse(response: Response): Promise<unknown> {
  if (response.status === 429) throw new ChatModelInterfaceError("操作太频繁，请稍后再试");
  const data: unknown = await response.json().catch(cause => {
    if (!(cause instanceof SyntaxError)) throw cause;
    if (response.ok) invalidResponse();
    return null;
  });
  if (!response.ok) {
    const message = isRecord(data) && typeof data.detail === "string" ? data.detail : "操作失败，请重试";
    throw new ChatModelInterfaceError(message);
  }
  return data;
}

export async function getChatModel(signal?: AbortSignal): Promise<ChatModelSettings> {
  const data = await readResponse(await apiFetch(`${API}/chat-model`, { cache: "no-store", signal }));
  if (!isRecord(data) || typeof data.available !== "boolean" || !Array.isArray(data.providers)
    || (!data.available && typeof data.unavailable_reason !== "string")) invalidResponse();
  const providers = data.providers.map((value: unknown) => parseProvider(value));
  if (!providers.length || new Set(providers.map(provider => provider.id)).size !== providers.length) invalidResponse();
  const config = data.config === null ? null : parseConfig(data.config);
  if (config && !providers.some(provider => provider.id === config.provider)) invalidResponse();
  return {
    available: data.available, providers, config,
    unavailable_reason: typeof data.unavailable_reason === "string" ? data.unavailable_reason : undefined,
  };
}

async function updateChatModel(method: "PUT" | "PATCH", body: ChatModelDraft | ChatModelOptions, signal?: AbortSignal): Promise<ChatModelConfig> {
  const data = await readResponse(await apiFetch(`${API}/chat-model`, {
    method, signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }));
  if (!isRecord(data)) invalidResponse();
  return parseConfig(data.config);
}

export function saveChatModel(draft: ChatModelDraft, signal?: AbortSignal): Promise<ChatModelConfig> {
  return updateChatModel("PUT", draft, signal);
}

export function setChatModelEnabled(enabled: boolean, signal?: AbortSignal): Promise<ChatModelConfig> {
  return setChatModelOptions({ enabled }, signal);
}

export function setChatModelOptions(options: ChatModelOptions, signal?: AbortSignal): Promise<ChatModelConfig> {
  return updateChatModel("PATCH", options, signal);
}

export async function deleteChatModel(signal?: AbortSignal): Promise<void> {
  const response = await apiFetch(`${API}/chat-model`, { method: "DELETE", signal });
  if (!response.ok) await readResponse(response);
  else if (response.status !== 204) invalidResponse();
}

export async function testChatModel(draft: ChatModelDraft, signal?: AbortSignal): Promise<{ ok: boolean; message: string }> {
  const data = await readResponse(await apiFetch(`${API}/chat-model/test`, {
    method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft),
  }));
  if (!isRecord(data) || typeof data.ok !== "boolean" || typeof data.message !== "string") invalidResponse();
  return { ok: data.ok, message: data.message };
}

export function parseReplyModel(value: unknown): ReplyModel | null {
  return isRecord(value) && value.source === "byok" && typeof value.label === "string" && value.label.length > 0
    ? { source: "byok", label: value.label } : null;
}

export function publishChatModelRevision(): void {
  try {
    localStorage.setItem(CHAT_MODEL_REV_KEY, String(Date.now()));
  } catch {
    // The in-memory selection still works when browser storage is unavailable.
  }
}
