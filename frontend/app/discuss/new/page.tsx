"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import DiscussCreateForm from "@/components/discuss/DiscussCreateForm";
import DiscussShell from "@/components/discuss/DiscussShell";
import { LoadingState } from "@/components/novel/NovelStates";

function NewDiscussContent() {
  const embedded = useSearchParams().get("embed") === "1";
  return <DiscussShell embedded={embedded}><DiscussCreateForm embedded={embedded} /></DiscussShell>;
}

export default function NewDiscussPage() {
  return <Suspense fallback={<div className="p-6"><LoadingState>正在打开讨论群…</LoadingState></div>}>
    <NewDiscussContent />
  </Suspense>;
}
