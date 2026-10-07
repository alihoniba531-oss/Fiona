"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArrowLeft, Loader2 } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import InkLandscape from "@/components/InkLandscape";
import AgentIdentityCard from "@/components/AgentIdentityCard";
import { API_BASE as API } from "@/lib/config";
import { apiJson, errorMessage, type AgentCard } from "@/lib/agents";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";

function AgentPageContent() {
  const { id } = useParams<{ id: string }>();
  const owner = useAccountIdentity();
  return <AccountAgentCard key={`${owner}:${id}`} id={id} owner={owner} />;
}

function AccountAgentCard({ id, owner }: { id: string; owner: string }) {
  const [result, setResult] = useState<{ id: string; agent?: AgentCard; error?: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const { beginRequest } = useAccountRequest(owner);
  useEffect(() => {
    const request = beginRequest();
    if (!request) return;
    apiJson<{ agent: AgentCard }>(`${API}/agents/${encodeURIComponent(id)}`, { signal: request.signal })
      .then(data => { if (request.isCurrent()) setResult({ id, agent: data.agent }); })
      .catch(error => { if (request.isCurrent()) setResult({ id, error: errorMessage(error) }); });
  }, [beginRequest, id, retry]);
  const current = result?.id === id ? result : null;
  return (
    <div className="relative flex h-screen flex-col overflow-hidden max-md:h-dvh">
      <InkLandscape variant="page" />
      <div className="relative z-[1] flex min-h-0 flex-1"><Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto max-md:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]">
          <header className="mx-auto max-w-[1236px] px-[72px] pb-[22px] pt-7 max-md:px-4 max-md:pb-5 max-md:pt-4">
            <div className="flex items-end justify-between gap-4 border-b pb-[22px]" style={{ borderColor: "var(--rule)" }}>
              <div>
                <Link href="/agents/me" className="mb-2 inline-flex min-h-10 items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft size={13} />我的分身</Link>
                <h1 className="text-[30px] font-medium tracking-[.24em]">分身名片</h1>
              </div>
            </div>
          </header>
          <div className="mx-auto max-w-[560px] space-y-5 px-8 pb-10 pt-3 max-md:px-4 max-md:pb-6 max-md:pt-0">
            {!owner ? <p role="status" className="text-sm text-muted-foreground">请登录后查看分身名片。<Link href="/login" className="ml-2 text-[color:var(--ink)] underline">前往登录</Link></p> : !current ? <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 size={16} className="animate-spin" />正在加载名片…</p>
              : current.agent ? <AgentIdentityCard agent={current.agent} />
              : <div className="ceramic-card space-y-3 p-6"><p role="alert" className="text-sm text-[color:var(--seal)]">{current.error}</p><button type="button" onClick={() => { setResult(null); setRetry(value => value + 1); }} className="btn btn-quiet">重新加载</button></div>}
          </div>
        </main>
      </div>
    </div>
  );
}

export default function AgentPage() {
  return <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">正在加载名片…</p>}><AgentPageContent /></Suspense>;
}
