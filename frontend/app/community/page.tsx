"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";

function CommunityContent() {
  const sp = useSearchParams();
  const embedded = sp?.get("embed") === "1";
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <div className="flex flex-1 min-h-0">
        {!embedded && <Sidebar />}
        <div className="flex flex-col flex-1 min-w-0">
          <header className="glass sticky top-0 z-[2] shrink-0 border-b px-8 pb-[18px] pt-7" style={{ borderColor: "var(--glass-border)" }}>
            <div className="flex max-w-[976px] items-end justify-between gap-4">
              <div>
                <h1 className="text-xl font-medium tracking-[-0.01em]">社群</h1>
                <p className="mt-1 text-[13px] text-muted-foreground">发现志同道合的人</p>
              </div>
            </div>
          </header>
          <div className="flex flex-1 items-center justify-center px-8 text-center">
            <div className="glass-card p-8">
              <p className="text-sm text-muted-foreground">社群功能即将上线</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function CommunityPage() {
  return (
    <Suspense fallback={null}>
      <CommunityContent />
    </Suspense>
  );
}
