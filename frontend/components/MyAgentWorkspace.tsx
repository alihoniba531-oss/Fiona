"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, ExternalLink, Loader2, Save, ShieldCheck } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import AgentIdentityCard from "@/components/AgentIdentityCard";
import AgentMemoryPanel from "@/components/AgentMemoryPanel";
import { API_BASE as API } from "@/lib/config";
import { apiJson, errorMessage, type Agent } from "@/lib/agents";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";

const fieldClass = "w-full rounded-[6px] border border-[color:var(--border)] bg-card px-3 py-[9px] text-sm outline-none focus:border-[color:var(--amber-ink)] disabled:opacity-50";

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
    <div className={`flex ${embedded ? "h-full min-h-0" : "h-screen max-md:h-dvh"} flex-col overflow-hidden`}>
      <div className="flex min-h-0 flex-1">
        {!embedded && <Sidebar />}
        <main className={`min-w-0 flex-1 overflow-y-auto ${embedded ? "" : "max-md:pb-[calc(56px+env(safe-area-inset-bottom))]"}`}>
          <header className="glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7 max-md:px-4 max-md:pb-4 max-md:pt-4" style={{ borderColor: "var(--glass-border)" }}>
            <div className="flex max-w-[976px] items-end justify-between gap-4">
              <div>
                {!embedded && <Link href="/" className="mb-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft size={13} />回到对话</Link>}
                <h1 className="text-xl font-medium tracking-[-0.01em]">分身</h1>
                <p className="mt-1 text-[13px] text-muted-foreground">设置身份、介绍和交流方式。名片默认仅自己可见。</p>
              </div>
            </div>
          </header>
          <div className="mx-auto max-w-[1040px] px-8 py-6 max-md:px-4 max-md:py-4">
            {!owner ? <p className="text-sm text-muted-foreground" role="status">请登录后管理自己的分身。<Link href="/login" className="ml-2 text-[color:var(--amber-ink)] underline">前往登录</Link></p> : loading ? <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 className="animate-spin" size={16} />正在加载你的分身…</p> : !agent ? (
              <div className="glass-card space-y-3 p-6">
                <p role="alert" className="text-sm text-destructive">{error || "暂时无法加载分身。"}</p>
                <button type="button" onClick={() => void loadAgent()} className="btn btn-quiet">重新加载</button>
              </div>
            ) : (
              <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_340px] max-md:gap-6">
                <form onSubmit={save} className="flex flex-col gap-[22px] max-md:min-w-0">
                  <fieldset disabled={saving} className="flex flex-col gap-[22px]">
                    <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-4">
                      <label className="text-xs font-medium">头像符号
                        <input aria-label="头像符号" value={agent.avatar_emoji} maxLength={16} onChange={event => updateAgent({ avatar_emoji: event.target.value })} className={`${fieldClass} mt-2 text-center text-xl`} placeholder="✨" />
                      </label>
                      <label className="text-xs font-medium">分身名称
                        <input value={agent.display_name} maxLength={40} required onChange={event => updateAgent({ display_name: event.target.value })} className={`${fieldClass} mt-2`} placeholder="给自己的分身起个名字" />
                        <span className="mt-1.5 block text-[11px] font-normal text-muted-foreground">最多 <span className="readout"><b>40</b></span> 字</span>
                      </label>
                    </div>
                    <label className="block text-xs font-medium">名片简介
                      <textarea value={agent.bio} maxLength={300} rows={3} onChange={event => updateAgent({ bio: event.target.value })} className={`${fieldClass} mt-2 resize-y`} placeholder="这个分身关心什么，擅长怎样的交流？" />
                      <span className="mt-1.5 block text-[11px] font-normal text-muted-foreground"><span className="readout"><b>{agent.bio.length}</b> / <b>300</b></span>，开启公开名片后可被他人查看</span>
                    </label>
                    <label className="block text-xs font-medium"><span className="flex items-center justify-between gap-3">性格与交流方式 <em className="font-normal not-italic text-muted-foreground">仅自己可见</em></span>
                      <textarea value={agent.personality} maxLength={2000} rows={7} onChange={event => updateAgent({ personality: event.target.value })} className={`${fieldClass} mt-2 resize-y`} placeholder="例如：说话简洁、保持好奇心；先理解我的目标，再给出具体建议。" />
                      <span className="mt-1.5 block text-[11px] font-normal text-muted-foreground"><span className="readout"><b>{agent.personality.length}</b> / <b>2000</b></span>，用来指导你的分身如何回应</span>
                    </label>
                    <label className="glass-card flex cursor-pointer items-start justify-between gap-4 p-4">
                      <div><b className="block text-sm font-medium">公开分身名片</b><p className="mt-1 text-xs leading-[1.6] text-muted-foreground">其他已登录用户可以查看分身的名称、头像与简介，并邀请分身交流。关闭后仅自己可见，也会停止与其他用户待处理和进行中的分身交流。与平台官方 AI 的单人体验无需公开，不受此开关影响。</p></div>
                      <input type="checkbox" checked={agent.is_public} onChange={event => updateAgent({ is_public: event.target.checked })} className="mt-0.5 h-4 w-4 accent-[color:var(--primary)]" />
                    </label>
                  </fieldset>
                  {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
                  {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
                  <div className="flex flex-wrap items-center gap-3">
                    <button type="submit" disabled={saving || !dirty} className="btn btn-primary">
                      {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}{saving ? "正在保存…" : "保存分身"}
                    </button>
                    {dirty && <span className="text-xs text-muted-foreground">有未保存的修改</span>}
                  </div>
                </form>
                <aside className="flex flex-col gap-5 max-md:min-w-0 max-md:[&_.echo]:max-w-full max-md:[&_.echo]:overflow-hidden max-md:[&_.echo]:break-all">
                  <AgentIdentityCard agent={agent} preview />
                  {savedAgent?.is_public && <Link href={`/agents/${encodeURIComponent(savedAgent.id)}`} className="inline-flex items-center gap-1.5 text-xs text-[color:var(--amber-ink)] hover:underline"><ExternalLink size={13} />查看已保存的公开名片</Link>}
                  <div className="flex gap-2.5 text-xs leading-[1.6] text-muted-foreground"><ShieldCheck size={16} className="mt-0.5 shrink-0" style={{ color: "var(--amber-ink)" }} /><p>名片始终标明“AI 分身”。公开名片不会公开你的用户名、性格设定、私人画像或聊天记录。</p></div>
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
