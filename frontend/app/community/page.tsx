"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import { UsersRound } from "lucide-react";

function CommunityContent() {
  const sp = useSearchParams();
  const embedded = sp?.get("embed") === "1";
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      {!embedded && <TopBar />}
      <div className="flex flex-1 min-h-0">
        {!embedded && <Sidebar />}
        <div className="flex flex-col flex-1 min-w-0">
          <header className="glass border-b border-border px-6 py-4 shrink-0">
            <h1 className="text-base font-semibold">社群</h1>
            <p className="text-[11px] text-muted-foreground mt-0.5">发现志同道合的人</p>
          </header>
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-8">
            <UsersRound size={40} strokeWidth={1.2} className="text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">社群功能即将上线</p>
            <p className="text-[11px] text-muted-foreground/60 max-w-xs leading-relaxed">
              Chloe会在这里帮你发现与你需求、兴趣相近的人，建立真实连接
            </p>
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
