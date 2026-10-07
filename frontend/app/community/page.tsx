"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import InkLandscape from "@/components/InkLandscape";

function CommunityContent() {
  const sp = useSearchParams();
  const embedded = sp?.get("embed") === "1";
  return (
    <div className={`relative flex h-dvh flex-col overflow-hidden ${!embedded ? "mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]" : ""}`}>
      <InkLandscape variant="page" />
      <div className="relative z-[1] flex flex-1 min-h-0">
        {!embedded && <Sidebar />}
        <div className="flex flex-col flex-1 min-w-0">
          <header className="mx-auto w-full max-w-[1236px] shrink-0 px-[72px] pb-[22px] pt-7 mobile:px-4 mobile:pt-4">
            <div className="flex items-end justify-between gap-4 border-b pb-[22px]" style={{ borderColor: "var(--rule)" }}>
              <div>
                <h1 className="text-[30px] font-medium tracking-[.24em]">社群</h1>
                <p className="mt-2 text-[14px] tracking-[.04em] text-[color:var(--ink2)]">发现志同道合的人</p>
              </div>
            </div>
          </header>
          <div className="flex flex-1 items-center justify-center px-8 text-center mobile:px-4">
            <div className="ceramic-card p-8">
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
