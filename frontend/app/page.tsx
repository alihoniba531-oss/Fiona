"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import ChatBubble, { type Message, type CardData, type WeatherData } from "@/components/ChatBubble";
import AmbientHUD from "@/components/AmbientHUD";
import HudOrb from "@/components/HudOrb";
import StarField from "@/components/StarField";
import { ChevronUp } from "lucide-react";
import {
  Send, Mic, Volume2, VolumeX, ChevronDown, ChevronRight,
  Trash2, ImagePlus, X, UserRound, Wifi, WifiOff, Clock,
  Sparkles, Globe,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch, getToken, getUsername as readStoredUsername } from "@/lib/auth";

const API = "/api";
const WS_BASE = typeof window !== "undefined"
  ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/api`
  : "";

// ── interfaces (kept but peer chat is not rendered in UI) ──

interface PeerMessage {
  id?: number;
  sender: string;
  content: string;
  created_at: string;
}

interface PeerRoom {
  peer: string;
  room_id: string;
}

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

// ── Mini cloud card for match popups ──

function MiniCloudCard({
  match,
  pos,
  onAccept,
  onSkip,
  onExpire,
}: {
  match: PendingMatch;
  pos: { x: number; y: number };
  onAccept: (m: PendingMatch) => void;
  onSkip: (id: number) => void;
  onExpire: (id: number) => void;
}) {
  const [visible, setVisible] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const t1 = setTimeout(() => setVisible(true), 50);
    const t2 = setTimeout(() => setLeaving(true), 25000);
    const t3 = setTimeout(() => onExpire(match.id), 27000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, [match.id, onExpire]);

  return (
    <div
      className="w-64 bg-card/90 backdrop-blur-md border border-border/60 rounded-2xl px-4 py-3 shadow-xl"
      style={{
        position: "absolute",
        left: `${pos.x}%`,
        top: `${pos.y}%`,
        zIndex: 20,
        opacity: leaving ? 0 : visible ? 1 : 0,
        transform: leaving
          ? "translateY(-20px) scale(0.95)"
          : visible
            ? "translateY(0) scale(1)"
            : "translateY(-16px) scale(0.96)",
        transition: "opacity 1s ease, transform 1.2s cubic-bezier(0.16,1,0.3,1)",
      }}
    >
      <div className="flex items-start gap-2">
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
          <Sparkles size={13} className="text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="font-semibold text-xs text-foreground/60">神秘好友</span>
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
              {match.type}
            </span>
          </div>
          {match.interest_topic && (
            <p className="text-[9px] text-muted-foreground mb-1">
              因为聊到{" "}
              <span className="text-foreground/70 font-medium">「{match.interest_topic}」</span>
            </p>
          )}
          <p className="text-[11px] text-foreground/80 leading-snug line-clamp-2">
            {match.reason}
          </p>
          {match.peer_greeting && (
            <p className="text-[10px] text-foreground/70 mt-1.5 bg-secondary/60 rounded-lg px-2 py-1">
              「{match.peer_greeting}」
            </p>
          )}
        </div>
      </div>
      <div className="flex gap-1.5 mt-2.5 justify-end">
        <button
          onClick={() => onSkip(match.id)}
          className="text-[10px] px-2.5 py-1 rounded-full text-muted-foreground hover:bg-secondary transition-colors"
        >
          算了
        </button>
        <button
          onClick={() => onAccept(match)}
          className="text-[10px] px-2.5 py-1 rounded-full bg-primary text-white hover:opacity-90 transition-opacity"
        >
          认识下
        </button>
      </div>
    </div>
  );
}

// ── demo messages & helpers ──

const DEMO_MESSAGES: Message[] = [
  { id: "1", role: "assistant", content: "嘿，今天怎么样？", timestamp: new Date("2025-05-07T10:00:00") },
  { id: "2", role: "user", content: "还行，就是有点累", timestamp: new Date("2025-05-07T10:01:00") },
  { id: "3", role: "assistant", content: "累是什么感觉的累？身体还是脑子？", timestamp: new Date("2025-05-07T10:02:00") },
  { id: "4", role: "user", content: "脑子累，想太多了", timestamp: new Date("2025-05-08T09:15:00") },
  { id: "5", role: "assistant", content: "想太多的时候，最近脑子里转的是什么？", timestamp: new Date("2025-05-08T09:16:00") },
  { id: "6", role: "user", content: "工作的事，感觉方向不对但又不知道怎么调", timestamp: new Date("2025-05-08T09:18:00") },
  { id: "7", role: "assistant", content: "妈的，这种感觉最难受了。说说看，哪里让你觉得不对？", timestamp: new Date("2025-05-09T20:30:00") },
  { id: "8", role: "user", content: "就是每天做的事好像和自己想要的越来越远", timestamp: new Date("2025-05-09T20:32:00") },
];

function groupByDate(msgs: Message[]) {
  const groups: Record<string, Message[]> = {};
  msgs.forEach((m) => {
    const key = m.timestamp.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
    if (!groups[key]) groups[key] = [];
    groups[key].push(m);
  });
  // Sort groups by the actual timestamp of the first message in each group
  return Object.entries(groups).sort(
    (a, b) => b[1][0].timestamp.getTime() - a[1][0].timestamp.getTime(),
  );
}

// ── weather helpers ──
const WEATHER_CN: Record<string, string> = {
  "sunny": "晴", "clear": "晴", "partly cloudy": "多云", "cloudy": "阴",
  "overcast": "阴", "mist": "薄雾", "fog": "雾", "haze": "霾",
  "rain": "雨", "light rain": "小雨", "moderate rain": "中雨", "heavy rain": "大雨",
  "drizzle": "毛毛雨", "shower": "阵雨", "thunder": "雷", "storm": "暴风雨",
  "snow": "雪", "light snow": "小雪", "heavy snow": "大雪", "hail": "冰雹",
  "sleet": "雨夹雪", "ice": "冻雨",
};
function weatherCN(cond: string) {
  const c = (cond || "").toLowerCase();
  for (const [en, zh] of Object.entries(WEATHER_CN)) {
    if (c.includes(en)) return zh;
  }
  return cond || "?";
}

function getWeatherTheme(condition: string) {
  const c = (condition || "").toLowerCase();
  if (c.includes("sunny") || c.includes("clear")) {
    return { bg: "linear-gradient(145deg, #1a0a00 0%, #2d1810 30%, #4a2c10 60%, #2d1810 100%)", accent: "#f0a030", glow: "rgba(240,160,48,0.25)", text: "#fdd8a0", sub: "rgba(253,200,140,0.5)" };
  }
  if (c.includes("cloud") || c.includes("overcast")) {
    return { bg: "linear-gradient(145deg, #0d1117 0%, #161b22 30%, #21262d 60%, #161b22 100%)", accent: "#8b949e", glow: "rgba(139,148,158,0.2)", text: "#c9d1d9", sub: "rgba(201,209,217,0.5)" };
  }
  if (c.includes("rain") || c.includes("drizzle") || c.includes("shower")) {
    return { bg: "linear-gradient(145deg, #050d18 0%, #0d1b2a 30%, #1b2838 60%, #0d1b2a 100%)", accent: "#38bdf8", glow: "rgba(56,189,248,0.25)", text: "#bae6fd", sub: "rgba(186,230,253,0.5)" };
  }
  if (c.includes("thunder") || c.includes("storm")) {
    return { bg: "linear-gradient(145deg, #0a001a 0%, #1a0040 30%, #2d0060 60%, #1a0040 100%)", accent: "#a78bfa", glow: "rgba(167,139,250,0.3)", text: "#ddd6fe", sub: "rgba(221,214,254,0.5)" };
  }
  if (c.includes("snow") || c.includes("ice") || c.includes("hail")) {
    return { bg: "linear-gradient(145deg, #0a1628 0%, #112240 30%, #1a3350 60%, #112240 100%)", accent: "#e2e8f0", glow: "rgba(226,232,240,0.25)", text: "#f1f5f9", sub: "rgba(241,245,249,0.5)" };
  }
  if (c.includes("mist") || c.includes("fog") || c.includes("haze")) {
    return { bg: "linear-gradient(145deg, #0f0f1a 0%, #1a1a2e 30%, #252540 60%, #1a1a2e 100%)", accent: "#94a3b8", glow: "rgba(148,163,184,0.2)", text: "#cbd5e1", sub: "rgba(203,213,225,0.5)" };
  }
  // default — warm amber
  return { bg: "linear-gradient(145deg, #1a0a00 0%, #2d1810 30%, #4a2c10 60%, #2d1810 100%)", accent: "#f0a030", glow: "rgba(240,160,48,0.25)", text: "#fdd8a0", sub: "rgba(253,200,140,0.5)" };
}

// ── main page ──

export default function ChatPage() {
  // ---- core chat state ----
  const [messages, setMessages] = useState<Message[]>([]);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [sessionStart, setSessionStart] = useState<Date>(new Date(0));
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeCards, setActiveCards] = useState<CardData[]>([]);
  const [hoveredCard, setHoveredCard] = useState<number | null>(null);
  const [enlargedCard, setEnlargedCard] = useState<CardData | null>(null);
  const [plazaOpen, setPlazaOpen] = useState(false);
  const [matchOpen, setMatchOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [username, setUsername] = useState("默认用户");
  const [hydrated, setHydrated] = useState(false);
  const [allUsers, setAllUsers] = useState<string[]>([]);
  const [voiceOn, setVoiceOn] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const [recording, setRecording] = useState(false);
  const [inlineRecording, setInlineRecording] = useState(false);
  const [voiceText, setVoiceText] = useState("");
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  // 中间聊天面板"卷帘门"状态 —— 只能手动点 COLLAPSE/EXPAND 切换，不再 30s 自动收起
  const [chatCollapsed, setChatCollapsed] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  // 跟随贴底状态：用 scroll 事件维护，而不是渲染后量距离 —— 渲染后新消息已撑大 scrollHeight，
  // 量出来的"距底"会包含新消息高度，长消息一进来就误判为"用户上滑"，结果不跟随
  const wasNearBottomRef = useRef(true);
  const peerWasNearBottomRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isComposingRef = useRef(false);
  const handleSendRef = useRef<(text?: string) => Promise<void>>(async () => {});
  const handsFreeRef = useRef(false);
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);
  const ttsPreloadRef = useRef<HTMLAudioElement | null>(null);  // 预取下一句音频，消除句间空隙
  const ttsQueueRef = useRef<string[]>([]);
  const ttsPlayingRef = useRef(false);
  const ttsSessionRef = useRef(0);
  const streamDoneRef = useRef(true);
  const synthRef = useRef<SpeechSynthesis | null>(null);
  const nlsWsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  // ---- peer chat state (not rendered in UI) ----
  const [peerRooms, setPeerRooms] = useState<PeerRoom[]>([]);
  const [activePeer, setActivePeer] = useState<PeerRoom | null>(null);
  const [pendingMatches, setPendingMatches] = useState<PendingMatch[]>([]);
  const [cardPositions, setCardPositions] = useState<Record<number, { x: number; y: number }>>({});
  const [peerMessages, setPeerMessages] = useState<PeerMessage[]>([]);
  const [peerInput, setPeerInput] = useState("");
  const [peerConnected, setPeerConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const peerBottomRef = useRef<HTMLDivElement>(null);

  // ---- user identity / settings ----
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [myGender, setMyGender] = useState<"male" | "female" | null>(null);
  const [matchPref, setMatchPref] = useState<"male" | "female" | "both">("both");
  const userMenuRef = useRef<HTMLDivElement>(null);

  // ── effects ──

  // Hydrate username from localStorage (must finish before history/persist effects run)
  useEffect(() => {
    const stored = localStorage.getItem("fiona_user");
    if (stored) setUsername(stored);
    setHydrated(true);
  }, []);

  // Persist username to localStorage — only after hydration, so initial "默认用户" doesn't overwrite a stored login
  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem("fiona_user", username);
  }, [username, hydrated]);

  // Load all users
  useEffect(() => {
    // /users 仅 DEV_MODE 开放；prod 返 404，安静忽略
    fetch(`${API}/users`)
      .then((r) => r.ok ? r.json() : { users: [] })
      .then((d) => setAllUsers(d.users || []))
      .catch(() => {});
  }, []);

  // Load user settings
  useEffect(() => {
    if (!hydrated || !username) return;
    apiFetch(`${API}/user/settings`)
      .then((r) => r.json())
      .then((d) => {
        const s = d.settings || {};
        setMyGender(s.gender === "male" || s.gender === "female" ? s.gender : null);
        setMatchPref(
          ["male", "female", "both"].includes(s.match_pref) ? s.match_pref : "both",
        );
      })
      .catch(() => {});
  }, [username, hydrated]);

  // Close user menu on outside click
  useEffect(() => {
    if (!userMenuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [userMenuOpen]);

  // Load peer rooms
  const loadPeerRooms = useCallback(() => {
    apiFetch(`${API}/peer/rooms`)
      .then((r) => r.json())
      .then((d) => setPeerRooms(d.rooms || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    loadPeerRooms();
  }, [loadPeerRooms, hydrated]);

  // Poll pending matches
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
        setPendingMatches((prev) => {
          const existingIds = new Set(prev.map((p) => p.id));
          const fresh = incoming.filter(
            (p) => !existingIds.has(p.id) && !lastIds.has(p.id),
          );
          const canAdd = Math.max(0, 3 - prev.length);
          const toAdd = fresh.slice(0, canAdd);
          toAdd.forEach((p) => {
            lastIds.add(p.id);
            setCardPositions((pos) => ({
              ...pos,
              [p.id]: {
                x: 2 + Math.random() * 20,
                y: 5 + Math.random() * 55,
              },
            }));
          });
          return [...prev, ...toAdd];
        });
      } catch {
        // ignore polling errors
      }
    }
    poll();
    const timer = setInterval(poll, 8000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [username, hydrated]);

  // Init TTS + pre-request mic permission so it doesn't interrupt press-and-hold
  useEffect(() => {
    synthRef.current = window.speechSynthesis;
    // Pre-warm mic permission on first visit
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream) => { stream.getTracks().forEach(t => t.stop()); })
      .catch(() => {}); // user denied — handle gracefully
  }, []);

  // Global mouseup: stop recording if mouse released outside the button
  useEffect(() => {
    if (!recording) return;
    const up = () => setRecording(false);
    window.addEventListener("mouseup", up);
    window.addEventListener("touchend", up);
    return () => {
      window.removeEventListener("mouseup", up);
      window.removeEventListener("touchend", up);
    };
  }, [recording]);

  // HTTP-based voice recognition (one-shot)
  const mediaRecorderRef2 = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const startNlsAsr = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      mediaRecorderRef2.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (blob.size < 100) { setVoiceText(""); return; }
        setVoiceText("识别中…");
        try {
          // Convert blob to base64
          const buf = await blob.arrayBuffer();
          const bytes = new Uint8Array(buf);
          let b64 = "";
          for (let i = 0; i < bytes.length; i++) b64 += String.fromCharCode(bytes[i]);
          const base64 = btoa(b64);
          const res = await fetch(`${API}/asr/recognize`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ audio: base64, format: "opus", sample_rate: 16000 }),
          });
          const data = await res.json();
          if (data.text) { setVoiceText(""); handleSendRef.current(data.text); }
          else { setVoiceText(data.error || "未识别到语音"); setTimeout(() => setVoiceText(""), 2000); }
        } catch (e: any) { setVoiceText("识别失败"); setTimeout(() => setVoiceText(""), 2000); }
      };
      mr.start();
    } catch (e: any) {
      setVoiceText("麦克风未授权"); setTimeout(() => setRecording(false), 1000);
    }
  }, []);

  const stopNlsAsr = useCallback(() => {
    const mr = mediaRecorderRef2.current;
    if (mr && mr.state === 'recording') mr.stop();
  }, []);

  // Toggle recording (voice panel)
  useEffect(() => {
    if (recording) { setVoiceText(""); startNlsAsr(); }
    else { stopNlsAsr(); }
  }, [recording, startNlsAsr, stopNlsAsr]);

  // Inline voice-to-text: records, sends to ASR, puts text in input for review
  const inlineMrRef = useRef<MediaRecorder | null>(null);
  const inlineChunksRef = useRef<Blob[]>([]);
  const toggleInlineVoice = useCallback(async () => {
    if (inlineRecording) {
      // Stop recording
      const mr = inlineMrRef.current;
      if (mr && mr.state === 'recording') mr.stop();
      setInlineRecording(false);
    } else {
      // Start recording
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
        inlineMrRef.current = mr;
        inlineChunksRef.current = [];
        mr.ondataavailable = (e) => { if (e.data.size > 0) inlineChunksRef.current.push(e.data); };
        mr.onstop = async () => {
          stream.getTracks().forEach(t => t.stop());
          const blob = new Blob(inlineChunksRef.current, { type: 'audio/webm' });
          if (blob.size < 100) return;
          try {
            const buf = await blob.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let b64 = ""; for (let i = 0; i < bytes.length; i++) b64 += String.fromCharCode(bytes[i]);
            const res = await fetch(`${API}/asr/recognize`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ audio: btoa(b64), format: "opus", sample_rate: 16000 }),
            });
            const data = await res.json();
            if (data.text) handleSendRef.current(data.text);
          } catch (_) {}
        };
        mr.start();
        setInlineRecording(true);
      } catch (_) {}
    }
  }, [inlineRecording]);

  // ── 免提模式：朗读完自动录音，静音 1.5s 自动停 + 自动发 ──
  const startHandsFreeRecording = useCallback(async () => {
    if (!handsFreeRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      const chunks: Blob[] = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };

      const audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      const SILENCE_THRESHOLD = 0.015;
      const SILENCE_MS = 1500;
      const MAX_MS = 30000;
      let hasSpoken = false;
      let silenceSince = 0;
      const startedAt = Date.now();

      const tick = () => {
        if (mr.state !== 'recording') return;
        analyser.getByteTimeDomainData(buf);
        let sumSq = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sumSq += v * v;
        }
        const rms = Math.sqrt(sumSq / buf.length);
        const now = Date.now();
        if (rms > SILENCE_THRESHOLD) {
          hasSpoken = true;
          silenceSince = 0;
        } else if (hasSpoken && silenceSince === 0) {
          silenceSince = now;
        }
        if (hasSpoken && silenceSince && now - silenceSince > SILENCE_MS) { mr.stop(); return; }
        if (now - startedAt > MAX_MS) { mr.stop(); return; }
        if (!handsFreeRef.current) { mr.stop(); return; }
        requestAnimationFrame(tick);
      };

      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        audioCtx.close().catch(() => {});
        if (!hasSpoken) return;
        const blob = new Blob(chunks, { type: 'audio/webm' });
        if (blob.size < 100) return;
        try {
          const ab = await blob.arrayBuffer();
          const bytes = new Uint8Array(ab);
          let b64 = ""; for (let i = 0; i < bytes.length; i++) b64 += String.fromCharCode(bytes[i]);
          const res = await fetch(`${API}/asr/recognize`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ audio: btoa(b64), format: "opus", sample_rate: 16000 }),
          });
          const data = await res.json();
          if (data.text) handleSendRef.current(data.text);
        } catch (_) {}
      };

      mr.start();
      requestAnimationFrame(tick);
    } catch (e) { console.error('[handsfree] mic error', e); }
  }, []);

  // ── 流式 TTS 队列：按句送合成、顺序播放，**预取下一句消除句间空隙** ──
  const mkTtsAudio = useCallback((text: string): HTMLAudioElement => {
    const url = `${API}/tts/stream?text=${encodeURIComponent(text.slice(0, 300))}&voice=longxiaoxia_v2&speech_rate=1.15`;
    const a = new Audio(url);
    a.preload = "auto";
    return a;
  }, []);

  // 当前句正在播 → 把队头那句的音频提前 fetch 好，下一句结束时立刻接上
  const tryPrefetch = useCallback(() => {
    if (!ttsPlayingRef.current) return;
    if (ttsPreloadRef.current) return;
    const next = ttsQueueRef.current.shift();
    if (!next) return;
    const a = mkTtsAudio(next);
    a.load();
    ttsPreloadRef.current = a;
  }, [mkTtsAudio]);

  const playNextInQueue = useCallback(() => {
    if (ttsPlayingRef.current) return;

    // 优先用已预取的，否则现 fetch
    let audio = ttsPreloadRef.current;
    ttsPreloadRef.current = null;
    if (!audio) {
      const next = ttsQueueRef.current.shift();
      if (!next) {
        if (streamDoneRef.current && handsFreeRef.current) {
          startHandsFreeRecording();
        }
        return;
      }
      audio = mkTtsAudio(next);
    }

    ttsPlayingRef.current = true;
    ttsAudioRef.current = audio;
    // 立刻把"再下一句"也预取，与当前播放重叠
    tryPrefetch();

    const onDone = () => {
      ttsPlayingRef.current = false;
      ttsAudioRef.current = null;
      playNextInQueue();
    };
    audio.onended = onDone;
    audio.onerror = onDone;
    audio.play().catch(onDone);
  }, [startHandsFreeRecording, mkTtsAudio, tryPrefetch]);

  // ── TTS 文本归一化：日期/时间/数字范围转成可读的中文 ──
  // CosyVoice 默认会把 "4.3" 念成"四点三"（小数），把 "780–2380" 念成"七百八十—两千三百八十"
  // 拼读出来的句子不像人话。在送 TTS 前把这些模式改写成口播友好的写法。
  // 屏幕上的文字保持原样（"4.3–4.5"看着像日期就够了），只改语音那一路。
  const normalizeForTTS = useCallback((text: string): string => {
    let s = text;
    // 日期范围 "M.D–M.D" → "M月D日到M月D日"
    // 月份/日期 alternation 必须长串在前（JS 正则不是 longest-match，先匹配先决定），
    // 否则 "5.15" 会被吃成 "5月1日" + 残留 "5"
    s = s.replace(
      /(1[0-2]|[1-9])\.(3[01]|[12]\d|[1-9])\s*[–—~\-]\s*(1[0-2]|[1-9])\.(3[01]|[12]\d|[1-9])/g,
      "$1月$2日到$3月$4日",
    );
    // 单个 "M.D" 极容易和小数 (3.14 / 版本号 / 4.5 分钟) 撞，删除该规则
    // 范围形式 "M.D–M.D" 因为有 "–" 锚定，是唯一安全的日期模式
    // 时间范围 "HH:MM–HH:MM" → "HH点MM分到HH点MM分"
    s = s.replace(
      /(\d{1,2}):(\d{2})\s*[–—~\-]\s*(\d{1,2}):(\d{2})/g,
      "$1点$2分到$3点$4分",
    );
    // 单个时间 "HH:MM" → "HH点MM分"
    s = s.replace(/(\d{1,2}):(\d{2})(?!\d)/g, "$1点$2分");
    // 纯数字范围 "780–2380" → "780到2380"（仅 unicode 长划线，避开 "-1" 之类）
    s = s.replace(/(\d+(?:\.\d+)?)\s*[–—~]\s*(\d+(?:\.\d+)?)/g, "$1到$2");
    return s;
  }, []);

  const enqueueSpeech = useCallback((text: string, sessionId: number) => {
    if (!voiceOn) return;
    if (sessionId !== ttsSessionRef.current) return;
    const t = normalizeForTTS(text.trim());
    if (!t) return;
    ttsQueueRef.current.push(t);
    if (ttsPlayingRef.current) {
      tryPrefetch();  // 与当前播放重叠 fetch
    } else {
      playNextInQueue();
    }
  }, [voiceOn, playNextInQueue, tryPrefetch, normalizeForTTS]);

  const clearTtsQueue = useCallback(() => {
    ttsQueueRef.current = [];
    if (ttsAudioRef.current) {
      try { ttsAudioRef.current.pause(); } catch (_) {}
      ttsAudioRef.current = null;
    }
    if (ttsPreloadRef.current) {
      try { ttsPreloadRef.current.pause(); } catch (_) {}
      ttsPreloadRef.current = null;
    }
    ttsPlayingRef.current = false;
  }, []);

  // keep handsFreeRef in sync with state for closures that capture once
  useEffect(() => { handsFreeRef.current = handsFree; }, [handsFree]);

  // Mount-time reset (F5 fix: clear stuck isLoading and typing messages)
  useEffect(() => {
    setIsLoading(false);
    setMessages((prev) => prev.filter((m) => !m.isTyping));
  }, []);

  // Load history — only after hydration so we use the real username, not the "默认用户" placeholder
  useEffect(() => {
    if (!hydrated) return;
    apiFetch(`${API}/history`)
      .then((r) => r.json())
      .then((data) => {
        const loaded: Message[] = (data.messages || []).map(
          (m: {
            id: number;
            role: string;
            content: string;
            image_path: string | null;
            created_at: string;
          }) => ({
            id: `db-${m.id}`,
            dbId: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
            timestamp: new Date(m.created_at),
            imageUrl: m.image_path ? `${API}${m.image_path}` : undefined,
          }),
        );
        setMessages(loaded);
      })
      .catch(() => {});
  }, [username, hydrated]);

  // 监听滚动维护"贴底"状态（独立于渲染时机）：用户手滑离底 → 不跟随；
  // 程序触发的 scrollIntoView 也会回调这里，自然把状态拉回 true
  useEffect(() => {
    const container = bottomRef.current?.parentElement;
    if (!container) return;
    const onScroll = () => {
      const dist = container.scrollHeight - container.scrollTop - container.clientHeight;
      wasNearBottomRef.current = dist < 100;
    };
    onScroll();
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const container = peerBottomRef.current?.parentElement;
    if (!container) return;
    const onScroll = () => {
      const dist = container.scrollHeight - container.scrollTop - container.clientHeight;
      peerWasNearBottomRef.current = dist < 100;
    };
    onScroll();
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  // 消息更新时若 *渲染前* 在底部 → 跟随；否则放手，让用户继续看历史
  useEffect(() => {
    if (wasNearBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages]);

  useEffect(() => {
    if (peerWasNearBottomRef.current) {
      peerBottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [peerMessages]);

  // ── callbacks / handlers ──

  const saveUserSettings = useCallback(
    (gender: "male" | "female" | null, pref: "male" | "female" | "both") => {
      apiFetch(`${API}/user/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gender, match_pref: pref }),
      }).catch(() => {});
    },
    [],
  );

  const removeCard = useCallback((id: number) => {
    setPendingMatches((prev) => prev.filter((p) => p.id !== id));
    setCardPositions((prev) => {
      const n = { ...prev };
      delete n[id];
      return n;
    });
  }, []);

  const handleCardExpire = useCallback(
    (id: number) => {
      apiFetch(`${API}/match/pending/${id}/seen`, { method: "POST" }).catch(() => {});
      removeCard(id);
    },
    [removeCard],
  );

  const handleAcceptCard = useCallback(
    async (match: PendingMatch) => {
      apiFetch(`${API}/match/pending/${match.id}/seen`, { method: "POST" }).catch(() => {});
      try {
        await apiFetch(`${API}/match/response`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            peer: match.peer_username,
            response: "accept",
          }),
        });
        loadPeerRooms();
      } catch {
        // ignore
      }
      removeCard(match.id);
    },
    [loadPeerRooms, removeCard],
  );

  const handleSkipCard = useCallback(
    (id: number) => {
      apiFetch(`${API}/match/pending/${id}/seen`, { method: "POST" }).catch(() => {});
      removeCard(id);
    },
    [removeCard],
  );

  // ── chat actions ──

  const handleDeleteMessage = async (id: string, dbId?: number) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
    if (dbId) {
      await apiFetch(`${API}/message/${dbId}`, { method: "DELETE" }).catch(() => {});
    }
  };

  // 搜索类回复："帮我读" — 把搁置的 tip 文本送进 TTS 队列开始播放
  // 用户显式点击 = 想听 → 即使 AUDIO OFF 也自动开启并播放（绕开 enqueueSpeech 的 voiceOn 守卫）
  const handleConfirmTts = (id: string, text: string) => {
    if (!voiceOn) setVoiceOn(true);
    ttsSessionRef.current += 1;
    streamDoneRef.current = true;
    const t = normalizeForTTS(text.trim());
    if (t) {
      ttsQueueRef.current.push(t);
      if (!ttsPlayingRef.current) playNextInQueue();
    }
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, pendingTtsText: undefined } : m)));
  };

  // 搜索类回复："不用" — 直接清掉 pending 文本
  const handleDeclineTts = (id: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, pendingTtsText: undefined } : m)));
  };

  const handleClearChat = () => {
    if (!confirm("清空当前聊天界面？（历史记录仍保留）")) return;
    setMessages([]);
  };

  const handleNewChat = () => {
    setSessionStart(new Date());
    setCollapsed({});
    setTimeout(() => textareaRef.current?.focus(), 100);
  };

  const handleClearHistory = async () => {
    if (!confirm("确定要清空所有历史记录吗？此操作不可恢复。")) return;
    await apiFetch(`${API}/history`, { method: "DELETE" }).catch(() => {});
    setMessages([]);
  };

  const handleDismissCard = (index: number) => {
    setActiveCards((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSend = async (textOverride?: string) => {
    const text = (textOverride ?? input).trim();
    if ((!text && !pendingImage) || isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text || "[发了一张图片]",
      timestamp: new Date(),
      imageUrl: pendingImage || undefined,
    };
    const typingMsg: Message = {
      id: "typing",
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isTyping: true,
    };

    setMessages((prev) => [...prev, userMsg, typingMsg]);
    const sentImage = pendingImage;
    setInput("");
    setPendingImage(null);
    setIsLoading(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    // ── 流式 TTS：新一轮 → 清队列 + 新 session + 按句切（首句激进、碰逗号也切）──
    clearTtsQueue();
    ttsSessionRef.current += 1;
    const mySession = ttsSessionRef.current;
    streamDoneRef.current = false;
    let ttsBuf = "";
    let firstFlushDone = false;
    const flushSentences = () => {
      // 首句更激进：碰逗号也切；后续只在句末（。！？）切，保留韵律
      const re = firstFlushDone ? /[。！？\n.!?；;]/ : /[。！？\n.!?；;，,]/;
      // 数字间的 . : 不是句号 / 时间间隔，是日期 / 时间分隔符，不能在这里切句
      // 例: "4.3–4.5" 不能从 "4." 切开，会让 TTS 念成 "4   3"
      const isRealBoundary = (i: number): boolean => {
        const ch = ttsBuf[i];
        if (!re.test(ch)) return false;
        if (ch === "." || ch === "．") {
          const prev = ttsBuf[i - 1] || "";
          const next = ttsBuf[i + 1] || "";
          if (/\d/.test(prev) && /\d/.test(next)) return false;
        }
        return true;
      };
      // 单段 TTS 上限：CosyVoice 后端截 300，留余量
      const MAX_CHUNK = 250;
      while (true) {
        // 在前 MAX_CHUNK 个字符内，从后往前找最后一个标点；超出范围就在 MAX_CHUNK 处强切
        const scanUpTo = Math.min(ttsBuf.length, MAX_CHUNK);
        let lastIdx = -1;
        for (let i = scanUpTo - 1; i >= 0; i--) {
          if (isRealBoundary(i)) { lastIdx = i; break; }
        }
        if (lastIdx < 0 && ttsBuf.length > MAX_CHUNK) lastIdx = MAX_CHUNK - 1;
        if (lastIdx < 0) return;
        // 首次切要求至少 4 字符，避免"嗯，"这种没意义小段
        const minChars = firstFlushDone ? 1 : 4;
        if (lastIdx + 1 < minChars) return;
        const chunk = ttsBuf.slice(0, lastIdx + 1).trim();
        ttsBuf = ttsBuf.slice(lastIdx + 1);
        if (!chunk) return;
        enqueueSpeech(chunk, mySession);
        firstFlushDone = true;
        if (ttsBuf.length === 0) return;
      }
    };

    let reply = "";
    try {
      const res = await apiFetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          image_base64: sentImage || undefined,
        }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      const replyId = Date.now().toString();

      // Replace typing placeholder with an empty assistant bubble
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== "typing")
          .concat({
            id: replyId,
            role: "assistant",
            content: "",
            timestamp: new Date(),
          }),
      );

      // SSE 按完整事件解析：事件之间用 \n\n 分隔，单个事件可能跨多次 reader.read()
      let sseBuffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        sseBuffer += decoder.decode(value, { stream: true });
        const events = sseBuffer.split("\n\n");
        sseBuffer = events.pop() || ""; // 末尾可能是不完整的事件，留到下次拼
        for (const ev of events) {
          const line = ev.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          let data: any;
          try {
            data = JSON.parse(line.slice(6));
          } catch {
            continue; // 损坏的事件跳过，不要让一条坏事件拖死整个流
          }
          if (data.tool) {
            // Tool executed; refocus input
            setTimeout(() => textareaRef.current?.focus(), 100);
          }
          if (data.text) {
            reply += data.text;
            ttsBuf += data.text;
            flushSentences();
            setMessages((prev) =>
              prev.map((m) => (m.id === replyId ? { ...m, content: reply } : m)),
            );
          }
          if (data.card) {
            const card: CardData = {
              source: data.card.source || "网页",
              points: data.card.points || [],
              url: data.card.url,
              error: data.card.error,
              subtype: data.card.subtype,
              weather: data.card.weather,
            };
            setActiveCards((prev) => [card, ...prev].slice(0, 5));
            // 旅行规划卡：后端紧跟着会发完整口播 text，气泡不用 "搜到了" 占位覆盖
            const tip = card.subtype === "travel_plan"
              ? ""
              : card.subtype === "weather" && card.weather
              ? (() => {
                  const w = card.weather;
                  const c = (w.condition || "").toLowerCase();
                  const t = parseInt(w.currentTemp) || 20;
                  const fl = parseInt(w.feelsLike) || t;
                  const loc = card.source || "这里";
                  let msg = `${loc}现在${t}° ${weatherCN(w.condition)}，体感${fl}°。`;
                  // 未来三天概要
                  const fc = w.forecast || [];
                  if (fc.length >= 2) {
                    const parts = fc.slice(0, 3).map((f: any) => `${f.day} ${weatherCN(f.condition)} ${f.low}~${f.high}°`);
                    msg += `接下来：${parts.join("；")}。`;
                    // 预警未来三天内的坏天气
                    const hasRain = fc.slice(0, 3).some((f: any) => {
                      const fc = (f.condition || "").toLowerCase();
                      return fc.includes("rain") || fc.includes("drizzle") || fc.includes("shower") || fc.includes("thunder");
                    });
                    if (hasRain) msg += "有雨天，记得带伞。";
                  }
                  // 今日建议
                  if (c.includes("rain") || c.includes("drizzle") || c.includes("shower")) msg += "现在出门带把伞。";
                  else if (t > 32) msg += "热得够呛，注意防暑喝水。";
                  else if (t > 28) msg += "穿凉快点。";
                  else if (t < 10) msg += "挺冷的，穿厚点别着凉。";
                  else if (t < 18) msg += "微凉，带件薄外套。";
                  else if (fl < t - 3) msg += "风大比看上去冷，多穿一层。";
                  else if (fl > t + 3) msg += "闷闷的，穿透气些。";
                  msg += " 右边卡片有详情——接下来几天的都帮你看了。";
                  return msg;
                })()
              : "搜到了，看右边卡片";
            // 卡片回复替换流式文本 — 清掉旧队列；TTS 不自动播，挂 pendingTtsText 等用户点"帮我读"
            clearTtsQueue();
            ttsBuf = "";
            reply = tip;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === replyId
                  ? { ...m, content: tip, cardData: undefined, pendingTtsText: tip || undefined }
                  : m,
              ),
            );
          }
        }
      }
      textareaRef.current?.focus();
    } catch (err) {
      console.error("[chat error]", err);
      const errMsg = err instanceof Error ? err.message : String(err);
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== "typing")
          .concat({
            id: Date.now().toString(),
            role: "assistant",
            content: `[连接出错: ${errMsg}]`,
            timestamp: new Date(),
          }),
      );
    }
    // 流式 TTS 收尾：flush 尾巴 + 标记流结束 + 启动队列
    streamDoneRef.current = true;
    if (ttsBuf.trim()) enqueueSpeech(ttsBuf, mySession);
    if (!ttsPlayingRef.current) playNextInQueue();
    setIsLoading(false);
  };
  handleSendRef.current = handleSend;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Enter" || e.shiftKey) return;
    // Use ref for IME composing state — more reliable than e.nativeEvent.isComposing
    if (isComposingRef.current) return;
    e.preventDefault();
    handleSend();
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  const handlePickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      alert("只能上传图片");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert("图片不能超过 5MB");
      return;
    }
    const reader = new FileReader();
    reader.onloadend = () => {
      setPendingImage(reader.result as string);
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  // ── WebSocket peer chat (not rendered in UI) ──

  const openPeerChat = useCallback(
    (room: PeerRoom) => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setActivePeer(room);
      setPeerMessages([]);
      setPeerConnected(false);

      // WS 鉴权：浏览器没法给 WebSocket 加 header，token 走 query；dev 无 token 时退化为 dev_user
      const token = getToken();
      const wsAuth = token
        ? `token=${encodeURIComponent(token)}`
        : `dev_user=${encodeURIComponent(readStoredUsername() || username)}`;
      const ws = new WebSocket(`${WS_BASE}/ws/peer/${room.room_id}?${wsAuth}`);
      wsRef.current = ws;

      ws.onopen = () => setPeerConnected(true);
      ws.onclose = () => setPeerConnected(false);
      ws.onerror = () => setPeerConnected(false);
      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === "history") {
          setPeerMessages(data.messages || []);
        } else if (data.type === "message") {
          setPeerMessages((prev) => [...prev, data]);
        }
      };
    },
    [username],
  );

  const sendPeerMessage = () => {
    const text = peerInput.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ content: text }));
    setPeerInput("");
  };

  const handlePeerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendPeerMessage();
    }
  };

  // ── render ──

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      <TopBar />

      <div className="flex flex-1 min-h-0 relative">
        {/* ── sidebar 64px ── */}
        <Sidebar
          onHistoryClick={() => setShowHistory(!showHistory)}
          onPlazaClick={() => setPlazaOpen((o) => !o)}
          plazaActive={plazaOpen}
          onMatchClick={() => setMatchOpen((o) => !o)}
          matchActive={matchOpen}
        />

        {/* ── history slide-out drawer ── */}
        {showHistory && (
        <div
          className="absolute left-16 top-0 bottom-0 w-64 z-50 flex flex-col bg-background/98 backdrop-blur-xl animate-in slide-in-from-left duration-300"
          style={{
            boxShadow: "8px 0 40px rgba(0,0,0,0.5), 2px 0 12px rgba(0,0,0,0.3), inset -1px 0 0 rgba(255,255,255,0.04)",
            borderRight: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <>
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <div className="flex items-center gap-1.5">
                  <Clock size={12} className="text-muted-foreground" />
                  <span className="text-xs font-semibold text-muted-foreground tracking-wide">历史记录</span>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={handleClearHistory} className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-destructive transition-colors" title="清空所有历史记录">
                    <Trash2 size={11} />清空
                  </button>
                  <button onClick={() => setShowHistory(false)} className="text-muted-foreground hover:text-foreground">
                    <X size={14} />
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto py-3 px-3">
                <div className="space-y-1">
                  {groupByDate(messages).map(([date, msgs]) => {
                    const isOpen = !collapsed[date];
                    return (
                      <div key={date}>
                        <button onClick={() => setCollapsed((prev) => ({ ...prev, [date]: !prev[date] }))} className="w-full flex items-center gap-2 px-2 py-2 rounded-xl hover:bg-secondary transition-all text-left">
                          {isOpen ? <ChevronDown size={13} className="text-muted-foreground shrink-0" /> : <ChevronRight size={13} className="text-muted-foreground shrink-0" />}
                          <span className="text-[11px] font-semibold text-muted-foreground truncate">{date}</span>
                          <span className="text-[10px] text-muted-foreground/50 ml-auto shrink-0">{msgs.length} 条</span>
                        </button>
                        {isOpen && (
                          <div className="ml-5 border-l border-border pl-3 pb-2 space-y-2.5 mt-1">
                            {msgs.map((msg, idx2) => (
                              <div key={`${msg.id}-${idx2}`} className="flex flex-col gap-0.5">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-[10px] font-medium text-muted-foreground">{msg.role === "assistant" ? "菲欧娜" : "我"}</span>
                                  <span className="text-[9px] text-muted-foreground/50">{msg.timestamp.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                                </div>
                                <p className="text-[11px] text-foreground/70 leading-relaxed line-clamp-2">{msg.content}</p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="border-t border-border px-4 py-2.5">
                <button onClick={() => window.open(`/history?user=${encodeURIComponent(username)}`, "_blank")} className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors w-full" title="查看完整历史记录">
                  <Clock size={11} />查看完整历史记录
                </button>
            </div>
          </>
        </div>
        )}

        {/* ── subtle backdrop behind drawer (does NOT cover sidebar) */}
        {showHistory && (
          <div className="absolute left-16 top-0 bottom-0 right-0 z-40 bg-black/20 backdrop-blur-sm transition-opacity" onClick={() => setShowHistory(false)} />
        )}

        {/* ── main content: flex-col flex-1 ── */}
        <div className="flex flex-col flex-1 min-w-0">
          {/* header — single column: Fiona + new chat + voice toggle */}
          <header className="hud-panel hud-corners flex shrink-0" style={{ borderRadius: 0, borderTop: "none", borderLeft: "none", borderRight: "none" }}>
            <div className="flex-1 px-5 py-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <div className="hud-avatar-ring">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center"
                    style={{
                      background: "radial-gradient(circle at 30% 30%, rgba(0,212,255,0.6), rgba(0,90,140,0.95))",
                      boxShadow: "inset 0 0 8px rgba(0,212,255,0.55), 0 0 12px rgba(0,212,255,0.4)",
                    }}
                  >
                    <span className="text-[#e0f6ff] text-xs font-semibold tracking-wider">菲</span>
                  </div>
                </div>
                <div className="leading-tight">
                  <p className="text-sm font-semibold tracking-wider" style={{ color: "var(--hud-cyan)", textShadow: "0 0 6px var(--hud-cyan-glow)" }}>F·I·O·N·A</p>
                  <p className="hud-label flex items-center gap-1.5 mt-0.5">
                    <span className="hud-pulse" />
                    <span>ONLINE · CH.A1</span>
                  </p>
                </div>
                {/* new chat button */}
                <button
                  onClick={handleNewChat}
                  className="hud-btn flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium"
                  style={{ clipPath: "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))" }}
                  title="新建聊天"
                >
                  <span className="hud-label">NEW</span>
                  <span style={{ color: "var(--hud-cyan)", textShadow: "0 0 6px var(--hud-cyan-glow)", lineHeight: 1, fontSize: 14 }}>+</span>
                </button>
              </div>
              <div className="flex items-center gap-2">
                {/* voice toggle */}
                <button
                  onClick={() => setVoiceOn(!voiceOn)}
                  className={cn(
                    "hud-btn flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium",
                    voiceOn && "hud-btn-active"
                  )}
                  style={{ clipPath: "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))" }}
                >
                  {voiceOn ? <Volume2 size={13} /> : <VolumeX size={13} />}
                  <span className="hud-label" style={voiceOn ? { color: "inherit", textShadow: "none" } : undefined}>{voiceOn ? "AUDIO ON" : "AUDIO OFF"}</span>
                </button>
                {/* hands-free toggle */}
                <button
                  onClick={() => {
                    const next = !handsFree;
                    setHandsFree(next);
                    if (next) setVoiceOn(true);
                  }}
                  className={cn(
                    "hud-btn flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium",
                    handsFree && "hud-btn-active"
                  )}
                  style={{ clipPath: "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))" }}
                  title="免提：菲欧娜说完自动开麦，你停顿 1.5 秒后自动发"
                >
                  <span className="hud-label" style={handsFree ? { color: "inherit", textShadow: "none" } : undefined}>{handsFree ? "HANDS·FREE" : "HANDS"}</span>
                </button>
              </div>
            </div>
          </header>

          {/* body: 三块浮起玻璃卡片 + 后景星空 */}
          <div className="flex flex-1 min-h-0 gap-4 p-4 relative overflow-hidden">
            <StarField />
            {/* left column: HUD 能量球 / 语音端口 */}
            <div className="w-1/4 hud-card-float flex flex-col overflow-y-auto items-center relative pt-10 pb-6 z-10">
              {/* 顶部 HUD 标签 */}
              <div className="absolute top-4 left-4 right-4 flex items-center justify-between">
                <span className="hud-label">VOICE PORT</span>
                <span className="hud-label opacity-60">CH.A1 · 16K</span>
              </div>

              {/* 上：动态能量球（不停形变 + 轨道粒子） */}
              <div className="mt-2">
                <HudOrb recording={recording} size={240} />
              </div>

              {/* 下：录音按钮 + 状态文字 */}
              <div className="mt-auto flex flex-col items-center gap-3">
                <button
                  onPointerDown={(e) => { e.preventDefault(); (e.target as HTMLElement).setPointerCapture(e.pointerId); setRecording(true); }}
                  onPointerUp={(e) => { e.preventDefault(); (e.target as HTMLElement).releasePointerCapture(e.pointerId); setRecording(false); }}
                  className={cn(
                    "hud-btn flex items-center gap-2 px-5 py-2 text-xs font-medium",
                    recording && "hud-btn-active"
                  )}
                  style={{ clipPath: "polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px))" }}
                >
                  <Mic size={14} />
                  <span className="hud-label" style={recording ? { color: "inherit", textShadow: "none" } : undefined}>
                    {recording ? "TRANSMIT" : "HOLD · TALK"}
                  </span>
                </button>

                <div className="hud-label text-[10px]" style={{ color: recording ? "#ff6680" : "var(--hud-cyan)", letterSpacing: "0.18em" }}>
                  {recording ? "● LISTENING" : "▶ READY"}
                </div>

                {/* 录音波形 / 待机心电图 */}
                {recording ? (
                  <div className="flex gap-1 h-5 items-end">
                    {[0, 1, 2, 3, 4, 5, 6].map((i) => (
                      <div
                        key={i}
                        className="w-[3px] rounded-sm wave-bar"
                        style={{
                          height: `${10 + Math.random() * 18}px`,
                          background: "linear-gradient(180deg, #00d4ff, #ff6680)",
                          boxShadow: "0 0 6px rgba(0,212,255,0.65)",
                          animationDelay: `${i * 0.08}s`,
                          animationDuration: `${0.5 + Math.random() * 0.3}s`,
                        }}
                      />
                    ))}
                  </div>
                ) : (
                  <svg className="hud-ekg" width="140" height="20" viewBox="0 0 140 20">
                    <path d="M0,10 L25,10 L30,3 L34,17 L39,10 L65,10 L70,6 L74,14 L78,10 L140,10" />
                  </svg>
                )}

                {voiceText && (
                  <p className="text-xs text-center px-4 leading-relaxed" style={{ color: "var(--hud-cyan)", textShadow: "0 0 4px var(--hud-cyan-glow)" }}>
                    {voiceText}
                  </p>
                )}
              </div>

              {/* 底部 HUD 元数据 */}
              <div className="absolute bottom-4 left-4 right-4 flex justify-between hud-label text-[9px] opacity-60">
                <span>SR · 16000Hz</span>
                <span className="hud-flicker">CODEC · OPUS</span>
              </div>
            </div>

            {/* chat slot — 卷帘门：里面的卡片可向下滑出 */}
            <div
              className="w-1/2 min-h-0 relative z-10 overflow-hidden"
              style={{ contain: "layout paint" }}  /* 严格 layout/paint 隔离，防卷帘 transform 动画过程中视觉跳出父框 */
            >
            <div
              className="absolute inset-0 hud-card-float flex flex-col min-h-0"
              style={{
                transform: chatCollapsed ? "translateY(calc(100% - 28px))" : "translateY(0)",
                transition: "transform 600ms cubic-bezier(.22,.61,.36,1)",
                willChange: "transform",
                maxHeight: "100%",  /* 强制不超过父容器，避免子内容撑大让 absolute inset-0 失效 */
              }}
            >
              {/* 卷帘把手条 —— 收起时唯一可见的部分，点击展开/收起 */}
              <div
                className="shutter-handle shrink-0"
                onClick={() => setChatCollapsed((v) => !v)}
                title={chatCollapsed ? "展开聊天" : "卷起聊天 · 露出星空"}
              >
                <span className="chev">{chatCollapsed ? "▲" : "▼"}</span>
                <div className="shutter-handle-grip" />
                <span className="chev">{chatCollapsed ? "EXPAND" : "COLLAPSE"}</span>
              </div>
              <div className="flex-1 overflow-y-auto py-4 px-6 space-y-4 min-h-0">
                {messages.filter((m) => m.timestamp >= sessionStart).length === 0 && (
                  <p className="text-xs text-muted-foreground/50 text-center pt-8">新对话</p>
                )}
                {messages.filter((m) => m.timestamp >= sessionStart).map((msg) => (
                  <ChatBubble key={msg.id} message={msg} onDelete={handleDeleteMessage} onConfirmTts={handleConfirmTts} onDeclineTts={handleDeclineTts} />
                ))}
                <div ref={bottomRef} />
              </div>
              {/* inline input */}
              <div className="border-t border-border px-3 py-2 shrink-0">
                <div className="bg-secondary rounded-2xl px-3 py-1.5 flex items-end gap-2">
                  {pendingImage && (
                    <div className="relative inline-block w-fit pt-1">
                      <img src={pendingImage} alt="待发送" className="rounded-xl max-h-20 max-w-[120px] object-cover border border-border" />
                      <button onClick={() => setPendingImage(null)} className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-background border border-border flex items-center justify-center hover:bg-destructive hover:text-white transition-colors">
                        <X size={10} />
                      </button>
                    </div>
                  )}
                  <textarea ref={textareaRef} value={input} onChange={handleInput} onKeyDown={handleKeyDown}
                    onCompositionStart={() => { isComposingRef.current = true; }}
                    onCompositionEnd={() => { isComposingRef.current = false; }}
                    placeholder={pendingImage ? "说点什么…（可选）" : "说点什么…"} rows={1}
                    className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none py-1 leading-relaxed max-h-[80px]"
                  />
                  <div className="flex items-center gap-0.5 pb-0.5">
                    <input ref={fileInputRef} type="file" accept="image/*" onChange={handlePickImage} className="hidden" />
                    <button type="button" onClick={() => fileInputRef.current?.click()} className="w-6 h-6 flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground transition-colors" title="发送图片">
                      <ImagePlus size={14} />
                    </button>
                    <button type="button" onClick={toggleInlineVoice}
                      className={cn("w-6 h-6 flex items-center justify-center rounded-full transition-colors",
                        inlineRecording ? "text-red-400 bg-red-500/10" : "text-muted-foreground hover:text-foreground")}
                      title="语音转文字">
                      <Mic size={14} />
                    </button>
                    <button onClick={() => handleSend()} disabled={!input.trim() && !pendingImage}
                      className={cn("w-7 h-7 flex items-center justify-center rounded-full transition-all", input.trim() || pendingImage ? "bg-primary text-white hover:opacity-90 active:scale-95" : "text-muted-foreground cursor-not-allowed")}
                    ><Send size={14} /></button>
                  </div>
                </div>
                <p className="text-[9px] text-muted-foreground text-center mt-1">Enter 发送 · Shift+Enter 换行</p>
              </div>
            </div>
            </div>

            {/* right column: card panel + ambient HUD */}
            <div className="w-1/4 hud-card-float flex flex-col min-h-0 relative z-10">
              <div className="px-4 pt-4 pb-2 flex items-center justify-between" style={{ borderBottom: "1px solid rgba(0,212,255,0.15)" }}>
                <span className="hud-label flex items-center gap-1.5">
                  <span className="hud-pulse" style={{ width: 6, height: 6 }} />
                  DATA STREAM
                </span>
                <span className="hud-label opacity-60">{activeCards.length.toString().padStart(2, "0")} / 05</span>
              </div>
              <div className="flex-1 overflow-y-auto p-4 relative">
                {activeCards.length > 0 ? (
                  <div className="max-w-[260px] mx-auto flex flex-col items-center">
                    {/* SIMPLE CSS animation — NO template literals with weird quotes */}
                    <style>{'@keyframes cardSlideIn{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}'}</style>
                    {activeCards.map((card, idx) => {
                      const isNewest = idx === 0;
                      const isHovered = hoveredCard === idx;
                      return (
                        <div
                          key={`cs-${idx}-${card.source}-${card.subtype}`}
                          className="w-full cursor-pointer"
                          style={{
                            marginTop: isHovered ? 12 : idx === 0 ? 0 : -24,
                            zIndex: isHovered ? 200 : 100 - idx,
                            position: 'relative',
                            transition: 'margin 0.3s ease, z-index 0s',
                            animation: isNewest ? 'cardSlideIn 0.5s cubic-bezier(0.16,1,0.3,1) both' : undefined,
                          }}
                          onMouseEnter={() => idx > 0 && setHoveredCard(idx)}
                          onMouseLeave={() => setHoveredCard(null)}
                          onClick={() => setEnlargedCard(card)}
                          title="点击放大"
                        >
                          {/* X button on newest or hovered card */}
                          {(isNewest || isHovered) && (
                            <button onClick={(e) => { e.stopPropagation(); handleDismissCard(idx); }}
                              className="absolute -top-1 -right-1 z-20 w-5 h-5 flex items-center justify-center rounded-full bg-background/80 border border-border hover:bg-destructive hover:text-white transition-colors">
                              <X size={10} />
                            </button>
                          )}

                          {card.subtype === 'weather' && card.weather ? (() => {
                            const theme = getWeatherTheme(card.weather.condition);
                            return (
                            <div className="rounded-xl overflow-hidden"
                              style={{
                                background: theme.bg,
                                color: theme.text,
                                boxShadow: idx === 0
                                  ? `0 8px 32px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.4), 0 0 0 1px ${theme.glow}, inset 0 1px 0 ${theme.glow}, inset 0 -1px 0 rgba(0,0,0,0.3)`
                                  : `0 2px 8px rgba(0,0,0,0.3), 0 0 0 1px ${theme.glow}`,
                                border: `1px solid ${theme.glow}`,
                              }}
                            >
                              {idx > 0 && !isHovered ? (
                                <div className="px-3 py-1.5 flex items-center gap-3">
                                  <span style={{fontSize:11,color:theme.sub,opacity:0.7,fontWeight:500}}>{card.weather.location}</span>
                                  <span style={{fontSize:18,fontWeight:300,color:theme.accent}}>{card.weather.currentTemp + '°'}</span>
                                  <span style={{fontSize:10,color:theme.sub,opacity:0.6}}>{weatherCN(card.weather.condition)}</span>
                                </div>
                              ) : (
                                /* FULL weather card: location, large temp, feels like, humidity/wind/vis, divider, forecast */
                                <>
                                  <div className="px-3 pt-3 pb-2">
                                    <div style={{fontSize:10,color:theme.sub}}>{card.weather.location}</div>
                                    <div style={{fontSize:30,fontWeight:300,color:theme.accent,marginTop:4}}>{card.weather.currentTemp + '°'}</div>
                                    <div style={{fontSize:10,color:theme.sub,opacity:0.8,marginTop:2}}>体感 {card.weather.feelsLike + '°'} · {weatherCN(card.weather.condition)}</div>
                                  </div>
                                  <div className="px-3 pb-3 flex gap-3" style={{fontSize:10,color:theme.sub,opacity:0.6}}>
                                    <span>💧 {card.weather.humidity + '%'}</span>
                                    <span>🌬 {card.weather.windSpeed + 'km/h'}</span>
                                    <span>👁 {card.weather.visibility + 'km'}</span>
                                  </div>
                                  <div className="mx-3" style={{height:1,background:theme.glow,opacity:0.3}} />
                                  <div className="px-2 py-2">
                                    {card.weather.forecast.map((f: any, i: number) => (
                                      <div key={i} className="flex items-center px-1 py-1">
                                        <span style={{fontSize:10,color:theme.sub,width:40,flexShrink:0}}>{f.day}</span>
                                        {f.icon && <img src={f.icon} alt={f.condition} className="w-4 h-4 mx-1 opacity-60" />}
                                        <span style={{fontSize:10,color:theme.sub,opacity:0.6,flex:1}}>{f.condition}</span>
                                        <span className="tabular-nums" style={{fontSize:10,color:theme.accent}}>
                                          <span style={{opacity:0.5}}>{f.low + '°'}</span> <span>{f.high + '°'}</span>
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                </>
                              )}
                            </div>
                            );
                          })() : card.points && card.points.length > 0 ? (
                            <div className="rounded-xl"
                              style={{
                                background: 'linear-gradient(160deg, #0d1117 0%, #161b22 50%, #0d1117 100%)',
                                boxShadow: idx === 0 ? '0 6px 24px rgba(0,0,0,0.5), 0 1px 4px rgba(0,0,0,0.4), 0 0 0 1px rgba(56,189,248,0.15)' : '0 2px 6px rgba(0,0,0,0.3), 0 0 0 1px rgba(56,189,248,0.08)',
                                border: '1px solid rgba(56,189,248,0.15)',
                              }}
                            >
                              {idx > 0 && !isHovered ? (
                                <div className="px-3 py-1.5 flex items-center gap-2 cursor-pointer" onClick={() => handleDismissCard(idx)}>
                                  <Globe size={11} style={{color:'rgba(56,189,248,0.5)'}} />
                                  <span style={{fontSize:11,color:'rgba(125,211,252,0.6)',fontWeight:500}}>{card.source}</span>
                                </div>
                              ) : (
                                <div className="p-3">
                                  <div className="flex items-center gap-2 mb-2">
                                    <Globe size={11} style={{color:'rgba(56,189,248,0.6)'}} />
                                    <span style={{fontSize:10,color:'rgba(125,211,252,0.5)',fontWeight:500}}>{card.source}</span>
                                  </div>
                                  <ul className="space-y-1.5">
                                    {card.points.map((point: string, i: number) => (
                                      <li key={i} style={{fontSize:11,display:'flex',gap:6,color:'rgba(186,230,253,0.7)'}}>
                                        <span style={{color:'rgba(56,189,248,0.4)',flexShrink:0,marginTop:2}}>•</span>
                                        <span>{point}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <AmbientHUD username={username} messageCount={messages.length} />
                )}
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* 我的世界 抽屉 — 从右侧滑出，覆盖 2/3 聊天区；不卸载 iframe，重开秒回原状态 */}
      <div
        className="fixed z-[55] flex flex-col"
        style={{
          top: 0,
          bottom: 0,
          right: 0,
          width: "calc((100vw - 64px) * 2 / 3)",
          background: "linear-gradient(180deg, rgba(4,10,22,0.96) 0%, rgba(2,6,18,0.98) 100%)",
          borderLeft: "1px solid rgba(0,212,255,0.18)",
          boxShadow: plazaOpen ? "-18px 0 48px rgba(0,0,0,0.55), inset 1px 0 0 rgba(0,212,255,0.08)" : "none",
          transform: plazaOpen ? "translateX(0)" : "translateX(105%)",
          transition: "transform 360ms cubic-bezier(.22,.61,.36,1)",
          willChange: "transform",
        }}
      >
        <div
          className="flex items-center justify-between px-4 py-2 shrink-0"
          style={{
            borderBottom: "1px solid rgba(0,212,255,0.15)",
            background: "linear-gradient(180deg, rgba(0,212,255,0.04) 0%, transparent 100%)",
          }}
        >
          <span className="hud-label text-[11px] tracking-wider" style={{ color: "rgba(0,212,255,0.85)" }}>我的世界</span>
          <button
            onClick={() => setPlazaOpen(false)}
            className="w-6 h-6 flex items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
            title="收起"
          >
            <X size={14} />
          </button>
        </div>
        <iframe src="/plaza?embed=1" className="flex-1 w-full border-0" />
      </div>

      {/* 匹配 抽屉 — 同样从右侧滑出，覆盖 2/3 聊天区 */}
      <div
        className="fixed z-[55] flex flex-col"
        style={{
          top: 0,
          bottom: 0,
          right: 0,
          width: "calc((100vw - 64px) * 2 / 3)",
          background: "linear-gradient(180deg, rgba(4,10,22,0.96) 0%, rgba(2,6,18,0.98) 100%)",
          borderLeft: "1px solid rgba(0,212,255,0.18)",
          boxShadow: matchOpen ? "-18px 0 48px rgba(0,0,0,0.55), inset 1px 0 0 rgba(0,212,255,0.08)" : "none",
          transform: matchOpen ? "translateX(0)" : "translateX(105%)",
          transition: "transform 360ms cubic-bezier(.22,.61,.36,1)",
          willChange: "transform",
        }}
      >
        <div
          className="flex items-center justify-between px-4 py-2 shrink-0"
          style={{
            borderBottom: "1px solid rgba(0,212,255,0.15)",
            background: "linear-gradient(180deg, rgba(0,212,255,0.04) 0%, transparent 100%)",
          }}
        >
          <span className="hud-label text-[11px] tracking-wider" style={{ color: "rgba(0,212,255,0.85)" }}>匹配</span>
          <button
            onClick={() => setMatchOpen(false)}
            className="w-6 h-6 flex items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
            title="收起"
          >
            <X size={14} />
          </button>
        </div>
        <iframe src="/match?embed=1" className="flex-1 w-full border-0" />
      </div>

      {/* 卡片放大层 — 点击卡片或背景关闭 */}
      {enlargedCard && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center"
          style={{ background: "rgba(2,6,18,0.78)", backdropFilter: "blur(6px)" }}
          onClick={() => setEnlargedCard(null)}
        >
          <div
            className="topic-drawer-in relative"
            style={{ maxWidth: 760, width: "92%", maxHeight: "88vh" }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setEnlargedCard(null)}
              className="absolute -top-3 -right-3 z-10 w-7 h-7 flex items-center justify-center rounded-full bg-background border border-border hover:bg-destructive hover:text-white transition-colors"
              title="缩小"
            >
              <X size={14} />
            </button>

            {enlargedCard.subtype === "weather" && enlargedCard.weather ? (() => {
              const w = enlargedCard.weather;
              const theme = getWeatherTheme(w.condition);
              return (
                <div className="rounded-2xl overflow-hidden"
                  style={{ background: theme.bg, color: theme.text, border: `1px solid ${theme.glow}`, boxShadow: `0 16px 48px rgba(0,0,0,0.6), inset 0 1px 0 ${theme.glow}` }}>
                  <div className="px-6 pt-6 pb-3">
                    <div style={{ fontSize: 14, color: theme.sub }}>{w.location}</div>
                    <div style={{ fontSize: 72, fontWeight: 200, color: theme.accent, marginTop: 8, lineHeight: 1 }}>{w.currentTemp}°</div>
                    <div style={{ fontSize: 14, color: theme.sub, opacity: 0.85, marginTop: 6 }}>体感 {w.feelsLike}° · {weatherCN(w.condition)}</div>
                  </div>
                  <div className="px-6 pb-5 flex gap-6" style={{ fontSize: 13, color: theme.sub, opacity: 0.75 }}>
                    <span>💧 {w.humidity}%</span>
                    <span>🌬 {w.windSpeed} km/h</span>
                    <span>👁 {w.visibility} km</span>
                  </div>
                  <div className="mx-6" style={{ height: 1, background: theme.glow, opacity: 0.35 }} />
                  <div className="px-4 py-3">
                    {w.forecast.map((f: any, i: number) => (
                      <div key={i} className="flex items-center px-2 py-2">
                        <span style={{ fontSize: 13, color: theme.sub, width: 56 }}>{f.day}</span>
                        {f.icon && <img src={f.icon} alt={f.condition} className="w-6 h-6 mx-2 opacity-75" />}
                        <span style={{ fontSize: 13, color: theme.sub, opacity: 0.7, flex: 1 }}>{f.condition}</span>
                        <span className="tabular-nums" style={{ fontSize: 14, color: theme.accent }}>
                          <span style={{ opacity: 0.5 }}>{f.low}°</span> <span className="ml-1">{f.high}°</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })() : (
              <div className="hud-card-float rounded-2xl px-8 py-7 bg-background/95 flex flex-col" style={{ maxHeight: "88vh" }}>
                <div className="hud-label text-xs opacity-75 mb-4 shrink-0 tracking-wider">{enlargedCard.source || "卡片"}</div>
                <div className="flex-1 overflow-y-auto pr-2 -mr-2">
                  {enlargedCard.points && enlargedCard.points.length > 0 ? (
                    <ul className="space-y-4 text-[15px] leading-relaxed">
                      {enlargedCard.points.map((p, i) => (
                        <li key={i} className="flex gap-3">
                          <span className="text-primary/70 shrink-0 mt-0.5">▸</span>
                          <span>{p}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-base opacity-70">无可展示内容</p>
                  )}
                </div>
                {enlargedCard.url && (
                  <a href={enlargedCard.url} target="_blank" rel="noopener noreferrer"
                    className="block mt-5 pt-4 border-t border-border/40 text-sm text-primary hover:underline truncate shrink-0">
                    {enlargedCard.url}
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
