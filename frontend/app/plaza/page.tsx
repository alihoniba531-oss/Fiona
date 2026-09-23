"use client";

import { Suspense, useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import SolarSystem3D from "@/components/SolarSystem3D";
import { Plus, Heart, Video, X, Check, Sparkles, Music2, BarChart2, Cpu, BookOpen, Flame, TrendingUp, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/auth";
import { openExternal } from "@/lib/open";
import { useCategorizedHotTopics, useHotTopics, type HotFeedState } from "@/lib/useHotTopics";

import { API_BASE as API } from "@/lib/config";

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
  const diff = Date.now() - new Date(ts.replace(" ", "T") + "Z").getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

// ─────────────────── 帖子卡 ───────────────────
function PostCard({ post }: { post: Post }) {
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
    <div className="glass-card group overflow-hidden">
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
            <div className="rounded-[6px] border bg-black/60 p-1" style={{ borderColor: "var(--glass-border)" }}>
              <Video size={10} style={{ color: "var(--amber-ink)" }} />
            </div>
          )}
          {post.likes >= 5 && (
            <div className="tag tag-amber gap-0.5">
              <Flame size={9} />
              <span>热门</span>
            </div>
          )}
        </div>

        {post.tags.length > 0 && (
          <div className="absolute bottom-2 left-2 flex flex-wrap gap-1 max-w-[80%]">
            {post.tags.slice(0, 2).map((t) => (
              <span key={t} className="tag border bg-black/60 text-[9px] text-white/80" style={{ borderColor: "var(--glass-border)" }}>
                #{t}
              </span>
            ))}
            {post.tags.length > 2 && (
              <span className="tag border bg-black/60 text-[9px] text-white/70" style={{ borderColor: "var(--glass-border)" }}>
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
          <div className="flex items-center gap-1.5 mobile:min-w-0">
            <div className="grid h-6 w-6 place-items-center rounded-[6px] bg-secondary">
              <span className="text-[9px] font-medium text-muted-foreground">{(post.anon_id || "?")[0].toUpperCase()}</span>
            </div>
            <span className="readout text-[10px] mobile:truncate">{post.anon_id}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="readout text-[10px]">{timeAgo(post.created_at)}</span>
            <button
              onClick={handleLike}
              className={cn("relative flex items-center gap-1 transition-colors", liked ? "text-[color:var(--amber-ink)]" : "text-muted-foreground hover:text-[color:var(--amber-ink)]")}
            >
              <Heart size={13} fill={liked ? "currentColor" : "none"} className={burst ? "hud-like-burst" : undefined} />
              <span className="readout text-[11px]" style={liked ? { color: "var(--amber-ink)" } : undefined}>{likes}</span>
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
  title, icon: Icon, items, style, onItemClick, feed,
}: {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string; style?: React.CSSProperties }>;
  items: string[];
  style: React.CSSProperties;
  onItemClick?: (title: string) => void;
  feed: Omit<HotFeedState<unknown>, "data"> & { refresh: () => Promise<void> };
}) {
  const hasItems = items.length > 0;
  const updateDate = feed.updatedAt ? new Date(feed.updatedAt) : null;
  const updatedTime = updateDate && Number.isFinite(updateDate.getTime())
    ? updateDate.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : null;
  const notice = feed.error
    ? hasItems ? "更新失败，显示上次内容" : feed.error
    : feed.stale ? "实时更新暂不可用，显示上次内容"
    : feed.partial ? "部分来源暂不可用" : null;
  return (
    <div
      className="glass-card w-[220px] px-3 py-2 pointer-events-auto mobile:w-full"
      style={style}
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon size={12} style={{ color: "var(--amber-ink)" }} />
        <span className="text-[13px] font-medium">
          {title}
        </span>
        <button
          type="button"
          onClick={() => void feed.refresh()}
          disabled={feed.loading}
          aria-label={`刷新${title}`}
          title={feed.loading ? "更新中" : "刷新热点"}
          className="btn btn-quiet ml-auto h-7 w-7 px-0"
        >
          <RefreshCw size={12} className={feed.loading ? "animate-spin" : undefined} />
        </button>
      </div>
      {notice && (
        <div role="status" className="mb-1.5 text-[10px] leading-relaxed text-[color:var(--rec)]">
          {notice}
          <button
            type="button"
            onClick={() => void feed.refresh()}
            disabled={feed.loading}
            className="btn btn-quiet ml-1.5 h-7 px-2.5 text-xs"
          >
            {feed.loading ? "重试中…" : "重试"}
          </button>
        </div>
      )}
      <ul className="space-y-1">
        {!hasItems ? (
          <li className="text-xs text-muted-foreground">
            {feed.loading ? "拉取中…" : notice ? "暂无可显示的热点" : "暂时没有相关热点"}
          </li>
        ) : (
          items.slice(0, 4).map((it, i) => (
            <li
              key={i}
              className="flex cursor-pointer gap-1.5 text-xs leading-snug text-foreground/80 transition-colors hover:text-foreground"
              onClick={() => onItemClick?.(it)}
              style={{ borderRadius: 3 }}
              title="点开查看详情"
            >
              <span className="readout mt-0.5 shrink-0 text-[11px]">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="truncate">{it}</span>
            </li>
          ))
        )}
      </ul>
      {updatedTime && hasItems && (
        <div className="readout mt-1.5 text-[10px]" title={updateDate?.toLocaleString("zh-CN")}>
          {feed.loading ? "更新中 · " : ""}获取于 {updatedTime}
        </div>
      )}
    </div>
  );
}

// ─────────────────── 主页 ───────────────────
function PlazaContent() {
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

  const hotFeed = useHotTopics("微博");
  const trendingFeed = useHotTopics("抖音");
  const categoryFeed = useCategorizedHotTopics();
  const cats = categoryFeed.data;
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
    } catch (e: unknown) {
      setExpanded({ title, error: e instanceof Error ? e.message : "拉取失败" });
    } finally {
      setExpanding(false);
    }
  }, []);

  const [interests, setInterests] = useState<string[]>([]);
  const [communityItems, setCommunityItems] = useState<{ tag: string; user: string }[]>([]);

  useEffect(() => {
    const u = localStorage.getItem("fiona_user");
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadPosts();
  }, [loadPosts, hydrated]);

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
    <div className={cn("flex h-screen flex-col overflow-hidden mobile:h-dvh", !embedded && "mobile:pb-[calc(56px+env(safe-area-inset-bottom))]")}>
      <div className="flex flex-1 min-h-0 relative">
        {!embedded && <Sidebar />}

        <main className={cn("flex flex-col flex-1 min-w-0 relative overflow-hidden mobile:overflow-y-auto", !embedded && "mobile:pb-20")}>
          {/* 太阳系 3D 全息背景 */}
          <SolarSystem3D />

          {/* 左栏：TODAY + 娱乐 + 经济 + 生活 */}
          <div
            className="mobile:static! mobile:mx-4 mobile:mt-4 mobile:shrink-0 mobile:gap-3 mobile:max-h-none! mobile:overflow-visible!"
            style={{
              position: "absolute", top: 16, left: 16, zIndex: 20,
              display: "flex", flexDirection: "column", gap: 10,
              maxHeight: "calc(100% - 70px)", overflowY: "auto",
            }}
          >
            <CategoryCard title="今日热点" icon={Flame} items={hotFeed.data} feed={hotFeed} style={{}} onItemClick={openTopic} />
            <CategoryCard title="娱乐" icon={Music2} items={cats["娱乐"] || []} feed={categoryFeed} style={{}} onItemClick={openTopic} />
            <CategoryCard title="经济" icon={BarChart2} items={cats["经济"] || []} feed={categoryFeed} style={{}} onItemClick={openTopic} />
            <CategoryCard title="生活" icon={Sparkles} items={cats["生活"] || []} feed={categoryFeed} style={{}} onItemClick={openTopic} />
          </div>

          {/* 右栏：TRENDING + 科技 + 文化 */}
          <div
            className="mobile:static! mobile:mx-4 mobile:mt-3 mobile:shrink-0 mobile:gap-3 mobile:max-h-none! mobile:overflow-visible!"
            style={{
              position: "absolute", top: 16, right: 16, zIndex: 20,
              display: "flex", flexDirection: "column", gap: 10,
              maxHeight: "calc(100% - 70px)", overflowY: "auto",
            }}
          >
            <CategoryCard title="潮流" icon={TrendingUp} items={trendingFeed.data} feed={trendingFeed} style={{}} onItemClick={openTopic} />
            <CategoryCard title="科技" icon={Cpu} items={cats["科技"] || []} feed={categoryFeed} style={{}} onItemClick={openTopic} />
            <CategoryCard title="文化" icon={BookOpen} items={cats["文化"] || []} feed={categoryFeed} style={{}} onItemClick={openTopic} />
          </div>

          {/* 纯网格内容流 — 居中容器 + 半透明，让背景透出 */}
          <div className="relative z-10 flex-1 overflow-y-auto px-4 py-6 mobile:flex-none mobile:overflow-visible">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-w-2xl mx-auto mobile:grid-cols-1!">
              {posts.map((p) => <PostCard key={p.id} post={p} />)}
            </div>
          </div>

          {/* 热点话题展开层 — 居中抽屉式拉出，左右避开两侧分类卡 */}
          {expanded && (
            <div
              className={cn(
                "absolute z-30 flex items-stretch justify-center pointer-events-none mobile:fixed! mobile:top-4! mobile:left-4! mobile:right-4!",
                embedded ? "mobile:bottom-4!" : "mobile:bottom-[calc(56px+env(safe-area-inset-bottom)+16px)]!",
              )}
              style={{ top: 16, bottom: 56, left: 260, right: 260 }}
            >
            <div
              className="glass topic-drawer-in pointer-events-auto flex flex-col rounded-[10px] border"
              style={{
                width: "100%",
                maxWidth: 920,
                overflow: "hidden",
                borderColor: "var(--glass-border)",
              }}>
              {/* 头部 */}
              <div className="flex shrink-0 items-center justify-between border-b px-5 py-3" style={{ borderColor: "var(--glass-border)" }}>
                <div className="flex items-center gap-2 min-w-0">
                  <Flame size={14} className="shrink-0" style={{ color: "var(--amber-ink)" }} />
                  <span className="truncate text-[13px] font-medium">{expanded.title}</span>
                </div>
                <button
                  onClick={() => setExpanded(null)}
                  className="btn btn-quiet h-7 w-7 px-0"
                  title="关闭"
                  aria-label="关闭话题详情"
                ><X size={14} /></button>
              </div>

              {/* 内容区 */}
              <div className="flex-1 overflow-y-auto px-6 py-5 text-sm leading-relaxed space-y-4 mobile:px-4">
                {expanding && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="state-dot state-dot-speaking" />
                    加载中…
                  </div>
                )}
                {expanded.error && (
                  <div className="text-xs text-[color:var(--rec)]">拉取失败：{expanded.error}</div>
                )}
                {expanded.summary && (
                  <div className="text-foreground/95 text-[15px] leading-relaxed">{expanded.summary}</div>
                )}
                {expanded.whats_happening && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-muted-foreground">发生了什么</div>
                    <div className="text-foreground/85">{expanded.whats_happening}</div>
                  </div>
                )}
                {expanded.why_trending && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-muted-foreground">为什么上热搜</div>
                    <div className="text-foreground/85">{expanded.why_trending}</div>
                  </div>
                )}
                {expanded.key_facts && expanded.key_facts.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-muted-foreground">关键事实</div>
                    <ul className="space-y-1.5">
                      {expanded.key_facts.map((f, i) => (
                        <li key={i} className="flex gap-2 text-foreground/85">
                          <span className="mt-2 h-1.5 w-1.5 shrink-0" style={{ background: "var(--amber-ink)" }} />
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {expanded.background && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-muted-foreground">背景</div>
                    <div className="text-foreground/75 text-[13px]">{expanded.background}</div>
                  </div>
                )}
                {expanded.sources && expanded.sources.length > 0 && (
                  <div className="border-t pt-2" style={{ borderColor: "var(--glass-border)" }}>
                    <div className="mb-2 text-xs font-medium text-muted-foreground">来源</div>
                    <ul className="space-y-1">
                      {expanded.sources.map((s, i) => (
                        <li key={i}>
                          {s.url ? (
                            <button
                              onClick={() => openExternal(s.url)}
                              className="cursor-pointer break-all border-0 bg-transparent p-0 text-left text-[12px] text-[color:var(--amber-ink)] opacity-80 hover:opacity-100"
                            >
                              {s.title || s.url}
                            </button>
                          ) : (
                            // 链接死了（AI 编的）时只显示标题，加灰并标注
                            <span
                              className="break-all text-[12px] text-[color:var(--amber-ink)] opacity-40"
                              title="AI 整理时未能确认此来源原链接"
                            >
                              {s.title || "来源"}
                              <span className="ml-1 text-[9px] opacity-60">（链接失效）</span>
                            </span>
                          )}
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
            className="glass pointer-events-none z-20 flex items-center gap-3 border-t px-4 mobile:static! mobile:h-auto! mobile:min-w-0 mobile:flex-col mobile:items-stretch mobile:gap-2 mobile:py-2"
            style={{
              position: "absolute", bottom: 0, left: 0, right: 0,
              height: 44,
              borderColor: "var(--glass-border)",
            }}
          >
            {/* 左侧：我的兴趣（固定） */}
            <div className="flex items-center gap-2 shrink-0 pointer-events-auto mobile:min-w-0 mobile:w-full">
              <Sparkles size={12} style={{ color: "var(--amber-ink)" }} />
              <span className="text-xs font-medium text-muted-foreground">我的兴趣</span>
              {interests.length > 0 ? (
                <div className="flex gap-1 mobile:min-w-0 mobile:overflow-x-auto">
                  {interests.map((tag) => (
                    <span
                      key={tag}
                      className="chip h-6 px-2 text-[10px] mobile:shrink-0 mobile:whitespace-nowrap"
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
            <div className="h-5 w-px shrink-0 mobile:hidden" style={{ background: "var(--glass-border)" }} />

            {/* 右侧：其他用户兴趣滚动 */}
            <div className="flex-1 overflow-hidden relative mobile:min-h-4">
              {communityItems.length > 0 && (
                <div className="ticker-track gap-5 items-center">
                  {[...communityItems, ...communityItems].map((item, i) => (
                    <span key={i} className="inline-flex items-center gap-1 shrink-0 mr-5">
                      <span className="readout text-[9px]">{item.user}</span>
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
            className={cn(
              "btn btn-primary pointer-events-auto z-30 h-14 w-14 rounded-full p-0 mobile:fixed! mobile:right-4!",
              embedded ? "mobile:bottom-16!" : "mobile:bottom-[calc(56px+env(safe-area-inset-bottom)+64px)]!",
            )}
            style={{
              position: "absolute", bottom: 56, right: 24,
            }}
            title="发布到我的世界"
          >
            <Plus size={22} className="text-primary-foreground" strokeWidth={2.5} />
          </button>
        </main>
      </div>

      <input ref={fileRef} type="file" accept="image/*,video/*" className="hidden" onChange={handleFileChange} />

      {showModal && (
        <div className={cn("fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4", !embedded && "mobile:bottom-[calc(56px+env(safe-area-inset-bottom))]!")}>
          <div
            className={cn(
              "glass w-full max-w-sm overflow-hidden rounded-[10px] border mobile:overflow-y-auto",
              embedded ? "mobile:max-h-[calc(100dvh-2rem)]" : "mobile:max-h-[calc(100dvh-2rem-56px-env(safe-area-inset-bottom))]",
            )}
            style={{ borderColor: "var(--glass-border)" }}
          >
            <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--glass-border)" }}>
              <div className="flex items-center gap-2 text-sm font-medium">
                <Plus size={14} style={{ color: "var(--amber-ink)" }} />
                发布到世界
              </div>
              <button onClick={handleClose} className="btn btn-quiet h-7 w-7 px-0" aria-label="关闭发布面板">
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
                className="w-full resize-none rounded-[6px] border bg-card px-3 py-[9px] text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground focus:border-[color:var(--amber-ink)] mobile:text-base"
              />

              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">标签 · 最多 5</p>
                <div className="flex flex-wrap gap-1.5">
                  {ALL_TAGS.map((tag) => {
                    const selected = selectedTags.includes(tag);
                    return (
                      <button
                        key={tag}
                        onClick={() => togglePostTag(tag)}
                        className={cn("chip", selected && "chip-on")}
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
                className="btn btn-primary h-10 w-full"
              >
                {uploading ? "正在发布…" : "发布"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PlazaPage() {
  return (
    <Suspense fallback={null}>
      <PlazaContent />
    </Suspense>
  );
}
