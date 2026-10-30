"use client";

import { useEffect, useRef, useState, type JSX, type KeyboardEvent } from "react";
import { ImagePlus } from "lucide-react";
import { cn } from "@/lib/utils";

export type ImageMenuItem = {
  key: "see" | "generate" | "edit";
  label: string;
  description: string;
  disabled: boolean;
  title?: string;
  onSelect: () => void;
};

export default function ComposerImageMenu({ items, disabled = false, active = false }: { items: ImageMenuItem[]; disabled?: boolean; active?: boolean }): JSX.Element {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const allDisabled = items.every((item) => item.disabled);
  const triggerDisabled = disabled || allDisabled;
  const isOpen = open && !triggerDisabled;
  const firstEnabledIndex = items.findIndex((item) => !item.disabled);

  useEffect(() => {
    if (!triggerDisabled) return;
    // R2-4: drop the open state while disabled so re-enabling does not reopen the menu.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOpen(false);
  }, [triggerDisabled]);

  useEffect(() => {
    if (!isOpen) return;
    itemRefs.current[firstEnabledIndex]?.focus();
  }, [isOpen, firstEnabledIndex]);

  useEffect(() => {
    if (!isOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [isOpen]);

  const focusEnabledItem = (step: 1 | -1) => {
    const enabledItems = itemRefs.current.filter((item): item is HTMLButtonElement => !!item && !item.disabled);
    if (!enabledItems.length) return;
    const currentIndex = enabledItems.indexOf(document.activeElement as HTMLButtonElement);
    const nextIndex = currentIndex < 0
      ? (step === 1 ? 0 : enabledItems.length - 1)
      : (currentIndex + step + enabledItems.length) % enabledItems.length;
    enabledItems[nextIndex]?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!isOpen) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      triggerRef.current?.focus();
      return;
    }
    if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      focusEnabledItem(event.key === "ArrowDown" ? 1 : -1);
    }
  };

  const handleSelect = (item: ImageMenuItem) => {
    setOpen(false);
    item.onSelect();
    triggerRef.current?.focus();
  };

  return (
    <div ref={rootRef} className="relative" onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        disabled={triggerDisabled}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="图片：发图给 Chloe 看、生成图片或改一张图"
        className={cn("btn btn-quiet h-8 px-2 text-fs-12 max-md:h-10", active && "text-[color:var(--ink)]")}
        onClick={() => setOpen((previous) => !previous)}
      >
        <ImagePlus size={14} aria-hidden="true" />
        <span>图片</span>
      </button>
      {isOpen && (
        <div
          role="menu"
          aria-label="图片操作"
          className="ceramic-card absolute bottom-full left-0 z-[60] mb-2 w-[min(280px,calc(100vw-32px))] p-1.5"
          style={{ backdropFilter: "var(--bd)", WebkitBackdropFilter: "var(--bd)" }}
        >
          {items.map((item, index) => (
            <button
              key={item.key}
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              title={item.title}
              className="min-h-11 w-full rounded-[8px] px-3 py-2 text-left hover:bg-[color:var(--fill)] disabled:opacity-45 disabled:cursor-not-allowed"
              onClick={() => handleSelect(item)}
            >
              <span className="block text-fs-15 text-[color:var(--ink)]">{item.label}</span>
              <span className="block text-fs-12 text-[color:var(--ink2)]">{item.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
