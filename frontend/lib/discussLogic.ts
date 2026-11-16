import type {
  DiscussAction,
  DiscussCatalog,
  DiscussCreateForm,
  DiscussCreateInput,
  DiscussDetail,
  DiscussIdentityInput,
  DiscussLimits,
  DiscussMember,
  DiscussMemberInput,
  DiscussMessage,
  DiscussPlanDraft,
  DiscussPlanPatchInput,
  DiscussPlanPickInput,
  DiscussStatus,
  DiscussSummary,
  DiscussTab,
  DiscussTaskCardView,
} from "./discuss";

// 讨论群的纯函数。这里不引入任何运行时依赖（只允许 import type），
// 测试会在 Node 里直接转译执行。界面上「按状态决定显示什么」的判断都放这里。

const STATUS_LABELS: Record<string, string> = {
  planning: "立项中",
  awaiting_start: "等你开工",
  running: "讨论中",
  awaiting_user: "等你决定",
  closed: "已结束",
  failed: "出错了",
};

const PAUSED_LABELS: Record<string, string> = {
  user: "已暂停",
  budget: "预算用完",
  insufficient_strawberries: "草莓不足",
  byok_unavailable: "自带模型不可用",
  step_failed: "有一步没跑通",
  search_unavailable: "联网搜索暂不可用",
  server_restart_failed: "恢复失败",
};

const PAUSED_HINTS: Record<string, string> = {
  budget: "预算用完了。继续之前先追加预算。",
  insufficient_strawberries: "草莓不够了。补充草莓后点继续。",
  byok_unavailable: "自带模型用不了。到设置里检查后点继续。",
  step_failed: "有一步连着几次没跑通。点继续会从断的地方接着跑。",
  search_unavailable: "联网搜索暂时拿不到结果。过一会儿点继续。",
  server_restart_failed: "服务重启后没能自动接上。点继续会从断的地方接着跑。",
};

const KIND_LABELS: Record<string, string> = {
  plan: "方案",
  brief: "主人背景",
  note: "调研笔记",
  notice: "说明",
  critique: "质疑",
  decision: "裁决",
  draft: "成稿",
  view: "主人视角",
  verdict: "验收",
  rework: "返工安排",
  user: "插话",
};

export function discussStatusLabel(
  group: Pick<DiscussSummary, "status" | "stop_reason">,
): string {
  if (group.status === "done") {
    return group.stop_reason === "accepted_by_user" ? "你已接受" : "验收通过";
  }
  if (group.status === "paused") {
    return PAUSED_LABELS[group.stop_reason ?? ""] ?? "已暂停";
  }
  return STATUS_LABELS[group.status] ?? group.status;
}

export function discussStopHint(
  group: Pick<DiscussSummary, "status" | "stop_reason">,
): string {
  if (group.status === "awaiting_start") {
    return "方案已经出来了。看一眼、改一改，回答主持人的问题，然后开工。";
  }
  if (group.status === "awaiting_user") {
    return "轮数用完了，验收还没通过。你可以接受现在的成果，或者追加轮数让它继续。";
  }
  if (group.status === "paused") {
    return PAUSED_HINTS[group.stop_reason ?? ""] ?? "";
  }
  if (group.status === "failed") {
    return "出了意料之外的错误。点继续会从断的地方接着跑。";
  }
  if (group.status === "done" && group.stop_reason !== "accepted_by_user") {
    return "验收通过了。想再改，先在群聊里写下意见，再点按意见返工。";
  }
  return "";
}

export function discussIsActive(status: DiscussStatus | string): boolean {
  return status === "planning" || status === "running";
}

export function discussNeedsAuthor(
  group: Pick<DiscussSummary, "status">,
): boolean {
  return group.status === "awaiting_start"
    || group.status === "awaiting_user"
    || group.status === "paused"
    || group.status === "failed";
}

export function discussActions(
  group: Pick<DiscussSummary, "status" | "output_version">,
): DiscussAction[] {
  const actions: DiscussAction[] = [];
  switch (group.status) {
    case "planning":
      actions.push("pause");
      break;
    case "awaiting_start":
      actions.push("start", "close");
      break;
    case "running":
      actions.push("pause");
      break;
    case "paused":
      actions.push("resume");
      if (group.output_version >= 1) actions.push("accept");
      actions.push("close");
      break;
    case "awaiting_user":
      actions.push("continue");
      if (group.output_version >= 1) actions.push("accept");
      actions.push("close");
      break;
    case "done":
      actions.push("rework");
      break;
    case "failed":
      actions.push("resume", "close");
      break;
    case "closed":
      break;
  }
  if (group.output_version >= 1) actions.push("export");
  actions.push("delete");
  return actions;
}

export function discussDefaultTab(
  group: Pick<DiscussSummary, "status" | "output_version">,
): DiscussTab {
  if (group.status === "awaiting_start") return "plan";
  if ((group.status === "awaiting_user"
    || group.status === "done"
    || group.status === "closed")
    && group.output_version >= 1) return "output";
  return "chat";
}

export function discussKindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? "";
}

export function mergeDiscussMessages(
  current: DiscussMessage[],
  incoming: DiscussMessage[],
): DiscussMessage[] {
  const merged = new Map<number, DiscussMessage>();
  for (const message of current) merged.set(message.id, message);
  for (const message of incoming) merged.set(message.id, message);
  return [...merged.values()].sort((left, right) => left.id - right.id);
}

export function applyPendingNotes(
  messages: DiscussMessage[],
  pendingNotes: number,
): DiscussMessage[] {
  const count = Number.isInteger(pendingNotes) && pendingNotes > 0 ? pendingNotes : 0;
  const userIds = messages
    .filter(message => message.sender === "user")
    .map(message => message.id)
    .sort((left, right) => right - left);
  const unread = new Set(userIds.slice(0, count));
  return messages.map(message => message.sender === "user"
    ? { ...message, consumed: !unread.has(message.id) }
    : message);
}

/**
 * 读取游标只由「服务器读回的消息」推进：取旧游标与本批消息最大 id 的较大值。
 * 插话被本地并进列表时不调用这个函数，避免跳过插话之前尚未读到的引擎消息。
 */
export function advanceDiscussCursor(
  cursor: number,
  messages: Pick<DiscussMessage, "id">[],
): number {
  let next = Number.isInteger(cursor) && cursor > 0 ? cursor : 0;
  if (!Array.isArray(messages)) return next;
  for (const message of messages) {
    const id = message?.id;
    if (typeof id === "number" && Number.isInteger(id) && id > next) next = id;
  }
  return next;
}

/** 调研成员（角色池或自定义）有 non-empty focus 时显示分工。 */
export function discussMemberShowsFocus(
  member: Pick<DiscussMember, "kind" | "focus">,
): boolean {
  return (member.kind === "lens" || member.kind === "custom")
    && typeof member.focus === "string"
    && member.focus.trim().length > 0;
}

export interface DiscussRoundGroup {
  round: number;
  label: string;
  messages: DiscussMessage[];
}

export function groupDiscussRounds(messages: DiscussMessage[]): DiscussRoundGroup[] {
  const groups: DiscussRoundGroup[] = [];
  for (const message of messages) {
    const last = groups[groups.length - 1];
    if (last && last.round === message.round) {
      last.messages.push(message);
      continue;
    }
    groups.push({
      round: message.round,
      label: message.round === 0 ? "立项" : `第 ${message.round} 轮`,
      messages: [message],
    });
  }
  return groups;
}

export type DiscussDocumentBlock =
  | { kind: "markdown"; text: string }
  | { kind: "table"; header: string[]; rows: string[][] };

const TABLE_ROW = /^\s*\|/;
const TABLE_SEPARATOR = /^[\s|:-]+$/;
const isSeparator = (line: string) => TABLE_SEPARATOR.test(line) && /-{3,}/.test(line);

function tableCells(line: string): string[] {
  const trimmed = line.trim();
  const withoutStart = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const inner = withoutStart.endsWith("|") ? withoutStart.slice(0, -1) : withoutStart;
  return inner.split("|").map(cell => cell.trim());
}

/** 表格最小宽度：每列至少 8em；列少时由 w-full 撑满容器。 */
export function discussTableMinWidth(columnCount: number): number {
  const count = Number.isFinite(columnCount)
    ? Math.max(1, Math.trunc(columnCount))
    : 1;
  return count * 8;
}

export function splitDiscussDocument(text: string): DiscussDocumentBlock[] {
  if (typeof text !== "string") return [];
  const lines = text.split("\n");
  const blocks: DiscussDocumentBlock[] = [];
  let pending: string[] = [];
  let inFence = false;

  const flush = () => {
    if (pending.length === 0) return;
    const value = pending.join("\n");
    pending = [];
    if (value.trim()) blocks.push({ kind: "markdown", text: value });
  };

  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (line.startsWith("```")) {
      inFence = !inFence;
      pending.push(line);
      index += 1;
      continue;
    }
    if (!inFence
      && TABLE_ROW.test(line)
      && index + 1 < lines.length
      && isSeparator(lines[index + 1])) {
      flush();
      const header = tableCells(line);
      const rows: string[][] = [];
      let rowIndex = index + 2;
      while (rowIndex < lines.length && TABLE_ROW.test(lines[rowIndex])) {
        const cells = tableCells(lines[rowIndex]).slice(0, header.length);
        while (cells.length < header.length) cells.push("");
        rows.push(cells);
        rowIndex += 1;
      }
      blocks.push({ kind: "table", header, rows });
      index = rowIndex;
      continue;
    }
    pending.push(line);
    index += 1;
  }
  flush();
  return blocks;
}

export type DiscussInlineBlock =
  | { kind: "text"; text: string }
  | { kind: "cite"; id: string };

export function splitDiscussCitations(text: string): DiscussInlineBlock[] {
  if (typeof text !== "string" || text === "") return [];
  const blocks: DiscussInlineBlock[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[S(\d{1,4})\]/g)) {
    const start = match.index ?? 0;
    if (start > last) blocks.push({ kind: "text", text: text.slice(last, start) });
    blocks.push({ kind: "cite", id: `S${match[1]}` });
    last = start + match[0].length;
  }
  if (last === 0) return [{ kind: "text", text }];
  if (last < text.length) blocks.push({ kind: "text", text: text.slice(last) });
  return blocks;
}

export function safeExternalUrl(url: unknown): string | null {
  if (typeof url !== "string") return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

function memberName(draft: { name: string; default_name?: string }): string {
  return draft.name.trim() || (draft.default_name ?? "").trim();
}

/**
 * 自定义成员没有目录默认值，取角色池成员（catalog.roles 里 kind=lens）的默认模型。
 * 目录真实形状里角色池成员都是 DeepSeek Flash，与后端未指定时的回落一致。
 */
export function defaultDiscussCustomMemberModel(
  catalog: Pick<DiscussCatalog, "roles" | "defaults">,
): string {
  for (const role of catalog.roles ?? []) {
    if (role.kind !== "lens") continue;
    const value = catalog.defaults?.[role.id];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

export function validateDiscussCreate(
  form: DiscussCreateForm,
  limits: DiscussLimits,
): string {
  const request = form.request.trim();
  if (request.length < limits.request_min || request.length > limits.request_max) {
    return `诉求需要 ${limits.request_min}–${limits.request_max} 字`;
  }
  if (form.materials.length > limits.materials_max) {
    return `补充材料最多 ${limits.materials_max} 字`;
  }
  if (!Number.isInteger(form.budget_strawberries)
    || form.budget_strawberries < limits.budget_min
    || form.budget_strawberries > limits.budget_max) {
    return `预算需要 ${limits.budget_min}–${limits.budget_max} 颗`;
  }
  if (!Number.isInteger(form.max_rounds)
    || form.max_rounds < limits.rounds_min
    || form.max_rounds > limits.rounds_max) {
    return `轮数需要 ${limits.rounds_min}–${limits.rounds_max} 轮`;
  }

  if (form.team === "self") {
    const selected = form.lenses.filter(lens => lens.selected);
    const custom = form.custom_members;
    const memberCount = selected.length + custom.length;
    if (memberCount < limits.members_min || memberCount > limits.members_max) {
      return `调研成员需要 ${limits.members_min}–${limits.members_max} 位`;
    }
    if (custom.some(item => !item.name.trim() || !item.does.trim())) {
      return "自定义成员要写名字和职责";
    }
    const names = [
      ...selected.map(lens => memberName(lens)),
      ...custom.map(item => item.name.trim()),
    ];
    if (names.some(name => name.length > limits.name_max)) {
      return `名字最多 ${limits.name_max} 字`;
    }
    if (custom.some(item => item.does.trim().length > limits.custom_does_max)) {
      return `职责最多 ${limits.custom_does_max} 字`;
    }
    const seen = new Set<string>();
    for (const name of names) {
      if (!name) continue;
      if (seen.has(name)) return "成员的名字不能重复";
      seen.add(name);
    }
  }

  if (form.identities.some(seat => seat.name.trim().length > limits.name_max)) {
    return `固定席位的名字最多 ${limits.name_max} 字`;
  }
  if (form.identities.some(seat => seat.persona.length > limits.persona_max)) {
    return `身份设定最多 ${limits.persona_max} 字`;
  }
  return "";
}

export function buildDiscussCreateBody(form: DiscussCreateForm): DiscussCreateInput {
  const body: DiscussCreateInput = {
    request: form.request.trim(),
    materials: form.materials.trim(),
    budget_strawberries: form.budget_strawberries,
    max_rounds: form.max_rounds,
    avatar: form.avatar,
  };
  const models: Record<string, string> = {};

  if (form.team === "self") {
    const members: DiscussMemberInput[] = [];
    for (const lens of form.lenses) {
      if (!lens.selected) continue;
      const name = lens.name.trim() || lens.default_name.trim();
      const does = lens.does.trim() || lens.default_does.trim();
      const member: DiscussMemberInput = { role: lens.role };
      if (name !== lens.default_name.trim() || does !== lens.default_does.trim()) {
        member.name = name;
        member.does = does;
      }
      members.push(member);
      if (lens.model && lens.model !== lens.default_model) models[lens.role] = lens.model;
    }
    form.custom_members.forEach((member, index) => {
      members.push({ name: member.name.trim(), does: member.does.trim() });
      // 自定义成员没有后端目录默认值，始终把界面显示的模型发给后端。
      models[`custom${index + 1}`] = member.model;
    });
    body.members = members;
  }

  for (const seat of form.identities) {
    if (seat.model && seat.model !== seat.default_model) models[seat.role] = seat.model;
  }
  if (form.avatar
    && form.avatar_model
    && form.avatar_model !== form.default_avatar_model) {
    models.avatar = form.avatar_model;
  }
  if (Object.keys(models).length > 0) body.models = models;

  const identities: Record<string, DiscussIdentityInput> = {};
  for (const seat of form.identities) {
    const name = seat.name.trim();
    const persona = seat.persona;
    if (!name && !persona.trim()) continue;
    const entry: DiscussIdentityInput = {};
    if (name) entry.name = name;
    if (persona.trim()) entry.persona = persona;
    identities[seat.role] = entry;
  }
  if (Object.keys(identities).length > 0) body.identities = identities;
  return body;
}

/**
 * 新建页按任务卡预填：返回新表单，不改入参。诉求与补充材料照卡片原样填；
 * 卡片给了整数建议时夹在目录给出的上下限之间，没给或不是整数时保留表单原值。
 */
export function applyDiscussTaskPrefill(
  form: DiscussCreateForm,
  task: Pick<DiscussTaskCardView, "request" | "materials" | "max_rounds" | "budget_strawberries">,
  limits: Pick<DiscussLimits, "rounds_min" | "rounds_max" | "budget_min" | "budget_max">,
): DiscussCreateForm {
  const suggestedRounds = task.max_rounds;
  const suggestedBudget = task.budget_strawberries;
  const maxRounds = typeof suggestedRounds === "number" && Number.isInteger(suggestedRounds)
    ? Math.min(Math.max(suggestedRounds, limits.rounds_min), limits.rounds_max)
    : form.max_rounds;
  const budgetStrawberries = typeof suggestedBudget === "number" && Number.isInteger(suggestedBudget)
    ? Math.min(Math.max(suggestedBudget, limits.budget_min), limits.budget_max)
    : form.budget_strawberries;
  return {
    ...form,
    request: task.request,
    materials: typeof task.materials === "string" ? task.materials : form.materials,
    max_rounds: maxRounds,
    budget_strawberries: budgetStrawberries,
  };
}

interface PickShape {
  role: string;
  name: string;
  does: string;
  focus: string;
}

const samePicks = (left: PickShape[], right: PickShape[]) =>
  left.length === right.length
  && left.every((pick, index) => pick.role === right[index].role
    && pick.name === right[index].name
    && pick.does === right[index].does
    && pick.focus === right[index].focus);

export function buildDiscussPlanPatch(
  detail: DiscussDetail,
  draft: DiscussPlanDraft,
): DiscussPlanPatchInput {
  const patch: DiscussPlanPatchInput = { expected_revision: detail.plan_revision };

  const title = draft.title.trim();
  if (title !== detail.title.trim()) patch.title = title;

  const currentCriteria = (detail.plan?.criteria ?? []).map(item => item.text);
  if (currentCriteria.length !== draft.criteria.length
    || currentCriteria.some((text, index) => text !== draft.criteria[index])) {
    patch.criteria = [...draft.criteria];
  }

  const currentPicks: PickShape[] = (detail.plan?.picks ?? []).map(item => ({
    role: item.role,
    name: item.name,
    does: item.does,
    focus: item.focus,
  }));
  const draftPicks: PickShape[] = draft.picks.map(item => ({
    role: (item.role ?? "").trim(),
    name: item.name.trim(),
    does: item.does.trim(),
    focus: item.focus.trim(),
  }));
  if (!samePicks(currentPicks, draftPicks)) {
    patch.picks = draftPicks.map((pick): DiscussPlanPickInput => pick.role
      ? { role: pick.role, name: pick.name, does: pick.does, focus: pick.focus }
      : { name: pick.name, does: pick.does, focus: pick.focus });
  }

  const currentSeats = new Map(
    detail.members
      .filter(member => member.kind === "core")
      .map(member => [member.role, member] as const),
  );
  const identities: Record<string, DiscussIdentityInput> = {};
  for (const seat of draft.identities) {
    const current = currentSeats.get(seat.role);
    const currentName = current?.name ?? "";
    const currentPersona = current?.does ?? "";
    const name = seat.name.trim();
    if (name === currentName && seat.persona === currentPersona) continue;
    const entry: DiscussIdentityInput = {};
    if (name !== currentName) entry.name = name;
    if (seat.persona !== currentPersona) entry.persona = seat.persona;
    identities[seat.role] = entry;
  }
  if (Object.keys(identities).length > 0) patch.identities = identities;

  if (draft.budget_strawberries !== detail.budget_strawberries) {
    patch.budget_strawberries = draft.budget_strawberries;
  }
  if (draft.max_rounds !== detail.max_rounds) {
    patch.max_rounds = draft.max_rounds;
  }
  const currentAvatar = detail.members.some(member => member.kind === "avatar");
  if (draft.avatar !== currentAvatar) patch.avatar = draft.avatar;

  const currentModels = new Map(
    detail.members.map(member => [member.role, member.model] as const),
  );
  const models: Record<string, string> = {};
  for (const [role, model] of Object.entries(draft.models)) {
    if (!model || currentModels.get(role) === model) continue;
    models[role] = model;
  }
  if (Object.keys(models).length > 0) patch.models = models;

  if (draft.answers !== detail.answers) patch.answers = draft.answers;
  return patch;
}

export function discussPlanPatchIsEmpty(patch: DiscussPlanPatchInput): boolean {
  if (!patch || typeof patch !== "object") return true;
  return Object.keys(patch).every(key => key === "expected_revision");
}

function property(source: unknown, key: string): unknown {
  return source !== null && typeof source === "object"
    ? (source as Record<string, unknown>)[key]
    : undefined;
}

export function discussErrorMessage(error: unknown): string {
  const status = property(error, "status");
  const message = property(error, "message");
  if (status === 404 && typeof message === "string" && message.trim() === "Not Found") {
    return "讨论群尚未开放";
  }
  if (status === 403) return "你的账号暂未开通讨论群";
  if (typeof message === "string" && /[\u3400-\u9fff]/.test(message)) return message;
  return "请求未完成，请稍后重试。";
}

export function discussHref(path: string, embedded: boolean): string {
  return embedded ? `${path}${path.includes("?") ? "&" : "?"}embed=1` : path;
}

export function discussModelLabel(id: string): string {
  return ({
    "dashscope:qwen3.8-max": "千问 3.8 Max",
    "deepseek:deepseek-flash": "DeepSeek Flash",
    "ark:doubao-seed-2-1-pro-260915": "豆包 Seed 2.1 Pro",
    "byok:self": "我的模型",
  } as Record<string, string>)[id] ?? id;
}
