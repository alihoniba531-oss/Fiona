"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { formatStudioDate, studioErrorMessage } from "@/lib/studio";
import { getKbStats, kbSceneTypeLabel, parseKbJson, type KbStatRow, type KbStats } from "@/lib/studio-kb";

function statRows(stats: KbStats): KbStatRow[] {
  return Array.isArray(stats.scene_types) ? stats.scene_types
    : Array.isArray(stats.stats) ? stats.stats
    : Array.isArray(stats.rows) ? stats.rows
    : Array.isArray(stats.by_scene_type) ? stats.by_scene_type
    : [];
}
function distribution(value: Record<string, number> | undefined): { label: string; count: number }[] {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).filter(([, count]) => typeof count === "number" && Number.isFinite(count)).map(([label, count]) => ({ label, count }));
}

export default function KbStatsPanel({ owner }: { owner: string }) {
  const [stats, setStats] = useState<KbStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { beginRequest: beginRead } = useAccountRequest(owner);
  const load = useCallback(async () => {
    const request = beginRead();
    if (!request) return;
    setLoading(true);
    try {
      const next = await getKbStats(request.signal);
      if (!request.isCurrent()) return;
      setStats(next); setError("");
    } catch (cause) { if (request.isCurrent()) setError(studioErrorMessage(cause)); }
    finally { if (request.isCurrent()) setLoading(false); }
  }, [beginRead]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  if (loading) return <LoadingState>正在读取节奏统计…</LoadingState>;
  if (error) return <ErrorNotice message={error} retry={() => { void load(); }} />;
  if (!stats) return <EmptyState>累计满 5 集后显示你的节奏统计</EmptyState>;
  if (!stats.ready) return <div className="min-w-0 space-y-2"><EmptyState>累计满 5 集后显示你的节奏统计</EmptyState><p className="readout">当前累计 {stats.episodes ?? 0} 集</p></div>;

  const rows = statRows(stats);
  const episodes = stats.episodes ?? rows.reduce((sum, row) => sum + (row.episodes ?? 0), 0);
  const shots = stats.shots ?? rows.reduce((sum, row) => sum + (row.shots ?? 0), 0);
  return <div className="min-w-0 space-y-4">
    <div className="flex min-w-0 flex-wrap gap-2">
      <span className="chip">累计 {episodes} 集</span>
      <span className="chip">累计 {shots} 镜</span>
      {typeof stats.avg_shot_s === "number" && <span className="chip">平均每镜 {stats.avg_shot_s.toFixed(2)} 秒</span>}
    </div>
    {rows.length === 0 ? <EmptyState>统计已就绪，但还没有分场景数据。</EmptyState>
      : <div className="grid min-w-0 grid-cols-1 gap-3 @[900px]:grid-cols-2">{rows.map(row => {
        const sizes = distribution(row.shot_size ?? parseKbJson<Record<string, number>>(row.shot_size_json, {}));
        const cameras = distribution(row.camera ?? parseKbJson<Record<string, number>>(row.camera_json, {}));
        return <article key={row.scene_type} className="ceramic-card min-w-0 space-y-2 rounded-2xl p-4">
          <h3 className="break-words text-fs-16.5">{kbSceneTypeLabel(row.scene_type)}</h3>
          <p className="readout break-words">{row.episodes ?? 0} 集 · {row.shots ?? 0} 镜{typeof row.avg_shot_s === "number" ? ` · 平均 ${row.avg_shot_s.toFixed(2)} 秒/镜` : ""}</p>
          {sizes.length > 0 && <div><p className="mb-1 text-fs-12 text-[color:var(--ink2)]">景别</p><div className="flex flex-wrap gap-1">{sizes.map(item => <span key={item.label} className="tag whitespace-normal break-words">{item.label} {item.count}</span>)}</div></div>}
          {cameras.length > 0 && <div><p className="mb-1 text-fs-12 text-[color:var(--ink2)]">运镜</p><div className="flex flex-wrap gap-1">{cameras.map(item => <span key={item.label} className="tag whitespace-normal break-words">{item.label} {item.count}</span>)}</div></div>}
          {row.updated_at && <p className="readout break-words">更新于 {formatStudioDate(row.updated_at)}</p>}
        </article>;
      })}</div>}
  </div>;
}
