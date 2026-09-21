# 返修指令 2（用户验收后追加的两条）

只改 `frontend/app/page.tsx` 一个文件，其余一律不动，不得回滚已完成的工作。改完在 `frontend/` 目录跑判据、`npm run lint`、`npx tsc --noEmit`，把原始输出追加到 `docs/tasks/2026-09-12-frosted-instrument-ui-v2/03-report.md` 末尾「## 返修 2」一节。

## 1. 输入区 chips 行移进内框（对照原型 `.composer-box` → `.composer-row`）

现状：`data-chat-composer` 容器的第一个子元素是 `<div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px]">`（上传参考图 / 生成图片 / 比例 / 返回聊天 / 状态提示等 chips），位于 `var(--fill)` 内框**上方**；内框是单行 `flex items-end gap-2`（待发送图 + textarea + 右侧按钮组）。

改法（原型结构：内框里 textarea 在上，下面一行左 chips 右按钮）：
- 内框 `<div className="flex items-end gap-2 rounded-[10px] border px-3.5 py-2.5" style={{background:"var(--fill)", …}}>` 改为 `flex flex-col gap-2`。
- 第一行 `<div className="flex items-end gap-2">`：放待发送图 `{pendingImage && …}` 与 `<textarea …>`（原样）。
- 第二行 `<div className="flex flex-wrap items-center justify-between gap-2">`：
  - 左：把原来那个 chips `div` 整个移进来，去掉 `mb-1.5`，其余类与全部子元素、handler、disabled、title 原样（隐藏的 `<input type="file" multiple …>` 跟着一起搬）。
  - 右：原来的按钮组 `<div className="flex items-center gap-0.5 pb-0.5">`（图片附件 / 麦克风 / 按住说话 / 发送）原样，去掉 `pb-0.5`，加 `ml-auto shrink-0`。
- `referenceUploadError` 提示与参考图缩略条（`hasReferenceImages && <div className="mb-2 …">`）仍放在内框**上方**，不动。
- 底部提示行不动。

判据：
```bash
# chips 的第一个按钮必须出现在内框起始行之后、发送按钮之前
awk '/var\(--fill\)/{b=NR} /className=\{cn\("chip", hasReferenceImages/{c=NR} /aria-label=\{hasReferenceImages \? "修改图片"/{s=NR} END{print (b && c>b && c<s)?"chips inside box: ok":"chips inside box: WRONG b="b" c="c" s="s}' app/page.tsx   # 期望 ok
grep -c 'mb-1.5 flex flex-wrap items-center gap-2 text-\[11px\]' app/page.tsx   # 期望 0（改前 1）
```

## 2. 输入区高度实测，不再用固定 172px 底距

现状：滚动区外层 `<div className="absolute inset-0 flex flex-col pt-16 pb-[172px]">`，footer 高于 172px 时（出现参考图缩略条 `max-h-[144px]`、`referenceUploadError`、`voiceText`、多行输入）会盖住最后一条消息。

改法：
- 新增 `const composerRef = useRef<HTMLElement>(null);` 与 `const [composerHeight, setComposerHeight] = useState(172);`。
- `<footer …>` 加 `ref={composerRef}`。
- 新增 effect：`useEffect(() => { const el = composerRef.current; if (!el) return; const update = () => setComposerHeight(Math.ceil(el.getBoundingClientRect().height)); update(); const ro = new ResizeObserver(update); ro.observe(el); return () => ro.disconnect(); }, []);`
- 滚动区外层去掉 `pb-[172px]`，改 `style={{ paddingBottom: composerHeight }}`。
- 跟随：`components/ChatScrollArea.tsx` 第 73 行有 ResizeObserver 调 `scheduleFollow`。先确认它观察的是滚动容器本身还是内容：若观察容器（容器高度随 padding 变化而变化，会触发跟随），不必再做；若只观察内容，则再加一个 `useEffect(() => { chatScrollRef.current?.scrollToLatest(); }, [composerHeight])`——但只在用户原本处于底部时才应跟随，`ChatScrollArea` 若无此判断接口，就以 `ChatScrollArea.tsx` 内部的跟随语义为准，不要改 `ChatScrollArea.tsx`。在报告里写明你确认到的观察目标与最终选择。

判据：
```bash
grep -c 'pb-\[172px\]' app/page.tsx   # 期望 0（改前 1）
grep -c 'new ResizeObserver' app/page.tsx   # 期望 ≥ 1（改前 0）
grep -c 'paddingBottom: composerHeight' app/page.tsx   # 期望 1
grep -c 'ref={composerRef}' app/page.tsx   # 期望 1
```

## 通用判据
```bash
npm run lint      # 0 errors，warnings ≤ 28
npx tsc --noEmit  # 无输出
```
派单方会在隔离环境实测：选 2 张参考图后，最后一条消息底边必须在 footer 顶边之上。
