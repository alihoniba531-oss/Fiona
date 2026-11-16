import { ApiError, apiJson } from "@/lib/agents";
import { apiFetch } from "@/lib/auth";
import { API_BASE } from "@/lib/config";

// 讨论群的类型与接口。字段名与 backend/discuss/service.py 返回的一致；
// 纯展示判断放在 lib/discussLogic.ts，这里只放数据形状与请求。

export type DiscussStatus =
  | "planning"
  | "awaiting_start"
  | "running"
  | "awaiting_user"
  | "paused"
  | "done"
  | "failed"
  | "closed";

export type DiscussTab = "chat" | "plan" | "output" | "sources";

export type DiscussAction =
  | "start"
  | "pause"
  | "resume"
  | "continue"
  | "rework"
  | "accept"
  | "close"
  | "export"
  | "delete";

export type DiscussTeamMode = "host" | "self";

export type DiscussCoreRole = "host" | "critic" | "writer" | "acceptor";

export type DiscussMemberKind = "core" | "lens" | "custom" | "avatar";

/** 群摘要：建群返回值与列表的每一项。 */
export interface DiscussSummary {
  id: string;
  title: string;
  status: DiscussStatus;
  stop_reason: string | null;
  round: number;
  max_rounds: number;
  budget_strawberries: number;
  spent_strawberries: number;
  output_version: number;
  created_at: string;
  updated_at: string;
}

/** 群成员。core 固定席位、lens 调研、custom 自定义、avatar 分身。 */
export interface DiscussMember {
  role: string;
  name: string;
  kind: DiscussMemberKind;
  does: string;
  /** 只有调研成员才有分工。 */
  focus?: string;
  model: string;
  working: boolean;
}

/** 群里的一条消息。payload 是后端解码后的对象，可能是空对象。 */
export interface DiscussMessage {
  id: number;
  round: number;
  sender: string;
  sender_name: string;
  kind: string;
  content: string;
  payload: Record<string, unknown>;
  created_at: string;
  consumed: boolean | null;
}

export interface DiscussPlanCriterion {
  id: string;
  text: string;
}

/** 方案里的一位调研成员；后端在方案出来时已填好具体名字与职责。 */
export interface DiscussPlanPick {
  role: string;
  name: string;
  does: string;
  focus: string;
}

export interface DiscussPlan {
  title: string;
  goal: string;
  deliverable: { kind: string; outline: string[] };
  criteria: DiscussPlanCriterion[];
  picks: DiscussPlanPick[];
  questions: string[];
}

export interface DiscussVerdictItem {
  id: string;
  pass: boolean;
  evidence: string;
}

export interface DiscussVerdictIssue {
  quote: string;
  problem: string;
}

/** 验收载荷。字段缺失或类型不对时由界面逐条跳过，不在这里做强约束。 */
export interface DiscussVerdict {
  verdicts: DiscussVerdictItem[];
  citation_issues: DiscussVerdictIssue[];
  rework: string[];
  [key: string]: unknown;
}

/** 详情里的成果摘要（最新一版，不含全文）。 */
export interface DiscussOutputSummary {
  version: number;
  round: number;
  passed: boolean;
  verdict: DiscussVerdict | null;
  words: number;
}

/** GET output 的成果正文。 */
export interface DiscussOutput {
  version: number;
  round: number;
  content: string;
  passed: boolean;
  verdict: DiscussVerdict | null;
  created_at: string;
}

/** 群详情。answers 是作者对主持人问题的回答（后端 4.3 补充）。 */
export interface DiscussDetail extends DiscussSummary {
  request: string;
  last_error: string | null;
  reserved_strawberries: number;
  plan_revision: number;
  plan: DiscussPlan | null;
  members: DiscussMember[];
  messages: DiscussMessage[];
  output: DiscussOutputSummary | null;
  pending_notes: number;
  answers: string;
}

/** 任务卡上的群摘要：卡片已建群且群还在时才有。 */
export interface DiscussTaskCardGroup {
  id: string;
  title: string;
  status: DiscussStatus;
  stop_reason: string | null;
}

/** GET /discuss/task-cards/{id} 的任务卡视图。 */
export interface DiscussTaskCardView {
  id: string;
  request: string;
  materials: string;
  max_rounds: number | null;
  budget_strawberries: number | null;
  group_id: string | null;
  group: DiscussTaskCardGroup | null;
  created_at: string;
}

/** 意见卡送出后对应的那条插话，consumed 表示主持人读到没有。 */
export interface DiscussNoteCardMessage {
  id: number;
  consumed: boolean;
}

/** 意见卡上的群摘要：群还在时才有。 */
export interface DiscussNoteCardGroup {
  id: string;
  title: string;
  status: DiscussStatus;
  stop_reason: string | null;
  pending_notes: number;
}

/** GET /discuss/note-cards/{id} 的意见卡视图。 */
export interface DiscussNoteCardView {
  id: string;
  group_id: string | null;
  group_title: string;
  text: string;
  sent_at: string | null;
  message: DiscussNoteCardMessage | null;
  group: DiscussNoteCardGroup | null;
  created_at: string;
}

export interface DiscussSource {
  id: string;
  title: string;
  site_name: string;
  url: string;
}

export interface DiscussLimits {
  budget_min: number;
  budget_max: number;
  budget_default: number;
  rounds_min: number;
  rounds_max: number;
  rounds_default: number;
  members_min: number;
  members_max: number;
  name_max: number;
  persona_max: number;
  custom_does_max: number;
  request_min: number;
  request_max: number;
  materials_max: number;
  unread_notes_max: number;
}

export interface DiscussCatalogRole {
  id: string;
  name: string;
  does: string;
  kind: "core" | "lens" | "avatar";
}

export interface DiscussCatalog {
  roles: DiscussCatalogRole[];
  models: { id: string; price: { input: number; output: number } }[];
  byok: { provider: string; model: string; model_spec?: string } | null;
  defaults: Record<string, string>;
  limits: DiscussLimits;
  search_price: number;
  notice: string;
}

/** POST /discuss/groups 的成员形状：角色池成员带 role，自定义成员不带。 */
export interface DiscussMemberInput {
  role?: string;
  name?: string;
  does?: string;
}

export interface DiscussIdentityInput {
  name?: string;
  persona?: string;
}

export interface DiscussCreateInput {
  request: string;
  materials?: string;
  budget_strawberries: number;
  max_rounds: number;
  avatar: boolean;
  models?: Record<string, string>;
  members?: DiscussMemberInput[];
  identities?: Record<string, DiscussIdentityInput>;
  /** 带上时建群会消费这张任务卡；不带时建群行为与旧版相同。 */
  task_id?: string;
}

export interface DiscussPlanPickInput {
  /** 已有成员或角色池成员带 role；新增自定义成员不带。 */
  role?: string;
  name: string;
  does: string;
  focus: string;
}

export interface DiscussPlanPatchInput {
  expected_revision: number;
  title?: string;
  criteria?: string[];
  picks?: DiscussPlanPickInput[];
  identities?: Record<string, DiscussIdentityInput>;
  budget_strawberries?: number;
  max_rounds?: number;
  avatar?: boolean;
  models?: Record<string, string>;
  answers?: string;
}

export interface DiscussStartInput {
  expected_revision: number;
}

export interface DiscussResumeInput {
  add_budget?: number;
}

export interface DiscussContinueInput {
  add_rounds?: number;
  add_budget?: number;
}

export interface DiscussNoteInput {
  text: string;
}

// ── 表单类型 ────────────────────────────────────────────────────
//
// 表单里同时保留「作者当前填的值」与「初始化时的默认值/当前值」，
// buildDiscussCreateBody / buildDiscussPlanPatch 靠这些基线判断作者改过哪些字段，
// 没改过的字段不发给后端。

/**
 * 新建页「我来组队」里角色池的一位成员（未勾选时只用于渲染勾选框）。
 * 从 catalog 初始化：name/does/default_name/default_does 都抄角色池的 name/does，
 * model/default_model 都抄 catalog.defaults[role]。
 */
export interface DiscussLensDraft {
  role: string;
  selected: boolean;
  name: string;
  does: string;
  default_name: string;
  default_does: string;
  model: string;
  default_model: string;
}

/**
 * 新建页里作者添加的自定义成员。目录没有自定义成员的默认模型，初始化时
 * model 与 default_model 都取角色池成员（kind=lens）的默认模型，例如
 * DeepSeek Flash；建群请求始终把 customN 的当前模型发给后端。
 */
export interface DiscussCustomMemberDraft {
  name: string;
  does: string;
  model: string;
  default_model: string;
}

/**
 * 新建页「更多设置」里固定席位的名字、身份设定与模型。name/persona 留空表示
 * 用默认名字、没有身份设定；model/default_model 都从 catalog.defaults[role] 初始化。
 */
export interface DiscussIdentityDraft {
  role: DiscussCoreRole;
  name: string;
  persona: string;
  model: string;
  default_model: string;
}

/**
 * 新建页表单。下游拿到 catalog 后按下述方式初始化：
 * - lenses：catalog.roles 里 kind === "lens" 的项，selected 默认 false；
 * - custom_members：空数组；
 * - avatar：true；avatar_model/default_avatar_model：catalog.defaults.avatar；
 * - budget_strawberries：catalog.limits.budget_default；max_rounds：catalog.limits.rounds_default；
 * - identities：host、critic、writer、acceptor 四位，名字与身份设定留空，
 *   model/default_model 抄 catalog.defaults[role]；
 * - team："host"。
 */
export interface DiscussCreateForm {
  request: string;
  materials: string;
  team: DiscussTeamMode;
  lenses: DiscussLensDraft[];
  custom_members: DiscussCustomMemberDraft[];
  avatar: boolean;
  avatar_model: string;
  default_avatar_model: string;
  budget_strawberries: number;
  max_rounds: number;
  identities: DiscussIdentityDraft[];
}

/**
 * 方案编辑里的一位调研成员。已有成员抄详情里的 role/name/does/focus；
 * 从角色池新加的角色带 role，新加的自定义成员不填 role。
 */
export interface DiscussPickDraft {
  role?: string;
  name: string;
  does: string;
  focus: string;
}

/**
 * 方案编辑里固定席位的名字与身份设定。name/persona 抄详情 members 里
 * kind === "core" 的 name 与 does；default_name/default_persona 抄同一份，
 * 用来判断作者是否改过（清空名字会发给后端，表示恢复默认名字）。
 */
export interface DiscussPlanIdentityDraft {
  role: DiscussCoreRole;
  name: string;
  persona: string;
  default_name: string;
  default_persona: string;
}

/**
 * 方案编辑表单。从 detail 初始化：
 * - title：detail.title；criteria：detail.plan.criteria 的 text 数组；
 * - picks：detail.plan.picks（含 role）；新增角色池成员保留其 role，新增自定义成员不填 role；
 * - identities：四位核心成员按上面的 DiscussPlanIdentityDraft 复制；
 * - budget_strawberries、max_rounds：detail 里的当前值；
 * - avatar：detail.members 里是否有 kind === "avatar"；
 * - models：detail.members 的 role → model（含 host 与 avatar）；
 * - answers：detail.answers。
 * models 里新增自定义成员的键由后端按 custom1、custom2… 分配，界面可先不填，
 * 不填时后端用默认模型。
 */
export interface DiscussPlanDraft {
  title: string;
  criteria: string[];
  picks: DiscussPickDraft[];
  identities: DiscussPlanIdentityDraft[];
  budget_strawberries: number;
  max_rounds: number;
  avatar: boolean;
  models: Record<string, string>;
  answers: string;
}

const root = `${API_BASE}/discuss`;
const groupPath = (id: string) => `${root}/groups/${encodeURIComponent(id)}`;
const taskCardPath = (id: string) => `${root}/task-cards/${encodeURIComponent(id)}`;
const noteCardPath = (id: string) => `${root}/note-cards/${encodeURIComponent(id)}`;
const json = (method: string, body: unknown, signal?: AbortSignal): RequestInit => ({
  method,
  signal,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export async function checkDiscussAccess(signal?: AbortSignal): Promise<boolean> {
  const response = await apiFetch(`${root}/access`, { signal, cache: "no-store" });
  return response.status === 200;
}

export const getDiscussCatalog = (signal?: AbortSignal) =>
  apiJson<DiscussCatalog>(`${root}/catalog`, { signal, cache: "no-store" });

export const listDiscussGroups = (signal?: AbortSignal) =>
  apiJson<DiscussSummary[]>(`${root}/groups`, { signal, cache: "no-store" });

export const createDiscussGroup = (input: DiscussCreateInput, signal?: AbortSignal) =>
  apiJson<DiscussSummary>(`${root}/groups`, json("POST", input, signal));

export const getDiscussTaskCard = (id: string, signal?: AbortSignal) =>
  apiJson<DiscussTaskCardView>(taskCardPath(id), { signal, cache: "no-store" });

export const getDiscussNoteCard = (id: string, signal?: AbortSignal) =>
  apiJson<DiscussNoteCardView>(noteCardPath(id), { signal, cache: "no-store" });

export const sendDiscussNoteCard = (id: string, signal?: AbortSignal) =>
  apiJson<DiscussNoteCardView>(`${noteCardPath(id)}/send`, json("POST", {}, signal));

export const getDiscussGroup = (id: string, after = 0, signal?: AbortSignal) =>
  apiJson<DiscussDetail>(`${groupPath(id)}?after=${after}`, { signal, cache: "no-store" });

export const updateDiscussPlan = (id: string, input: DiscussPlanPatchInput, signal?: AbortSignal) =>
  apiJson<DiscussDetail>(`${groupPath(id)}/plan`, json("PATCH", input, signal));

/** 讨论群操作用 POST；body 为空时也发一个空对象，与后端默认请求体一致。 */
const action = (id: string, path: string, body: unknown = {}, signal?: AbortSignal) =>
  apiJson<DiscussDetail>(`${groupPath(id)}/${path}`, json("POST", body, signal));

export const startDiscussGroup = (id: string, input: DiscussStartInput, signal?: AbortSignal) =>
  action(id, "start", input, signal);

export const addDiscussNote = (id: string, input: DiscussNoteInput, signal?: AbortSignal) =>
  apiJson<DiscussMessage>(`${groupPath(id)}/notes`, json("POST", input, signal));

export const pauseDiscussGroup = (id: string, signal?: AbortSignal) =>
  action(id, "pause", undefined, signal);

export const resumeDiscussGroup = (id: string, input: DiscussResumeInput = {}, signal?: AbortSignal) =>
  action(id, "resume", input, signal);

export const continueDiscussGroup = (id: string, input: DiscussContinueInput, signal?: AbortSignal) =>
  action(id, "continue", input, signal);

export const acceptDiscussGroup = (id: string, signal?: AbortSignal) =>
  action(id, "accept", undefined, signal);

export const closeDiscussGroup = (id: string, signal?: AbortSignal) =>
  action(id, "close", undefined, signal);

export const deleteDiscussGroup = (id: string, signal?: AbortSignal) =>
  apiJson<{ deleted: boolean }>(groupPath(id), { method: "DELETE", signal });

export const listDiscussSources = (id: string, signal?: AbortSignal) =>
  apiJson<DiscussSource[]>(`${groupPath(id)}/sources`, { signal, cache: "no-store" });

export const getDiscussOutput = (id: string, version?: number, signal?: AbortSignal) =>
  apiJson<DiscussOutput>(
    `${groupPath(id)}/output${version === undefined ? "" : `?version=${version}`}`,
    { signal, cache: "no-store" },
  );

function attachmentFilename(header: string | null): string {
  // 优先 RFC 5987 的 filename*=UTF-8''…，退回普通 filename=…
  const encoded = header?.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded) {
    try { return decodeURIComponent(encoded[1].trim()); } catch { /* 非法编码时用底线 */ }
  }
  const plain = header?.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1].trim() : "";
}

/** 导出成果并带上响应头里的附件名；取不到时由调用方用「讨论群成果.md」。 */
export async function exportDiscussGroupFile(
  id: string,
  signal?: AbortSignal,
): Promise<{ blob: Blob; filename: string }> {
  const response = await apiFetch(`${groupPath(id)}/export`, { signal });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(
      typeof data?.detail === "string" ? data.detail : "导出失败，请稍后重试。",
      response.status,
    );
  }
  if (!response.headers.get("Content-Type")?.toLowerCase().includes("text/markdown")) {
    throw new Error("导出内容格式不正确，请稍后重试。");
  }
  return {
    blob: await response.blob(),
    filename: attachmentFilename(response.headers.get("Content-Disposition")),
  };
}

export async function exportDiscussGroup(id: string, signal?: AbortSignal): Promise<Blob> {
  return (await exportDiscussGroupFile(id, signal)).blob;
}
