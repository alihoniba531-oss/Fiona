"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import Earth3D from "@/components/Earth3D";
import { Send, User, Sparkles, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch, getToken, getUsername as readStoredUsername } from "@/lib/auth";

const API = "/api";
// WebSocket 需要完整 scheme + host，"/api" 直接 new WebSocket 会抛 SyntaxError
const WS_BASE = typeof window !== "undefined"
  ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/api`
  : "";

interface Room { peer: string; room_id: string }
interface PeerMsg { sender: string; content: string; created_at: string }
interface PendingMatch {
  id: number;
  peer_username: string;
  interest_topic: string;
  reason: string;
  type: string;
  tags: string[];
  created_at: string;
  peer_greeting?: string | null;
}

// 单张云朵卡片
function CloudCard({
  match,
  index,
  pos,
  onAccept,
  onSkip,
  onExpire,
}: {
  match: PendingMatch;
  index: number;
  pos: { x: number; y: number };
  onAccept: (m: PendingMatch, greeting: string) => void;
  onSkip: (id: number) => void;
  onExpire: (id: number) => void;
}) {
  const [phase, setPhase] = useState<"in" | "stable" | "out">("in");
  const [showGreeting, setShowGreeting] = useState(false);
  const [greetingText, setGreetingText] = useState("");

  useEffect(() => {
    const t1 = setTimeout(() => setPhase("stable"), 800);
    const t2 = setTimeout(() => setPhase("out"), 25000);
    const t3 = setTimeout(() => onExpire(match.id), 27000);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [match.id, onExpire]);

  return (
    <div
      className={cn(
        "cloud-card w-80 bg-card/70 backdrop-blur-md border border-border/60 rounded-2xl px-5 py-4 shadow-lg",
        phase === "in" && "cloud-in",
        phase === "stable" && "cloud-stable",
        phase === "out" && "cloud-out",
      )}
      style={{
        position: "absolute",
        left: `${pos.x}%`,
        top: `${pos.y}%`,
        animationDelay: `${index * 0.15}s`,
      }}
    >
      <div className="flex items-start gap-3">
        {/* 匿名头像 */}
        <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
          <Sparkles size={16} className="text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-semibold text-sm text-foreground/60">神秘好友</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary">
              {match.type}
            </span>
          </div>
          {match.interest_topic && (
            <p className="text-[10px] text-muted-foreground mb-1.5">
              因为你聊到了 <span className="text-foreground/70 font-medium">「{match.interest_topic}」</span>
            </p>
          )}
          <p className="text-sm text-foreground/85 leading-relaxed">{match.reason}</p>
          {/* 对方的招呼 */}
          {match.peer_greeting && (
            <div className="flex items-start gap-1.5 mt-2 bg-secondary/60 rounded-xl px-3 py-2">
              <MessageCircle size={11} className="text-primary mt-0.5 shrink-0" />
              <p className="text-[11px] text-foreground/80 leading-relaxed">「{match.peer_greeting}」</p>
            </div>
          )}
          {match.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {match.tags.map((t, i) => (
                <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-secondary text-muted-foreground">
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 打招呼展开区 */}
      {showGreeting && (
        <div className="mt-3">
          <textarea
            value={greetingText}
            onChange={e => setGreetingText(e.target.value.slice(0, 50))}
            placeholder="说点什么吧（可选，50字以内）"
            rows={2}
            className="w-full resize-none bg-secondary/60 rounded-xl px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground outline-none leading-relaxed"
          />
          <div className="flex gap-2 mt-2 justify-end">
            <button
              onClick={() => setShowGreeting(false)}
              className="text-[10px] px-3 py-1.5 rounded-full text-muted-foreground hover:bg-secondary transition-colors"
            >跳过</button>
            <button
              onClick={() => onAccept(match, greetingText)}
              className="text-[10px] px-3 py-1.5 rounded-full bg-primary text-white hover:opacity-90 transition-opacity"
            >发送打招呼</button>
          </div>
        </div>
      )}

      {!showGreeting && (
        <div className="flex gap-2 mt-3 justify-end">
          <button
            onClick={() => onSkip(match.id)}
            className="text-[11px] px-3 py-1.5 rounded-full text-muted-foreground hover:bg-secondary transition-colors"
          >算了</button>
          <button
            onClick={() => setShowGreeting(true)}
            className="text-[11px] px-3 py-1.5 rounded-full bg-primary text-white hover:opacity-90 transition-opacity"
          >认识下</button>
        </div>
      )}
    </div>
  );
}

export default function MatchPage() {
  const [username, setUsername] = useState("默认用户");
  const [hydrated, setHydrated] = useState(false);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [selected, setSelected] = useState<Room | null>(null);
  const [messages, setMessages] = useState<PeerMsg[]>([]);
  const [input, setInput] = useState("");
  const [pendingMatches, setPendingMatches] = useState<PendingMatch[]>([]);
  const [cardPositions, setCardPositions] = useState<Record<number, { x: number; y: number }>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 启动后从 localStorage 读取当前身份
  useEffect(() => {
    const u = localStorage.getItem("fiona_user");
    if (u) setUsername(u);
    setHydrated(true);
  }, []);

  // 加载 rooms
  const loadRooms = useCallback(() => {
    apiFetch(`${API}/peer/rooms`)
      .then(r => r.json())
      .then(data => setRooms((data.rooms || []).slice(0, 5)))
      .catch(() => {});
  }, []);

  // 拉取最近5个已接受匹配
  useEffect(() => {
    if (!hydrated) return;
    loadRooms();
  }, [loadRooms, hydrated]);

  // 轮询 pending matches（对话内匹配卡）
  useEffect(() => {
    if (!hydrated || !username) return;
    let mounted = true;
    let lastIds = new Set<number>();

    async function poll() {
      try {
        const r = await apiFetch(`${API}/match/pending`);
        const data = await r.json();
        if (!mounted) return;
        const incoming: PendingMatch[] = data.pending || [];
        // 只把新出现的卡加进 state；已经在 state 的不重复
        setPendingMatches(prev => {
          const existingIds = new Set(prev.map(p => p.id));
          const fresh = incoming.filter(p => !existingIds.has(p.id) && !lastIds.has(p.id));
          // 最多同时显示 3 张，超出的等旧卡消失后下次轮询再补
          const canAdd = Math.max(0, 3 - prev.length);
          const toAdd = fresh.slice(0, canAdd);
          toAdd.forEach(p => {
            lastIds.add(p.id);
            setCardPositions(pos => ({
              ...pos,
              [p.id]: {
                x: 5 + Math.random() * 50,
                y: 5 + Math.random() * 60,
              },
            }));
          });
          return [...prev, ...toAdd];
        });
      } catch {}
    }

    poll();
    const timer = setInterval(poll, 8000); // 每 8s 查一次新匹配
    return () => { mounted = false; clearInterval(timer); };
  }, [username, hydrated]);

  const removeCard = useCallback((id: number) => {
    setPendingMatches(prev => prev.filter(p => p.id !== id));
    setCardPositions(prev => { const n = { ...prev }; delete n[id]; return n; });
  }, []);

  // 卡片自然过期（淡出动画完成后）
  const handleCardExpire = useCallback((id: number) => {
    apiFetch(`${API}/match/pending/${id}/seen`, { method: "POST" }).catch(() => {});
    removeCard(id);
  }, [removeCard]);

  // 用户点"认识下" → accept + 可选招呼
  const handleAcceptMatch = useCallback(async (match: PendingMatch, greeting: string = "") => {
    apiFetch(`${API}/match/pending/${match.id}/seen`, { method: "POST" }).catch(() => {});
    try {
      await apiFetch(`${API}/match/response`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          peer: match.peer_username,
          response: "accept",
          greeting: greeting.trim(),
        }),
      });
      loadRooms();
    } catch {}
    removeCard(match.id);
  }, [loadRooms, removeCard]);

  // 用户点"算了"
  const handleSkipMatch = useCallback((id: number) => {
    apiFetch(`${API}/match/pending/${id}/seen`, { method: "POST" }).catch(() => {});
    removeCard(id);
  }, [removeCard]);

  // 切换联系人：加载历史 + 连 WebSocket
  const openChat = useCallback((room: Room) => {
    if (wsRef.current) wsRef.current.close();
    setSelected(room);
    setMessages([]);

    apiFetch(`${API}/peer/history/${room.room_id}`)
      .then(r => r.json())
      .then(data => setMessages(data.messages || []))
      .catch(() => {});

    const token = getToken();
    const wsAuth = token
      ? `token=${encodeURIComponent(token)}`
      : `dev_user=${encodeURIComponent(readStoredUsername() || username)}`;
    const ws = new WebSocket(`${WS_BASE}/ws/peer/${room.room_id}?${wsAuth}`);
    ws.onmessage = (e) => {
      const msg: PeerMsg = JSON.parse(e.data);
      setMessages(prev => [...prev, msg]);
    };
    wsRef.current = ws;
  }, [username]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ content: text }));
    setInput("");
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const searchParams = useSearchParams();
  const embedded = searchParams?.get("embed") === "1";

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      {!embedded && <TopBar />}
      <div className="flex flex-1 min-h-0">
        {!embedded && <Sidebar />}
        <div className="flex flex-1 min-w-0 relative overflow-hidden">

          {/* 3D 地球背景：横跨整个区域，让左栏也能透出宇宙 */}
          <Earth3D />

          {/* 左侧：最近 5 个联系人 (玻璃质感，星空直接穿透) */}
          <div
            className="w-64 flex flex-col shrink-0 relative z-10"
            style={{
              background:
                "linear-gradient(180deg, rgba(8,18,38,0.08) 0%, rgba(4,10,22,0.14) 100%)",
              borderRight: "1px solid rgba(0,212,255,0.22)",
              backdropFilter: "blur(4px) saturate(140%)",
              WebkitBackdropFilter: "blur(4px) saturate(140%)",
              boxShadow: "inset -1px 0 0 rgba(0,212,255,0.10), inset 0 1px 0 rgba(0,212,255,0.06)",
            }}
          >
            <div className="px-4 py-3" style={{ borderBottom: "1px solid rgba(0,212,255,0.15)" }}>
              <p className="hud-label text-[10px] tracking-wider" style={{ color: "rgba(0,212,255,0.85)" }}>最近聊天</p>
            </div>
            <div className="flex-1 overflow-y-auto py-1">
              {rooms.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-40 px-4 text-center gap-2">
                  <User size={28} className="text-muted-foreground/40" />
                  <p className="text-[11px] text-muted-foreground">接受匹配后会出现在这里</p>
                </div>
              ) : rooms.map(room => (
                <button
                  key={room.room_id}
                  onClick={() => openChat(room)}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-3 transition-all hover:bg-secondary text-left",
                    selected?.room_id === room.room_id && "bg-secondary"
                  )}
                >
                  <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <span className="text-sm font-semibold text-primary">{room.peer[0]}</span>
                  </div>
                  <span className="text-sm font-medium truncate">{room.peer}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 右侧：聊天区 / 匹配卡飘动区 (Earth3D 在外层公共背景) */}
          <div className="flex-1 flex flex-col min-w-0 relative z-10">
            {!selected ? (
              <div className="flex-1 relative overflow-hidden">
                {pendingMatches.length === 0 ? (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center opacity-60">
                    <Sparkles size={28} className="text-muted-foreground/40" />
                    <p className="text-xs text-muted-foreground">聊到能连上别人的话题时<br/>她会在这儿轻轻提一下</p>
                  </div>
                ) : (
                  pendingMatches.map((m, idx) => {
                    const pos = cardPositions[m.id] ?? { x: 10 + idx * 8, y: 10 + idx * 8 };
                    return (
                      <CloudCard
                        key={m.id}
                        match={m}
                        index={idx}
                        pos={pos}
                        onAccept={(m, g) => handleAcceptMatch(m, g)}
                        onSkip={handleSkipMatch}
                        onExpire={handleCardExpire}
                      />
                    );
                  })
                )}
              </div>
            ) : (
              <>
                {/* header */}
                <div className="glass border-b border-border px-5 py-3 shrink-0 flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center">
                    <span className="text-xs font-semibold text-primary">{selected.peer[0]}</span>
                  </div>
                  <p className="text-sm font-semibold">{selected.peer}</p>
                </div>

                {/* 消息列表 */}
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
                  {messages.map((m, i) => {
                    const isSelf = m.sender === username;
                    return (
                      <div key={i} className={cn("flex", isSelf ? "justify-end" : "justify-start")}>
                        <div className={cn(
                          "max-w-[70%] px-4 py-2 rounded-2xl text-sm leading-relaxed",
                          isSelf
                            ? "bg-primary text-white rounded-br-sm"
                            : "bg-secondary text-foreground rounded-bl-sm"
                        )}>
                          {m.content}
                        </div>
                      </div>
                    );
                  })}
                  <div ref={bottomRef} />
                </div>

                {/* 输入框 */}
                <div className="glass border-t border-border px-4 py-3 shrink-0">
                  <div className="flex items-end gap-2 bg-secondary rounded-2xl px-4 py-2">
                    <textarea
                      value={input}
                      onChange={e => setInput(e.target.value)}
                      onKeyDown={handleKey}
                      placeholder="发消息…"
                      rows={1}
                      className="flex-1 resize-none bg-transparent text-sm outline-none py-1.5 leading-relaxed max-h-[100px] text-foreground placeholder:text-muted-foreground"
                    />
                    <button
                      onClick={handleSend}
                      disabled={!input.trim()}
                      className={cn(
                        "w-8 h-8 flex items-center justify-center rounded-full transition-all mb-0.5",
                        input.trim() ? "bg-primary text-white hover:opacity-90" : "text-muted-foreground"
                      )}
                    >
                      <Send size={14} />
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

        </div>
      </div>
      <style jsx global>{`
        @keyframes cloud-drift {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
        .cloud-card {
          opacity: 0;
          transform: translateY(-24px) scale(0.96);
          transition: opacity 1.2s ease-out, transform 1.5s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .cloud-card.cloud-stable {
          opacity: 1;
          transform: translateY(0) scale(1);
          animation: cloud-drift 6s ease-in-out infinite;
        }
        .cloud-card.cloud-out {
          opacity: 0;
          transform: translateY(-32px) scale(0.95);
          transition: opacity 2s ease-in, transform 2.5s ease-in;
          animation: none;
        }
      `}</style>
    </div>
  );
}
