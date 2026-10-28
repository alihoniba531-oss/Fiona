"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

export interface ConfirmOptions {
  body: string;
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

export interface NoticeOptions {
  body: string;
  title?: string;
  okLabel?: string;
}

interface QueueItem {
  kind: "confirm" | "notice";
  body: string;
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  okLabel?: string;
  resolve: (result: boolean | undefined) => void;
}

let host: ((item: QueueItem) => void) | null = null;

function confirmImpl(options: ConfirmOptions): Promise<boolean> {
  const enqueue = host;
  if (!enqueue) return Promise.reject(new Error("ConfirmProvider missing"));
  return new Promise<boolean>((resolve) => {
    enqueue({
      kind: "confirm",
      body: options.body,
      title: options.title,
      confirmLabel: options.confirmLabel,
      cancelLabel: options.cancelLabel,
      danger: options.danger,
      resolve: (result) => resolve(result === true),
    });
  });
}

function noticeImpl(options: NoticeOptions): Promise<void> {
  const enqueue = host;
  if (!enqueue) return Promise.reject(new Error("ConfirmProvider missing"));
  return new Promise<void>((resolve) => {
    enqueue({
      kind: "notice",
      body: options.body,
      title: options.title,
      okLabel: options.okLabel,
      resolve: () => resolve(),
    });
  });
}

export function useConfirm(): (options: ConfirmOptions) => Promise<boolean> {
  return confirmImpl;
}

export function useNotice(): (options: NoticeOptions) => Promise<void> {
  return noticeImpl;
}

export function ConfirmProvider({ children }: { children: ReactNode }): ReactElement {
  const [active, setActive] = useState<QueueItem | null>(null);
  const queueRef = useRef<QueueItem[]>([]);
  const activeRef = useRef<QueueItem | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const okRef = useRef<HTMLButtonElement>(null);
  const baseId = useId();
  const titleId = `${baseId}-confirm-title`;
  const bodyId = `${baseId}-confirm-body`;

  const pump = useCallback(() => {
    if (activeRef.current) return;
    const next = queueRef.current.shift();
    if (!next) return;
    activeRef.current = next;
    setActive(next);
  }, []);

  const enqueue = useCallback((item: QueueItem) => {
    queueRef.current.push(item);
    pump();
  }, [pump]);

  useEffect(() => {
    host = enqueue;
    return () => {
      if (host === enqueue) host = null;
    };
  }, [enqueue]);

  const settle = useCallback((result?: boolean) => {
    const item = activeRef.current;
    if (!item) return;
    activeRef.current = null;
    const dialog = dialogRef.current;
    if (dialog?.open) dialog.close();
    setActive(null);
    item.resolve(result);
    const opener = openerRef.current;
    openerRef.current = null;
    if (opener?.isConnected) opener.focus();
    pump();
  }, [pump]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || !active) return;
    if (!dialog.open) {
      if (openerRef.current === null) {
        openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      }
      dialog.showModal();
    }
    (active.kind === "confirm" ? cancelRef.current : okRef.current)?.focus();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, [active]);

  const dialog = (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      role={active?.kind === "confirm" ? "alertdialog" : undefined}
      aria-labelledby={active?.title ? titleId : undefined}
      aria-describedby={active ? bodyId : undefined}
      onCancel={(event) => {
        event.preventDefault();
        settle(false);
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) settle(false);
      }}
    >
      {active && (
        <div className="px-6 pt-6 pb-5">
          {active.title && <h2 id={titleId} className="text-base tracking-[.06em] mb-3">{active.title}</h2>}
          <p id={bodyId} className="whitespace-pre-wrap text-[15px] leading-[1.85] text-[color:var(--ink)]">{active.body}</p>
          <div className="mt-6 flex justify-end gap-2">
            {active.kind === "confirm" ? (
              <>
                <button ref={cancelRef} type="button" className="btn btn-quiet" onClick={() => settle(false)}>
                  {active.cancelLabel ?? "取消"}
                </button>
                <button
                  type="button"
                  className={active.danger ? "btn btn-danger" : "btn btn-primary"}
                  onClick={() => settle(true)}
                >
                  {active.confirmLabel ?? "确定"}
                </button>
              </>
            ) : (
              <button ref={okRef} type="button" className="btn btn-primary" onClick={() => settle(undefined)}>
                {active.okLabel ?? "知道了"}
              </button>
            )}
          </div>
        </div>
      )}
    </dialog>
  );

  return (
    <>
      {children}
      {dialog}
    </>
  );
}
