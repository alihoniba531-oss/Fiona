"use client";

import { Suspense, useState, useEffect, useRef, useCallback, type CSSProperties } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import Glaze from "@/components/Glaze";
import InkLandscape from "@/components/InkLandscape";
import StarChart from "@/components/StarChart";
import { Plus, Heart, Video, X, Check, Flame, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/auth";
import { useAccountIdentity } from "@/lib/useAccountIdentity";
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
    <div className="ceramic-card group overflow-hidden">
      <div className="relative aspect-square bg-[color:var(--slip)] overflow-hidden">
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
            <div className="rounded-[6px] border bg-[color:var(--mount)] p-1" style={{ borderColor: "var(--rule)" }}>
              <Video size={10} style={{ color: "var(--ink)" }} />
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
              <span key={t} className="tag border bg-[color:var(--mount)] text-[9px] text-[color:var(--ink)]" style={{ borderColor: "var(--rule)" }}>
                #{t}
              </span>
            ))}
            {post.tags.length > 2 && (
              <span className="tag border bg-[color:var(--mount)] text-[9px] text-[color:var(--ink2)]" style={{ borderColor: "var(--rule)" }}>
                +{post.tags.length - 2}
              </span>
            )}
          </div>
        )}

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
              aria-label="点赞"
              aria-pressed={liked}
              className={cn("relative flex items-center gap-1 transition-colors mobile:min-h-10 mobile:min-w-10 mobile:justify-center", liked ? "text-[color:var(--seal)]" : "text-[color:var(--ink2)] hover:text-[color:var(--seal)]")}
            >
              <Heart size={13} fill={liked ? "currentColor" : "none"} className={burst ? "porcelain-like-burst" : undefined} />
              <span className="readout text-[11px]" style={liked ? { color: "var(--seal)" } : undefined}>{likes}</span>
              {burst > 0 && <span key={burst} className="porcelain-like-pop">+1</span>}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────── 分类热搜卡 ───────────────────
function CategoryCard({
  title, items, onItemClick, feed,
}: {
  title: string;
  items: string[];
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
    <section className="min-w-0 pointer-events-auto">
      <div className="flex items-baseline justify-between gap-2 border-b border-[color:var(--carve)] pb-2 shadow-[0_1px_0_var(--etch)]">
        <h2 className="text-[15px] font-medium tracking-[.16em]">{title}</h2>
        <button
          type="button"
          onClick={() => void feed.refresh()}
          disabled={feed.loading}
          aria-label={`刷新${title}`}
          title={feed.loading ? "更新中" : "刷新热点"}
          className="inline-flex shrink-0 items-center gap-1 border-0 bg-transparent text-xs text-[color:var(--ink2)] disabled:opacity-45 mobile:min-h-10 mobile:min-w-10 mobile:justify-center"
        >
          {feed.loading && <RefreshCw size={12} aria-hidden="true" className="animate-spin" />}
          刷新
        </button>
      </div>
      {notice && (
        <div role="status" className="mt-2 text-[11.5px] leading-relaxed text-[color:var(--seal)]">
          {notice}
          <button
            type="button"
            onClick={() => void feed.refresh()}
            disabled={feed.loading}
            className="btn btn-quiet ml-1.5 h-7 px-2.5 text-xs mobile:min-h-10"
          >
            {feed.loading ? "重试中…" : "重试"}
          </button>
        </div>
      )}
      <ol className="mt-2 list-none p-0 text-[13.5px] leading-7">
        {!hasItems ? (
          <li className="text-xs text-[color:var(--ink2)]">
            {feed.loading ? "拉取中…" : notice ? "暂无可显示的热点" : "暂时没有相关热点"}
          </li>
        ) : (
          items.slice(0, 4).map((it, i) => (
            <li key={i} className="min-w-0">
              <button
                type="button"
                className="flex min-w-0 w-full items-baseline gap-2.5 rounded-sm border-0 bg-transparent p-0 text-left text-[color:var(--ink)] hover:underline mobile:min-h-10"
                onClick={() => onItemClick?.(it)}
                title="点开查看详情"
              >
                <span className="w-3 shrink-0 text-xs tabular-nums text-[color:var(--ink2)]">{i + 1}</span>
                <span className="truncate">{it}</span>
              </button>
            </li>
          ))
        )}
      </ol>
      {updatedTime && hasItems && (
        <div className="mt-0.5 text-[11.5px] tabular-nums text-[color:var(--ink2)]" title={updateDate?.toLocaleString("zh-CN")}>
          {feed.loading ? "更新中 · " : ""}获取于 {updatedTime}
        </div>
      )}
    </section>
  );
}

// ─────────────────── 主页 ───────────────────
function PlazaContent() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<"image" | "video">("image");
  const [caption, setCaption] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const username = useAccountIdentity();
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

  const loadPosts = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "30" });
      const r = await apiFetch(`${API}/plaza/feed?${params}`);
      const data = await r.json();
      setPosts(data.posts || []);
    } catch {}
  }, []);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadPosts();
  }, [loadPosts]);

  // 拉用户兴趣（当前时段 top tags）
  useEffect(() => {
    if (!username) return;
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
  }, [username]);

  // 拉社区其他用户兴趣（底部 ticker）
  useEffect(() => {
    if (!username) return;
    apiFetch(`${API}/plaza/community-interests`)
      .then((r) => r.json())
      .then((d) => setCommunityItems(d.items || []))
      .catch(() => {});
  }, [username]);

  const togglePostTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : prev.length < 5 ? [...prev, tag] : prev
    );
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSubmitError("");
    selectedFile.current = file;
    setPreviewType(file.type.startsWith("video/") ? "video" : "image");
    setPreview(URL.createObjectURL(file));
    setShowModal(true);
  };

  const handleSubmit = async () => {
    if (!selectedFile.current || uploading || !username) return;
    setUploading(true);
    setSubmitError("");
    try {
      const form = new FormData();
      form.append("caption", caption);
      form.append("tags", JSON.stringify(selectedTags));
      form.append("file", selectedFile.current);
      const response = await apiFetch(`${API}/plaza/post`, { method: "POST", body: form });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : `发布失败（${response.status}），请重试`);
      }
      handleClose();
      await loadPosts();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "发布失败，请重试");
    } finally {
      setUploading(false);
    }
  };

  const handleClose = () => {
    setShowModal(false);
    setSubmitError("");
    setPreview(null);
    setCaption("");
    setSelectedTags([]);
    selectedFile.current = null;
    if (fileRef.current) fileRef.current.value = "";
  };

  const searchParams = useSearchParams();
  const embedded = searchParams?.get("embed") === "1";

  return (
    <div className={cn("flex h-screen flex-col overflow-hidden mobile:h-dvh", !embedded && "mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]")}>
      <div className="flex flex-1 min-h-0 relative">
        {!embedded && <Sidebar />}

        <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden mobile:overflow-y-auto">
          <InkLandscape variant="world" />

          <div
            className="relative flex flex-1 min-h-0 p-3 mobile:flex-none mobile:flex-col"
            style={{ "--world-panel-w": "min(40%, max(320px, calc(50% - 42.37vh + 36px)))" } as CSSProperties}
          >
            {/* 两列热点各在一整片釉上，星图外规从内侧口沿下穿过。 */}
            <Glaze
              variant="panel"
              lens
              fur
              className="relative z-20 flex w-[var(--world-panel-w)] shrink-0 flex-col rounded-[18px] mobile:w-full mobile:shrink-0"
              style={{ "--glaze-lens-filter": "url(#yqw-lens-chart)", "--glaze-edge-x": "28px" } as CSSProperties}
            >
              <div className="flex min-h-0 flex-col gap-6 overflow-y-auto px-9 py-5 mobile:overflow-visible mobile:px-5">
                <CategoryCard title="今日热点" items={hotFeed.data} feed={hotFeed} onItemClick={openTopic} />
                <CategoryCard title="娱乐" items={cats["娱乐"] || []} feed={categoryFeed} onItemClick={openTopic} />
                <CategoryCard title="经济" items={cats["经济"] || []} feed={categoryFeed} onItemClick={openTopic} />
                <CategoryCard title="生活" items={cats["生活"] || []} feed={categoryFeed} onItemClick={openTopic} />
              </div>
            </Glaze>

            <div className="relative z-[1] flex min-w-0 flex-1 items-center justify-center mobile:order-first mobile:h-[360px] mobile:flex-none">
              <StarChart className="top-7 w-[min(calc(118%+104px),calc(100vh+20px))] max-w-none mobile:top-0 mobile:w-[min(100%,390px)]" />
            </div>

            <Glaze
              variant="panel"
              lens
              fur
              className="relative z-20 flex w-[var(--world-panel-w)] shrink-0 flex-col rounded-[18px] mobile:mt-3 mobile:w-full mobile:shrink-0"
              style={{ "--glaze-lens-filter": "url(#yqw-lens-chart)", "--glaze-edge-x": "28px" } as CSSProperties}
            >
              <div className="flex min-h-0 flex-col gap-6 overflow-y-auto px-9 py-5 mobile:overflow-visible mobile:px-5">
                <CategoryCard title="潮流" items={trendingFeed.data} feed={trendingFeed} onItemClick={openTopic} />
                <CategoryCard title="科技" items={cats["科技"] || []} feed={categoryFeed} onItemClick={openTopic} />
                <CategoryCard title="文化" items={cats["文化"] || []} feed={categoryFeed} onItemClick={openTopic} />
              </div>
            </Glaze>

            {/* 保留帖子流；有内容时铺在星图前，清釉装裱不做背景模糊。 */}
            <div
              className="absolute z-10 overflow-y-auto px-3 py-5 mobile:static! mobile:mt-3 mobile:flex-none mobile:overflow-visible mobile:px-0 mobile:py-0"
              style={{ left: "calc(var(--world-panel-w) + 12px)", right: "calc(var(--world-panel-w) + 12px)", top: 12, bottom: 12 }}
            >
              <div
                className="grid gap-3 max-w-2xl mx-auto mobile:grid-cols-1!"
                style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))" }}
              >
                {posts.map((p) => <PostCard key={p.id} post={p} />)}
              </div>
            </div>
          </div>

          {/* 热点话题展开层；窄桌面 iframe 仍保留可读宽度。 */}
          {expanded && (
            <div
              className={cn(
                "absolute z-30 flex items-stretch justify-center pointer-events-none mobile:fixed! mobile:top-4! mobile:left-4! mobile:right-4!",
                embedded ? "mobile:bottom-4!" : "mobile:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom)+16px)]!",
              )}
              style={{ top: 12, bottom: 76, left: 12, right: 12 }}
            >
            <div
              className="ceramic-card topic-drawer-in pointer-events-auto flex flex-col rounded-[18px]"
              style={{
                width: "100%",
                maxWidth: 920,
                overflow: "hidden",
                borderColor: "var(--rule)",
                backdropFilter: "var(--bd)",
                WebkitBackdropFilter: "var(--bd)",
              }}>
              {/* 头部 */}
              <div className="flex shrink-0 items-center justify-between border-b px-5 py-3" style={{ borderColor: "var(--rule)" }}>
                <div className="flex items-center gap-2 min-w-0">
                  <Flame size={14} className="shrink-0" style={{ color: "var(--ink)" }} />
                  <span className="truncate text-[13px] font-medium">{expanded.title}</span>
                </div>
                <button
                  onClick={() => setExpanded(null)}
                  className="btn btn-quiet h-7 w-7 px-0 mobile:h-10 mobile:w-10"
                  title="关闭"
                  aria-label="关闭话题详情"
                ><X size={14} /></button>
              </div>

              {/* 内容区 */}
              <div className="flex-1 overflow-y-auto px-6 py-5 text-sm leading-relaxed space-y-4 mobile:px-4">
                {expanding && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    加载中…
                  </div>
                )}
                {expanded.error && (
                  <div className="text-xs text-[color:var(--seal)]">拉取失败：{expanded.error}</div>
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
                          <span className="mt-2 h-1.5 w-1.5 shrink-0" style={{ background: "var(--ink)" }} />
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
                  <div className="border-t pt-2" style={{ borderColor: "var(--rule)" }}>
                    <div className="mb-2 text-xs font-medium text-muted-foreground">来源</div>
                    <ul className="space-y-1">
                      {expanded.sources.map((s, i) => (
                        <li key={i}>
                          {s.url ? (
                            <button
                              onClick={() => openExternal(s.url)}
                              className="cursor-pointer break-all border-0 bg-transparent p-0 text-left text-[12px] text-[color:var(--ink)] opacity-80 hover:opacity-100 mobile:min-h-10 mobile:py-2"
                            >
                              {s.title || s.url}
                            </button>
                          ) : (
                            // 链接死了（AI 编的）时只显示标题，加灰并标注
                            <span
                              className="break-all text-[12px] text-[color:var(--ink)] opacity-40"
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

          {/* 底部兴趣釉条与墨底发布按钮。 */}
          <Glaze
            as="footer"
            variant="strip"
            lens
            className="world-interest-glaze relative z-20 mx-3 mb-3 flex h-[52px] shrink-0 items-center gap-4 rounded-[16px] pl-7 pr-[9px] mobile:h-auto mobile:min-w-0 mobile:flex-wrap mobile:gap-3 mobile:px-4 mobile:py-3"
            style={{ "--glaze-lens-filter": "url(#yqw-lens-bar)" } as CSSProperties}
          >
            <div className="flex min-w-0 shrink items-center gap-3 mobile:w-full">
              <span className="shrink-0 text-[13px] tracking-[.1em]">我的兴趣</span>
              {interests.length > 0 ? (
                <div className="flex min-w-0 gap-1 overflow-x-auto">
                  {interests.map((tag) => (
                    <span key={tag} className="chip h-6 shrink-0 whitespace-nowrap px-2 text-[11px]">{tag}</span>
                  ))}
                </div>
              ) : <span className="text-xs text-[color:var(--ink2)]">点赞后出现</span>}
            </div>

            <div className="h-3 w-px shrink-0 mobile:hidden" style={{ background: "var(--rule2)" }} />
            <div className="relative min-w-0 flex-1 overflow-hidden mobile:min-h-4 mobile:w-full mobile:flex-auto">
              {communityItems.length > 0 && (
                <div className="ticker-track gap-5 items-center">
                  {[...communityItems, ...communityItems].map((item, i) => (
                    <span key={i} className="inline-flex items-center gap-1 shrink-0 mr-5">
                      <span className="readout text-[11px]">{item.user}</span>
                      <span className="text-xs text-[color:var(--ink2)]">{item.tag}</span>
                    </span>
                  ))}
                </div>
              )}
              {communityItems.length === 0 && <span className="text-xs text-[color:var(--ink2)]">暂无其他用户兴趣数据</span>}
            </div>

            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="btn btn-primary h-[34px] shrink-0 px-[18px] text-[13px] tracking-[.16em] mobile:h-10 mobile:ml-auto"
              title="发布到我的世界"
            >发布照片</button>
          </Glaze>
        </main>
      </div>

      <input ref={fileRef} type="file" accept="image/*,video/*" className="hidden" onChange={handleFileChange} />

      {showModal && (
        <div className={cn("fixed inset-0 z-50 flex items-center justify-center bg-[color:var(--scrim)] p-4", !embedded && "mobile:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]!")}>
          <div
            className={cn(
              "ceramic-card w-full max-w-sm overflow-hidden rounded-[18px] mobile:overflow-y-auto",
              embedded ? "mobile:max-h-[calc(100dvh-2rem)]" : "mobile:max-h-[calc(100dvh-2rem-var(--tabbar-h)-env(safe-area-inset-bottom))]",
            )}
            style={{ borderColor: "var(--rule)" }}
          >
            <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--rule)" }}>
              <div className="flex items-center gap-2 text-sm font-medium">
                <Plus size={14} style={{ color: "var(--ink)" }} />
                发布到世界
              </div>
              <button onClick={handleClose} className="btn btn-quiet h-7 w-7 px-0 mobile:h-10 mobile:w-10" aria-label="关闭发布面板">
                <X size={14} />
              </button>
            </div>

            {preview && (
              <div className="aspect-square bg-[color:var(--slip)]">
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
                className="w-full resize-none rounded-[6px] border bg-card px-3 py-[9px] text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground focus:border-[color:var(--ink)] mobile:text-base"
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
                        className={cn("chip mobile:min-h-10", selected && "chip-on")}
                      >
                        {selected && <Check size={9} />}
                        #{tag}
                      </button>
                    );
                  })}
                </div>
              </div>

              {submitError && <p role="alert" className="text-xs text-[color:var(--seal)]">{submitError}</p>}
              <button
                onClick={handleSubmit}
                disabled={uploading || !username}
                className="btn btn-primary h-10 w-full"
              >
                {uploading ? "正在发布…" : !username ? "正在获取账号信息…" : "发布"}
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
