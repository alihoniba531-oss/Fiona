"use client";

import { EmptyState } from "@/components/novel/NovelStates";
import type { StudioJob } from "@/lib/studio";
import ShotCard, { type ShotActions } from "./ShotCard";

export default function ShotWall({ jobs, ...actions }: { jobs: StudioJob[] } & ShotActions) {
  return <section className="@container min-w-0" aria-labelledby="studio-wall-title">
    <h2 id="studio-wall-title" className="mb-4 text-xl tracking-[.24em]">镜头墙 <span className="readout">{jobs.length}</span></h2>
    {jobs.length === 0 ? <div className="ceramic-card p-5"><EmptyState>还没有试拍镜头。上传首帧，写好提示词后先看一次报价。</EmptyState></div> : <div className="grid min-w-0 grid-cols-1 items-start gap-4 @[580px]:grid-cols-2 @[920px]:grid-cols-3">{jobs.map(job => <ShotCard key={job.id} job={job} {...actions} />)}</div>}
  </section>;
}
