"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { ArrowLeft, ExternalLink, Loader2 } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import InkLandscape from "@/components/InkLandscape";
import AgentIdentityCard from "@/components/AgentIdentityCard";
import AgentMemoryPanel from "@/components/AgentMemoryPanel";
import { API_BASE as API } from "@/lib/config";
import { apiJson, errorMessage, type Agent } from "@/lib/agents";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";

const fieldClass = "ceramic-card w-full rounded-[10px] border-0 px-4 py-3 text-[16px] leading-[1.8] tracking-normal text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";

interface MyAgentWorkspaceProps {
  embedded?: boolean;
  onSaved?: (agent: Agent) => void;
}

export default function MyAgentWorkspace({ embedded = false, onSaved }: MyAgentWorkspaceProps) {
  const owner = useAccountIdentity();
  // Remount private state on account changes; no old form or memory survives.
  return <MyAgentEditor key={owner} owner={owner} embedded={embedded} onSaved={onSaved} />;
}

function MyAgentEditor({ owner, embedded, onSaved }: { owner: string } & MyAgentWorkspaceProps) {
  const publicCardDescriptionId = useId();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [savedAgent, setSavedAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const { beginRequest, isCurrentOwner } = useAccountRequest(owner);

  const loadAgent = useCallback(async () => {
    const request = beginRequest();
    if (!request) return;
    setLoading(true);
    setError("");
    try {
      const result = await apiJson<{ agent: Agent }>(`${API}/agents/me`, { signal: request.signal });
      if (!request.isCurrent()) return;
      if (result.agent.owner_username !== owner) throw new Error("账号状态已变化，请重新登录后再管理分身。");
      setAgent(result.agent);
      setSavedAgent(result.agent);
    } catch (error) {
      if (request.isCurrent()) setError(errorMessage(error));
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [beginRequest, owner]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => { if (!cancelled) void loadAgent(); });
    return () => { cancelled = true; };
  }, [loadAgent]);

  const updateAgent = (patch: Partial<Agent>) => {
    setAgent(previous => previous ? { ...previous, ...patch } : previous);
    setNotice("");
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!agent || saving || !isCurrentOwner() || agent.owner_username !== owner) return;
    if (!agent.display_name.trim()) { setError("给分身起一个名字再保存。"); return; }
    const request = beginRequest();
    if (!request) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await apiJson<{ agent: Agent }>(`${API}/agents/me`, {
        method: "PUT", signal: request.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: agent.display_name.trim(), bio: agent.bio.trim(),
          personality: agent.personality.trim(), avatar_emoji: agent.avatar_emoji.trim() || "✨",
          is_public: agent.is_public,
        }),
      });
      if (!request.isCurrent()) return;
      if (result.agent.owner_username !== owner) throw new Error("账号状态已变化，请重新登录后再管理分身。");
      setAgent(result.agent);
      setSavedAgent(result.agent);
      setNotice("已保存。新的对话回复会使用这些分身设定。");
      onSaved?.(result.agent);
    } catch (error) {
      if (request.isCurrent()) setError(errorMessage(error));
    } finally {
      if (request.isCurrent()) setSaving(false);
    }
  };

  const dirty = agent !== null && JSON.stringify(agent) !== JSON.stringify(savedAgent);

  return (
    <div className={`relative flex ${embedded ? "h-full min-h-0" : "h-screen max-md:h-dvh"} flex-col overflow-hidden`}>
      {!embedded && <InkLandscape variant="page" />}
      <div className="relative z-[1] flex min-h-0 flex-1">
        {!embedded && <Sidebar />}
        <main className={`min-w-0 flex-1 overflow-y-auto ${embedded ? "" : "max-md:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]"}`}>
          <header className="mx-auto max-w-[1236px] px-[72px] pb-[22px] pt-7 max-md:px-4 max-md:pb-5 max-md:pt-4">
            <div className="flex items-end justify-between gap-4 border-b pb-[22px]" style={{ borderColor: "var(--rule)" }}>
              <div>
                {!embedded && <Link href="/" className="mb-2 inline-flex min-h-10 items-center gap-1.5 text-xs text-[color:var(--ink2)] hover:text-[color:var(--ink)]"><ArrowLeft size={13} />回到对话</Link>}
                <h1 className="text-[30px] font-medium tracking-[.24em]">分身</h1>
                <p className="mt-2 text-[14px] leading-[1.85] tracking-[.04em] text-[color:var(--ink2)]">设置身份、介绍和交流方式。名片默认仅自己可见。</p>
              </div>
            </div>
          </header>
          <div className="mx-auto max-w-[1236px] px-[72px] pb-10 pt-2 max-md:px-4 max-md:pb-6 max-md:pt-0">
            {!owner ? <p className="text-sm text-muted-foreground" role="status">请登录后管理自己的分身。<Link href="/login" className="ml-2 text-[color:var(--ink)] underline">前往登录</Link></p> : loading ? <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 className="animate-spin" size={16} />正在加载你的分身…</p> : !agent ? (
              <div className="ceramic-card space-y-3 p-6">
                <p role="alert" className="text-sm text-destructive">{error || "暂时无法加载分身。"}</p>
                <button type="button" onClick={() => void loadAgent()} className="btn btn-quiet">重新加载</button>
              </div>
            ) : (
              <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_380px] max-md:gap-7">
                <form onSubmit={save} className="flex min-w-0 flex-col gap-[22px]">
                  <fieldset disabled={saving} className="flex min-w-0 flex-col gap-[22px]">
                    <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-5 max-md:grid-cols-[72px_minmax(0,1fr)] max-md:gap-4">
                      <label className="text-[13px] tracking-[.1em] text-[color:var(--ink2)]">头像符号
                        <input aria-label="头像符号" value={agent.avatar_emoji === "✨" ? "" : agent.avatar_emoji} maxLength={16} onChange={event => updateAgent({ avatar_emoji: event.target.value })} className={`${fieldClass} mt-2.5 h-[72px] w-[72px]! rounded-[14px]! px-1! text-center text-[32px]!`} placeholder="✦" />
                      </label>
                      <label className="min-w-0 text-[13px] tracking-[.1em] text-[color:var(--ink2)]">分身名称
                        <input value={agent.display_name} maxLength={40} required onChange={event => updateAgent({ display_name: event.target.value })} className="mt-2 block h-12 w-full min-w-0 border-0 border-b border-[color:var(--rule2)] bg-transparent px-0 text-[22px] tracking-normal text-[color:var(--ink)] outline-none focus:border-[color:var(--ink)] disabled:opacity-50" placeholder="给自己的分身起个名字" />
                        <span className="mt-1.5 block text-xs font-normal tracking-normal text-muted-foreground">最多 <span className="readout"><b>40</b></span> 字</span>
                      </label>
                    </div>
                    <label className="block text-[13px] tracking-[.1em] text-[color:var(--ink2)]">名片简介
                      <textarea value={agent.bio} maxLength={300} rows={3} onChange={event => updateAgent({ bio: event.target.value })} className={`${fieldClass} mt-2 resize-y`} placeholder="这个分身关心什么，擅长怎样的交流？" />
                      <span className="mt-1.5 block text-xs font-normal tracking-normal text-muted-foreground"><span className="readout"><b>{agent.bio.length}</b> / <b>300</b></span>，开启公开名片后可被他人查看</span>
                    </label>
                    <label className="block text-[13px] tracking-[.1em] text-[color:var(--ink2)]"><span className="flex items-center justify-between gap-3">性格与交流方式 <em className="shrink-0 text-xs font-normal not-italic tracking-normal text-muted-foreground">仅自己可见</em></span>
                      <textarea value={agent.personality} maxLength={2000} rows={4} onChange={event => updateAgent({ personality: event.target.value })} className={`${fieldClass} mt-2 resize-y`} placeholder="例如：说话简洁、保持好奇心；先理解我的目标，再给出具体建议。" />
                      <span className="mt-1.5 block text-xs font-normal tracking-normal text-muted-foreground"><span className="readout"><b>{agent.personality.length}</b> / <b>2000</b></span>，用来指导你的分身如何回应</span>
                    </label>
                    <label className="flex cursor-pointer items-start justify-between gap-6 border-t pt-[22px]" style={{ borderColor: "var(--rule)" }}>
                      <div className="min-w-0"><b className="block text-[16px] font-medium tracking-[.06em]">公开分身名片</b><p id={publicCardDescriptionId} className="mt-1.5 text-[13px] leading-[1.85] text-muted-foreground">其他已登录用户可以查看分身的名称、头像与简介，并邀请分身交流。关闭后仅自己可见，也会停止与其他用户待处理和进行中的分身交流。与平台官方 AI 的单人体验无需公开，不受此开关影响。</p></div>
                      <span className="relative flex h-10 w-11 shrink-0 items-center">
                        <input type="checkbox" aria-label="公开分身名片" aria-describedby={publicCardDescriptionId} checked={agent.is_public} onChange={event => updateAgent({ is_public: event.target.checked })} className="peer absolute inset-0 z-[1] h-full w-full cursor-pointer opacity-0" />
                        <span aria-hidden="true" className="flex h-6 w-11 items-center rounded-full border border-[color:var(--rule2)] bg-[color:var(--tile)] p-0.5 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-4 peer-focus-visible:outline-[color:var(--ink)]" style={{ boxShadow: "inset 0 -1px 0 var(--lip)" }}><span className={`h-[18px] w-[18px] rounded-full bg-[color:var(--ink2)] transition-transform ${agent.is_public ? "translate-x-5" : ""}`} /></span>
                      </span>
                    </label>
                  </fieldset>
                  {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
                  {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
                  <div className="flex flex-wrap items-center gap-3">
                    <button type="submit" disabled={saving || !dirty} className="btn btn-primary min-h-11 px-[30px] tracking-[.24em]">
                      {saving && <Loader2 size={15} className="animate-spin" />}{saving ? "正在保存…" : "保存分身"}
                    </button>
                    {dirty && <span className="text-xs text-muted-foreground">有未保存的修改</span>}
                  </div>
                </form>
                <aside className="flex min-w-0 flex-col gap-3.5">
                  <AgentIdentityCard agent={agent} preview />
                  {savedAgent?.is_public && <Link href={`/agents/${encodeURIComponent(savedAgent.id)}`} className="inline-flex min-h-10 items-center gap-1.5 text-xs text-[color:var(--ink)] hover:underline"><ExternalLink size={13} />查看已保存的公开名片</Link>}
                  <p className="text-[13px] leading-[1.85] text-[color:var(--ink2)]">名片始终标明“AI 分身”。公开名片不会公开你的用户名、性格设定、私人画像或聊天记录。</p>
                  <AgentMemoryPanel />
                </aside>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
