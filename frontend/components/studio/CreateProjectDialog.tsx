"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { novelFieldClass } from "@/components/novel/NovelModelFields";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/novel/NovelStates";
import { useAccountRequest } from "@/lib/useAccountIdentity";
import { listStudioNovelSources, listStudioExchangeSources, formatStudioDate, studioErrorMessage, type StudioProject, type StudioCreateInput, type StudioNovelSources, type StudioExchangeSource } from "@/lib/studio";
import { NovelSourceChoice, SourceAspectPicker, sourceDialogClass } from "./SourceChoices";

export function validateStudioSourceFile(file: Pick<File, "name" | "size">): string {
  if (!/\.(txt|md|docx)$/i.test(file.name)) return "仅支持 txt、md、docx 文件。";
  return file.size > 10 * 1024 * 1024 ? "文件不能超过 10 MB。" : "";
}
export function CreateProjectDialog({ owner, embedded = false, busy, onCreate, onClose }: { owner: string; embedded?: boolean; busy: boolean; onCreate: (input: StudioCreateInput) => Promise<void>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState("");
  const [aspect, setAspect] = useState<StudioProject["aspect"]>("16:9");
  const [kind, setKind] = useState<StudioCreateInput["kind"]>("blank");
  const [novels, setNovels] = useState<StudioNovelSources>({ enabled: false, books: [] });
  const [exchanges, setExchanges] = useState<StudioExchangeSource[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [sourceError, setSourceError] = useState("");
  const [query, setQuery] = useState("");
  const [bookId, setBookId] = useState("");
  const [exchangeId, setExchangeId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const lock = useRef(false);
  const { beginRequest } = useAccountRequest(owner);
  const loadSources = useCallback(async () => {
    const request = beginRequest(); if (!request) return;
    setSourcesLoading(true); setSourceError("");
    const results = await Promise.allSettled([listStudioNovelSources(request.signal), listStudioExchangeSources(request.signal)]);
    if (!request.isCurrent()) return;
    if (results[0].status === "fulfilled") setNovels(results[0].value);
    if (results[1].status === "fulfilled") setExchanges(results[1].value);
    const failures = results.flatMap(result => result.status === "rejected" ? [studioErrorMessage(result.reason)] : []);
    setSourceError(failures.join("；")); setSourcesLoading(false);
  }, [beginRequest]);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  useEffect(() => { void Promise.resolve().then(loadSources); }, [loadSources]);
  const invalidFile = file ? validateStudioSourceFile(file) : "";
  const textLength = Array.from(text).length;
  const selectedBook = novels.books.find(book => book.id === bookId);
  const canSubmit = !!title.trim() && (kind === "blank" || kind === "novel" && !!selectedBook?.eligible || kind === "exchange" && !!exchangeId || kind === "upload" && !!file && !invalidFile || kind === "paste" && !!text.trim() && textLength <= 500000);
  const submit = async () => {
    if (lock.current || busy || !canSubmit) return;
    lock.current = true; setError("");
    const common = { title: title.trim(), aspect };
    let input: StudioCreateInput;
    if (kind === "novel") input = { ...common, kind, book_id: bookId };
    else if (kind === "exchange") input = { ...common, kind, exchange_id: exchangeId };
    else if (kind === "upload" && file) input = { ...common, kind, file };
    else if (kind === "paste") input = { ...common, kind, text };
    else input = { ...common, kind: "blank" };
    try { await onCreate(input); }
    catch (cause) { setError(studioErrorMessage(cause)); }
    finally { lock.current = false; }
  };
  const choices = [{ id: "blank", label: "空白项目" }, ...(novels.enabled ? [{ id: "novel", label: "小说工坊" }] : []), { id: "upload", label: "上传文件" }, { id: "paste", label: "粘贴文本" }, { id: "exchange", label: "创意搭档成稿" }] as { id: StudioCreateInput["kind"]; label: string }[];
  const filteredBooks = novels.books.filter(book => book.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <dialog ref={ref} aria-labelledby="studio-create-title" onCancel={event => { if (busy || lock.current) event.preventDefault(); else onClose(); }} className={sourceDialogClass}>
    <h2 id="studio-create-title" className="mb-5 text-xl tracking-[.24em]">新建项目</h2>
    {error && <ErrorNotice message={error} />}
    <fieldset disabled={busy} className="min-w-0"><legend className="mb-2">作品来源</legend><div className="flex flex-wrap gap-2">{choices.map(choice => <button key={choice.id} type="button" aria-pressed={kind === choice.id} className={`chip min-h-10 ${kind === choice.id ? "chip-on" : ""}`} onClick={() => { setKind(choice.id); setError(""); }}>{choice.label}</button>)}</div></fieldset>
    {sourcesLoading && <LoadingState>正在读取作品来源…</LoadingState>}
    {sourceError && <ErrorNotice message={sourceError} retry={() => void loadSources()} />}
    {kind === "novel" && <div className="mt-4 min-w-0 space-y-3"><label className="block space-y-2"><span>按书名筛选</span><input value={query} disabled={busy} onChange={event => setQuery(event.target.value)} className={novelFieldClass} /></label>{filteredBooks.map(book => <NovelSourceChoice key={book.id} book={book} selected={book.id === bookId} disabled={busy} embedded={embedded} onSelect={() => { setBookId(book.id); setTitle(book.title.slice(0, 200)); }} />)}{!sourcesLoading && !filteredBooks.length && <EmptyState>没有找到符合书名的作品。只有已完结并通过检查的作品可以导入。</EmptyState>}</div>}
    {kind === "upload" && <div className="mt-4 min-w-0 space-y-2"><label className="block space-y-2"><span>选择文件（txt / md / docx，最多 10 MB）</span><input type="file" accept=".txt,.md,.docx" disabled={busy} className="block w-full min-w-0 text-sm" onChange={event => { const next = event.target.files?.[0] ?? null; setFile(next); if (next && !title.trim()) setTitle(next.name.replace(/\.[^.]+$/, "").slice(0, 200)); }} /></label>{file && <p className="break-all text-sm">{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB</p>}{invalidFile && <ErrorNotice message={invalidFile} />}</div>}
    {kind === "paste" && <label className="mt-4 block space-y-2"><span>粘贴作品正文</span><textarea id="studio-source-text" rows={8} value={text} disabled={busy} onChange={event => setText(event.target.value)} className={novelFieldClass} /><span className="readout block text-sm" role="status">{textLength.toLocaleString()} / 500,000 字</span>{textLength > 500000 && <span className="block text-sm text-[color:var(--seal)]">作品超过 50 万字，暂不支持</span>}</label>}
    {kind === "exchange" && <div className="mt-4 space-y-3">{exchanges.map(exchange => <button key={exchange.id} type="button" disabled={busy} aria-pressed={exchange.id === exchangeId} className={`ceramic-card block w-full min-w-0 break-words rounded-xl p-3 text-left ${exchange.id === exchangeId ? "ring-1 ring-[color:var(--ink)]" : ""}`} onClick={() => { setExchangeId(exchange.id); setTitle(exchange.title.slice(0, 200)); }}><span className="block">{exchange.title}</span><span className="readout mt-2 block text-sm">{exchange.chars.toLocaleString()} 字 · {formatStudioDate(exchange.completed_at)}</span></button>)}{!sourcesLoading && !exchanges.length && <EmptyState>还没有可导入的成稿。请先与「短视频创意搭档」完成一次交流。</EmptyState>}</div>}
    <label className="mt-4 block space-y-2"><span>项目标题</span><input id="studio-source-title" autoFocus maxLength={200} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} className={novelFieldClass} /></label>
    <SourceAspectPicker aspect={aspect} disabled={busy} onChange={setAspect} />
    <div className="flex flex-wrap gap-3"><button type="button" className="btn btn-primary min-h-10" disabled={busy || !canSubmit} onClick={() => void submit()}>{busy ? "正在建立快照…" : "创建项目"}</button><button type="button" className="btn btn-quiet min-h-10" disabled={busy} onClick={onClose}>取消</button></div>
  </dialog>;
}
