"use client";

import { useCallback, useEffect, useRef, useState, type JSX } from "react";
import DiscussDocument from "@/components/discuss/DiscussDocument";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import {
  getDiscussOutput,
  type DiscussDetail,
  type DiscussOutput,
  type DiscussOutputSummary,
  type DiscussSource,
  type DiscussVerdict,
} from "@/lib/discuss";
import { discussErrorMessage } from "@/lib/discussLogic";
import { useAccountRequest } from "@/lib/useAccountIdentity";

type OutputPanelProps = {
  owner: string;
  groupId: string;
  detail: DiscussDetail;
  sources: Record<string, DiscussSource>;
  requestedVersion?: number;
  onExport: () => void;
  exportBusy: boolean;
  onContentLoaded: (content: string | null) => void;
};

type ShownOutput = DiscussOutput | DiscussOutputSummary;
type VerdictRow = { id: string; pass: boolean; evidence: string };
type CitationIssueRow = { quote: string; problem: string };

function verdictRecord(verdict: DiscussVerdict | null | undefined): Record<string, unknown> | null {
  return verdict !== null && typeof verdict === "object"
    ? verdict as Record<string, unknown>
    : null;
}

// 验收载荷来自模型，字段缺失或类型不对时逐条跳过，不抛错。
function verdictRows(verdict: DiscussVerdict | null | undefined): VerdictRow[] {
  const record = verdictRecord(verdict);
  if (!record || !Array.isArray(record.verdicts)) return [];
  const rows: VerdictRow[] = [];
  for (const item of record.verdicts) {
    if (item === null || typeof item !== "object") continue;
    const entry = item as Record<string, unknown>;
    const { id, pass, evidence } = entry;
    if (typeof id !== "string" || !id) continue;
    if (typeof pass !== "boolean") continue;
    if (typeof evidence !== "string") continue;
    rows.push({ id, pass, evidence });
  }
  return rows;
}

function citationIssueRows(verdict: DiscussVerdict | null | undefined): CitationIssueRow[] {
  const record = verdictRecord(verdict);
  if (!record || !Array.isArray(record.citation_issues)) return [];
  const rows: CitationIssueRow[] = [];
  for (const item of record.citation_issues) {
    if (item === null || typeof item !== "object") continue;
    const entry = item as Record<string, unknown>;
    const { quote, problem } = entry;
    if (typeof quote !== "string" || typeof problem !== "string") continue;
    rows.push({ quote, problem });
  }
  return rows;
}

function reworkRows(verdict: DiscussVerdict | null | undefined): string[] {
  const record = verdictRecord(verdict);
  if (!record || !Array.isArray(record.rework)) return [];
  return record.rework.filter((item): item is string => typeof item === "string");
}

function hasVerdictValue(verdict: DiscussVerdict | null | undefined): verdict is DiscussVerdict {
  return verdict !== null && typeof verdict === "object";
}

function verdictLabel(output: ShownOutput): string {
  if (!hasVerdictValue(output.verdict)) return "等待验收";
  return output.passed ? "验收通过" : "验收未通过";
}

function contentWords(output: DiscussOutput): number {
  return typeof output.content === "string" ? Array.from(output.content.trim()).length : 0;
}

export default function DiscussOutputPanel(props: OutputPanelProps): JSX.Element {
  // 群或账号切换时重新挂载，版本选择与已加载正文不会串到另一个群。
  return <OutputPanelBody key={`${props.owner}:${props.groupId}`} {...props} />;
}

function OutputPanelBody({
  owner,
  groupId,
  detail,
  sources,
  requestedVersion,
  onExport,
  exportBusy,
  onContentLoaded,
}: OutputPanelProps): JSX.Element {
  const latestVersion = Math.max(0, detail.output_version);
  const hasOutput = latestVersion >= 1;
  const [selectedVersion, setSelectedVersion] = useState(latestVersion);
  const [acknowledgedLatest, setAcknowledgedLatest] = useState(latestVersion);
  const [output, setOutput] = useState<DiscussOutput | null>(null);
  const [loading, setLoading] = useState(hasOutput);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const contentLoadedRef = useRef(onContentLoaded);
  const requestedVersionRef = useRef(0);
  const { beginRequest } = useAccountRequest(owner);

  useEffect(() => {
    contentLoadedRef.current = onContentLoaded;
  }, [onContentLoaded]);

  // 点群聊里的「看这一版成果」时由父组件指定版本；同一次请求只应用一次，
  // 之后作者仍可自己切换版本。
  useEffect(() => {
    const wanted = requestedVersion;
    if (wanted === undefined || !Number.isInteger(wanted) || wanted < 1 || wanted > latestVersion) return;
    if (wanted === requestedVersionRef.current) return;
    requestedVersionRef.current = wanted;
    // 事件驱动的版本跳转放到微任务里，避免在 effect 同步 setState 触发级联渲染。
    void Promise.resolve().then(() => {
      setSelectedVersion(wanted);
      if (wanted >= latestVersion) setAcknowledgedLatest(latestVersion);
    });
  }, [latestVersion, requestedVersion]);

  // 页面先在第 0 版打开、随后才出现成果时，把第一版当作已看过的最新版；
  // 之后再有新版本才提示「有新的一版」。放到微任务里，避免同步 setState。
  useEffect(() => {
    if (latestVersion >= 1 && selectedVersion < 1) {
      void Promise.resolve().then(() => {
        setSelectedVersion(latestVersion);
        setAcknowledgedLatest(latestVersion);
      });
    }
  }, [latestVersion, selectedVersion]);

  // 选中的版本仍有效时保持不动；只有越界或还没选过版本时才显示最新版。
  const activeVersion = selectedVersion >= 1 && selectedVersion <= latestVersion
    ? selectedVersion
    : latestVersion;

  const load = useCallback(async () => {
    if (!owner || !hasOutput || activeVersion < 1) {
      setOutput(null);
      setLoading(false);
      setError("");
      contentLoadedRef.current(null);
      return;
    }
    const request = beginRequest();
    if (!request) return;
    setLoading(true);
    setError("");
    setOutput(null);
    contentLoadedRef.current(null);
    try {
      const next = await getDiscussOutput(groupId, activeVersion, request.signal);
      if (!request.isCurrent()) return;
      setOutput(next);
      contentLoadedRef.current(typeof next.content === "string" ? next.content : "");
    } catch (cause) {
      if (request.isCurrent()) setError(discussErrorMessage(cause));
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [activeVersion, beginRequest, groupId, hasOutput, owner]);

  useEffect(() => {
    void Promise.resolve().then(() => load());
  }, [load, reloadKey]);

  const currentOutput = output && output.version === activeVersion ? output : null;
  const shown: ShownOutput | null = currentOutput
    ?? (activeVersion === latestVersion ? detail.output : null);
  const failed = hasVerdictValue(shown?.verdict) && shown?.passed === false;
  const hasVerdict = hasVerdictValue(shown?.verdict);
  const verdict = shown?.verdict ?? null;
  const rows = verdictRows(verdict);
  const issues = citationIssueRows(verdict);
  const rework = reworkRows(verdict);
  const words = currentOutput
    ? contentWords(currentOutput)
    : activeVersion === latestVersion
      ? detail.output?.words
      : undefined;
  const showLoading = !!owner
    && (loading || (hasOutput && activeVersion >= 1 && !currentOutput && !error));
  const hasNewVersion = latestVersion > acknowledgedLatest
    && acknowledgedLatest > 0
    && activeVersion === acknowledgedLatest;

  if (!hasOutput) {
    return <EmptyState>成果还没写出来。撰稿人交稿后会出现在这里。</EmptyState>;
  }

  const selectVersion = (version: number) => {
    if (!Number.isInteger(version) || version < 1 || version > latestVersion) return;
    setSelectedVersion(version);
    if (version >= latestVersion) setAcknowledgedLatest(latestVersion);
  };

  return (
    <div className="min-w-0 space-y-4">
      {hasNewVersion && (
        <div
          role="status"
          className="ceramic-card flex flex-wrap items-center justify-between gap-2 p-3 text-fs-13"
        >
          <span className="text-[color:var(--ink)]">有新的一版</span>
          <button
            type="button"
            className="btn btn-quiet min-h-10"
            onClick={() => selectVersion(latestVersion)}
          >
            看最新版
          </button>
        </div>
      )}

      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
        {latestVersion > 1 ? (
          <label className="inline-flex min-w-0 items-center">
            <span className="sr-only">选择版本</span>
            <select
              aria-label="选择版本"
              value={activeVersion}
              onChange={event => selectVersion(Number(event.target.value))}
              className="ceramic-card min-h-10 min-w-0 rounded-[10px] px-3 py-2 text-fs-13 text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)]"
            >
              {Array.from({ length: latestVersion }, (_, index) => index + 1).map(version => (
                <option key={version} value={version}>第 {version} 版</option>
              ))}
            </select>
          </label>
        ) : (
          <span className="readout text-fs-13">第 {latestVersion} 版</span>
        )}
        {shown && <span className="readout text-fs-13">第 {shown.round} 轮</span>}
        {words !== undefined && <span className="readout text-fs-13">{words} 字</span>}
        {shown && <span className="tag">{verdictLabel(shown)}</span>}
        <button
          type="button"
          className="btn btn-quiet min-h-10"
          disabled={exportBusy}
          onClick={onExport}
        >
          导出
        </button>
        {activeVersion !== latestVersion && (
          <span className="text-fs-12 text-[color:var(--ink2)]">导出的是最新一版</span>
        )}
      </div>

      {shown && hasVerdict && (
        <details
          key={`${activeVersion}-${failed ? "failed" : "passed"}`}
          className="min-w-0 border-t border-[color:var(--rule)] pt-3"
          open={failed}
        >
          <summary className="flex min-h-10 cursor-pointer items-center text-fs-13 text-[color:var(--ink2)]">
            验收明细
          </summary>
          <div className="mt-2 space-y-4 text-fs-13 leading-[1.8]">
            {rows.length > 0 && (
              <ul className="list-none space-y-1 p-0">
                {rows.map((row, index) => (
                  <li key={`${row.id}-${index}`} className="whitespace-pre-wrap break-words">
                    {row.id} {row.pass ? "通过" : "未通过"}：{row.evidence}
                  </li>
                ))}
              </ul>
            )}
            {issues.length > 0 && (
              <div>
                <p className="text-fs-12 text-[color:var(--ink2)]">引用问题</p>
                <ul className="mt-1 list-none space-y-1 p-0">
                  {issues.map((issue, index) => (
                    <li key={index} className="whitespace-pre-wrap break-words">
                      {issue.quote}：{issue.problem}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {rework.length > 0 && (
              <div>
                <p className="text-fs-12 text-[color:var(--ink2)]">返工要求</p>
                <ul className="mt-1 list-none space-y-1 p-0">
                  {rework.map((item, index) => (
                    <li key={index} className="whitespace-pre-wrap break-words">{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </details>
      )}

      {showLoading ? (
        <LoadingState>正在加载成果…</LoadingState>
      ) : error ? (
        <ErrorNotice message={error} retry={() => setReloadKey(key => key + 1)} />
      ) : currentOutput ? (
        <div className="min-w-0 max-w-[720px]">
          <DiscussDocument
            text={typeof currentOutput.content === "string" ? currentOutput.content : ""}
            sources={sources}
          />
        </div>
      ) : null}
    </div>
  );
}
