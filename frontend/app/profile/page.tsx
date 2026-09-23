"use client";

import { Suspense, useState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { ArrowUpRight, Shield, Loader2, Heart, Scale, CircleHelp, Wrench, TriangleAlert } from "lucide-react";
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

const Section = ({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string; style?: React.CSSProperties }>;
  children: React.ReactNode;
}) => (
  <div className="glass-card p-5">
    <h3 className="mb-3 flex items-center gap-2 text-sm font-medium">
      <Icon size={14} style={{ color: "var(--amber-ink)" }} />
      {title}
    </h3>
    {children}
  </div>
);

const TagList = ({ items }: { items: string[] }) => (
  <div className="flex flex-wrap gap-2">
    {items.map((item) => (
      <span key={item} className="chip mobile:h-auto mobile:max-w-full mobile:break-all mobile:whitespace-normal">
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
    <div className={`flex h-dvh flex-col overflow-hidden ${!embedded ? "mobile:pb-[calc(56px+env(safe-area-inset-bottom))]" : ""}`}>
      <div className="flex flex-1 min-h-0">
        {!embedded && <Sidebar />}
        <div className="flex flex-col flex-1 min-w-0">
        <header className="glass sticky top-0 z-[2] shrink-0 border-b px-8 pb-[18px] pt-7 mobile:px-4 mobile:pt-4" style={{ borderColor: "var(--glass-border)" }}>
          <div className="flex max-w-[976px] items-end justify-between gap-4 mobile:flex-col mobile:items-start mobile:gap-2">
            <div>
              <h1 className="text-xl font-medium tracking-[-0.01em]">旧社交画像</h1>
              <p className="mt-1 text-[13px] text-muted-foreground">此前用于社交匹配的画像；新会话记忆在“我的分身”中查看</p>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Shield size={13} style={{ color: "var(--amber-ink)" }} />
              本人查看
            </div>
          </div>
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto px-8 py-6 mobile:min-w-0 mobile:px-4 mobile:py-4">
          {/* Avatar & 基本信息 */}
          <div className="glass-card flex items-center gap-4 p-5">
            <div className="grid h-14 w-14 place-items-center rounded-[6px] bg-secondary">
              <span className="text-xl font-medium" style={{ color: "var(--amber-ink)" }}>{username[0]}</span>
            </div>
            <div className="min-w-0">
              <p className="truncate font-medium">{username}</p>
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
            <div className="glass-card p-8 text-center">
              <p className="text-sm text-muted-foreground mb-2">暂无旧社交画像</p>
              <p className="text-[11px] text-muted-foreground/70 leading-relaxed">
                新会话形成的私有记忆已单独保存，<br/>
                请前往“我的分身”查看和管理。
              </p>
            </div>
          ) : (
            <>
              <Section title="兴趣" icon={Heart}>
                {interests.length ? <TagList items={interests} /> : <Empty hint="暂无记录" />}
              </Section>
              <Section title="价值观" icon={Scale}>
                {values.length ? <TagList items={values} /> : <Empty hint="暂无记录" />}
              </Section>
              <Section title="当前需求 / 想解决的问题" icon={CircleHelp}>
                {needs.length ? <TagList items={needs} /> : <Empty hint="暂无记录" />}
              </Section>
              <Section title="技能 / 可分享的经验" icon={Wrench}>
                {skills.length ? <TagList items={skills} /> : <Empty hint="暂无记录" />}
              </Section>
              <Section title="当前困境" icon={TriangleAlert}>
                {struggles.length ? <TagList items={struggles} /> : <Empty hint="暂无记录" />}
              </Section>
            </>
          )}

          <div className="glass-card flex items-start gap-2 p-5">
            <Shield size={13} className="mt-0.5 shrink-0" style={{ color: "var(--amber-ink)" }} />
            <p className="text-xs text-muted-foreground leading-relaxed">
              这里保留旧社交画像，不展示新会话的私有记忆。你可以在“我的分身”中查看新记忆，或清空分身记忆和已有个人画像；聊天记录会保留。
            </p>
          </div>

          <div className="flex gap-2 pb-4">
            <Link href="/agents/me" target={embedded ? "_top" : undefined} className="btn flex-1 mobile:h-auto mobile:min-h-10 mobile:whitespace-normal">
              <ArrowUpRight size={14} />
              前往我的分身管理记忆
            </Link>
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
