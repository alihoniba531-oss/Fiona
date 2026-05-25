"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import SolarSystem3D from "@/components/SolarSystem3D";
import { Plus, Heart, ImageIcon, Video, X, Check, Sparkles, Music2, BarChart2, Cpu, BookOpen, Newspaper, Flame, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/auth";

const API = "/api";

const ALL_TAGS = ["日常", "风景", "美食", "创意", "情感", "搞笑", "音乐", "运动", "宠物", "穿搭", "旅行", "随拍"];

interface Post {
  id: number;
  anon_id: string;
  media_path: string;
  media_type: "image" | "video";
  caption: string;
  tags: string[];
  likes: number;
  created_at: string;
}

function timeAgo(ts: string) {
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

// ─────────────────── 帖子卡 ───────────────────
function PostCard({ post, username }: { post: Post; username: string }) {
  const [liked, setLiked] = useState(false);
  const [likes, setLikes] = useState(post.likes);
  const [burst, setBurst] = useState(0);
  const burstTimer = useRef<number | null>(null);

  const handleLike = async () => {
    if (liked) return;
    setLiked(true);
    setLikes((l) => l + 1);
    setBurst((b) => b + 1);
    if (burstTimer.current) window.clearTimeout(burstTimer.current);
    burstTimer.current = window.setTimeout(() => setBurst(0), 800);
    try {
      await apiFetch(`${API}/plaza/like/${post.id}`, { method: "POST" });
    } catch {}
  };

  return (
    <div className="plaza-card group">
      <div className="relative aspect-square bg-black/40 overflow-hidden">
        {post.media_type === "video" ? (
          <video
            src={`${API}${post.media_path}`}
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
            muted loop playsInline
            onMouseEnter={(e) => (e.currentTarget as HTMLVideoElement).play()}
            onMouseLeave={(e) => { const v = e.currentTarget as HTMLVideoElement; v.pause(); v.currentTime = 0; }}
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`${API}${post.media_path}`}
            alt=""
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
          />
        )}

        <div className="absolute top-2 right-2 flex flex-col items-end gap-1">
          {post.media_type === "video" && (
            <div className="rounded-full bg-black/60 backdrop-blur-sm p-1 border border-cyan-400/30">
              <Video size={10} className="text-cyan-300" />
            </div>
          )}
          {post.likes >= 5 && (
            <div className="flex items-center gap-0.5 rounded-full bg-orange-500/20 backdrop-blur-sm px-1.5 py-0.5 border border-orange-400/40">
              <Flame size={9} className="text-orange-300" />
              <span className="text-[9px] font-semibold text-orange-200">HOT</span>
            </div>
          )}
        </div>

        {post.tags.length > 0 && (
          <div className="absolute bottom-2 left-2 flex flex-wrap gap-1 max-w-[80%]">
            {post.tags.slice(0, 2).map((t) => (
              <span key={t} className="text-[9px] px-2 py-0.5 rounded-full bg-black/60 text-cyan-200 font-medium backdrop-blur-sm border border-cyan-400/30">
                #{t}
              </span>
            ))}
            {post.tags.length > 2 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-black/60 text-cyan-300/70 backdrop-blur-sm border border-cyan-400/20">
                +{post.tags.length - 2}
              </span>
            )}
          </div>
        )}

        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/70 to-transparent" />
      </div>

      <div className="px-3 py-2.5">
        {post.caption && (
          <p className="text-[12px] text-foreground/85 leading-relaxed mb-1.5 line-clamp-2">{post.caption}</p>
        )}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center"
              style={{
                background: "radial-gradient(circle at 30% 30%, rgba(0,212,255,0.55), rgba(0,90,140,0.85))",
                boxShadow: "inset 0 0 6px rgba(0,212,255,0.5), 0 0 8px rgba(0,212,255,0.3)",
              }}
            >
              <span className="text-[9px] font-semibold text-cyan-50 tracking-wider">{post.anon_id[0].toUpperCase()}</span>
            </div>
            <span className="text-[10px] text-muted-foreground hud-label">{post.anon_id}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-muted-foreground/80 tabular-nums">{timeAgo(post.created_at)}</span>
            <button
              onClick={handleLike}
              className={cn("relative flex items-center gap-1 transition-colors", liked ? "text-rose-400" : "text-muted-foreground hover:text-rose-300")}
            >
              <Heart size={13} fill={liked ? "currentColor" : "none"} className={burst ? "hud-like-burst" : undefined} />
              <span className="text-[11px] tabular-nums">{likes}</span>
              {burst > 0 && <span key={burst} className="hud-like-pop">+1</span>}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────── 分类热搜卡 ───────────────────
function CategoryCard({
  title, accent, icon: Icon, items, style, onItemClick,
}: {
  title: string;
  accent: string;
  icon: React.ComponentType<{ size?: number; className?: string; style?: React.CSSProperties }>;
  items: string[];
  style: React.CSSProperties;
  onItemClick?: (title: string) => void;
}) {
  // 去掉标题前的序号 "01. " 和尾部的 " · 12.3万"，得到纯净的话题文本
  const cleanTitle = (raw: string): string => {
    let s = raw.replace(/^\d+\.\s*/, "");
    s = s.replace(/\s*·\s*[\d.]+[万亿千]?$/, "");
    return s.trim();
  };
  return (
    <div
      className="z-20 w-[220px] hud-card-float px-3 py-2 pointer-events-auto"
      style={{ ...style, borderColor: accent + "44" }}
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon size={10} style={{ color: accent }} />
        <span className="hud-label text-[9px]" style={{ color: accent, textShadow: `0 0 6px ${accent}88` }}>
          {title}
        </span>
        <span className="ml-auto hud-pulse" style={{ background: accent, boxShadow: `0 0 5px ${accent}` }} />
      </div>
      <ul className="space-y-1">
        {items.length === 0 ? (
          <li className="text-[10px] text-muted-foreground/50">拉取中…</li>
        ) : (
          items.slice(0, 4).map((it, i) => (
            <li
              key={i}
              className="text-[11px] leading-snug text-foreground/80 flex gap-1.5 cursor-pointer hover:text-white transition-colors"
              onClick={() => onItemClick?.(cleanTitle(it))}
              style={{ borderRadius: 3 }}
              title="点开查看详情"
            >
              <span className="tabular-nums shrink-0 text-[9px] mt-0.5" style={{ color: accent + "99" }}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="truncate">{it}</span>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

// ─────────────────── 主页 ───────────────────
export default function PlazaPage() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [uploading, setUploading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<"image" | "video">("image");
  const [caption, setCaption] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [username, setUsername] = useState("默认用户");
  const [hydrated, setHydrated] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const selectedFile = useRef<File | null>(null);

  // 分类热搜数据
  type CatMap = Record<string, string[]>;
  const [cats, setCats] = useState<CatMap>({
    娱乐: [], 经济: [], 生活: [], 历史: [], 哲学: [], 科技: [], 文化: [], 时事: [],
  });
  // 热点话题展开
  type ExpandedTopic = {
    title: string;
    summary?: string;
    whats_happening?: string;
    why_trending?: string;
    key_facts?: string[];
    background?: string;
    sources?: { title: string; url: string }[];
    error?: string;
  };
  const [expanded, setExpanded] = useState<ExpandedTopic | null>(null);
  const [expanding, setExpanding] = useState(false);

  const openTopic = useCallback(async (title: string) => {
    if (!title) return;
    setExpanded({ title });  // 立刻显示标题占位
    setExpanding(true);
    try {
      const res = await apiFetch(`${API}/hot/expand?title=${encodeURIComponent(title)}`);
      const data = await res.json();
      setExpanded({ title, ...data });
    } catch (e: any) {
      setExpanded({ title, error: e?.message || "拉取失败" });
    } finally {
      setExpanding(false);
    }
  }, []);

  const [hotNews,  setHotNews]  = useState<string[]>([]);
  const [trending, setTrending] = useState<string[]>([]);
  const [interests, setInterests] = useState<string[]>([]);
  const [communityItems, setCommunityItems] = useState<{ tag: string; user: string }[]>([]);

  useEffect(() => {
    const u = localStorage.getItem("fiona_user");
    if (u) setUsername(u);
    setHydrated(true);
  }, []);

  const loadPosts = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "30" });
      const r = await apiFetch(`${API}/plaza/feed?${params}`);
      const data = await r.json();
      setPosts(data.posts || []);
    } catch {}
  }, []);
  useEffect(() => {
    if (!hydrated) return; // 等 localStorage hydrate 完再拉，免得用"默认用户"先拉一次
    loadPosts();
  }, [loadPosts, hydrated]);

  // 拉热搜 / 潮流（贴边）
  useEffect(() => {
    const grab = (src: string, set: (v: string[]) => void) =>
      apiFetch(`${API}/hot/${encodeURIComponent(src)}`)
        .then((r) => r.json())
        .then((d) => {
          // points 形如 "1. 标题 · 154万" — 去掉序号方便重新编号
          const items: string[] = (d.points || []).map((p: string) => p.replace(/^\d+\.\s*/, ""));
          set(items.slice(0, 5));
        })
        .catch(() => {});
    grab("微博", setHotNews);
    grab("抖音", setTrending);
    // 同时拉一份按类目分桶的热搜（娱乐/经济/生活/历史/哲学 等）
    const grabCats = () =>
      apiFetch(`${API}/hot/categorized/all`)
        .then((r) => r.json())
        .then((d) => setCats(d.categories || {}))
        .catch(() => {});
    grabCats();
    const id = window.setInterval(() => {
      grab("微博", setHotNews);
      grab("抖音", setTrending);
      grabCats();
    }, 5 * 60_000); // 5 分钟刷一次
    return () => window.clearInterval(id);
  }, []);

  // 拉用户兴趣（当前时段 top tags）
  useEffect(() => {
    if (!hydrated || !username) return;
    apiFetch(`${API}/plaza/time-prefs`)
      .then((r) => r.json())
      .then((d) => {
        const slot = d.time_slot;
        const prefs = (d.prefs && d.prefs[slot]) || d.prefs?.global || {};
        const arr = Object.entries(prefs)
          .map(([tag, score]) => ({ tag, score: Number(score) || 0 }))
          .sort((a, b) => b.score - a.score)
          .slice(0, 5);
        setInterests(arr.map((x) => `#${x.tag}`));
      })
      .catch(() => {});
  }, [username, hydrated]);

  // 拉社区其他用户兴趣（底部 ticker）
  useEffect(() => {
    if (!hydrated || !username) return;
    apiFetch(`${API}/plaza/community-interests`)
      .then((r) => r.json())
      .then((d) => setCommunityItems(d.items || []))
      .catch(() => {});
  }, [username, hydrated]);

  const togglePostTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : prev.length < 5 ? [...prev, tag] : prev
    );
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    selectedFile.current = file;
    setPreviewType(file.type.startsWith("video/") ? "video" : "image");
    setPreview(URL.createObjectURL(file));
    setShowModal(true);
  };

  const handleSubmit = async () => {
    if (!selectedFile.current || uploading) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("caption", caption);
      form.append("tags", JSON.stringify(selectedTags));
      form.append("file", selectedFile.current);
      await apiFetch(`${API}/plaza/post`, { method: "POST", body: form });
      handleClose();
      await loadPosts();
    } catch {}
    setUploading(false);
  };

  const handleClose = () => {
    setShowModal(false);
    setPreview(null);
    setCaption("");
    setSelectedTags([]);
    selectedFile.current = null;
    if (fileRef.current) fileRef.current.value = "";
  };

  const searchParams = useSearchParams();
  const embedded = searchParams?.get("embed") === "1";

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      {!embedded && <TopBar />}
      <div className="flex flex-1 min-h-0 relative">
        {!embedded && <Sidebar />}

        <main className="flex flex-col flex-1 min-w-0 relative overflow-hidden">
          {/* 太阳系 3D 全息背景 */}
          <SolarSystem3D />

          {/* 左栏：TODAY + 娱乐 + 经济 + 生活 */}
          <div
            style={{
              position: "absolute", top: 16, left: 16, zIndex: 20,
              display: "flex", flexDirection: "column", gap: 10,
              maxHeight: "calc(100% - 70px)", overflowY: "auto",
            }}
          >
            <CategoryCard title="TODAY · 今日热点" accent="#ff7720" icon={Flame}      items={hotNews}        style={{}} onItemClick={openTopic} />
            <CategoryCard title="ENT · 娱乐"      accent="#ff66cc" icon={Music2}     items={cats["娱乐"] || []} style={{}} onItemClick={openTopic} />
            <CategoryCard title="ECON · 经济"     accent="#facc15" icon={BarChart2}  items={cats["经济"] || []} style={{}} onItemClick={openTopic} />
            <CategoryCard title="LIFE · 生活"     accent="#22d3ee" icon={Sparkles}   items={cats["生活"] || []} style={{}} onItemClick={openTopic} />
          </div>

          {/* 右栏：TRENDING + 科技 + 文化 */}
          <div
            style={{
              position: "absolute", top: 16, right: 16, zIndex: 20,
              display: "flex", flexDirection: "column", gap: 10,
              maxHeight: "calc(100% - 70px)", overflowY: "auto",
            }}
          >
            <CategoryCard title="TRENDING · 潮流" accent="#ff3e80" icon={TrendingUp} items={trending}           style={{}} onItemClick={openTopic} />
            <CategoryCard title="TECH · 科技"     accent="#a78bfa" icon={Cpu}        items={cats["科技"] || []} style={{}} onItemClick={openTopic} />
            <CategoryCard title="CULT · 文化"     accent="#94e6c4" icon={BookOpen}   items={cats["文化"] || []} style={{}} onItemClick={openTopic} />
          </div>

          {/* 纯网格内容流 — 居中容器 + 半透明，让背景透出 */}
          <div className="relative z-10 flex-1 overflow-y-auto px-4 py-6">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-w-2xl mx-auto">
              {posts.length === 0 ? (
                <div className="col-span-full flex flex-col items-center justify-center py-20 gap-3 opacity-60">
                  <ImageIcon size={36} className="text-cyan-300/60" />
                  <p className="text-sm text-cyan-300/70">还没有内容，来发第一条吧</p>
                </div>
              ) : (
                posts.map((p) => <PostCard key={p.id} post={p} username={username} />)
              )}
            </div>
          </div>

          {/* 热点话题展开层 — 居中抽屉式拉出，左右避开两侧分类卡 */}
          {expanded && (
            <div
              className="absolute z-30 flex items-stretch justify-center pointer-events-none"
              style={{ top: 16, bottom: 56, left: 260, right: 260 }}
            >
            <div
              className="flex flex-col hud-card-float topic-drawer-in pointer-events-auto"
              style={{
                width: "100%",
                maxWidth: 920,
                background: "rgba(4,10,22,0.94)",
                backdropFilter: "blur(8px)",
                overflow: "hidden",
              }}>
              {/* 头部 */}
              <div className="flex items-center justify-between px-5 py-3 border-b border-cyan-500/20 shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                  <Flame size={14} className="text-orange-400 shrink-0" />
                  <span className="hud-label text-[10px] text-orange-300/80 shrink-0">HOT TOPIC</span>
                  <span className="text-sm text-foreground/90 truncate ml-2">{expanded.title}</span>
                </div>
                <button
                  onClick={() => setExpanded(null)}
                  className="text-cyan-300/70 hover:text-cyan-200 text-lg leading-none px-2"
                  title="关闭"
                >✕</button>
              </div>

              {/* 内容区 */}
              <div className="flex-1 overflow-y-auto px-6 py-5 text-sm leading-relaxed space-y-4">
                {expanding && (
                  <div className="flex items-center gap-2 text-cyan-300/70 text-xs">
                    <span className="inline-block w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                    加载中…
                  </div>
                )}
                {expanded.error && (
                  <div className="text-orange-300/90 text-xs">拉取失败：{expanded.error}</div>
                )}
                {expanded.summary && (
                  <div className="text-foreground/95 text-[15px] leading-relaxed">{expanded.summary}</div>
                )}
                {expanded.whats_happening && (
                  <div>
                    <div className="hud-label text-[9px] text-cyan-300/80 mb-1.5">发生了什么</div>
                    <div className="text-foreground/85">{expanded.whats_happening}</div>
                  </div>
                )}
                {expanded.why_trending && (
                  <div>
                    <div className="hud-label text-[9px] text-pink-300/80 mb-1.5">为什么上热搜</div>
                    <div className="text-foreground/85">{expanded.why_trending}</div>
                  </div>
                )}
                {expanded.key_facts && expanded.key_facts.length > 0 && (
                  <div>
                    <div className="hud-label text-[9px] text-yellow-300/80 mb-1.5">关键事实</div>
                    <ul className="space-y-1.5">
                      {expanded.key_facts.map((f, i) => (
                        <li key={i} className="flex gap-2 text-foreground/85">
                          <span className="text-yellow-400/70 shrink-0">▸</span>
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {expanded.background && (
                  <div>
                    <div className="hud-label text-[9px] text-violet-300/80 mb-1.5">背景</div>
                    <div className="text-foreground/75 text-[13px]">{expanded.background}</div>
                  </div>
                )}
                {expanded.sources && expanded.sources.length > 0 && (
                  <div className="pt-2 border-t border-cyan-500/15">
                    <div className="hud-label text-[9px] text-cyan-300/80 mb-2">来源</div>
                    <ul className="space-y-1">
                      {expanded.sources.map((s, i) => (
                        <li key={i}>
                          <a
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[12px] text-cyan-300/80 hover:text-cyan-200 break-all"
                          >
                            {s.title || s.url}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
            </div>
          )}

          {/* 底部兴趣横栏 */}
          <div
            className="z-20 flex items-center gap-3 px-4 pointer-events-none"
            style={{
              position: "absolute", bottom: 0, left: 0, right: 0,
              height: 44,
              background: "linear-gradient(0deg, rgba(0,4,16,0.82) 0%, transparent 100%)",
              borderTop: "1px solid rgba(0,212,255,0.10)",
            }}
          >
            {/* 左侧：我的兴趣（固定） */}
            <div className="flex items-center gap-2 shrink-0 pointer-events-auto">
              <Sparkles size={10} className="text-cyan-400" />
              <span className="hud-label text-[9px] text-cyan-400">我的兴趣</span>
              {interests.length > 0 ? (
                <div className="flex gap-1">
                  {interests.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-2 py-0.5 rounded-full text-cyan-200"
                      style={{ background: "rgba(0,212,255,0.10)", border: "1px solid rgba(0,212,255,0.22)" }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-[10px] text-muted-foreground/50">点赞后出现</span>
              )}
            </div>

            {/* 分隔线 */}
            <div className="w-px h-5 shrink-0" style={{ background: "rgba(0,212,255,0.20)" }} />

            {/* 右侧：其他用户兴趣滚动 */}
            <div className="flex-1 overflow-hidden relative">
              {communityItems.length > 0 && (
                <div className="ticker-track gap-5 items-center">
                  {[...communityItems, ...communityItems].map((item, i) => (
                    <span key={i} className="inline-flex items-center gap-1 shrink-0 mr-5">
                      <span className="text-[9px]" style={{ color: "rgba(0,212,255,0.45)" }}>{item.user}</span>
                      <span className="text-[11px] text-foreground/70">{item.tag}</span>
                    </span>
                  ))}
                </div>
              )}
              {communityItems.length === 0 && (
                <span className="text-[10px] text-muted-foreground/40">暂无其他用户兴趣数据</span>
              )}
            </div>
          </div>

          {/* 右下角 FAB 发布（上移避开底栏）*/}
          <button
            onClick={() => fileRef.current?.click()}
            className="z-30 w-14 h-14 rounded-full flex items-center justify-center transition-all hover:scale-110 active:scale-95 pointer-events-auto"
            style={{
              position: "absolute", bottom: 56, right: 24,
              background: "linear-gradient(135deg, rgba(0,212,255,0.95), rgba(0,140,200,0.95))",
              boxShadow: "0 0 24px rgba(0,212,255,0.55), 0 8px 18px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.3)",
              border: "1px solid rgba(0,212,255,0.7)",
            }}
            title="发布到我的世界"
          >
            <Plus size={22} className="text-[#001821]" strokeWidth={2.5} />
          </button>
        </main>
      </div>

      <input ref={fileRef} type="file" accept="image/*,video/*" className="hidden" onChange={handleFileChange} />

      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="hud-card-float w-full max-w-sm overflow-hidden">
            <div className="shutter-handle" style={{ cursor: "default", borderRadius: "16px 16px 0 0" }}>
              <span className="chev">▲</span>
              <div className="hud-label">TRANSMIT TO PLAZA</div>
              <button onClick={handleClose} className="ml-2 text-cyan-300/80 hover:text-cyan-200">
                <X size={14} />
              </button>
            </div>

            {preview && (
              <div className="aspect-square bg-black/50">
                {previewType === "video"
                  ? <video src={preview} className="w-full h-full object-cover" controls />
                  : <img src={preview} alt="" className="w-full h-full object-cover" />}
              </div>
            )}

            <div className="p-4 space-y-3">
              <textarea
                value={caption}
                onChange={(e) => setCaption(e.target.value.slice(0, 100))}
                placeholder="说点什么…（可选，100字以内）"
                rows={2}
                className="w-full resize-none bg-black/40 border border-cyan-400/20 rounded-xl px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground outline-none leading-relaxed focus:border-cyan-400/50 transition-colors"
              />

              <div>
                <p className="hud-label mb-2 text-[10px]">SELECT TAGS · 最多 5</p>
                <div className="flex flex-wrap gap-1.5">
                  {ALL_TAGS.map((tag) => {
                    const selected = selectedTags.includes(tag);
                    return (
                      <button
                        key={tag}
                        onClick={() => togglePostTag(tag)}
                        className={cn("hud-pill flex items-center gap-1", selected && "hud-pill-active")}
                      >
                        {selected && <Check size={9} />}
                        #{tag}
                      </button>
                    );
                  })}
                </div>
              </div>

              <button
                onClick={handleSubmit}
                disabled={uploading}
                className={cn("w-full py-2.5 hud-btn flex items-center justify-center gap-2", !uploading && "hud-btn-active")}
                style={{ clipPath: "polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px))" }}
              >
                <span className="hud-label" style={uploading ? undefined : { color: "inherit", textShadow: "none" }}>
                  {uploading ? "UPLINK ·" : "TRANSMIT ▸"}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
