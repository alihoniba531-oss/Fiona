"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import StudioShelf from "@/components/studio/StudioShelf";
import { LoadingState } from "@/components/novel/NovelStates";
import { studioHref } from "@/lib/studio";

function KbEntryLink() {
  const embedded = useSearchParams().get("embed") === "1";
  return <Link href={studioHref("/studio/kb", embedded)} className="btn btn-quiet min-h-10">导演知识库</Link>;
}

export default function StudioPage() {
  return <div className="flex h-dvh min-w-0 flex-col">
    <header className="shrink-0 border-b border-[color:var(--carve)]">
      <div className="mx-auto flex w-full max-w-[1440px] justify-end px-4 py-2">
        <Suspense fallback={<span className="btn btn-quiet min-h-10">导演知识库</span>}><KbEntryLink /></Suspense>
      </div>
    </header>
    <div className="min-h-0 flex-1 [&>div]:h-full">
      <Suspense fallback={<LoadingState>正在打开短片工作室…</LoadingState>}><StudioShelf /></Suspense>
    </div>
  </div>;
}
