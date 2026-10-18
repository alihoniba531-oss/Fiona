"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import Glaze from "@/components/Glaze";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { ApiError } from "@/lib/agents";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";
import { useRovingTabs } from "@/lib/useRovingTabs";
import { getStudioAccess, studioErrorMessage, studioHref } from "@/lib/studio";
import type { KbCardType } from "@/lib/studio-kb";
import StudioShell from "../StudioShell";
import KbCardBrowser from "./KbCardBrowser";
import KbExemplars from "./KbExemplars";
import KbStatsPanel from "./KbStatsPanel";
import KbTrialPanel from "./KbTrialPanel";

interface KbTab { id: string; label: string; cardType?: KbCardType }
const tabs: KbTab[] = [
  { id: "grammar", label: "语法", cardType: "grammar" },
  { id: "scene", label: "场景模板", cardType: "scene" },
  { id: "model", label: "模型能力", cardType: "model" },
  { id: "negative", label: "反例", cardType: "negative" },
  { id: "exemplars", label: "案例库" },
  { id: "stats", label: "节奏统计" },
  { id: "trial", label: "试拆对比" },
];

export default function KbWorkbench({ embedded = false }: { embedded?: boolean }) {
  const owner = useAccountIdentity();
  return <AccountKbWorkbench key={owner} owner={owner} embedded={embedded} />;
}

export function AccountKbWorkbench({ owner, embedded }: { owner: string; embedded: boolean }) {
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState("");
  const tabProps = useRovingTabs(tabs.length, index, setIndex);
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const load = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    setLoading(true);
    try {
      await getStudioAccess(request.signal);
      if (!request.isCurrent()) return;
      setUnavailable(false); setError("");
    } catch (cause) {
      if (!request.isCurrent()) return;
      if (cause instanceof ApiError && cause.status === 404) { setUnavailable(true); setError(""); }
      else setError(studioErrorMessage(cause));
    } finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const tab = tabs[index];
  return <StudioShell embedded={embedded}>
    <header className="mb-5">
      <Link href={studioHref("/studio", embedded)} className="mb-2 inline-flex min-h-10 items-center gap-1 text-sm text-[color:var(--ink2)]"><ArrowLeft size={14} />短片工作室</Link>
      <Glaze variant="panel" lens={false} backdrop={!embedded} className="min-w-0 rounded-2xl p-5">
        <h1 className="break-words text-[26px] tracking-[.24em]">导演知识库</h1>
        <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-[color:var(--ink2)]">卡片是仓库里的 YAML；案例和节奏统计只存在本机 SQLite。运行时不会访问外部资源。</p>
      </Glaze>
    </header>
    {!owner ? <EmptyState>请登录后打开导演知识库。</EmptyState>
      : loading ? <LoadingState>正在打开导演知识库…</LoadingState>
      : unavailable ? <EmptyState>暂未开放</EmptyState>
      : error ? <ErrorNotice message={error} retry={() => { void load(); }} />
      : <>
        <nav role="tablist" aria-label="导演知识库页签" className="mb-5 flex min-w-0 flex-wrap border-b border-[color:var(--carve)]">{tabs.map((item, tabIndex) => <button key={item.id} id={`kb-tab-${item.id}`} type="button" role="tab" aria-selected={index === tabIndex} aria-controls={`kb-panel-${item.id}`} {...tabProps(tabIndex)} onClick={() => setIndex(tabIndex)} className={`min-h-10 border-b px-3 py-3 text-[13px] @[640px]:text-sm ${index === tabIndex ? "border-[color:var(--ink)] text-[color:var(--ink)]" : "border-transparent text-[color:var(--ink2)]"}`}>{item.label}</button>)}</nav>
        <section role="tabpanel" id={`kb-panel-${tab.id}`} aria-labelledby={`kb-tab-${tab.id}`} className="min-w-0">
          {tab.cardType ? <KbCardBrowser key={tab.id} type={tab.cardType} owner={owner} />
            : tab.id === "exemplars" ? <KbExemplars owner={owner} />
            : tab.id === "stats" ? <KbStatsPanel owner={owner} />
            : <KbTrialPanel owner={owner} />}
        </section>
      </>}
  </StudioShell>;
}
