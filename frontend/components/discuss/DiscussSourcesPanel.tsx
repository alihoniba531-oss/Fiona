"use client";

import { useMemo, useState, type JSX } from "react";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import type { DiscussSource } from "@/lib/discuss";
import { safeExternalUrl, splitDiscussCitations } from "@/lib/discussLogic";

function citedIds(content: string | null): Set<string> {
  if (!content) return new Set();
  const ids = new Set<string>();
  for (const block of splitDiscussCitations(content)) {
    if (block.kind === "cite") ids.add(block.id);
  }
  return ids;
}

export default function DiscussSourcesPanel(props: {
  sources: DiscussSource[];
  loading: boolean;
  error: string;
  onRetry: () => void;
  selectedOutputContent: string | null;
  hasOutput: boolean;
}): JSX.Element {
  const {
    sources,
    loading,
    error,
    onRetry,
    selectedOutputContent,
    hasOutput,
  } = props;
  const [onlyCited, setOnlyCited] = useState(false);
  const allSources = Array.isArray(sources) ? sources : [];
  const cited = useMemo(() => citedIds(selectedOutputContent), [selectedOutputContent]);
  const shownSources = onlyCited && hasOutput
    ? allSources.filter(source => cited.has(source.id))
    : allSources;

  if (error) return <ErrorNotice message={error} retry={onRetry} />;
  if (loading) return <LoadingState>正在加载来源…</LoadingState>;
  if (allSources.length === 0) {
    return <EmptyState>还没有登记来源。调研开始后会出现在这里。</EmptyState>;
  }

  return (
    <div className="min-w-0 space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {hasOutput && (
          <label className="flex min-h-10 items-center gap-2 text-fs-13 text-[color:var(--ink)]">
            <input
              type="checkbox"
              checked={onlyCited}
              onChange={event => setOnlyCited(event.target.checked)}
              className="h-4 w-4 shrink-0 accent-[color:var(--ink)]"
            />
            只看成果引用到的
          </label>
        )}
        <span className="readout text-fs-12">共 {shownSources.length} 条</span>
      </div>

      {shownSources.length === 0 ? (
        <EmptyState>成果里还没有引用来源。</EmptyState>
      ) : (
        <ul className="list-none p-0">
          {shownSources.map(source => {
            const href = safeExternalUrl(source.url);
            const label = `${source.title}（${source.site_name}）`;
            return (
              <li
                key={source.id}
                className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-[color:var(--carve)] py-2 text-fs-13 first:border-t-0"
              >
                <span className="readout shrink-0 text-fs-12">{source.id}</span>
                <span className="min-w-0 flex-1 break-words text-[color:var(--ink)]">
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer" title={label} className="underline underline-offset-2">{source.title}</a>
                  ) : (
                    source.title
                  )}
                </span>
                <span className="shrink-0 text-fs-12 text-[color:var(--ink2)]">{source.site_name}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
