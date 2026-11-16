"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import DiscussShell from "@/components/discuss/DiscussShell";
import DiscussShelf from "@/components/discuss/DiscussShelf";
import { LoadingState } from "@/components/novel/NovelStates";

function DiscussShelfContent() {
  const embedded = useSearchParams().get("embed") === "1";
  return <DiscussShell embedded={embedded}><DiscussShelf embedded={embedded} /></DiscussShell>;
}

export default function DiscussPage() {
  return <Suspense fallback={<div className="p-6"><LoadingState>正在打开讨论群…</LoadingState></div>}>
    <DiscussShelfContent />
  </Suspense>;
}
