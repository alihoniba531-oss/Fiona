"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import NovelWorkbench from "@/components/novel/NovelWorkbench";
import { LoadingState } from "@/components/novel/NovelStates";

function WorkbenchContent() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  return <NovelWorkbench id={id} embedded={searchParams.get("embed") === "1"} />;
}

export default function NovelPage() {
  return <Suspense fallback={<div className="p-6"><LoadingState>正在打开这本书…</LoadingState></div>}><WorkbenchContent /></Suspense>;
}
