"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  formatElapsed,
  generateSong,
  isInstrumentalType,
  parseSongTimestamp,
  sectionTypeLabel,
  songAudioUrl,
  songBriefTags,
  useSongProject,
  type SongBrief,
  type SongCheck,
  type SongLyrics,
  type SongProject,
  type SongSection,
  type SongVersion,
} from "@/lib/songs";

export interface SongProjectCardProps {
  projectId: string;
  onCompose?: (text: string) => void;
}

function SongCardShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="ceramic-card w-full max-w-[600px] min-w-0 overflow-hidden">
      <div
        className="flex min-w-0 flex-wrap items-center justify-between gap-2 border-b px-4 py-3"
        style={{ borderColor: "var(--carve)" }}
      >
        <span className="min-w-0 break-words text-fs-15 text-[color:var(--ink)]">
          {title ? `写歌 ·《${title}》` : "写歌"}
        </span>
        <span className="tag shrink-0 text-fs-12">AI 生成</span>
      </div>
      <div className="min-w-0 px-4 py-3">{children}</div>
    </div>
  );
}

function BriefTags({ brief }: { brief: SongBrief | null | undefined }) {
  const tags = songBriefTags(brief);
  if (!tags.length) return null;
  return (
    <div className="flex min-w-0 flex-wrap gap-1.5">
      {tags.map((tag, index) => (
        <span key={`${index}:${tag}`} className="tag text-fs-12">
          {tag}
        </span>
      ))}
    </div>
  );
}

function countDisplayChars(line: string, lang: string | undefined): number {
  if (lang === "English") return line.trim().split(/\s+/).filter(Boolean).length;
  return line.match(/[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]|[A-Za-z0-9]+/g)?.length ?? 0;
}

function lineChecksFor(
  section: SongSection,
  check: SongCheck | null | undefined,
): Map<number, { chars: number; rhyme_ok: boolean | null }> {
  const rows = (check?.lines ?? []).filter(row => row.section_id === section.id);
  const result = new Map<number, { chars: number; rhyme_ok: boolean | null }>();
  if (!rows.length) return result;
  const oneBased = rows.every(row => row.line_index >= 1)
    && rows.some(row => row.line_index === section.lines.length);
  for (const row of rows) {
    result.set(oneBased ? row.line_index - 1 : row.line_index, {
      chars: row.chars,
      rhyme_ok: row.rhyme_ok,
    });
  }
  return result;
}

function SongLyricsSection({
  section,
  check,
  lang,
  changed,
  onCompose,
}: {
  section: SongSection;
  check: SongCheck | null | undefined;
  lang: string | undefined;
  changed: boolean;
  onCompose?: (text: string) => void;
}) {
  const instrumental = isInstrumentalType(section.type);
  const typeLabel = sectionTypeLabel(section.type);
  const lineChecks = lineChecksFor(section, check);
  const composeText = `把【${typeLabel} ${section.id}】改成：`;

  return (
    <section className="min-w-0">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="break-words text-fs-15 text-[color:var(--ink)]">
            {typeLabel} · {section.id}
          </span>
          {changed && <span className="tag text-fs-12">本稿修改</span>}
        </div>
        {!instrumental && (
          <button
            type="button"
            className="chip shrink-0 text-fs-12"
            disabled={!onCompose}
            onClick={() => onCompose?.(composeText)}
          >
            改这一段
          </button>
        )}
      </div>
      {instrumental ? (
        <p className="mt-1 text-fs-12 text-[color:var(--ink2)]">（器乐）</p>
      ) : (
        <div className="mt-1 space-y-1">
          {section.lines.map((line, index) => {
            const lineCheck = lineChecks.get(index);
            const chars = typeof lineCheck?.chars === "number"
              ? lineCheck.chars
              : countDisplayChars(line, lang);
            return (
              <div key={index} className="flex min-w-0 items-start justify-between gap-2">
                <p className="min-w-0 flex-1 whitespace-pre-wrap break-words text-fs-15 leading-6 text-[color:var(--ink)]">
                  {line || " "}
                </p>
                <span className="shrink-0 whitespace-nowrap text-fs-12 text-[color:var(--ink2)]">
                  <span>{chars} 字</span>
                  {lineCheck?.rhyme_ok === true && <span className="ml-1">押</span>}
                  {lineCheck?.rhyme_ok === false && (
                    <span className="ml-1" style={{ color: "var(--seal)" }}>不押</span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function SongCheckSummary({ check }: { check: SongCheck | null | undefined }) {
  const errors = check?.errors ?? [];
  const warnings = check?.warnings ?? [];
  if (!errors.length && !warnings.length) {
    return <p className="text-fs-12 text-[color:var(--ink2)]">字数与押韵检查通过</p>;
  }
  return (
    <div className="min-w-0 space-y-1">
      {errors.map((issue, index) => (
        <p key={`error-${index}`} className="whitespace-pre-wrap break-words text-fs-12" style={{ color: "var(--seal)" }}>
          {issue.message || issue.code}
        </p>
      ))}
      {warnings.map((issue, index) => (
        <p key={`warning-${index}`} className="whitespace-pre-wrap break-words text-fs-12" style={{ color: "var(--ink2)" }}>
          {issue.message || issue.code}
        </p>
      ))}
    </div>
  );
}

function versionStatusText(version: SongVersion): string {
  switch (version.status) {
    case "queued":
      return "排队中";
    case "submitting":
      return "正在提交";
    case "submitted":
    case "running": {
      const progress = Math.max(0, Math.min(100, Math.round(version.progress || 0)));
      return `生成中 ${progress}%`;
    }
    case "downloading":
      return "正在保存";
    case "succeeded":
      return "已完成";
    case "failed":
      return "失败";
    case "rejected":
      return "提交被拒，已退回草莓";
    case "uncertain":
      return "结果不确定，已退回草莓";
    case "expired":
      return "超时，已退回草莓";
    default:
      return version.status;
  }
}

function SongVersionRow({ version }: { version: SongVersion }) {
  const statusText = versionStatusText(version);
  const generating = version.status === "submitted" || version.status === "running";
  const failed = version.status === "failed";
  const audioUrl = version.status === "succeeded" ? songAudioUrl(version.id) : null;
  const elapsed = generating ? formatElapsed(version.created_at) : "";

  return (
    <div className="min-w-0 space-y-1">
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="break-words text-fs-15 text-[color:var(--ink)]">
          第 {version.lyrics_revision} 稿 · {statusText}
        </span>
        {elapsed && <span className="shrink-0 text-fs-12 text-[color:var(--ink2)]">{elapsed}</span>}
      </div>
      {failed && (
        <p className="whitespace-pre-wrap break-words text-fs-12" style={{ color: "var(--seal)" }}>
          {version.failure_message || "生成失败，请稍后再试"}
        </p>
      )}
      {version.status === "succeeded" && audioUrl && (
        <div className="min-w-0 space-y-1">
          <audio
            controls
            preload="none"
            src={audioUrl}
            aria-label={`第 ${version.lyrics_revision} 稿试听`}
            className="block w-full max-w-full"
          />
          <a
            href={`${audioUrl}?download=1`}
            className="inline-block text-fs-12 text-[color:var(--ink2)] underline underline-offset-2 hover:text-[color:var(--ink)]"
          >
            下载
          </a>
        </div>
      )}
    </div>
  );
}

function SongVersionList({ versions }: { versions: SongVersion[] }) {
  if (!versions.length) {
    return <p className="text-fs-12 text-[color:var(--ink2)]">还没有生成试听。</p>;
  }
  const ordered = versions
    .map((version, index) => ({ version, index, time: parseSongTimestamp(version.created_at) }))
    .sort((left, right) => {
      const leftTime = Number.isFinite(left.time) ? left.time : 0;
      const rightTime = Number.isFinite(right.time) ? right.time : 0;
      return rightTime - leftTime || left.index - right.index;
    })
    .map(item => item.version);
  return (
    <div className="min-w-0 space-y-3">
      {ordered.map(version => <SongVersionRow key={version.id} version={version} />)}
    </div>
  );
}

function GenerateAction({ project, refresh }: { project: SongProject; refresh: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const busyRef = useRef(false);
  const titleId = useId();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const lyricsRevision = project.lyrics?.revision ?? project.lyrics_revision;
  const durationSeconds = typeof project.brief?.duration_seconds === "number"
    && Number.isFinite(project.brief.duration_seconds)
    ? Math.round(project.brief.duration_seconds)
    : 0;
  const price = project.price_strawberries;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialogOpen && dialog && !dialog.open) dialog.showModal();
  }, [dialogOpen]);

  useEffect(() => () => { dialogRef.current?.close(); }, []);

  const openDialog = () => {
    if (!project.can_generate) return;
    setFailure("");
    setDialogOpen(true);
  };

  const closeDialog = () => {
    if (busyRef.current) return;
    setFailure("");
    dialogRef.current?.close();
    setDialogOpen(false);
  };

  const confirm = async () => {
    if (busyRef.current || !project.can_generate) return;
    busyRef.current = true;
    setBusy(true);
    setFailure("");
    try {
      await generateSong(project.id, lyricsRevision);
      dialogRef.current?.close();
      setDialogOpen(false);
      refresh();
    } catch (cause) {
      setFailure(cause instanceof Error ? cause.message : "生成请求失败，请稍后再试。");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="min-w-0">
      <button
        type="button"
        className="btn btn-primary max-w-full whitespace-normal text-fs-12"
        disabled={!project.can_generate || busy}
        title={!project.can_generate ? project.generate_blocked_reason ?? undefined : undefined}
        onClick={openDialog}
      >
        生成试听（{price} 草莓）
      </button>
      {!project.can_generate && project.generate_blocked_reason && (
        <p role="status" className="mt-1 text-fs-12 text-[color:var(--ink2)]">
          {project.generate_blocked_reason}
        </p>
      )}

      {dialogOpen && createPortal(
        <dialog
          ref={dialogRef}
          aria-labelledby={titleId}
          onCancel={event => {
            if (busyRef.current) event.preventDefault();
            else closeDialog();
          }}
          onClose={() => {
            setFailure("");
            setDialogOpen(false);
          }}
          className="m-auto max-h-[85dvh] w-[min(560px,calc(100vw-32px))] max-w-full overflow-y-auto rounded-[10px] border border-[color:var(--carve)] bg-[color:var(--paper)] p-5 text-[color:var(--ink)] backdrop:bg-[color:var(--scrim)]"
        >
          <div className="min-w-0 space-y-2 text-fs-15 leading-6">
            <p id={titleId} className="text-fs-16.5">确认生成试听</p>
            <p>
              将用第 {lyricsRevision} 稿歌词生成一首约 {durationSeconds} 秒的试听，预扣 {price} 颗草莓，失败自动退回。
            </p>
            <p>歌词与曲风参数会发送给字节跳动火山引擎生成音乐。</p>
            <p>生成的音频带有 AI 生成标识。</p>
            {failure && (
              <p role="alert" className="whitespace-pre-wrap break-words text-fs-12" style={{ color: "var(--seal)" }}>
                {failure}
              </p>
            )}
          </div>
          <div className="mt-4 flex flex-wrap justify-end gap-2">
            <button type="button" className="btn btn-quiet min-h-10 text-fs-12" disabled={busy} onClick={closeDialog}>
              取消
            </button>
            <button type="button" className="btn btn-primary min-h-10 text-fs-12" disabled={busy} onClick={() => void confirm()}>
              {busy ? "正在提交…" : "确认生成"}
            </button>
          </div>
        </dialog>,
        document.body,
      )}
    </div>
  );
}

function SongProjectBody({
  project,
  onCompose,
  refresh,
}: {
  project: SongProject;
  onCompose?: (text: string) => void;
  refresh: () => void;
}) {
  const lyrics = project.lyrics as SongLyrics;
  const changed = new Set([
    ...(lyrics.changed_section_ids ?? []),
    ...(project.changed_section_ids ?? []),
  ]);
  const lang = project.brief?.language;
  return (
    <div className="min-w-0 space-y-4">
      <BriefTags brief={project.brief} />
      <div className="min-w-0 space-y-4">
        {lyrics.sections.map(section => (
          <SongLyricsSection
            key={section.id}
            section={section}
            check={lyrics.check}
            lang={lang}
            changed={changed.has(section.id)}
            onCompose={onCompose}
          />
        ))}
      </div>
      <SongCheckSummary check={lyrics.check} />
      <GenerateAction project={project} refresh={refresh} />
      <div className="min-w-0 border-t pt-3" style={{ borderColor: "var(--carve)" }}>
        <p className="mb-2 text-fs-12 text-[color:var(--ink2)]">生成记录</p>
        <SongVersionList versions={project.versions ?? []} />
      </div>
    </div>
  );
}

export default function SongProjectCard({ projectId, onCompose }: SongProjectCardProps) {
  const { project, loading, error, refresh, notFound } = useSongProject(projectId);
  const title = typeof project?.title === "string" ? project.title.trim() : "";

  if (loading) {
    return (
      <SongCardShell title={title}>
        <p role="status" className="text-fs-13 text-[color:var(--ink2)]">正在读取写歌项目…</p>
      </SongCardShell>
    );
  }

  if (notFound) {
    return (
      <SongCardShell title={title}>
        <p className="text-fs-13 text-[color:var(--ink2)]">这个写歌项目已删除</p>
      </SongCardShell>
    );
  }

  if (error) {
    return (
      <SongCardShell title={title}>
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <p role="alert" className="text-fs-13" style={{ color: "var(--seal)" }}>写歌项目读取失败</p>
          <button type="button" className="btn btn-quiet min-h-10 px-3 text-fs-12" onClick={refresh}>
            重试
          </button>
        </div>
        {error !== "写歌项目读取失败" && (
          <p className="mt-1 whitespace-pre-wrap break-words text-fs-12 text-[color:var(--ink2)]">{error}</p>
        )}
      </SongCardShell>
    );
  }

  if (!project) {
    return (
      <SongCardShell title={title}>
        <p className="text-fs-13 text-[color:var(--ink2)]">写歌项目读取失败</p>
      </SongCardShell>
    );
  }

  if (!project.lyrics || !project.lyrics.sections?.length) {
    return (
      <SongCardShell title={title}>
        <div className="min-w-0 space-y-3">
          <BriefTags brief={project.brief} />
          <p className="text-fs-13 text-[color:var(--ink2)]">歌词还在写，Claude 提交后会显示在这里</p>
        </div>
      </SongCardShell>
    );
  }

  return (
    <SongCardShell title={title}>
      <SongProjectBody project={project} onCompose={onCompose} refresh={refresh} />
    </SongCardShell>
  );
}
