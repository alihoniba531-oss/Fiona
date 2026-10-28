# 组件语言统一（UI 复核第二批）实施报告

- 规格：`docs/tasks/2026-10-28-component-language/02-spec.md` v1（2026-10-28）
- 基线：`main` @ `6410890`；工作分支 `feat/component-language`
- 实施：dsh（DeepSeek Flash，max）
- 说明：本报告只记录本工作树实际执行的命令与代码依据；真实浏览器昼夜、1440×900 与 390×844 的实测由 Claude 另行完成。

## 1. 拆分与派发记录

| Agent | 范围 | 结果 |
|---|---|---|
| A | `ConfirmDialog.tsx`（新）、`layout.tsx`、`globals.css`（T1/T4/T6） | 完成 |
| B | `page.tsx`、`lib/ttsChunks.ts`（新）（T2 #4–7、T3-1、T3-6、T5 粗体） | 完成 |
| C | `ChatBubble.tsx`（T3-2 至 T3-5） | 完成 |
| D | `settings/page.tsx`、`LocalWatchSection.tsx`、`AgentMemoryPanel.tsx`、`ChatModelSection.tsx`、`novel/NovelWorkbench.tsx`（T2 #1–3、#8–12、T5 中点） | 完成 |
| E | `plaza/page.tsx`、`profile/page.tsx`、`AgentExchangeWorkspace.tsx`（T5 其余） | 完成 |
| F | `backend/tests/test_component_language.py`（T7） | 完成 |
| G（补修） | 仅 `ConfirmDialog.tsx`：兼容既有离线渲染测试的极简 React stub（无 `createContext`/`useContext`） | 完成 |

编排说明：最初两次 workflow 启动因 `parallel()` 参数写法在调度层失败，未产生任何文件改动；最终 workflow 运行 A–F。A 的初版在既有轻量 React stub 测试中触发 `createContext is not a function`，因此追加 G 做纯兼容补修，未改既有测试。

## 2. 修改与新增文件

### 修改（12）

- `frontend/app/layout.tsx`
- `frontend/app/globals.css`
- `frontend/app/page.tsx`
- `frontend/app/plaza/page.tsx`
- `frontend/app/profile/page.tsx`
- `frontend/app/settings/page.tsx`
- `frontend/components/AgentExchangeWorkspace.tsx`
- `frontend/components/AgentMemoryPanel.tsx`
- `frontend/components/ChatBubble.tsx`
- `frontend/components/ChatModelSection.tsx`
- `frontend/components/LocalWatchSection.tsx`
- `frontend/components/novel/NovelWorkbench.tsx`

### 新增（本单）

- `frontend/components/ConfirmDialog.tsx`
- `frontend/lib/ttsChunks.ts`
- `backend/tests/test_component_language.py`
- `docs/tasks/2026-10-28-component-language/03-report.md`

`docs/tasks/2026-10-28-component-language/02-spec.md` 为本单输入，工作树中原本即存在；未改既有测试、`package.json`、lockfile、`next.config.ts`、后端或白名单外文件。

## 3. 实现摘要

### T1 共用确认框

新增 `ConfirmDialog.tsx`：

- FIFO 队列，同一时刻一个原生 `<dialog>`，`showModal()` 打开；确认完成后才进入下一项。
- 确认类 `role="alertdialog"`，提示类保持原生 `dialog` 角色；`aria-labelledby` 在传标题时指向标题，`aria-describedby` 指向正文。
- 确认类默认聚焦「取消」，提示类聚焦「知道了」；关闭后把焦点还给打开前的 `document.activeElement`（若仍 `isConnected`）。
- Esc 的 `cancel` 事件与遮罩点击（`event.target === currentTarget`）均走取消；确认按钮 resolve `true`。
- `useConfirm` / `useNotice` 在真实 Provider 外抛 `Error("ConfirmProvider missing")`。
- 正文 `whitespace-pre-wrap`，按钮行 `mt-6 flex justify-end gap-2`，取消 `btn btn-quiet`，危险确认 `btn btn-danger`，普通确认/提示 `btn btn-primary`；无粗体。
- `layout.tsx` 在 `<body>` 内以 `<ConfirmProvider>` 包住 `{children}`，`<LensDefs />` 在前、`<PwaRegister />` 在后。

### T2 12 处原生弹窗

全部换成 `await confirm(...)` / `await notice(...)`；正文逐字保留，标签与 `danger` 按规格表。涉及：

- settings：清空聊天记录、永久删除账号、删号后媒体未清理提示。
- page：清空聊天界面、删除对话、上传非图片提示、图片超过 5MB 提示。
- LocalWatch：吊销设备令牌、删除规则。
- AgentMemoryPanel：清空记忆。
- ChatModelSection：删除自带模型配置与 Key。
- NovelWorkbench：删除书。

对话框打开期间可能切号/进入 busy 的位置，在 `await` 后重复检查了原守卫；settings 额外用 `getUsername()` 与捕获的 `username` 比较，避免误清新账号的本地认证。

### T3 消息行与单条朗读

- `ChatBubble.tsx` 元信息行改为纯文字按钮：分身「时间　朗读　复制　删除」，用户「时间　复制　删除」，不依赖 hover，无 `svg`、无中点/竖线分隔，父容器 `gap-3`。
- 「朗读」只在分身消息、有文本、非 typing 且传入 `onSpeak` 时显示；`speaking` 时变「停止」；`speakDisabled` 时 disabled。
- 「复制」对两种消息显示；分身消息先 `stripMessageMarkdown`；使用 `navigator.clipboard`，成功「已复制」、失败「复制失败」，1500ms 后恢复；计时器与挂载状态在卸载时清理。
- 「删除」不再依赖 `hovered`；悬停色为 `hover:text-[color:var(--seal)]`。删除了 `muted`/`hovered`、根元素鼠标进出处理及 `VolumeX`/`Trash2` 引入。
- 分身名 title 改为「（AI 分身）」；「由你的模型回复」前改为细竖线，与页头同一写法。
- `page.tsx` 新增 `speakingMessageId` 与 `handleSpeakMessage`：按固定顺序同步 `primeTtsAudio()`，用 `splitTtsChunks` 切分去 Markdown 后的正文，`ttsSessionRef` 递增，不调用 `setVoiceOn`；队列空、清空队列时复位 `speakingMessageId`。
- `lib/ttsChunks.ts` 新增纯函数 `splitTtsChunks`：句末标点切句、数字间英文句点不切、贪心拼接、超长硬切、空段丢弃。

### T4 焦点

`globals.css` 的 `@layer base` 内、`*` 规则后追加墨线 `:focus-visible` 规则，覆盖链接、按钮、summary、常见 role 与可聚焦 `tabindex` 元素；组件层 `.btn`/`.chip` 与显式 utility 的优先级不变。

### T5 粗体与中点

- `page.tsx` 3 处 `font-semibold` 去掉。
- `AgentExchangeWorkspace.tsx` 两个 `<b className="readout">` 加 `font-normal`。
- 规格 §2.6 表 8 处中点替换完成：ChatBubble 两处、settings 关于、plaza 两处、profile、LocalWatch 规则行、AgentExchange 参与者标签；「平台官方 AI · 无真人用户」保持不变且仅 1 次。

### T6 确认框样式

`globals.css` 在 `.image-preview-dialog` 规则后加入 `.confirm-dialog`、`::backdrop`、`.dark .confirm-dialog::backdrop`；宽度 `min(420px, calc(100vw - 32px))`、`margin:auto`、12px 圆角、`padding:0`，其余瓷片底/rim/lip/外阴影按规格。

### T7 新测试

新增 `backend/tests/test_component_language.py`：21 个测试（10 个测试函数，含参数化），覆盖原生弹窗清零、12 段文案、组件契约、消息行、朗读链路、`splitTtsChunks` 行为、焦点 base 规则、粗体与中点。

### T8 报告

本文件。

## 4. 验收命令与结果（§6 第 1–7 条）

### 4.1 `npx tsc --noEmit`

```text
exit 0，无输出
```

### 4.2 `npm run lint`

```text
✖ 25 problems (0 errors, 25 warnings)
```

warning 数与基线 25 相同；无新增 error。

### 4.3 `npm run build`

```text
✓ Compiled successfully
✓ Generating static pages (18/18)
exit 0
```

### 4.4 后端验收集合

命令：

```bash
cd backend
.venv/bin/python -m pytest -q \
  tests/test_ui_polish_*.py tests/test_*frontend*.py \
  tests/test_mobile_chat_fix.py tests/test_component_language.py \
  -p no:cacheprovider
```

结果：

```text
520 passed in 42.26s
```

即既有 499 条全部保留，新增 21 条；`test_novel_p2_frontend.py::test_workbench_polls_only_running_books_and_pauses_on_visibility` 仍通过。新测试单跑 `21 passed in 0.21s`。

### 4.5 结构判据实测值（括号内为 HEAD 基线）

| 判据 | 实测 |
|---|---|
| 原生 `confirm/alert` 扫描 | **0**（12） |
| `useConfirm()`：settings/page/LocalWatch/AgentMemory/ChatModel/NovelWorkbench | 每文件 **1** |
| `useNotice()`：settings/page | 每文件 **1** |
| `<ConfirmProvider>` in layout | **1** |
| `font-semibold` in `page.tsx` | **0**（3） |
| `setMuted\|setHovered\|onMouseEnter\|VolumeX\|Trash2` in ChatBubble | **0** |
| `setVoiceOn` in `page.tsx` | **5**（HEAD 5） |
| `aria-label=` 总数 | **118**（≥118） |
| `平台官方 AI · 无真人用户` | **1**（1） |

### 4.6 改动集合（§6.6）

`git status --porcelain` 只出现：

```text
 M frontend/app/globals.css
 M frontend/app/layout.tsx
 M frontend/app/page.tsx
 M frontend/app/plaza/page.tsx
 M frontend/app/profile/page.tsx
 M frontend/app/settings/page.tsx
 M frontend/components/AgentExchangeWorkspace.tsx
 M frontend/components/AgentMemoryPanel.tsx
 M frontend/components/ChatBubble.tsx
 M frontend/components/ChatModelSection.tsx
 M frontend/components/LocalWatchSection.tsx
 M frontend/components/novel/NovelWorkbench.tsx
?? backend/tests/test_component_language.py
?? docs/tasks/2026-10-28-component-language/
?? frontend/components/ConfirmDialog.tsx
?? frontend/lib/ttsChunks.ts
```

`git diff --stat` 未包含 `package.json`、`package-lock.json`、`next.config.ts`、`backend/`（新测试为 untracked）、`components/ui/`、`components/studio/`、`SongProjectCard.tsx`。`git diff --check` exit 0。

### 4.7 ChatCard 未动（§6.7）

```bash
diff <(git show HEAD:frontend/components/ChatBubble.tsx | \
  awk '/^function weatherDayLabel\(/{p=1} /^export type ImageAspectRatio/{exit} p') \
  <(awk '/^function weatherDayLabel\(/{p=1} /^export type ImageAspectRatio/{exit} p' \
  frontend/components/ChatBubble.tsx)
```

输出为空，exit 0；另单独比对 `ChatCard` 函数体（HEAD 行 107–256 对当前行 108–257）也无差异。

## 5. §6 第 8 条：未执行的浏览器项与代码依据

当前沙箱没有浏览器，未在本机执行真实浏览器量测、截图或 `page.on("dialog")` 监听；以下为对应实现依据，供 Claude 复核。

| 视觉/交互判据 | 代码依据 |
|---|---|
| 每条分身消息不悬停可见「朗读 复制 删除」，用户「复制 删除」；元信息行无 svg | `ChatBubble.tsx:426-456`，按钮条件不含 hover；三个按钮均为文字；元信息行唯一图标来源已删除。手机 40px 触控由 `globals.css:377` 的全局 `button` 最小尺寸规则保证。 |
| 点「朗读」变「停止」、发换票请求；停止/播完回「朗读」；全局开关不变 | `ChatBubble.tsx:429-437`；`page.tsx:1619-1632`（`primeTtsAudio()` 同步在点击链里，`splitTtsChunks` 入队，`setSpeakingMessageId(id)`）；`page.tsx:1309`、`:1408` 复位；`setVoiceOn` 计数仍为 5。 |
| 分身 Markdown 消息复制后「已复制」，剪贴板无 `**`/`## `/`- ` | `ChatBubble.tsx:315-330`：`stripMessageMarkdown` 后写剪贴板，成功/失败状态与 1500ms 复位；卸载清理计时器。 |
| 删除出现 `.confirm-dialog[open]`，正文、焦点取消；Esc 不发 DELETE；确认后删除并发 DELETE | `page.tsx:1585-1590`；`ConfirmDialog.tsx:124-191`：`showModal()`、取消按钮先聚焦、`onCancel` 与遮罩 cancel、确认 resolve；删消息请求在确认之后。 |
| 全程无原生 `page.on("dialog")` | 静态扫描 0 处原生 `confirm/alert`（含上传提示）；§6.5 首项。 |
| 加载样例对话无 `.msg-in-*`，新发用户消息只有该条带 `.msg-in-right` | `ChatBubble.tsx:348`：仅 `!message.id.startsWith("db-")` 时加动画；历史/本机提醒使用 `db-` 前缀。 |
| Tab 焦点墨线，非 input/textarea 有 outline 或 box-shadow | `globals.css:301` 的 base 层 `:where(...):focus-visible { outline:1px solid var(--ink) }`；`.btn`/`.chip` 的 3px offset 规则仍在。 |
| 各页及确认框无 ≥600 粗体 | `page.tsx` 无 `font-semibold`；`AgentExchangeWorkspace.tsx:222` 两个 readout `<b>` 带 `font-normal`；`ConfirmDialog.tsx` 标题/正文/按钮均未加粗。 |
| 确认框昼/夜瓷片底、朱字危险操作、无粗体 | `ConfirmDialog.tsx:158-190` 的类名；`globals.css:506-508` 的 `.confirm-dialog` 瓷片底与 `btn-danger`/`btn-primary`；无粗体样式。 |

## 6. 未完成、需人工确认与主动偏离

1. **§6 第 8 条未在本沙箱执行**：昼夜、1440×900 / 390×844、真实剪贴板权限、TTS 换票/audio 播放、`page.on("dialog")` 与截图需 Claude 在真实浏览器完成。本报告已给出逐项代码依据。
2. **ConfirmDialog 测试 stub 兼容（主动偏离）**：既有离线渲染测试注入的 fake React 没有 `createContext`/`useContext`，并直接渲染 `NovelWorkbench`（无 Provider）。为保证既有测试不被修改且仍绿，`ConfirmDialog.tsx` 在检测不到 `createContext` 时改用无 Context 的兼容分支：`useConfirm`/`useNotice` 返回一个被调用时才抛 `ConfirmProvider missing` 的函数。真实 React 下仍使用 Context，Provider 外仍立即抛错。该分支只影响离线 fake 环境，不影响应用运行；已在 `test_component_language.py` 与既有 `test_novel_p2_r1.py` / `test_studio_sources_frontend.py` 中验证。
3. **`splitTtsChunks` 的全角句点**：规格要求兼容英文句点数字规则；实现同时把全角 `．` 视为句点，属于宽松兼容，不改变规格测试的输入行为。
4. **无标题确认框**：本批 12 处均不传 `title`，因此 `aria-labelledby` 不出现；正文由 `aria-describedby` 关联，符合 T1 的「有标题时」条件。
5. **未提交 git**：按规格与工作约定，未执行 commit。

## R1 返修（2026-10-28）

R1 按返修单把 `ConfirmDialog` 从 React Context 改为模块级队列，并删除了上一版为离线测试 stub 保留的 `createContext`/`useContext` 兼容分支。第 6 节第 2 条所述「测试 stub 兼容（主动偏离）」自本节起不再适用，以本节为准。

### R1-1 实现

- `ConfirmDialog.tsx` 新增模块级 `let host: ((item: QueueItem) => void) | null = null;`。
- `confirmImpl` / `noticeImpl` 为模块级普通函数；`host` 为空时返回 `Promise.reject(new Error("ConfirmProvider missing"))`，否则入队并返回 Promise。
- `useConfirm()` / `useNotice()` 返回上述模块级函数的稳定引用，不调用任何 React API；导出名与签名不变。
- `ConfirmProvider` 用 `useEffect` 在挂载时注册 `host = enqueue`，卸载时仅在 `host === enqueue` 时置回 `null`。
- `ConfirmProvider` 返回 `<>{children}{dialog}</>`；FIFO 队列、`showModal()`、`role="alertdialog"`、默认焦点、Esc/遮罩取消、焦点归还与样式类均未改。
- 已删除 `createContext`、`useContext`/`readContext`、`ConfirmContext`、`readContextValue`、`ConfirmContextValue`、`useMemo` 及无 Context 分支。

### R1-2 测试补强

`backend/tests/test_component_language.py` 只增不减，新增 2 条测试：

- `test_confirm_dialog_uses_module_level_queue_without_context`：断言源码不含 `createContext`、`useContext`、`readContext`、`ConfirmContext`；含 `Promise.reject(new Error("ConfirmProvider missing"))` 与模块级 `host` 注册/清理；`useConfirm`、`useNotice` 函数体不匹配 `\buse[A-Z]\w*\(`。
- `test_use_confirm_rejects_without_mounted_provider`：Node + TypeScript 转译 `ConfirmDialog.tsx`，不挂 Provider 调用 `useConfirm()({ body: "x" })`，断言 Promise 被拒绝且错误信息为 `ConfirmProvider missing`。缺少 TypeScript/React 时按现有写法 `pytest.skip`。

新测试文件现为 23 个测试（原 21 + 新增 2）。

### R1-3 自检命令与实际输出

#### `cd frontend && npx tsc --noEmit`

```text
exit 0，无输出
```

#### `cd frontend && npm run lint`

```text
✖ 25 problems (0 errors, 25 warnings)
```

0 errors；warning 25，与既有基线相同。

#### `cd frontend && npm run build`

```text
✓ Compiled successfully in 454ms
✓ Generating static pages using 17 workers (18/18) in 171ms
exit 0
```

#### 后端验收

```bash
cd backend
.venv/bin/python -m pytest -q \
  tests/test_ui_polish_*.py tests/test_*frontend*.py \
  tests/test_mobile_chat_fix.py tests/test_component_language.py \
  tests/test_novel_p2_r1.py -p no:cacheprovider
```

```text
536 passed in 44.91s
```

0 failed，0 skipped。范围包含 `test_novel_p2_r1.py`；既有 fake React 无 `createContext`/`useContext` 的渲染测试也保持通过。

R1 只改了 `frontend/components/ConfirmDialog.tsx`、`backend/tests/test_component_language.py`（只增不减），并在本报告末尾追加本节；未改其他文件，未提交 git。
