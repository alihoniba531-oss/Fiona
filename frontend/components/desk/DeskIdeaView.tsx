import { EmptyState } from "@/components/novel/NovelStates";
import type { NovelDetail } from "@/lib/novels";

type DeskIdeaViewProps = {
  book: NovelDetail;
  onOpenNovel: (path: string) => void;
};

function clean(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

export default function DeskIdeaView({ book, onOpenNovel }: DeskIdeaViewProps) {
  const compass = book.compass;
  const openButton = (
    <div className="mt-4 border-t border-[color:var(--rule)] pt-2">
      <button type="button" className="btn btn-quiet min-h-10" onClick={() => onOpenNovel("/novels/" + book.id + "?embed=1")}>
        在书斋打开
      </button>
    </div>
  );

  if (!compass) {
    return (
      <div className="min-w-0">
        <EmptyState>立意还没定下来。</EmptyState>
        {openButton}
      </div>
    );
  }

  const logline = clean(compass.logline);
  const theme = clean(compass.theme);
  const coreConflict = clean(compass.core_conflict);
  const protagonist = compass.protagonist;
  const protagonistName = clean(protagonist?.name);
  const protagonistWant = clean(protagonist?.want);
  const protagonistNeed = clean(protagonist?.need);
  const threads = (compass.main_threads ?? [])
    .map(thread => ({ name: clean(thread.name), description: clean(thread.description) }))
    .filter(thread => thread.name || thread.description);

  return (
    <div className="min-w-0">
      <dl className="min-w-0">
        {logline && (
          <div className="grid min-w-0 grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-[color:var(--rule)] py-3 last:border-b-0">
            <dt className="text-fs-12 text-[color:var(--ink2)]">一句话故事</dt>
            <dd className="min-w-0 whitespace-pre-wrap break-words text-fs-15">{logline}</dd>
          </div>
        )}
        {theme && (
          <div className="grid min-w-0 grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-[color:var(--rule)] py-3 last:border-b-0">
            <dt className="text-fs-12 text-[color:var(--ink2)]">主题</dt>
            <dd className="min-w-0 whitespace-pre-wrap break-words text-fs-15">{theme}</dd>
          </div>
        )}
        {coreConflict && (
          <div className="grid min-w-0 grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-[color:var(--rule)] py-3 last:border-b-0">
            <dt className="text-fs-12 text-[color:var(--ink2)]">核心冲突</dt>
            <dd className="min-w-0 whitespace-pre-wrap break-words text-fs-15">{coreConflict}</dd>
          </div>
        )}
        {(protagonistName || protagonistWant || protagonistNeed) && (
          <div className="grid min-w-0 grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-[color:var(--rule)] py-3 last:border-b-0">
            <dt className="text-fs-12 text-[color:var(--ink2)]">主角</dt>
            <dd className="min-w-0 space-y-1 whitespace-pre-wrap break-words text-fs-15">
              {protagonistName && <p>{protagonistName}</p>}
              {protagonistWant && <p>想要：{protagonistWant}</p>}
              {protagonistNeed && <p>需要：{protagonistNeed}</p>}
            </dd>
          </div>
        )}
        {threads.length > 0 && (
          <div className="grid min-w-0 grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-[color:var(--rule)] py-3 last:border-b-0">
            <dt className="text-fs-12 text-[color:var(--ink2)]">主线</dt>
            <dd className="min-w-0 space-y-1 whitespace-pre-wrap break-words text-fs-15">
              {threads.map((thread, index) => (
                <p key={index}>{thread.name && thread.description ? `${thread.name}：${thread.description}` : thread.name || thread.description}</p>
              ))}
            </dd>
          </div>
        )}
      </dl>
      {openButton}
    </div>
  );
}
