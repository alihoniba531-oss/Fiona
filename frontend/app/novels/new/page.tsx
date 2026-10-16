"use client";

import { Suspense } from "react";
import NovelWizard from "@/components/novel/NovelWizard";
import { LoadingState } from "@/components/novel/NovelStates";

export default function NewNovelPage() {
  return <Suspense fallback={<LoadingState>正在准备建书向导…</LoadingState>}><NovelWizard /></Suspense>;
}
