"use client";

import { Clock, Moon, Plus, Sun, Trash2 } from "lucide-react";
import { type Conversation } from "@/lib/agents";
import { useTheme } from "@/lib/useTheme";

function formatRelative(iso: string) {
  const date = new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso.replace(" ", "T") + "Z");
  const now = new Date();
  const dateStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const daysAgo = Math.round((todayStart.getTime() - dateStart.getTime()) / 86_400_000);

  if (daysAgo === 0) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  if (daysAgo === 1) return "昨天";
  if (daysAgo > 1 && daysAgo < 7) return `周${"日一二三四五六"[date.getDay()]}`;
  return `${String(date.getMonth() + 1).padStart(2, "0")}/${String(date.getDate()).padStart(2, "0")}`;
}

export default function ConversationPicker({
  conversations, selectedId, loading, locked, canCreate, error, onSelect, onCreate, onDelete, onRetry, onHistory, onFullHistory, className = "",
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
}) {
  const disabled = loading || locked;
  const { dark, toggleTheme } = useTheme();
  return (
    <aside
      className={`glass flex h-full w-[260px] shrink-0 flex-col border-r max-md:w-full ${className}`}
      style={{ borderColor: "var(--glass-border)" }}
      aria-label="对话列表"
    >
      <div className="flex h-16 shrink-0 items-center justify-between border-b pl-5 pr-3" style={{ borderColor: "var(--glass-border)" }}>
        <h2 className="text-sm font-medium">对话</h2>
        <div className="flex items-center gap-1">
          {onHistory && (
            <button type="button" className="btn btn-quiet w-[34px] px-0 max-md:h-10 max-md:w-10" title="当前对话记录" aria-label="当前对话记录" onClick={onHistory}>
              <Clock size={16} />
            </button>
          )}
          <button type="button" className="btn btn-quiet w-[34px] px-0 max-md:h-10 max-md:w-10" title="新对话" aria-label="新对话" onClick={onCreate} disabled={disabled || !canCreate}>
            <Plus size={16} />
          </button>
        </div>
      </div>

      <ul className="flex-1 overflow-y-auto p-2" role="listbox" aria-label="对话">
        {loading ? (
          <li className="px-3 py-2 text-xs text-muted-foreground" role="status">正在加载对话…</li>
        ) : conversations.map(conversation => (
          <li
            key={conversation.id}
            role="option"
            aria-selected={conversation.id === selectedId}
            className="group flex cursor-pointer items-baseline gap-2 rounded-[6px] px-3 py-2 text-[13px] text-muted-foreground hover:bg-secondary hover:text-foreground aria-selected:bg-secondary aria-selected:text-foreground"
          >
            <button type="button" className="min-w-0 flex-1 truncate text-left" onClick={() => onSelect(conversation.id)} disabled={disabled}>
              {conversation.title || "新对话"}
            </button>
            <span className="readout shrink-0 text-[11px]">{formatRelative(conversation.updated_at)}</span>
            <button
              type="button"
              aria-label="删除对话"
              title="删除对话"
              className="text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-[color:var(--rec)] focus-visible:opacity-100 disabled:opacity-40 max-md:grid max-md:h-10 max-md:w-10 max-md:place-items-center max-md:opacity-100"
              onClick={() => onDelete(conversation.id)}
              disabled={disabled}
            >
              <Trash2 size={13} />
            </button>
          </li>
        ))}
      </ul>

      {locked && <p className="px-5 pb-2 text-[11px] text-muted-foreground" role="status">分身回复或语音进行中，结束后可以切换对话。</p>}
      {!loading && !conversations.length && !error && <p className="px-5 pb-2 text-xs leading-relaxed text-muted-foreground">还没有对话。点「新对话」，开始和自己的分身交流。</p>}
      {error && <div className="flex flex-wrap items-center gap-1 px-5 pb-2 text-xs text-[color:var(--rec)]" role="alert">
        <span>{error}</span>
        <button type="button" onClick={onRetry} disabled={disabled} className="btn btn-quiet h-7 px-2.5 text-xs">重试加载</button>
      </div>}

      <div className="flex items-center justify-between border-t px-5 py-3 text-xs text-muted-foreground" style={{ borderColor: "var(--glass-border)" }}>
        <span>对话仅你可见</span>
        <button type="button" onClick={onFullHistory} className="hover:text-foreground">完整历史</button>
      </div>
      <div className="flex shrink-0 items-center justify-end border-t px-5 py-2 md:hidden" style={{ borderColor: "var(--glass-border)" }}>
        <button type="button" onClick={toggleTheme} className="btn btn-quiet h-10 px-2.5" title={dark ? "切换浅色" : "切换深色"} aria-label={dark ? "切换浅色" : "切换深色"}>
          {dark ? <Sun size={18} /> : <Moon size={18} />}
          <span>主题</span>
        </button>
      </div>
    </aside>
  );
}
