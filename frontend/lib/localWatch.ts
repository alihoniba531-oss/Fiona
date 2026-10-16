import { apiFetch } from "@/lib/auth";
import { API_BASE as API } from "@/lib/config";
import type { Message } from "@/components/ChatBubble";

export interface LocalWatchDevice {
  id: number; name: string | null; created_at: string; last_seen_at: string | null; revoked: boolean | number;
}

export interface LocalWatchWindow { app_name: string; bundle_id: string; title: string }
export type LocalWatchKind = "keyword" | "number" | "ai";
export interface LocalWatchParams {
  keywords?: string[]; label?: string; op?: ">" | ">=" | "<" | "<="; threshold?: number;
  condition?: string; model?: "platform" | "claude";
}
export interface LocalWatchCapture {
  ok: boolean; neutral?: boolean; message: string; since?: string;
}
export interface LocalWatchRule {
  id: number; name: string; app_match: string; title_match: string; kind: LocalWatchKind;
  params: LocalWatchParams; interval_seconds: number; cooldown_seconds: number;
  enabled: boolean | number; conversation_id: string | null;
  capture?: LocalWatchCapture;
}
export type LocalWatchRuleDraft = Omit<LocalWatchRule, "id" | "capture">;

export function localWatchCaptureMessage(rule: LocalWatchRule): string {
  return rule.capture?.ok ? "监控中" : rule.capture?.message ?? "监控程序未在运行";
}

// A TypeScript type cannot remove server metadata at runtime. Build the exact
// writable API fields and the selected kind's parameters for every submission.
export function localWatchRulePayload(draft: LocalWatchRuleDraft): LocalWatchRuleDraft {
  const params = draft.kind === "keyword" ? { keywords: [...(draft.params.keywords ?? [])] }
    : draft.kind === "number" ? { label: draft.params.label ?? "", op: draft.params.op ?? ">=", threshold: draft.params.threshold ?? 0 }
    : { condition: draft.params.condition ?? "", model: draft.params.model ?? "platform" };
  return {
    name: draft.name.trim(), app_match: draft.app_match.trim(), title_match: draft.title_match.trim(),
    kind: draft.kind, params, interval_seconds: draft.interval_seconds,
    cooldown_seconds: draft.cooldown_seconds, enabled: !!draft.enabled,
    conversation_id: draft.conversation_id || null,
  };
}

export function localWatchDraft(rule?: LocalWatchRule): LocalWatchRuleDraft {
  return localWatchRulePayload(rule ?? {
    name: "", app_match: "", title_match: "", kind: "keyword", params: { keywords: [] },
    interval_seconds: 3, cooldown_seconds: 60, enabled: true, conversation_id: null,
  });
}

export interface LocalWatchAlert {
  id: number; rule_name: string; summary: string; content: string; created_at: string;
  conversation_id: string; message_id: number;
}
export interface LocalWatchPollOptions {
  isVisible: () => boolean;
  fetchPage: (after: number, signal: AbortSignal) => Promise<{ status: number; alerts: LocalWatchAlert[] }>;
  onAlerts: (alerts: LocalWatchAlert[]) => void;
}

export class LocalWatchError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function localWatchRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(`${API}/local-watch${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new LocalWatchError(response.status === 404 ? "本机监控暂未开启"
      : typeof data?.detail === "string" ? data.detail : "操作失败，请检查输入后重试", response.status);
  }
  return response.status === 204 ? undefined as T : await response.json() as T;
}

export function localWatchErrorMessage(cause: unknown): string {
  return cause instanceof LocalWatchError ? cause.message : "网络错误，请重试";
}

// The cursor belongs to one mounted account. Initial pagination establishes a
// complete baseline even when there are more than 50 historical alerts.
export function createLocalWatchPoller(options: LocalWatchPollOptions) {
  let cursor = 0;
  let initialized = false;
  let stopped = false;
  let pending = false;
  let active: AbortController | null = null;
  async function tick() {
    if (stopped || pending || !options.isVisible()) return;
    pending = true;
    const request = new AbortController();
    active = request;
    try {
      let after = cursor;
      while (!stopped && options.isVisible() && !request.signal.aborted) {
        const result = await options.fetchPage(after, request.signal);
        if (stopped || !options.isVisible() || request.signal.aborted) return;
        if (result.status === 404) { stopped = true; return; }
        if (result.status !== 200) return;
        const fresh = result.alerts.filter(alert => alert.id > after);
        const latest = fresh.reduce((maximum, alert) => Math.max(maximum, alert.id), after);
        if (initialized) {
          if (fresh.length) options.onAlerts(fresh);
          cursor = latest;
          return;
        }
        // No history is delivered, including partial pages from a failed read.
        if (result.alerts.length < 50 || latest === after) {
          cursor = latest;
          initialized = true;
          return;
        }
        after = latest;
      }
    } catch {
      // Retry on the next visible tick, keeping the accepted cursor unchanged.
    } finally {
      if (active === request) active = null;
      pending = false;
    }
  }
  return {
    tick,
    pause: () => active?.abort(),
    dispose: () => { stopped = true; active?.abort(); },
  };
}

export function localWatchMessage(alert: LocalWatchAlert): Message {
  return {
    id: `db-${alert.message_id}`, dbId: alert.message_id, role: "assistant",
    content: alert.content,
    timestamp: new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(alert.created_at)
      ? alert.created_at : `${alert.created_at.replace(" ", "T")}Z`),
  };
}

export function appendLocalWatchMessages(messages: Message[], alerts: LocalWatchAlert[], conversationId: string | undefined, busy: boolean): Message[] {
  if (busy || !conversationId) return messages;
  const additions = alerts.filter(alert => alert.conversation_id === conversationId
    && !messages.some(message => message.dbId === alert.message_id || message.id === `db-${alert.message_id}`));
  return additions.length ? [...messages, ...additions.map(localWatchMessage)] : messages;
}

export function localWatchNotificationsEnabled(username: string): boolean {
  try { return localStorage.getItem(`fiona_local_watch_notifications:${encodeURIComponent(username)}`) === "1"; }
  catch { return false; }
}

export function setLocalWatchNotifications(username: string, enabled: boolean): void {
  localStorage.setItem(`fiona_local_watch_notifications:${encodeURIComponent(username)}`, enabled ? "1" : "0");
}
