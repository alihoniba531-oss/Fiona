"use client";

import { useEffect, useState } from "react";
import { ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { getStudioAssetBlob, studioErrorMessage } from "@/lib/studio";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";

export default function StudioAssetAudio({ assetId, label, className = "" }: { assetId: string; label?: string; className?: string }) {
  const owner = useAccountIdentity();
  return <AccountAssetAudio key={`${owner}:${assetId}`} owner={owner} assetId={assetId} label={label} className={className} />;
}

function AccountAssetAudio({ owner, assetId, label, className }: { owner: string; assetId: string; label?: string; className: string }) {
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const { beginRequest } = useAccountRequest(owner);
  useEffect(() => {
    const request = beginRequest();
    if (!request) return;
    let objectUrl = "";
    void (async () => {
      try {
        const blob = await getStudioAssetBlob(assetId, request.signal);
        if (!request.isCurrent()) return;
        if (!blob.type.startsWith("audio/")) throw new Error("试听音频格式无法播放，请重试。");
        objectUrl = URL.createObjectURL(blob);
        setSource(objectUrl);
        setError("");
      } catch (cause) {
        if (request.isCurrent()) setError(studioErrorMessage(cause));
      }
    })();
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [assetId, attempt, beginRequest]);
  return <div className="min-w-0 space-y-2">
    {error ? <ErrorNotice message={error} retry={() => { setError(""); setSource(""); setAttempt(value => value + 1); }} /> : source ? <>
      <audio controls preload="metadata" src={source} aria-label={label ?? "试听音频"} className={`block w-full ${className}`} />
      {label && <p className="readout text-fs-13">{label}</p>}
    </> : <LoadingState>正在加载试听音频…</LoadingState>}
  </div>;
}
