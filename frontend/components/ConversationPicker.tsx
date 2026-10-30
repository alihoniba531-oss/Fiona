"use client";

import { Trash2 } from "lucide-react";
import { type Conversation } from "@/lib/agents";
import { beijingDayNumber, beijingParts, formatBeijingTime } from "@/lib/beijingTime";
import Glaze from "@/components/Glaze";
import { useTheme } from "@/lib/useTheme";

function formatRelative(iso: string) {
  const date = new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso.replace(" ", "T") + "Z");
  const now = new Date();
  const daysAgo = beijingDayNumber(now) - beijingDayNumber(date);
  const parts = beijingParts(date);

  if (daysAgo === 0) {
    return formatBeijingTime(date);
  }
  if (daysAgo === 1) return "昨天";
  if (daysAgo > 1 && daysAgo < 7) return `周${"日一二三四五六"[parts.weekday]}`;
  return `${String(parts.month).padStart(2, "0")}/${String(parts.day).padStart(2, "0")}`;
}

export default function ConversationPicker({
  conversations, selectedId, loading, locked, canCreate, error, onSelect, onCreate, onDelete, onRetry, onHistory, onFullHistory, className = "", glazed = true,
}: {
  conversations: Conversation[];
  selectedId?: string;
  loading: boolean;
  locked: boolean;
  canCreate: boolean;
  error: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onRetry: () => void;
  onHistory?: () => void;
  onFullHistory?: () => void;
  className?: string;
  glazed?: boolean;
}) {
  const disabled = loading || locked;
  const { dark, toggleTheme } = useTheme();
  const content = (
    <aside
      className={`flex h-full w-[288px] shrink-0 flex-col max-md:w-full ${className}`}
      aria-label="对话列表"
    >
      <div className="flex h-[76px] shrink-0 items-center justify-between border-b pl-5 pr-3" style={{ borderColor: "var(--rule)" }}>
        <h2 className="text-fs-18 font-medium tracking-[.18em]">对话</h2>
        <div className="flex items-center gap-1">
          {onHistory && (
            <button type="button" className="btn btn-quiet px-2 max-md:h-10" title="当前对话记录" aria-label="历史：当前对话记录" onClick={onHistory}>
              历史
            </button>
          )}
          <button type="button" className="btn btn-quiet px-2 max-md:h-10" title="新对话" aria-label="新建：新对话" onClick={onCreate} disabled={disabled || !canCreate}>
            新建
          </button>
        </div>
      </div>

      <ul className="flex-1 overflow-y-auto p-2" role="listbox" aria-label="对话">
        {loading ? (
          <li className="px-3 py-2 text-fs-12 text-[color:var(--ink2)]" role="status">正在加载对话…</li>
        ) : conversations.map(conversation => (
          <li
            key={conversation.id}
            role="option"
            aria-selected={conversation.id === selectedId}
            className="group flex cursor-pointer items-baseline gap-2 rounded-lg px-[18px] py-3.5 text-fs-15 text-[color:var(--ink2)] hover:bg-[color:var(--slip)] hover:text-[color:var(--ink)] aria-selected:bg-[color:var(--chip)] aria-selected:shadow-[inset_0_0_0_1px_var(--rim)] aria-selected:text-[color:var(--ink)]"
          >
            <button type="button" className="min-w-0 flex-1 truncate text-left" onClick={() => onSelect(conversation.id)} disabled={disabled}>
              {conversation.title || "新对话"}
            </button>
            <span className="readout shrink-0 text-fs-12">{formatRelative(conversation.updated_at)}</span>
            <button
              type="button"
              aria-label="删除对话"
              title="删除对话"
              className="text-[color:var(--ink2)] opacity-0 group-hover:opacity-100 hover:text-[color:var(--seal)] focus-visible:opacity-100 disabled:opacity-40 max-md:grid max-md:h-10 max-md:w-10 max-md:place-items-center max-md:opacity-100"
              onClick={() => onDelete(conversation.id)}
              disabled={disabled}
            >
              <Trash2 size={13} />
            </button>
          </li>
        ))}
      </ul>

      {locked && <p className="px-5 pb-2 text-fs-11 text-[color:var(--ink2)]" role="status">分身回复或语音进行中，结束后可以切换对话。</p>}
      {!loading && !conversations.length && !error && <p className="px-5 pb-2 text-fs-12 leading-relaxed text-[color:var(--ink2)]">还没有对话。点「新建」，开始和自己的分身交流。</p>}
      {error && <div className="flex flex-wrap items-center gap-1 px-5 pb-2 text-fs-12 text-[color:var(--seal)]" role="alert">
        <span>{error}</span>
        <button type="button" onClick={onRetry} disabled={disabled} className="btn btn-quiet h-7 px-2.5 text-fs-12">重试加载</button>
      </div>}

      <div className="flex items-center justify-between border-t px-5 py-3 text-fs-12 text-[color:var(--ink2)]" style={{ borderColor: "var(--rule)" }}>
        <span>对话仅你可见</span>
        <button type="button" onClick={onFullHistory} className="min-h-10 hover:text-[color:var(--ink)]">完整历史</button>
      </div>
      <div className="flex shrink-0 items-center justify-end border-t px-5 py-2 md:hidden" style={{ borderColor: "var(--rule)" }}>
        <button type="button" onClick={toggleTheme} className="btn btn-quiet h-10 px-2.5" title={dark ? "切换浅色" : "切换深色"} aria-label={dark ? "切换浅色" : "切换深色"}>
          <span className="theme-day">夜</span><span className="theme-night">昼</span>
          <span>主题</span>
        </button>
      </div>
    </aside>
  );
  return glazed ? <Glaze as="div" variant="panel" className="h-full">{content}</Glaze> : content;
}
