"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import ChatBubble, { type Message, type CardData, type WeatherForecastDay, type ImageAspectRatio, type ImageGenerationRetry } from "@/components/ChatBubble";
import GeneratedImage from "@/components/GeneratedImage";
import ConversationPicker from "@/components/ConversationPicker";
import ChatScrollArea, { type ChatScrollHandle } from "@/components/ChatScrollArea";
import Signal from "@/components/Signal";
import MyAgentWorkspace from "@/components/MyAgentWorkspace";
import AgentExchangeWorkspace from "@/components/AgentExchangeWorkspace";
import { useConversations } from "@/lib/useConversations";
import {
  Send, Mic, Volume2, VolumeX, ChevronDown, ChevronRight,
  Trash2, ImagePlus, X, Clock, Sparkles, PencilLine, ArrowLeft, ArrowRight, PanelLeft, AudioLines,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch, getUsername as readStoredUsername } from "@/lib/auth";
import { generatedImagePath, referenceImagePath, referencePreviewUrl, isLocalReferenceDataUrl, type ReferenceImageInput } from "@/lib/generatedImages";
import { readLocalReferenceImage, MAX_REFERENCE_FILE_BYTES, REFERENCE_FILE_TYPES } from "@/lib/localReferenceImages";

import { API_BASE as API, WS_BASE } from "@/lib/config";

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

interface ChatStreamEvent {
  type?: "reference_images";
  reference_image_paths?: string[];
  tool?: unknown;
  text?: string;
  card?: CardData;
  error?: string;
  done?: boolean;
  status?: "generating_image" | "editing_image";
  message?: string;
  generated_image?: { image_path: string; model: string; width: number; height: number; reference_image_paths?: string[]; reference_image_path?: string };
}

interface ImageReferenceSelection {
  images: { id: string; source: ReferenceImageInput }[];
  owner: string;
  conversationId: string;
}

function imageAspectRatioFromPrompt(prompt: string): ImageAspectRatio {
  // Match backend intent_router.image_aspect_ratio so retries preserve natural-language ratios.
  if (/9\s*[:：]\s*16|竖[版屏幅]/.test(prompt)) return "9:16";
  if (/16\s*[:：]\s*9|横[版屏幅]/.test(prompt)) return "16:9";
  return "1:1";
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
      className="glass-card w-64 px-4 py-3"
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
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[6px] bg-secondary">
          <Sparkles size={13} style={{ color: "var(--amber-ink)" }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="font-semibold text-xs text-foreground/60">神秘好友</span>
            <span className="tag tag-amber">
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
          className="text-[10px] px-2.5 py-1 rounded-full bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
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

// ── main page ──

export default function ChatPage() {
  // ---- core chat state ----
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  // 右侧面板互斥，分身管理也在当前聊天页内打开。
  type DrawerName = "agent" | "exchange" | "plaza" | "settings" | null;
  const [drawer, setDrawer] = useState<DrawerName>(null);
  const [worldTab, setWorldTab] = useState<"plaza" | "match">("plaza");
  const [settingsTab, setSettingsTab] = useState<"settings" | "profile">("settings");
  const [conversationPickerOpen, setConversationPickerOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [strawberryBalance, setStrawberryBalance] = useState<number | null>(null);
  const conversationListButtonRef = useRef<HTMLButtonElement>(null);
  const conversationDialogRef = useRef<HTMLDivElement>(null);
  const restoreConversationFocusRef = useRef(true);
  const historyCloseButtonRef = useRef<HTMLButtonElement>(null);
  const restoreHistoryFocusRef = useRef(false);
  const closeMobilePanelsFromNavigation = () => {
    restoreConversationFocusRef.current = false;
    restoreHistoryFocusRef.current = false;
    setConversationPickerOpen(false);
    if (window.matchMedia("(width < 768px)").matches) setShowHistory(false);
  };
  const toggleDrawer = (name: Exclude<DrawerName, null>) => {
    closeMobilePanelsFromNavigation();
    setDrawer((d) => (d === name ? null : name));
  };
  const closeDrawer = () => {
    setDrawer(null);
    closeMobilePanelsFromNavigation();
  };
  const focusVisibleDrawerTrigger = (id: string) => {
    Array.from(document.querySelectorAll<HTMLButtonElement>(`button[aria-controls="${id}"]`))
      .find(button => button.getClientRects().length > 0)?.focus();
  };
  const agentOpen     = drawer === "agent";
  const agentPanelRef = useRef<HTMLElement>(null);
  const exchangeOpen = drawer === "exchange";
  const exchangePanelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (agentOpen) agentPanelRef.current?.focus();
    if (exchangeOpen) exchangePanelRef.current?.focus();
  }, [agentOpen, exchangeOpen]);
  const plazaOpen     = drawer === "plaza";
  const settingsOpen  = drawer === "settings";
  const anyDrawerOpen = drawer !== null;
  useEffect(() => {
    if (!conversationPickerOpen) return;
    const dialog = conversationDialogRef.current;
    const trigger = conversationListButtonRef.current;
    if (!dialog) return;
    const mobileBreakpoint = window.matchMedia("(width < 768px)");
    const onBreakpointChange = () => {
      if (mobileBreakpoint.matches) return;
      restoreConversationFocusRef.current = false;
      setConversationPickerOpen(false);
    };
    mobileBreakpoint.addEventListener("change", onBreakpointChange);
    if (!mobileBreakpoint.matches) {
      onBreakpointChange();
      return () => mobileBreakpoint.removeEventListener("change", onBreakpointChange);
    }
    (dialog.querySelector<HTMLElement>('button:not([disabled])') ?? dialog).focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setConversationPickerOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'));
      if (!focusable.length) { event.preventDefault(); dialog.focus(); return; }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      mobileBreakpoint.removeEventListener("change", onBreakpointChange);
      if (restoreConversationFocusRef.current) trigger?.focus();
    };
  }, [conversationPickerOpen]);
  useEffect(() => {
    if (!showHistory || !restoreHistoryFocusRef.current) return;
    const trigger = conversationListButtonRef.current;
    historyCloseButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !window.matchMedia("(width < 768px)").matches) return;
      event.preventDefault();
      setShowHistory(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (restoreHistoryFocusRef.current && window.matchMedia("(width < 768px)").matches) {
        trigger?.focus();
      }
      restoreHistoryFocusRef.current = false;
    };
  }, [showHistory]);
  const [username, setUsername] = useState("默认用户");
  const [hydrated, setHydrated] = useState(false);
  const {
    agent, conversations, current: currentConversation, messages, setMessages,
    loading: conversationLoading, error: conversationError, reload: reloadConversations,
    hasMoreMessages, updateAgent,
    createConversation, selectConversation, deleteConversation, refreshList, getSelectionVersion,
  } = useConversations(username, hydrated);
  const [allUsers, setAllUsers] = useState<string[]>([]);
  const [voiceOn, setVoiceOn] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const [recording, setRecording] = useState(false);
  const [inlineRecording, setInlineRecording] = useState(false);
  const [voiceText, setVoiceText] = useState("");
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [imageMode, setImageMode] = useState(false);
  const [referenceImages, setReferenceImages] = useState<ImageReferenceSelection | null>(null);
  const [aspectRatio, setAspectRatio] = useState<ImageAspectRatio>("1:1");
  const [isReadingImage, setIsReadingImage] = useState(false);
  const [isReadingReferences, setIsReadingReferences] = useState(false);
  const [referenceUploadError, setReferenceUploadError] = useState("");
  const imageReaderRef = useRef<FileReader | null>(null);
  const referenceReadControllerRef = useRef<AbortController | null>(null);
  const chatScrollRef = useRef<ChatScrollHandle>(null);
  const composerRef = useRef<HTMLElement>(null);
  const [composerHeight, setComposerHeight] = useState(172);
  const peerWasNearBottomRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const focusChatInput = useCallback(() => {
    // Check the current DOM state: the stream may have started before the panel opened.
    if (agentPanelRef.current?.getAttribute("aria-hidden") !== "false" && exchangePanelRef.current?.getAttribute("aria-hidden") !== "false") {
      textareaRef.current?.focus();
    }
  }, []);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const referenceFileInputRef = useRef<HTMLInputElement>(null);
  const isComposingRef = useRef(false);
  const handleSendRef = useRef<(text?: string) => Promise<void>>(async () => {});
  const handsFreeRef = useRef(false);
  const asrSessionRef = useRef(0);
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);
  const ttsPreloadRef = useRef<HTMLAudioElement | null>(null);  // 预取下一句音频，消除句间空隙
  const ttsQueueRef = useRef<string[]>([]);
  const ttsPlayingRef = useRef(false);
  const playNextInQueueRef = useRef<() => void>(() => {});
  const ttsSessionRef = useRef(0);
  const streamDoneRef = useRef(true);
  const synthRef = useRef<SpeechSynthesis | null>(null);
  const nlsWsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);

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

  useEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    const update = () => setComposerHeight(Math.ceil(el.getBoundingClientRect().height));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Keep the account label in sync with same-origin settings and other tabs.
  useEffect(() => {
    const hydrate = () => {
      setUsername(readStoredUsername() || "默认用户");
      setHydrated(true);
    };
    const onStorage = (event: StorageEvent) => {
      if (!event.key || event.key === "fiona_user") hydrate();
    };
    hydrate();
    window.addEventListener("storage", onStorage);
    window.addEventListener("fiona-user-changed", hydrate);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("fiona-user-changed", hydrate);
    };
  }, []);

  // Load all users
  useEffect(() => {
    // /users 仅 DEV_MODE 开放；prod 返 404，安静忽略
    apiFetch(`${API}/users`)
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
    const up = () => {
      asrSessionRef.current += 1;
      setRecording(false);
    };
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
    const sessionId = ++asrSessionRef.current;
    const selectionVersion = getSelectionVersion();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (asrSessionRef.current !== sessionId) {
        stream.getTracks().forEach(t => t.stop());
        return;
      }
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      mediaRecorderRef2.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        if (selectionVersion !== getSelectionVersion()) return;
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
          const res = await apiFetch(`${API}/asr/recognize`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ audio: base64, format: "opus", sample_rate: 16000 }),
          });
          const data = await res.json();
          if (selectionVersion !== getSelectionVersion()) return;
          if (data.text) { setVoiceText(""); handleSendRef.current(data.text); }
          else { setVoiceText(data.error || "未识别到语音"); setTimeout(() => setVoiceText(""), 2000); }
        } catch {
          if (selectionVersion !== getSelectionVersion()) return;
          setVoiceText("识别失败"); setTimeout(() => setVoiceText(""), 2000);
        }
      };
      mr.start();
    } catch {
      if (asrSessionRef.current !== sessionId) return;
      setVoiceText("麦克风未授权");
      setTimeout(() => {
        if (asrSessionRef.current !== sessionId) return;
        asrSessionRef.current += 1;
        setRecording(false);
      }, 1000);
    }
  }, [getSelectionVersion]);

  const stopNlsAsr = useCallback(() => {
    asrSessionRef.current += 1;
    const mr = mediaRecorderRef2.current;
    if (mr && mr.state === 'recording') mr.stop();
  }, []);

  // Toggle recording (voice panel)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (recording) { setVoiceText(""); startNlsAsr(); }
    else { stopNlsAsr(); }
  }, [recording, startNlsAsr, stopNlsAsr]);

  // Inline voice-to-text: records, sends to ASR, puts text in input for review
  const inlineMrRef = useRef<MediaRecorder | null>(null);
  const inlineChunksRef = useRef<Blob[]>([]);
  const toggleInlineVoice = useCallback(async () => {
    const selectionVersion = getSelectionVersion();
    if (inlineRecording) {
      // Stop recording
      const mr = inlineMrRef.current;
      if (mr && mr.state === 'recording') mr.stop();
      setInlineRecording(false);
    } else {
      // Start recording
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (selectionVersion !== getSelectionVersion()) {
          stream.getTracks().forEach(track => track.stop());
          return;
        }
        const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
        inlineMrRef.current = mr;
        inlineChunksRef.current = [];
        mr.ondataavailable = (e) => { if (e.data.size > 0) inlineChunksRef.current.push(e.data); };
        mr.onstop = async () => {
          stream.getTracks().forEach(t => t.stop());
          if (selectionVersion !== getSelectionVersion()) return;
          const blob = new Blob(inlineChunksRef.current, { type: 'audio/webm' });
          if (blob.size < 100) return;
          try {
            const buf = await blob.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let b64 = ""; for (let i = 0; i < bytes.length; i++) b64 += String.fromCharCode(bytes[i]);
            const res = await apiFetch(`${API}/asr/recognize`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ audio: btoa(b64), format: "opus", sample_rate: 16000 }),
            });
            const data = await res.json();
            if (selectionVersion !== getSelectionVersion()) return;
            if (data.text) handleSendRef.current(data.text);
          } catch (_) {}
        };
        mr.start();
        setInlineRecording(true);
      } catch (_) {}
    }
  }, [inlineRecording, getSelectionVersion]);

  // ── 免提模式：朗读完自动录音，静音 1.5s 自动停 + 自动发 ──
  const startHandsFreeRecording = useCallback(async () => {
    if (!handsFreeRef.current) return;
    const selectionVersion = getSelectionVersion();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (selectionVersion !== getSelectionVersion() || !handsFreeRef.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
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
        if (selectionVersion !== getSelectionVersion() || !handsFreeRef.current) return;
        if (!hasSpoken) return;
        const blob = new Blob(chunks, { type: 'audio/webm' });
        if (blob.size < 100) return;
        try {
          const ab = await blob.arrayBuffer();
          const bytes = new Uint8Array(ab);
          let b64 = ""; for (let i = 0; i < bytes.length; i++) b64 += String.fromCharCode(bytes[i]);
          const res = await apiFetch(`${API}/asr/recognize`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ audio: btoa(b64), format: "opus", sample_rate: 16000 }),
          });
          const data = await res.json();
          if (selectionVersion !== getSelectionVersion() || !handsFreeRef.current) return;
          if (data.text) handleSendRef.current(data.text);
        } catch (_) {}
      };

      mr.start();
      requestAnimationFrame(tick);
    } catch (e) { console.error('[handsfree] mic error', e); }
  }, [getSelectionVersion]);

  // ── 流式 TTS 队列：按句送合成、顺序播放，**预取下一句消除句间空隙** ──
  // 同源 <audio> 会自动携带 HttpOnly Cookie；仅开发构建保留 dev_user 兜底。
  const mkTtsAudio = useCallback((text: string): HTMLAudioElement => {
    const params = new URLSearchParams({
      text: text.slice(0, 300),
      voice: "longxiaoxia_v2",
      speech_rate: "1.15",
    });
    if (process.env.NODE_ENV !== "production") {
      const u = typeof window !== "undefined" ? localStorage.getItem("fiona_user") : null;
      if (u) params.set("dev_user", u);
    }
    const a = new Audio(`${API}/tts/stream?${params.toString()}`);
    a.preload = "auto";
    return a;
  }, []);

  // 当前句正在播时，把队头那句的音频提前 fetch 好，下一句结束时立刻接上
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

    let done = false;
    const onDone = () => {
      if (done || ttsAudioRef.current !== audio) return;
      done = true;
      ttsPlayingRef.current = false;
      ttsAudioRef.current = null;
      playNextInQueueRef.current();
    };
    audio.addEventListener("ended", onDone, { once: true });
    audio.addEventListener("error", onDone, { once: true });
    audio.play().catch(onDone);
  }, [startHandsFreeRecording, mkTtsAudio, tryPrefetch]);

  useEffect(() => {
    playNextInQueueRef.current = playNextInQueue;
  }, [playNextInQueue]);

  // ── TTS 文本归一化：日期/时间/数字范围转成可读的中文 ──
  // CosyVoice 默认会把 "4.3" 念成"四点三"（小数），把 "780–2380" 念成"七百八十—两千三百八十"
  // 拼读出来的句子不像人话。在送 TTS 前把这些模式改写成口播友好的写法。
  // 屏幕上的文字保持原样（"4.3–4.5"看着像日期就够了），只改语音那一路。
  const normalizeForTTS = useCallback((text: string): string => {
    let s = text;
    // 日期范围 "M.D–M.D" 改为 "M月D日到M月D日"
    // 月份/日期 alternation 必须长串在前（JS 正则不是 longest-match，先匹配先决定），
    // 否则 "5.15" 会被吃成 "5月1日" + 残留 "5"
    s = s.replace(
      /(1[0-2]|[1-9])\.(3[01]|[12]\d|[1-9])\s*[–—~\-]\s*(1[0-2]|[1-9])\.(3[01]|[12]\d|[1-9])/g,
      "$1月$2日到$3月$4日",
    );
    // 单个 "M.D" 极容易和小数 (3.14 / 版本号 / 4.5 分钟) 撞，删除该规则
    // 范围形式 "M.D–M.D" 因为有 "–" 锚定，是唯一安全的日期模式
    // 时间范围 "HH:MM–HH:MM" 改为 "HH点MM分到HH点MM分"
    s = s.replace(
      /(\d{1,2}):(\d{2})\s*[–—~\-]\s*(\d{1,2}):(\d{2})/g,
      "$1点$2分到$3点$4分",
    );
    // 单个时间 "HH:MM" 改为 "HH点MM分"
    s = s.replace(/(\d{1,2}):(\d{2})(?!\d)/g, "$1点$2分");
    // 纯数字范围 "780–2380" 改为 "780到2380"（仅 unicode 长划线，避开 "-1" 之类）
    s = s.replace(/(\d+(?:\.\d+)?)\s*[–—~]\s*(\d+(?:\.\d+)?)/g, "$1到$2");
    // 剥掉打勾/项目符号/箭头/markdown 标记——CosyVoice 会念出 "白色重复选中标记" 这种 Unicode 名字
    // 打勾、叉号、箭头、项目符号以及 **加粗** 标记，全部当作没出现
    s = s.replace(/[✅✓☑❌✖✗✘❎✨✳✴⚠⚫]/g, "");
    s = s.replace(/[\u2192←↑↓⇒⇐⇑⇓➡]/g, "，");
    s = s.replace(/[•▪▫◆◇★☆●○■□·]/g, "");
    s = s.replace(/\*\*(.+?)\*\*/g, "$1").replace(/\*(.+?)\*/g, "$1");
    s = s.replace(/`([^`]+)`/g, "$1");
    // 兜底：剥掉其他 BMP 外的 emoji 区段（杂项符号、表情、交通、补充符号等）
    s = s.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "");
    // 连续空白与多余逗号收敛
    s = s.replace(/，{2,}/g, "，").replace(/\s{2,}/g, " ").trim();
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

  // A changed account or page unmount must not leave an old stream/voice session active.
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      setIsLoading(false);
      setInput("");
      setPendingImage(null);
      setImageMode(false);
      setReferenceImages(null);
      setAspectRatio("1:1");
      setIsReadingImage(false);
      setIsReadingReferences(false);
      setReferenceUploadError("");
      setHandsFree(false);
      setRecording(false);
      setInlineRecording(false);
    });
    return () => {
      cancelled = true;
      chatAbortRef.current?.abort();
      chatAbortRef.current = null;
      imageReaderRef.current?.abort();
      imageReaderRef.current = null;
      referenceReadControllerRef.current?.abort();
      referenceReadControllerRef.current = null;
      asrSessionRef.current += 1;
      handsFreeRef.current = false;
      clearTtsQueue();
      for (const recorder of [mediaRecorderRef2.current, inlineMrRef.current]) {
        if (recorder?.state === "recording") recorder.stop();
      }
    };
  }, [username, clearTtsQueue]);

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

  const handleDeleteMessage = useCallback(async (id: string, dbId?: number) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
    if (dbId) {
      await apiFetch(`${API}/message/${dbId}`, { method: "DELETE" }).catch(() => {});
    }
  }, [setMessages]);

  // 搜索类回复："帮我读" — 把搁置的 tip 文本送进 TTS 队列开始播放
  // 用户显式点击就是想听；即使朗读关闭也自动开启并播放（绕开 enqueueSpeech 的 voiceOn 守卫）
  const handleConfirmTts = useCallback((id: string, text: string) => {
    if (!voiceOn) setVoiceOn(true);
    ttsSessionRef.current += 1;
    streamDoneRef.current = true;
    const t = normalizeForTTS(text.trim());
    if (t) {
      ttsQueueRef.current.push(t);
      if (!ttsPlayingRef.current) playNextInQueue();
    }
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, pendingTtsText: undefined } : m)));
  }, [normalizeForTTS, playNextInQueue, voiceOn, setMessages]);

  // 搜索类回复："不用" — 直接清掉 pending 文本
  const handleDeclineTts = useCallback((id: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, pendingTtsText: undefined } : m)));
  }, [setMessages]);

  const handleClearChat = () => {
    if (!confirm("清空当前聊天界面？（历史记录仍保留）")) return;
    setMessages([]);
  };

  const conversationLocked = isLoading || recording || inlineRecording || handsFree;
  const selectedReferenceImages = referenceImages?.owner === username && referenceImages.conversationId === currentConversation?.id
    ? referenceImages.images : [];
  const selectedReferenceImagePaths = selectedReferenceImages.map(image => image.source.image_path ?? `local:${image.id}`);
  const hasReferenceImages = selectedReferenceImages.length > 0;

  const resetConversationPresentation = () => {
    clearTtsQueue();
    asrSessionRef.current += 1;
    setInput("");
    setPendingImage(null);
    imageReaderRef.current?.abort();
    imageReaderRef.current = null;
    setIsReadingImage(false);
    referenceReadControllerRef.current?.abort();
    referenceReadControllerRef.current = null;
    setIsReadingReferences(false);
    setReferenceUploadError("");
    setImageMode(false);
    setReferenceImages(null);
    setAspectRatio("1:1");
    setVoiceText("");
    setCollapsed({});
  };

  const handleNewChat = async () => {
    if (conversationLocked || conversationLoading) return;
    resetConversationPresentation();
    await createConversation();
    focusChatInput();
  };

  const handleSelectConversation = async (id: string) => {
    if (conversationLocked || conversationLoading || id === currentConversation?.id) return;
    resetConversationPresentation();
    await selectConversation(id);
  };

  const handleDeleteConversation = async (id: string) => {
    if (conversationLocked || conversationLoading) return;
    if (!confirm("删除这段对话及其中的消息？其他对话和分身设定会保留。此操作不可恢复。")) return;
    resetConversationPresentation();
    await deleteConversation(id);
  };

  const handleSelectReferenceImage = (imageUrl: string) => {
    if (conversationLocked || chatAbortRef.current || conversationLoading || !currentConversation || pendingImage || isReadingImage || referenceReadControllerRef.current) return;
    const imagePath = generatedImagePath(imageUrl);
    if (!imagePath || !messages.some(message => message.role === "assistant" && generatedImagePath(message.imageUrl) === imagePath)) return;
    setReferenceImages(previous => {
      const selected = previous?.owner === username && previous.conversationId === currentConversation.id ? previous.images : [];
      if (selected.some(image => image.source.image_path === imagePath) || selected.length >= 3) return previous;
      return { images: [...selected, { id: imagePath, source: { image_path: imagePath } }], owner: username, conversationId: currentConversation.id };
    });
    setReferenceUploadError("");
    setImageMode(false);
    // The image preview may have just closed its native modal dialog.
    requestAnimationFrame(focusChatInput);
  };

  const clearReferenceImages = () => {
    if (conversationLocked || conversationLoading || isReadingReferences) return;
    setReferenceImages(null);
    setReferenceUploadError("");
    requestAnimationFrame(focusChatInput);
  };

  const removeReferenceImage = (id: string) => {
    if (conversationLocked || conversationLoading || isReadingReferences) return;
    setReferenceImages(previous => {
      if (!previous || previous.owner !== username || previous.conversationId !== currentConversation?.id) return previous;
      const images = previous.images.filter(image => image.id !== id);
      return images.length ? { ...previous, images } : null;
    });
    setReferenceUploadError("");
    requestAnimationFrame(focusChatInput);
  };

  const moveReferenceImage = (id: string, direction: -1 | 1) => {
    if (conversationLocked || conversationLoading || isReadingReferences) return;
    setReferenceImages(previous => {
      if (!previous || previous.owner !== username || previous.conversationId !== currentConversation?.id) return previous;
      const from = previous.images.findIndex(image => image.id === id);
      const to = from + direction;
      if (from < 0 || to < 0 || to >= previous.images.length) return previous;
      const images = [...previous.images];
      [images[from], images[to]] = [images[to], images[from]];
      return { ...previous, images };
    });
  };

  const handleSend = async (textOverride?: string, imageRetry?: ImageGenerationRetry) => {
    const text = (textOverride ?? input).trim();
    if ((!text && !pendingImage) || isLoading || chatAbortRef.current || conversationLoading || !currentConversation || isReadingImage || referenceReadControllerRef.current) return;
    if (imageRetry && pendingImage) return;
    if (imageRetry && (imageRetry.owner !== username || imageRetry.conversationId !== currentConversation.id)) return;
    const sentImage = pendingImage;
    let requestReferenceImages = imageRetry ? imageRetry.referenceImages ?? [] : selectedReferenceImages.map(image => ({ ...image.source }));
    if (requestReferenceImages.length && (sentImage || requestReferenceImages.length > 3
      || requestReferenceImages.some(image => image.image_path
        ? image.image_base64 !== undefined || referenceImagePath(image.image_path) !== image.image_path
        : !image.image_base64 || !isLocalReferenceDataUrl(image.image_base64)))) return;
    const requestMode = requestReferenceImages.length ? "image_edit" : (imageRetry || imageMode) && !sentImage ? "image" : "chat";
    const requestAspectRatio = imageRetry ? imageRetry.aspectRatio
      : requestMode === "image_edit" ? undefined
      : requestMode === "image" ? aspectRatio : imageAspectRatioFromPrompt(text);
    const pendingImageStatus = requestMode === "image_edit" ? requestReferenceImages.some(image => image.image_base64) ? "正在上传参考图…" : "正在修改图片…"
      : requestMode === "image" ? "正在生成图片…" : undefined;
    const selectionVersion = getSelectionVersion();
    const chatController = new AbortController();
    chatAbortRef.current = chatController;
    const isCurrentStream = () => !chatController.signal.aborted
      && chatAbortRef.current === chatController && selectionVersion === getSelectionVersion()
      && (readStoredUsername() || "默认用户") === username;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text || "[发了一张图片]",
      timestamp: new Date(),
      imageUrl: requestReferenceImages.length ? referencePreviewUrl(requestReferenceImages[0]) : sentImage || undefined,
      referenceImageUrls: requestReferenceImages.length ? requestReferenceImages.map(referencePreviewUrl) : undefined,
      localReferenceImageUrls: requestReferenceImages.flatMap(image => image.image_base64 ? [image.image_base64] : []),
    };
    const typingMsg: Message = {
      id: "typing",
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isTyping: true,
      generationStatus: pendingImageStatus,
    };

    chatScrollRef.current?.scrollToLatest();
    setMessages((prev) => [...prev, userMsg, typingMsg]);
    // Retrying a generation or sending voice text must preserve the user's draft.
    if (textOverride === undefined) setInput("");
    if (sentImage) setPendingImage(null);
    if (requestReferenceImages.length && !imageRetry) setReferenceImages(null);
    setReferenceUploadError("");
    setIsLoading(true);
    if (textOverride === undefined && textareaRef.current) textareaRef.current.style.height = "auto";

    // ── 流式 TTS：新一轮先清队列并创建 session，再按句切（首句激进、碰逗号也切）──
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
    const replyId = `${Date.now()}-reply`;
    let generatingImage = requestMode !== "chat";
    let editingImage = requestMode === "image_edit";
    let generatedImageReceived = false;
    let responseComplete = false;
    try {
      const res = await apiFetch(`${API}/chat`, {
        method: "POST",
        signal: chatController.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: currentConversation.id,
          message: text,
          image_base64: sentImage || undefined,
          mode: requestMode,
          aspect_ratio: requestMode !== "chat" ? requestAspectRatio : undefined,
          reference_images: requestReferenceImages.length ? requestReferenceImages : undefined,
        }),
      });
      if (!isCurrentStream()) return;

      if (!res.ok) {
        const raw = await res.text();
        let errorMessage = `请求失败 (${res.status})`;
        const dataLine = raw.split(/\r?\n/).find((line) => line.startsWith("data:"));
        const payload = (dataLine ? dataLine.slice(5) : raw).trim();
        if (payload) {
          try {
            const data = JSON.parse(payload) as { error?: unknown; detail?: unknown };
            if (typeof data.error === "string") errorMessage = data.error;
            else if (typeof data.detail === "string") errorMessage = data.detail;
            else if (Array.isArray(data.detail)) errorMessage = requestMode === "image_edit"
              ? "参考图参数校验失败。请确认图片为 PNG、JPEG 或 WebP，每张不超过5MB，最多3张。"
              : "请求参数校验失败，请检查内容后重新发送。";
          } catch {
            // Do not expose a raw validation payload: it can contain image data.
          }
        }
        throw new Error(errorMessage);
      }
      if (!res.body) throw new Error("服务器未返回响应内容");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      // Replace typing placeholder with an empty assistant bubble
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== "typing")
          .concat({
            id: replyId,
            role: "assistant",
            content: "",
            timestamp: new Date(),
            generationStatus: pendingImageStatus,
          }),
      );

      // SSE 按完整事件解析：事件之间用 \n\n 分隔，单个事件可能跨多次 reader.read()
      let sseBuffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (!isCurrentStream()) { await reader.cancel(); return; }
        if (value) sseBuffer += decoder.decode(value, { stream: true });
        if (done) sseBuffer += decoder.decode();
        const events = sseBuffer.split(/\r?\n\r?\n/);
        sseBuffer = done ? "" : events.pop() || ""; // 流结束时也处理未带空行的最后一个事件
        for (const ev of events) {
          const line = ev.split(/\r?\n/).find((l) => l.startsWith("data:"));
          if (!line) continue;
          let data: ChatStreamEvent;
          try {
            data = JSON.parse(line.slice(5).trimStart());
          } catch {
            continue; // 损坏的事件跳过，不要让一条坏事件拖死整个流
          }
          if (data.tool) {
            // Keep focus in the avatar form while a background reply continues.
            setTimeout(focusChatInput, 100);
          }
          if (data.type === "reference_images") {
            const paths = data.reference_image_paths;
            if (!Array.isArray(paths) || paths.length !== requestReferenceImages.length || !paths.length || paths.length > 3
              || paths.some(path => typeof path !== "string" || referenceImagePath(path) !== path)) {
              throw new Error("参考图保存结果无效，请重试。");
            }
            // Persisted references replace local data in both this user message
            // and any earlier retry button used to initiate the current attempt.
            requestReferenceImages = paths.map(image_path => ({ image_path }));
            const normalizedReferences = requestReferenceImages;
            setMessages(previous => previous.map(message => {
              if (message.id === userMsg.id) return {
                ...message, imageUrl: `${API}${paths[0]}`,
                referenceImageUrls: paths.map(path => `${API}${path}`), localReferenceImageUrls: undefined,
              };
              if (imageRetry && message.imageGenerationRetry === imageRetry) return {
                ...message, imageGenerationRetry: { ...imageRetry, referenceImages: normalizedReferences },
              };
              return message;
            }));
          }
          if (data.status === "generating_image" || data.status === "editing_image") {
            generatingImage = true;
            editingImage = data.status === "editing_image";
            setMessages((prev) => prev.map((m) => m.id === replyId
              ? { ...m, generationStatus: data.message || (editingImage ? "正在修改图片…" : "正在生成图片…") } : m));
          }
          if (data.generated_image) {
            const generated = data.generated_image;
            // Generated assets must be served by our authenticated uploads endpoint.
            if (!generatedImagePath(generated.image_path)) {
              throw new Error("生成图片的地址无效，请重试。");
            }
            generatingImage = true;
            generatedImageReceived = true;
            setMessages((prev) => prev.map((m) => m.id === replyId ? {
              ...m, imageUrl: `${API}${generated.image_path}`, generationStatus: undefined,
              generatedImage: { width: generated.width, height: generated.height, model: generated.model },
            } : m));
          }
          if (data.text) {
            reply += data.text;
            ttsBuf += data.text;
            flushSentences();
            setMessages((prev) =>
              prev.map((m) => (m.id === replyId ? { ...m, content: reply } : m)),
            );
          }
          if (data.error) {
            await reader.cancel();
            throw new Error(data.error);
          }
          if (data.card) {
            const card: CardData = {
              source: data.card.source || "网页",
              points: data.card.points || [],
              url: data.card.url,
              error: data.card.error,
              subtype: data.card.subtype,
              weather: data.card.weather,
              items: data.card.items,
              sources: data.card.sources,
            };
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
                    const parts = fc.slice(0, 3).map((f: WeatherForecastDay) => `${f.day} ${weatherCN(f.condition)} ${f.low}~${f.high}°`);
                    msg += `接下来：${parts.join("；")}。`;
                    // 预警未来三天内的坏天气
                    const hasRain = fc.slice(0, 3).some((f: WeatherForecastDay) => {
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
                  msg += " 下面的卡片有详情——接下来几天的都帮你看了。";
                  return msg;
                })()
              : "搜到了，详情在下面的卡片里";
            // 卡片回复替换流式文本 — 清掉旧队列；TTS 不自动播，挂 pendingTtsText 等用户点"帮我读"
            clearTtsQueue();
            ttsBuf = "";
            reply = tip;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === replyId
                  ? { ...m, content: tip, cardData: card, pendingTtsText: tip || undefined }
                  : m,
              ),
            );
          }
          if (data.done) {
            responseComplete = true;
            streamDoneRef.current = true;
            break;
          }
        }
        // Drain to EOF after done so the server can finish saved-response accounting.
        if (done) break;
      }
      if (generatingImage && !generatedImageReceived) throw new Error(editingImage ? "图片修改未完成，请重试。" : "图片生成未完成，请重试。");
      if (!responseComplete && !generatedImageReceived) throw new Error("连接已中断，请重新发送消息。");
      focusChatInput();
    } catch (err) {
      if (!isCurrentStream()) return;
      const errMsg = err instanceof Error ? err.message : String(err);
      ttsBuf = "";
      clearTtsQueue();
      const failure: Partial<Message> = {
        content: `${reply ? `${reply}\n\n` : ""}错误：${errMsg}`,
        generationStatus: undefined,
        isTyping: false,
        imageGenerationRetry: generatingImage && !generatedImageReceived ? {
          prompt: text, aspectRatio: requestAspectRatio,
          referenceImages: requestReferenceImages.length ? requestReferenceImages.map(image => ({ ...image })) : undefined,
          owner: username, conversationId: currentConversation.id,
        } : undefined,
      };
      setMessages((prev) => {
        const retained = prev.filter((m) => m.id !== "typing");
        return retained.some(m => m.id === replyId)
          ? retained.map(m => m.id === replyId ? { ...m, ...failure } : m)
          : [...retained, { id: replyId, role: "assistant", content: "", timestamp: new Date(), ...failure }];
      });
    } finally {
      // Only the request that still owns this slot may clear its loading state.
      if (chatAbortRef.current === chatController) {
        streamDoneRef.current = true;
        if (isCurrentStream()) {
          if (ttsBuf.trim()) enqueueSpeech(ttsBuf, mySession);
          if (!ttsPlayingRef.current) playNextInQueue();
          setMessages(prev => prev.map(m => m.id === replyId ? { ...m, generationStatus: undefined, isTyping: false } : m));
          void refreshList();
        }
        setIsLoading(false);
        chatAbortRef.current = null;
      }
    }
  };
  useEffect(() => {
    handleSendRef.current = handleSend;
  }, [handleSend]);

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
    e.target.value = "";
    if (!file || imageMode || hasReferenceImages || referenceReadControllerRef.current || isLoading || conversationLoading || !currentConversation) return;
    if (!file.type.startsWith("image/")) {
      alert("只能上传图片");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert("图片不能超过 5MB");
      return;
    }
    const reader = new FileReader();
    imageReaderRef.current?.abort();
    imageReaderRef.current = reader;
    const selectionVersion = getSelectionVersion();
    setIsReadingImage(true);
    reader.onloadend = () => {
      if (imageReaderRef.current !== reader) return;
      imageReaderRef.current = null;
      setIsReadingImage(false);
      if (selectionVersion !== getSelectionVersion() || readStoredUsername() !== username) return;
      if (typeof reader.result === "string") setPendingImage(reader.result);
    };
    reader.readAsDataURL(file);
  };

  const handlePickReferenceImages = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length || conversationLocked || chatAbortRef.current || conversationLoading || !currentConversation
      || pendingImage || isReadingImage || referenceReadControllerRef.current) return;
    const remaining = 3 - selectedReferenceImages.length;
    if (files.length > remaining) {
      setReferenceUploadError(`最多共3张参考图，当前还可添加${remaining}张，请重新选择。`);
      return;
    }
    if (files.some(file => !REFERENCE_FILE_TYPES.includes(file.type))) {
      setReferenceUploadError("参考图仅支持 PNG、JPEG、WebP 格式。");
      return;
    }
    if (files.some(file => !file.size || file.size > MAX_REFERENCE_FILE_BYTES)) {
      setReferenceUploadError("每张参考图需大于 0 字节且不超过 5MB。");
      return;
    }
    const controller = new AbortController();
    referenceReadControllerRef.current = controller;
    const selectionVersion = getSelectionVersion();
    const conversationId = currentConversation.id;
    const isCurrentRead = () => referenceReadControllerRef.current === controller && !controller.signal.aborted
      && selectionVersion === getSelectionVersion() && (readStoredUsername() || "默认用户") === username;
    setIsReadingReferences(true);
    setReferenceUploadError("");
    try {
      const dataUrls = await Promise.all(files.map(file => readLocalReferenceImage(file, controller.signal)));
      if (!isCurrentRead()) return;
      const uniqueUrls = [...new Set(dataUrls)].filter(url => !selectedReferenceImages.some(image => image.source.image_base64 === url));
      if (!uniqueUrls.length) {
        setReferenceUploadError("这些图片已加入参考，请选择其他图片。");
        return;
      }
      const additions = uniqueUrls.map(image_base64 => ({ id: crypto.randomUUID(), source: { image_base64 } }));
      setReferenceImages(previous => {
        const selected = previous?.owner === username && previous.conversationId === conversationId ? previous.images : [];
        return { images: [...selected, ...additions].slice(0, 3), owner: username, conversationId };
      });
      setImageMode(false);
      requestAnimationFrame(focusChatInput);
    } catch (error) {
      if (!isCurrentRead()) return;
      controller.abort();
      setReferenceUploadError(error instanceof Error ? error.message : "参考图读取失败，请重新选择。");
    } finally {
      if (referenceReadControllerRef.current === controller) {
        referenceReadControllerRef.current = null;
        setIsReadingReferences(false);
      }
    }
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

      // WebSocket 握手自动携带同源 HttpOnly Cookie；开发构建可用 dev_user。
      const devAuth = process.env.NODE_ENV !== "production"
        ? `?dev_user=${encodeURIComponent(readStoredUsername() || username)}`
        : "";
      const ws = new WebSocket(`${WS_BASE}/ws/peer/${room.room_id}${devAuth}`);
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

  const signalMode = recording || inlineRecording ? "listening" : isLoading ? "speaking" : "idle";
  const conversationPickerProps = {
    conversations,
    selectedId: currentConversation?.id,
    loading: conversationLoading,
    locked: conversationLocked,
    canCreate: !!agent,
    error: conversationError,
    onSelect: (id: string) => { setConversationPickerOpen(false); void handleSelectConversation(id); },
    onCreate: () => { setConversationPickerOpen(false); void handleNewChat(); },
    onDelete: (id: string) => { void handleDeleteConversation(id); },
    onRetry: () => { if (!conversationLocked) { resetConversationPresentation(); void reloadConversations(); } },
    onHistory: () => {
      if (conversationPickerOpen && window.matchMedia("(width < 768px)").matches) {
        restoreConversationFocusRef.current = false;
        restoreHistoryFocusRef.current = true;
        setConversationPickerOpen(false);
        setShowHistory(true);
        return;
      }
      setConversationPickerOpen(false);
      setShowHistory(value => !value);
    },
    onFullHistory: () => { setConversationPickerOpen(false); window.open(`/history?user=${encodeURIComponent(username)}`, "_blank", "noopener,noreferrer"); },
  };

  // ── render ──

  return (
    <div className="flex flex-col h-dvh overflow-hidden">
      <div className="flex flex-1 min-h-0 relative">
        {/* ── sidebar 56px ── */}
        <Sidebar
          onChatClick={closeDrawer}
          onAgentClick={() => toggleDrawer("agent")}
          agentActive={agentOpen}
          onExchangeClick={() => toggleDrawer("exchange")}
          exchangeActive={exchangeOpen}
          onPlazaClick={() => toggleDrawer("plaza")}
          plazaActive={plazaOpen}
          onSettingsClick={() => toggleDrawer("settings")}
          settingsActive={settingsOpen}
          onBalanceChange={setStrawberryBalance}
        />

        {/* ── history slide-out drawer ── */}
        {showHistory && (
        <div
          className="glass absolute left-14 top-0 bottom-0 w-64 z-50 flex flex-col animate-in slide-in-from-left duration-300 max-md:left-0 max-md:bottom-[calc(56px+env(safe-area-inset-bottom))] max-md:w-[min(85vw,320px)]"
          style={{ borderRight: "1px solid var(--glass-border)", boxShadow: "8px 0 32px rgba(0,0,0,0.28)" }}
        >
          <>
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <div className="flex items-center gap-1.5">
                  <Clock size={12} className="text-muted-foreground" />
                  <span className="text-xs font-semibold text-muted-foreground tracking-wide">当前对话记录</span>
                </div>
                <div className="flex items-center gap-2">
                  <button disabled={!currentConversation || conversationLocked || conversationLoading} onClick={() => currentConversation && handleDeleteConversation(currentConversation.id)} className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-destructive transition-colors disabled:opacity-40" title="删除当前对话">
                    <Trash2 size={11} />删除
                  </button>
                  <button ref={historyCloseButtonRef} onClick={() => setShowHistory(false)} aria-label="关闭当前对话记录" className="text-muted-foreground hover:text-foreground max-md:grid max-md:h-10 max-md:w-10 max-md:place-items-center">
                    <X size={14} />
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto py-3 px-3">
                {hasMoreMessages && <p className="px-2 pb-3 text-[11px] text-muted-foreground">当前显示最近 500 条消息，完整记录可在历史页查看。</p>}
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
                                  <span className="text-[10px] font-medium text-muted-foreground">{msg.role === "assistant" ? agent?.display_name || "我的分身" : "我"}</span>
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
          </>
        </div>
        )}

        {/* ── subtle backdrop behind drawer (does NOT cover sidebar) */}
        {showHistory && (
          <div className="absolute left-14 top-0 bottom-0 right-0 z-40 bg-black/20 backdrop-blur-sm transition-opacity max-md:left-0 max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]" onClick={() => setShowHistory(false)} />
        )}

        <div className="flex flex-1 min-w-0 min-h-0">
          <ConversationPicker {...conversationPickerProps} className="max-md:hidden" />

          {conversationPickerOpen && <>
            <div className="fixed inset-x-0 top-0 bottom-[calc(56px+env(safe-area-inset-bottom))] z-[61] bg-black/20 backdrop-blur-sm md:hidden" onClick={() => setConversationPickerOpen(false)} aria-hidden="true" />
            <div id="conversation-picker-dialog" ref={conversationDialogRef} role="dialog" aria-modal="true" aria-label="对话列表" tabIndex={-1}
              className="fixed left-0 top-0 bottom-[calc(56px+env(safe-area-inset-bottom))] z-[62] w-[min(85vw,320px)] animate-in slide-in-from-left duration-300 outline-none md:hidden">
              <ConversationPicker {...conversationPickerProps} />
            </div>
          </>}

          <div className="relative flex-1 min-w-0" data-chat-panel>
            <header
              className="glass absolute inset-x-0 top-0 z-[2] grid h-16 grid-cols-[auto_minmax(120px,1fr)_auto] items-center gap-6 border-b px-6 max-md:h-20 max-md:grid-cols-[minmax(0,1fr)_auto] max-md:grid-rows-[56px_24px] max-md:gap-0 max-md:px-3"
              style={{ borderColor: "var(--glass-border)" }}
            >
              <div className="flex items-center gap-3 max-md:min-w-0 max-md:gap-2">
                <button ref={conversationListButtonRef} type="button" aria-label="对话列表" aria-expanded={conversationPickerOpen} aria-controls={conversationPickerOpen ? "conversation-picker-dialog" : undefined}
                  onClick={() => { restoreConversationFocusRef.current = true; setConversationPickerOpen(true); }} className="btn btn-quiet hidden h-10 w-10 shrink-0 px-0 max-md:inline-flex">
                  <PanelLeft size={20} />
                </button>
                <span className="grid h-8 w-8 place-items-center rounded-[6px] bg-secondary text-base max-md:shrink-0" aria-hidden="true">{agent?.avatar_emoji || "✨"}</span>
                <div className="max-md:min-w-0">
                  <div className="text-sm font-medium max-md:truncate">{agent?.display_name || "我的分身"}</div>
                  <div className="flex gap-2 text-xs text-muted-foreground max-md:hidden"><span>AI 分身</span><span>仅你可见</span></div>
                </div>
              </div>
              <Signal mode={signalMode} className="max-md:col-span-2 max-md:row-start-2 max-md:h-6" />
              <div className="flex items-center gap-2 max-md:col-start-2 max-md:row-start-1 max-md:shrink-0 max-md:gap-1">
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className={cn("state-dot", signalMode === "listening" && "state-dot-listening", signalMode === "speaking" && "state-dot-speaking")} />
                  <span className="max-md:hidden">{signalMode === "listening" ? "正在听" : signalMode === "speaking" ? "正在说" : "待命"}</span>
                </span>
                <button type="button" className={cn("chip max-md:h-9 max-md:w-9 max-md:justify-center max-md:px-0", voiceOn && "chip-on")}
                  onClick={() => setVoiceOn(!voiceOn)} aria-label="朗读">
                  {voiceOn ? <Volume2 size={13} /> : <VolumeX size={13} />}<span className="max-md:hidden">朗读</span>
                </button>
                <button
                  type="button"
                  className={cn("chip max-md:h-9 max-md:w-9 max-md:justify-center max-md:px-0", handsFree && "chip-on")}
                  onClick={() => {
                    const next = !handsFree;
                    setHandsFree(next);
                    if (next) setVoiceOn(true);
                  }}
                  disabled={conversationLoading || !currentConversation}
                  aria-label="免提"
                  title="免提：分身说完自动开麦，你停顿 1.5 秒后自动发"
                >
                  <AudioLines size={13} className="md:hidden" /><span className="max-md:hidden">免提</span>
                </button>
                <span className="hidden shrink-0 items-center gap-0.5 whitespace-nowrap text-xs max-md:inline-flex" title="草莓余额，每条消息消耗 10 颗">
                  <span aria-hidden="true">🍓</span>
                  <b className="readout" style={{ color: strawberryBalance !== null && strawberryBalance < 30 ? "var(--rec)" : strawberryBalance !== null && strawberryBalance < 100 ? "var(--amber-ink)" : "var(--foreground)" }}>
                    {strawberryBalance === null ? "…" : strawberryBalance}
                  </b>
                </span>
              </div>
            </header>
            <div className="absolute inset-0 flex flex-col pt-16 pb-[var(--composer-height)] max-md:pt-20 max-md:pb-[calc(var(--composer-height)+56px+env(safe-area-inset-bottom))]"
              style={{ "--composer-height": `${composerHeight}px` } as React.CSSProperties}>
              <ChatScrollArea ref={chatScrollRef} resetKey={`${username}:${currentConversation?.id ?? "loading"}`}>
                <div className="flex w-full max-w-[760px] flex-col gap-[22px]">
                  {hasMoreMessages && <p className="text-xs text-muted-foreground text-center">当前显示最近 500 条消息；更早记录可在历史页查看。</p>}
                  {messages.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center pt-8" role="status">{conversationLoading ? "正在加载对话…" : conversationError ? "对话加载失败，请在上方重试。" : currentConversation ? `和 ${agent?.display_name || "你的分身"} 开始新的交流。` : "点击上方“新对话”，开始和自己的分身交流。"}</p>
                  )}
                  {messages.map((msg) => (
                    <ChatBubble key={`${username}-${currentConversation?.id}-${msg.id}`} message={msg} agentName={agent?.display_name} agentAvatar={agent?.avatar_emoji} onDelete={isLoading ? undefined : handleDeleteMessage} onConfirmTts={handleConfirmTts} onDeclineTts={handleDeclineTts}
                      onRetryImage={request => { void handleSend(request.prompt, request); }} onEditImage={handleSelectReferenceImage}
                      selectedReferenceImagePaths={selectedReferenceImagePaths}
                      imageRetryDisabled={conversationLocked || conversationLoading || !currentConversation || !!pendingImage || isReadingImage || isReadingReferences} />
                  ))}
                </div>
              </ChatScrollArea>
            </div>
            <footer ref={composerRef} className="glass absolute inset-x-0 bottom-0 z-[2] border-t px-8 pb-4 pt-3 max-md:bottom-[calc(56px+env(safe-area-inset-bottom))] max-md:px-3 max-md:pb-3" style={{ borderColor: "var(--glass-border)" }}>
              <div data-chat-composer className="mx-auto max-w-[760px]">
                {referenceUploadError && <p role="alert" className="mb-2 text-xs text-destructive">{referenceUploadError}</p>}
                {hasReferenceImages && <div className="mb-2 rounded-[10px] bg-secondary/50 p-2">
                  <div className="flex max-h-[144px] items-start gap-2 overflow-auto pb-1" aria-label="已选参考图，按编号顺序发送">
                    {selectedReferenceImages.map((image, index) => <div key={`${username}:${currentConversation?.id}:${image.id}`} className="w-[120px] shrink-0">
                      <GeneratedImage imageUrl={referencePreviewUrl(image.source)} variant="reference" referenceIndex={index + 1} compact localPreview={!!image.source.image_base64} />
                      <div className="mt-1 flex items-center justify-between gap-1 px-1 text-muted-foreground max-md:gap-0 max-md:px-0">
                        <button type="button" aria-label={`将图${index + 1}前移`} title="前移" disabled={conversationLocked || conversationLoading || isReadingReferences || index === 0}
                          onClick={() => moveReferenceImage(image.id, -1)} className="rounded p-1 hover:bg-secondary hover:text-foreground disabled:opacity-30 max-md:grid max-md:h-10 max-md:w-10 max-md:place-items-center max-md:p-0"><ArrowLeft size={12} /></button>
                        <button type="button" aria-label={`将图${index + 1}后移`} title="后移" disabled={conversationLocked || conversationLoading || isReadingReferences || index === selectedReferenceImages.length - 1}
                          onClick={() => moveReferenceImage(image.id, 1)} className="rounded p-1 hover:bg-secondary hover:text-foreground disabled:opacity-30 max-md:grid max-md:h-10 max-md:w-10 max-md:place-items-center max-md:p-0"><ArrowRight size={12} /></button>
                        <button type="button" aria-label={`移除参考图${index + 1}`} title="移除这张参考图" disabled={conversationLocked || conversationLoading || isReadingReferences}
                          onClick={() => removeReferenceImage(image.id)} className="ml-auto rounded p-1 hover:bg-destructive/10 hover:text-destructive disabled:opacity-30 max-md:grid max-md:h-10 max-md:w-10 max-md:place-items-center max-md:p-0"><X size={12} /></button>
                      </div>
                    </div>)}
                  </div>
                  <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
                    {selectedReferenceImagePaths.length === 3 ? "已选满3张。例：用图1的人物、图2的场景、图3的色调。"
                      : selectedReferenceImagePaths.length === 2 ? "例：用图1的人物、图2的场景。还可加入1张参考图。"
                      : "输入修改要求，也可上传本地图片或加入已生成图片，最多3张。"}
                  </p>
                </div>}
                <div className="flex flex-col gap-2 rounded-[10px] border px-3.5 py-2.5" style={{ background: "var(--fill)", borderColor: "var(--glass-border)" }}>
                  <div className="flex items-end gap-2">
                    {pendingImage && (
                      <div className="relative inline-block w-fit pt-1">
                        <img src={pendingImage} alt="待发送" className="rounded-xl max-h-20 max-w-[120px] object-cover border border-border" />
                        <button type="button" aria-label="移除待发送图片" onClick={() => setPendingImage(null)} className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-background border border-border flex items-center justify-center hover:bg-destructive hover:text-white transition-colors max-md:-right-4 max-md:h-10 max-md:w-10">
                          <X size={10} />
                        </button>
                      </div>
                    )}
                    <textarea ref={textareaRef} value={input} onChange={handleInput} onKeyDown={handleKeyDown}
                      disabled={conversationLoading || !currentConversation}
                      onCompositionStart={() => { isComposingRef.current = true; }}
                      onCompositionEnd={() => { isComposingRef.current = false; }}
                      placeholder={hasReferenceImages ? "描述修改要求，可用图1、图2、图3指定各图用途…" : imageMode ? "描述想生成的画面、风格和细节…" : pendingImage ? "说点什么…（可选）" : "说点什么…"} rows={1}
                      className="min-w-0 flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none py-1 leading-relaxed max-h-[80px] max-md:text-base"
                    />
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <input ref={referenceFileInputRef} type="file" multiple accept="image/png,image/jpeg,image/webp" onChange={handlePickReferenceImages} className="hidden" />
                      <button type="button" onClick={() => referenceFileInputRef.current?.click()}
                        disabled={conversationLocked || conversationLoading || !currentConversation || !!pendingImage || isReadingImage || isReadingReferences || selectedReferenceImages.length >= 3}
                        title={pendingImage ? "请先移除普通待发送图片" : selectedReferenceImages.length >= 3 ? "最多3张参考图，请先移除一张" : "选择 PNG、JPEG 或 WebP；每张不超过5MB，发送修改要求时才上传"}
                        className={cn("chip max-md:h-10", hasReferenceImages && "chip-on")}>
                        <ImagePlus size={12} />上传参考图
                      </button>
                      {isReadingReferences && <span role="status" className="text-muted-foreground">正在读取并检查参考图…</span>}
                      {hasReferenceImages ? <>
                        <span className="chip chip-on"><PencilLine size={12} />修改图片</span>
                        <span role="status" className="text-[color:var(--amber-ink)]">参考图 {selectedReferenceImagePaths.length}/3</span>
                        <span className="text-muted-foreground">尺寸跟随图1</span>
                        <button type="button" disabled={conversationLocked || conversationLoading || isReadingReferences} onClick={clearReferenceImages} className="ml-auto flex items-center gap-1 text-muted-foreground hover:text-foreground disabled:opacity-40 max-md:min-h-10"><X size={11} />全部取消</button>
                      </> : imageMode ? <>
                        <span className="chip chip-on"><Sparkles size={12} />生成图片</span>
                        <div role="group" aria-label="图片比例" className="flex items-center gap-1">
                          {(["1:1", "16:9", "9:16"] as const).map(ratio => <button key={ratio} type="button" aria-pressed={aspectRatio === ratio} disabled={isLoading}
                            onClick={() => setAspectRatio(ratio)} className={cn("chip h-6 px-2 max-md:h-10", aspectRatio === ratio && "chip-on")}>
                            {ratio}
                          </button>)}
                        </div>
                        <button type="button" disabled={isLoading} onClick={() => setImageMode(false)} className="ml-auto flex items-center gap-1 text-muted-foreground hover:text-foreground disabled:opacity-40 max-md:min-h-10"><X size={11} />返回聊天</button>
                      </> : <>
                        <button type="button" onClick={() => setImageMode(true)} disabled={!!pendingImage || isReadingImage || isReadingReferences || conversationLocked || conversationLoading || !currentConversation}
                          title={pendingImage || isReadingImage ? "请先移除待发送图片，再切换到生成图片" : "用文字描述生成一张图片"}
                          className="chip max-md:h-10">
                          <Sparkles size={12} />生成图片
                        </button>
                        {pendingImage && <span className="text-muted-foreground">先移除待发送图片，即可切换生成模式</span>}
                        {isReadingImage && <span role="status" className="text-muted-foreground">正在读取图片…</span>}
                      </>}
                    </div>
                    <div className="flex items-center gap-0.5 ml-auto shrink-0">
                    <input ref={fileInputRef} type="file" accept="image/*" onChange={handlePickImage} className="hidden" />
                    <button type="button" onClick={() => fileInputRef.current?.click()} disabled={imageMode || hasReferenceImages || isReadingImage || isReadingReferences || isLoading || conversationLoading || !currentConversation}
                      className="btn btn-quiet h-8 w-8 px-0 max-md:h-10 max-md:w-10" title={hasReferenceImages ? "取消参考后可发送看图聊天附件" : imageMode ? "返回聊天后可发送看图聊天附件" : "发送看图聊天附件"}>
                      <ImagePlus size={14} />
                    </button>
                    <button type="button" onClick={toggleInlineVoice}
                      disabled={conversationLoading || !currentConversation || isLoading}
                      className={cn("btn btn-quiet h-8 w-8 px-0 max-md:h-10 max-md:w-10", inlineRecording && "text-[color:var(--rec)] bg-[color:var(--rec-soft)]")}
                      aria-label="语音转文字"
                      title="语音转文字">
                      <Mic size={14} />
                    </button>
                    <button
                      type="button"
                      onPointerDown={(e) => { e.preventDefault(); (e.target as HTMLElement).setPointerCapture(e.pointerId); setRecording(true); }}
                      onPointerUp={(e) => { e.preventDefault(); (e.target as HTMLElement).releasePointerCapture(e.pointerId); asrSessionRef.current += 1; setRecording(false); }}
                      className={cn("btn btn-quiet h-8 px-2.5 text-xs max-md:h-10 max-md:w-10 max-md:px-0", recording && "text-[color:var(--rec)] bg-[color:var(--rec-soft)]")}
                      aria-label="按住说话"
                      disabled={conversationLoading || !currentConversation || isLoading}
                    >
                      <Mic size={14} /><span className="max-md:hidden">按住说话</span>
                    </button>
                    <button onClick={() => handleSend()} aria-label={hasReferenceImages ? "修改图片" : imageMode ? "生成图片" : "发送消息"} disabled={isLoading || isReadingImage || isReadingReferences || conversationLoading || !currentConversation || (!input.trim() && !pendingImage)}
                      className="grid h-8 w-8 place-items-center rounded-[6px] bg-primary text-primary-foreground disabled:bg-secondary disabled:text-[color:var(--dim)] max-md:h-10 max-md:w-10"
                    ><Send size={14} /></button>
                    </div>
                  </div>
                </div>
                {voiceText && <p className="mt-2 text-xs text-muted-foreground">{voiceText}</p>}
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span className="max-md:hidden">Enter 发送，Shift + Enter 换行</span>
                  <span>每条消息消耗 <b className="readout">10</b> 颗草莓</span>
                </div>
              </div>
            </footer>
          </div>
        </div>
      </div>

      {/* 分身直接复用管理组件，点击即时展开，不依赖整页路由切换。 */}
      <section
        id="agent-drawer"
        ref={agentPanelRef}
        aria-label="分身管理"
        aria-hidden={!agentOpen}
        inert={!agentOpen}
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            closeDrawer();
            focusVisibleDrawerTrigger("agent-drawer");
          }
        }}
        className={cn("glass fixed inset-y-0 right-0 z-[55] flex flex-col outline-none max-md:left-0 max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]! max-md:w-screen!", !agentOpen && "max-md:hidden")}
        style={{
          width: "min(960px, calc(100vw - 56px))",
          borderLeft: "1px solid var(--glass-border)",
          boxShadow: agentOpen ? "-12px 0 32px rgba(0,0,0,0.28)" : "none",
          transform: agentOpen ? "translateX(0)" : "translateX(105%)",
          transition: "transform 360ms cubic-bezier(.22,.61,.36,1)",
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--glass-border)" }}>
          <span className="text-xs font-medium text-muted-foreground">分身</span>
          <button type="button" onClick={closeDrawer} aria-label="收起分身面板" className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground max-md:h-10 max-md:w-10">
            <X size={14} />
          </button>
        </div>
        {agentOpen && <MyAgentWorkspace embedded onSaved={updateAgent} />}
      </section>

      <section
        id="exchange-drawer"
        ref={exchangePanelRef}
        aria-label="分身广场"
        aria-hidden={!exchangeOpen}
        inert={!exchangeOpen}
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            closeDrawer();
            focusVisibleDrawerTrigger("exchange-drawer");
          }
        }}
        className={cn("glass fixed inset-y-0 right-0 z-[55] flex flex-col outline-none max-md:left-0 max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]! max-md:w-screen!", !exchangeOpen && "max-md:hidden")}
        style={{
          width: "min(960px, calc(100vw - 56px))",
          borderLeft: "1px solid var(--glass-border)",
          boxShadow: exchangeOpen ? "-12px 0 32px rgba(0,0,0,0.28)" : "none",
          transform: exchangeOpen ? "translateX(0)" : "translateX(105%)",
          transition: "transform 360ms cubic-bezier(.22,.61,.36,1)",
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--glass-border)" }}>
          <span className="text-xs font-medium text-muted-foreground">分身广场</span>
          <button type="button" onClick={closeDrawer} aria-label="收起分身广场" className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground max-md:h-10 max-md:w-10"><X size={14} /></button>
        </div>
        {exchangeOpen && <AgentExchangeWorkspace embedded onOpenMyAgent={() => setDrawer("agent")} />}
      </section>

      {/* 世界抽屉 — 从右侧滑出，覆盖 2/3 聊天区；不卸载 iframe，重开秒回原状态 */}
      <div
        id="plaza-drawer"
        className={cn("glass fixed z-[55] flex flex-col max-md:left-0 max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]! max-md:w-screen!", !plazaOpen && "max-md:hidden")}
        style={{
          top: 0,
          bottom: 0,
          right: 0,
          width: "calc((100vw - 56px) * 2 / 3)",
          borderLeft: "1px solid var(--glass-border)",
          boxShadow: plazaOpen ? "-12px 0 32px rgba(0,0,0,0.28)" : "none",
          transform: plazaOpen ? "translateX(0)" : "translateX(105%)",
          transition: "transform 360ms cubic-bezier(.22,.61,.36,1)",
          willChange: "transform",
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--glass-border)" }}>
          <span className="text-xs font-medium text-muted-foreground">世界</span>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setWorldTab("plaza")} className={cn("chip", worldTab === "plaza" && "chip-on")}>热点与帖子</button>
            <button type="button" onClick={() => setWorldTab("match")} className={cn("chip", worldTab === "match" && "chip-on")}>匹配</button>
            <button
              onClick={closeDrawer}
              className="w-6 h-6 flex items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground max-md:h-10 max-md:w-10"
              title="收起"
            >
              <X size={14} />
            </button>
          </div>
        </div>
        <iframe src={worldTab === "plaza" ? "/plaza?embed=1" : "/match?embed=1"} className="flex-1 w-full border-0" />
      </div>

      {/* 设置抽屉 — 「我的」作为账户标签并入设置。 */}
      <div
        id="settings-drawer"
        className={cn("glass fixed z-[55] flex flex-col max-md:left-0 max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]! max-md:w-screen!", !settingsOpen && "max-md:hidden")}
        style={{
          top: 0,
          bottom: 0,
          right: 0,
          width: "calc((100vw - 56px) * 2 / 3)",
          borderLeft: "1px solid var(--glass-border)",
          boxShadow: settingsOpen ? "-12px 0 32px rgba(0,0,0,0.28)" : "none",
          transform: settingsOpen ? "translateX(0)" : "translateX(105%)",
          transition: "transform 360ms cubic-bezier(.22,.61,.36,1)",
          willChange: "transform",
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--glass-border)" }}>
          <span className="text-xs font-medium text-muted-foreground">设置</span>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setSettingsTab("settings")} className={cn("chip", settingsTab === "settings" && "chip-on")}>设置</button>
            <button type="button" onClick={() => setSettingsTab("profile")} className={cn("chip", settingsTab === "profile" && "chip-on")}>账户</button>
            <button
              onClick={closeDrawer}
              className="w-6 h-6 flex items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground max-md:h-10 max-md:w-10"
              title="收起"
            >
              <X size={14} />
            </button>
          </div>
        </div>
        <iframe src={settingsTab === "settings" ? "/settings?embed=1" : "/profile?embed=1"} className="flex-1 w-full border-0" />
      </div>

      {/* 抽屉外部点击关闭 — 任一右侧抽屉打开时铺一层透明背板，盖在抽屉之下、聊天区之上。
          z-50 < 抽屉 z-55；left-14 避开 sidebar 让侧栏始终可点切换抽屉 */}
      {anyDrawerOpen && (
        <div
          className="fixed left-14 top-0 right-0 bottom-0 z-50 max-md:left-0 max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]"
          onClick={closeDrawer}
          aria-hidden
        />
      )}

    </div>
  );
}
