"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/auth";
import { API_BASE as API } from "@/lib/config";

// 火山豆包音乐 v4.3 的取值 → 中文说明。只收录卡片会展示的类别；
// 数据来自 docs/tasks/2026-10-18-song-agent-p0/refs/volc-v43-options.md。
export const GENRE_LABELS: Record<string, string> = {
  "Blues": "布鲁斯",
  "Trip Hop": "神游舞曲",
  "Chinese Folk": "国语民谣",
  "Chinese Opera": "中国戏曲",
  "Ambient": "氛围电子",
  "Contemporary Blues": "当代布鲁斯",
  "Chinese Style": "国风音乐",
  "Deep Pop Edm": "流行电子舞曲",
  "Contemporary Folk": "当代民谣",
  "Chinese Tradition": "中国传统",
  "EDM Trap": "陷阱舞曲",
  "Country Blues": "乡村布鲁斯",
  "Classical": "古典",
  "Future House": "未来浩室",
  "Emo Rap": "情绪说唱",
  "Country": "乡村",
  "China-Wave": "国风流行",
  "Gangsta Rap": "匪帮说唱",
  "DJ": "DJ",
  "GuFeng Music": "古风",
  "Hardstyle": "硬派舞曲",
  "Easy Listening": "轻音乐",
  "Chinoiserie Rap": "国风嘻哈",
  "Melbourne Bounce": "墨尔本弹跳",
  "Electronic": "电子",
  "Chinoiserie Electronic": "国风电子",
  "Pop Punk": "流行朋克",
  "Folk": "民谣",
  "Hard Rock": "硬摇滚",
  "Rock Blues": "摇滚布鲁斯",
  "Hip Hop/Rap": "嘻哈",
  "Pop Rock": "流行摇滚",
  "Thrash Metal": "激流金属",
  "Jazz": "爵士",
  "Alternative Rock": "另类摇滚",
  "Traditional Jazz": "传统爵士",
  "MC": "喊麦",
  "Indie Rock": "独立摇滚",
  "Breakbeat": "碎拍",
  "Metal": "金属",
  "Soft Rock": "轻摇滚",
  "Country Rock": "乡村摇滚",
  "Pop": "流行",
  "Jazz Pop": "流行爵士",
  "Jazz Blues": "爵士布鲁斯",
  "Punk": "朋克",
  "Bossa Nova": "巴塞诺瓦",
  "Bebop": "波普",
  "R&B/Soul": "节奏蓝调/灵魂",
  "Swing": "摇摆乐",
  "Brit Pop": "英伦流行",
  "Reggae": "雷鬼",
  "Big Band": "大乐队",
  "Bubblegum Bass": "泡泡糖贝斯",
  "Rock": "摇滚",
  "Cool Jazz": "冷爵士",
  "Chinese Ballad Pop": "国语抒情歌曲",
  "8 Bit": "8 Bit",
  "Trap Rap": "陷阱说唱",
  "Classical period": "古典主义音乐",
  "Alternative/Indie": "另类独立",
  "R&B Rap": "旋律说唱",
  "Classic R&B / Soul": "传统节奏布鲁斯/灵魂乐",
  "Chinese Pop": "国语流行",
  "Jazz Hip Hop": "爵士嘻哈",
  "Dancehall": "舞场雷鬼",
  "Teen Pop": "青少年流行",
  "Pop Rap": "流行说唱",
  "Deathcore": "死核",
  "Indie Pop": "独立流行",
  "Hardcore Rap": "硬核说唱",
  "Doo-Wop": "嘟喔普",
  "Dream Pop": "梦幻流行",
  "Hip House": "说唱浩室",
  "Downtempo": "缓拍",
  "City Pop": "都市流行",
  "Chill Beats": "弛放节拍",
  "Grunge Rock": "油渍摇滚",
  "Synth Pop": "合成器流行",
  "Funk": "放克音乐",
  "Gypsy Jazz": "吉普赛爵士",
  "Dance Pop": "流行舞曲",
  "Contemporary R&B": "当代节奏布鲁斯",
  "Hard Bop": "硬波普爵士",
  "Electropop": "电音流行",
  "Neo Soul": "新灵魂乐",
  "Hardcore": "硬核",
  "Chamber Pop": "室内流行",
  "Soul": "灵魂乐",
  "Modernism": "现代主义音乐",
  "EDM": "EDM",
  "Pop Soul": "流行灵魂乐",
  "Neo Funk": "新放克",
  "House": "浩室舞曲",
  "Glam Metal": "华丽金属",
  "Nu Metal": "新金属",
  "Dubstep": "回响贝斯",
  "Power Metal": "力量金属",
  "Post-Punk": "后朋克",
  "Future Bass": "未来贝斯",
  "Gospel": "福音音乐",
  "Progressive R&B": "前卫节奏布鲁斯",
  "Chillout": "驰放",
  "Traditional Chinese Folk": "传统民歌",
  "Synthwave": "合成器潮",
  "Trance": "出神舞曲",
  "Chinese Quyi": "中国曲艺",
  "Jersey Club": "泽西俱乐部",
  "Drum&Bass": "鼓与贝斯舞曲",
  "Folk Pop": "流行民谣",
  "Chinoiserie Rock": "国风摇滚",
  "Tropical House": "热带浩室",
  "Indie Folk": "独立民谣",
  "Midtempo": "中速节奏",
  "Disco": "迪斯科舞曲",
  "Boombap": "蹦啪说唱",
  "Kawaii Bass": "可爱贝斯",
  "Vaporwave": "蒸汽波",
  "Chillwave": "寒潮",
};

export const MOOD_LABELS: Record<string, string> = {
  "Angry/Aggressive": "生气/激进",
  "Romantic": "浪漫",
  "Calm/Relaxing": "平静",
  "Sorrow/Sad": "悲伤",
  "Chill": "轻松/放松",
  "Sweet_SA_MOOD": "甜蜜",
  "Cute/Playful": "可爱/调皮",
  "Thrilling/Suspenseful/Tense": "惊险/悬疑/紧张",
  "Dynamic/Energetic": "动态的/精力充沛的",
  "Weird": "奇怪",
  "Excited": "兴奋",
  "Groovy/Funky": "律动",
  "Funny": "有趣",
  "Nostalgic/Memory": "怀旧的/记忆",
  "Happy": "开心/快乐",
  "Dreamy/Ethereal": "梦幻/超凡脱俗的",
  "Healing": "治疗",
  "Magnificent/Epic": "震撼/壮丽",
  "Inspirational/Hopeful": "鼓舞人心的/希望的",
  "Brisk/Carefree": "轻快/自在的",
  "Sentimental/Melancholic/Lonely": "多愁善感/忧郁/孤单",
  "Warm/Kind": "温暖/友好的",
  "Miss": "想念",
  "Confident/Determined": "自信/坚定的",
  "Mysterious": "神秘",
  "Lyrical/Ballad": "抒情的",
};

export const TIMBRE_LABELS: Record<string, string> = {
  "Warm": "温暖",
  "Magnetic": "磁性的",
  "Uncle Like": "大叔风",
  "Ethereal": "空灵的",
  "Bel Canto": "美声",
  "Gritty": "粗犷的",
  "Husky": "烟嗓",
  "Gentle": "温柔的",
  "Romantic_AUDIO_TIMBRE": "浪漫的",
  "Deep": "低沉的",
  "Delicate": "细腻的",
  "Enthusiastic": "热情的",
  "Extreme": "极端的",
  "Energetic": "热血的",
  "Smoky": "烟嗓",
  "Sharp": "锐利的",
  "Sassy": "时髦自信的",
  "Chinese Opera Tune": "中国戏腔",
  "Bright": "明亮",
  "Refreshing": "清新的",
  "Round": "圆润的",
  "Powerful": "高亢",
  "Soothing": "治愈的",
  "Flat": "平淡",
  "Sexy/Lazy": "慵懒",
  "Comical": "滑稽的",
  "Growling": "嘶吼",
};

export const KMODE_LABELS: Record<string, string> = {
  "Major": "大调",
  "Minor": "小调",
};

export const TEMPO_LABELS: Record<string, string> = {
  "Grave": "庄板",
  "Adagio": "慢板",
  "Moderato": "中板",
  "Largo": "广板",
  "Andante": "行板",
  "Allegro": "快板",
  "Vivace": "活泼的快板",
  "Presto": "急板",
};

export const LANG_LABELS: Record<string, string> = {
  "Chinese": "普通话",
  "English": "英文",
  "Cantonese": "粤语",
};

const GENDER_LABELS: Record<string, string> = {
  Female: "女声",
  Male: "男声",
};

export type SongSectionType =
  | "intro"
  | "verse"
  | "pre-chorus"
  | "chorus"
  | "bridge"
  | "inst"
  | "outro"
  | "hook"
  | "build-up"
  | "drop"
  | "solo";

const SECTION_TYPE_LABELS: Record<string, string> = {
  intro: "前奏",
  verse: "主歌",
  "pre-chorus": "导歌",
  chorus: "副歌",
  bridge: "桥段",
  inst: "间奏",
  outro: "尾奏",
  hook: "记忆点",
  "build-up": "铺垫",
  drop: "高潮段",
  solo: "独奏",
};

const INSTRUMENTAL_TYPES = new Set<string>(["intro", "inst", "outro", "solo"]);

export const SONG_ACTIVE_STATUSES = [
  "queued",
  "submitting",
  "submitted",
  "running",
  "downloading",
] as const;

export interface SongLineCheck {
  section_id: string;
  line_index: number;
  chars: number;
  rhyme_group: string | null;
  rhyme_ok: boolean | null;
}

export interface SongIssue {
  code: string;
  section_id?: string | null;
  line_index?: number | null;
  message: string;
}

export interface SongCheck {
  ok: boolean;
  errors: SongIssue[];
  warnings: SongIssue[];
  lines: SongLineCheck[];
  provider_text?: string;
  provider_chars?: number;
}

export interface SongSection {
  id: string;
  type: string;
  lines: string[];
}

export interface SongLyrics {
  revision: number;
  sections: SongSection[];
  check: SongCheck;
  changed_section_ids?: string[];
}

export interface SongVersion {
  id: string;
  lyrics_revision: number;
  status: string;
  progress: number;
  failure_message?: string | null;
  duration_s?: number | null;
  created_at: string;
}

export interface SongBrief {
  theme?: string;
  occasion?: string;
  recipient?: string;
  language?: string;
  duration_seconds?: number;
  gender?: string;
  genre?: string[];
  genre_extra?: string[];
  mood?: string[];
  timbre?: string[];
  key?: string;
  kmode?: string;
  tempo?: string;
  instrument?: string[];
  scene?: string[];
  style_notes?: string;
}

export interface SongStructureSection {
  id: string;
  type: string;
  lines: number;
  chars?: [number, number];
  rhyme?: string;
}

export interface SongProject {
  id: string;
  title: string;
  brief: SongBrief;
  structure: SongStructureSection[];
  lyrics_revision: number;
  lyrics: SongLyrics | null;
  versions: SongVersion[];
  price_strawberries: number;
  can_generate: boolean;
  generate_blocked_reason: string | null;
  configured: boolean;
  changed_section_ids?: string[];
}

export function labelFrom(
  labels: Record<string, string>,
  value: string | null | undefined,
): string {
  const key = typeof value === "string" ? value.trim() : "";
  return key ? labels[key] ?? key : "";
}

export function genreLabel(value: string | null | undefined): string {
  return labelFrom(GENRE_LABELS, value);
}

export function moodLabel(value: string | null | undefined): string {
  return labelFrom(MOOD_LABELS, value);
}

export function tempoLabel(value: string | null | undefined): string {
  return labelFrom(TEMPO_LABELS, value);
}

export function kmodeLabel(value: string | null | undefined): string {
  return labelFrom(KMODE_LABELS, value);
}

export function timbreLabel(value: string | null | undefined): string {
  return labelFrom(TIMBRE_LABELS, value);
}

export function langLabel(value: string | null | undefined): string {
  return labelFrom(LANG_LABELS, value);
}

export function genderLabel(value: string | null | undefined): string {
  return labelFrom(GENDER_LABELS, value);
}

export function sectionTypeLabel(type: string): string {
  return SECTION_TYPE_LABELS[type] ?? type;
}

export function isInstrumentalType(type: string): boolean {
  return INSTRUMENTAL_TYPES.has(type);
}

export function isSongActiveStatus(status: string): boolean {
  return (SONG_ACTIVE_STATUSES as readonly string[]).includes(status);
}

export function formatSongDuration(seconds: number | null | undefined): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) return "";
  const whole = Math.round(seconds);
  if (whole % 60 === 0) return `${whole / 60} 分钟`;
  if (whole < 60) return `${whole} 秒`;
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分钟`;
}

export function formatKeyMode(
  key: string | null | undefined,
  kmode: string | null | undefined,
): string {
  return [typeof key === "string" ? key.trim() : "", kmodeLabel(kmode)].filter(Boolean).join(" ");
}

function normalizedList(value: string[] | string | null | undefined): string[] {
  if (Array.isArray(value)) {
    return value.flatMap(item => typeof item === "string" && item.trim() ? [item.trim()] : []);
  }
  if (typeof value === "string" && value.trim()) {
    return value.split(/[,，]/).flatMap(item => item.trim() ? [item.trim()] : []);
  }
  return [];
}

function joinedLabels(
  labels: Record<string, string>,
  value: string[] | string | null | undefined,
): string {
  return normalizedList(value).map(item => labelFrom(labels, item)).filter(Boolean).join("、");
}

/** 卡片简报行的 tag 文本，顺序固定为语言、时长、曲风、情绪、调式、速度、人声。 */
export function songBriefTags(brief: SongBrief | null | undefined): string[] {
  if (!brief) return [];
  const tags: string[] = [];
  const language = langLabel(brief.language);
  if (language) tags.push(language);
  const duration = formatSongDuration(brief.duration_seconds);
  if (duration) tags.push(duration);
  const genre = joinedLabels(GENRE_LABELS, [
    ...normalizedList(brief.genre),
    ...normalizedList(brief.genre_extra),
  ]);
  if (genre) tags.push(genre);
  const mood = joinedLabels(MOOD_LABELS, brief.mood);
  if (mood) tags.push(mood);
  const keyMode = formatKeyMode(brief.key, brief.kmode);
  if (keyMode) tags.push(keyMode);
  const tempo = tempoLabel(brief.tempo);
  if (tempo) tags.push(tempo);
  const gender = genderLabel(brief.gender);
  if (gender) tags.push(gender);
  return tags;
}

export function parseSongTimestamp(value: string | null | undefined): number {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return Number.NaN;
  return Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(text) ? text : `${text.replace(" ", "T")}Z`);
}

export function formatElapsed(createdAt: string, now = Date.now()): string {
  const start = parseSongTimestamp(createdAt);
  if (!Number.isFinite(start)) return "";
  const total = Math.max(0, Math.floor((now - start) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes < 1) return `已用 ${seconds} 秒`;
  if (minutes < 60) return seconds ? `已用 ${minutes} 分 ${seconds} 秒` : `已用 ${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  return `已用 ${hours} 时 ${minutes % 60} 分 ${seconds} 秒`;
}

/** 只对合法的 32 位小写十六进制版本 id 拼音频地址；其他输入一律返回 null。 */
export function songAudioUrl(versionId: string): string | null {
  return /^[0-9a-f]{32}$/.test(versionId) ? `${API}/songs/versions/${versionId}/audio` : null;
}

export async function generateSong(projectId: string, lyricsRevision: number): Promise<SongVersion> {
  const idempotencyKey = crypto.randomUUID().replace(/-/g, "");
  const response = await apiFetch(
    `${API}/songs/projects/${encodeURIComponent(projectId)}/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lyrics_revision: lyricsRevision,
        idempotency_key: idempotencyKey,
      }),
    },
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : `生成请求失败（${response.status}）`);
  }
  if (!data || typeof data.id !== "string") {
    throw new Error("服务器未返回完整数据，请重试。");
  }
  return data as SongVersion;
}

const POLL_INTERVAL_MS = 4000;
const MAX_INFLIGHT_MS = 15 * 60 * 1000;

function parseTimeOrNull(version: SongVersion): number | null {
  const parsed = parseSongTimestamp(version.created_at);
  return Number.isFinite(parsed) ? parsed : null;
}

/** 最老在途版本超过 15 分钟即停止轮询；时间缺失时继续轮询，避免接口异常导致永远不刷新。 */
function shouldPoll(project: SongProject): boolean {
  const active = (project.versions ?? []).filter(version => isSongActiveStatus(version.status));
  if (!active.length) return false;
  const createdTimes = active
    .map(parseTimeOrNull)
    .filter((time): time is number => time !== null);
  if (!createdTimes.length) return true;
  return Date.now() - Math.min(...createdTimes) <= MAX_INFLIGHT_MS;
}

class SongProjectNotFound extends Error {}

async function fetchSongProject(projectId: string, signal: AbortSignal): Promise<SongProject> {
  const response = await apiFetch(
    `${API}/songs/projects/${encodeURIComponent(projectId)}`,
    { signal, cache: "no-store" },
  );
  if (response.status === 404) throw new SongProjectNotFound("这个写歌项目已删除");
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string" ? detail : `写歌项目读取失败（${response.status}）`,
    );
  }
  if (!data || typeof data.id !== "string") throw new Error("服务器未返回完整数据，请重试。");
  return data as SongProject;
}

/**
 * 读取写歌项目快照。有在途版本时每 4 秒刷新；页面隐藏时暂停；
 * 最老在途版本超过 15 分钟时停止轮询。卸载或 projectId 变化时取消请求。
 */
export function useSongProject(projectId: string) {
  const [state, setState] = useState<{
    projectId: string;
    project: SongProject | null;
    loading: boolean;
    error: string;
    notFound: boolean;
  }>(() => ({ projectId, project: null, loading: true, error: "", notFound: false }));
  const refreshRef = useRef<() => void>(() => {});

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let current = new AbortController();
    let latest: SongProject | null = null;
    let runId = 0;

    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const schedule = () => {
      clearTimer();
      if (cancelled || !latest || !shouldPoll(latest)) return;
      if (typeof document !== "undefined" && document.hidden) return;
      timer = setTimeout(() => {
        timer = null;
        void load();
      }, POLL_INTERVAL_MS);
    };

    const load = async () => {
      if (cancelled) return;
      const thisRun = ++runId;
      current.abort();
      const controller = new AbortController();
      current = controller;
      try {
        const data = await fetchSongProject(projectId, controller.signal);
        if (cancelled || thisRun !== runId) return;
        latest = data;
        setState({ projectId, project: data, loading: false, error: "", notFound: false });
      } catch (cause) {
        if (cancelled || thisRun !== runId || controller.signal.aborted) return;
        if (cause instanceof SongProjectNotFound) {
          latest = null;
          setState({ projectId, project: null, loading: false, error: "", notFound: true });
        } else if (!latest) {
          setState(previous => ({
            ...previous,
            projectId,
            project: null,
            loading: false,
            error: cause instanceof Error ? cause.message : "写歌项目读取失败",
            notFound: false,
          }));
        }
      } finally {
        if (!cancelled && thisRun === runId) schedule();
      }
    };

    const onVisibilityChange = () => {
      if (cancelled) return;
      if (document.hidden) {
        clearTimer();
        return;
      }
      if (latest && shouldPoll(latest)) void load();
    };

    refreshRef.current = () => {
      if (!cancelled) {
        clearTimer();
        void load();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    void load();

    return () => {
      cancelled = true;
      clearTimer();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      current.abort();
      refreshRef.current = () => {};
    };
  }, [projectId]);

  const refresh = useCallback(() => {
    setState(previous => previous.projectId === projectId && previous.project === null
      ? { ...previous, loading: true, error: "", notFound: false }
      : previous);
    refreshRef.current();
  }, [projectId]);
  const sameProject = state.projectId === projectId;

  return {
    project: sameProject ? state.project : null,
    loading: sameProject ? state.loading : true,
    error: sameProject ? state.error : "",
    refresh,
    notFound: sameProject ? state.notFound : false,
  };
}
