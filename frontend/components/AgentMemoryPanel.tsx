"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { API_BASE as API } from "@/lib/config";
import { apiJson, errorMessage } from "@/lib/agents";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";

const labels: Record<string, string> = {
  interests: "兴趣", values: "价值观", needs: "当前需求", skills: "可分享的经验",
  struggles: "当前困境", city: "城市", occupation: "职业", stage: "当前阶段",
};

function memoryText(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(memoryText).filter(Boolean).join("、");
  if (value && typeof value === "object") return Object.entries(value).map(([key, item]) => `${labels[key] || key}：${memoryText(item)}`).join("；");
  return "";
}

export default function AgentMemoryPanel() {
  const owner = useAccountIdentity();
  return <AccountMemoryPanel key={owner} owner={owner} />;
}

function AccountMemoryPanel({ owner }: { owner: string }) {
  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [revision, setRevision] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const { beginRequest, isCurrentOwner } = useAccountRequest(owner);

  const load = useCallback(async () => {
    const request = beginRequest();
    if (!request) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiJson<{ profile: Record<string, unknown> | null; revision?: number }>(`${API}/agents/me/memory`, { signal: request.signal });
      if (request.isCurrent()) {
        setProfile(data.profile || {});
        setRevision(typeof data.revision === "number" ? data.revision : null);
      }
    } catch (error) {
      if (request.isCurrent()) setError(errorMessage(error));
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, [beginRequest]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => { if (!cancelled) void load(); });
    return () => { cancelled = true; };
  }, [load]);

  const clear = async () => {
    if (clearing || loading || !isCurrentOwner() || !confirm("清空分身记忆和已有个人画像？聊天记录与分身设定会保留，后续交流可形成新的记忆。")) return;
    // The account can change while the confirmation dialog is open.
    const request = beginRequest();
    if (!request) return;
    setClearing(true);
    setError("");
    setNotice("");
    try {
      await apiJson(`${API}/agents/me/memory`, { method: "DELETE", signal: request.signal });
      if (!request.isCurrent()) return;
      setProfile({});
      setNotice("分身记忆和已有个人画像已清空，聊天记录与分身设定已保留。");
    } catch (error) {
      if (request.isCurrent()) setError(errorMessage(error));
    } finally {
      if (request.isCurrent()) setClearing(false);
    }
  };

  const entries = Object.entries(profile).map(([key, value]) => [labels[key] || key, memoryText(value)]).filter(([, value]) => value);

  return (
    <section className="flex flex-col gap-3 border-t pt-[18px]" style={{ borderColor: "var(--glass-border)" }} aria-labelledby="private-memory-title">
      <div className="flex items-center justify-between gap-3">
        <h3 id="private-memory-title" className="text-sm font-medium">私有记忆</h3>
        <span className="readout">{revision === null ? "仅自己可见" : <>修订 <b>{revision}</b></>}</span>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">分身从交流中整理的兴趣、需求与个人画像。这些内容不出现在公开名片里。</p>
      {!owner ? <p className="text-xs text-muted-foreground" role="status">请登录后查看私有记忆。</p> : loading ? <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status"><Loader2 size={13} className="animate-spin" />正在加载记忆…</p>
        : entries.length ? <ul>{entries.map(([label, value]) => <li key={label} className="border-b py-1.5 text-[13px] leading-relaxed text-muted-foreground" style={{ borderColor: "var(--glass-border)" }}>{label}：<span className="whitespace-pre-wrap break-words">{value}</span></li>)}</ul>
        : !error && <p className="text-xs text-muted-foreground">还没有私人画像。和分身聊聊自己后，这里会逐步形成记忆。</p>}
      {error && <p className="text-xs text-[color:var(--rec)]" role="alert">{error}<button type="button" onClick={() => void load()} disabled={loading || clearing} className="btn btn-quiet ml-2 h-7 px-2.5 text-xs">重试</button></p>}
      {notice && <p className="text-xs text-muted-foreground" role="status">{notice}</p>}
      <footer className="flex flex-wrap items-center justify-between gap-1.5">
        <button type="button" onClick={() => void load()} disabled={!owner || loading || clearing} className="btn btn-quiet">刷新</button>
        <button type="button" onClick={() => void clear()} disabled={!owner || loading || clearing} className="btn btn-danger">
          {clearing ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}{clearing ? "正在清空…" : "清空记忆与个人画像"}
        </button>
      </footer>
      <p className="text-[11px] leading-relaxed text-muted-foreground">清空分身记忆和已有个人画像；聊天记录保留，后续交流可形成新的记忆。</p>
    </section>
  );
}
