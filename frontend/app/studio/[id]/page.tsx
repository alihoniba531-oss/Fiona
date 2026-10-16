"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import StudioWorkbench from "@/components/studio/StudioWorkbench";
import { LoadingState } from "@/components/novel/NovelStates";

function WorkbenchContent() {
  const { id } = useParams<{ id: string }>();
  const embedded = useSearchParams().get("embed") === "1";
  return <StudioWorkbench id={id} embedded={embedded} />;
}
export default function StudioProjectPage() {
  return <Suspense fallback={<LoadingState>正在打开项目…</LoadingState>}><WorkbenchContent /></Suspense>;
}
