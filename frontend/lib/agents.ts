import { apiFetch } from "@/lib/auth";

export interface AgentCard {
  id: string;
  display_name: string;
  bio: string;
  avatar_emoji: string;
  is_public: boolean;
  kind?: "official";
}

export interface Agent extends AgentCard {
  owner_username: string;
  personality: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  agent_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(url, init);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail ?? data?.error;
    throw new ApiError(typeof detail === "string" ? detail : response.status === 422
      ? "填写的信息不符合要求，请检查长度和内容。"
      : response.status === 404 ? "内容不存在或暂未公开。"
      : `请求未完成（${response.status}），请重试。`, response.status);
  }
  if (data === null) throw new Error("服务器未返回完整数据，请重试。");
  return data as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "连接失败，请检查网络后重试。";
}
