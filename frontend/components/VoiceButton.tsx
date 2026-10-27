"use client";

import { useEffect, useRef, useState, type JSX, type MouseEvent, type PointerEvent } from "react";
import { Mic } from "lucide-react";
import { cn } from "@/lib/utils";

const HINT_KEY = "chloe-voice-hint-v1";
const HINT_DURATION_MS = 4000;
const CLICK_AFTER_POINTERUP_MS = 500;

export default function VoiceButton({ disabled, dictating, holding, onTap, onHoldStart, onHoldEnd, holdDelayMs = 350 }: {
  disabled: boolean;
  dictating: boolean;
  holding: boolean;
  onTap: () => void;
  onHoldStart: () => void;
  onHoldEnd: () => void;
  holdDelayMs?: number;
}): JSX.Element {
  const [showHint, setShowHint] = useState(false);
  const holdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pressingRef = useRef(false);
  const longPressRef = useRef(false);
  const pointerUpHandledRef = useRef(false);
  const captureLostAfterPointerUpRef = useRef(false);
  const pointerUpAtRef = useRef(Number.NEGATIVE_INFINITY);

  const clearHoldTimer = () => {
    if (holdTimerRef.current !== null) {
      clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
  };

  const showHintOnce = () => {
    try {
      if (localStorage.getItem(HINT_KEY) !== null) return;
      localStorage.setItem(HINT_KEY, "1");
    } catch {
      return;
    }
    setShowHint(true);
    if (hintTimerRef.current !== null) clearTimeout(hintTimerRef.current);
    hintTimerRef.current = setTimeout(() => {
      hintTimerRef.current = null;
      setShowHint(false);
    }, HINT_DURATION_MS);
  };

  const handleTap = () => {
    if (!dictating) showHintOnce();
    onTap();
  };

  const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (disabled || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    pressingRef.current = true;
    longPressRef.current = false;
    pointerUpHandledRef.current = false;
    captureLostAfterPointerUpRef.current = false;
    if (dictating) return;
    holdTimerRef.current = setTimeout(() => {
      holdTimerRef.current = null;
      if (!pressingRef.current) return;
      longPressRef.current = true;
      onHoldStart();
    }, holdDelayMs);
  };

  const handlePointerUp = (event: PointerEvent<HTMLButtonElement>) => {
    clearHoldTimer();
    const wasLongPress = longPressRef.current;
    longPressRef.current = false;
    if (!pressingRef.current) return;
    pressingRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (wasLongPress) onHoldEnd();
    else handleTap();
    pointerUpHandledRef.current = true;
    pointerUpAtRef.current = performance.now();
    captureLostAfterPointerUpRef.current = false;
  };

  const handlePointerCancel = () => {
    clearHoldTimer();
    pressingRef.current = false;
    pointerUpHandledRef.current = false;
    captureLostAfterPointerUpRef.current = false;
    if (longPressRef.current) {
      longPressRef.current = false;
      onHoldEnd();
    }
  };

  const handleLostPointerCapture = () => {
    clearHoldTimer();
    pressingRef.current = false;
    captureLostAfterPointerUpRef.current = pointerUpHandledRef.current;
    pointerUpHandledRef.current = false;
    if (longPressRef.current) {
      longPressRef.current = false;
      onHoldEnd();
    }
  };

  const handleClick = () => {
    const hadPointerMarker = pointerUpHandledRef.current || captureLostAfterPointerUpRef.current;
    if (pointerUpHandledRef.current) {
      pointerUpHandledRef.current = false;
    }
    if (captureLostAfterPointerUpRef.current) {
      captureLostAfterPointerUpRef.current = false;
    }
    if (hadPointerMarker && performance.now() - pointerUpAtRef.current <= CLICK_AFTER_POINTERUP_MS) {
      return;
    }
    handleTap();
  };

  const handleContextMenu = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
  };

  useEffect(() => {
    return () => {
      if (holdTimerRef.current !== null) clearTimeout(holdTimerRef.current);
      if (hintTimerRef.current !== null) clearTimeout(hintTimerRef.current);
    };
  }, []);

  const stateLabel = holding
    ? "正在录音，松开发送"
    : dictating
      ? "正在录音，轻点发送"
      : "语音：轻点开始录音，再点一下发送；按住说话，松开发送";
  const shortLabel = holding ? "松开发送" : dictating ? "点此发送" : "语音";

  return (
    <div className="relative inline-flex">
      {showHint && (
        <span role="status" className="ceramic-card absolute bottom-full right-0 z-[60] mb-2 whitespace-nowrap px-3 py-2 text-xs leading-relaxed text-[color:var(--ink2)]">
          也可以按住说话，松开就发送
        </span>
      )}
      <button
        type="button"
        disabled={disabled}
        aria-label={stateLabel}
        title={stateLabel}
        className={cn("btn btn-quiet h-8 px-2.5 text-xs max-md:h-10 max-md:w-10 max-md:px-0 select-none", (dictating || holding) && "text-[color:var(--rec)] bg-[color:var(--rec-soft)]")}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onLostPointerCapture={handleLostPointerCapture}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      >
        <Mic size={14} aria-hidden="true" />
        <span className="max-md:hidden">{shortLabel}</span>
      </button>
    </div>
  );
}
