"use client";

import { Suspense, useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import Earth3D from "@/components/Earth3D";
import { Send, User, Sparkles, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch, getUsername as readStoredUsername } from "@/lib/auth";

import { API_BASE as API, WS_BASE } from "@/lib/config";

interface Room { peer: string; room_id: string }
interface PeerMsg { sender: string; content: string; created_at: string }
type PeerWsEvent =
  | ({ type: "message" } & PeerMsg)
  | { type: "history"; messages: PeerMsg[] };
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
        "cloud-card glass-card w-80 px-5 py-4 mobile:static! mobile:w-full mobile:min-w-0 mobile:break-words",
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
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-[6px] bg-secondary">
          <Sparkles size={16} style={{ color: "var(--amber-ink)" }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-foreground/70">神秘好友</span>
            <span className="tag tag-amber">
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
            <div
              className="mt-2 flex items-start gap-1.5 rounded-[6px] border px-3.5 py-2.5"
              style={{ background: "var(--fill)", borderColor: "var(--glass-border)" }}
            >
              <MessageCircle size={11} className="mt-0.5 shrink-0" style={{ color: "var(--amber-ink)" }} />
              <p className="text-[11px] text-foreground/80 leading-relaxed">「{match.peer_greeting}」</p>
            </div>
          )}
          {match.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {match.tags.map((t, i) => (
                <span key={i} className="chip h-6 px-2 text-[10px] mobile:h-auto mobile:max-w-full mobile:break-all mobile:whitespace-normal">
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
            className="w-full resize-none rounded-[6px] border bg-card px-3 py-[9px] text-xs leading-relaxed text-foreground outline-none placeholder:text-muted-foreground focus:border-[color:var(--amber-ink)] mobile:text-base"
          />
          <div className="flex gap-2 mt-2 justify-end">
            <button
              onClick={() => setShowGreeting(false)}
              className="btn btn-quiet h-7 px-2.5 text-xs"
            >跳过</button>
            <button
              onClick={() => onAccept(match, greetingText)}
              className="btn btn-primary h-7 px-2.5 text-xs"
            >发送打招呼</button>
          </div>
        </div>
      )}

      {!showGreeting && (
        <div className="flex gap-2 mt-3 justify-end">
          <button
            onClick={() => onSkip(match.id)}
            className="btn btn-quiet h-7 px-2.5 text-xs"
          >算了</button>
          <button
            onClick={() => setShowGreeting(true)}
            className="btn btn-primary h-7 px-2.5 text-xs"
          >认识下</button>
        </div>
      )}
    </div>
  );
}

function MatchContent() {
  const [username, setUsername] = useState("默认用户");
  const [hydrated, setHydrated] = useState(false);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [selected, setSelected] = useState<Room | null>(null);
  const [messages, setMessages] = useState<PeerMsg[]>([]);
  const [input, setInput] = useState("");
  const [pendingMatches, setPendingMatches] = useState<PendingMatch[]>([]);
  const [cardPositions, setCardPositions] = useState<Record<number, { x: number; y: number }>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const selectedRoomIdRef = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 启动后从 localStorage 读取当前身份
  useEffect(() => {
    const u = localStorage.getItem("fiona_user");
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
    const lastIds = new Set<number>();

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

  // 用户点"认识下"后 accept，并携带可选招呼
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
    const roomId = room.room_id;
    selectedRoomIdRef.current = roomId;
    if (wsRef.current) wsRef.current.close();
    setSelected(room);
    setMessages([]);

    apiFetch(`${API}/peer/history/${roomId}`)
      .then(r => r.json())
      .then(data => {
        if (selectedRoomIdRef.current === roomId && data.room_id === roomId) {
          setMessages(data.messages || []);
        }
      })
      .catch(() => {});

    const devAuth = process.env.NODE_ENV !== "production"
      ? `?dev_user=${encodeURIComponent(readStoredUsername() || username)}`
      : "";
    const ws = new WebSocket(`${WS_BASE}/ws/peer/${roomId}${devAuth}`);
    ws.onmessage = (e) => {
      if (selectedRoomIdRef.current !== roomId || wsRef.current !== ws) return;
      const msg = JSON.parse(e.data) as PeerWsEvent;
      if (msg.type === "history") return;
      if (msg.type === "message") setMessages(prev => [...prev, msg]);
    };
    wsRef.current = ws;
  }, [username]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 离开页面时关掉聊天 WebSocket，避免连接泄漏与卸载后 setState 警告
  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

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
    <div className={cn("flex h-screen flex-col overflow-hidden mobile:h-dvh", !embedded && "mobile:pb-[calc(56px+env(safe-area-inset-bottom))]")}>
      <div className="flex flex-1 min-h-0">
        {!embedded && <Sidebar />}
        <div className="flex flex-1 min-w-0 relative overflow-hidden mobile:min-h-0 mobile:flex-col">

          {/* 3D 地球背景：横跨整个区域，让左栏也能透出宇宙 */}
          <Earth3D />

          {/* 左侧：最近 5 个联系人 (玻璃质感，星空直接穿透) */}
          <div className="glass-card relative z-10 m-4 mr-0 flex w-64 shrink-0 flex-col overflow-hidden mobile:m-3 mobile:mb-0 mobile:w-auto">
            <div className="border-b px-4 py-3" style={{ borderColor: "var(--glass-border)" }}>
              <p className="text-xs font-medium text-muted-foreground">最近聊天</p>
            </div>
            <div className="flex-1 overflow-y-auto py-1 mobile:flex mobile:flex-none mobile:overflow-x-auto mobile:overflow-y-hidden">
              {rooms.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-40 px-4 text-center gap-2 mobile:h-16 mobile:w-full">
                  <User size={28} className="text-muted-foreground/40" />
                  <p className="text-[11px] text-muted-foreground">接受匹配后会出现在这里</p>
                </div>
              ) : rooms.map(room => (
                <button
                  key={room.room_id}
                  onClick={() => openChat(room)}
                  className={cn(
                    "chip h-auto w-full justify-start px-4 py-3 text-left transition-colors hover:bg-secondary mobile:w-auto mobile:min-w-32 mobile:shrink-0",
                    selected?.room_id === room.room_id && "chip-on"
                  )}
                >
                  <div className="grid h-9 w-9 shrink-0 place-items-center rounded-[6px] bg-secondary">
                    <span className="text-sm font-medium" style={{ color: "var(--amber-ink)" }}>{room.peer[0]}</span>
                  </div>
                  <span className="text-sm font-medium truncate">{room.peer}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 右侧：聊天区 / 匹配卡飘动区 (Earth3D 在外层公共背景) */}
          <div className={cn("relative z-10 flex min-w-0 flex-1 flex-col mobile:min-h-0", selected && "glass-card m-4 overflow-hidden mobile:m-3")}>
            {!selected ? (
              <div className="flex-1 relative overflow-hidden mobile:flex mobile:min-h-0 mobile:flex-col mobile:gap-3 mobile:overflow-y-auto mobile:p-3">
                {pendingMatches.length === 0 ? null : (
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
                <div className="flex shrink-0 items-center gap-3 border-b px-5 py-3 mobile:px-4" style={{ borderColor: "var(--glass-border)" }}>
                  <div className="grid h-7 w-7 place-items-center rounded-[6px] bg-secondary">
                    <span className="text-xs font-medium" style={{ color: "var(--amber-ink)" }}>{selected.peer[0]}</span>
                  </div>
                  <p className="text-sm font-medium mobile:min-w-0 mobile:truncate">{selected.peer}</p>
                </div>

                {/* 消息列表 */}
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 mobile:min-h-0 mobile:px-4">
                  {messages.map((m, i) => {
                    const isSelf = m.sender === username;
                    return (
                      <div key={i} className={cn("flex", isSelf ? "justify-end" : "justify-start")}>
                        <div className={cn("flex flex-col gap-1.5 mobile:max-w-[80vw] mobile:min-w-0", isSelf ? "max-w-[520px] items-end" : "max-w-[640px] items-start")}>
                          {!isSelf && (
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                              <span className="inline-block h-1.5 w-1.5" style={{ background: "var(--amber-ink)" }} />
                              {m.sender}
                            </div>
                          )}
                          <div className={cn("text-sm mobile:max-w-full mobile:break-words", isSelf ? "bubble-user" : "bubble-ai")}>
                            {m.content}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  <div ref={bottomRef} />
                </div>

                {/* 输入框 */}
                <div className="glass shrink-0 border-t px-4 py-3 mobile:px-3" style={{ borderColor: "var(--glass-border)" }}>
                  <div className="flex items-end gap-2 rounded-[10px] border px-3.5 py-2.5 mobile:min-w-0" style={{ background: "var(--fill)", borderColor: "var(--glass-border)" }}>
                    <textarea
                      value={input}
                      onChange={e => setInput(e.target.value)}
                      onKeyDown={handleKey}
                      placeholder="发消息…"
                      rows={1}
                      className="flex-1 resize-none bg-transparent text-sm outline-none py-1.5 leading-relaxed max-h-[100px] text-foreground placeholder:text-muted-foreground mobile:min-w-0 mobile:text-base"
                    />
                    <button
                      onClick={handleSend}
                      disabled={!input.trim()}
                      className="btn btn-primary mb-0.5 h-8 w-8 px-0 mobile:h-10 mobile:w-10 mobile:shrink-0"
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
          50% { transform: translateY(-3px); }
        }
        .cloud-card.glass-card {
          opacity: 0;
          transform: translateY(-24px) scale(0.96);
          transition: opacity 1.2s ease-out, transform 1.5s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .cloud-card.cloud-stable {
          opacity: 1;
          transform: translateY(0) scale(1);
          animation: cloud-drift 10s ease-in-out infinite;
        }
        .cloud-card.cloud-out {
          opacity: 0;
          transform: translateY(-32px) scale(0.95);
          transition: opacity 2s ease-in, transform 2.5s ease-in;
          animation: none;
        }
        @media (prefers-reduced-motion: reduce) {
          .cloud-card.cloud-stable {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
}

export default function MatchPage() {
  return (
    <Suspense fallback={null}>
      <MatchContent />
    </Suspense>
  );
}
