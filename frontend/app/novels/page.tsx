"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import NovelShelf from "@/components/novel/NovelShelf";
import { LoadingState } from "@/components/novel/NovelStates";

function EmbeddedNovelShelf() {
  const embedded = useSearchParams().get("embed") === "1";
  return <div className={`h-full${embedded ? " [&_header_h1]:sr-only [&_header_h1+*]:ml-auto" : ""}`}><NovelShelf /></div>;
}

export default function NovelsPage() {
  return <Suspense fallback={<LoadingState>正在打开书斋…</LoadingState>}><EmbeddedNovelShelf /></Suspense>;
}
