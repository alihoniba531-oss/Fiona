"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Download, ImageOff, LoaderCircle, Maximize2, PencilLine, RotateCcw, X } from "lucide-react";
import { apiFetch } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { isLocalReferenceDataUrl } from "@/lib/generatedImages";

interface Props {
  imageUrl: string;
  width?: number;
  height?: number;
  variant?: "generated" | "reference";
  onEdit?: () => void;
  editDisabled?: boolean;
  editLabel?: string;
  editDisabledReason?: string;
  editSelected?: boolean;
  referenceIndex?: number;
  compact?: boolean;
  localPreview?: boolean;
}

export default function GeneratedImage({ imageUrl, width, height, variant = "generated", onEdit, editDisabled, editLabel = "以此图修改", editDisabledReason, editSelected, referenceIndex, compact = false, localPreview = false }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const restoreFocusRef = useRef(true);
  const [visible, setVisible] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [source, setSource] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);
  const isReference = variant === "reference";
  const referenceLabel = referenceIndex ? `参考图 ${referenceIndex}` : "参考图";
  const imageLabel = isReference ? referenceLabel : "AI 生成的图片";
  // Only references explicitly created by the local file picker may use data URLs.
  const localSource = localPreview && isLocalReferenceDataUrl(imageUrl) ? imageUrl : "";
  const previewSource = localSource || source;
  const previewError = localPreview && !localSource ? "本地参考图格式无效，请重新选择。" : error;

  useEffect(() => {
    const target = containerRef.current;
    if (!target) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "240px" });
    observer.observe(target);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || localPreview) return;
    const controller = new AbortController();
    let objectUrl = "";
    void (async () => {
      try {
        // The same authenticated local file supplies both preview and download.
        const response = await apiFetch(imageUrl, { signal: controller.signal });
        if (!response.ok) throw new Error("图片加载失败，请重试。");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        if (!blob.type.startsWith("image/")) throw new Error("图片格式无法显示，请重试。");
        objectUrl = URL.createObjectURL(blob);
        setSource(objectUrl);
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "图片加载失败，请重试。");
      }
    })();
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [visible, imageUrl, attempt, localPreview]);

  useEffect(() => {
    if (!expanded) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (restoreFocusRef.current && previousFocus?.isConnected) previousFocus.focus();
    };
  }, [expanded]);

  const retry = () => {
    setError("");
    setSource("");
    setLoaded(false);
    setAttempt(value => value + 1);
  };

  const download = () => {
    if (!previewSource) return;
    const anchor = document.createElement("a");
    const original = new URL(imageUrl, window.location.href);
    // A same-origin attachment response also supports WebViews that cannot save blob URLs.
    // Development may authenticate with a header, so it keeps the already authenticated blob.
    if (!localPreview && process.env.NODE_ENV === "production" && original.origin === window.location.origin) {
      original.searchParams.set("download", "1");
      anchor.href = original.href;
    } else {
      anchor.href = previewSource;
    }
    anchor.download = localPreview ? `参考图.${imageUrl.startsWith("data:image/jpeg;") ? "jpg" : imageUrl.startsWith("data:image/webp;") ? "webp" : "png"}`
      : imageUrl.split("/").pop()?.split("?")[0] || "生成图片.png";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  };

  const openPreview = () => {
    restoreFocusRef.current = true;
    setExpanded(true);
  };

  const selectForEdit = () => {
    if (!onEdit || editDisabled || !loaded || previewError) return;
    // Let the composer receive focus after selecting an image from the modal.
    restoreFocusRef.current = false;
    dialogRef.current?.close();
    setExpanded(false);
    onEdit();
  };

  return (
    <div
      ref={containerRef}
      className={cn("glass-card max-w-full overflow-hidden rounded-[10px] border", isReference ? "w-[120px]" : "w-[280px]", editSelected && "ring-1 ring-[color:var(--amber-ink)]")}
      style={{ borderColor: editSelected ? "var(--amber-ink)" : "var(--glass-border)" }}
    >
      <div className={cn("relative flex items-center justify-center bg-secondary/40", isReference ? (previewError ? "min-h-12" : compact ? "min-h-12 max-h-16" : "min-h-18 max-h-24") : "min-h-36 max-h-[360px]")} style={!isReference && width && height ? { aspectRatio: `${width}/${height}` } : undefined}>
        {!previewError && !loaded && <div role="status" className={cn("flex items-center gap-2 text-xs text-muted-foreground", isReference ? "p-3" : "p-6")}><LoaderCircle size={15} className="shrink-0 animate-spin" />{isReference ? "加载中…" : "正在加载图片…"}</div>}
        {previewError ? <div role="alert" className="flex flex-col items-center gap-2 p-5 text-xs text-muted-foreground">
          <ImageOff size={22} />
          <span>{previewError}</span>
          <button type="button" onClick={retry} className="btn btn-quiet h-7 px-2.5 text-xs"><RotateCcw size={12} />重新加载</button>
        </div> : previewSource && <button type="button" disabled={!loaded} aria-label={`放大${imageLabel}`} onClick={openPreview} className={loaded ? "block w-full focus-visible:outline-2 focus-visible:outline-[color:var(--ring)]" : "absolute inset-0 opacity-0"}>
          {/* Authenticated blob URLs do not use the Next image optimization proxy. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img key={attempt} src={previewSource} alt={imageLabel} loading={localPreview ? "eager" : "lazy"} onLoad={() => setLoaded(true)} onError={() => setError("图片无法显示，请重新加载。")}
            className={cn("w-full object-contain", isReference ? compact ? "max-h-16" : "max-h-24" : "max-h-[360px]")} />
        </button>}
      </div>
      <div className="flex items-center gap-1 border-t px-3 py-2 text-[11px]" style={{ borderColor: "var(--glass-border)" }}>
        <span className="mr-auto shrink-0 text-muted-foreground">{isReference ? referenceLabel : "AI 生成"}</span>
        <button type="button" aria-label={`放大${imageLabel}`} title="放大" onClick={openPreview} disabled={!loaded || !!previewError} className="btn btn-quiet h-7 px-2.5 text-xs"><Maximize2 size={12} />{!isReference && "放大"}</button>
        <button type="button" aria-label={`下载${imageLabel}`} title="下载" onClick={download} disabled={!loaded || !!previewError} className="btn btn-quiet h-7 px-2.5 text-xs"><Download size={12} />{!isReference && "下载"}</button>
      </div>
      {!isReference && onEdit && <button type="button" onClick={selectForEdit} disabled={editDisabled || !loaded || !!previewError}
        title={editDisabled ? editDisabledReason || "请等待当前操作完成，并移除待发送图片后再选择" : "选择这张图作为参考，输入希望修改的地方"}
        className={cn("btn btn-quiet h-7 w-full rounded-none border-x-0 border-b-0 border-t px-2.5 text-xs", editSelected ? "font-medium text-[color:var(--amber-ink)]" : "disabled:opacity-40")}
        style={{ borderColor: "var(--glass-border)" }}>
        <PencilLine size={12} />{editLabel}
      </button>}
      {expanded && createPortal(
        <dialog ref={dialogRef} aria-label={`${imageLabel}预览`} onCancel={() => setExpanded(false)} onClose={() => setExpanded(false)}
          onClick={event => { if (event.target === event.currentTarget) setExpanded(false); }}
          className="glass m-auto max-h-[94vh] max-w-[94vw] overflow-auto rounded-[10px] border p-0 text-foreground shadow-2xl backdrop:bg-black/75"
          style={{ borderColor: "var(--glass-border)" }}>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3" style={{ borderColor: "var(--glass-border)" }}>
            <span className="text-sm">{imageLabel}</span>
            <div className="flex items-center gap-3">
              {!isReference && onEdit && <button type="button" onClick={selectForEdit} disabled={editDisabled || !loaded || !!previewError}
                title={editDisabledReason}
                className={cn("btn btn-quiet h-7 px-2.5 text-xs", editSelected && "font-medium text-[color:var(--amber-ink)]")}><PencilLine size={14} />{editLabel}</button>}
              <button type="button" onClick={download} className="btn btn-quiet h-7 px-2.5 text-xs"><Download size={14} />下载图片</button>
              <button type="button" autoFocus aria-label="关闭图片预览" onClick={() => setExpanded(false)} className="btn btn-quiet h-7 w-7 px-0"><X size={18} /></button>
            </div>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={previewSource} alt={`${imageLabel}，大图预览`} className="max-h-[80vh] max-w-[92vw] object-contain" />
        </dialog>, document.body,
      )}
    </div>
  );
}
