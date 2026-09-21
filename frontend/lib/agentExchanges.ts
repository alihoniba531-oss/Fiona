import type { AgentCard } from "@/lib/agents";

export type ExchangeStatus = "pending" | "running" | "completed" | "stopped" | "rejected" | "failed";

export interface ExchangeModelMetadata {
  provider?: string;
  model?: string;
  model_label?: string;
}

export interface OfficialAgentCard extends AgentCard, ExchangeModelMetadata {
  kind: "official";
  suggested_topic?: string;
}

export interface AgentExchange {
  id: string;
  kind?: "peer" | "official";
  topic: string;
  max_turns: number;
  turn_count: number;
  status: ExchangeStatus;
  summary: string;
  workflow_version?: string;
  artifact?: string;
  has_artifact?: boolean;
  artifact_status?: "" | "draft" | "approved" | "needs_revision";
  completion_reason?: string;
  error: string;
  created_at: string;
  updated_at: string;
  initiator: AgentCard & ExchangeModelMetadata;
  recipient: AgentCard & ExchangeModelMetadata;
  viewer_role: "initiator" | "recipient";
  usage?: {
    model_calls: number;
    max_model_calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated: boolean;
    token_budget: number;
    budget_used?: number;
    reserved_tokens?: number;
  };
}

export interface ExchangeMessage {
  id: string;
  exchange_id: string;
  sequence: number;
  agent_id: string;
  display_name: string;
  avatar_emoji: string;
  content: string;
  stage?: "" | "draft" | "review" | "revision";
  review_json?: string;
  created_at: string;
}

export interface ExchangeDetail {
  exchange: AgentExchange;
  messages: ExchangeMessage[];
}

export const exchangeStatusLabel: Record<ExchangeStatus, string> = {
  pending: "等待接受", running: "交流中", completed: "已完成",
  stopped: "已停止", rejected: "已拒绝", failed: "交流失败",
};

export function isExchangeActive(status: ExchangeStatus) {
  return status === "pending" || status === "running";
}

export function exchangeBelongsTo(exchange: AgentExchange, agentId: string) {
  if (isOfficialExchange(exchange)) return exchange.viewer_role === "initiator" && exchange.initiator.id === agentId;
  return (exchange.viewer_role === "initiator" && exchange.initiator.id === agentId)
    || (exchange.viewer_role === "recipient" && exchange.recipient.id === agentId);
}

export function isOfficialExchange(exchange: AgentExchange) {
  return exchange.kind === "official" || exchange.recipient.kind === "official";
}

export function isDraftReviewExchange(exchange: AgentExchange) {
  return exchange.workflow_version === "draft_review_v1";
}

export function isArtifactApproved(exchange: AgentExchange) {
  return isDraftReviewExchange(exchange) && exchange.status === "completed"
    && exchange.artifact_status === "approved" && (exchange.artifact !== undefined
      ? !!exchange.artifact.trim() : exchange.has_artifact === true);
}

export class ExchangeIdentityError extends Error {
  constructor() {
    super("账号状态已变化，旧交流内容已清除。请重新登录后查看。");
  }
}
