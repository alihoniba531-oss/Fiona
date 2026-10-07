"use client";

import { Suspense, useState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import Glaze from "@/components/Glaze";
import InkLandscape from "@/components/InkLandscape";
import { ArrowUpRight, Shield, Loader2, Heart, Scale, CircleHelp, Wrench, TriangleAlert } from "lucide-react";
import { apiFetch } from "@/lib/auth";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";

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
  <section className="grid min-w-0 grid-cols-[160px_minmax(0,1fr)] gap-6 border-t border-[color:var(--carve)] py-[22px] shadow-[inset_0_1px_0_var(--etch)] mobile:grid-cols-1 mobile:gap-3">
    <h3 className="flex items-start gap-2 text-base font-medium leading-[1.8] tracking-[0.08em]">
      <Icon size={14} className="mt-[7px] shrink-0" style={{ color: "var(--ink2)" }} />
      {title}
    </h3>
    <div className="min-w-0">{children}</div>
  </section>
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
  <p className="text-xs text-[color:var(--ink2)]">{hint}</p>
);

function ProfileForAccount({ username }: { username: string }) {
  const { beginRequest } = useAccountRequest(username);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const request = beginRequest();
    if (!request) return;
    apiFetch(`${API}/profile`, { signal: request.signal })
      .then(r => r.json())
      .then(data => { if (request.isCurrent()) setProfile(data.profile || {}); })
      .catch(() => { if (request.isCurrent()) setProfile({}); })
      .finally(() => { if (request.isCurrent()) setLoading(false); });
  }, [beginRequest]);

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
    <div className={`relative flex h-dvh flex-col overflow-hidden ${!embedded ? "mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]" : ""}`}>
      <InkLandscape variant="page" />
      <div className="relative flex min-h-0 flex-1">
        {!embedded && <Sidebar />}
        <main className="flex min-w-0 flex-1 justify-center overflow-x-hidden overflow-y-auto p-3">
          <Glaze variant="panel" fur className="relative z-[1] box-border min-h-full w-full max-w-[712px] self-start rounded-[18px] px-12 pb-8 pt-7 mobile:px-6 mobile:pb-6 mobile:pt-5">
            <header className="pb-7">
              <h1 className="mt-[18px] text-[30px] font-medium tracking-[0.16em] mobile:text-[26px]">旧社交画像</h1>
              <p className="mt-2 text-[13px] leading-[1.85] tracking-[0.04em] text-[color:var(--ink2)]">此前用于社交匹配的画像；新会话记忆在“我的分身”中查看</p>
              <div className="mt-3 flex items-center gap-1.5 text-xs text-[color:var(--ink2)]"><Shield size={13} />本人查看</div>
            </header>

            <section className="flex min-w-0 items-center gap-4 border-t border-[color:var(--carve)] py-[22px] shadow-[inset_0_1px_0_var(--etch)]">
              <div className="grid h-14 w-14 shrink-0 place-items-center rounded-[8px] border border-[color:var(--rule2)] bg-[color:var(--mount)]">
                <span className="text-[26px] font-light">{Array.from(username)[0]}</span>
              </div>
              <div className="min-w-0">
                <p className="break-all text-xl tracking-[0.02em]">{username}</p>
                <p className="mt-1 text-[13px] leading-[1.85] text-[color:var(--ink2)]">
                  {[city, occupation, stage].filter(Boolean).join(" · ") || "（暂未提取到基本信息）"}
                </p>
              </div>
            </section>

            {loading ? (
              <div role="status" className="flex items-center justify-center gap-2 py-12 text-[color:var(--ink2)]">
                <Loader2 size={16} className="animate-spin" /><span className="text-sm">加载中…</span>
              </div>
            ) : isEmpty ? (
              <div className="border-t border-[color:var(--carve)] py-8 text-center">
                <p className="mb-2 text-sm text-[color:var(--ink2)]">暂无旧社交画像</p>
                <p className="text-[13px] leading-[1.85] text-[color:var(--ink2)]">新会话形成的私有记忆已单独保存，<br />请前往“我的分身”查看和管理。</p>
              </div>
            ) : (
              <>
                <Section title="兴趣" icon={Heart}>{interests.length ? <TagList items={interests} /> : <Empty hint="暂无记录" />}</Section>
                <Section title="价值观" icon={Scale}>{values.length ? <TagList items={values} /> : <Empty hint="暂无记录" />}</Section>
                <Section title="当前需求 / 想解决的问题" icon={CircleHelp}>{needs.length ? <TagList items={needs} /> : <Empty hint="暂无记录" />}</Section>
                <Section title="技能 / 可分享的经验" icon={Wrench}>{skills.length ? <TagList items={skills} /> : <Empty hint="暂无记录" />}</Section>
                <Section title="当前困境" icon={TriangleAlert}>{struggles.length ? <TagList items={struggles} /> : <Empty hint="暂无记录" />}</Section>
              </>
            )}

            <div className="flex items-start gap-2 border-t border-[color:var(--carve)] py-[22px] shadow-[inset_0_1px_0_var(--etch)]">
              <Shield size={13} className="mt-1 shrink-0 text-[color:var(--ink2)]" />
              <p className="text-[13px] leading-[1.85] text-[color:var(--ink2)]">这里保留旧社交画像，不展示新会话的私有记忆。你可以在“我的分身”中查看新记忆，或清空分身记忆和已有个人画像；聊天记录会保留。</p>
            </div>
            <Link href="/agents/me" target={embedded ? "_top" : undefined} className="btn min-h-10 px-[18px] mobile:h-auto mobile:max-w-full mobile:whitespace-normal">
              <ArrowUpRight size={14} />前往我的分身管理记忆
            </Link>
          </Glaze>
        </main>
      </div>
    </div>
  );
}

function ProfileContent() {
  const username = useAccountIdentity();
  if (!username) {
    return <div role="status" className="flex h-dvh items-center justify-center text-sm text-muted-foreground">加载中…</div>;
  }
  return <ProfileForAccount key={username} username={username} />;
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<div role="status" className="flex h-dvh items-center justify-center text-sm text-muted-foreground">加载中…</div>}>
      <ProfileContent />
    </Suspense>
  );
}
