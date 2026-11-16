"use client";

import { useRef, useState, type ChangeEvent, type JSX, type KeyboardEvent } from "react";
import type { DiscussStatus } from "@/lib/discuss";
import { discussErrorMessage } from "@/lib/discussLogic";

const MAX_LENGTH = 500;

export default function DiscussComposer({
  status,
  pendingNotes,
  busy,
  onSend,
}: {
  status: DiscussStatus;
  pendingNotes: number;
  busy: boolean;
  onSend: (text: string) => Promise<void>;
}): JSX.Element {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const composingRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const count = Array.from(text).length;

  const submit = async () => {
    const value = text.trim();
    if (!value || sendingRef.current || busy) return;
    sendingRef.current = true;
    setSending(true);
    setError("");
    try {
      await onSend(value);
      setText("");
    } catch (caught) {
      setError(discussErrorMessage(caught));
    } finally {
      sendingRef.current = false;
      setSending(false);
      // 成功或失败都把焦点留在插话框，键盘用户可以接着输入。
      textareaRef.current?.focus();
    }
  };

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const next = Array.from(event.target.value).slice(0, MAX_LENGTH).join("");
    setText(next);
    if (error) setError("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    if (event.nativeEvent.isComposing || composingRef.current) return;
    event.preventDefault();
    void submit();
  };

  if (status === "closed") {
    return (
      <p className="shrink-0 px-1 py-2 text-fs-13 text-[color:var(--ink2)]">
        这个群已经结束，不能再插话。
      </p>
    );
  }
  if (status === "failed") {
    return (
      <p className="shrink-0 px-1 py-2 text-fs-13 text-[color:var(--ink2)]">
        出错停下了。点继续之后可以再插话。
      </p>
    );
  }

  return (
    <div className="shrink-0 space-y-2 border-t border-[color:var(--rule)] pt-3">
      {pendingNotes > 0 && (
        <p className="text-fs-12 text-[color:var(--ink2)]">还有 {pendingNotes} 条插话没被读到。</p>
      )}
      {status === "done" && (
        <p className="text-fs-12 text-[color:var(--ink2)]">写下意见后，点上面的按意见返工。</p>
      )}
      {status === "awaiting_start" && (
        <p className="text-fs-12 text-[color:var(--ink2)]">开工前写的话，成员开工时都能看到。</p>
      )}
      {error && (
        <p role="alert" className="whitespace-pre-wrap break-words text-fs-12 text-[color:var(--seal)]">
          {error}
        </p>
      )}
      <div className="ceramic-card p-2">
        <textarea
          ref={textareaRef}
          data-discuss-composer
          aria-label="插话"
          rows={2}
          value={text}
          readOnly={sending || busy}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => { composingRef.current = true; }}
          onCompositionEnd={() => { composingRef.current = false; }}
          className="block min-h-[52px] w-full resize-none bg-transparent px-1 py-1 text-fs-15 leading-[1.8] text-[color:var(--ink)] outline-none placeholder:text-[color:var(--ink2)] read-only:opacity-60"
        />
        <div className="mt-1 flex items-center justify-end gap-3">
          <span className="readout text-fs-11">{count} / 500</span>
          <button
            type="button"
            className="btn btn-primary"
            disabled={sending || busy || !text.trim()}
            onClick={() => void submit()}
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
