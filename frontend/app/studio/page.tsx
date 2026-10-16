"use client";

import { Suspense } from "react";
import StudioShelf from "@/components/studio/StudioShelf";
import { LoadingState } from "@/components/novel/NovelStates";

export default function StudioPage() {
  return <Suspense fallback={<LoadingState>正在打开短片工作室…</LoadingState>}><StudioShelf /></Suspense>;
}
