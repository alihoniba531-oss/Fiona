"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ArrowLeft, Check, ChevronRight, Download, Loader2, Play, RefreshCw, Send, Square, X } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { ApiError, apiJson, errorMessage, type Agent, type AgentCard } from "@/lib/agents";
import { ExchangeIdentityError, exchangeBelongsTo, exchangeStatusLabel, isExchangeActive, isOfficialExchange, isDraftReviewExchange, isArtifactApproved, type AgentExchange, type ExchangeDetail, type ExchangeModelMetadata, type OfficialAgentCard } from "@/lib/agentExchanges";
import { useAgentExchanges } from "@/lib/useAgentExchanges";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";
import { apiFetch } from "@/lib/auth";
import { API_BASE as API } from "@/lib/config";

const fieldClass = "w-full rounded-[6px] border border-[color:var(--border)] bg-card px-3 py-[9px] text-sm outline-none focus:border-[color:var(--amber-ink)] disabled:opacity-50";

interface WorkspaceProps {
  embedded?: boolean;
  onOpenMyAgent?: () => void;
}

export default function AgentExchangeWorkspace(props: WorkspaceProps) {
  const owner = useAccountIdentity();
  return <ExchangeWorkspace key={owner} owner={owner} {...props} />;
}

function ExchangeWorkspace({ owner, embedded = false, onOpenMyAgent }: WorkspaceProps & { owner: string }) {
  const [tab, setTab] = useState<"official" | "experiences" | "gallery" | "received" | "sent">("official");
  const tabsRef = useRef<HTMLElement>(null);
  const [moreTabsRight, setMoreTabsRight] = useState(false);
  const [target, setTarget] = useState<AgentCard | OfficialAgentCard | null>(null);
  const [selected, setSelected] = useState<AgentExchange | null>(null);
  const clearPrivateSelection = useCallback(() => { setTarget(null); setSelected(null); }, []);
  const data = useAgentExchanges(owner, clearPrivateSelection);
  const pendingCount = data.exchanges.filter(item => !isOfficialExchange(item) && item.viewer_role === "recipient" && item.status === "pending").length;
  const records = data.exchanges.filter(item => tab === "experiences" ? isOfficialExchange(item) : !isOfficialExchange(item) && item.viewer_role === (tab === "received" ? "recipient" : "initiator"));
  const others = data.agents.filter(item => item.id !== data.agent?.id);
  const manageAgent = onOpenMyAgent
    ? <button type="button" className="text-[color:var(--amber-ink)] underline underline-offset-4" onClick={onOpenMyAgent}>管理我的分身</button>
    : <Link className="text-[color:var(--amber-ink)] underline underline-offset-4" href="/agents/me">管理我的分身</Link>;

  const back = () => { setTarget(null); setSelected(null); };

  useEffect(() => {
    const tabs = tabsRef.current;
    if (!tabs) return;
    const updateHint = () => {
      const lastTab = tabs.lastElementChild as HTMLElement | null;
      const contentEnd = lastTab ? lastTab.offsetLeft + lastTab.offsetWidth - tabs.offsetLeft : tabs.scrollWidth;
      setMoreTabsRight(tabs.scrollLeft + tabs.clientWidth < contentEnd - 1);
    };
    const observer = new ResizeObserver(updateHint);
    observer.observe(tabs);
    Array.from(tabs.children).forEach(child => observer.observe(child));
    tabs.addEventListener("scroll", updateHint, { passive: true });
    return () => {
      observer.disconnect();
      tabs.removeEventListener("scroll", updateHint);
    };
  }, [owner]);

  return (
    <div className={`flex ${embedded ? "h-full min-h-0" : "h-screen max-md:h-dvh"} flex-col overflow-hidden`} data-agent-exchange-workspace>
      <div className="flex min-h-0 flex-1">
        {!embedded && <Sidebar />}
        <main className={`min-w-0 flex-1 overflow-y-auto ${embedded ? "" : "max-md:pb-[calc(56px+env(safe-area-inset-bottom))]"}`} aria-label="分身交流工作区">
          <header className="glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7 max-md:px-4 max-md:pb-4 max-md:pt-4" style={{ borderColor: "var(--glass-border)" }}>
            <div className="flex max-w-[976px] items-end justify-between gap-4">
              <div className="max-md:min-w-0">
                {!embedded && <Link href="/" className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft size={13} />回到对话</Link>}
                <h1 className="text-xl font-medium tracking-[-0.01em]">广场</h1>
                <p className="mt-1 text-[13px] text-muted-foreground">让分身和官方搭档讨论一个话题，一个账号就能开始。也可以邀请其他用户的公开分身。 <span className="text-xs">{manageAgent}</span></p>
              </div>
              {owner && <button type="button" className="btn btn-quiet max-md:shrink-0" disabled={data.loading || data.officialLoading} onClick={() => { void data.refreshDirectory().then(data.refreshRecords); void data.refreshOfficial(); }} aria-label="刷新分身与交流记录"><RefreshCw size={14} className={data.loading || data.officialLoading ? "animate-spin" : ""} />刷新</button>}
            </div>
          </header>

          <div className="mx-auto max-w-[1040px] px-8 py-6 max-md:px-4 max-md:py-4">
            {!owner ? <EmptyState>请登录后查看分身和自己的交流记录。<Link href="/login" className="ml-2 text-[color:var(--amber-ink)] underline">前往登录</Link></EmptyState> : <>
              {data.error && <ErrorNotice message={data.error} retry={() => void data.refreshDirectory()} />}
              <div className="relative mb-6">
                <nav ref={tabsRef} role="tablist" className="mobile-scrollbar-none flex gap-1 border-b max-md:overflow-x-auto max-md:pr-7 max-md:whitespace-nowrap" style={{ borderColor: "var(--border)" }} aria-label="分身广场分类">
                  {([{ key: "official", label: "单人体验" }, { key: "experiences", label: "体验记录" }, { key: "gallery", label: "发现分身" }, { key: "received", label: "收到的邀请" }, { key: "sent", label: "发出的邀请" }] as const).map(item => (
                    <button key={item.key} type="button" role="tab" aria-selected={tab === item.key} onClick={() => { setTab(item.key); back(); }} className={`-mb-px flex h-9 items-center gap-1.5 border-b-2 px-3 text-[13px] max-md:shrink-0 max-md:whitespace-nowrap ${tab === item.key ? "border-[color:var(--amber-ink)] text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>{item.label}{item.key === "received" && pendingCount > 0 && <span className="readout text-[11px]" style={{ color: "var(--amber-ink)" }}>{pendingCount}</span>}</button>
                  ))}
                </nav>
                {moreTabsRight && <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-0 hidden w-7 items-center justify-center border-l bg-card text-muted-foreground max-md:flex" style={{ borderColor: "var(--border)" }}><ChevronRight size={16} /></span>}
              </div>
              {data.recordsError && <ErrorNotice message={`交流记录暂未更新：${data.recordsError}`} retry={() => void data.refreshRecords()} />}

              {!data.agent ? data.loading ? <LoadingState>正在确认你的分身身份…</LoadingState> : <EmptyState>暂时无法确认当前分身身份，请刷新或重新登录。</EmptyState> : selected ? <ExchangeConversation key={selected.id} owner={owner} agentId={data.agent.id} initial={selected} onBack={back} onChanged={data.onExchangeChanged} onIdentityInvalid={data.invalidateIdentity} manageAgent={manageAgent} /> : tab === "official" ? <>
                <p className="mb-4 text-xs leading-relaxed text-muted-foreground">以下均为平台官方 AI，无真人用户。分身先写完整初稿，官方搭档审稿，再按意见修订；审稿通过提前结束，可随时停止。</p>
                {data.officialError && <ErrorNotice message={`官方搭档暂不可用：${data.officialError}`} retry={() => void data.refreshOfficial()} />}
                {data.officialLoading ? <LoadingState>正在加载官方搭档…</LoadingState> : data.officialAgents.length === 0 ? <EmptyState>暂时没有可用的官方搭档，请稍后刷新。</EmptyState> : <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-3" role="radiogroup" aria-label="选择官方搭档">
                  {data.officialAgents.map(card => {
                    const modelLabel = card.model_label || card.model;
                    const checked = target?.kind === "official" && target.id === card.id;
                    return <button key={card.id} type="button" role="radio" aria-checked={checked} className={`glass-card flex flex-col gap-2.5 p-4 text-left max-md:min-w-0 ${checked ? "border-[color:var(--amber-ink)]" : ""}`} data-official-agent={card.id} onClick={() => { setTarget(card); setSelected(null); }}>
                      <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-medium">{card.display_name}</h3><span className="tag">官方 AI</span></div>
                      <p className="line-clamp-3 flex-1 text-xs leading-[1.6] text-muted-foreground">{card.bio}</p>
                      {modelLabel && <span className="readout max-md:break-all">{modelLabel}</span>}
                    </button>;
                  })}
                </div>}
                {target?.kind === "official" && <ExchangeStartForm key={target.id} owner={owner} agent={data.agent} target={target} onCancel={back} onIdentityInvalid={data.invalidateIdentity} onCreated={exchange => { data.onExchangeChanged(exchange); setTarget(null); setSelected(exchange); setTab("experiences"); }} />}
              </> : tab === "gallery" ? <>
                <p className="mb-3.5 text-xs text-muted-foreground">邀请需要双方都已公开名片。交流只使用公开名片和这次话题。{!data.agent.is_public && <> {manageAgent}</>}</p>
                {data.loading ? <LoadingState>正在寻找公开分身…</LoadingState> : others.length === 0 ? <EmptyState>最近公开的分身中暂无其他交流对象。分身主人开启公开名片后，就会出现在这里。</EmptyState> : <div className="grid gap-3 md:grid-cols-3">
                  {others.map(card => <section key={card.id} className="glass-card flex flex-col gap-2.5 p-4">
                    <div className="flex items-center gap-2.5"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-[6px] bg-secondary" aria-hidden="true">{card.avatar_emoji || "✨"}</span><h3 className="break-words text-sm font-medium">{card.display_name}</h3></div>
                    <p className="flex-1 whitespace-pre-wrap break-words text-xs leading-[1.6] text-muted-foreground">{card.bio || "这位分身还没有填写简介。"}</p>
                    <button type="button" className="btn self-start" disabled={!data.agent?.is_public} onClick={() => { setTarget(card); setSelected(null); }}><Send size={14} />邀请交流</button>
                  </section>)}
                </div>}
                {target?.kind !== "official" && target && <div className="mt-6"><ExchangeStartForm key={target.id} owner={owner} agent={data.agent} target={target} onCancel={back} onIdentityInvalid={data.invalidateIdentity} onCreated={exchange => { data.onExchangeChanged(exchange); setTarget(null); setSelected(exchange); setTab("sent"); }} /></div>}
              </> : <>
                <p className="mb-4 text-xs text-muted-foreground">展示最近 50 条交流记录中的{tab === "experiences" ? "单人体验，只有你自己可以查看。" : tab === "received" ? "已收邀请，需要你接受才会开始。" : "已发邀请，等待对方主人接受。"} 记录会自动更新。</p>
                {data.recordsLoading ? <LoadingState>正在加载交流记录…</LoadingState> : records.length === 0 ? <EmptyState>{tab === "experiences" ? "最近记录中暂无单人体验。去“单人体验”选择一位官方搭档，开始第一次讨论。" : tab === "received" ? "最近记录中暂无收到的邀请。公开分身名片后，其他用户就能发现你。" : "最近记录中暂无发出的邀请。去“发现分身”选择一位交流对象。"}</EmptyState> : <div>
                  <div className="grid grid-cols-[minmax(0,1fr)_150px_120px_60px_60px] gap-4 px-2 pb-2 text-[11px] max-md:hidden" style={{ color: "var(--dim)" }}><span>话题</span><span>搭档</span><span>状态</span><span className="text-right">次数</span><span className="text-right">时间</span></div>
                  {records.map(exchange => {
                    const other = exchange.viewer_role === "initiator" ? exchange.recipient : exchange.initiator;
                    return <button key={exchange.id} type="button" onClick={() => setSelected(exchange)} className="grid w-full grid-cols-[minmax(0,1fr)_150px_120px_60px_60px] items-center gap-4 border-b px-2 py-3 text-left text-[13px] hover:bg-card max-md:grid-cols-1 max-md:gap-1" data-exchange-id={exchange.id}>
                      <span className="truncate">{exchange.topic}</span>
                      <span className="truncate text-xs text-muted-foreground max-md:hidden">{other.display_name}</span>
                      <StatusBadge exchange={exchange} className="max-md:hidden" />
                      <span className="readout text-right max-md:hidden">{exchange.turn_count}</span>
                      <span className="readout text-right max-md:hidden">{formatDate(exchange.created_at)}</span>
                      <span className="hidden min-w-0 items-center gap-2 max-md:flex">
                        <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground"><span className="sr-only">搭档：</span>{other.display_name}</span>
                        <span className="sr-only">状态：</span>
                        <StatusBadge exchange={exchange} />
                        <span className="readout shrink-0"><span className="sr-only">次数：</span>{exchange.turn_count}</span>
                        <span className="readout shrink-0"><span className="sr-only">时间：</span>{formatDate(exchange.created_at)}</span>
                      </span>
                    </button>;
                  })}
                </div>}
              </>}
            </>}
          </div>
        </main>
      </div>
    </div>
  );
}

function ExchangeStartForm({ owner, agent, target, onCancel, onCreated, onIdentityInvalid }: { owner: string; agent: Agent; target: AgentCard | OfficialAgentCard; onCancel: () => void; onCreated: (exchange: AgentExchange) => void; onIdentityInvalid: () => void }) {
  const official = target.kind === "official";
  const [topic, setTopic] = useState("");
  const [maxTurnsInput, setMaxTurnsInput] = useState(official ? "99" : "6");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const topicLimit = official ? 10000 : 300;
  const validTopic = topic.trim().length > 0 && topic.length <= topicLimit;
  const turnLimit = official ? 99 : 6;
  const maxTurns = Number(maxTurnsInput);
  const validMaxTurns = maxTurnsInput.trim() !== "" && Number.isInteger(maxTurns) && maxTurns >= 2 && maxTurns <= turnLimit;
  const suggestedTopic = "suggested_topic" in target ? target.suggested_topic : undefined;
  const { beginRequest, isCurrentOwner } = useAccountRequest(owner);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !validTopic || !validMaxTurns || (!official && !agent.is_public) || agent.id === target.id || !isCurrentOwner()) return;
    const request = beginRequest();
    if (!request) return;
    setBusy(true); setError("");
    try {
      await assertAccountAgent(owner, agent.id, request.signal);
      if (!request.isCurrent()) return;
      const result = await apiJson<{ exchange: AgentExchange }>(`${API}/agent-exchanges${official ? "/official" : ""}`, {
        method: "POST", signal: request.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...(official ? { official_agent_id: target.id } : { target_agent_id: target.id }), topic: topic.trim(), max_turns: maxTurns }),
      });
      if (!request.isCurrent()) return;
      if (result.exchange.initiator.id !== agent.id || result.exchange.recipient.id !== target.id || result.exchange.viewer_role !== "initiator" || isOfficialExchange(result.exchange) !== official) throw new ExchangeIdentityError();
      onCreated(result.exchange);
    } catch (error) {
      if (request.isCurrent()) {
        if (error instanceof ExchangeIdentityError) onIdentityInvalid();
        else setError(errorMessage(error));
      }
    } finally {
      if (request.isCurrent()) setBusy(false);
    }
  };
  return <section className="flex flex-col gap-4">
    <button type="button" disabled={busy} onClick={onCancel} className="btn btn-quiet self-start"><ArrowLeft size={14} />返回{official ? "单人体验" : "分身列表"}</button>
    <div className="grid gap-3 sm:grid-cols-2">
      <Participant card={agent} label={official ? "你的 AI 分身" : "我的 AI 分身 · 发起方"} />
      <Participant card={target} label={official ? "平台官方 AI · 无真人用户" : "对方 AI 分身 · 受邀方"} />
    </div>
    <form onSubmit={submit} className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_220px]">
      <fieldset disabled={busy} className="min-w-0">
        <label className="flex flex-col gap-2 text-xs font-medium">{official ? "讨论话题" : "交流话题"}
          <textarea autoFocus required value={topic} maxLength={topicLimit} onChange={event => setTopic(event.target.value)} className={`${fieldClass} min-h-[150px] resize-y`} placeholder={official ? "写下你想讨论的内容，可以详细补充人物设定、故事背景、风格、时长要求，也可以粘贴已有大纲或完整需求。" : "例如：一起讨论怎样安排一个不赶时间的周末。"} />
          <small className="font-normal text-muted-foreground"><b className="readout">{topic.length.toLocaleString("zh-CN")}</b> / <b className="readout">{topicLimit.toLocaleString("zh-CN")}</b>，人物、背景、风格和时长都可以写进来</small>
        </label>
        {official && suggestedTopic && <button type="button" className="btn btn-quiet mt-2 h-7 px-2.5 text-xs" onClick={() => setTopic(suggestedTopic.slice(0, topicLimit))}>使用示例话题</button>}
      </fieldset>
      <div className="flex flex-col gap-3">
        <fieldset disabled={busy}>
          <label className="flex flex-col gap-2 text-xs font-medium">回复次数
            <input type="number" required min={2} max={turnLimit} step={1} inputMode="numeric" value={maxTurnsInput} onChange={event => setMaxTurnsInput(event.target.value)} className={`${fieldClass} readout`} aria-describedby={official ? "official-reply-count-help" : "reply-count-help"} />
            <small id={official ? "official-reply-count-help" : "reply-count-help"} className="font-normal text-muted-foreground">双方合计，2–{turnLimit}。{official ? "审稿通过会提前结束。" : "对方接受后开始。"}</small>
          </label>
        </fieldset>
        <button type="submit" className="btn btn-primary h-10 w-full" disabled={busy || !validTopic || !validMaxTurns || (!official && !agent.is_public)}>{busy ? <Loader2 className="animate-spin" size={14} /> : official ? <Play size={14} /> : <Send size={14} />}{busy ? official ? "正在开始…" : "正在发送…" : official ? "开始讨论" : "发送邀请"}</button>
        <p className="text-xs leading-relaxed text-muted-foreground">{official ? "流程是主创初稿、官方审稿、主创修订。只用分身的名字、简介和这次话题，不读取性格设定、私聊或私有记忆。记录仅你可见，内测期间不扣草莓。" : `对方接受后将调用模型，两个 AI 分身轮流回复，${validMaxTurns ? `合计最多 ${maxTurns} 次` : `请设置 2–${turnLimit} 次总回复`}，结束后生成总结。只使用双方公开名片和这次话题，不读取私聊或私有记忆。`}</p>
        {error && <ErrorNotice message={error} />}
      </div>
    </form>
  </section>;
}

function ExchangeConversation({ owner, agentId, initial, onBack, onChanged, onIdentityInvalid, manageAgent }: { owner: string; agentId: string; initial: AgentExchange; onBack: () => void; onChanged: (exchange: AgentExchange) => void; onIdentityInvalid: () => void; manageAgent: ReactNode }) {
  const [detail, setDetail] = useState<ExchangeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [unavailable, setUnavailable] = useState(false);
  const inaccessible = useRef(false);
  const mutating = useRef(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const status = useRef(initial.status);
  const { beginRequest, isCurrentOwner } = useAccountRequest(owner);
  const id = initial.id;
  const handleError = useCallback((error: unknown) => {
    if (error instanceof ExchangeIdentityError || (error instanceof ApiError && [401, 403, 404].includes(error.status))) {
      inaccessible.current = true;
      setDetail(null); setUnavailable(true);
      setError(error instanceof ExchangeIdentityError ? error.message : "这段交流已被删除或无法访问，旧内容已清除。");
      if (error instanceof ExchangeIdentityError) onIdentityInvalid();
    } else setError(errorMessage(error));
  }, [onIdentityInvalid]);
  const load = useCallback(async () => {
    if (mutating.current || inaccessible.current) return;
    const request = beginRequest();
    if (!request) return;
    try {
      const result = await apiJson<ExchangeDetail>(`${API}/agent-exchanges/${encodeURIComponent(id)}`, { signal: request.signal });
      if (!request.isCurrent()) return;
      if (result.exchange.id !== id || !exchangeBelongsTo(result.exchange, agentId)) throw new ExchangeIdentityError();
      setDetail(result); status.current = result.exchange.status; setError("");
    } catch (error) {
      if (request.isCurrent()) handleError(error);
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [agentId, beginRequest, handleError, id]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      if (cancelled) return;
      await load();
      if (!cancelled && !inaccessible.current && isExchangeActive(status.current)) timer = setTimeout(poll, 3000);
    };
    void Promise.resolve().then(poll);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [load]);

  const act = async (action: "accept" | "reject" | "stop") => {
    if (mutating.current || inaccessible.current || !isCurrentOwner()) return;
    if (isOfficialExchange(detail?.exchange ?? initial) && action !== "stop") return;
    const request = beginRequest();
    if (!request) return;
    mutating.current = true; setBusy(action); setError("");
    try {
      await assertAccountAgent(owner, agentId, request.signal);
      if (!request.isCurrent()) return;
      const result = await apiJson<ExchangeDetail>(`${API}/agent-exchanges/${encodeURIComponent(id)}/${action}`, { method: "POST", signal: request.signal });
      if (!request.isCurrent()) return;
      if (result.exchange.id !== id || !exchangeBelongsTo(result.exchange, agentId)) throw new ExchangeIdentityError();
      setDetail(result); status.current = result.exchange.status;
      onChanged(result.exchange);
    } catch (error) {
      if (request.isCurrent()) handleError(error);
    } finally {
      mutating.current = false;
      if (request.isCurrent()) { setBusy(""); setLoading(false); }
    }
  };

  if (unavailable) return <section className="flex flex-col gap-4"><ErrorNotice message={error} /><button type="button" onClick={onBack} className="btn btn-quiet self-start"><ArrowLeft size={14} />返回交流记录</button></section>;

  const exchange = detail?.exchange ?? initial;
  const official = isOfficialExchange(exchange);
  const workflow = isDraftReviewExchange(exchange);
  const mine = exchange.viewer_role === "initiator" ? exchange.initiator : exchange.recipient;
  const other = mine.id === exchange.initiator.id ? exchange.recipient : exchange.initiator;
  const mineModel = mine.model_label || mine.model;
  const otherModel = other.model_label || other.model;
  const pending = !official && exchange.status === "pending";
  return <section className="flex flex-col gap-6" data-exchange-detail={exchange.id}>
    <button type="button" onClick={onBack} className="btn btn-quiet self-start"><ArrowLeft size={14} />{official ? "体验记录" : exchange.viewer_role === "recipient" ? "收到的邀请" : "发出的邀请"}</button>
    <div className="flex items-start justify-between gap-4 max-md:flex-col max-md:gap-2">
      <div className="min-w-0">
        <h2 className="break-words text-lg font-medium">{exchange.topic.slice(0, 40)}{exchange.topic.length > 40 ? "…" : ""}</h2>
        <div className="mt-1.5 flex flex-wrap items-center gap-3.5 text-xs text-muted-foreground">
          <span className="max-md:break-all">{mine.display_name} {mineModel && <span className="readout">{mineModel}</span>}</span>
          <span className="max-md:break-all">{other.display_name} {otherModel && <span className="readout">{otherModel}</span>}</span>
          <span className="readout">第 <b>{exchange.turn_count}</b> 次 / {exchange.max_turns}</span>
        </div>
      </div>
      <StatusBadge exchange={exchange} />
    </div>
    {workflow && <div className="inline-flex self-start overflow-hidden rounded-[6px] border max-md:w-full" style={{ borderColor: "var(--glass-border)" }} aria-label="流程阶段">
      {([{ key: "draft", label: "主创初稿" }, { key: "review", label: "官方审稿" }, { key: "revision", label: "主创修订" }] as const).map((stage, index) => {
        const done = detail?.messages.some(message => message.stage === stage.key) ?? false;
        return <span key={stage.key} className={`flex items-center gap-1.5 px-3.5 py-1.5 text-xs max-md:min-w-0 max-md:flex-1 max-md:justify-center max-md:gap-1 max-md:px-1 max-md:whitespace-nowrap ${index ? "border-l" : ""} ${done ? "text-foreground" : "text-muted-foreground"}`} style={index ? { borderColor: "var(--glass-border)" } : undefined}>{done && <Check size={14} style={{ color: "var(--amber-ink)" }} />}{stage.label}</span>;
      })}
    </div>}
    <ExchangeTopic topic={exchange.topic} />
    {pending && <p className="text-xs leading-relaxed text-muted-foreground">{exchange.viewer_role === "recipient" ? `接受后将调用模型，两个分身合计最多回复 ${exchange.max_turns} 次，并生成总结。双方名片均需保持公开。` : "邀请已发出，等待对方主人接受后才会调用模型开始交流。"} {manageAgent}</p>}
    {loading ? <LoadingState>正在读取交流详情…</LoadingState> : pending && <div className="flex flex-wrap gap-2">
      {exchange.viewer_role === "recipient" && <><button type="button" className="btn btn-primary" disabled={!!busy || !detail} onClick={() => void act("accept")}>{busy === "accept" ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}接受并开始交流</button><button type="button" className="btn btn-quiet" disabled={!!busy || !detail} onClick={() => void act("reject")}><X size={14} />拒绝邀请</button></>}
      <button type="button" className="btn" disabled={!!busy || !detail} onClick={() => void act("stop")}>{busy === "stop" ? <Loader2 size={14} className="animate-spin" /> : <Square size={12} />}取消这次邀请</button>
    </div>}
    {error && <ErrorNotice message={`交流暂未更新：${error}`} retry={busy ? undefined : () => void load()} />}
    {exchange.status === "running" && <div className="glass sticky top-0 z-[2] -mx-8 flex items-center justify-between px-8 py-2 text-xs text-muted-foreground max-md:-mx-4 max-md:flex-col max-md:items-start max-md:gap-2 max-md:px-4">
      <span>交流正在自动更新，停止后保留已有内容</span>
      <div className="flex flex-wrap gap-2"><button type="button" className="btn btn-quiet" onClick={() => messagesRef.current?.scrollIntoView({ block: "end" })}>查看最新回复</button><button type="button" className="btn" disabled={!!busy || !detail} onClick={() => void act("stop")}>{busy === "stop" ? <Loader2 size={14} className="animate-spin" /> : <Square size={12} />}停止交流</button></div>
    </div>}
    {workflow && <ExchangeArtifact exchange={exchange}><ExchangeDocuments owner={owner} agentId={agentId} exchange={exchange} ready={!!detail && !loading} onAccessError={handleError} embedded /></ExchangeArtifact>}
    <p className="text-xs leading-relaxed text-muted-foreground">{official ? "这是你的分身与平台官方 AI 的单人体验，没有另一位真人用户。只使用你的分身名字、简介和本次讨论内容，不读取私聊、性格设定或私有记忆；无需公开，体验记录仅自己可见。" : "以下内容由 AI 分身根据公开名片和本次话题生成，不读取私聊或私有记忆，不代表真人即时发言。交流记录仅供双方账号查看。"}</p>
    <div ref={messagesRef} className="flex flex-col gap-[18px]" role="region" aria-label="双分身交流消息" aria-busy={exchange.status === "running"}>
      {detail?.messages.map(message => <article key={message.id} className="grid min-w-0 grid-cols-[28px_minmax(0,1fr)] gap-3" data-exchange-message={message.sequence}>
        <span className="readout pt-[3px]">{message.sequence}</span>
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span className="max-md:break-all">{message.display_name}</span>{message.stage && <span className="tag">{stageLabel(message.stage)}</span>}<span>{message.agent_id === mine.id ? "你的 AI 分身" : official ? "平台官方 AI" : "对方 AI 分身"}</span></div>
          <div className="whitespace-pre-wrap break-words text-[13px] leading-[1.75]">{message.content}</div>
        </div>
      </article>)}
      {detail && detail.messages.length === 0 && <EmptyState>{pending ? "对方接受邀请后，两位 AI 分身的回复会出现在这里。" : exchange.status === "running" ? "分身正在准备第一条回复…" : "这段交流没有生成回复。"}</EmptyState>}
    </div>
    {exchange.summary && <section className="glass-card p-4"><h3 className="mb-3 text-sm font-medium">{workflow ? "创作说明" : "交流总结 · AI 生成"}</h3><p className="whitespace-pre-wrap break-words text-[13px] leading-[1.75]">{exchange.summary}</p></section>}
    {!workflow && <ExchangeDocuments owner={owner} agentId={agentId} exchange={exchange} ready={!!detail && !loading} onAccessError={handleError} />}
    {exchange.status === "failed" && <ErrorNotice message={exchange.error || (official ? "这次体验未能完成。已有回复已保留，可以返回单人体验重新开始讨论。" : "这段交流未能完成。已有回复已保留，可以返回广场重新发起邀请。")} />}
    {exchange.status === "stopped" && <EmptyState>交流已停止，已有回复保留。{exchange.error && <span className="mt-2 block">{exchange.error}</span>}</EmptyState>}
    {exchange.status === "rejected" && <EmptyState>对方已拒绝这次邀请，分身不会开始交流。</EmptyState>}
    {exchange.status !== "running" && !pending && <div className="flex items-center gap-3"><button type="button" className="btn" disabled><Square size={12} />停止交流</button><span className="text-xs text-muted-foreground">已结束，记录仅你可见</span></div>}
  </section>;
}

function stageLabel(stage: string) {
  return ({ draft: "主创初稿", review: "官方审稿", revision: "主创修订" } as Record<string, string>)[stage] || "交流";
}

function completionLabel(reason?: string) {
  return ({ review_approved: "AI 审稿已通过，提前结束。", turn_limit: "已达到回复次数上限，当前稿件保留为草稿。", no_progress: "修订没有发生实质变化，已停止反复讨论，当前稿件保留为草稿。", output_limit: "模型输出达到长度上限，当前稿件可能不完整，请检查后继续编辑。", incomplete_output: "模型输出未正常结束，当前稿件保留为草稿。" } as Record<string, string>)[reason || ""];
}

function ExchangeArtifact({ exchange, children }: { exchange: AgentExchange; children: ReactNode }) {
  const approved = isArtifactApproved(exchange);
  const reason = completionLabel(exchange.completion_reason);
  const length = exchange.artifact?.trim().length ?? 0;
  return <section className="glass-card" aria-label="当前作品" data-exchange-artifact>
    <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3" style={{ borderColor: "var(--glass-border)" }}>
      <b className="font-medium">当前作品</b>
      <span className="flex items-center gap-2"><span className="readout"><b>{length.toLocaleString("zh-CN")}</b> 字</span><span className={`tag ${approved ? "tag-amber" : ""}`}>{approved ? "审稿通过，待你验收" : exchange.artifact_status === "needs_revision" ? "待修订" : "草稿"}</span></span>
    </div>
    {reason && <p className="px-4 pt-3 text-xs text-muted-foreground">{reason}</p>}
    {exchange.artifact?.trim() ? <div role="region" aria-label="完整作品稿件" tabIndex={0} className="max-h-[36rem] overflow-y-auto whitespace-pre-wrap break-words p-4 text-[13px] leading-[1.8] select-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ring)]">{exchange.artifact}</div> : <p className="p-4 text-[13px] text-muted-foreground">{exchange.has_artifact && exchange.artifact === undefined ? "正在读取已保存的完整稿件…" : exchange.status === "running" ? "主创正在准备完整初稿，保存后会显示在这里。" : "这次创作尚未保存作品稿件，已有讨论仍可下载。"}</p>}
    {children}
  </section>;
}

function ExchangeDocuments({ owner, agentId, exchange, ready, onAccessError, embedded = false }: { owner: string; agentId: string; exchange: AgentExchange; ready: boolean; onAccessError: (error: unknown) => void; embedded?: boolean }) {
  const [downloading, setDownloading] = useState<"readme" | "discussion" | "artifact" | "">("");
  const [error, setError] = useState("");
  const activeDownload = useRef(false);
  const { beginRequest, isCurrentOwner } = useAccountRequest(owner);
  const workflow = isDraftReviewExchange(exchange);
  const draft = workflow ? !isArtifactApproved(exchange) : exchange.status !== "completed" || !exchange.summary;

  const download = async (kind: "readme" | "discussion" | "artifact") => {
    if (!ready || activeDownload.current || !isCurrentOwner()) return;
    const request = beginRequest();
    if (!request) return;
    activeDownload.current = true;
    setDownloading(kind); setError("");
    try {
      await assertAccountAgent(owner, agentId, request.signal);
      if (!request.isCurrent()) return;
      const response = await apiFetch(`${API}/agent-exchanges/${encodeURIComponent(exchange.id)}/export?document=${kind}`, { signal: request.signal, cache: "no-store" });
      if (!request.isCurrent()) return;
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new ApiError(typeof body?.detail === "string" ? body.detail : `文档下载失败（${response.status}），请重试。`, response.status);
      }
      if (!response.headers.get("Content-Type")?.toLowerCase().startsWith("text/markdown")) throw new Error("服务器未返回 Markdown 文档，请重试。");
      const blob = await response.blob();
      if (!request.isCurrent()) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      try {
        link.href = url;
        link.download = kind === "readme" ? "README.md" : `${kind}-${exchange.id}.md`;
        link.hidden = true;
        document.body.appendChild(link);
        link.click();
      } finally {
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (error) {
      if (request.isCurrent()) {
        if (error instanceof ExchangeIdentityError || (error instanceof ApiError && [401, 403, 404].includes(error.status))) onAccessError(error);
        else setError(errorMessage(error));
      }
    } finally {
      activeDownload.current = false;
      if (request.isCurrent()) setDownloading("");
    }
  };

  return <section className={`${embedded ? "border-t p-3" : "glass-card p-4"} flex flex-col gap-3`} style={embedded ? { borderColor: "var(--glass-border)" } : undefined} aria-label="文档交付物">
    <p className="text-xs leading-relaxed text-muted-foreground">{workflow ? "作品文档保存完整稿件；README.md 包含原始需求、稿件和审核状态；完整讨论保留每轮写稿与审稿。" : "README.md 包含原始需求和已有总结；完整讨论保留双方逐轮回复。"}{draft ? workflow ? " 当前导出为尚未通过审稿的草稿快照。" : " 当前导出为已保存内容的快照。" : " 下载只导出实际保存的文字内容。"}</p>
    <div className="flex flex-wrap gap-1.5">
      {workflow && <button type="button" className="btn max-w-full" disabled={!ready || !!downloading || !exchange.artifact?.trim()} onClick={() => void download("artifact")}>{downloading === "artifact" ? <Loader2 size={15} className="shrink-0 animate-spin" /> : <Download size={15} className="shrink-0" />}作品 Markdown</button>}
      <button type="button" className="btn max-w-full" disabled={!ready || !!downloading} onClick={() => void download("readme")}>{downloading === "readme" ? <Loader2 size={15} className="shrink-0 animate-spin" /> : <Download size={15} className="shrink-0" />}README.md</button>
      <button type="button" className="btn max-w-full" disabled={!ready || !!downloading} onClick={() => void download("discussion")}>{downloading === "discussion" ? <Loader2 size={15} className="shrink-0 animate-spin" /> : <Download size={15} className="shrink-0" />}完整讨论</button>
    </div>
    {downloading && <p role="status" className="text-xs text-muted-foreground">正在下载{downloading === "readme" ? " README.md" : downloading === "artifact" ? "作品文档" : "完整讨论文档"}…</p>}
    {error && <ErrorNotice message={error} />}
  </section>;
}

function ExchangeTopic({ topic }: { topic: string }) {
  if (topic.length <= 300) return <p className="whitespace-pre-wrap break-words text-base leading-relaxed">{topic}</p>;
  return <div className="space-y-2">
    <p className="line-clamp-4 whitespace-pre-wrap break-words text-base leading-relaxed">{topic.slice(0, 300)}…</p>
    <details className="glass-card group p-3">
      <summary className="cursor-pointer text-sm text-[color:var(--amber-ink)] focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ring)]"><span className="group-open:hidden">展开完整话题</span><span className="hidden group-open:inline">收起完整话题</span>（{topic.length.toLocaleString("zh-CN")} 字）</summary>
      <div role="region" aria-label="完整讨论话题" tabIndex={0} className="mt-3 max-h-80 overflow-y-auto whitespace-pre-wrap break-words pr-2 text-sm leading-7 select-text focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ring)]">{topic}</div>
    </details>
  </div>;
}

function Participant({ card, label }: { card: AgentCard & ExchangeModelMetadata; label: string }) {
  const modelLabel = card.model_label || card.model;
  return <div className="flex min-w-0 items-center gap-2.5"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-[6px] bg-secondary text-base" aria-hidden="true">{card.avatar_emoji || "✨"}</span><div className="min-w-0"><p className="break-words text-sm font-medium">{card.display_name}</p><p className="text-xs text-muted-foreground">{label}</p>{modelLabel && <span className="readout break-words max-md:break-all">{modelLabel}</span>}</div></div>;
}

function StatusBadge({ exchange, className = "" }: { exchange: AgentExchange; className?: string }) {
  return <span className={`tag shrink-0 ${exchange.status === "failed" ? "tag-rec" : isExchangeActive(exchange.status) ? "tag-amber" : ""} ${className}`}>{exchange.status === "running" && <Loader2 size={11} className="animate-spin" />}{isDraftReviewExchange(exchange) && exchange.status === "completed" ? isArtifactApproved(exchange) ? "AI 审稿通过 · 待你验收" : "已结束 · 草稿" : exchangeStatusLabel[exchange.status]}</span>;
}

function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <div role="alert" className="glass-card flex flex-col gap-2 p-3 text-[13px]"><p className="whitespace-pre-wrap break-words text-destructive">{message}</p>{retry && <button type="button" onClick={retry} className="btn btn-quiet h-7 self-start">重新加载</button>}</div>;
}

function EmptyState({ children }: { children: ReactNode }) {
  return <p className="py-6 text-[13px] leading-relaxed text-muted-foreground">{children}</p>;
}

function LoadingState({ children }: { children: ReactNode }) {
  return <p role="status" className="flex items-center gap-2 py-3 text-[13px] text-muted-foreground"><Loader2 size={15} className="animate-spin" />{children}</p>;
}

function formatDate(value: string) {
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value) ? `${value.replace(" ", "T")}Z` : value;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "";
  const today = new Date();
  if (date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() && date.getDate() === today.getDate()) return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${String(date.getMonth() + 1).padStart(2, "0")}/${String(date.getDate()).padStart(2, "0")}`;
}

async function assertAccountAgent(owner: string, agentId: string, signal: AbortSignal) {
  const result = await apiJson<{ agent: Agent }>(`${API}/agents/me`, { signal });
  if (result.agent.owner_username !== owner || result.agent.id !== agentId) throw new ExchangeIdentityError();
}
