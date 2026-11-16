"use client";

import { useEffect, useRef, useState, type JSX, type UIEvent } from "react";
import { Loader2 } from "lucide-react";
import type { DiscussMember, DiscussMessage, DiscussSource, DiscussStatus } from "@/lib/discuss";
import { discussIsActive, discussKindLabel, groupDiscussRounds } from "@/lib/discussLogic";
import { formatNovelDate } from "@/lib/novels";
import { EmptyState, LoadingState } from "@/components/novel/NovelStates";
import DiscussDocument from "./DiscussDocument";

const BOTTOM_GAP = 80;

function TimelineMessage({
  message,
  sources,
  onOpenDraft,
}: {
  message: DiscussMessage;
  sources: Record<string, DiscussSource>;
  onOpenDraft: (version: number) => void;
}): JSX.Element {
  const isUser = message.sender === "user";
  const kindLabel = discussKindLabel(message.kind);
  const version = message.payload?.version;
  const draftVersion = typeof version === "number" && Number.isInteger(version) && version > 0
    ? version
    : null;
  return (
    <article className={isUser ? "min-w-0 rounded-[8px] bg-[color:var(--slip)] px-3 py-2.5" : "min-w-0"}>
      <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-fs-13">
        <span className="text-[color:var(--ink)]">{message.sender_name}</span>
        {isUser && (
          <span className="text-fs-11 text-[color:var(--ink2)]">
            {message.consumed ? "已读到" : "还没读到"}
          </span>
        )}
        {kindLabel && <span className="tag">{kindLabel}</span>}
        <span className="readout ml-auto text-fs-11">{formatNovelDate(message.created_at)}</span>
      </div>
      <DiscussDocument text={message.content} sources={sources} />
      {draftVersion !== null && (
        <button type="button" className="btn mt-2" onClick={() => onOpenDraft(draftVersion)}>
          看这一版成果
        </button>
      )}
    </article>
  );
}

export default function DiscussTimeline({
  messages,
  members,
  status,
  sources,
  active,
  onOpenDraft,
}: {
  messages: DiscussMessage[];
  members: DiscussMember[];
  status: DiscussStatus;
  sources: Record<string, DiscussSource>;
  active: boolean;
  onOpenDraft: (version: number) => void;
}): JSX.Element {
  const viewportRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const nearBottomRef = useRef(true);
  const lastMessageIdRef = useRef<number | null>(null);
  const firstViewRef = useRef(true);
  const pendingWhileHiddenRef = useRef(false);
  const [hasNew, setHasNew] = useState(false);

  const workingNames = members.filter(member => member.working).map(member => member.name);

  // 第一次真正看到群聊时（包括从别的标签切过来）停在最新一条。
  // 用 rAF 等到布局完成再滚，并在 cleanup 里取消；开发模式下 effect 跑两遍时
  // 第一遍会被取消、第二遍仍会执行，不依赖「只执行一次」。
  useEffect(() => {
    if (!active || !firstViewRef.current) return;
    const frame = requestAnimationFrame(() => {
      const element = viewportRef.current;
      if (!element || element.getClientRects().length === 0) return;
      element.scrollTop = element.scrollHeight;
      nearBottomRef.current = true;
      setHasNew(false);
      firstViewRef.current = false;
    });
    return () => cancelAnimationFrame(frame);
  }, [active]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
    const lastMessageId = lastMessage?.id ?? null;
    const previousMessageId = lastMessageIdRef.current;
    lastMessageIdRef.current = lastMessageId;
    const firstLoad = previousMessageId === null;
    const arrived = previousMessageId !== null
      && lastMessageId !== null
      && lastMessageId !== previousMessageId;
    if (!active) {
      // 不在群聊标签时记录新消息；回来时按离开前是否贴底决定跟随还是提示。
      if (arrived && !firstViewRef.current) pendingWhileHiddenRef.current = true;
      return;
    }
    if (!firstLoad && !arrived) return;
    const shouldFollow = firstLoad || nearBottomRef.current || lastMessage?.sender === "user";
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const element = viewportRef.current;
      if (!element) return;
      if (shouldFollow) {
        element.scrollTop = element.scrollHeight;
        nearBottomRef.current = true;
        setHasNew(false);
      } else {
        setHasNew(true);
      }
    });
  }, [active, messages]);

  useEffect(() => {
    if (!active || firstViewRef.current || !pendingWhileHiddenRef.current) return;
    const shouldFollow = nearBottomRef.current;
    const frame = requestAnimationFrame(() => {
      const element = viewportRef.current;
      if (!element) return;
      if (shouldFollow) {
        element.scrollTop = element.scrollHeight;
        nearBottomRef.current = true;
        setHasNew(false);
      } else {
        setHasNew(true);
      }
      pendingWhileHiddenRef.current = false;
    });
    return () => cancelAnimationFrame(frame);
  }, [active]);

  useEffect(() => () => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
  }, []);

  const scrollToLatest = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    viewport.scrollTop = viewport.scrollHeight;
    nearBottomRef.current = true;
    setHasNew(false);
  };

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    const viewport = event.currentTarget;
    const nearBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= BOTTOM_GAP;
    nearBottomRef.current = nearBottom;
    if (nearBottom && hasNew) setHasNew(false);
  };

  return (
    <section className="flex flex-[1_0_auto] flex-col" aria-label="群聊">
      <div className="shrink-0 border-b border-[color:var(--rule)] pb-2.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-fs-13 text-[color:var(--ink)]">
          {members.map((member, index) => (
            <span key={`${member.role}-${index}`} className="inline-flex items-center gap-1">
              <span>{member.name}</span>
              {member.working && (
                <Loader2 size={12} className="animate-spin text-[color:var(--ink2)]" aria-label="正在工作" />
              )}
            </span>
          ))}
        </div>
        {workingNames.length > 0 ? (
          <p className="readout mt-1.5 text-fs-11">{workingNames.join("、")} 正在工作…</p>
        ) : discussIsActive(status) ? (
          <p className="readout mt-1.5 text-fs-11">正在安排下一步…</p>
        ) : null}
      </div>
      <div className="relative flex min-h-0 flex-[1_0_auto] flex-col">
        <div
          ref={viewportRef}
          onScroll={handleScroll}
          className="min-h-[120px] flex-[1_1_0px] overflow-y-auto px-1 py-4"
        >
          {messages.length === 0 ? (
            discussIsActive(status) ? (
              <LoadingState>主持人正在看你的诉求…</LoadingState>
            ) : (
              <EmptyState>还没有消息。</EmptyState>
            )
          ) : (
            <div className="space-y-6">
              {groupDiscussRounds(messages).map((group, groupIndex) => (
                <section key={`${group.round}-${group.messages[0]?.id ?? groupIndex}`}>
                  <div className="mb-3 flex items-center gap-3">
                    <span aria-hidden="true" className="h-px flex-1 bg-[color:var(--rule)]" />
                    <span className="readout text-fs-11">{group.label}</span>
                    <span aria-hidden="true" className="h-px flex-1 bg-[color:var(--rule)]" />
                  </div>
                  <div className="space-y-4">
                    {group.messages.map(message => (
                      <TimelineMessage
                        key={message.id}
                        message={message}
                        sources={sources}
                        onOpenDraft={onOpenDraft}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
        {messages.length > 0 && hasNew && (
          <button
            type="button"
            onClick={scrollToLatest}
            className="btn absolute bottom-3 right-3 bg-[color:var(--paper)]"
          >
            有新消息
          </button>
        )}
      </div>
    </section>
  );
}
