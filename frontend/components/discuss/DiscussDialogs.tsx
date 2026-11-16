"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { DiscussDetail, DiscussContinueInput } from "@/lib/discuss";
import { discussErrorMessage } from "@/lib/discussLogic";

const FIELD_CLASS = "ceramic-card min-h-10 w-full min-w-0 rounded-[10px] px-4 py-3 text-fs-16.5 text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";
const TOTAL_BUDGET_MAX = 20000;

function DialogFrame({
  title,
  children,
  onClose,
  submitting,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  submitting: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    // 触发按钮就是打开前的 activeElement；关闭后把焦点还回去。
    openerRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    if (!dialog.open) dialog.showModal();
    // 打开时焦点落在第一个输入框，而不是上面的「关闭」按钮。
    dialog.querySelector<HTMLElement>(
      "input:not([disabled]), select:not([disabled]), textarea:not([disabled])",
    )?.focus();
    return () => {
      if (dialog.open) dialog.close();
      const opener = openerRef.current;
      if (opener?.isConnected && opener.getClientRects().length > 0) opener.focus();
    };
  }, []);
  const requestClose = () => {
    if (!submitting) onClose();
  };
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      className="m-auto max-h-[85dvh] w-[min(520px,calc(100vw-32px))] max-w-full overflow-y-auto rounded-2xl border border-[color:var(--carve)] bg-[color:var(--paper)] text-[color:var(--ink)] scrim-dialog"
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onKeyDown={(event) => {
        // 对话框里的 Esc 只处理对话框，不冒泡去关掉主页抽屉。
        if (event.key === "Escape") event.stopPropagation();
      }}
      onClick={(event) => {
        // 原生 dialog 元素自身不带内边距，这条判断只会在遮罩上成立。
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <div className="p-6 mobile:p-4">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 id={titleId} className="text-fs-22 tracking-[.24em]">{title}</h2>
          <button type="button" className="btn btn-quiet min-h-10" disabled={submitting} onClick={requestClose}>
            关闭
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

export function DiscussBudgetDialog({
  detail,
  onConfirm,
  onClose,
}: {
  detail: DiscussDetail;
  onConfirm: (addBudget: number) => Promise<void>;
  onClose: () => void;
}) {
  const [amount, setAmount] = useState("200");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);

  const submit = async () => {
    if (submittingRef.current) return;
    const value = Number(amount);
    setError("");
    if (!Number.isInteger(value) || value < 1) {
      setError("追加预算至少 1 颗");
      return;
    }
    if (detail.budget_strawberries + value > TOTAL_BUDGET_MAX) {
      setError(`加上后总预算不能超过 ${TOTAL_BUDGET_MAX} 颗`);
      return;
    }
    if (detail.budget_strawberries + value <= detail.spent_strawberries) {
      setError("预算已经用完，请先调高预算");
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    try {
      await onConfirm(value);
      setSubmitting(false);
      onClose();
    } catch (cause) {
      submittingRef.current = false;
      setSubmitting(false);
      setError(discussErrorMessage(cause));
    }
  };

  return (
    <DialogFrame title="追加预算" onClose={onClose} submitting={submitting}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <p className="readout text-fs-12">
          当前预算 {detail.budget_strawberries} 颗 · 已花 {detail.spent_strawberries} 颗
        </p>
        <label className="block space-y-2">
          <span className="text-fs-13">追加预算（颗）</span>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={Math.max(1, TOTAL_BUDGET_MAX - detail.budget_strawberries)}
            step={1}
            value={amount}
            disabled={submitting}
            onChange={(event) => {
              setAmount(event.target.value);
              if (error) setError("");
            }}
            className={FIELD_CLASS}
          />
        </label>
        <p className="text-fs-12 leading-[1.8] text-[color:var(--ink2)]">
          至少追加 1 颗，总预算最多 {TOTAL_BUDGET_MAX} 颗。
        </p>
        {error && (
          <p role="alert" className="whitespace-pre-wrap break-words text-fs-13 text-[color:var(--seal)]">
            {error}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2 border-t border-[color:var(--carve)] pt-4">
          <button type="button" className="btn btn-quiet min-h-10" disabled={submitting} onClick={onClose}>
            取消
          </button>
          <button type="submit" className="btn btn-primary min-h-10" disabled={submitting}>
            {submitting ? "继续中…" : "继续"}
          </button>
        </div>
      </form>
    </DialogFrame>
  );
}

export function DiscussContinueDialog({
  detail,
  title,
  onConfirm,
  onClose,
}: {
  detail: DiscussDetail;
  title: string;
  onConfirm: (input: DiscussContinueInput) => Promise<void>;
  onClose: () => void;
}) {
  const [rounds, setRounds] = useState("1");
  const [budget, setBudget] = useState("0");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);

  const submit = async () => {
    if (submittingRef.current) return;
    const addRounds = Number(rounds);
    const addBudget = Number(budget);
    setError("");
    if (!Number.isInteger(addRounds) || addRounds < 1 || addRounds > 3) {
      setError("追加轮数需要 1–3 轮");
      return;
    }
    if (detail.max_rounds + addRounds > 10) {
      setError("追加后总轮数不能超过 10 轮");
      return;
    }
    if (!Number.isInteger(addBudget) || addBudget < 0) {
      setError("追加预算需要是非负整数");
      return;
    }
    if (detail.budget_strawberries + addBudget > TOTAL_BUDGET_MAX) {
      setError(`加上后总预算不能超过 ${TOTAL_BUDGET_MAX} 颗`);
      return;
    }
    if (detail.budget_strawberries + addBudget <= detail.spent_strawberries) {
      setError("预算已经用完，请先调高预算");
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    try {
      await onConfirm({ add_rounds: addRounds, add_budget: addBudget });
      setSubmitting(false);
      onClose();
    } catch (cause) {
      submittingRef.current = false;
      setSubmitting(false);
      setError(discussErrorMessage(cause));
    }
  };

  return (
    <DialogFrame title={title} onClose={onClose} submitting={submitting}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <p className="readout text-fs-12">
          当前轮数上限 {detail.max_rounds} 轮 · 预算 {detail.budget_strawberries} 颗 · 已花 {detail.spent_strawberries} 颗
        </p>
        <div className="grid grid-cols-2 gap-4 mobile:grid-cols-1">
          <label className="block min-w-0 space-y-2">
            <span className="text-fs-13">追加几轮（1–3）</span>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              max={3}
              step={1}
              value={rounds}
              disabled={submitting}
              onChange={(event) => {
                setRounds(event.target.value);
                if (error) setError("");
              }}
              className={FIELD_CLASS}
            />
          </label>
          <label className="block min-w-0 space-y-2">
            <span className="text-fs-13">追加预算（颗）</span>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={budget}
              disabled={submitting}
              onChange={(event) => {
                setBudget(event.target.value);
                if (error) setError("");
              }}
              className={FIELD_CLASS}
            />
          </label>
        </div>
        <p className="text-fs-12 leading-[1.8] text-[color:var(--ink2)]">
          追加后总轮数最多 10 轮，总预算最多 {TOTAL_BUDGET_MAX} 颗，并且要大于已花。
        </p>
        {error && (
          <p role="alert" className="whitespace-pre-wrap break-words text-fs-13 text-[color:var(--seal)]">
            {error}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2 border-t border-[color:var(--carve)] pt-4">
          <button type="button" className="btn btn-quiet min-h-10" disabled={submitting} onClick={onClose}>
            取消
          </button>
          <button type="submit" className="btn btn-primary min-h-10" disabled={submitting}>
            {submitting ? "提交中…" : "确定"}
          </button>
        </div>
      </form>
    </DialogFrame>
  );
}
