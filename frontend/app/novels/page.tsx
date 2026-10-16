"use client";

import { Suspense } from "react";
import NovelShelf from "@/components/novel/NovelShelf";
import { LoadingState } from "@/components/novel/NovelStates";

export default function NovelsPage() {
  return <Suspense fallback={<LoadingState>正在打开书斋…</LoadingState>}><NovelShelf /></Suspense>;
}
