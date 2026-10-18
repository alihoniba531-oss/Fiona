"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import KbWorkbench from "@/components/studio/kb/KbWorkbench";
import { LoadingState } from "@/components/novel/NovelStates";

function KbContent() {
  const embedded = useSearchParams().get("embed") === "1";
  return <KbWorkbench embedded={embedded} />;
}

export default function StudioKbPage() {
  return <Suspense fallback={<LoadingState>正在打开导演知识库…</LoadingState>}><KbContent /></Suspense>;
}
