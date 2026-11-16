"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import DiscussRoom from "@/components/discuss/DiscussRoom";
import DiscussShell from "@/components/discuss/DiscussShell";
import { LoadingState } from "@/components/novel/NovelStates";

function DiscussGroupContent() {
  const { id } = useParams<{ id: string }>();
  const embedded = useSearchParams().get("embed") === "1";
  return (
    <DiscussShell embedded={embedded}>
      <DiscussRoom id={id} embedded={embedded} />
    </DiscussShell>
  );
}

export default function DiscussGroupPage() {
  return (
    <Suspense fallback={<div className="p-6"><LoadingState>正在打开讨论群…</LoadingState></div>}>
      <DiscussGroupContent />
    </Suspense>
  );
}
