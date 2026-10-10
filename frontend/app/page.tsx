"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Glaze from "@/components/Glaze";
import InkLandscape from "@/components/InkLandscape";
import Seal from "@/components/Seal";
import Sidebar from "@/components/Sidebar";
import ChatBubble, { type Message, type CardData, type WeatherForecastDay, type ImageAspectRatio, type ImageModelId, type ImageGenerationRetry } from "@/components/ChatBubble";
import GeneratedImage from "@/components/GeneratedImage";
import ConversationPicker from "@/components/ConversationPicker";
import ChatScrollArea, { type ChatScrollHandle } from "@/components/ChatScrollArea";
import Signal from "@/components/Signal";
import MyAgentWorkspace from "@/components/MyAgentWorkspace";
import AgentExchangeWorkspace from "@/components/AgentExchangeWorkspace";
import { useConversations } from "@/lib/useConversations";
import { formatChineseDate } from "@/lib/chineseDate";
import { DEFAULT_IMAGE_MODEL, FALLBACK_IMAGE_MODELS } from "@/lib/imageModels";
import {
  Mic, Volume2, VolumeX, ChevronDown, ChevronRight,
  Trash2, ImagePlus, X, Clock, Sparkles, PencilLine, ArrowLeft, ArrowRight, PanelLeft, AudioLines,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch, getUsername as readStoredUsername } from "@/lib/auth";
import { requestTtsTicket, type TtsBackoff } from "@/lib/ttsTicket";
import { generatedImagePath, referenceImagePath, referencePreviewUrl, isLocalReferenceDataUrl, type ReferenceImageInput } from "@/lib/generatedImages";
import { readLocalReferenceImage, MAX_REFERENCE_FILE_BYTES, REFERENCE_FILE_TYPES } from "@/lib/localReferenceImages";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { CHAT_MODEL_REV_KEY, CLAUDE_EFFORTS, CHAT_MODEL_EFFORT_LABELS, CHAT_MODEL_EFFORT_TITLES, chatModelErrorMessage, getChatModel, setChatModelEnabled, setChatModelOptions, publishChatModelRevision, parseReplyModel, type ChatModelEffort, type ChatModelSettings } from "@/lib/chatModel";

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
  reply_model?: unknown;
  type?: "reference_images";
  crisis?: boolean;
  reference_image_paths?: string[];
  tool?: unknown;
  text?: string;
  speak?: boolean;
  card?: CardData;
  error?: string;
  done?: boolean;
  status?: "generating_image" | "editing_image";
  source?: string;
  message?: string;
  generated_image?: { image_path: string; model: string; width: number; height: number; reference_image_paths?: string[]; reference_image_path?: string };
}

interface ImageReferenceSelection {
  images: { id: string; source: ReferenceImageInput }[];
  owner: string;
  conversationId: string;
}

const IMAGE_MODEL_STORAGE_KEY = "fiona_image_model";

interface PreparedTtsAudio {
  text: string;
  slot: TtsAudioSlot;
  audio: HTMLAudioElement;
  session: number;
  ready: Promise<boolean>;
  controller: AbortController;
  listeners: AbortController | null;
  cancelled: boolean;
  waitingUntil: number | null;
  ticketExpiresAt: number | null;
}

interface TtsAudioSlot {
  audio: HTMLAudioElement;
  owner: PreparedTtsAudio | null;
  unlocked: boolean;
  primeAttempt: object | null;
}

// 以后端 expires_in 为准，剩余不足 15 秒视为不够用，留出开始播放和首个
// Range 请求的余量；按 150 秒有效期，正常流程不会触发。
const TTS_TICKET_MIN_REMAINING_MS = 15_000;

function isTicketStale(prepared: PreparedTtsAudio): boolean {
  return prepared.ticketExpiresAt !== null
    && prepared.ticketExpiresAt - Date.now() < TTS_TICKET_MIN_REMAINING_MS;
}

let silentTtsWavUri: string | null = null;
function getSilentTtsWavUri(): string {
  if (silentTtsWavUri) return silentTtsWavUri;
  // 40 ms of 8 kHz, unsigned 8-bit mono PCM silence.
  const samples = 320;
  const wav = new Uint8Array(44 + samples);
  const view = new DataView(wav.buffer);
  const label = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) wav[offset + i] = value.charCodeAt(i);
  };
  label(0, "RIFF");
  view.setUint32(4, 36 + samples, true);
  label(8, "WAVE");
  label(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true);
  view.setUint32(28, 8000, true);
  view.setUint16(32, 1, true);
  view.setUint16(34, 8, true);
  label(36, "data");
  view.setUint32(40, samples, true);
  wav.fill(128, 44);
  silentTtsWavUri = `data:audio/wav;base64,${btoa(String.fromCharCode(...wav))}`;
  return silentTtsWavUri;
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
      className="ceramic-card w-64 px-4 py-3"
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

function drawerStyle(open: boolean): React.CSSProperties {
  return {
    visibility: open ? "visible" : "hidden",
    boxShadow: open ? "-12px 0 32px var(--drop)" : "none",
    transform: open ? "translateX(0)" : "translateX(105%)",
    transition: `transform 360ms cubic-bezier(.22,.61,.36,1), visibility 0s linear ${open ? "0s" : "360ms"}`,
  };
}

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
function weatherForecastCondition(forecast: WeatherForecastDay) {
  return forecast.dayWeather === forecast.nightWeather
    ? forecast.dayWeather
    : [forecast.dayWeather, forecast.nightWeather].filter(Boolean).join("转");
}

// ── main page ──

function ChatModelFooter({ username, settingsOpen, chatMode, loading }: {
  username: string; settingsOpen: boolean; chatMode: boolean; loading: boolean;
}) {
  const [settings, setSettings] = useState<ChatModelSettings | null>(null);
  const [busy, setBusy] = useState<"toggle" | "effort" | null>(null);
  const [error, setError] = useState("");
  const { beginRequest } = useAccountRequest(username);
  const { beginRequest: beginMutation } = useAccountRequest(username);
  const revision = useRef(0);
  const errorOwner = useRef<"refresh" | "operation" | null>(null);
  const effortGroup = useRef<HTMLDivElement>(null);
  const refresh = useCallback(() => {
    const request = beginRequest();
    if (!request) return;
    const readRevision = revision.current;
    getChatModel(request.signal).then(value => {
      if (!request.isCurrent() || readRevision !== revision.current) return;
      setSettings(value);
      if (errorOwner.current === "refresh") {
        errorOwner.current = null;
        setError("");
      }
    }).catch(cause => {
      if (request.isCurrent() && readRevision === revision.current && errorOwner.current !== "operation") {
        errorOwner.current = "refresh";
        setError(chatModelErrorMessage(cause));
      }
    });
  }, [beginRequest]);
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === CHAT_MODEL_REV_KEY) refresh();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    if (!settingsOpen) refresh();
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh, settingsOpen]);

  const toggle = async () => {
    if (!settings?.config || busy || loading) return;
    const request = beginMutation();
    if (!request) return;
    errorOwner.current = null;
    revision.current += 1;
    setBusy("toggle"); setError("");
    try {
      const config = await setChatModelEnabled(!settings.config.enabled, request.signal);
      if (!request.isCurrent()) return;
      revision.current += 1;
      setSettings(previous => previous ? { ...previous, config } : previous);
      publishChatModelRevision();
    } catch (cause) {
      if (request.isCurrent()) {
        errorOwner.current = "operation";
        setError(chatModelErrorMessage(cause));
      }
    } finally {
      if (request.isCurrent()) setBusy(null);
    }
  };

  const changeEffort = async (effort: ChatModelEffort) => {
    const current = settings?.config;
    if (!chatMode || !current?.enabled || current.provider !== "anthropic" || current.status !== "ok"
      || current.effort === effort || !settings?.available || busy || loading) return;
    const request = beginMutation();
    if (!request) return;
    errorOwner.current = null;
    revision.current += 1;
    setBusy("effort"); setError("");
    try {
      const config = await setChatModelOptions({ effort }, request.signal);
      if (!request.isCurrent()) return;
      revision.current += 1;
      setSettings(previous => previous ? { ...previous, config } : previous);
      publishChatModelRevision();
    } catch (cause) {
      if (request.isCurrent()) {
        errorOwner.current = "operation";
        setError(chatModelErrorMessage(cause));
      }
    } finally {
      if (request.isCurrent()) setBusy(null);
    }
  };

  const config = settings?.config;
  const provider = settings?.providers.find(item => item.id === config?.provider);
  useEffect(() => {
    const group = effortGroup.current;
    if (!busy && !loading && group?.contains(document.activeElement)) {
      group.querySelector<HTMLButtonElement>('button[role="radio"][aria-checked="true"]')?.focus();
    }
  }, [busy, loading, config?.effort]);
  const label = config?.enabled
        ? `聊天：${provider?.name ?? config.provider} · ${config.model}（不扣草莓）`
        : "聊天：平台 · 每条 10 颗草莓";
  return <div className="flex min-w-0 flex-col items-end gap-1 max-md:items-start xl:flex-1">
    {chatMode && config ? <div className="flex max-w-full flex-wrap items-center justify-end gap-x-2 gap-y-1 max-md:justify-start xl:w-full xl:flex-nowrap">
      <span className="min-w-0 break-all xl:truncate" title={label}>{label}</span>
      {config.enabled && config.provider === "anthropic" && config.status === "ok" && <div ref={effortGroup} role="radiogroup" aria-label="思考强度"
        className="flex max-w-full flex-wrap items-center gap-1 xl:shrink-0 xl:flex-nowrap"
        onKeyDown={event => {
          if (busy || loading || !settings.available) return;
          const index = CLAUDE_EFFORTS.indexOf(config.effort);
          const nextIndex = event.key === "ArrowRight" ? (index + 1) % CLAUDE_EFFORTS.length
            : event.key === "ArrowLeft" ? (index + CLAUDE_EFFORTS.length - 1) % CLAUDE_EFFORTS.length : -1;
          if (nextIndex < 0) return;
          event.preventDefault();
          void changeEffort(CLAUDE_EFFORTS[nextIndex]);
          event.currentTarget.querySelectorAll<HTMLButtonElement>('button[role="radio"]')[nextIndex]?.focus();
        }}>
        <span aria-hidden="true">思考</span>
        {CLAUDE_EFFORTS.map(effort => <button key={effort} type="button" role="radio" aria-checked={config.effort === effort}
          tabIndex={config.effort === effort ? 0 : -1} title={CHAT_MODEL_EFFORT_TITLES[effort]} aria-disabled={busy !== null || loading || !settings.available}
          onClick={() => void changeEffort(effort)}
          className="btn btn-quiet h-7 shrink-0 px-2 text-xs aria-checked:bg-[color:var(--btn)] aria-checked:text-[color:var(--btnink)] aria-checked:hover:bg-[color:var(--btn)] aria-checked:hover:text-[color:var(--btnink)] aria-disabled:opacity-50 aria-disabled:cursor-default max-md:min-h-10">
          {CHAT_MODEL_EFFORT_LABELS[effort]}
        </button>)}
      </div>}
      <button type="button" disabled={busy !== null || loading || (!config.enabled && (config.status !== "ok" || !settings.available))}
        title={!config.enabled && config.status !== "ok" ? "请在设置中重新填写 Key" : undefined}
        onClick={() => void toggle()} className="btn btn-quiet h-7 shrink-0 px-2 text-xs max-md:min-h-10">
        {busy === "toggle" ? "正在切换…" : config.enabled ? "改用平台" : "改用我的模型"}
      </button>
    </div> : <span>每条消息消耗 <b className="readout">10</b> 颗草莓</span>}
    {chatMode && error && <div className="flex items-center gap-2 text-[color:var(--seal)]">
      <span role="alert">{error}</span>
      {!settings && <button type="button" disabled={busy !== null || loading} onClick={refresh}
        className="btn btn-quiet h-7 shrink-0 px-2 text-xs max-md:min-h-10">重试</button>}
    </div>}
  </div>;
}

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
    if (window.matchMedia("(width < 1024px)").matches) setShowHistory(false);
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
    const mobileBreakpoint = window.matchMedia("(width < 1024px)");
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
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'))
        .filter(element => element.getClientRects().length > 0);
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
      if (event.key !== "Escape" || !window.matchMedia("(width < 1024px)").matches) return;
      event.preventDefault();
      setShowHistory(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (restoreHistoryFocusRef.current && window.matchMedia("(width < 1024px)").matches) {
        trigger?.focus();
      }
      restoreHistoryFocusRef.current = false;
    };
  }, [showHistory]);
  const [username, setUsername] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const {
    agent, conversations, current: currentConversation, messages, setMessages,
    loading: conversationLoading, error: conversationError, reload: reloadConversations,
    hasMoreMessages, updateAgent,
    createConversation, selectConversation, deleteConversation, refreshList, getSelectionVersion,
  } = useConversations(username, hydrated && !!username);
  const [allUsers, setAllUsers] = useState<string[]>([]);
  const [voiceOn, setVoiceOn] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const [recording, setRecording] = useState(false);
  const [inlineRecording, setInlineRecording] = useState(false);
  const [micNotice, setMicNotice] = useState<string | null>(null);
  const [voiceText, setVoiceText] = useState("");
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [imageMode, setImageMode] = useState(false);
  const [preferredImageModel, setPreferredImageModel] = useState<ImageModelId>(DEFAULT_IMAGE_MODEL);
  const [imageModels, setImageModels] = useState(FALLBACK_IMAGE_MODELS);
  // Availability changes only the current selection, preserving the user's preference.
  const imageModel = imageModels.find(model => model.id === preferredImageModel)?.available
    ? preferredImageModel : DEFAULT_IMAGE_MODEL;
  const [referenceImages, setReferenceImages] = useState<ImageReferenceSelection | null>(null);
  const [aspectRatio, setAspectRatio] = useState<ImageAspectRatio>("1:1");
  const [isReadingImage, setIsReadingImage] = useState(false);
  const [isReadingReferences, setIsReadingReferences] = useState(false);
  const [referenceUploadError, setReferenceUploadError] = useState("");
  const [ttsWaitUntil, setTtsWaitUntil] = useState<number | null>(null);
  const [ttsWaitNow, setTtsWaitNow] = useState(0);
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
  const handsFreeRecRef = useRef<{ recorder: MediaRecorder | null; discard: boolean } | null>(null);
  const asrSessionRef = useRef(0);
  const ttsAudioPoolRef = useRef<TtsAudioSlot[] | null>(null);
  const ttsCurrentRef = useRef<PreparedTtsAudio | null>(null);
  const ttsPreloadRef = useRef<PreparedTtsAudio | null>(null);  // 预取下一句音频，消除句间空隙
  const ttsQueueRef = useRef<string[]>([]);
  const ttsPlayingRef = useRef(false);
  const [ttsPlaybackBlocked, setTtsPlaybackBlocked] = useState(false);
  const ttsBackoffRef = useRef<TtsBackoff>({ until: 0 });
  const playNextInQueueRef = useRef<() => void>(() => {});
  const ttsSessionRef = useRef(0);
  const ttsStoppedSessionRef = useRef<number | null>(null);
  const streamDoneRef = useRef(true);
  const synthRef = useRef<SpeechSynthesis | null>(null);
  const nlsWsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (ttsWaitUntil === null) return;
    const timer = window.setInterval(() => setTtsWaitNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [ttsWaitUntil]);

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
      setUsername(readStoredUsername());
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

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      let storedModel: ImageModelId = DEFAULT_IMAGE_MODEL;
      try {
        const stored = localStorage.getItem(IMAGE_MODEL_STORAGE_KEY);
        const option = FALLBACK_IMAGE_MODELS.find(model => model.id === stored);
        if (option) storedModel = option.id;
      } catch {
        // Keep the default when browser storage is unavailable.
      }
      setPreferredImageModel(storedModel);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!hydrated || !username) return;
    let cancelled = false;
    apiFetch(`${API}/image-models`)
      .then(async response => {
        if (!response.ok) throw new Error("Image models unavailable");
        const data = await response.json() as { models?: { id?: unknown; label?: unknown; available?: unknown }[] };
        if (!Array.isArray(data.models)) throw new Error("Invalid image models");
        const options = data.models;
        return FALLBACK_IMAGE_MODELS.map(option => {
          const model = options.find(candidate => candidate && candidate.id === option.id);
          if (!model || typeof model.available !== "boolean" || typeof model.label !== "string") {
            throw new Error("Invalid image model");
          }
          return { ...option, label: model.label, available: model.available };
        });
      })
      .then(models => {
        if (cancelled) return;
        setImageModels(models);
      })
      .catch(() => {
        if (!cancelled) setImageModels(FALLBACK_IMAGE_MODELS);
      });
    return () => { cancelled = true; };
  }, [hydrated, username]);

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
    if (!hydrated || !username) return;
    loadPeerRooms();
  }, [loadPeerRooms, hydrated, username]);

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
      let stream: MediaStream | null = null;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setMicNotice(null);
        if (selectionVersion !== getSelectionVersion()) {
          stream.getTracks().forEach(track => track.stop());
          return;
        }
        const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
        inlineMrRef.current = mr;
        inlineChunksRef.current = [];
        mr.ondataavailable = (e) => { if (e.data.size > 0) inlineChunksRef.current.push(e.data); };
        mr.onstop = async () => {
          stream?.getTracks().forEach(t => t.stop());
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
            if (res.status === 429 && "retry_after" in data) {
              setMicNotice(data.error);
              return;
            }
            if (data.text) handleSendRef.current(data.text);
          } catch (_) {}
        };
        mr.start();
        setInlineRecording(true);
      } catch (e) {
        stream?.getTracks().forEach(track => track.stop());
        const errorName = (e as { name?: string } | null)?.name;
        setMicNotice(errorName === "NotAllowedError" || errorName === "SecurityError"
          ? "没有麦克风权限，请在浏览器里允许使用麦克风"
          : "麦克风用不了");
      }
    }
  }, [inlineRecording, getSelectionVersion]);

  // ── 免提模式：朗读完自动录音，静音 1.5s 自动停 + 自动发 ──
  const startHandsFreeRecording = useCallback(async () => {
    if (!handsFreeRef.current || handsFreeRecRef.current) return;
    const selectionVersion = getSelectionVersion();
    const rec: { recorder: MediaRecorder | null; discard: boolean } = { recorder: null, discard: false };
    handsFreeRecRef.current = rec;
    let stream: MediaStream | null = null;
    let audioCtx: AudioContext | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setMicNotice(null);
      if (rec.discard || selectionVersion !== getSelectionVersion() || !handsFreeRef.current) {
        stream.getTracks().forEach(track => track.stop());
        if (handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
        return;
      }
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      rec.recorder = mr;
      const chunks: Blob[] = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };

      audioCtx = new AudioContext();
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
        if (handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
        stream?.getTracks().forEach(t => t.stop());
        audioCtx?.close().catch(() => {});
        if (rec.discard || selectionVersion !== getSelectionVersion() || !handsFreeRef.current) return;
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
          if (res.status === 429 && "retry_after" in data) {
            setHandsFree(false);
            setMicNotice(data.error.replace(/。$/, "") + "，免提已关闭");
            return;
          }
          if (data.text) handleSendRef.current(data.text);
        } catch (_) {}
      };

      mr.start();
      requestAnimationFrame(tick);
    } catch (e) {
      stream?.getTracks().forEach(track => track.stop());
      audioCtx?.close().catch(() => {});
      if (handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
      setHandsFree(false);
      const errorName = (e as { name?: string } | null)?.name;
      setMicNotice((errorName === "NotAllowedError" || errorName === "SecurityError"
        ? "没有麦克风权限，请在浏览器里允许使用麦克风"
        : "麦克风用不了") + "，免提已关闭");
      if (errorName === "NotAllowedError" || errorName === "SecurityError" || errorName === "NotFoundError") {
        console.warn('[handsfree] mic error', e);
      } else {
        console.error('[handsfree] mic error', e);
      }
    }
  }, [getSelectionVersion]);

  const stopHandsFreeRecording = useCallback(({ discard }: { discard: boolean }) => {
    const rec = handsFreeRecRef.current;
    if (!rec) return;
    if (discard) rec.discard = true;
    if (!rec.recorder) {
      if (discard && handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
      return;
    }
    if (rec.recorder.state === 'recording') {
      rec.recorder.stop();
      if (discard && handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
    }
  }, []);

  // ── 流式 TTS 队列：按句送合成、顺序播放，**预取下一句消除句间空隙** ──
  // 私聊原文仅进入 POST 请求体；<audio> 用一次性票据保留流式播放。
  const getTtsAudioPool = useCallback((): TtsAudioSlot[] => {
    if (!ttsAudioPoolRef.current) {
      // The only audio creation site: one pool of two elements for this component's lifetime.
      ttsAudioPoolRef.current = Array.from({ length: 2 }, () => {
        const audio = document.createElement("audio");
        audio.preload = "auto";
        return { audio, owner: null, unlocked: false, primeAttempt: null };
      });
    }
    return ttsAudioPoolRef.current;
  }, []);

  const primeTtsAudio = useCallback(() => {
    const silentSrc = getSilentTtsWavUri();
    for (const slot of getTtsAudioPool()) {
      if (slot.owner || slot.unlocked || slot.primeAttempt) continue;
      const attempt = {};
      slot.primeAttempt = attempt;
      slot.audio.src = silentSrc;
      const finish = (error?: unknown) => {
        if (slot.primeAttempt !== attempt) return;
        if (!error || !(typeof error === "object" && error !== null && "name" in error && error.name === "NotAllowedError")) {
          slot.unlocked = true;
        }
        slot.primeAttempt = null;
        if (!slot.owner && slot.audio.getAttribute("src") === silentSrc) {
          slot.audio.pause();
          slot.audio.removeAttribute("src");
          slot.audio.load();
        }
      };
      try {
        // This call must happen synchronously in the gesture, before any ticket request.
        Promise.resolve(slot.audio.play()).then(() => finish(), finish);
      } catch (error) {
        finish(error);
      }
    }
  }, [getTtsAudioPool]);

  const releaseTtsAudio = useCallback((prepared: PreparedTtsAudio) => {
    prepared.cancelled = true;
    prepared.controller.abort();
    prepared.listeners?.abort();
    prepared.listeners = null;
    const { slot } = prepared;
    if (slot.owner !== prepared) return;
    slot.owner = null;
    slot.audio.pause();
    slot.audio.removeAttribute("src");
    slot.audio.load();
  }, []);

  const mkTtsAudio = useCallback((text: string): PreparedTtsAudio | null => {
    const slot = getTtsAudioPool().find(candidate => !candidate.owner);
    if (!slot) return null;
    // A real sentence takes over a priming element only after silencing and clearing it.
    slot.audio.pause();
    slot.audio.removeAttribute("src");
    slot.audio.load();
    const controller = new AbortController();
    const session = ttsSessionRef.current;
    const prepared: PreparedTtsAudio = {
      text, slot, audio: slot.audio, session, ready: Promise.resolve(false),
      controller, listeners: null, cancelled: false, waitingUntil: null, ticketExpiresAt: null,
    };
    slot.owner = prepared;
    const canUse = () => slot.owner === prepared && !prepared.cancelled
      && !controller.signal.aborted && session === ttsSessionRef.current;
    prepared.ready = (async () => {
      try {
        const ticket = await requestTtsTicket({
          text: text.slice(0, 300),
          signal: controller.signal,
          backoff: ttsBackoffRef.current,
          isStale: () => !canUse(),
          onWait: until => {
            prepared.waitingUntil = until;
            if (ttsCurrentRef.current === prepared) {
              setTtsWaitNow(Date.now());
              setTtsWaitUntil(until);
            }
          },
          onWaitEnd: () => {
            prepared.waitingUntil = null;
            if (ttsCurrentRef.current === prepared) setTtsWaitUntil(null);
          },
        });
        if (!canUse() || !ticket) return false;
        slot.audio.src = `${API}/tts/stream?ticket=${encodeURIComponent(ticket.ticket)}`;
        prepared.ticketExpiresAt = Date.now() + ticket.expiresInMs;
        if (!canUse()) return false;
        slot.audio.load();
        return true;
      } catch {
        return false;
      }
    })();
    return prepared;
  }, [getTtsAudioPool]);

  // 当前句正在播时，把队头那句的音频提前 fetch 好，下一句结束时立刻接上
  const tryPrefetch = useCallback(() => {
    if (!ttsPlayingRef.current) return;
    if (ttsPreloadRef.current) return;
    const next = ttsQueueRef.current[0];
    if (!next) return;
    const prepared = mkTtsAudio(next);
    if (!prepared) return;
    ttsQueueRef.current.shift();
    ttsPreloadRef.current = prepared;
  }, [mkTtsAudio]);

  const finishCurrentTts = useCallback((prepared: PreparedTtsAudio) => {
    if (ttsCurrentRef.current !== prepared || prepared.slot.owner !== prepared || prepared.cancelled) return;
    ttsCurrentRef.current = null;
    ttsPlayingRef.current = false;
    setTtsPlaybackBlocked(false);
    setTtsWaitUntil(null);
    releaseTtsAudio(prepared);
    playNextInQueueRef.current();
  }, [releaseTtsAudio]);

  const playPreparedTts = useCallback((prepared: PreparedTtsAudio) => {
    if (ttsCurrentRef.current !== prepared || prepared.slot.owner !== prepared || prepared.cancelled) return;
    if (prepared.controller.signal.aborted || prepared.session !== ttsSessionRef.current) {
      finishCurrentTts(prepared);
      return;
    }
    if (!prepared.listeners) {
      // The ticket src is already installed; these listeners belong only to this sentence.
      const listeners = new AbortController();
      prepared.listeners = listeners;
      prepared.audio.addEventListener("ended", () => finishCurrentTts(prepared), { signal: listeners.signal });
      prepared.audio.addEventListener("error", () => finishCurrentTts(prepared), { signal: listeners.signal });
    }
    let playback: Promise<void>;
    try {
      playback = prepared.audio.play();
    } catch (error) {
      playback = Promise.reject(error);
    }
    void playback.then(() => {
      if (ttsCurrentRef.current === prepared && prepared.slot.owner === prepared && !prepared.cancelled) {
        prepared.slot.unlocked = true;
      }
    }).catch(error => {
      if (ttsCurrentRef.current !== prepared || prepared.slot.owner !== prepared || prepared.cancelled) return;
      if (error && typeof error === "object" && "name" in error && error.name === "NotAllowedError"
        && prepared.session === ttsSessionRef.current) {
        setTtsPlaybackBlocked(true);
      } else {
        finishCurrentTts(prepared);
      }
    });
  }, [finishCurrentTts]);

  const playNextInQueue = useCallback(() => {
    if (ttsPlayingRef.current) return;

    // 优先用已预取的，否则现 fetch
    let prepared = ttsPreloadRef.current;
    ttsPreloadRef.current = null;
    if (prepared && isTicketStale(prepared)) {
      releaseTtsAudio(prepared);
      ttsQueueRef.current.unshift(prepared.text);
      prepared = null;
    }
    if (!prepared) {
      const next = ttsQueueRef.current[0];
      if (!next) {
        if (streamDoneRef.current && handsFreeRef.current) {
          startHandsFreeRecording();
        }
        return;
      }
      prepared = mkTtsAudio(next);
      if (!prepared) return;
      ttsQueueRef.current.shift();
    }

    ttsPlayingRef.current = true;
    ttsCurrentRef.current = prepared;
    if (prepared.waitingUntil !== null) setTtsWaitNow(Date.now());
    setTtsWaitUntil(prepared.waitingUntil);
    // 立刻把"再下一句"也预取，与当前播放重叠
    tryPrefetch();
    prepared.ready.then(ready => {
      if (ttsCurrentRef.current !== prepared || prepared.slot.owner !== prepared || prepared.cancelled) return;
      if (!ready) { finishCurrentTts(prepared); return; }
      playPreparedTts(prepared);
    }).catch(() => finishCurrentTts(prepared));
  }, [startHandsFreeRecording, mkTtsAudio, tryPrefetch, finishCurrentTts, playPreparedTts, releaseTtsAudio]);

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
    if (ttsStoppedSessionRef.current === sessionId) return;
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
    const current = ttsCurrentRef.current;
    const preload = ttsPreloadRef.current;
    ttsCurrentRef.current = null;
    ttsPreloadRef.current = null;
    ttsPlayingRef.current = false;
    setTtsPlaybackBlocked(false);
    setTtsWaitUntil(null);
    if (current) releaseTtsAudio(current);
    if (preload) releaseTtsAudio(preload);
    // A click that clears the queue may have just primed an otherwise idle slot: stop the silent
    // audio but keep primeAttempt so finish() still classifies the resulting AbortError as unlocked (spec 3.2).
    for (const slot of ttsAudioPoolRef.current ? getTtsAudioPool() : []) {
      if (slot.owner || !slot.primeAttempt) continue;
      slot.audio.pause();
      slot.audio.removeAttribute("src");
      slot.audio.load();
    }
  }, [releaseTtsAudio, getTtsAudioPool]);

  // 用户显式停止（不听了 / 关朗读）：同一条流式回复的后续分句不再入队；
  // 若打断的是正在进行的朗读且流已结束、免提开着，补一次开麦，免提循环不能因此停住。
  const stopTtsByUser = useCallback(() => {
    const wasPlaying = ttsPlayingRef.current;
    ttsStoppedSessionRef.current = ttsSessionRef.current;
    clearTtsQueue();
    if (wasPlaying && streamDoneRef.current && handsFreeRef.current) startHandsFreeRecording();
  }, [clearTtsQueue, startHandsFreeRecording]);

  const resumeBlockedTts = useCallback(() => {
    const current = ttsCurrentRef.current;
    if (!current || !ttsPlaybackBlocked) return;
    const preload = ttsPreloadRef.current;
    if (preload && !preload.slot.unlocked) {
      ttsPreloadRef.current = null;
      ttsQueueRef.current.unshift(preload.text);
      releaseTtsAudio(preload);
    }
    if (isTicketStale(current)) {
      ttsCurrentRef.current = null;
      ttsPlayingRef.current = false;
      const remainingPreload = ttsPreloadRef.current;
      if (remainingPreload) {
        ttsPreloadRef.current = null;
        ttsQueueRef.current.unshift(remainingPreload.text);
        releaseTtsAudio(remainingPreload);
      }
      ttsQueueRef.current.unshift(current.text);
      releaseTtsAudio(current);
      primeTtsAudio();
      setTtsPlaybackBlocked(false);
      playNextInQueue();
      return;
    }
    primeTtsAudio();
    // Replay this ticket directly in the same gesture; do not fetch or load it again.
    playPreparedTts(current);
    setTtsPlaybackBlocked(false);
    tryPrefetch();
  }, [ttsPlaybackBlocked, releaseTtsAudio, primeTtsAudio, playPreparedTts, tryPrefetch, playNextInQueue]);

  useEffect(() => {
    const onGesture = () => {
      if (voiceOn && ttsAudioPoolRef.current?.some(slot => !slot.owner && !slot.unlocked && !slot.primeAttempt)) {
        primeTtsAudio();
      }
    };
    document.addEventListener("click", onGesture, true);
    document.addEventListener("keydown", onGesture, true);
    document.addEventListener("touchend", onGesture, true);
    return () => {
      document.removeEventListener("click", onGesture, true);
      document.removeEventListener("keydown", onGesture, true);
      document.removeEventListener("touchend", onGesture, true);
    };
  }, [voiceOn, primeTtsAudio]);

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
    stopHandsFreeRecording({ discard: true });
    clearTtsQueue();
    primeTtsAudio();
    if (!voiceOn) {
      ttsStoppedSessionRef.current = null;
      setVoiceOn(true);
    }
    ttsSessionRef.current += 1;
    if (!chatAbortRef.current) streamDoneRef.current = true;
    const t = normalizeForTTS(text.trim());
    if (t) {
      ttsQueueRef.current.push(t);
      playNextInQueue();
    }
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, pendingTtsText: undefined } : m)));
  }, [normalizeForTTS, playNextInQueue, voiceOn, setMessages, primeTtsAudio, clearTtsQueue, stopHandsFreeRecording]);

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
    if (!username || (!text && !pendingImage) || isLoading || chatAbortRef.current || conversationLoading || !currentConversation || isReadingImage || referenceReadControllerRef.current) return;
    if (imageRetry && pendingImage) return;
    if (imageRetry && (imageRetry.owner !== username || imageRetry.conversationId !== currentConversation.id)) return;
    const sentImage = pendingImage;
    let requestReferenceImages = imageRetry ? imageRetry.referenceImages ?? [] : selectedReferenceImages.map(image => ({ ...image.source }));
    if (requestReferenceImages.length && (sentImage || requestReferenceImages.length > 3
      || requestReferenceImages.some(image => image.image_path
        ? image.image_base64 !== undefined || referenceImagePath(image.image_path) !== image.image_path
        : !image.image_base64 || !isLocalReferenceDataUrl(image.image_base64)))) return;
    const requestMode = requestReferenceImages.length ? "image_edit" : (imageRetry || imageMode) && !sentImage ? "image" : "chat";
    const requestImageModel = imageModel;
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
      && readStoredUsername() === username;

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
    stopHandsFreeRecording({ discard: true });
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
    let imageGenerationFromTool = false;
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
          image_model: requestImageModel,
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
          if (data.crisis === true) {
            generatingImage = false;
            editingImage = false;
            setMessages((prev) => prev.map((m) => m.id === replyId
              ? { ...m, generationStatus: undefined, imageGenerationRetry: undefined } : m));
          }
          const replyModel = parseReplyModel(data.reply_model);
          if (replyModel) {
            setMessages(previous => previous.map(message => message.id === replyId
              ? { ...message, replyModelLabel: replyModel.label } : message));
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
            imageGenerationFromTool = imageGenerationFromTool || data.source === "tool";
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
            if (data.speak !== false) {
              ttsBuf += data.text;
              flushSentences();
            }
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
              : card.subtype === "weather" && card.weather && card.weather.forecast.length > 0
              ? (() => {
                  const w = card.weather;
                  const today = w.forecast[0];
                  const tomorrow = w.forecast[1];
                  let msg = `${w.location}今天${weatherForecastCondition(today)}`;
                  if (today.low.trim() && today.high.trim()
                    && Number.isFinite(Number(today.low)) && Number.isFinite(Number(today.high))) {
                    msg += `，${today.low}~${today.high}°`;
                  }
                  msg += "。";
                  if (tomorrow) msg += `明天${weatherForecastCondition(tomorrow)}。`;
                  const conditions = w.forecast.slice(0, 2).flatMap(f => [f.dayWeather, f.nightWeather]);
                  if (conditions.some(condition => condition.includes("雨"))) msg += "记得带伞。";
                  if (conditions.some(condition => condition.includes("雪"))) msg += "注意保暖、路滑。";
                  if (conditions.some(condition => condition.includes("雷"))) msg += "雷雨天尽量待在室内。";
                  return msg;
                })()
              : card.error
              ? card.points[0] || "这次没查到可靠的结果"
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
        imageGenerationRetry: generatingImage && !generatedImageReceived && !imageGenerationFromTool ? {
          prompt: text, aspectRatio: requestAspectRatio, imageModel: requestImageModel,
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
    if (!username || !file || imageMode || hasReferenceImages || referenceReadControllerRef.current || isLoading || conversationLoading || !currentConversation) return;
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
    if (!username || !files.length || conversationLocked || chatAbortRef.current || conversationLoading || !currentConversation
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
      && selectionVersion === getSelectionVersion() && readStoredUsername() === username;
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
      if (!username) return;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setActivePeer(room);
      setPeerMessages([]);
      setPeerConnected(false);

      // WebSocket 握手自动携带同源 HttpOnly Cookie；开发构建可用 dev_user。
      const devAuth = process.env.NODE_ENV !== "production"
        ? `?dev_user=${encodeURIComponent(readStoredUsername())}`
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
      if (conversationPickerOpen && window.matchMedia("(width < 1024px)").matches) {
        restoreConversationFocusRef.current = false;
        restoreHistoryFocusRef.current = true;
        setConversationPickerOpen(false);
        setShowHistory(true);
        return;
      }
      setConversationPickerOpen(false);
      setShowHistory(value => !value);
    },
    onFullHistory: () => { if (!username) return; setConversationPickerOpen(false); window.open(`/history?user=${encodeURIComponent(username)}`, "_blank", "noopener,noreferrer"); },
  };

  // ── render ──

  const imageModelGroup = (
    <div role="group" aria-label="图片模型" className="image-model-segments flex items-center gap-1 max-md:w-full"><span className="hidden shrink-0 text-xs text-[var(--ink2)] max-md:inline">模型</span>
      {imageModels.map(model => <button key={model.id} type="button" aria-pressed={imageModel === model.id} disabled={isLoading || !model.available}
        title={model.available ? model.label : "管理员尚未配置此模型"} onClick={() => {
          setPreferredImageModel(model.id);
          try {
            localStorage.setItem(IMAGE_MODEL_STORAGE_KEY, model.id);
          } catch {
            // The preference still works in memory when storage is unavailable.
          }
        }}
        className={cn("chip h-6 px-2 max-md:h-10", imageModel === model.id && "chip-on")}>
        {model.shortLabel}
      </button>)}
    </div>
  );

  return (
    <div className="chat-shell relative flex flex-col h-dvh overflow-hidden">
      <InkLandscape variant="chat" />
      <Glaze variant="panel" fur className="chat-left-material fixed bottom-3 left-3 top-3 z-[1] w-[calc(var(--rail-w)+288px-12px)] max-lg:w-[calc(var(--rail-w)-12px)] max-md:hidden" />
      <div className="flex flex-1 min-h-0 relative">
        {/* ── bookmark navigation ── */}
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
        <Glaze variant="panel"
          className="absolute left-[calc(var(--rail-w)+12px)] top-3 bottom-3 w-64 z-50 flex flex-col glaze-slide-in max-md:left-0 max-md:top-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] max-md:w-[min(85vw,320px)] max-md:rounded-none max-md:pt-[env(safe-area-inset-top)]"
          style={{ borderRight: "1px solid var(--glass-border)", boxShadow: "8px 0 32px var(--drop)" }}
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
        </Glaze>
        )}

        {/* ── subtle backdrop behind drawer (does NOT cover sidebar) */}
        {showHistory && (
          <div className="absolute left-[var(--rail-w)] top-0 bottom-0 right-0 z-40 bg-[var(--scrim)] transition-opacity max-md:left-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]" onClick={() => setShowHistory(false)} />
        )}

        <div className="flex flex-1 min-w-0 min-h-0">
          <ConversationPicker {...conversationPickerProps} glazed={false} className="relative z-[2] my-3 h-[calc(100%-24px)]! max-lg:hidden" />

          {conversationPickerOpen && <>
            <div className="fixed left-[var(--rail-w)] right-0 top-0 bottom-0 z-[61] bg-[var(--scrim)] lg:hidden max-md:left-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]" onClick={() => setConversationPickerOpen(false)} aria-hidden="true" />
            <div id="conversation-picker-dialog" ref={conversationDialogRef} role="dialog" aria-modal="true" aria-label="对话列表" tabIndex={-1}
              className="chat-conversation-modal fixed left-[calc(var(--rail-w)+12px)] top-3 bottom-3 z-[62] w-[min(85vw,320px)] glaze-slide-in outline-none lg:hidden max-md:left-0 max-md:top-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] max-md:rounded-none max-md:pt-[env(safe-area-inset-top)]">
              <ConversationPicker {...conversationPickerProps} />
            </div>
          </>}

          <div className="relative z-[1] flex-1 min-w-0" data-chat-panel>
            <Glaze as="header" variant="strip"
              className="chat-header absolute left-3 right-3 top-3 z-[2] grid h-16 grid-cols-[minmax(0,auto)_minmax(48px,1fr)_auto] items-center gap-6 rounded-[16px] px-6 max-md:inset-x-0 max-md:top-0 max-md:h-[calc(94px+env(safe-area-inset-top))] max-md:grid-cols-[minmax(0,1fr)_auto] max-md:grid-rows-[50px_24px] max-md:gap-0 max-md:rounded-none max-md:px-2 max-md:pt-[calc(6px+env(safe-area-inset-top))] max-md:pb-3.5"
            >
              <div className="flex min-w-0 items-center gap-3 max-md:gap-2">
                <button ref={conversationListButtonRef} type="button" aria-label="对话列表" aria-expanded={conversationPickerOpen} aria-controls={conversationPickerOpen ? "conversation-picker-dialog" : undefined}
                  onClick={() => { restoreConversationFocusRef.current = true; setConversationPickerOpen(true); }} className="btn btn-quiet hidden h-10 w-10 shrink-0 px-0 max-lg:inline-flex">
                  <PanelLeft size={20} />
                </button>
                {!anyDrawerOpen && <Seal variant="agent" avatar={agent?.avatar_emoji} size={36} className="max-md:w-7 max-md:h-7" />}
                <div className="min-w-0">
                  <div className="truncate text-[18px] font-medium max-md:text-base">{agent?.display_name || "我的分身"}</div>
                  <div className="flex gap-2 whitespace-nowrap text-xs text-muted-foreground max-lg:hidden"><span>AI 分身</span><span aria-hidden="true" className="h-3 border-l border-[var(--rule2)]" /><span>仅你可见</span></div>
                </div>
              </div>
              <Signal mode={signalMode} className="max-md:col-span-2 max-md:row-start-2 max-md:h-6" />
              <div className="flex items-center gap-2 max-md:col-start-2 max-md:row-start-1 max-md:shrink-0 max-md:gap-1">
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="whitespace-nowrap max-md:hidden">{signalMode === "listening" ? "正在听" : signalMode === "speaking" ? "正在说" : "待命"}</span>
                </span>
                <button type="button" className={cn("chip max-md:h-10 max-md:w-10 max-md:justify-center max-md:px-0", voiceOn && "chip-on")}
                  onClick={() => {
                    if (voiceOn) {
                      stopTtsByUser();
                      setVoiceOn(false);
                    } else {
                      ttsStoppedSessionRef.current = null;
                      primeTtsAudio();
                      setVoiceOn(true);
                    }
                  }} aria-label="朗读" aria-pressed={voiceOn}>
                  {voiceOn ? <Volume2 size={13} /> : <VolumeX size={13} />}<span className="max-md:hidden">朗读</span>
                </button>
                <button
                  type="button"
                  className={cn("chip max-md:h-10 max-md:w-10 max-md:justify-center max-md:px-0", handsFree && "chip-on")}
                  onClick={() => {
                    const next = !handsFree;
                    setHandsFree(next);
                    if (next) {
                      setMicNotice(null);
                      if (!voiceOn) ttsStoppedSessionRef.current = null;
                      primeTtsAudio();
                      setVoiceOn(true);
                    }
                  }}
                  disabled={conversationLoading || !currentConversation}
                  aria-label="免提"
                  aria-pressed={handsFree}
                  title="免提：分身说完自动开麦，你停顿 1.5 秒后自动发"
                >
                  <AudioLines size={13} className="md:hidden" /><span className="max-md:hidden">免提</span>
                </button>
                <span className="hidden shrink-0 flex-col items-end gap-0.5 whitespace-nowrap text-xs max-md:inline-flex" title="平台模型每条消息消耗 10 颗；自带模型聊天不扣">
                  <b className="readout" style={{ color: strawberryBalance !== null && strawberryBalance < 30 ? "var(--rec)" : "var(--foreground)" }}>
                    {strawberryBalance === null ? "…" : strawberryBalance}
                  </b>
                  <span className="text-[10.5px] text-[var(--ink2)]">草莓</span>
                </span>
              </div>
            </Glaze>
            <div className="chat-message-layer absolute inset-0 flex flex-col [mask-image:var(--chat-message-mask)]"
              style={{ "--composer-height": `${composerHeight}px` } as React.CSSProperties}>
              <ChatScrollArea ref={chatScrollRef} resetKey={`${username}:${currentConversation?.id ?? "loading"}`}>
                <div className="mx-auto flex w-full max-w-[760px] flex-col gap-7">
                  {hasMoreMessages && <p className="text-xs text-muted-foreground text-center">当前显示最近 500 条消息；更早记录可在历史页查看。</p>}
                  {messages.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center pt-8" role="status">{conversationLoading ? "正在加载对话…" : conversationError ? "对话加载失败，请在上方重试。" : currentConversation ? `和 ${agent?.display_name || "你的分身"} 开始新的交流。` : "点击上方“新对话”，开始和自己的分身交流。"}</p>
                  )}
                  {messages.map((msg, index) => (
                    <div key={`${username}-${currentConversation?.id}-${msg.id}`}>
                    {(index === 0 || msg.timestamp.toDateString() !== messages[index - 1].timestamp.toDateString()) && <div className="mb-7 flex items-center gap-[18px] text-xs tracking-[.32em] text-[var(--ink2)]"><span className="h-px flex-1 bg-[var(--rule)]" />{formatChineseDate(msg.timestamp)}<span className="h-px flex-1 bg-[var(--rule)]" /></div>}
                    <ChatBubble key={`${username}-${currentConversation?.id}-${msg.id}`} message={msg} agentName={agent?.display_name} onDelete={isLoading ? undefined : handleDeleteMessage} onConfirmTts={handleConfirmTts} onDeclineTts={handleDeclineTts}
                      onRetryImage={request => { void handleSend(request.prompt, request); }} onEditImage={handleSelectReferenceImage}
                      selectedReferenceImagePaths={selectedReferenceImagePaths}
                      imageRetryDisabled={conversationLocked || conversationLoading || !currentConversation || !!pendingImage || isReadingImage || isReadingReferences} />
                    </div>
                  ))}
                </div>
              </ChatScrollArea>
            </div>
            <Glaze as="footer" variant="slab" ref={composerRef} className="chat-composer absolute bottom-[18px] left-1/2 z-[2] w-[min(760px,calc(100%-48px))] -translate-x-1/2 rounded-[14px] px-[18px] pb-3 pt-3 max-md:inset-x-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] max-md:w-full max-md:translate-x-0 max-md:rounded-t-[18px] max-md:rounded-b-none max-md:px-2.5 max-md:pb-2">
              <div data-chat-composer className="mx-auto max-w-[760px]">
                <div role="status" aria-live="polite">
                  {ttsPlaybackBlocked && <div className="mb-2 flex min-w-0 items-center gap-1 text-xs">
                    <span className="min-w-0 flex-1 text-muted-foreground">浏览器拦下了自动朗读</span>
                    <button type="button" onClick={resumeBlockedTts} className="btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9">
                      <Volume2 size={13} />点此播放
                    </button>
                    <button type="button" onClick={stopTtsByUser} className="btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9">不听了</button>
                  </div>}
                  {ttsWaitUntil !== null && <div className="mb-2 flex min-w-0 items-center gap-1 text-xs">
                    <span className="min-w-0 flex-1 text-muted-foreground">
                      <span aria-hidden="true">朗读限速中，{Math.max(1, Math.ceil((ttsWaitUntil - ttsWaitNow) / 1000))} 秒后接着读</span>
                      <span className="sr-only">朗读限速中，稍后自动接着读</span>
                    </span>
                    <button type="button" onClick={stopTtsByUser} className="btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9">不听了</button>
                  </div>}
                  {micNotice && <div className="mb-2 flex min-w-0 items-center gap-1 text-xs">
                    <span className="min-w-0 flex-1 text-muted-foreground">{micNotice}</span>
                    <button type="button" onClick={() => setMicNotice(null)} className="btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9">知道了</button>
                  </div>}
                </div>
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
                <div className={cn("composer-inner flex flex-col max-md:grid gap-2 rounded-lg px-0 py-0 max-md:bg-[var(--tile)] max-md:px-3 max-md:py-2", (imageMode || hasReferenceImages) && "composer-with-model")}>
                  <div className="composer-text flex items-end gap-2">
                    {pendingImage && (
                      <div className="relative inline-block w-fit pt-1">
                        <img src={pendingImage} alt="待发送" className="rounded-xl max-h-20 max-w-[120px] object-cover border border-border" />
                        <button type="button" aria-label="移除待发送图片" onClick={() => setPendingImage(null)} className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-background border border-border flex items-center justify-center hover:bg-destructive hover:text-[var(--btnink)] transition-colors max-md:-right-4 max-md:h-10 max-md:w-10">
                          <X size={10} />
                        </button>
                      </div>
                    )}
                    <textarea ref={textareaRef} value={input} onChange={handleInput} onKeyDown={handleKeyDown}
                      disabled={conversationLoading || !currentConversation}
                      onCompositionStart={() => { isComposingRef.current = true; }}
                      onCompositionEnd={() => { isComposingRef.current = false; }}
                      placeholder={hasReferenceImages ? "描述修改要求，可用图1、图2、图3指定各图用途…" : imageMode ? "描述想生成的画面、风格和细节…" : pendingImage ? "说点什么…（可选）" : "说点什么…"} rows={1}
                      className="min-w-0 flex-1 resize-none bg-transparent text-base text-foreground placeholder:text-muted-foreground outline-none py-1 leading-relaxed max-h-[80px] max-md:text-base"
                    />
                  </div>
                  <div className="composer-toolbar flex max-md:contents flex-wrap items-center justify-between gap-2">
                    <div className="composer-mode-tools flex max-md:contents flex-wrap items-center gap-2">
                    <div className="composer-tools flex flex-wrap items-center gap-2 text-[11px]">
                      <input ref={referenceFileInputRef} type="file" multiple accept="image/png,image/jpeg,image/webp" onChange={handlePickReferenceImages} className="hidden" />
                      <button type="button" onClick={() => referenceFileInputRef.current?.click()}
                        disabled={conversationLocked || conversationLoading || !currentConversation || !!pendingImage || isReadingImage || isReadingReferences || selectedReferenceImages.length >= 3}
                        title={pendingImage ? "请先移除普通待发送图片" : selectedReferenceImages.length >= 3 ? "最多3张参考图，请先移除一张" : "选择 PNG、JPEG 或 WebP；每张不超过5MB，发送修改要求时才上传"}
                        className={cn("btn btn-quiet px-2 max-md:h-10", hasReferenceImages && "text-[var(--ink)]")}>
                        上传参考图
                      </button>
                      <span aria-hidden="true" className="h-3 border-l border-[var(--rule2)]" />
                      {isReadingReferences && <span role="status" className="text-muted-foreground">正在读取并检查参考图…</span>}
                      {hasReferenceImages ? <>
                        <span className="chip chip-on"><PencilLine size={12} />修改图片</span>
                        <span role="status" className="text-[color:var(--amber-ink)]">参考图 {selectedReferenceImagePaths.length}/3</span>
                        <span className="text-muted-foreground">尺寸跟随图1</span>
                      </> : imageMode ? <>
                        <span className="chip chip-on">生成图片</span>
                        <div role="group" aria-label="图片比例" className="flex items-center gap-1">
                          {(["1:1", "16:9", "9:16"] as const).map(ratio => <button key={ratio} type="button" aria-pressed={aspectRatio === ratio} disabled={isLoading}
                            onClick={() => setAspectRatio(ratio)} className={cn("chip h-6 px-2 max-md:h-10", aspectRatio === ratio && "chip-on")}>
                            {ratio}
                          </button>)}
                        </div>
                      </> : <>
                        <button type="button" onClick={() => setImageMode(true)} disabled={!!pendingImage || isReadingImage || isReadingReferences || conversationLocked || conversationLoading || !currentConversation}
                          title={pendingImage || isReadingImage ? "请先移除待发送图片，再切换到生成图片" : "用文字描述生成一张图片"}
                          className="btn btn-quiet px-2 max-md:h-10">
                          生成图片
                        </button>
                        {pendingImage && <span className="text-muted-foreground">先移除待发送图片，即可切换生成模式</span>}
                        {isReadingImage && <span role="status" className="text-muted-foreground">正在读取图片…</span>}
                      </>}
                    </div>
                    {(imageMode || hasReferenceImages) && imageModelGroup}
                    {hasReferenceImages ? (
                      <button type="button" disabled={conversationLocked || conversationLoading || isReadingReferences} onClick={clearReferenceImages} className="composer-mode-exit ml-auto flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-40 max-md:min-h-10"><X size={11} />全部取消</button>
                    ) : imageMode && (
                      <button type="button" disabled={isLoading} onClick={() => setImageMode(false)} className="composer-mode-exit ml-auto flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-40 max-md:min-h-10"><X size={11} />返回聊天</button>
                    )}
                    </div>
                    <div className="composer-actions flex items-center gap-0.5 ml-auto shrink-0">
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
                      onPointerDown={(e) => { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); setRecording(true); }}
                      onPointerUp={(e) => { e.preventDefault(); if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); asrSessionRef.current += 1; setRecording(false); }}
                      className={cn("btn btn-quiet h-8 px-2.5 text-xs max-md:h-10 max-md:w-10 max-md:px-0", recording && "text-[color:var(--rec)] bg-[color:var(--rec-soft)]")}
                      aria-label="按住说话"
                      disabled={conversationLoading || !currentConversation || isLoading}
                    >
                      <Mic size={14} /><span className="max-md:hidden">按住说话</span>
                    </button>
                    <button onClick={() => handleSend()} aria-label={hasReferenceImages ? "修改图片" : imageMode ? "生成图片" : "发送消息"} disabled={isLoading || isReadingImage || isReadingReferences || conversationLoading || !currentConversation || (!input.trim() && !pendingImage)}
                      className="btn btn-primary h-9 px-4 tracking-[.2em] max-md:h-10"
                    >{hasReferenceImages ? "修改" : imageMode ? "生成" : "发送"}</button>
                    </div>
                  </div>
                </div>
                {voiceText && <p className="mt-2 text-xs text-muted-foreground">{voiceText}</p>}
                <div className="mt-2 flex min-w-0 items-center justify-between gap-3 border-t border-[var(--carve)] pt-2 text-xs text-muted-foreground shadow-[inset_0_1px_0_var(--etch)] xl:flex-nowrap">
                  <span className="shrink-0 max-md:hidden">Enter 发送，Shift + Enter 换行</span>
                  <ChatModelFooter key={username} username={username} settingsOpen={settingsOpen} chatMode={!imageMode && !hasReferenceImages} loading={isLoading} />
                </div>
              </div>
            </Glaze>
          </div>
        </div>
      </div>

      {/* 分身直接复用管理组件，点击即时展开，不依赖整页路由切换。 */}
      <Glaze as="section" variant="panel"
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
        className="fixed top-3 bottom-3 right-3 z-[55] flex flex-col outline-none max-md:left-0 max-md:top-0 max-md:right-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]! max-md:w-screen! max-md:rounded-none max-md:pt-[env(safe-area-inset-top)]"
        style={{
          width: "min(960px, calc(100vw - var(--rail-w) - 12px))",
          borderLeft: "1px solid var(--glass-border)",
          ...drawerStyle(agentOpen),
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--glass-border)" }}>
          <span className="text-xs font-medium text-muted-foreground">分身</span>
          <button type="button" onClick={closeDrawer} aria-label="收起分身面板" className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground max-md:h-10 max-md:w-10">
            <X size={14} />
          </button>
        </div>
        {agentOpen && <MyAgentWorkspace embedded onSaved={updateAgent} />}
      </Glaze>

      <Glaze as="section" variant="panel"
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
        className="fixed top-3 bottom-3 right-3 z-[55] flex flex-col outline-none max-md:left-0 max-md:top-0 max-md:right-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]! max-md:w-screen! max-md:rounded-none max-md:pt-[env(safe-area-inset-top)]"
        style={{
          width: "min(960px, calc(100vw - var(--rail-w) - 12px))",
          borderLeft: "1px solid var(--glass-border)",
          ...drawerStyle(exchangeOpen),
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--glass-border)" }}>
          <span className="text-xs font-medium text-muted-foreground">分身广场</span>
          <button type="button" onClick={closeDrawer} aria-label="收起分身广场" className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground max-md:h-10 max-md:w-10"><X size={14} /></button>
        </div>
        {exchangeOpen && <AgentExchangeWorkspace embedded onOpenMyAgent={() => setDrawer("agent")} />}
      </Glaze>

      {/* 世界抽屉 — 从右侧滑出，覆盖 2/3 聊天区；不卸载 iframe，重开秒回原状态 */}
      <Glaze variant="panel"
        id="plaza-drawer"
        lens={false}
        backdrop={false}
        className="fixed top-3 bottom-3 right-3 z-[55] flex flex-col overflow-hidden max-md:left-0 max-md:top-0 max-md:right-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]! max-md:w-screen! max-md:rounded-none max-md:pt-[env(safe-area-inset-top)]"
        style={{
          width: "calc((100vw - var(--rail-w) - 12px) * 2 / 3)",
          borderLeft: "1px solid var(--glass-border)",
          ...drawerStyle(plazaOpen),
          willChange: "transform",
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ background: "var(--hi)", borderColor: "var(--glass-border)" }}>
          <span className="text-xs font-medium text-muted-foreground">世界</span>
          <div className="flex items-center gap-1 max-md:[&>button]:min-h-10">
            <button type="button" onClick={() => setWorldTab("plaza")} className={cn("chip", worldTab === "plaza" && "chip-on")}>热点与帖子</button>
            <button type="button" onClick={() => setWorldTab("match")} className={cn("chip", worldTab === "match" && "chip-on")}>匹配</button>
            <button
              onClick={closeDrawer}
              className="w-6 h-6 flex items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground max-md:h-10 max-md:w-10"
              title="收起" aria-label="收起"
            >
              <X size={14} />
            </button>
          </div>
        </div>
        {username ? (
          <iframe src={worldTab === "plaza" ? "/plaza?embed=1" : "/match?embed=1"} className="flex-1 w-full border-0" />
        ) : (
          <div role="status" className="flex-1 p-5 text-sm text-muted-foreground">正在加载身份…</div>
        )}
      </Glaze>

      {/* 设置抽屉 — 「我的」作为账户标签并入设置。 */}
      <Glaze variant="panel"
        id="settings-drawer"
        lens={false}
        backdrop={false}
        className="fixed top-3 bottom-3 right-3 z-[55] flex flex-col overflow-hidden max-md:left-0 max-md:top-0 max-md:right-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]! max-md:w-screen! max-md:rounded-none max-md:pt-[env(safe-area-inset-top)]"
        style={{
          width: "calc((100vw - var(--rail-w) - 12px) * 2 / 3)",
          borderLeft: "1px solid var(--glass-border)",
          ...drawerStyle(settingsOpen),
          willChange: "transform",
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ background: "var(--hi)", borderColor: "var(--glass-border)" }}>
          <span className="text-xs font-medium text-muted-foreground">设置</span>
          <div className="flex items-center gap-1 max-md:[&>button]:min-h-10">
            <button type="button" onClick={() => setSettingsTab("settings")} className={cn("chip", settingsTab === "settings" && "chip-on")}>设置</button>
            <button type="button" onClick={() => setSettingsTab("profile")} className={cn("chip", settingsTab === "profile" && "chip-on")}>账户</button>
            <button
              onClick={closeDrawer}
              className="w-6 h-6 flex items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground max-md:h-10 max-md:w-10"
              title="收起" aria-label="收起"
            >
              <X size={14} />
            </button>
          </div>
        </div>
        {username ? (
          <iframe src={settingsTab === "settings" ? "/settings?embed=1" : "/profile?embed=1"} className="flex-1 w-full border-0" />
        ) : (
          <div role="status" className="flex-1 p-5 text-sm text-muted-foreground">正在加载身份…</div>
        )}
      </Glaze>

      {/* 抽屉外部点击关闭 — 任一右侧抽屉打开时铺一层透明背板，盖在抽屉之下、聊天区之上。
          z-50 < 抽屉 z-55；left-[var(--rail-w)] 避开 sidebar 让侧栏始终可点切换抽屉 */}
      {anyDrawerOpen && (
        <div
          className="fixed left-[var(--rail-w)] top-0 right-0 bottom-0 z-50 bg-[var(--scrim)] max-md:left-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]"
          onClick={closeDrawer}
          aria-hidden
        />
      )}

    </div>
  );
}
