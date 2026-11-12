import type { NovelChapterSummary } from "@/lib/novels";

export type DeskStage = "idea" | "chapters" | "episodes" | "shots" | "film";
export type DeskMode = "dock" | "drawer" | "sheet";
export type DeskSubject = { kind: "draft"; draftId: string } | { kind: "project"; projectId: string };
export interface DeskPrefs { open: boolean; novelId: string | null; stage: DeskStage }

export const DESK_STAGES: readonly { id: DeskStage; label: string; enabled: boolean }[] = [
  { id: "idea", label: "立意", enabled: true },
  { id: "chapters", label: "章回", enabled: true },
  { id: "episodes", label: "分集", enabled: true },
  { id: "shots", label: "分镜", enabled: false },
  { id: "film", label: "成片", enabled: false },
];

export const DESK_DEFAULT_PREFS: DeskPrefs = { open: false, novelId: null, stage: "chapters" };

const ID = /^[0-9a-f-]{36}$/;
const PROJECT_PATH = /^\/studio\/([A-Za-z0-9_-]{1,64})$/;

function defaultPrefs(): DeskPrefs {
  return { ...DESK_DEFAULT_PREFS };
}

export function deskMode(width: number): DeskMode {
  if (width >= 1440) return "dock";
  if (width >= 768) return "drawer";
  return "sheet";
}

export function deskAutoOpens(width: number): boolean {
  return deskMode(width) !== "sheet";
}

export function deskStageByKey(
  current: DeskStage,
  key: string,
  orientation: "vertical" | "horizontal",
): DeskStage | null {
  const enabled = DESK_STAGES.filter(item => item.enabled);
  const index = enabled.findIndex(item => item.id === current);
  if (index < 0) return null;
  if (key === "Home") return enabled[0].id;
  if (key === "End") return enabled[enabled.length - 1].id;
  const delta = orientation === "vertical"
    ? (key === "ArrowDown" ? 1 : key === "ArrowUp" ? -1 : 0)
    : (key === "ArrowRight" ? 1 : key === "ArrowLeft" ? -1 : 0);
  if (delta === 0) return null;
  return enabled[(index + delta + enabled.length) % enabled.length].id;
}

export function deskSubjectFromCard(card: unknown): DeskSubject | null {
  if (card === null || typeof card !== "object" || Array.isArray(card)) return null;
  const candidate = card as Record<string, unknown>;
  if (candidate.subtype === "novel_draft") {
    return typeof candidate.draft_id === "string" && ID.test(candidate.draft_id)
      ? { kind: "draft", draftId: candidate.draft_id }
      : null;
  }
  if (candidate.subtype === "studio_project") {
    if (candidate.error) return null;
    if (typeof candidate.url !== "string") return null;
    const match = PROJECT_PATH.exec(candidate.url);
    return match ? { kind: "project", projectId: match[1] } : null;
  }
  return null;
}

export function deskAskPrefix(target: { title: string | null; chapter?: number; episode?: number }): string {
  const title = target.title?.trim() ?? "";
  const subject = title ? `《${title}》` : "这本书";
  if (target.chapter !== undefined && target.chapter !== null) {
    return `关于${subject}第 ${target.chapter} 章：`;
  }
  if (target.episode !== undefined && target.episode !== null) {
    return `关于${subject}第 ${target.episode} 集：`;
  }
  return `关于${subject}：`;
}

export function deskPrefsKey(username: string): string {
  return "fiona.desk.v1:" + username;
}

export function parseDeskPrefs(raw: string | null): DeskPrefs {
  if (raw === null) return defaultPrefs();
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return defaultPrefs();
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) return defaultPrefs();
  const record = value as Record<string, unknown>;
  const stage = DESK_STAGES.find(item => item.enabled && item.id === record.stage)?.id ?? "chapters";
  return {
    open: record.open === true,
    novelId: typeof record.novelId === "string" && ID.test(record.novelId) ? record.novelId : null,
    stage,
  };
}

export function readDeskPrefs(storage: Pick<Storage, "getItem"> | null | undefined, username: string): DeskPrefs {
  if (!storage || username === "") return defaultPrefs();
  try {
    return parseDeskPrefs(storage.getItem(deskPrefsKey(username)));
  } catch {
    return defaultPrefs();
  }
}

export function updateDeskPrefs(
  storage: Pick<Storage, "getItem" | "setItem"> | null | undefined,
  username: string,
  patch: Partial<DeskPrefs>,
): DeskPrefs {
  const current = readDeskPrefs(storage, username);
  const merged = parseDeskPrefs(JSON.stringify({ ...current, ...patch }));
  if (storage && username !== "") {
    try {
      storage.setItem(deskPrefsKey(username), JSON.stringify(merged));
    } catch {
      // 记忆偏好失败不影响案头使用
    }
  }
  return merged;
}

export function chapterTag(
  chapter: Pick<NovelChapterSummary, "chapter" | "status">,
  chaptersDone: number,
): { label: string; settled: boolean } {
  switch (chapter.status) {
    case "stale":
      return { label: "待复核", settled: false };
    case "awaiting_plan_approval":
      return { label: "细纲等你确认", settled: false };
    case "planning":
      return { label: "定细纲中", settled: false };
    case "writing":
      return { label: "写作中", settled: false };
    case "failed":
      return { label: "出错了", settled: false };
    case "done":
      return chapter.chapter <= chaptersDone
        ? { label: "定稿", settled: true }
        : { label: "处理中", settled: false };
    default:
      return { label: "处理中", settled: false };
  }
}

export function currentChapterNumber(
  book: { chapters_done: number; chapters: Pick<NovelChapterSummary, "chapter" | "status">[] },
): number | null {
  if (book.chapters.length === 0) return null;
  const pending = book.chapters.find(chapter => chapter.status !== "done" && chapter.status !== "stale");
  return pending ? pending.chapter : book.chapters[book.chapters.length - 1].chapter;
}

export function episodeLocks(
  plan: { status?: string; active_breakdown_status?: string | null; rebreakdown_pending?: boolean },
): { editsBlocked: boolean; approvalBlocked: boolean } {
  const activeStatus = plan.active_breakdown_status ?? plan.status;
  const regenerating = activeStatus === "running" || activeStatus === "partial";
  const editsBlocked = regenerating || !!plan.rebreakdown_pending;
  const approvalBlocked = editsBlocked || (plan.status !== undefined && plan.status !== "done");
  return { editsBlocked, approvalBlocked };
}

export function isRevisionConflict(
  previousRevision: number,
  refreshed: { plan_revision: number } | null | undefined,
): boolean {
  return !!refreshed && refreshed.plan_revision !== previousRevision;
}

export function latestProject<T extends { id: string; created_at: string }>(projects: readonly T[]): T | null {
  let latest: T | null = null;
  for (const project of projects) {
    if (!latest || project.created_at > latest.created_at) latest = project;
  }
  return latest;
}
