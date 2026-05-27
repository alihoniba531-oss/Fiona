"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import { Edit3, Trash2, Shield, Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/auth";

import { API_BASE as API } from "@/lib/config";

interface Profile {
  interests?: string[];
  values?: string[];
  needs?: string[];
  skills?: string[];
  struggles?: string[];
  city?: string;
  occupation?: string;
  stage?: string;
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="bg-card border border-border rounded-2xl p-5">
    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">{title}</h3>
    {children}
  </div>
);

const TagList = ({ items }: { items: string[] }) => (
  <div className="flex flex-wrap gap-2">
    {items.map((item) => (
      <span key={item} className="text-xs px-3 py-1 bg-secondary text-foreground rounded-full">
        {item}
      </span>
    ))}
  </div>
);

const Empty = ({ hint }: { hint: string }) => (
  <p className="text-xs text-muted-foreground/60 italic">{hint}</p>
);

function ProfileContent() {
  const [username, setUsername] = useState("默认用户");
  const [hydrated, setHydrated] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const u = localStorage.getItem("fiona_user");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (u) setUsername(u);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return; // 等 localStorage 读完再拉，避免用"默认用户"拉一次空 profile
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    apiFetch(`${API}/profile`)
      .then(r => r.json())
      .then(data => setProfile(data.profile || {}))
      .catch(() => setProfile({}))
      .finally(() => setLoading(false));
  }, [username, hydrated]);

  const interests = profile?.interests || [];
  const values = profile?.values || [];
  const needs = profile?.needs || [];
  const skills = profile?.skills || [];
  const struggles = profile?.struggles || [];
  const city = profile?.city || "";
  const occupation = profile?.occupation || "";
  const stage = profile?.stage || "";

  const isEmpty = !loading
    && interests.length === 0 && values.length === 0
    && needs.length === 0 && skills.length === 0
    && struggles.length === 0 && !city && !occupation && !stage;

  const sp = useSearchParams();
  const embedded = sp?.get("embed") === "1";

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      {!embedded && <TopBar />}
      <div className="flex flex-1 min-h-0">
        {!embedded && <Sidebar />}
        <div className="flex flex-col flex-1 min-w-0">
        <header className="glass border-b border-border px-6 py-4 shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-base font-semibold">我的画像</h1>
              <p className="text-[11px] text-muted-foreground mt-0.5">Chloe从对话中整理的信息，每 5 轮自动更新</p>
            </div>
            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <Shield size={12} />
              仅你可见
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-3">
          {/* Avatar & 基本信息 */}
          <div className="flex items-center gap-4 bg-card border border-border rounded-2xl p-5">
            <div className="w-14 h-14 rounded-full bg-primary/20 flex items-center justify-center">
              <span className="text-primary text-xl font-bold">{username[0]}</span>
            </div>
            <div className="min-w-0">
              <p className="font-semibold truncate">{username}</p>
              <p className="text-xs text-muted-foreground mt-0.5 truncate">
                {[city, occupation, stage].filter(Boolean).join(" · ") || "（暂未提取到基本信息）"}
              </p>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
              <Loader2 size={16} className="animate-spin" />
              <span className="text-sm">加载中…</span>
            </div>
          ) : isEmpty ? (
            <div className="bg-card border border-border rounded-2xl p-8 text-center">
              <p className="text-sm text-muted-foreground mb-2">画像还没建立起来</p>
              <p className="text-[11px] text-muted-foreground/70 leading-relaxed">
                跟Chloe聊几轮你的兴趣、烦恼、最近在做的事，<br/>
                每 5 轮她会在后台静默更新这里
              </p>
            </div>
          ) : (
            <>
              <Section title="兴趣">
                {interests.length ? <TagList items={interests} /> : <Empty hint="还没聊到" />}
              </Section>
              <Section title="价值观">
                {values.length ? <TagList items={values} /> : <Empty hint="还没聊到" />}
              </Section>
              <Section title="当前需求 / 想解决的问题">
                {needs.length ? <TagList items={needs} /> : <Empty hint="还没聊到" />}
              </Section>
              <Section title="技能 / 可分享的经验">
                {skills.length ? <TagList items={skills} /> : <Empty hint="还没聊到" />}
              </Section>
              <Section title="当前困境">
                {struggles.length ? <TagList items={struggles} /> : <Empty hint="还没聊到" />}
              </Section>
            </>
          )}

          <div className="flex items-start gap-2 px-4 py-3 bg-accent/30 rounded-xl">
            <Shield size={13} className="text-accent-foreground mt-0.5 shrink-0" />
            <p className="text-xs text-muted-foreground leading-relaxed">
              这些信息仅用于帮你匹配合适的人，不会透露给其他用户。匹配时只说&quot;有位朋友在关注类似的事&quot;。
            </p>
          </div>

          <div className="flex gap-2 pb-4">
            <button className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-secondary text-sm text-muted-foreground hover:text-foreground transition-all">
              <Edit3 size={14} />
              修正信息
            </button>
            <button className="flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl text-sm text-destructive/70 hover:text-destructive hover:bg-destructive/10 transition-all">
              <Trash2 size={14} />
              清除全部
            </button>
          </div>
        </div>
        </div>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <Suspense fallback={null}>
      <ProfileContent />
    </Suspense>
  );
}
