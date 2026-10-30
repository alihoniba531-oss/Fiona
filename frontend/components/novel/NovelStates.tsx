import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <div role="alert" className="ceramic-card flex flex-col gap-2 p-3 text-fs-13"><p className="whitespace-pre-wrap break-words text-[color:var(--ink)]">{message}</p>{retry && <button type="button" onClick={retry} className="btn btn-quiet min-h-10 self-start">重新加载</button>}</div>;
}
export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="py-6 text-fs-13 leading-relaxed text-[color:var(--ink2)]">{children}</div>;
}
export function LoadingState({ children }: { children: ReactNode }) {
  return <p role="status" className="flex items-center gap-2 py-3 text-fs-13 text-[color:var(--ink2)]"><Loader2 size={15} className="animate-spin" />{children}</p>;
}
