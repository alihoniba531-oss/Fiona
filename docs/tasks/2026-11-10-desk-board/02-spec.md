# 案头第一期 · 规格 v1.5

级别：L3（主聊天页结构性新增）。状态：作者已于 2026-11-10 确认 v1.0 并派单；v1.1 是首轮交付经门禁与界面走查后的修订（第 10 节）；v1.2 是 Opus 独立复核之后的修订（第 11 节）；v1.3 是 R2 交付经界面走查后的两处修订（第 12 节）；v1.4 是第二轮独立复核之后的修订（第 13 节）；v1.5 是第三轮独立复核之后的修订（第 14 节，只改一个测试文件）。**后面的节与前文不一致时以后面的节为准。**
基线：main `9adf34c`。执行分支：`feat/desk-board`（专用 worktree）。

本规格自包含。执行者看不到任何对话，规格没写的不要自行扩展。

---

## 1. 目标与场景

在主聊天页增加一块叫「案头」的面板，与对话并排。它显示作者的一本书（来自书斋）以及这本书的短片项目（来自短片工作室）进行到哪一步、有哪些条目、此刻在等作者确认什么，并且让作者不离开对话就能完成那些**本来就由作者亲手点**的操作。

四个要走通的场景：

1. 书停在「等你确认细纲」。作者打开案头，章回页最上面是关卡提示，点「查看并批准细纲」弹出细纲编辑器，原样批准、改完批准或附一句话重做。
2. 一批章节写完等审。作者在案头留一句话，再点继续。
3. 这本书已有短片项目且拆解完成。作者在分集页逐集看标题、变化、钩子、预估时长，修改某一集，把某一集与下一集合并，批准分集方案。
4. 分身在聊天里出了「书斋草稿」卡或「短片工作室」卡。案头自动打开并定位到那本书或那个项目。

**第一期只动前端。不改 `backend/` 下任何非测试文件，不新增接口，不新增 npm 或 pip 依赖，不改任何既有组件的源码（只 import 复用）。**

---

## 2. 现状事实

从 HEAD `9adf34c` 读代码得到。行号只帮你定位，以标识符和字面量为准。**你实测到的事实优先于本节的断言；发现不符就停下来说明，不要照着错的写。**

### 2.1 主聊天页 `frontend/app/page.tsx`

- 3018 行，文件开头有 UTF-8 BOM，**必须保留**。
- 根结构（约 2460 行起）：

  ```tsx
  <div className="chat-shell relative flex flex-col h-dvh overflow-clip">
    <InkLandscape variant="chat" />
    <Glaze variant="panel" fur className="chat-left-material …" />
    <div className="flex flex-1 min-h-0 relative">
      <Sidebar … />
      …历史抽屉、遮罩…
      <div className="flex flex-1 min-w-0 min-h-0">
        <ConversationPicker … className="relative z-[2] my-3 h-[calc(100%-24px)]! max-lg:hidden" />
        …窄屏对话列表弹层…
        <div className="relative z-[1] flex-1 min-w-0" data-chat-panel style={{ "--composer-height": `${composerHeight}px` } as React.CSSProperties}>
          <Glaze as="header" variant="strip" className="chat-header …"> …头部… </Glaze>
          …消息层、输入区…
        </div>
      </div>
    </div>
    …六个 fixed 抽屉：agent / exchange / plaza / settings / novel / studio…
  </div>
  ```

- 抽屉状态：`type DrawerName = "agent" | "exchange" | "plaza" | "settings" | "studio" | "novel" | null;`，`const [drawer, setDrawer] = useState<DrawerName>(null);`。抽屉是 `fixed top-3 bottom-3 right-3 z-[55]` 的 `Glaze`，桌面宽 `calc((100vw - var(--rail-w) - 12px) * 2 / 3)`，手机全屏并让出底部 `--tabbar-h`。
- 书斋抽屉内是 iframe，`src={novelFrameSrc}`；`const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")`。`openNovelAt(path)` 只接受两种形状，其余直接返回：
  - `/^\/novels\/new\?embed=1&draft=[0-9a-f-]{36}$/`
  - `/^\/novels\/[0-9a-f-]{36}\?embed=1$/`
- 工作室抽屉内是 iframe：`{studioAllowed ? <iframe key={username} ref={studioFrameRef} title="短片工作室工作区" src="/studio?embed=1" … />`。`const studioAllowed = studioAccess.owner === username && studioAccess.allowed;`。
- 设置抽屉的打开方式（书斋 iframe 发消息时就这么做）：`setSettingsTab("settings"); setDrawer("settings");`。
- 头部右侧的两个开关按钮「朗读」「免提」写法（约 2573–2607 行）：

  ```tsx
  <button type="button" className={cn("chip max-md:h-10 max-md:w-10 max-md:justify-center max-md:px-0", voiceOn && "chip-on")} onClick={…} aria-label="朗读" aria-pressed={voiceOn}>
    {voiceOn ? <Volume2 size={13} /> : <VolumeX size={13} />}<span className="max-md:hidden">朗读</span>
  </button>
  ```

- 输入框：`const [input, setInput] = useState("");`，`textareaRef`。已有一个把文字放进输入框并聚焦的函数：

  ```tsx
  const composeSongSection = useCallback((text: string) => {
    setInput(text);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, []);
  ```

- 流式回复里卡片的处理（约 2151–2180 行）有两个分支：`if (data.card && data.append === true) {…}` 与 `if (data.card && data.append !== true) {…}`，都从 `data.card` 取 `source / points / url / error / subtype / project_id / draft_id / …`。
- 其他可用状态：`hydrated`、`username`、`composerHeight`。

### 2.2 被基线测试锁住的字面量（一个字符都不能变）

以下字符串必须原样留在 `frontend/app/page.tsx` 里：

```
const openNovelAt = (path: string) => {
onOpenNovel={openNovelAt}
const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")
src={novelFrameSrc}
studioAllowed ? <iframe
key={username}
src="/studio?embed=1"
```

锁它们的测试在 `backend/tests/test_novel_chat_create_frontend.py`、`test_novel_p2_frontend.py`、`test_studio_frontend_navigation.py`、`test_ui_polish_page_contracts.py`。还有很多别的测试读 page.tsx，所以接线只许在第 5 节 T3 列出的位置动手。

### 2.3 书斋数据与函数（`frontend/lib/novels.ts`，只 import，不改）

类型：`NovelSummary`、`NovelDetail`、`NovelChapterSummary`、`NovelChapter`、`NovelBeatSheet`、`NovelCompass`、`NovelDraft`、`NovelAction`。

- `NovelDetail` 在 `NovelSummary` 之上有 `config`（含 `batch_size`、`adaptation.max_scenes_per_chapter`）、`compass`、`bible`、`chapters: NovelChapterSummary[]`、`pending_gate`、`pending_notes`、`last_error`。
- `NovelChapterSummary = { chapter, title, status, words, flags, edited_by_user }`。`status` 的全部取值：`planning`、`awaiting_plan_approval`、`writing`、`done`、`stale`、`failed`。
- 书的 `status`：`setup_running | awaiting_setup | running | awaiting_review | awaiting_plan | awaiting_end | completed | paused | failed`。
- 单章 `NovelChapter` 有 `body`（正文，可能为 null）与 `meeting`；待批细纲在 `chapter.meeting.decision.beat_sheet`。
- 章节摘要在 `book.bible?.dynamic.chapter_summaries`（`{ chapter, title, summary }[]`）。详情里的圣经经过裁剪，**旧章的摘要可能没有**，没有就不显示。

函数：`listNovels`、`getNovel`、`getNovelChapter`、`getNovelDraft`、`addNovelNote`、`exportNovel`、`novelApi.action(id, path, body?, { signal })`、`novelStatusLabel`、`novelErrorMessage`、`displayNovelChapterTitle`。

后端语义（只需知道，不要改）：

- 批准细纲 `plan/approve`：可带改过的 `beat_sheet`；批准后立即开始写这一章，按这本书已定的预算扣草莓。
- 重做细纲 `plan/redo`：必须带一句话，**会再次扣草莓**。
- 留言 `POST /novels/{id}/notes`：免费；待处理留言最多 5 条，超了返回 409，`detail` 是「待处理留言最多五条」。
- 账号没开通书斋时 `/novels` 返回 403，书斋总开关关着时返回 404；`novelErrorMessage` 已把这两种情况转成中文。

### 2.4 工作室数据与函数（`frontend/lib/studio.ts`、`frontend/lib/studio-breakdown.ts`，只 import，不改）

- `listStudioNovelSources()` 返回 `{ enabled, books: StudioNovelCandidate[] }`；`StudioNovelCandidate = { id, title, status, chapters_done, words_done, …, eligible, reason, flagged, projects: { id, title, snapshot_no, created_at }[] }`。用它从「书」找到「这本书的短片项目」。
- `getStudioEpisodes(projectId)` 返回 `StudioEpisodePlan`：

  ```ts
  { episodes: StudioEpisode[]; units; unassigned; uncovered?;
    plan_revision: number; plan_approved_revision: number | null; g0_approved: boolean; total_seconds: number;
    status?; active_breakdown_status?; rebreakdown_pending?; settings? }
  // StudioEpisode = { id, no, title, unit_from, unit_to, change, hook, notes, target_min, target_max,
  //                   est_seconds, est_shots, source_range, characters, warnings }
  ```

- `operateStudioEpisodes(projectId, op)`：`op` 必须带 `expected_revision: plan.plan_revision`。版本不一致返回 409。`{ op: "edit", no, fields }` 改标题、变化、钩子、备注、目标时长；`{ op: "merge", no }` 是**与下一集合并**（最后一集不能合并，后端返回 422「没有下一集可合并」）。返回新的 `StudioEpisodePlan`。
- `approveStudioEpisodes(projectId, plan.plan_revision)` 批准方案，免费。
- `formatEpisodeDuration(seconds)` 把秒格式化成「1 分 30 秒」。
- 不在工作室白名单时，所有 `/studio/*` 一律 404。
- 工作室分集表 `frontend/components/studio/EpisodePlan.tsx` 里的禁改与禁批条件，案头照抄：

  ```ts
  const activeStatus = plan.active_breakdown_status ?? plan.status;
  const regenerating = activeStatus === "running" || activeStatus === "partial";
  const editsBlocked = regenerating || !!plan.rebreakdown_pending;
  const approvalBlocked = editsBlocked || plan.status !== undefined && plan.status !== "done";
  ```

- **逐集分镜没有实现**：工作台的「③分镜」「⑤成片」显示「这一阶段将在后续版本开放」，没有镜头数据。案头的这两页在第一期一律置灰。

### 2.5 可以直接 import 复用的既有组件（不改它们的源码）

| 组件 | 文件 | 用途与签名要点 |
|---|---|---|
| `GateBanner` | `components/novel/GateBanner.tsx` | 书的当前关卡。props：`book, busy, onAction(action, body?), onNotes(), onSettings(resumeAfter?), onView(), onExport(), onOpenSettings(), onMakeFilm?`。书在 `running / setup_running` 时返回 null。不传 `onMakeFilm` 就不显示「做成片」按钮。 |
| `PlanEditor` | `components/novel/PlanEditor.tsx` | 细纲编辑器。props：`beatSheet, chapter, maxScenes, busy, onApprove(beat?), onRedo(text)`。自带「批准（原样）」「改完批准」「附一句话重新定稿」和「重新定稿会再次扣除草莓」提示。 |
| `ErrorNotice`、`EmptyState`、`LoadingState` | `components/novel/NovelStates.tsx` | 出错（可带重试）、空、加载三种状态。 |
| `EpisodeEditDialog` | `components/studio/EpisodePlan.tsx`（具名导出） | 单集修改对话框。props：`episode, busy, onSave(fields), onClose()`。 |
| `BreakdownDialog` | `components/studio/BreakdownDialog.tsx` | 确认对话框。props：`title, children, confirmLabel, busy, disabled, onConfirm, onClose`。 |
| `sourceDialogClass` | `components/studio/SourceChoices.tsx` | 对话框统一类名字符串。 |
| `Glaze` | `components/Glaze.tsx` | 釉面容器。props：`as, variant: "panel" | "strip" | "slab", lens, backdrop, fur`。 |
| `useAccountRequest(owner)` | `lib/useAccountIdentity.ts` | 返回 `{ beginRequest, isCurrentOwner }`；`beginRequest()` 返回 `{ signal, isCurrent() }` 或 null。换账号时自动取消。**案头的所有请求都必须经它发起，回来后先判 `isCurrent()` 再写状态。** |

书斋工作台的链式轮询写法见 `components/novel/NovelWorkbench.tsx`（搜 `setTimeout(poll, 3000)`）：页面可见且书处于运行态时每 3 秒一轮，一轮结束才排下一轮，页面隐藏时停。

### 2.6 设计门禁（新代码必须通过，测试已存在）

- `backend/tests/test_design_system_gate.py`：字号只能用 `text-fs-11 / 12 / 13 / 15 / 16.5 / 18 / 22 / 30 / 46 / 76` 令牌，不许 `text-[13px]` 这类写法；颜色工具类必须写成 `text-[color:var(--ink2)]`、`border-[color:var(--rule)]`、`bg-[color:var(--hi)]` 这种形式；`--ink3` 与 `--dim` 不许当文字色；`var(--stamp)` 不许出现在印章组件之外；文字色不许带透明度后缀。
- `backend/tests/test_ui_closeout_dialog_scrim.py`：每个 `<dialog>` 必须带 `scrim-dialog` 且只有一个 `className`；`globals.css` 里 `::backdrop` 恰好两条，不许再加；不许用 `backdrop:` 工具类。这份测试还写死了全仓 JSX `<dialog` 标签的总数：`def assert_dialogs_have_scrim(sources, *, expected_count=13):`。案头新增一个 `<dialog`，所以 v1.1 授权把这个 13 改成 14（见第 6 节），**不许用 `React.createElement("dialog")` 之类的写法躲开扫描**。
- 跨任务约定：**界面文字不加粗**。新代码里不得出现 `font-medium`、`font-semibold`、`font-bold`、`font-extrabold`、`font-black`，也不得出现大于 400 的 `font-weight` / `fontWeight`。层次只靠字号与灰度。

### 2.7 基线数字（2026-11-10 从 HEAD 实测）

| 命令 | 结果 |
|---|---|
| `cd backend && python -m pytest -q` | `7911 passed`，0 failed，0 skipped |
| `cd frontend && npx tsc --noEmit` | 退出 0 |
| `cd frontend && npm run lint` | `0 errors, 25 warnings` |
| `cd frontend && npm run build` | 退出 0 |

---

## 3. 范围

### 3.1 做

- A. 案头外壳：开关、三种呈现方式（并排、右侧抽屉、手机半屏）、书目切换、按账号记住上次状态。
- B. 阶段标签：立意、章回、分集可用；分镜、成片置灰。
- C. 立意页（只读）。
- D. 章回页：章节行、当前关卡、细纲对话框、读正文对话框、留言。
- E. 分集页：分集行、修改某一集、与下一集合并、批准方案。
- F. 聊天联动：流式回复里出现书斋草稿卡或工作室卡时打开并定位；每行「问分身」。
- G. 空、加载、无权限、出错、版本冲突五类状态。
- H. 新测试与文档同步。

### 3.2 不做（出现在参考稿里也不做）

- `backend/` 下任何非测试文件的改动；任何新接口、新表、新环境变量、新依赖。
- 分镜页、成片页的内容（`design/Director.dc.html` 整张不做）。
- 分身改稿、改动回执、「改 14:03」印、撤销、输入框引用条（参考稿聊天区里的这些元素都不做）。
- 在案头里报价、确认拆解、重试拆解批次（参考稿底栏的「确认拆解」不做，这些仍在工作室做）。
- 改章节正文、改人物设定、立项关卡的编辑、卷关卡。
- 分集的拆分、挪边界、删除、插入。
- 行内直接改字与自动保存（第一期用既有对话框）。
- 手机半屏的拖拽调高（用按钮切两档）。
- 修改 `components/novel/**`、`components/studio/**`、`components/ChatBubble.tsx`、`components/NovelDraftCard.tsx`、`components/Sidebar.tsx`、`components/ConversationPicker.tsx`、`lib/novels.ts`、`lib/studio*.ts` 以及任何既有测试。

---

## 4. 设计规范

### 4.1 参考稿

`docs/tasks/2026-11-10-desk-board/design/` 下六个 `.dc.html` 是静态 HTML，内联样式就是尺寸与层次的依据。它们引用的 `./support.js` 不存在，不需要运行，直接读源码。

| 文件 | 第一期用法 |
|---|---|
| `Chapters.dc.html` | 章回页的版式依据。聊天区里的回执条、「改」印不做。 |
| `Main.dc.html` | 分集页与并排布局的版式依据。行内编辑框、底栏报价、聊天区回执与引用条不做。 |
| `Mobile.dc.html` | 手机半屏的版式依据。 |
| `States.dc.html` | 只用前三格：空着的案头、取回中、出错。 |
| `Night.dc.html` | 仅说明夜色下的观感。全部用 CSS 变量即可自动得到，不单独实现。 |
| `Director.dc.html` | 不做。 |

参考稿与实现有三处**有意的差别**，以本规格为准：

1. 参考稿用方形小印表示状态；实现用现有 `.tag` 文字标签。只有「定稿」「已批准」两种标签用朱色，写法 `tag text-[color:var(--seal)] border-[color:var(--seal)]`，其余标签不加颜色类。
2. 参考稿行首用「一二三」；实现用阿拉伯数字，写法 `readout text-fs-18`。
3. 参考稿里凡是 `#6F7C76` 的文字，实现一律用 `--ink2`（门禁不许 `--ink3` 当文字色）。

### 4.2 三种呈现方式

由视口宽度决定，用 `deskMode(window.innerWidth)` 计算，监听 `resize`。挂载前（服务端渲染与水合首帧）什么都不渲染。案头关闭时不渲染面板内容，也不发任何请求。

| 方式 | 条件 | 位置与尺寸 |
|---|---|---|
| 并排 `dock` | 宽 ≥ 1440 | `<aside>` 是 `div.flex.flex-1.min-w-0.min-h-0` 的最后一个子元素，在文档流里，`flex: none`，总宽 488px（面板 448 + 书耳 28 + 右侧留白 12），上、下各留 12px。聊天列自然变窄。没有遮罩。 |
| 抽屉 `drawer` | 768 ≤ 宽 < 1440 | `fixed top-3 bottom-3 right-3`，总宽 **476px**（面板 448 + 书耳 28），书耳右缘离视口右缘 12px，与现有抽屉对齐；`z-[50]`（六个大抽屉是 55，要在它们下面）。盖住聊天右侧，没有遮罩，投影与现有抽屉相同：`-12px 0 32px var(--drop)`。 |
| 半屏 `sheet` | 宽 < 768 | `fixed left-0 right-0`，底边在输入区上方：`bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom) + <composerHeight>px)`；高度两档，默认是 `min(45dvh, calc(100dvh - 94px - env(safe-area-inset-top) - var(--tabbar-h) - env(safe-area-inset-bottom) - <composerHeight>px))`（45dvh，但不超过头部与输入区之间的可用高度），展开后顶边到 `calc(94px + env(safe-area-inset-top))`；`z-[50]`；左上右上圆角 14px；阶段标签改成横排。用一个按钮在两档之间切换，文字是「展开」与「收起一半」。 |

- 面板容器照现有抽屉的写法：`<Glaze as="aside" variant="panel" lens={false} backdrop={false} className="drawer-panel …">`，`id="desk-panel"`，`aria-label="案头"`，`tabIndex={-1}`。
- **抽屉与半屏方式下面板必须不透明**（它盖在聊天上面，釉面本身是半透明的，聊天文字会透上来和案头文字叠在一起）：这两种方式下给 `<aside>` 加 `bg-[color:var(--paper)]`。并排方式不加这个类。
- 抽屉与半屏方式下，开合的位移动画照 page.tsx 里的 `drawerStyle`（360ms），`prefers-reduced-motion: reduce` 时不做位移。除此之外不加任何动效。
- 抽屉与半屏方式下按 Esc 收起：条件与书斋抽屉一致，直接复用 `components/novel/NovelShell.tsx` 导出的 `canCloseNovelDrawer(event, focused, dialogOpen)`，并且焦点必须在案头内。并排方式下 Esc 不收起。
- 只有作者亲手点开（打开那一刻焦点在头部开关上）才把焦点移到面板；流式卡片触发的自动打开、刷新页面后的恢复打开都**不移动焦点**。收起后把焦点还给头部那个 `aria-controls="desk-panel"` 的按钮。（v1.2）

### 4.3 样式规则

- 颜色只用现有 CSS 变量，不写十六进制、`rgb()`、`rgba()`，不新增变量。对照表：

  | 参考稿 | 变量 |
  |---|---|
  | `#E8EEEA` | `--paper` |
  | `#F4F7F4` | `--hi` |
  | `#D5E0DA` | `--slip` |
  | `#93AFA4` | `--deep` |
  | `#1F2926` | `--ink` |
  | `#56635E`、`#6F7C76` | `--ink2` |
  | `rgba(31,41,38,0.12)` | `--rule` |
  | `rgba(31,41,38,0.26)` | `--rule2` |
  | `#A8322A` | `--seal` |

- 字号对照：22px → `text-fs-22`，18px → `text-fs-18`，16.5px → `text-fs-16.5`，15px → `text-fs-15`，13px → `text-fs-13`，12px → `text-fs-12`，11px → `text-fs-11`。
- 按钮用现有类：主按钮 `btn btn-primary`，次按钮 `btn`，文字按钮 `btn btn-quiet`，开关 `chip` / `chip-on`，状态 `tag`。数字用 `readout`。
- 行是账簿式的：网格 `grid-cols-[36px_minmax(0,1fr)_auto]`，行与行之间一条 1px 的 `--rule` 线。**面板内部不用卡片堆叠**（不给每一行套 `ceramic-card`）。
- 阶段标签（并排与抽屉方式）：面板右外侧一列竖排按钮，文字竖排（`[writing-mode:vertical-rl]`），每个宽 28px、高 92px，右侧圆角 6px，1px `--rule` 边。当前项：背景 `--hi`、文字 `--ink`、左边 2px `--seal`。其余项文字 `--ink2`。置灰项加 `disabled` 与 `title="后续开放"`。语义是 `role="tablist"` / `role="tab"` / `aria-selected`，方向键切换用 `lib/useRovingTabs.ts` 的 `useRovingTabs`。
- 文字不加粗（见 2.6）。
- 手机上可点区域不小于 40px。

### 4.4 固定文案

界面文字以本表为准，不要自拟近义词。

| 位置 | 文案 |
|---|---|
| 头部开关（`aria-label` 与可见文字） | 案头 |
| 面板小标题 | 案头 |
| 收起按钮 `aria-label` | 收起案头 |
| 刷新按钮 | 刷新 |
| 书目下拉 `aria-label` | 作品 |
| 去书斋 / 去工作室 | 在书斋打开 / 在工作室打开 |
| 阶段 | 立意、章回、分集、分镜、成片 |
| 置灰阶段的 `title` | 后续开放 |
| 半屏高度切换 | 展开 / 收起一半 |
| 取回中 | 正在取回作品… |
| 没有任何书 | 案头空着。对分身说想写什么，或者到书斋新建一本。 按钮：去书斋 |
| 草稿还没建书 | 草稿《{书名}》还没建书。 按钮：去书斋建书 |
| 章节标签 | 定稿、待复核、细纲等你确认、定细纲中、写作中、出错了、处理中 |
| 章名缺失 | 待定章名 |
| 章节行按钮 | 读正文、问分身 |
| 正文为空 | 这一章还没有正文。 |
| 细纲缺失 | 细纲还没准备好，请稍后刷新。 |
| 留言标签 / 占位 / 按钮 | 给编辑部留一句话 / 下一章定稿时会看到 / 留言 |
| 留言成功 | 已留言。 |
| 留言计数 | 待处理留言 {n} / 5 |
| 留言已满 | 待处理留言已满 5 条，等编辑部处理后再留。 |
| 工作室未开放 | 短片工作室暂未对该账号开放。 |
| 没有短片项目（可做成片） | 这本书还没有短片项目。对分身说「把《{书名}》做成片」，或在书斋里点「做成片」。 |
| 没有短片项目（暂不可做） | 这本书还没有短片项目。{后端给的 reason} |
| 多个项目下拉 `aria-label` | 短片项目 |
| 没有分集方案 | 还没有分集方案，拆解在工作室里做。 |
| 方案汇总 | 方案第 {n} 版　共 {m} 集　约 {时长} |
| 方案状态标签 | 已批准、待批准 |
| 分集行内 | 变化：{…}　钩子：{…}　空值显示 — |
| 分集行按钮 | 修改、与下一集合并、问分身 |
| 集有警告的标签 | 有提示 |
| 合并确认 | 标题：与下一集合并。正文：把第 {n} 集和第 {n+1} 集合成一集，标题、变化、钩子会拼在一起。 确认按钮：确认合并 |
| 批准按钮与确认 | 批准分集方案。标题：批准分集方案。正文：即将批准方案第 {n} 版。批准后再改会生成新版本、需要重新批准。 确认按钮：确认批准 |
| 版本冲突 | 分集方案已在别处改动，已为你刷新，请再试一次。 |
| 拆解未完成 | 拆解还没全部完成，暂时不能修改或批准，去工作室看进度。 |
| 未纳入的原文 | 还有 {n} 段原文没有纳入分集，在工作室处理。 |
| 「问分身」放进输入框的引子 | 关于《{书名}》第 {n} 章： / 关于《{书名}》第 {n} 集： |

---

## 5. 任务清单

### T1 新文件 `frontend/lib/desk.ts`（纯函数，供界面与测试共用）

不 import React，不在模块顶层访问 `window` / `document` / `localStorage`。导出清单与签名**固定如下**（其他任务按它并行开发）：

```ts
import type { NovelChapterSummary } from "@/lib/novels";

export type DeskStage = "idea" | "chapters" | "episodes" | "shots" | "film";
export type DeskMode = "dock" | "drawer" | "sheet";
export type DeskSubject = { kind: "draft"; draftId: string } | { kind: "project"; projectId: string };
export interface DeskPrefs { open: boolean; novelId: string | null; stage: DeskStage }

export const DESK_STAGES: readonly { id: DeskStage; label: string; enabled: boolean }[];
export const DESK_DEFAULT_PREFS: DeskPrefs;

export function deskMode(width: number): DeskMode;
export function deskSubjectFromCard(card: unknown): DeskSubject | null;
export function deskAskPrefix(target: { title: string | null; chapter?: number; episode?: number }): string;
export function deskPrefsKey(username: string): string;
export function parseDeskPrefs(raw: string | null): DeskPrefs;
export function readDeskPrefs(storage: Pick<Storage, "getItem"> | null | undefined, username: string): DeskPrefs;
export function updateDeskPrefs(storage: Pick<Storage, "getItem" | "setItem"> | null | undefined, username: string, patch: Partial<DeskPrefs>): DeskPrefs;
export function chapterTag(chapter: Pick<NovelChapterSummary, "chapter" | "status">, chaptersDone: number): { label: string; settled: boolean };
export function currentChapterNumber(book: { chapters_done: number; chapters: Pick<NovelChapterSummary, "chapter" | "status">[] }): number | null;
export function episodeLocks(plan: { status?: string; active_breakdown_status?: string | null; rebreakdown_pending?: boolean }): { editsBlocked: boolean; approvalBlocked: boolean };
export function latestProject<T extends { id: string; created_at: string }>(projects: readonly T[]): T | null;
```

逐个的行为：

- `DESK_STAGES`：按顺序 `idea 立意 true`、`chapters 章回 true`、`episodes 分集 true`、`shots 分镜 false`、`film 成片 false`。
- `DESK_DEFAULT_PREFS`：`{ open: false, novelId: null, stage: "chapters" }`。
- `deskMode(width)`：`width >= 1440` → `"dock"`；`768 <= width < 1440` → `"drawer"`；其余（含 `NaN`、负数）→ `"sheet"`。
- `deskSubjectFromCard(card)`：只认两种卡片，别的一律 `null`。
  - `card.subtype === "novel_draft"` 且 `card.draft_id` 是匹配 `/^[0-9a-f-]{36}$/` 的字符串 → `{ kind: "draft", draftId }`。
  - `card.subtype === "studio_project"`、`card.error` 为假、`card.url` 是字符串且整串匹配 `/^\/studio\/([A-Za-z0-9_-]{1,64})$/` → `{ kind: "project", projectId: 捕获组 }`。
  - 入参不是对象、是 `null`、字段类型不对，都返回 `null`，不抛异常。
- `deskAskPrefix`：书名取 `title` 去掉首尾空白，空就用「这本书」，否则用「《书名》」。有 `chapter` → `关于《书名》第 3 章：`；有 `episode` → `关于《书名》第 2 集：`；都没有 → `关于《书名》：`。无书名时形如 `关于这本书第 3 章：`。
- `deskPrefsKey(username)`：`"fiona.desk.v1:" + username`。
- `parseDeskPrefs(raw)`：`raw` 为 `null`、不是合法 JSON、不是普通对象时返回默认值的副本。逐字段校验：`open` 只有严格等于 `true` 才是 `true`；`novelId` 必须是匹配 `/^[0-9a-f-]{36}$/` 的字符串，否则 `null`；`stage` 必须是 `DESK_STAGES` 里 `enabled` 为真的 id，否则 `"chapters"`。
- `readDeskPrefs(storage, username)`：`storage` 为空、`username` 为空串或 `getItem` 抛异常时返回默认值；否则 `parseDeskPrefs(storage.getItem(deskPrefsKey(username)))`。
- `updateDeskPrefs(storage, username, patch)`：读出当前值，合并 `patch`，把合并结果再过一遍 `parseDeskPrefs` 的校验，写回并返回。`setItem` 抛异常时吞掉异常，仍返回合并后的值。`username` 为空串时不写。
- `chapterTag(chapter, chaptersDone)`：

  | 条件（按顺序判） | `label` | `settled` |
  |---|---|---|
  | `status === "stale"` | 待复核 | false |
  | `status === "awaiting_plan_approval"` | 细纲等你确认 | false |
  | `status === "planning"` | 定细纲中 | false |
  | `status === "writing"` | 写作中 | false |
  | `status === "failed"` | 出错了 | false |
  | `status === "done"` 且 `chapter <= chaptersDone` | 定稿 | true |
  | 其他 | 处理中 | false |

- `currentChapterNumber(book)`：返回第一条 `status` 不是 `done` 也不是 `stale` 的章号；没有这样的章时返回最后一章的章号；`chapters` 为空返回 `null`。
- `episodeLocks(plan)`：照 2.4 的四行逻辑，返回 `{ editsBlocked, approvalBlocked }`。
- `latestProject(projects)`：返回 `created_at` 字符串最大的那一个；并列取数组里靠前的；空数组返回 `null`。

### T2 新目录 `frontend/components/desk/`

文件与职责如下。**视图组件必须是纯展示**：数据与回调都从 props 进来，自己不发请求、不读 `localStorage`、不用 `useAccountRequest`，这样才能在测试里做服务端渲染。只有 `DeskDock.tsx` 负责取数、轮询、记忆与对话框开合。

| 文件 | 职责 |
|---|---|
| `DeskDock.tsx`（默认导出，`"use client"`） | 容器：算呈现方式、取书目与详情、轮询、解析聊天传来的定位、记忆、Esc 与焦点、把数据交给视图。 |
| `DeskFrame.tsx` | 面板骨架：小标题行（「案头」、刷新、去书斋 / 去工作室、收起）、书名与副标题、书目下拉、阶段标签、内容插槽。三种呈现方式的外观差异在这里处理。 |
| `DeskIdeaView.tsx` | 立意页。 |
| `DeskChaptersView.tsx` | 章回页（关卡、行、留言）。 |
| `DeskEpisodesView.tsx` | 分集页（汇总、行、批准）。 |
| `DeskDialogs.tsx` | 细纲对话框与读正文对话框。 |

`DeskDock` 的 props（page.tsx 按它传）：

```ts
{
  owner: string;                       // 当前账号名；空串时什么都不渲染
  open: boolean;
  onOpenChange: (open: boolean) => void;
  studioAllowed: boolean;
  composerHeight: number;
  focus: { subject: DeskSubject; nonce: number } | null;
  onAsk: (prefix: string) => void;
  onOpenNovel: (path: string) => void;          // 传 page.tsx 的 openNovelAt
  onOpenNovelShelf: () => void;                 // 打开书斋抽屉（书架）
  onOpenStudio: (projectId: string | null) => void;
  onOpenSettings: () => void;
}
```

容器行为：

1. `open` 为假或 `owner` 为空：返回 `null`，不发请求，不挂定时器。
2. `open` 变真时：`listNovels()` 取书目。403 / 404 用 `novelErrorMessage` 的文案显示无权限状态，不再发后续请求。书目为空显示「案头空着」状态，「去书斋」按钮调用 `onOpenNovelShelf()`（`onOpenNovel` 只接受带 id 的路径，打不开书架）。
3. 选哪本书：先看记忆里的 `novelId` 是否还在书目里；不在就选 `updated_at` 最新的一本。选定后 `getNovel(id)` 取详情，并把 `novelId` 写进记忆。
4. 轮询：书的 `status` 是 `running` 或 `setup_running`，且页面可见、案头开着时，每 3 秒链式取一次详情（一轮结束才排下一轮）。其余状态不轮询。页面从隐藏变可见、点「刷新」、任何一次写操作成功后，各取一次。
5. 所有请求经 `useAccountRequest(owner)`；回来后 `isCurrent()` 为假就丢弃。读请求与写请求各用一个 `useAccountRequest`，避免轮询把写请求取消掉（`components/studio/BrainTrial.tsx` 就是 `beginRead` 与 `beginMutation` 两个）。
6. `focus` 的 `nonce` 变化时解析定位：
   - `draft`：`getNovelDraft(draftId)`。有 `novel_id` → 选中那本书，阶段切到章回。没有 → 在内容区显示「草稿《{书名}》还没建书。」和按钮「去书斋建书」，按钮调用 `onOpenNovel("/novels/new?embed=1&draft=" + draftId)`。取草稿失败就忽略这次定位。
   - `project`：`studioAllowed` 为假就忽略。否则 `listStudioNovelSources()`，找到 `projects` 里含这个 `projectId` 的书 → 选中那本书、阶段切到分集、项目选它。找不到就忽略这次定位。
7. 阶段切换写进记忆。置灰的阶段点不动。

### T3 `frontend/app/page.tsx` 接线

**只许做下面七处改动，其余一行不动。BOM 保留，2.2 的字面量保留。**

1. import：新增 `DeskDock` 与 `@/lib/desk` 里要用的导出；在现有 `lucide-react` 的 import 里加一个图标名（建议 `ScrollText`）。
2. 状态（放在 `drawer` 状态附近）：

   ```tsx
   const [deskOpen, setDeskOpen] = useState(false);
   const [deskFocus, setDeskFocus] = useState<{ subject: DeskSubject; nonce: number } | null>(null);
   ```

3. 恢复与保存开关状态：`hydrated && username` 成立后读一次 `readDeskPrefs(window.localStorage, username).open` 放进 `deskOpen`；之后每次开关用 `updateDeskPrefs(window.localStorage, username, { open })` 保存。换账号时按新账号重新读。访问 `localStorage` 要包在 try/catch 或经 `lib/desk.ts` 的函数（它们已吞异常）。
4. 在 `openNovelAt` 之后新增（不要改 `openNovelAt` 本身）：

   ```tsx
   const openStudioAt = (projectId: string | null) => {
     if (!studioAllowed) return;
     setDrawer("studio");
     if (projectId && /^[A-Za-z0-9_-]{1,64}$/.test(projectId)) {
       studioFrameRef.current?.contentWindow?.location.replace(`/studio/${projectId}?embed=1`);
     }
   };
   ```

   工作室 iframe 的 `src="/studio?embed=1"` 字面量不许动，所以用同源 iframe 的 `location.replace` 跳转。
5. 「问分身」回调（放在 `composeSongSection` 附近）：

   ```tsx
   const askFromDesk = useCallback((prefix: string) => {
     setInput(current => current.trim() ? `${prefix}${current}` : prefix);
     requestAnimationFrame(() => textareaRef.current?.focus());
   }, []);
   ```

6. 头部开关：紧挨着「朗读」按钮**之前**插入一个按钮，写法与「朗读」同构：

   ```tsx
   <button type="button" className={cn("chip max-md:h-10 max-md:w-10 max-md:justify-center max-md:px-0", deskOpen && "chip-on")}
     onClick={…切换并保存…} aria-label="案头" aria-pressed={deskOpen} aria-controls="desk-panel">
     <ScrollText size={13} className="md:hidden" /><span className="max-md:hidden">案头</span>
   </button>
   ```

7. 两处与案头相连的地方：
   - 流式回复：在 `if (data.card && data.append === true) {` 这一行**之前**加一段，卡片能解析出定位就记下来，并且只在非手机宽度时自动打开：

     ```tsx
     if (data.card) {
       const subject = deskSubjectFromCard(data.card);
       if (subject) {
         setDeskFocus({ subject, nonce: Date.now() });
         if (deskAutoOpens(window.innerWidth)) { …打开并保存… }   // v1.2：判定挪进 lib/desk.ts
       }
     }
     ```

     只在这一处触发。历史消息里的卡片、刷新后重建的卡片都不触发。
   - 挂载：在 `<div className="flex flex-1 min-w-0 min-h-0">` 里、`data-chat-panel` 那个 div 的闭合标签**之后**，作为这个 flex 容器的最后一个子元素：

     ```tsx
     <DeskDock owner={username} open={deskOpen} onOpenChange={…} studioAllowed={studioAllowed} composerHeight={composerHeight}
       focus={deskFocus} onAsk={askFromDesk} onOpenNovel={openNovelAt} onOpenNovelShelf={() => setDrawer("novel")} onOpenStudio={openStudioAt}
       onOpenSettings={() => { setSettingsTab("settings"); setDrawer("settings"); }} />
     ```

`frontend/app/globals.css` 原则上不动。确实需要时只许**新增**以 `.desk-` 开头的类，不许新增颜色变量、不许新增 `::backdrop`、不许改现有规则。

### T4 立意页 `DeskIdeaView`

只读。数据来自 `book.compass`（可能为 null）。依次显示，缺哪项就不显示哪项：一句话故事 `logline`、主题 `theme`、核心冲突 `core_conflict`、主角（`protagonist.name`，想要 `want`，需要 `need`）、主线（`main_threads` 逐条 `name`：`description`）。每项是「小标签（`text-fs-12`、`--ink2`）+ 正文（`text-fs-15`）」。`compass` 为 null 时显示 `EmptyState`：「立意还没定下来。」。底部一个文字按钮「在书斋打开」，调用 `onOpenNovel("/novels/" + book.id + "?embed=1")`。

### T5 章回页 `DeskChaptersView` 与 `DeskDialogs`

自上而下三块，中间那块滚动：

1. **关卡**：直接渲染 `<GateBanner book={book} busy={busy} … />`，不传 `onMakeFilm`。回调：
   - `onAction(action, body)`：`novelApi.action(book.id, action, body, { signal })`，成功后刷新详情；失败时把 `novelErrorMessage(error)` 显示在关卡下方的 `ErrorNotice` 里，并把错误继续抛出。
   - `onNotes()`：把焦点放到留言输入框。
   - `onSettings()`、以及 `onView()` 在书的 `status` 不是 `awaiting_plan` 时：调用 `onOpenNovel("/novels/" + book.id + "?embed=1")`。
   - `onView()` 在 `status === "awaiting_plan"` 时：打开细纲对话框。
   - `onExport()`：`exportNovel(book.id)` 得到 Blob，用临时 `<a download>` 存成 `{书名或「小说」}.md`，1 秒后 `URL.revokeObjectURL`。
   - `onOpenSettings()`：调用容器的 `onOpenSettings`。
2. **章节行**：`book.chapters` 按章号升序。每行：
   - 左：章号，`readout text-fs-18`，颜色 `--ink2`，`aria-hidden`。
   - 中：章名 `displayNovelChapterTitle(title) || "待定章名"`（`text-fs-15`）；下面一行摘要（`text-fs-13`、`--ink2`、最多两行），取自 `book.bible?.dynamic.chapter_summaries` 里同章号的 `summary`，没有就不显示这一行。
   - 右：字数 `{words} 字`（`words > 0` 才显示，`readout`）；`chapterTag` 给出的标签，`settled` 为真时加朱色两类。
   - 整行的章名区是一个按钮，`aria-expanded`，点一下展开、再点收起，同一时刻只展开一行。组件接受可选 prop `initialExpanded?: number | null`（默认 null）作为展开状态的初值，供服务端渲染测试用。展开后在行内显示两个文字按钮：「读正文」（仅 `chapter.chapter <= book.chapters_done` 时显示）与「问分身」（调用 `onAsk(deskAskPrefix({ title: book.title, chapter }))`）。
   - 首次载入某本书时，把 `currentChapterNumber(book)` 那一行滚到可见处（`scrollIntoView({ block: "nearest" })`）。没有章节时显示 `EmptyState`：「第一章写好后会出现在这里。」。
3. **留言**（书的 `status === "completed"` 时整块不显示）：一个带可见 `<label>` 的单行输入框（`maxLength={500}`）与「留言」按钮。下方显示 `待处理留言 {book.pending_notes} / 5`。`pending_notes >= 5` 时输入框与按钮禁用并显示「留言已满」文案。提交调用 `addNovelNote(book.id, 去掉首尾空白的文字)`；成功后清空、显示「已留言。」并刷新详情；失败显示 `novelErrorMessage(error)`。空白内容不可提交。

对话框（都用原生 `<dialog>`，**必须写成 JSX 的 `<dialog …>` 标签**，两个对话框共用一个包装组件，所以 `DeskDialogs.tsx` 里 `<dialog` 恰好出现一次；`className` 用 `sourceDialogClass`，打开用 `showModal()`，带 `aria-labelledby`，有可见的「关闭」按钮，关闭后焦点回到触发它的元素）：

- **细纲对话框**：章号取 `book.chapters` 里 `status === "awaiting_plan_approval"` 的那一章，没有就取 `book.chapters_done + 1`。`getNovelChapter(book.id, n)` 取单章；取数中显示 `LoadingState`；`chapter.meeting?.decision?.beat_sheet` 不存在时显示「细纲缺失」文案。存在时渲染：

  ```tsx
  <PlanEditor key={`${n}:${chapter.updated_at}`} chapter={n} beatSheet={beatSheet}
    maxScenes={book.config.adaptation.max_scenes_per_chapter} busy={busy}
    onApprove={beat => act("plan/approve", beat ? { beat_sheet: beat } : {})}
    onRedo={text => act("plan/redo", { text })} />
  ```

  `act` 成功后关闭对话框并刷新详情；失败时**必须把错误抛出去**，让 `PlanEditor` 自己显示错误，对话框保持打开。不要另写批准、重做按钮，不要另写扣费提示。
- **读正文对话框**：标题「第 {n} 章　{章名}」。`getNovelChapter` 取 `body`，按 `whitespace-pre-wrap text-fs-16.5 leading-[1.9]` 显示；`body` 为空显示「这一章还没有正文。」。底部两个按钮：「在书斋打开」与「关闭」。只读，不提供修改。

### T6 分集页 `DeskEpisodesView`

进入这一页时才取数：

1. `studioAllowed` 为假：显示「工作室未开放」文案，不发请求。
2. `listStudioNovelSources()` 找到 `id === book.id` 的候选书。找不到或 `projects` 为空：显示「没有短片项目」文案，`eligible` 为真用第一种，否则用第二种并带上 `reason`。
3. 有项目：默认选 `latestProject(projects)`；多于一个时显示一个原生 `<select aria-label="短片项目">` 供切换（选项文字是项目标题）。聊天定位指定了项目就选它。
4. `getStudioEpisodes(projectId)`。`episodes` 为空时**只**显示「没有分集方案」文案与文字按钮「在工作室打开」（调用 `onOpenStudio(projectId)`）：不显示方案汇总行、状态标签、提示行，也不显示底部的批准栏。
5. 轮询：`episodeLocks(plan).editsBlocked` 为真且页面可见时每 5 秒链式取一次；否则不轮询。

显示：

- 汇总行：`方案第 {plan_revision} 版　共 {episodes.length} 集　约 {formatEpisodeDuration(total_seconds)}`，右边标签「已批准」（`g0_approved` 为真，朱色）或「待批准」。
- `editsBlocked` 为真时显示「拆解未完成」文案，下面所有修改、合并、批准按钮禁用。
- `(plan.unassigned ?? plan.uncovered ?? []).length > 0` 时显示「未纳入的原文」文案。
- 版本冲突提示：组件接受 prop `notice: string | null`，非空时在汇总行下面显示 `<p role="alert">{notice}</p>`。
- 分集行（展开状态的初值同样来自可选 prop `initialExpanded?: number | null`）：左集号（同章号写法）；中标题（`text-fs-15`）、`变化：…`（`text-fs-13`、`--ink2`）、`钩子：…`（`text-fs-13`、`--ink`），未展开时各最多三行；右 `formatEpisodeDuration(est_seconds)`（`readout`），`warnings.length > 0` 时加「有提示」标签，`title` 是各条警告用换行连起来。展开规则与章节行相同，展开后显示三个文字按钮：
  - 「修改」：打开 `<EpisodeEditDialog key={plan.plan_revision} episode={…} busy={…} onSave={fields => operate({ op: "edit", no, fields })} onClose={…} />`。
  - 「与下一集合并」：最后一集禁用。点了先出 `BreakdownDialog` 确认（文案见 4.4），确认后 `operate({ op: "merge", no })`。
  - 「问分身」：`onAsk(deskAskPrefix({ title: book.title, episode: no }))`。
- 底部固定一行：主按钮「批准分集方案」。禁用条件与工作室一致：`busy || approvalBlocked || episodes.length === 0 || plan.g0_approved`。点了先出 `BreakdownDialog` 确认，确认后 `approveStudioEpisodes(projectId, plan.plan_revision)`，用返回值替换当前方案。旁边一个文字按钮「在工作室打开」。

`operate(op)`：调用 `operateStudioEpisodes(projectId, { ...op, expected_revision: plan.plan_revision })`，用返回值替换当前方案。批准同理。捕获到 `ApiError` 且 `status === 409` 时：重新 `getStudioEpisodes`，把冲突文案「分集方案已在别处改动，已为你刷新，请再试一次。」存进容器的 `planNotice` 状态并通过 `notice` 传给视图，然后**正常返回，不抛错**。这样修改框、合并确认框、批准确认框会照常关闭，作者在列表上方看到冲突提示和刷新后的方案。（v1.0 要求抛错并由对话框显示，但单集修改框以 `key={plan.plan_revision}` 挂载，方案一刷新它就被重置，提示随之丢失。）`planNotice` 在这些时刻清空：下一次修改、合并或批准成功；切换项目；切换作品；点「刷新」。409 之外的错误原样抛出（`BreakdownDialog` 与 `EpisodeEditDialog` 会显示）。

### T7 面板头部与通用状态（`DeskFrame`）

- 第一行：左「案头」（`text-fs-12`、`--ink2`）；右依次是文字按钮「刷新」、当前阶段对应的去处（立意与章回显示「在书斋打开」，分集且有项目时显示「在工作室打开」）、收起按钮（`aria-label="收起案头"`，可见内容是一个 `X` 图标，`lucide-react` 的 `X`）。
- 第二行：书名 `《{title}》`（`text-fs-22`，无书名时「未命名」）。书目多于一本时，书名右侧放原生 `<select aria-label="作品">`（选项是各书书名，无书名的显示「未命名」）。
- 第三行副标题（`text-fs-13`、`--ink2`）：`novelStatusLabel(book)`、`已写 {chapters_done} 章`、`{words_done} 字`，用全角空格隔开。
- 取数中：`LoadingState`「正在取回作品…」。出错：`ErrorNotice`，带重试。

### T8 测试（全部放新文件，不改任何既有测试）

新文件名以 `backend/tests/test_desk_` 开头。要求：

- **离线**。不访问网络，不读仓库外的文件，不依赖 git 历史。
- 需要起 node 的用例，开头必须先探测 `frontend/node_modules` 里的入口文件与 `node` 可执行文件，缺了就 `pytest.skip`，并且带一条参数化自检证明「缺依赖时在起 node 之前就跳过」。照抄 `backend/tests/test_novel_chat_create_frontend.py` 里 `require_node_dependencies` 与它的自检的写法。
- 每条断言都要能区分对错实现。凡是「某写法不得出现」的扫描，必须先断言扫描到的文件集合非空且包含预期文件，并配一条自检：给一段故意违规的文本，断言扫描器能抓到。

至少覆盖：

1. `lib/desk.ts` 的每个导出（把 TS 转成 JS 在 node 里跑）：
   - `deskMode`：`1440 → dock`、`1439 → drawer`、`768 → drawer`、`767 → sheet`、`NaN → sheet`。
   - `deskSubjectFromCard`：合法草稿卡、合法项目卡各一；以下全部返回 `null`：`url` 为 `/studio/a/b`、`/studio/../x`、`/studio/a?b=1`、`https://x/studio/a`、带 `error` 的项目卡、`draft_id` 不是 36 位、`subtype` 是 `weather`、入参是 `null` / 字符串 / 数字。
   - `deskAskPrefix`：有章、有集、都没有、书名为 null、书名只有空白，各一例，断言完整字符串。
   - `parseDeskPrefs` / `readDeskPrefs` / `updateDeskPrefs`：坏 JSON、数组、`open: "true"`、`stage: "shots"`（置灰阶段要回落到 `chapters`）、非法 `novelId`、`getItem` 抛异常、`setItem` 抛异常、空用户名不写。
   - `chapterTag`：表里七行各一例，另加「`status` 是 `done` 但章号大于 `chaptersDone`」一例（应为「处理中」）。
   - `currentChapterNumber`、`episodeLocks`（`running`、`partial`、`rebreakdown_pending`、`status: "cancelled"`、全空各一例）、`latestProject`（空、并列、乱序）。
2. 视图组件的服务端渲染（node 里用 `react-dom/server`，给固定 props）：
   - 章回页：含一条 `awaiting_plan_approval`、一条 `done`、一条 `stale` 的书，断言三种标签文字都出现，朱色类只出现在「定稿」那个标签上。
   - 章回页：`pending_notes` 为 5 时留言输入框带 `disabled`，并出现「留言已满」文案；为 2 时不带 `disabled`，出现「待处理留言 2 / 5」。
   - 章回页：书 `status === "completed"` 时不出现留言输入框。
   - 分集页：`editsBlocked` 的方案里「批准分集方案」按钮带 `disabled` 且出现「拆解未完成」文案；正常方案里不带。
   - 分集页：`g0_approved` 为真时出现「已批准」且批准按钮禁用。
   - 阶段标签：五个都在，「分镜」「成片」带 `disabled` 与 `title="后续开放"`，当前阶段 `aria-selected="true"` 恰好一个。
   - （v1.1）章回页：`initialExpanded` 指向一条 `chapter <= chapters_done` 的章时出现「读正文」；指向一条 `chapter > chapters_done` 的章时不出现「读正文」但出现「问分身」。
   - （v1.1）分集页：「已批准」标签带两个朱色类，「待批准」标签不带。
   - （v1.1）分集页：`initialExpanded` 指向最后一集时「与下一集合并」带 `disabled`；指向第一集时不带。
   - （v1.1）分集页：`notice` 非空时出现 `role="alert"` 且文字是冲突文案；为 null 时不出现 `role="alert"`。
   - （v1.1）分集页：`episodes` 为空时出现「还没有分集方案，拆解在工作室里做。」与「在工作室打开」，不出现「方案第」与「批准分集方案」。
   - （v1.1）面板骨架：`mode` 为 `drawer` 与 `sheet` 时 `<aside>` 的类里有 `bg-[color:var(--paper)]`，为 `dock` 时没有；`drawer` 时外层容器类里有 `w-[476px]`；`sheet` 时内联样式里有 `45dvh`。
3. 源码契约（读文件做静态检查，不起 node）：
   - `frontend/app/page.tsx` 以 BOM 开头；2.2 的七条字面量逐条仍在。
   - page.tsx 里 `aria-controls="desk-panel"` 恰好出现一次，且它所在的按钮出现在 `aria-label="朗读"` 之前。
   - page.tsx 里 `<DeskDock` 恰好出现一次，位置在 `data-chat-panel` 之后、`id="agent-drawer"` 之前。
   - `frontend/components/desk/` 下至少有 T2 表里的六个文件；这些文件加上 `frontend/lib/desk.ts` 里：不出现 `font-medium|font-semibold|font-bold|font-extrabold|font-black`；不出现 `fontWeight` 与 `font-weight`；不出现 `#` 开头的 3 到 8 位十六进制色值；不出现 `rgb(` / `rgba(`；不出现 `var(--stamp)`、`var(--ink3)`、`var(--dim)`；不出现 `<iframe`；不出现 `fetch(`；不出现 `ceramic-card`。
   - `frontend/lib/desk.ts` 不 import `react`。
   - （v1.1）`frontend/components/desk/DeskDialogs.tsx` 里 `<dialog` 恰好出现一次；`frontend/components/desk/` 下所有文件都不出现 `createElement("dialog"` 与 `createElement('dialog'`。
   - 视图文件（`DeskFrame`、`DeskIdeaView`、`DeskChaptersView`、`DeskEpisodesView`）不出现 `useAccountRequest`、`localStorage`、`listNovels(`、`getNovel(`、`getStudioEpisodes(`。
   - `frontend/lib/novels.ts`、`frontend/lib/studio.ts`、`frontend/lib/studio-breakdown.ts` 没有被案头反向依赖之外的改动无法用静态检查证明，这一条由验收方用 `git diff` 核对，测试里不写。

### T9 文档同步

- `Fiona/CLAUDE.md`：新增一节「案头（第一期）」，写清它是什么、只动前端、三种呈现方式的宽度条件、复用了哪些组件、哪些操作会触发既有付费写作、已知局限（分镜与成片未开放、手机不自动打开、聊天读书不触发定位、编辑走对话框）。
- `Fiona/README.md`、`Fiona/docs/ARCHITECTURE.md`、`Fiona/PLAN.md`：各补一小段。PLAN 里把第二期（改稿提案）与第三期（分镜、成片）列为后续。
- 不改 `docs/DEPLOYMENT.md` 与 `backend/.env.example`（没有新配置）。
- 实施记录写到 `docs/tasks/2026-11-10-desk-board/impl/主代理.md`，不写本机绝对路径、账号名、密钥。

---

## 6. 白名单

只许新增或修改这些路径，其余任何文件不得改动：

- 新增：`frontend/lib/desk.ts`
- 新增：`frontend/components/desk/*.tsx`
- 修改：`frontend/app/page.tsx`（仅 T3 的七处）
- 修改：`frontend/app/globals.css`（仅在确有需要时新增 `.desk-` 前缀的类）
- 新增：`backend/tests/test_desk_*.py`
- 修改（v1.1 授权，仅此一处）：`backend/tests/test_ui_closeout_dialog_scrim.py` 第 117 行的 `expected_count=13` 改成 `expected_count=14`。这个文件的其他任何字符都不许动。
- 修改：`CLAUDE.md`、`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`
- 新增：`docs/tasks/2026-11-10-desk-board/impl/**`

除上面授权的那一处之外，不得修改任何既有测试的输入、断言与夹具。不得改 `package.json`、`package-lock.json`、`requirements*.txt`。

---

## 7. 验收标准

以下命令在仓库根目录的 worktree 里执行，逐条给出实际输出。

1. `cd backend && python -m pytest -q`：0 failed，通过数不少于 `7911 + 新增用例数`；除「缺 node 依赖」之外不得有 skip。在装了 `frontend/node_modules` 的环境里应为 0 skipped。
2. `cd backend && python -m pytest -q tests/test_desk_*.py -rsf`：全部通过，列出用例总数。
3. `cd frontend && npx tsc --noEmit`：退出 0。
4. `cd frontend && npm run lint`：0 errors，warnings 不多于 25。
5. `cd frontend && npm run build`：退出 0。
6. `git status --porcelain`（含未跟踪文件）列出的路径全部落在第 6 节白名单内。
7. `git diff --stat main -- backend ':!backend/tests'` 输出为空（后端非测试文件零改动）。`git diff main -- backend/tests` 只有一处改动：`test_ui_closeout_dialog_scrim.py` 里一行删、一行增（13 → 14）。
8. `git diff main -- frontend/package.json frontend/package-lock.json` 输出为空。
9. 2.2 的七条字面量逐条 `grep -c` 都不小于 1；`head -c 3 frontend/app/page.tsx | xxd -p` 输出 `efbbbf`。
10. `grep -rc 'createElement("dialog"' frontend/components/desk/` 每个文件都是 0；`grep -c '<dialog' frontend/components/desk/DeskDialogs.tsx` 是 1。

验收方（Claude）在此之外会自己做：在隔离的临时库环境里起前后端，分别在 1440、1280、390 三个宽度下走查四个场景并截图；对新测试做变异（把 `deskMode` 的阈值改掉、去掉留言已满的禁用、去掉 `editsBlocked` 的禁用、把朱色类加到所有标签上），确认对应用例变红；在不装 `node_modules` 的副本里跑新测试，确认按约定跳过而不是失败。

---

## 8. 什么时候停下来问

只有影响「做什么」时才停：

- 发现本规格与代码事实矛盾（例如某个复用组件的 props 与 2.5 写的不一样，某个接口的返回与 2.3 / 2.4 不一样）。
- 要满足某条要求就必须改白名单之外的文件，或必须改动 2.2 的字面量，或必须修改既有测试才能通过。
- 需要新增依赖。

只影响「怎么实现、怎么验证」的事自己决定，并在实施记录里写明理由。任何情况下不要回滚已经完成的工作。

---

## 9. 并行与报告

用工作流（`workflow` 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好。每个 agent 的任务说明必须自包含（它看不到你的对话），并写明**不得调用 subagent / subagent_fork / workflow**。同一个文件及其测试只归一个 agent。agent 失败先读结果再决定，不要盲目重派。主代理只做拆分、派发、汇总、白名单检查、门禁与报告。

建议的拆分（T1 的签名已经固定，所以可以并行）：

| agent | 文件 |
|---|---|
| A | `frontend/lib/desk.ts` 与 `backend/tests/test_desk_logic_frontend.py` |
| B | `DeskFrame.tsx` |
| C | `DeskIdeaView.tsx` |
| D | `DeskChaptersView.tsx` 与 `DeskDialogs.tsx` |
| E | `DeskEpisodesView.tsx` |
| F（在 A–E 之后） | `DeskDock.tsx` |
| G（在 F 之后） | `frontend/app/page.tsx` |
| H（在 B–E 之后） | `backend/tests/test_desk_views_frontend.py` |
| I（在 G 之后） | `backend/tests/test_desk_contract_frontend.py` |
| J | 四份文档 |

完成后给出变更总结，五项缺一不可：改了哪些文件；实现了哪些功能；与第 5 节任务清单的逐项对应；第 7 节每条命令的实际输出；没做完或需要人工确认的地方。报告开头列拆分表，如实列出全部派出过的 agent。

---

## 10. v1.1 变更（2026-11-10，首轮交付经门禁与界面走查之后）

首轮交付的机械门禁全过（44 项；全量 7975 通过、0 跳过）。下面六处是通读代码、变异测试和三个宽度的真实界面走查发现的，其中 1–4 是 v1.0 规格本身的问题，由规格作者负责。

1. **对话框计数**：既有门禁写死全仓 13 个 JSX `<dialog`。v1.0 没注意到这个数字，实施方为了不改既有测试改用 `React.createElement("dialog")`，等于让新对话框躲开了「必须带 scrim-dialog」的扫描。v1.1 改为：用 JSX `<dialog>`，并授权把那一个数字改成 14。
2. **抽屉与半屏不透明**：v1.0 让面板照抄现有抽屉的釉面写法，但现有抽屉里是自带底色的 iframe，案头不是，结果聊天文字透上来和案头文字叠在一起。v1.1 要求这两种方式下加纸色底。
3. **抽屉宽度**：v1.0 写 488，实际内容 476，右边多出 12px 空带，书耳离视口边 24px，和其他抽屉不齐。v1.1 改为 476。
4. **半屏高度**：v1.0 写 56dvh，在 844 高的手机上盖掉了头部与输入区之间 85% 的聊天区。v1.1 改为 45dvh 且不超过可用高度。
5. **版本冲突提示丢失**：单集修改框随方案版本号重新挂载，冲突后一刷新，提示和作者刚填的内容一起消失，没有任何反馈。v1.1 改为不抛错、关闭对话框、在列表上方显示冲突提示。
6. **没有分集的项目**：只显示空提示与去工作室的按钮，不再显示「方案第 0 版 共 0 集」和禁用的批准栏。

另补三处测试盲区（变异后没有任何用例变红）：「读正文」只对已写完的章出现；「已批准」标签才上朱色；最后一集不能合并。为此两个视图加了只用于初值的 `initialExpanded`。

---

## 11. v1.2 变更（2026-11-11，Opus 独立复核 R1 之后）

复核报告是同目录的 `05-review.md`。它确认第 7 节 10 条验收全部符合、没有新的付费途径、没有越权，结论为不通过，必须修复 2 条（11.1、11.9 的第一条）。其余各条是规格作者采纳的可优化项，一并列为本轮必须完成。本节与前文不一致时以本节为准。

### 11.1 加载标志不能被别的用途的请求取消（复核必须修复 1）

`DeskDock.tsx` 里两处会让界面永远停在「正在取回作品…」：

- 写操作（继续、恢复、完结确认、留言）还没返回时切换作品：写完后的刷新用详情作用域发起，把新书的详情请求取消了；旧书的回包又因为所选书已变被丢弃，`bookLoading` 没人清。
- 分集页拆解阻塞、5 秒轮询期间点「刷新」：取候选与取分集方案共用一个读作用域，轮询把候选请求取消了，`candidateLoading` 永远为真。

要求：

1. `loadBookDetail(id)` 在调用 `beginRead()` **之前**先判 `if (selectedBookRef.current !== id) return;`。`runNovelAction` 与 `addNote` 写完后的检查补上与 `planAct` 相同的所选书判断。
2. 书目、详情、候选、分集方案、对话框取数、聊天定位、导出，各用各的 `useAccountRequest` 作用域。
3. 逐个排查「由某个请求置真、只由它自己清除」的加载标志，确认同作用域里没有别的用途的请求能把它取消。

### 11.2 409 只有版本真的变了才算冲突

后端分集操作与批准有五种 409：「分集方案已更新，请刷新」「拆解尚未完成，完成后才能修改分集方案」「请先完成拆解」「拆解尚未全部完成，不能批准分集方案」「至少需要一集才能批准」。v1.1 把它们一律当成版本冲突，后四种会显示错误的提示并丢掉作者填的内容。

- `lib/desk.ts` 新增导出：

  ```ts
  export function isRevisionConflict(previousRevision: number, refreshed: { plan_revision: number } | null | undefined): boolean;
  ```

  `refreshed` 存在且 `refreshed.plan_revision !== previousRevision` 时返回 true，其余返回 false。
- `operatePlan` 与 `approvePlan` 遇到 409：先重新取分集方案（取到就替换当前方案）；`isRevisionConflict(发请求时的版本号, 刷新结果)` 为真才设 `planNotice` 并正常返回；否则把原来的 `ApiError` **原样抛出**，由对话框显示后端给的真实原因（这时方案版本没变，单集修改框不会被重新挂载，作者填的内容还在）。刷新本身失败时也按「不是版本冲突」处理。

### 11.3 自动打开不抢焦点

见 4.2 的改动。实现方式：打开那一刻 `document.activeElement` 是 `aria-controls="desk-panel"` 的按钮，才 `panelRef.current.focus()`。

`lib/desk.ts` 新增导出 `export function deskAutoOpens(width: number): boolean;`，等价于 `deskMode(width) !== "sheet"`。`page.tsx` 流式卡片那一处改用它（本轮授权改 `page.tsx` 的这一处判断和对应的 import 行，别处不动）。

### 11.4 关闭后不再发请求

规格 T2 第 1 条本来就要求「open 为假……不发请求」。现状是关闭后，写操作返回后的刷新、409 后的刷新、定位解析之后的选书仍会再发 GET；`resize` 监听从挂载起一直挂着。

要求：`open` 变假时让所有读作用域里在途的请求失效，并保证之后不再发起任何 GET，直到再次打开；`resize` 监听只在打开期间挂。

### 11.5 定位的两个副作用

- 定位到同一本书的另一个项目时清空 `planNotice`。
- 细纲对话框或正文对话框开着的时候忽略这一次定位，不关对话框。

### 11.6 细纲对话框

- `planAct` 失败时抛 `new Error(novelErrorMessage(cause))`，与书斋工作台一致，不把英文或原始错误直接给 `PlanEditor`。
- `DeskDialog` 增加 `busy` 参数；`busy` 为真时按 Esc 不关闭（细纲对话框把 `busy` 传进去）。
- 批准或重做细纲成功、对话框关闭后，焦点落到案头面板（`#desk-panel`），不落到头部开关。

### 11.7 无障碍

- 竖排阶段标签的 `tablist` 加 `aria-orientation="vertical"`。方向键只在**可用**阶段之间移动、到头循环，置灰阶段跳过：竖排用上下键，横排用左右键，Home / End 到第一个 / 最后一个可用阶段。不许改 `lib/useRovingTabs.ts`；可以只把可用阶段交给它，或在 `DeskFrame` 里自己处理按键。
- 章节行与分集行的展开按钮加 `aria-label`：`第 {n} 章　{章名}`、`第 {n} 集　{标题}`（行首数字是 `aria-hidden` 的，读屏用户现在听不到章号）。
- 没有章节时，`EmptyState` 不要放在 `role="list"` 的容器里。

### 11.8 文案与健壮性

- 没有短片项目且后端没给 `reason` 时，只显示「这本书还没有短片项目。」，不自拟后半句。
- 取数期间（还没有书的详情时）书名位置不显示「未命名」，留空；有详情但书名为空才显示「未命名」。
- `DeskDock.tsx` 里直接访问 `window.localStorage` 的地方包进 try/catch（访问这个属性本身就可能抛异常），失败时当作没有存储。

### 11.9 测试

- **（复核必须修复 2）**「已批准」朱色用例必须绑定到标签：找出类名含 `tag`、文字是「已批准」的 `<span>`，断言两个朱色类都在它的 `class` 里；已批准的渲染里两个朱色类在整页各只出现一次；待批准的渲染里文字是「待批准」的 `tag` 不带朱色，且整页没有朱色类；配一条自检：朱色挪到别的元素时检查器报错。
- 新增 `backend/tests/test_desk_dock_races_frontend.py`：参照 `05-review.md` 附录的 `desk-race.js`，在 node 里加载真实的 `DeskDock.tsx`、`useAccountIdentity.ts`、`desk.ts`，用带延迟的桩代替后端，复现 11.1 的两个场景，断言修复后 `bookLoading` 与 `candidateLoading` 最终为假、选中的是新书。照例先探测依赖，缺了就 skip，并带缺依赖自检。再加一个场景：关闭案头后等待一段时间，桩后端收到的 GET 数为 0（对应 11.4）。
- `lib/desk.ts` 两个新函数的逻辑用例：`deskAutoOpens` 在 767 / 768 / 1440；`isRevisionConflict` 在版本变了、没变、`null`、`undefined`。契约用例：`page.tsx` 里出现 `deskAutoOpens(window.innerWidth)`，且不再出现 `deskMode(window.innerWidth) !== "sheet"`。
- 把断言绑到元素上：
  - 面板骨架：`bg-[color:var(--paper)]` 在 `<aside>` 自己的 `class` 里（抽屉、半屏有，并排没有，并排用例要先断言确实渲染出了 `<aside>`）；
  - 半屏高度：给定 `composerHeight`（例如 88），内联样式里出现完整的 `min(45dvh, calc(100dvh - 94px - env(safe-area-inset-top) - var(--tabbar-h) - env(safe-area-inset-bottom) - 88px))`；
  - 半屏横排标签：「分镜」「成片」带 `disabled` 与 `title="后续开放"`；
  - `editsBlocked` 且 `initialExpanded` 指向某一集时，「修改」「与下一集合并」都带 `disabled`；
  - 冲突提示：带 `role="alert"` 的那个元素自己的文字就是冲突文案；
  - 竖排 `tablist` 带 `aria-orientation="vertical"`，横排不带；展开按钮的 `aria-label` 含章号 / 集号。

### 11.10 文档

- `CLAUDE.md` 与 `docs/ARCHITECTURE.md` 里「页面隐藏或操作中暂停」改成事实：轮询在页面隐藏、案头关闭、细纲或正文对话框打开时暂停，写操作进行中不暂停。
- 读请求作用域的描述按 11.1 改对。
- `impl/主代理.md`：首轮「用 createElement 写对话框」「未改任何既有测试」「localStorage 都包了 try/catch」三处旧说法标注已被 R1 / R2 取代。

### 11.11 留给作者裁定、本轮不做

- 768–1439 宽的抽屉方式会盖住聊天头部右侧的开关和「发送」按钮。
- 手机半屏未展开时列表只露出一行左右。

---

## 12. v1.3 变更（2026-11-11，R2 交付经门禁与界面走查之后）

R2 的机械门禁 50 项全过（全量 7997 通过、0 跳过），变异 50 项全部能被新测试抓到，三个宽度的界面走查 100 项里 98 项通过。没过的两项如下，都在真实界面上复现了。

### 12.1 竖排阶段标签的上下方向键不起作用（11.7 没做到）

现状：`DeskFrame` 把可用阶段交给 `lib/useRovingTabs.ts`，而它只认左右方向键和 Home / End。竖排标签上按 ↓ / ↑ 没有任何反应（走查：焦点在「分集」上按 ↓，焦点仍在「分集」）。

要求：

- `lib/desk.ts` 新增导出：

  ```ts
  export function deskStageByKey(current: DeskStage, key: string, orientation: "vertical" | "horizontal"): DeskStage | null;
  ```

  只在可用阶段（`DESK_STAGES` 里 `enabled` 为真）之间移动，到头循环：
  - `orientation === "vertical"`：`ArrowDown` 下一个，`ArrowUp` 上一个；`ArrowLeft` / `ArrowRight` 返回 null。
  - `orientation === "horizontal"`：`ArrowRight` 下一个，`ArrowLeft` 上一个；`ArrowUp` / `ArrowDown` 返回 null。
  - 两种方向下 `Home` 返回第一个可用阶段，`End` 返回最后一个可用阶段。
  - 其他按键返回 null；`current` 不是可用阶段时返回 null。
- `DeskFrame` 的两组标签都改用它处理 `onKeyDown`（竖排传 `"vertical"`，横排传 `"horizontal"`）：返回非 null 时 `preventDefault()`、切到那个阶段、把焦点移到那个阶段的标签按钮上。每个标签按钮加 `data-stage={item.id}`，按它找目标按钮，不要按下标找。当前阶段的标签 `tabIndex={0}`，其余 `tabIndex={-1}`。`DeskFrame` 不再使用 `useRovingTabs`（`lib/useRovingTabs.ts` 本身不许改）。

### 12.2 一张卡片只定位一次（R2 引入的回归）

现状：R2 为了「关闭后不再发请求」，在关闭时让聊天定位的读作用域失效；而定位用「上一次定位请求是否仍有效」来判断这张卡片处理过没有。于是每次关掉再打开案头，同一张旧卡片都会被重新定位一遍，把作者手动选的作品和阶段冲掉。（走查：卡片把案头定位到《归舟》的分集页 → 手动换到《春山》→ 收起 → 再打开，又回到了《归舟》。）

要求：用一个「已处理的 nonce」来记，与请求是否仍有效无关。

- 新增 `handledFocusNonceRef`。一次定位**走完**就把它设成这张卡片的 nonce，「走完」包括：定位生效、草稿还没建书而显示了提示、找不到对应的书、取数出错、因对话框开着被忽略、因工作室未开放被忽略。
- 定位的 effect 一开始就判：`handledFocusNonceRef.current === focus.nonce` 时直接返回，不发任何请求。
- 定位请求还没回来案头就被收起（请求被取消）的，不算走完；下次打开时重新定位一次，这是对的。
- 保留现有的防重入（同一 nonce 的请求仍在途时不重复发起）。

### 12.3 测试

- `test_desk_logic_frontend.py`：`deskStageByKey` 至少覆盖：竖排「分集」+ `ArrowDown` → 「立意」（循环）；竖排「立意」+ `ArrowUp` → 「分集」；竖排「章回」+ `ArrowDown` → 「分集」；竖排 + `ArrowRight` → null；横排「分集」+ `ArrowRight` → 「立意」；横排 + `ArrowDown` → null；`Home` / `End`；无关按键 → null；`current` 为 `"shots"` → null。
- `test_desk_contract_frontend.py`：`DeskFrame.tsx` 里出现 `deskStageByKey(`，不再出现 `useRovingTabs`；每个标签按钮带 `data-stage`。
- `test_desk_views_frontend.py`：竖排与横排渲染里，当前阶段的标签 `tabindex="0"` 恰好一个，其余可用阶段是 `tabindex="-1"`。
- `test_desk_dock_races_frontend.py` 加一个场景：卡片定位生效 → 手动换到另一本书 → 关闭 → 再打开 → 等待；断言最终选中的仍是手动选的那本，且重开之后没有再发「工作室来源」的请求。先在修复前跑一次确认是红的。

---

## 13. v1.4 变更（2026-11-11，第二轮独立复核之后）

第二轮复核报告是同目录的 `08-review-r2.md`：上一轮 2 条必须修复已修好，第 7 节 10 条验收全部符合；新发现必须修复 3 条（13.1–13.3），其中前两条是 R2 的改动带出来的。13.4–13.6 是规格作者采纳的可优化项，一并列为本轮必须完成。

### 13.1 非冲突 409 之后分集对话框关不掉（复核必须修复 1）

现状：`DeskEpisodesView.tsx` 三个对话框的 `busy` 把锁定状态算了进去（`busy={busy || editsBlocked}`、`busy={busy || approvalBlocked}`）。作者在工作室发起重新拆解后回案头保存修改、合并或批准，后端返回「拆解尚未完成…」一类的 409；按 11.2 对话框留着显示原因，但刷新回来的方案必然是锁定的，于是「取消」、Esc、「保存」全部失效，模态框挡住整个页面。

要求：

- 合并、批准两个确认框：`busy={busy}`，另加 `disabled={editsBlocked}` / `disabled={approvalBlocked}`（`BreakdownDialog` 的 `disabled` 只禁用确认按钮，不影响「取消」与 Esc）。
- 修改对话框：`busy={busy}`；`onSave` 在 `editsBlocked` 为真时不发请求，直接 `Promise.reject(new Error("拆解还没全部完成，暂时不能修改或批准，去工作室看进度。"))`。
- 打开这三个对话框的按钮仍按 `editsBlocked` / `approvalBlocked` 禁用，不变。
- 底线：非冲突 409 之后，对话框始终能用「取消」和 Esc 关闭，作者填的内容保留，并显示后端给的原因。

为了能在服务端渲染里测到对话框，`DeskEpisodesView` 加一个只作初值用的可选 prop：

```ts
initialDialog?: { kind: "edit" | "merge"; no: number } | { kind: "approve" } | null;   // 默认 null；DeskDock 不传
```

### 13.2 从面板里收起后焦点丢到 body（复核必须修复 2）

现状：案头由卡片自动打开或刷新后恢复打开时，焦点没进过面板；这时点面板里的「收起案头」，焦点落到 body，违反 4.2「收起后把焦点还给头部按钮」。

要求：面板里的收起按钮与 Esc 走同一条路——收起后显式把焦点还给头部 `aria-controls="desk-panel"` 的按钮：

```tsx
const closeFromPanel = useCallback(() => {
  onOpenChange(false);
  window.requestAnimationFrame(focusVisibleDeskToggle);
}, [onOpenChange]);
```

11.3 的打开规则保持不变。

### 13.3 四处断言绑到元素上（复核必须修复 3）

`backend/tests/test_desk_views_frontend.py`：

- 取出 `role="tablist"` 的开标签：并排与抽屉渲染时它自己带 `aria-orientation="vertical"`，且整页只出现一次；半屏渲染时它不带，整页也没有。
- 取出带 `aria-expanded` 的展开按钮开标签：`aria-label="第 1 章　…"`（分集同理）就在这个按钮上。
- Tab 停靠点：用非默认阶段（例如 `"episodes"`）分别渲染竖排与横排，唯一的 `tabindex="0"` 按钮同时带 `aria-selected="true"` 与 `data-stage="episodes"`，其余四个是 `tabindex="-1"`。
- 每条配一条自检：属性挪到别的元素上，检查器必须报错。

改完后把复核报告里的四个变异（`aria-orientation` 挪到外层容器；两种展开按钮的 `aria-label` 挪到整行；`selected` 钉在第一个标签）各做一次，都必须变红。

### 13.4 定位也要避开分集的三个对话框

11.5 只保护了细纲与正文对话框。分集的修改、合并、批准对话框开着时来一张项目卡，同样会把对话框和作者填的内容冲掉。

要求：`DeskEpisodesView` 加回调 prop `onDialogOpenChange?: (open: boolean) => void`，三个对话框任一打开或全部关闭时通知容器；容器把它并入「有对话框开着」的判断（`dialogOpenRef`），这时同样忽略定位。

### 13.5 两处小修

- 细纲对话框右上角的「关闭」在 `busy` 时禁用（批准或重做进行中关掉，失败信息就没处显示了）。
- 案头收起时把呈现方式清空（`setMode(null)`），重开后等算出当前宽度对应的方式再渲染，避免关闭期间改了窗口宽度、重开第一帧用旧方式渲染。

### 13.6 测试补充

- 视图：分集方案锁定（`active_breakdown_status: "running"`）且 `initialDialog` 分别为修改、合并、批准时，对话框里的「取消」不带 `disabled`；合并与批准的确认按钮带 `disabled`。变异：把 `busy` 改回含锁定状态，用例必须变红。
- 容器（`test_desk_dock_races_frontend.py`，可参照 `08-review-r2.md` 附录 A 的探针）：
  - 非冲突 409：操作被拒绝并带后端原因、`planNotice` 为 null、方案已刷新；真正的版本冲突：正常返回、`planNotice` 是冲突文案。
  - 卡片自动打开后从面板里收起：焦点在头部开关上；亲手打开后收起：同样在头部开关上。
  - 定位请求还没回来就收起，重开后会重新定位一次（12.2 第三条）。
- 逻辑：`deskStageByKey` 补竖排的 `Home` 与横排的 `End`。
- 视图：没有 `reason` 时文案**完整等于**「这本书还没有短片项目。」。

### 13.7 留给作者裁定、本轮不做

- 11.11 的两点不变。
- 定位已生效、但详情与项目候选还没取回就收起时，重开后项目选的是最新的而不是卡片指定的那个（只在一本书有多个短片项目时才会碰到）。

---

## 14. v1.5 变更（2026-11-11，第三轮独立复核之后）

第三轮复核报告是同目录的 `10-review-r3.md`：第二轮 3 条必须修复都已修好，第 13 节实现符合规格，第 7 节 10 条验收全部符合，R4 没有引入新的错误行为；新发现必须修复 1 条（14.1），只涉及一个测试文件。**本轮不改任何源码。**

### 14.1 「非冲突 409 之后方案已刷新」的容器用例要能证伪（复核必须修复）

现状（`backend/tests/test_desk_dock_races_frontend.py`）：

- 第二个 node 驱动 `NODE_FOCUS_DRIVER` 里 `let locked = LOCK;`，`lockedit` / `lockapprove` 场景第一次取到的分集方案就已经是锁定的（`active_breakdown_status: "running"`、第 5 版）。
- `test_non_conflict_409_keeps_reason_and_refreshes_locked_plan` 在 409 之后断言的「第 5 版、running」与操作前一模一样：容器不刷新、或刷新了不替换方案，这条用例照样通过。13.6 要求它证明「方案已刷新」，现在证明不了。
- `lockScenario` 里的日志写着「载入未阻塞方案后」，与实际不符。

要求：

1. `let locked = LOCK;` 改成 `let locked = false;`。`lockScenario` 在发起操作前已经执行 `locked = true; operationConflict = true;`，这一句不动；`let operationConflict = LOCK || CONFLICT;` 也不动。
2. `lockScenario` 在把 `locked` 置真**之前**记下 `view.plan.active_breakdown_status`，放进最后输出的 JSON，字段名 `beforeActive`。
3. `test_non_conflict_409_keeps_reason_and_refreshes_locked_plan` 对修改、批准两个场景都加断言 `beforeActive == "done"`，并保留原有断言（`activeStatus == "running"`、修改场景的 `planRevision == 5` 等）。
4. 改完后「载入未阻塞方案后」这句日志就与实际一致了，保持原文即可。

必须做的三个变异（都在 `frontend/components/desk/DeskDock.tsx`，每个做完按原字节还原并校验）：

- **G9（必须让这条用例变红）**：`refreshPlanAfterConflict` 里删掉 `setPlan(next); setPlanLoading(false); setPlanError(null);` 三行、只留 `return next;`；同时在 `operatePlan` 和 `approvePlan` 的冲突分支里，`setPlanNotice(PLAN_CONFLICT_TEXT);` 之前各加一行 `if (refreshed) setPlan(refreshed);`。这是「只在版本真变了才替换方案」的错误实现。
- **G2（这条用例仍变红）**：两处 `isRevisionConflict(currentPlan.plan_revision, refreshed)` 换成 `true`。
- **G3（`test_real_version_conflict_sets_notice_and_resolves` 仍变红）**：两处换成 `false`。

范围：只许改 `backend/tests/test_desk_dock_races_frontend.py` 和 `impl/主代理.md`。不新增用例，新测试仍是 100 条，全量仍是 8011。

### 14.2 留给作者裁定、本轮不做

13.7 的各点不变，另加第三轮复核列出的可优化项：

- 13.4（分集对话框开着时忽略定位）、13.5（收起时清空呈现方式）、13.1（锁定时保存不发请求）只有读源码的契约用例，没有行为用例。其中 13.4 与 13.1 验收方已用真实界面走查补了行为检查并做过正控。
- 分集对话框「开着」是按组件状态算的，不是按实际渲染算的：对话框开着时方案变成 0 集，或视图进入加载、出错分支，对话框不渲染了，容器仍当它开着、忽略聊天卡片，直到视图卸载。触发条件很窄（重新拆解期间后端保留上一次发布的方案，模态框又挡住「刷新」）。
- `test_locked_plan_dialogs_keep_cancel_enabled[edit]` 没有确认渲染出来的是修改对话框（标题「修改第 1 集」）。
