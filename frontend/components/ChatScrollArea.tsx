"use client";

import {
  forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect,
  useRef, useState, type ReactNode,
} from "react";
import { ArrowDown } from "lucide-react";

export interface ChatScrollHandle {
  scrollToLatest(): void;
}

interface Props {
  children: ReactNode;
  resetKey: string;
}

const BOTTOM_TOLERANCE = 2;

export default forwardRef<ChatScrollHandle, Props>(function ChatScrollArea({ children, resetKey }, ref) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const followingRef = useRef(true);
  const frameRef = useRef<number | null>(null);
  const previousRef = useRef<{ top: number; max: number } | null>(null);
  const upwardIntentRef = useRef(false);
  const touchYRef = useRef<number | null>(null);
  const [showLatest, setShowLatest] = useState(false);

  const updateButton = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const distance = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop;
    setShowLatest(!followingRef.current && distance > BOTTOM_TOLERANCE);
  }, []);

  const scheduleFollow = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const viewport = viewportRef.current;
      if (!viewport) return;
      if (followingRef.current) {
        // Scroll only this viewport. Smooth scrolling can lag behind text growth
        // and scrollIntoView can also move the surrounding clipped panels.
        viewport.scrollTop = viewport.scrollHeight;
        previousRef.current = {
          top: viewport.scrollTop,
          max: Math.max(0, viewport.scrollHeight - viewport.clientHeight),
        };
      }
      updateButton();
    });
  }, [updateButton]);

  const scrollToLatest = useCallback(() => {
    followingRef.current = true;
    upwardIntentRef.current = false;
    scheduleFollow();
  }, [scheduleFollow]);

  useImperativeHandle(ref, () => ({ scrollToLatest }), [scrollToLatest]);

  useLayoutEffect(() => {
    previousRef.current = null;
    scrollToLatest();
  }, [resetKey, scrollToLatest]);

  useEffect(() => {
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (!viewport || !content) return;
    const observer = new ResizeObserver(scheduleFollow);
    // The content grows after SSE completion while ChatBubble is still typing;
    // the viewport shrinks independently when the composer or window changes.
    observer.observe(content);
    observer.observe(viewport);
    scheduleFollow();
    return () => {
      observer.disconnect();
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, [scheduleFollow]);

  const noteScrollIntent = (direction: number) => {
    if (direction < 0 && (viewportRef.current?.scrollTop ?? 0) > 0) {
      upwardIntentRef.current = true;
      followingRef.current = false;
      updateButton();
    } else if (direction > 0) {
      upwardIntentRef.current = false;
    }
  };

  const onScroll = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const top = viewport.scrollTop;
    const max = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    const previous = previousRef.current;
    const atBottom = max - top <= BOTTOM_TOLERANCE;
    // A larger viewport or shorter content clamps scrollTop downward without
    // any user input. Do not treat that automatic clamp as an upward gesture.
    const clampedByResize = previous && max < previous.max && atBottom && !upwardIntentRef.current;
    if (previous && top < previous.top - BOTTOM_TOLERANCE && !clampedByResize) {
      followingRef.current = false;
    }
    if (atBottom && !upwardIntentRef.current) followingRef.current = true;
    previousRef.current = { top, max };
    upwardIntentRef.current = false;
    updateButton();
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col" data-chat-scroll-area>
      <div ref={viewportRef} role="region" aria-label="聊天消息" tabIndex={0}
        data-chat-scroll-viewport
        className="min-h-0 flex-1 overflow-y-auto outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary/40"
        style={{ overflowAnchor: "none", scrollBehavior: "auto" }}
        onScroll={onScroll}
        onWheel={event => { if (!event.ctrlKey) noteScrollIntent(event.deltaY); }}
        onTouchStart={event => { touchYRef.current = event.touches[0]?.clientY ?? null; }}
        onTouchMove={event => {
          const nextY = event.touches[0]?.clientY;
          if (nextY !== undefined && touchYRef.current !== null) noteScrollIntent(touchYRef.current - nextY);
          touchYRef.current = nextY ?? null;
        }}
        onTouchEnd={() => { touchYRef.current = null; }}
        onKeyDown={event => {
          const target = event.target as HTMLElement;
          if (event.defaultPrevented || target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
          if (["ArrowUp", "PageUp", "Home"].includes(event.key) || (event.key === " " && event.shiftKey && target === event.currentTarget)) noteScrollIntent(-1);
          if (["ArrowDown", "PageDown", "End"].includes(event.key) || (event.key === " " && !event.shiftKey && target === event.currentTarget)) noteScrollIntent(1);
        }}>
        <div ref={contentRef} className="space-y-4 px-6 py-4" data-chat-scroll-content>{children}</div>
      </div>
      {showLatest && <button type="button" onClick={scrollToLatest}
        className="absolute bottom-3 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-border bg-background/95 px-3 py-1.5 text-xs text-muted-foreground shadow-sm hover:text-foreground focus-visible:outline-2 focus-visible:outline-primary">
        <ArrowDown size={12} />回到最新
      </button>}
    </div>
  );
});
