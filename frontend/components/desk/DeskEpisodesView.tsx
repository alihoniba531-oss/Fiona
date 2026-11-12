"use client";

import { useEffect, useState } from "react";

import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import BreakdownDialog from "@/components/studio/BreakdownDialog";
import { EpisodeEditDialog } from "@/components/studio/EpisodePlan";
import { deskAskPrefix, episodeLocks } from "@/lib/desk";
import type { StudioNovelCandidate } from "@/lib/studio";
import {
  formatEpisodeDuration,
  type EpisodeFields,
  type StudioEpisode,
  type StudioEpisodePlan,
} from "@/lib/studio-breakdown";

type DeskEpisodeOperation =
  | { op: "edit"; no: number; fields: EpisodeFields }
  | { op: "merge"; no: number };

type DeskEpisodesViewProps = {
  studioAllowed: boolean;
  bookTitle: string | null;
  candidate: StudioNovelCandidate | null | undefined;
  candidateError: string | null;
  candidateLoading: boolean;
  projectId: string | null;
  onSelectProject: (projectId: string) => void;
  plan: StudioEpisodePlan | null;
  planLoading: boolean;
  planError: string | null;
  busy: boolean;
  onOperate: (operation: DeskEpisodeOperation) => Promise<void>;
  onApprove: () => Promise<void>;
  onOpenStudio: (projectId: string) => void;
  onAsk: (prefix: string) => void;
  onRefresh: () => void;
  notice: string | null;
  initialExpanded?: number | null;
  initialDialog?: { kind: "edit" | "merge"; no: number } | { kind: "approve" } | null;
  onDialogOpenChange?: (open: boolean) => void;
};

export default function DeskEpisodesView({
  studioAllowed,
  bookTitle,
  candidate,
  candidateError,
  candidateLoading,
  projectId,
  onSelectProject,
  plan,
  planLoading,
  planError,
  busy,
  onOperate,
  onApprove,
  onOpenStudio,
  onAsk,
  onRefresh,
  notice,
  initialExpanded = null,
  initialDialog = null,
  onDialogOpenChange,
}: DeskEpisodesViewProps) {
  const [expanded, setExpanded] = useState<number | null>(initialExpanded);
  const [editing, setEditing] = useState<StudioEpisode | null>(() => {
    if (initialDialog?.kind !== "edit") return null;
    return plan?.episodes.find(episode => episode.no === initialDialog.no) ?? null;
  });
  const [merging, setMerging] = useState<StudioEpisode | null>(() => {
    if (initialDialog?.kind !== "merge") return null;
    return plan?.episodes.find(episode => episode.no === initialDialog.no) ?? null;
  });
  const [approving, setApproving] = useState(initialDialog?.kind === "approve");
  const dialogOpen = editing !== null || merging !== null || approving;

  useEffect(() => {
    onDialogOpenChange?.(dialogOpen);
    return () => { if (dialogOpen) onDialogOpenChange?.(false); };
  }, [dialogOpen, onDialogOpenChange]);

  if (!studioAllowed) {
    return <p className="py-3 text-fs-13 text-[color:var(--ink2)]">短片工作室暂未对该账号开放。</p>;
  }

  if (candidateLoading) {
    return <LoadingState>正在取回作品…</LoadingState>;
  }

  if (candidateError) {
    return <ErrorNotice message={candidateError} retry={onRefresh} />;
  }

  if (candidate === undefined) {
    return <LoadingState>正在取回作品…</LoadingState>;
  }

  const projects = candidate?.projects ?? [];
  if (!candidate || projects.length === 0) {
    const title = bookTitle?.trim() ?? "";
    const subject = title ? `《${title}》` : "这本书";
    const message = candidate?.eligible
      ? `这本书还没有短片项目。对分身说「把${subject}做成片」，或在书斋里点「做成片」。`
      : `这本书还没有短片项目。${candidate?.reason?.trim() || ""}`;
    return <EmptyState>{message}</EmptyState>;
  }

  const { editsBlocked, approvalBlocked } = plan ? episodeLocks(plan) : { editsBlocked: false, approvalBlocked: false };
  const uncovered = plan ? plan.unassigned ?? plan.uncovered ?? [] : [];
  const openStudio = () => {
    if (projectId) onOpenStudio(projectId);
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      {projects.length > 1 && (
        <div className="shrink-0 pb-2">
          <select
            aria-label="短片项目"
            className="min-h-10 w-full min-w-0 rounded-lg border border-[color:var(--rule)] bg-[color:var(--hi)] px-2 text-fs-13 text-[color:var(--ink)]"
            value={projectId ?? ""}
            onChange={event => onSelectProject(event.target.value)}
          >
            {projects.map(project => (
              <option key={project.id} value={project.id}>
                {project.title}
              </option>
            ))}
          </select>
        </div>
      )}

      {planLoading ? (
        <LoadingState>正在取回分集方案…</LoadingState>
      ) : planError ? (
        <ErrorNotice message={planError} retry={onRefresh} />
      ) : plan === null || plan.episodes.length === 0 ? (
        <div>
          <EmptyState>还没有分集方案，拆解在工作室里做。</EmptyState>
          <button type="button" className="btn btn-quiet min-h-10" onClick={openStudio}>
            在工作室打开
          </button>
        </div>
      ) : (
        <>
          <div className="flex shrink-0 items-start justify-between gap-3">
            <p className="min-w-0 text-fs-13">
              {`方案第 ${plan.plan_revision} 版　共 ${plan.episodes.length} 集　约 ${formatEpisodeDuration(plan.total_seconds)}`}
            </p>
            <span className={plan.g0_approved ? "tag text-[color:var(--seal)] border-[color:var(--seal)]" : "tag"}>
              {plan.g0_approved ? "已批准" : "待批准"}
            </span>
          </div>
          {notice && <p role="alert" className="mt-2 shrink-0 break-words text-fs-13 text-[color:var(--ink)]">{notice}</p>}

          {(editsBlocked || uncovered.length > 0) && (
            <div className="shrink-0 space-y-1 pt-2">
              {editsBlocked && (
                <p role="status" className="text-fs-13">
                  拆解还没全部完成，暂时不能修改或批准，去工作室看进度。
                </p>
              )}
              {uncovered.length > 0 && (
                <p role="status" className="text-fs-13 text-[color:var(--ink2)]">
                  还有 {uncovered.length} 段原文没有纳入分集，在工作室处理。
                </p>
              )}
            </div>
          )}

          <div className="mt-2 min-h-0 flex-1 overflow-y-auto">
            {plan.episodes.length === 0 ? (
              <EmptyState>还没有分集方案，拆解在工作室里做。</EmptyState>
            ) : (
              <div role="list" aria-label="分集">
                {plan.episodes.map((episode, index) => {
                  const isOpen = expanded === episode.no;
                  const isLast = index === plan.episodes.length - 1;
                  return (
                    <div
                      key={episode.id || episode.no}
                      role="listitem"
                      className="grid grid-cols-[36px_minmax(0,1fr)_auto] items-start gap-3 border-b border-[color:var(--rule)] py-3 last:border-b-0"
                    >
                      <span aria-hidden="true" className="readout text-fs-18 text-[color:var(--ink2)]">
                        {episode.no}
                      </span>
                      <div className="min-w-0">
                        <button
                          type="button"
                          className="flex min-h-10 w-full min-w-0 items-center whitespace-normal break-words text-left text-fs-15"
                          aria-label={`第 ${episode.no} 集　${episode.title}`}
                          aria-expanded={isOpen}
                          onClick={() => setExpanded(current => (current === episode.no ? null : episode.no))}
                        >
                          {episode.title}
                        </button>
                        <p className={`mt-0.5 break-words text-fs-13 text-[color:var(--ink2)] ${isOpen ? "" : "line-clamp-3"}`}>
                          变化：{episode.change || "—"}
                        </p>
                        <p className={`mt-0.5 break-words text-fs-13 text-[color:var(--ink)] ${isOpen ? "" : "line-clamp-3"}`}>
                          钩子：{episode.hook || "—"}
                        </p>
                        {isOpen && (
                          <div className="mt-1 flex flex-wrap items-center gap-x-1">
                            <button
                              type="button"
                              className="btn btn-quiet min-h-10"
                              disabled={busy || editsBlocked}
                              onClick={() => setEditing(episode)}
                            >
                              修改
                            </button>
                            <button
                              type="button"
                              className="btn btn-quiet min-h-10"
                              disabled={isLast || busy || editsBlocked}
                              onClick={() => setMerging(episode)}
                            >
                              与下一集合并
                            </button>
                            <button
                              type="button"
                              className="btn btn-quiet min-h-10"
                              onClick={() => onAsk(deskAskPrefix({ title: bookTitle, episode: episode.no }))}
                            >
                              问分身
                            </button>
                          </div>
                        )}
                      </div>
                      <div className="flex min-w-0 flex-col items-end gap-1">
                        <span className="readout whitespace-nowrap">{formatEpisodeDuration(episode.est_seconds)}</span>
                        {episode.warnings.length > 0 && (
                          <span className="tag" title={episode.warnings.join("\n")}>
                            有提示
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="shrink-0 border-t border-[color:var(--rule)] pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn btn-primary min-h-10"
                disabled={busy || approvalBlocked || plan.episodes.length === 0 || plan.g0_approved}
                onClick={() => setApproving(true)}
              >
                批准分集方案
              </button>
              <button type="button" className="btn btn-quiet min-h-10" onClick={openStudio}>
                在工作室打开
              </button>
            </div>
          </div>

          {editing && (
            <EpisodeEditDialog
              key={plan.plan_revision}
              episode={editing}
              busy={busy}
              onSave={fields => {
                if (editsBlocked) {
                  return Promise.reject(new Error("拆解还没全部完成，暂时不能修改或批准，去工作室看进度。"));
                }
                return onOperate({ op: "edit", no: editing.no, fields });
              }}
              onClose={() => setEditing(null)}
            />
          )}

          {merging && (
            <BreakdownDialog
              title="与下一集合并"
              confirmLabel="确认合并"
              busy={busy}
              disabled={editsBlocked}
              onClose={() => setMerging(null)}
              onConfirm={async () => {
                await onOperate({ op: "merge", no: merging.no });
                setMerging(null);
              }}
            >
              <p className="break-words">
                把第 {merging.no} 集和第 {merging.no + 1} 集合成一集，标题、变化、钩子会拼在一起。
              </p>
            </BreakdownDialog>
          )}

          {approving && (
            <BreakdownDialog
              title="批准分集方案"
              confirmLabel="确认批准"
              busy={busy}
              disabled={approvalBlocked}
              onClose={() => setApproving(false)}
              onConfirm={async () => {
                await onApprove();
                setApproving(false);
              }}
            >
              <p className="break-words">
                即将批准方案第 {plan.plan_revision} 版。批准后再改会生成新版本、需要重新批准。
              </p>
            </BreakdownDialog>
          )}
        </>
      )}
    </div>
  );
}
