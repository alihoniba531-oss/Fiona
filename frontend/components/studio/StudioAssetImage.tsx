"use client";

import { useEffect, useState } from "react";
import { ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { getStudioAssetBlob, studioErrorMessage } from "@/lib/studio";
import { useAccountIdentity, useAccountRequest } from "@/lib/useAccountIdentity";

export default function StudioAssetImage({ assetId, alt, className = "" }: { assetId: string; alt: string; className?: string }) {
  const owner = useAccountIdentity();
  return <AccountAssetImage key={`${owner}:${assetId}`} owner={owner} assetId={assetId} alt={alt} className={className} />;
}

function AccountAssetImage({ owner, assetId, alt, className }: { owner: string; assetId: string; alt: string; className: string }) {
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
        if (!blob.type.startsWith("image/")) throw new Error("首帧格式无法显示，请重试。");
        objectUrl = URL.createObjectURL(blob);
        setSource(objectUrl);
        setError("");
      } catch (cause) {
        if (request.isCurrent()) setError(studioErrorMessage(cause));
      }
    })();
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [assetId, attempt, beginRequest]);
  return <div className="min-w-0">
    {error ? <ErrorNotice message={error} retry={() => { setError(""); setSource(""); setAttempt(value => value + 1); }} /> : source ? <>
      {/* Authenticated blobs bypass the Next image optimization proxy. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={source} alt={alt} onError={() => setError("首帧无法显示，请重新加载。")} className={`block w-full object-contain ${className}`} />
    </> : <LoadingState>正在加载首帧…</LoadingState>}
  </div>;
}
