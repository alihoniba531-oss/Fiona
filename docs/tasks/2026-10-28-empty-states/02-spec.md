# 02 规格：空态与文案（UI 复核第三批）

- 规格版本：v1.2（2026-10-28；v1 经四个视角对抗审查后修订为 v1.1；v1.1 实施后经独立复核与真实浏览器实测，再修订为 v1.2。修订点见文末 §10，返修单见 `05-fix-r1.md`）
- 基线：`main` @ `f6adca6`；工作分支 `feat/empty-states`（本工作树）
- 来源：`docs/tasks/2026-10-28-ui-review/01-audit.md` 的 P2-8、P2-10、P2-11、P3-19、P3-20、P3-21。
- 用户已拍板：
  - 画像页改名「社交画像（旧版）」，并授权改 `backend/tests/test_ui_polish_settings_drawers.py` 第 83 行这一处既有测试（只换标题参数，见 T5）。
  - P3-20 的同一根因在 10 处一起修（见 T1）。
- 级别：L2（组件与文案，不改接口、数据模型、依赖）。全程不设中途确认。
- 执行者：dsh（DeepSeek Flash，max）；Claude 做门禁与真实浏览器实测；独立复核另派。

---

## 1. 产品目标

七件事，都是「空着的地方不给方向，或者文案让人误会」：

1. **身份没确认就说「请登录」**（P3-20 与同根因 9 处）：已登录的人打开书斋、新建小说、工作室、知识库、分身、交流、记忆、分身名片这些页面时，会先看到「请登录后…」，网络慢时会持续好几秒。身份还没确认时，改为显示「正在加载身份…」。
   - 本批只修「身份确认中」这段时间。
   - 身份找回**失败**（`/api/profile` 返回 500 或断网）后，仍回到原来的「请登录后…」文案，这是本批的**已知局限**，写进报告，不在本批处理。
2. **抽屉里的重复标题与双入口**（P2-8）：
   - 工作室抽屉的页眉已经写着「工作室」，下面又是 28px 的「短片工作室」；
   - 书斋没有书时，页眉和空态卡里各有一个「新建一本」。
3. **新对话空态**（P2-10）：现在只有一行 12px 的「和 Chloe 开始新的交流。」，下面整屏空白。改为给三个可点的开场：「聊聊今天」「帮我画一张…」「看看我拍的这张图」。三个都只预填文字或打开入口，**绝不自动发送**（发送会扣草莓），包括按住 Enter 的情况。
4. **匹配页空态**（P2-10）：右侧整片空白，左栏只有一行 11px 小字。要讲清楚三件事：匹配是什么、为什么这里可能一直是空的、还有什么别的办法认识其他用户。并给出「查看公开名片设置」的入口。
5. **画像页改名**（P2-10）：「旧社交画像」是系统内部的叫法，改成「社交画像（旧版）」，页内说法统一。
6. **设置页隐私说明太长**（P2-11）：「聊天模型」一节末尾是 8 段 13px 的说明连排，把下一节挤出首屏。改为：
   - 最关键的第一段挪到「启用」开关和「保存」之前，常显；
   - 其余 7 段收进折叠块；
   - 选了 Claude 时多显示一句「图片和工具结果也会发给 Anthropic」；
   - 开关旁那句误导的说明改准（首次保存就会直接启用）。
7. **两个小处**：
   - 历史页日期筛选（P3-19）：原生日期框显示的是浏览器自带格式（英文环境下是 `mm/dd/yyyy`），和整页对不上。改为两枚 chip，显示中文日期。
   - 语音按钮（P3-21）：手机上按住或录音时，按钮上的「松开发送 / 点此发送」是隐藏的，只剩颜色变化。加一个只在手机上显示的状态气泡。

## 2. 现状事实（HEAD `f6adca6` 实测；行号以 HEAD 为准）

### 2.1 P3-20：「请登录」的根因（已在真实浏览器复现）

- `frontend/lib/useAccountIdentity.ts:18-23`：`useAccountIdentity()` 返回 `useSyncExternalStore(subscribeAccount, getUsername, serverIdentity)`，其中 `serverIdentity = () => ""`，所以服务端渲染与水合首帧时身份恒为空串。
- `frontend/lib/auth.ts:34-66` 的 `ensureAccountIdentity()`：
  - 本地存储 `fiona_user` 有名字时立即返回；
  - 没有名字时，用 Cookie 请求 `GET /api/profile` 找回，请求在途期间身份是空串；
  - 401 跳登录页；其他错误或断网返回空串，本页之后不再重试。
- 10 处组件都是同一结构：外层（调 `useAccountIdentity()` 的组件；第 10 处是被默认导出包在 Suspense 里的 `AgentPageContent`）渲染 `<Inner key=… owner={owner} …/>`，内层用 `!owner ? <请登录…> : …` 判断，于是空串一律被当成「未登录」。10 处见 T1 的表。
- HEAD 复现（隔离实例；复现脚本与结果在 `docs/tasks/2026-10-28-empty-states/verify/`，该目录由 Claude 维护，不在你的工作树里）：

| 场景（已登录） | `/novels/new` | `/novels` |
|---|---|---|
| 服务端渲染的原始 HTML（带有效 Cookie） | 含「请登录后新建小说」 | 含「请登录后查看你的书架」「前往登录」 |
| 正常网络 | 1 秒起显示向导 | 1 秒起显示空书架 |
| 前端脚本晚到 3 秒 | 前 2.5 秒显示「请登录」 | 前 2.5 秒显示「请登录」 |
| 本地无用户名、`/api/profile` 慢 4 秒 | 前 2.5 秒显示「请登录」 | 前 2.5 秒显示「请登录」 |
| 本地无用户名、`/api/profile` 返回 500 | 8 秒后仍显示「请登录」（本批不修，见 §1） | 同左 |

- 小说功能关闭（`FIONA_NOVEL` 不为 1）时，向导和书架显示「小说工坊尚未开放」。这是正确的文案，由 `ErrorNotice` 渲染，有测试锁定恰好 1 个（`test_novel_p2_r1.py:286-296`）。新分支必须放在 `!owner` 内部，不能吞掉它。
- 嵌入抽屉里点「前往登录」时，iframe 会自己跳到 `/login`；登录后 `router.replace("/")` 会把整个主页套进抽屉。可参照的先例：`app/profile/page.tsx:138` 用的是 `target={embedded ? "_top" : undefined}`。

### 2.2 P2-8：工作室与书斋

- 工作室：
  - 抽屉页眉文字是「工作室」（`app/page.tsx:2942`），iframe 地址是 `/studio?embed=1`。
  - `components/studio/StudioShelf.tsx:69` 是 `<div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-[28px] tracking-[.24em]">短片工作室</h1>`，h1 不带嵌入条件。
  - `:70` 是 `{access && !unavailable && <button type="button" className="btn btn-primary min-h-10" onClick={() => setCreating(true)}><Plus size={15} />新建项目</button>}`。
  - 既有测试要求嵌入态下「新建项目」仍是可点的原生 `button`（`test_studio_frontend_shell.py:155`）。
- 10-26 的做法：嵌入时只给 h1 加 `sr-only`，独立页不变。
  - 设置、画像、分身、广场：直接在 h1 上写 `${embedded ? " sr-only" : ""}`。
  - 书斋：在 `app/novels/page.tsx:10` 外包一层 `[&_header_h1]:sr-only [&_header_h1+*]:ml-auto`。
  - 两种写法都有测试锁定，**不要动** `app/novels/page.tsx`。
- h1 变成 `sr-only`（即 `position:absolute`）后，`justify-between` 下只剩按钮一个子项，按钮会贴左，所以要加 `ml-auto`。
- 书斋：
  - `components/novel/NovelShelf.tsx:59` 页眉的 `<Link href={newBookHref} className="btn btn-primary min-h-10"><Plus size={15} />新建一本</Link>` 没有任何条件；
  - `:64` 空态卡里还有一个 `<Link href={newBookHref} className="btn btn-primary min-h-10">新建一本</Link>`；
  - 没有测试锁定页眉这个 Link。
  - `:64` 的分支顺序是：未登录 → 出错 → 加载中 → 空态卡（`books.length === 0`）→ 书卡。
- 刷新按钮的现有问题：`NovelShelf.tsx:23` 的 `loading` 初值为 true，`:27-28` 没有身份时 `refresh` 在 `try` 之前就 return，所以未登录时刷新按钮一直显示「刷新中…」并禁用。本批顺手修（T2）。

### 2.3 P2-10：新对话空态（`frontend/app/page.tsx`）

- `:2596-2598` 原文：
  ```
  {messages.length === 0 && (
    <p className="text-xs text-muted-foreground text-center pt-8" role="status">{conversationLoading ? "正在加载对话…" : conversationError ? "对话加载失败，请在上方重试。" : currentConversation ? `和 ${agent?.display_name || "你的分身"} 开始新的交流。` : "点击上方“新对话”，开始和自己的分身交流。"}</p>
  )}
  ```
  （「新对话」两侧是弯引号 U+201C / U+201D。）
- 「新建」按钮的位置：
  - 1024px 以上，它在左栏对话列表顶部（`ConversationPicker.tsx:56-57`，可见文字「新建」）；
  - 1024px 以下，它收在页头「对话列表」图标后面（`page.tsx:2512-2514`）。
  - 所以「点击上方」「请在上方重试」两种说法的方位都不准。
  - `ConversationPicker.tsx:91` 写的是「还没有对话。点「新对话」，开始和自己的分身交流。」，和按钮名「新建」对不上。
- 可复用的能力：
  - `composeSongSection(text)`（`:654-657`）只做两件事：`setInput(text)`，下一帧聚焦输入框，不发送；
  - 图片菜单三项（`:2685-2709`）：「发图给 Chloe 看」调 `fileInputRef.current?.click()`，「生成图片」调 `setImageMode(true)`，「改一张图」调 `referenceFileInputRef.current?.click()`；
  - 用得到的变量位置：`conversationLocked` 在 `:1638`，`hasReferenceImages` 在 `:1764`，`handleNewChat` 在 `:1785`，`input` state 在 `:454`。
- 扣费只发生在 `handleSend` 调 `POST /api/chat` 时（`:1959`）。`setInput`、`setImageMode(true)`、`fileInputRef.click()` 都不发请求。
- **按住 Enter 的风险**：
  - `handleKeyDown`（`:2221-2227`）不判断 `e.repeat`；
  - 在开场 chip 上按住 Enter 超过按键重复延迟时，焦点被移到输入框后，重复的 keydown 会落在输入框上，直接 `handleSend()`；
  - `composeSongSection` 还会覆盖输入框里已有的草稿。
- `:962` 的注释「Inline voice-to-text: records, sends to ASR, puts text in input for review」与实现不符：实际是识别后直接发送（`:930`、`:1005`）。

### 2.4 P2-10：匹配页（`frontend/app/match/page.tsx`）与画像页

- 匹配页的位置与写法：
  - 匹配页只出现在主页「世界」抽屉的「匹配」chip 下（`app/page.tsx:2849`，`/match?embed=1`），只用 `mobile:` 变体（43 处，`max-md:` 0 处）。
  - 嵌入判断在 `:304`：`const embedded = searchParams?.get("embed") === "1";`，位于 `MatchForAccount` 内（`:152` 起）。
  - 文件没有导入 `next/link`。
  - `:74` 有一行注释 `{/* 匿名头像 */}`，在 CloudCard 内。**保持原样，不要改。**
  - 手机上外层是 `mobile:flex-col`（`:310`），「最近聊天」排在上方而不是左侧。
- 左栏空态 `:320-324`：`<p className="text-[11px] text-muted-foreground">接受匹配后会出现在这里</p>`。
- 右侧 `:345-347`：
  - 未选中联系人时渲染 `{pendingMatches.length === 0 ? null : (…CloudCard…)}`，没有推荐卡时整片空白；左栏有房间但没选中时也一样空白。
  - 桌面上这个容器是 `overflow-hidden`，不能滚动。
- 产品事实（写说明文案的依据，只写成立的事）：
  - 匹配是旧版的真人连接，系统曾根据对话和社交画像（旧版）推荐可能聊得来的人。现在的聊天路径不会再产生新的推荐卡：`backend/tests/test_conversation_chat.py:480-482` 锁定新会话零匹配调用，README.md:11 也有说明。
  - 推荐卡约 25 秒后开始淡出，27 秒后移除，并被标记为已看，之后不会再出现（`:53-54`、`:223-225`）。
  - 卡片上点「认识下」只会展开招呼框，框里的「发送打招呼」才真正接受，招呼可以不写；「跳过」只是收起招呼框（`:113-147`）。双方都接受后，对方才会出现在「最近聊天」里。
  - `/match/pending` 会把对方的真实用户名发到前端，所以**不能**写「匿名」或「对方不知道你是谁」。
  - 公开名片和匹配无关：匹配相关代码里 `is_public` 一处都没有。
    - 公开名片的作用：其他已登录用户能在「广场」看到你的分身，并邀请它交流。
    - 分身交流的前提：双方都已公开名片（`backend/exchange_store.py:439-442`）。
    - 分身交流的过程：对方接受后，两个 AI 分身轮流回复，结束后生成总结，**不会建立真人聊天**（`AgentExchangeWorkspace.tsx:119`、`:234`）。
    - 开关的位置：在 `MyAgentWorkspace`（`/agents/me`），开关名「公开分身名片」，勾选后还要点「保存分身」。
- 画像页 `frontend/app/profile/page.tsx`：
  - `:98` h1 是「旧社交画像」（嵌入时 `sr-only`）；
  - `:121` 是 `暂无旧社交画像`；
  - `:136` 是「这里保留旧社交画像，不展示新会话的私有记忆。你可以在“我的分身”中查看新记忆，或清空分身记忆和已有个人画像；聊天记录会保留。」。
  - 「清空记忆与个人画像」（`AgentMemoryPanel.tsx`，文案被测试锁定）清掉的正是这份旧画像（`backend/agent_store.py:253-254`）。
  - 「旧社交画像」在 frontend 里只有上面 3 处；文档里有 3 处：`README.md:11`、`PLAN.md:54`、`docs/ARCHITECTURE.md:126`。
  - `backend/tests/test_ui_polish_settings_drawers.py:83` 是 `assert_heading_hides_when_embedded(PROFILE, "旧社交画像")`。

### 2.5 P2-11：设置页隐私说明（`frontend/components/ChatModelSection.tsx`）

- 复核报告写的「7 段」「找保存要翻过去」都与源码不符。实际情况：
  - 隐私块在 `:368-377`，是 8 个不带属性的 `<p>`；
  - 「测试连接 / 保存」按钮在它前面（`:360-363`，第二个 `fieldset` 内）；
  - 问题出在整节太高，下一节被挤出首屏。
- 第二个 `fieldset` 里的结构：
  - `:345` 起是「启用我的聊天模型」开关块（`<div className="border-t border-[color:var(--carve)] pt-3 shadow-[inset_0_1px_0_var(--etch)]">`）；
  - `:358` 是开关说明 `{!config ? "先保存配置，才能启用。" : config.status === "needs_reentry" ? "请重新填写并保存 Key。" : "开关使用已保存的配置；关闭后使用平台模型。"}`。
- 首次「保存」就会启用自带模型：`backend/byok/store.py:173` 在首次保存时把 `enabled` 设为 True。所以「先保存配置，才能启用」会让人以为保存后还要再拨开关，是误导，而第一段说明必须在点「保存」之前就能看见。
- 当前选中的厂商是 `provider`（`:34`），选 Claude 时 `provider.id === "anthropic"`。
- 测试锁：
  - 第一段（`:369`，「启用后，聊天回复会把分身设定…」）没有测试锁。
  - 被测试按原文锁的是三段，都要求写在一行、不带属性的 `<p>…</p>`：`:371`「生图：…」（`test_chat_image_tool_frontend.py:164`）、`:372`「选 Claude 时，…」（`test_claude_agent_frontend.py:212-213`，要求在「生图」之后）、`:375`「开启『聊天读小说』后，…」（`test_novel_chat_frontend.py:59`）。
  - `:358` 的说明、`:144` 的「聊天模型已保存」都没有测试锁。
- 可参照的先例：
  - 前端已有 `<details>` 的用法（`AgentExchangeWorkspace.tsx:460-461`、`novel/NovelWizard.tsx:192`）；
  - Tailwind preflight 把 `summary` 设为 `display:list-item`，带默认三角；
  - 全局焦点规则已覆盖 `summary`（`globals.css:301`）。

### 2.6 P3-19：历史页日期筛选（`frontend/app/history/page.tsx`）

- 历史页是独立路由，从不嵌入；入口是对话目录的「完整历史」，用 `window.open` 打开。全文用 `max-md:`（55 处），`mobile:` 0 处。
- 日期块的结构：
  - `:207-210` 是「自定义区间」标题；
  - `:211` 是外层容器 `<div className="space-y-1.5 max-md:grid max-md:grid-cols-1 max-md:gap-1.5 max-md:space-y-0">`，它的 `</div>` 在 `:235`；
  - `:212-218` 是开始日期输入框（`aria-label="开始日期"`）；
  - `:219` 是 `<div className="text-center text-[10px] text-muted-foreground">至</div>`；
  - `:220-226` 是结束日期输入框；
  - `:227-234` 是「清除筛选」按钮。
- 原生日期框的占位格式跟着浏览器界面语言走。页面本身已是 `lang="zh-CN"`，但无头 Chromium 分别用 `zh-CN` 与 `en-US` 两种上下文实测，都显示 `mm/dd/yyyy`，页面无法可靠地改成中文。
- `:194` 「全部」的高亮条件是 `quick === key && dateFrom === (key === "all" ? "" : dateFrom)`，只设了「到」时「全部」仍然高亮。
- `:272` 右栏摘要直接显示原始日键 `{dateFrom || "—"} 至 {dateTo || "—"}`。
- 可用工具：
  - `lib/beijingTime.ts` 的 `beijingDayStart(dateKey)`（:36）、`formatBeijingDateLong(date)`（:64，输出「2026年10月27日」）；
  - `HTMLInputElement.showPicker()` 在 TS lib.dom 里已有声明。
- 全仓 `aria-label=` 现在正好 118 处，不得减少。
- 全局焦点规则（`globals.css:301`）不覆盖 `input`；`.chip-on` 的边框本来就是 ink 色（`globals.css:360`）。

### 2.7 P3-21：语音按钮（`frontend/components/VoiceButton.tsx`）

- 真实行为（README.md:16 也是这么写的；复核报告说「轻点转文字」不对）：
  - 轻点：开始录音；再点一下：停止并识别，有文字就**直接发送**，不填进输入框；
  - 按住满 350ms：开始录音；松开：识别后直接发送。
- 桌面上已经有提示：
  - `:141` 的 `shortLabel` 三态是「语音 / 点此发送 / 松开发送」；
  - 首次轻点后会弹出一次性气泡「也可以按住说话，松开就发送」，显示 4 秒，本地存储键 `chloe-voice-hint-v1`（JSX 在 `:145-149`）。
- 手机上，`<span className="max-md:hidden">{shortLabel}</span>`（`:164`）把短字隐藏了，按住或录音时只剩颜色变化。**缺口只在手机端。**
- `:163` 已有 `<Mic size={14} aria-hidden="true" />`；`max-md:hidden` 里含子串 `md:hidden`。新测试必须只针对新元素做断言（见 T9）。
- 这个文件被测试锁得很死（见 §3.2），只能在根元素里新增一个元素。

### 2.8 门禁基线（HEAD 实测，next 16.4.3，本工作树）

- 前端：`npx tsc --noEmit` → 0；`npm run lint` → 0 errors、25 warnings；`npm run build` → 0。
- 后端全量（约 300 秒）：`cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` → **7774 passed、0 skipped、0 failed**。

## 3. 技术约束

### 3.1 白名单

修改：
- `frontend/lib/useAccountIdentity.ts`（T1-1，只新增）
- 书斋：`frontend/components/novel/NovelWizard.tsx`、`frontend/components/novel/NovelShelf.tsx`、`frontend/components/novel/NovelWorkbench.tsx`
- 工作室：`frontend/components/studio/StudioShelf.tsx`、`frontend/components/studio/StudioWorkbench.tsx`、`frontend/components/studio/kb/KbWorkbench.tsx`
- 分身：`frontend/components/MyAgentWorkspace.tsx`、`frontend/components/AgentExchangeWorkspace.tsx`、`frontend/components/AgentMemoryPanel.tsx`、`frontend/app/agents/[id]/page.tsx`
- 对话：`frontend/app/page.tsx`、`frontend/components/ConversationPicker.tsx`
- `frontend/app/match/page.tsx`、`frontend/app/profile/page.tsx`
- `frontend/components/ChatModelSection.tsx`
- `frontend/app/history/page.tsx`
- `frontend/components/VoiceButton.tsx`
- `README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`：**只改**含「旧社交画像」的那一行（T5）
- `backend/tests/test_ui_polish_settings_drawers.py`：**只改第 83 行**（T5，用户授权的唯一一处既有测试改动）

新增：
- `backend/tests/test_empty_states_identity.py`、`test_empty_states_novel.py`、`test_empty_states_studio.py`、`test_empty_states_agents.py`、`test_empty_states_chat_openers.py`、`test_empty_states_match_profile.py`、`test_empty_states_settings_privacy.py`、`test_empty_states_history_dates.py`、`test_empty_states_voice_hint.py`（共 9 个）
- `docs/tasks/2026-10-28-empty-states/03-report.md`

其余一律不动：
- 不改 `package.json`、lockfile、`next.config.ts`；
- 不改 `frontend/lib/auth.ts`、`frontend/app/globals.css`、`frontend/app/novels/page.tsx`、`frontend/app/studio/page.tsx`；
- 不改 `StudioShell.tsx`、`NovelShell.tsx`、`NovelStates.tsx`、`ComposerImageMenu.tsx`、`ChatScrollArea.tsx`；
- 不改后端代码；不删文件；不提交 git。

完成标准与验收命令的覆盖范围与本白名单一致。本规格所在目录已在工作树里，属预期。

### 3.2 必须原样保留（既有测试锁定，改动会变红）

- **page.tsx**：
  - 不得出现 `onClick={() => setImageMode(true)}`；
  - 计数类锁：`type="file"` 恰好 2 处；`<ComposerImageMenu`、`<VoiceButton` 各 1 处；`drawer-panel` 恰好 6 处；
  - 结构类锁：`<ChatScrollArea`、`</ChatScrollArea>`、`className="chat-message-layer`、`<Glaze as="footer"`、`chat-latest` 各 1 处；含 `data-chat-panel` 的行恰好 1 行；「回到最新」1 处；
  - 字重类锁：`className="readout font-normal"` 恰好 2 处；不得有 `<b>`、`font-semibold`；
  - 不得出现 `title="语音转文字"`、`aria-label="按住说话"`、`>上传参考图<`、`<ImagePlus`、`<Mic`，开场 chip 不加图标；
  - 图片菜单 `items` 的 key、label、description、三个 `onSelect`、disabled 表达式原文不动，不得抽成共享变量或共享处理函数；
  - `handleSend` 一字不动（有两段按 sha256 锁定）；
  - 工作室提醒的 `useEffect`：从锚点 `const poller = createStudioNoticePoller({` 往回找最近的 `useEffect(() => {`，两者之间不得插入新的 `useEffect(() => {`；
  - 费用与快捷键文案不得复制：
    - `每条消息消耗 <span className="readout font-normal">10</span> 颗草莓` 恰好 1 处；
    - `"平台模型 · 每条 10 颗草莓"` 恰好 2 处；
    - `平台模型每条消息消耗 10 颗；自带模型聊天不扣` 恰好 1 处；
    - `Enter 发送，Shift + Enter 换行` 恰好 1 处；
  - 「有新的工作室提醒 · {notice.project_title}」保留原样。
- **设备时区扫描**：`page.tsx`、`ConversationPicker.tsx`、`AgentExchangeWorkspace.tsx`、`history/page.tsx` 被逐行扫描，注释也算。新代码和新注释里不得出现：
  - `toLocaleString`、`toLocaleDateString`、`toLocaleTimeString`、`toDateString(`；
  - 以 `getHours(`、`getMinutes(`、`getDate(`、`getDay(`、`getMonth(`、`getFullYear(` 结尾的任何标识符调用（不论有没有点号）。
- **VoiceButton.tsx**：
  - 全部现有行原样保留，包括：
    - 提示相关：`HINT_KEY`、`localStorage` 两句、`try {` 与 `} catch {` 各恰好 1 处、`setShowHint(true);`、`HINT_DURATION_MS = 4000`、`role="status"`、「也可以按住说话，松开就发送」、`ceramic-card absolute bottom-full`；
    - 按钮相关：按钮类名串、录音态类名、三条 `stateLabel` 和三个短字字面量、`<span className="max-md:hidden">{shortLabel}</span>`；
    - 全部指针状态机的逐字片段。
  - 导入行不变：只允许 `react`、`lucide-react`、`@/lib/utils`，`import { cn } from "@/lib/utils";` 一字不改。
  - 不新增 hook，不新增 `try`。
  - 根元素的 `props.children` 必须是数组，且 `<button>` 是根元素的**直接**子元素。
- **ChatModelSection.tsx**：
  - 被锁的三段（生图、选 Claude 时、开启『聊天读小说』）仍各为一行、不带属性的 `<p>…</p>`，生图在选 Claude 之前；
  - 第一段按 T6 写成 `<p className={noteClass}>`，文字一字不改；
  - 其余四段（危机复核、自带模型文字聊天、Key 加密保存、Claude 的接口不对中国大陆）保持原样，不带属性；
  - `noteClass` 常量不动；
  - 删除确认文案「确定删除自带模型配置与 Key？之后聊天将使用平台模型。」恰好 1 处；`useConfirm()` 保留。
- **history/page.tsx**：保留 `@/lib/beijingTime` 的导入与 `formatBeijingTime(` 调用；`<MessageText text={msg.content} highlight={query} />` 原样保留。
- **profile/page.tsx**：h1 开标签保留 `${embedded ? " sr-only" : ""}`；`.join("、")` 保留，不得出现 `.join(" · ")`。
- **AgentExchangeWorkspace.tsx**：含广场标题的 h1 恰好一行；不得出现 `<b className="readout">`；「平台官方 AI · 无真人用户」恰好 1 处。
- **AgentMemoryPanel.tsx**：清空确认文案「清空分身记忆和已有个人画像？聊天记录与分身设定会保留，后续交流可形成新的记忆。」恰好 1 处；`useConfirm()` 与 `isCurrentOwner()` 复查保留。
- **match/page.tsx**：`:74` 的 `{/* 匿名头像 */}` 注释保持原样。
- **书斋与工作室**：
  - `app/novels/page.tsx` 不动；`StudioShelf` 嵌入态的「新建项目」仍是原生 `button`；
  - 404 时恰好 1 个 `ErrorNotice`（「小说工坊尚未开放」）；
  - `components/novel/**` 与 `app/novels/**` 不得出现 `max-md:`、十六进制颜色、`rgba(` / `hsla(`、`font-family`、`font-mono`。
- **通用**：
  - 界面文字不加粗：不新增 `font-semibold`、`font-bold`、`fontWeight`、`font-weight ≥ 600`、`<strong>`，以及不带 `font-normal` 或 `font-medium` 的 `<b>`（`font-medium` 即 500，允许）；
  - 新写文案不用中点「·」；
  - 被 iframe 内嵌的页面（`/novels`、`/studio`、`/match`、`/profile`、`/settings`）只用 `mobile:`，不写 `max-md:`；`page.tsx`、`history/page.tsx`、`VoiceButton.tsx` 沿用 `max-md:` / `md:`；
  - 全仓 `aria-label=` 不少于 118；
  - 不新增原生 `confirm(` / `alert(`。

### 3.3 测试替身的限制（违反会让既有测试崩溃）

`backend/tests/` 里有三套「精简 React 替身」驱动，会真实加载 `lib/useAccountIdentity.ts` 和 T1 的大部分组件：
- `test_novel_p2_r1.py` 的 `DRIVER`；
- `test_studio_frontend_components.py` 的 `DRIVER`（在 kb 测试里导入为 `COMPONENT_DRIVER`）；
- `test_studio_frontend_navigation.py` 里的驱动。

它们只提供：
- React：`useState`、`useRef`、`useMemo`、`useEffect`、`useCallback`、`useSyncExternalStore`；`useId` 只有前两套提供，导航那套**没有**。
- `@/lib/auth`：只有 `getUsername`、`ensureAccountIdentity`、`apiFetch`；导航那套多一个 `updateBalance`。
- `window`：组件替身和导航替身里只有 `addEventListener` / `removeEventListener`；小说替身另有 `location.origin` 和 `parent`。三套都没有 `dispatchEvent`，一律不得依赖这些属性。

另外：
- 小说替身的 `useSyncExternalStore` 只调用 `getSnapshot`，订阅回调是空函数，永远不会因订阅而重渲染。
- 组件替身的 `useState` 每次渲染都返回新的 setter。
- 服务端渲染模式（真实 React）下，渲染期间不能碰 `window` / `localStorage`。
- 非 `@/` 开头、且不在替身白名单里的导入一律报错。例如 `cn` 会把 `clsx` 带进来。

由此规定：
- `lib/useAccountIdentity.ts` 的新代码只许用 `useEffect`、`useSyncExternalStore`、模块级变量，以及已导入的 `getUsername` / `ensureAccountIdentity`。不得新增从 `@/lib/auth` 的导入，不得用 `useId`、`useContext`、`useLayoutEffect`、`window.dispatchEvent`、`window.location`、`document`。
- T1 的 1–6 号文件（书斋、工作室共 6 个）不得新增 `cn` 或 `@/lib/utils` 导入，条件类名用模板字符串。
- `test_studio_kb_frontend.py:196-197` 会直接挂内层组件 `AccountKbWorkbench`，传 `{owner:'', embedded:false}`，并断言渲染出「请登录后打开导演知识库。」。所以内层新增的 prop 必须**可选，且默认 false**，默认时行为与现在完全相同。
- 新 hook 的 `identityRecoverySettled` 是模块级变量，只会从 false 变成 true。写新测试时：
  - 「用户名为空 → 确认中」的场景要单独放进一次 `probe()`（即新的 node 进程），在任何有用户名的渲染之前读取；
  - 或者在场景之间 `cache.clear()`，让模块重新求值。
  - 切换 `env.mode` 之后也必须 `cache.clear()`。

### 3.4 环境

- 沙箱是 workspace-write。
  - 跑 npm 前先 `export npm_config_cache=/tmp/fiona-npm-cache`；
  - `frontend/node_modules`（next 16.4.3）与 `backend/.venv` 已就位，不要重装。
- 沙箱里没有浏览器，§6 第 7 条由 Claude 用真实浏览器量。你负责两件事：
  - 把代码写对，把 §6 第 1–6 条跑绿；
  - 在报告里写明每条视觉判据对应的代码依据。
- 最多有 7 条既有测试依赖 git 历史。如果沙箱读不到主仓库的 `.git`，它们会被跳过：
  - `test_byok_image_tool.py` 中 4 条（:316、:342 各 2 条）；
  - `test_chat_image_tool.py` 中 1 条（:288）；
  - `test_chat_image_tool_docs.py` 中 1 条（:22，`test_r2_architecture_restores_complete_legacy_image_route`）；
  - `test_studio_casting_migration.py` 中 1 条（:203）。
  - 出现这种情况，在报告里照实写明跳过原因；Claude 会在沙箱外复跑全量，以 Claude 的结果为准。除此之外不得有任何跳过。
- 修改前端前先读 `frontend/AGENTS.md`。本单只用 React 客户端组件、`next/link`，以及原生的 `<details>` 和 `<input type="date">`。

## 4. 任务清单

### T1 身份确认中（10 处，P3-20）

**T1-1 新 hook（第一阶段单独完成，见 §9）。** 在 `frontend/lib/useAccountIdentity.ts` 里 `useAccountIdentity` 之后**追加**以下代码，逐字照抄，只可调整空行；已有代码一字不改：

```ts
// 身份是否还没确认：服务端渲染与水合首帧为 true；本地没有用户名、且本页第一次身份检查（ensureAccountIdentity）还没结束时也为 true。
// 第一次检查结束后不再回到确认中：另一个标签清掉本地用户名、而 Cookie 仍有效时，会先显示登录提示，等 auth.ts 用 Cookie 找回后再恢复。
// 测试替身只提供 useEffect / useSyncExternalStore 与 getUsername / ensureAccountIdentity，这里不能用别的。
let identityRecoverySettled = false;
const identityPendingListeners = new Set<() => void>();

function subscribeIdentityPending(onChange: () => void) {
  identityPendingListeners.add(onChange);
  const unsubscribeAccount = subscribeAccount(onChange);
  return () => {
    identityPendingListeners.delete(onChange);
    unsubscribeAccount();
  };
}

const clientIdentityPending = () => !getUsername() && !identityRecoverySettled;
const serverIdentityPending = () => true;

export function useAccountIdentityPending(): boolean {
  useEffect(() => {
    if (identityRecoverySettled) return;
    void ensureAccountIdentity().finally(() => {
      identityRecoverySettled = true;
      identityPendingListeners.forEach(listener => listener());
    });
  }, []);
  return useSyncExternalStore(subscribeIdentityPending, clientIdentityPending, serverIdentityPending);
}
```

**T1-2 十处接线。** 每处都按同一模式改：
1. 外层（调用 `useAccountIdentity()` 的组件）在那一行之后紧接着加 `const identityPending = useAccountIdentityPending();`，并把 `identityPending={identityPending}` 传给内层；导入改为 `import { useAccountIdentity, useAccountIdentityPending, … } from "@/lib/useAccountIdentity";`。
2. 内层的 props 增加 `identityPending = false`，类型写 `identityPending?: boolean`。交叉类型的，写进 `{ owner: string; identityPending?: boolean }` 那一侧。
3. 内层的登录分支 `!owner ? <原登录元素> : …` 改为 `!owner ? (identityPending ? <确认中元素> : <原登录元素>) : …`。原登录元素的文字、标签、类名一字不改，只按第 4 条给「前往登录」加 `target`。
4. 会被 iframe 嵌入、且带 `embedded` 的三处（NovelShelf、NovelWorkbench、StudioShelf），把原登录元素里的 `<Link href="/login" className="ml-2 underline">` 改为 `<Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">`。其余几处不改链接。

| # | 文件 | 外层 → 内层 | 原登录元素所在行 | 确认中元素 |
|---|---|---|---|---|
| 1 | `components/novel/NovelWizard.tsx` | `NovelWizard`(:40) → `Wizard`(:45) | :183 `<EmptyState>请登录后新建小说。</EmptyState>`（没有链接） | `<LoadingState>正在加载身份…</LoadingState>` |
| 2 | `components/novel/NovelShelf.tsx` | `NovelShelf`(:15) → `Shelf`(:20) | :64 `<EmptyState>请登录后查看你的书架。<Link …>前往登录</Link></EmptyState>` | 同上 |
| 3 | `components/novel/NovelWorkbench.tsx` | `NovelWorkbench`(:33) → `AccountWorkbench`(:38) | :275 `<EmptyState>请登录后打开你的书斋。<Link …>前往登录</Link></EmptyState>` | 同上 |
| 4 | `components/studio/StudioShelf.tsx` | `StudioShelf`(:17) → `Shelf`(:22) | :75 `<EmptyState>请登录后打开工作室。<Link …>前往登录</Link></EmptyState>` | 同上 |
| 5 | `components/studio/StudioWorkbench.tsx` | `StudioWorkbench`(:25) → `AccountStudioWorkbench`(:29) | :141 `<EmptyState>请登录后打开工作室。</EmptyState>` | 同上 |
| 6 | `components/studio/kb/KbWorkbench.tsx` | `KbWorkbench`(:30) → `AccountKbWorkbench`(:35) | :67 `<EmptyState>请登录后打开导演知识库。</EmptyState>` | 同上 |
| 7 | `components/MyAgentWorkspace.tsx` | `MyAgentWorkspace`(:21) → `MyAgentEditor`(:27) | :115 `<p className="text-sm text-muted-foreground" role="status">请登录后管理自己的分身。…</p>` | `<p className="text-sm text-muted-foreground" role="status">正在加载身份…</p>` |
| 8 | `components/AgentExchangeWorkspace.tsx` | `AgentExchangeWorkspace`(:25) → `ExchangeWorkspace`(:30) | :83 `<EmptyState>请登录后查看分身和自己的交流记录。…</EmptyState>` | `<LoadingState>正在加载身份…</LoadingState>`（用本文件 :484 的本地 LoadingState） |
| 9 | `components/AgentMemoryPanel.tsx` | `AgentMemoryPanel`(:22) → `AccountMemoryPanel`(:27) | :96 `<p className="text-xs text-muted-foreground" role="status">请登录后查看私有记忆。</p>` | `<p className="text-xs text-muted-foreground" role="status">正在加载身份…</p>` |
| 10 | `app/agents/[id]/page.tsx` | `AgentPageContent`(:14) → `AccountAgentCard`(:20) | :46 `<p role="status" className="text-sm text-muted-foreground">请登录后查看分身名片。…</p>` | `<p role="status" className="text-sm text-muted-foreground">正在加载身份…</p>` |

1–6 号文件已经从 `NovelStates` 导入了 `LoadingState`，不用新增导入。

### T2 书架嵌入标题与入口（P2-8）

1. `StudioShelf.tsx` 的标题与按钮：
   - `:69` 的 h1 改为 ``<h1 className={`text-[28px] tracking-[.24em]${embedded ? " sr-only" : ""}`}>短片工作室</h1>``；
   - `:70` 的按钮只把 className 改为 ``{`btn btn-primary min-h-10${embedded ? " ml-auto" : ""}`}``，条件、`type`、`onClick`、图标与文字都不动；
   - 外层 flex 行只在 className 开头加 `min-h-10`，改成 `<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">`，其余不动。
     （v1.2：嵌入时 h1 是 sr-only，不占高度，这一行的高度全靠按钮撑。按钮在工作室权限返回前后出没，下面的「在新页面打开」和额度条会跳 40px。加了 `min-h-10` 后行高恒不低于 40px；独立页的 h1 本来就高于 40px，不受影响。）
2. `NovelShelf.tsx:59`：把页眉的 `<Link href={newBookHref} className="btn btn-primary min-h-10"><Plus size={15} />新建一本</Link>` 原样包进 `{!(owner && !error && !loading && books.length === 0) && …}`。这样它只在空态卡出现时隐藏，加载中、出错、有书时照常显示。h1 和 `:64` 的空态卡不动；独立页与嵌入页一致。页眉这一行的 `<div className="flex flex-wrap items-center justify-between gap-3">` 改为 `<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">`。（v1.2：0 本书时页眉按钮隐藏、点「刷新」时又重新出现，嵌入时 h1 不占高度，不加 `min-h-10` 的话，说明文字、「刷新」和空态卡会跟着跳 40px。）
3. `NovelShelf.tsx:61` 的刷新按钮，`refresh` 的逻辑不动：
   - `disabled={loading}` 改为 `disabled={loading || !owner}`；
   - 文字 `{loading ? "刷新中…" : "刷新"}` 改为 `{loading && owner ? "刷新中…" : "刷新"}`；
   - 图标的 `animate-spin` 条件改为 `loading && owner`。

### T3 新对话开场与对话列表措辞（P2-10，`page.tsx` + `ConversationPicker.tsx`）

1. 在 `handleNewChat`（:1785）之后新增三个**普通箭头函数**（不要用 `useCallback`）：
   ```tsx
   const startChatOpener = () => {
     if (conversationLocked || conversationLoading || !currentConversation || imageMode || hasReferenceImages || !!input.trim()) return;
     composeSongSection("聊聊今天");
   };
   const startDrawOpener = () => {
     if (pendingImage || isReadingImage || isReadingReferences || conversationLocked || conversationLoading || !currentConversation || imageMode || hasReferenceImages) return;
     setImageMode(true);
     requestAnimationFrame(() => textareaRef.current?.focus());
   };
   const startPhotoOpener = () => {
     if (imageMode || hasReferenceImages || isReadingImage || isReadingReferences || isLoading || conversationLoading || !currentConversation) return;
     fileInputRef.current?.click();
   };
   ```
   三个函数体内不得出现 `handleSend`、`handleSendRef`、`apiFetch`、`fetch(`。
2. 把 :2596-2598 换成：
   ```tsx
   {messages.length === 0 && (conversationLoading || conversationError || !currentConversation ? (
     <p className="text-xs text-muted-foreground text-center pt-8" role="status">{conversationLoading ? "正在加载对话…" : conversationError ? "对话加载失败，请在对话列表里重试。" : "在对话列表里点「新建」，开始和自己的分身交流。"}</p>
   ) : (
     <div data-chat-openers className="flex flex-col items-center gap-4 pt-8 text-center max-md:pt-4">
       <p className="text-[15px] leading-[1.85] text-[color:var(--ink2)]" role="status">{`和 ${agent?.display_name || "你的分身"} 开始新的交流。`}</p>
       <div role="group" aria-label="开场" className="flex flex-wrap justify-center gap-2">
         <button type="button" className="chip min-h-10" disabled={conversationLocked || conversationLoading || !currentConversation || imageMode || hasReferenceImages || !!input.trim()} onClick={startChatOpener}>聊聊今天</button>
         <button type="button" className="chip min-h-10" disabled={!!pendingImage || isReadingImage || isReadingReferences || conversationLocked || conversationLoading || !currentConversation || imageMode || hasReferenceImages} onClick={startDrawOpener}>帮我画一张…</button>
         <button type="button" className="chip min-h-10" disabled={imageMode || hasReferenceImages || isReadingImage || isReadingReferences || isLoading || conversationLoading || !currentConversation} onClick={startPhotoOpener}>看看我拍的这张图</button>
       </div>
     </div>
   ))}
   ```
3. `handleKeyDown`（:2221）只在 `e.preventDefault();` 与 `handleSend();` 之间插入一行 `if (e.repeat) return;`，其余行一字不动。改完的函数体恰为：
   ```tsx
   const handleKeyDown = (e: React.KeyboardEvent) => {
     if (e.key !== "Enter" || e.shiftKey) return;
     // Use ref for IME composing state — more reliable than e.nativeEvent.isComposing
     if (isComposingRef.current) return;
     e.preventDefault();
     if (e.repeat) return;
     handleSend();
   };
   ```
   按住 Enter 时，第一下照常发送；之后的自动重复仍被 `preventDefault()` 拦下，不往输入框插换行，但不再发送。按住 Shift+Enter 照常连续换行；输入法组字时的 Enter 照常交给输入法。
   （v1.2：v1.1 把这一行放在函数体第一行、排在 `preventDefault()` 之前，自动重复会往输入框里插空行。实测打字后按住 Enter，消息发出后输入框里留下 4 个换行；HEAD 上为空。这是 v1.2 修正的回归。）
4. `page.tsx:962` 的注释改为 `// 轻点录音：再点一下停止，识别后直接发送（不填进输入框）`。
5. `ConversationPicker.tsx:91`：「还没有对话。点「新对话」，开始和自己的分身交流。」改为「还没有对话。点「新建」，开始和自己的分身交流。」，该行其余部分不动。

### T4 匹配页空态（P2-10，`match/page.tsx`）

1. 新增导入 `import Link from "next/link";`。
2. 左栏 `:323` 改为 `<p className="text-xs text-[color:var(--ink2)]">双方都接受匹配后，对方会出现在这里</p>`。
3. 右侧 `:347` 的 `{pendingMatches.length === 0 ? null : (` 里的 `null` 换成：
   ```tsx
   <section data-match-empty className="relative z-[1] mx-auto max-h-full max-w-[520px] overflow-y-auto px-6 pb-6 pt-10 text-[13px] leading-[1.85] text-[color:var(--ink2)] mobile:px-1 mobile:pt-2">
     <h2 className="text-[15px] font-medium tracking-[.16em] text-[color:var(--ink)]">匹配是什么</h2>
     {rooms.length > 0 && <p className="mt-3">从「最近聊天」选一位，就能继续和对方聊天。</p>}
     <p className="mt-3">这是旧版的真人连接：系统曾根据对话和社交画像（旧版），推荐可能聊得来的人。推荐卡约 25 秒后淡出，淡出后不会再出现。</p>
     <p className="mt-2">在卡片上点「认识下」，再点「发送打招呼」（招呼可以不写）。双方都这样做之后，对方会出现在「最近聊天」里。</p>
     <p className="mt-2">新的对话不会再产生推荐，所以这里可能一直是空的。</p>
     <p className="mt-2">也可以公开分身名片，再到「广场」邀请其他用户的公开分身交流：对方接受后，两个 AI 分身轮流对话并生成总结，不会建立真人聊天。公开后，其他已登录用户能看到分身的名称、头像和简介，也能邀请你的分身交流。</p>
     <Link href="/agents/me" target={embedded ? "_top" : undefined} className="btn mt-4 min-h-10 px-[18px] mobile:h-auto mobile:max-w-full mobile:whitespace-normal">查看公开名片设置</Link>
   </section>
   ```
   新增文案里不得出现「匿名」「不知道你是谁」「Skill」「自动交流」「左侧」。`:74` 的注释不动。

### T5 画像页改名（P2-10，`profile/page.tsx` + 三份文档 + 一行测试）

1. `profile/page.tsx`：
   - `:98` h1 的文字「旧社交画像」改为「社交画像（旧版）」，开标签与类名不动；
   - `:121`「暂无旧社交画像」改为「暂无社交画像（旧版）」；
   - `:136` 整句改为「这里保留社交画像（旧版），不展示新会话的私有记忆。你可以在“我的分身”中查看新记忆；那里的「清空记忆与个人画像」会一并清空这份社交画像（旧版），聊天记录会保留。」，`<p>` 标签与类名不动；
   - 改完后 frontend 里「旧社交画像」为 0 处。
2. 文档各改一处，该行其余文字不动：
   - `README.md:11`：「独立于旧社交画像保存」改为「独立于社交画像（旧版）保存」；
   - `PLAN.md:54`：「独立于旧社交画像；」改为「独立于社交画像（旧版）；」；
   - `docs/ARCHITECTURE.md:126`：「| 旧社交画像；新私有记忆在分身页管理 |」改为「| 社交画像（旧版）；新私有记忆在分身页管理 |」；
   - 写作「旧社会画像」的其他文档不改。
3. `backend/tests/test_ui_polish_settings_drawers.py:83`：把 `assert_heading_hides_when_embedded(PROFILE, "旧社交画像")` 改为 `assert_heading_hides_when_embedded(PROFILE, "社交画像（旧版）")`。这是本单**唯一**允许的既有测试改动，只改这一行里的这一个字符串。

### T6 设置页隐私说明（P2-11，`ChatModelSection.tsx`）

1. 把第一段 `<p>启用后，聊天回复会把分身设定、…账号名替换为「（账号已隐藏）」。</p>`（:369）**剪切**到第二个 `fieldset` 里、「启用我的聊天模型」开关块（:345 的 `<div className="border-t …">`）的**前面**，写成 `<p className={noteClass}>启用后，…</p>`，文字一字不改。
2. 紧接在第一段之后，新增一行只在选 Claude 时显示的说明：
   `{provider.id === "anthropic" && <p className={noteClass}>已选 Claude：你在聊天里发的图片和工具结果也会发送给 Anthropic，详见下方「更多隐私与计费说明」。</p>}`
   （v1.2：v1.1 写的是「本轮图片」，放在设置页里「本轮」没有指代对象。）
3. `:358` 的开关说明里，`!config` 分支的「先保存配置，才能启用。」改为「首次保存后会直接启用；之后可以用这个开关停用或重新启用。」，其余两个分支不动。
4. 把 :368 的外层 `<div className={`${noteClass} space-y-2 border-t …`}>` 换成：
   ```tsx
   <details className={`${noteClass} border-t border-[color:var(--carve)] pt-3 shadow-[inset_0_1px_0_var(--etch)]`}>
     <summary className="min-h-10 cursor-pointer py-2 text-sm tracking-[0.06em] text-[color:var(--ink)]">更多隐私与计费说明</summary>
     <div className="space-y-2 pt-1">
       {/* 其余 7 段原样剪切粘贴到这里，顺序不变 */}
     </div>
   </details>
   ```
   - 其余 7 段（危机复核、生图、选 Claude 时、自带模型文字聊天、Key 加密保存、开启『聊天读小说』、Claude 的接口不对中国大陆）保持原文、原顺序，仍各为一行、不带属性的 `<p>`；
   - :377 的 `</div>` 相应改为 `</div></details>`。
5. 默认收起，不写 `open`。不改 `noteClass`，不改思考强度组，不改 `settings/page.tsx`；两个 `fieldset` 除第 1–3 条之外不动。

### T7 历史页日期筛选（P3-19，`history/page.tsx`）

1. `:15` 的 `@/lib/beijingTime` 导入里加上 `formatBeijingDateLong`，原有的名字都保留。
2. 在 `HistoryForAccount`（:34）里、`applyQuick`（:66）附近新增两个函数：
   ```tsx
   const openDatePicker = (input: HTMLInputElement) => {
     try { input.showPicker(); } catch { /* 浏览器不支持或拒绝时，沿用原生点按 */ }
   };
   const dayFace = (key: string) => (key ? formatBeijingDateLong(beijingDayStart(key)) || key : "不限");
   ```
   （v1.2：值非空但不是合法的四位年份日期时，直接显示原值，不显示「不限」。v1.1 的写法在键入出 5 位年份（如 `61027-02-02`）时显示「不限」，筛选却已生效、列表被筛空，用户看不出原因。）
3. 日期块怎么改：
   - `:211` 外层容器开标签的 className 换成 `grid grid-cols-1 gap-1.5`；
   - 只把 `:212-226`（两个输入框和中间的「至」）换成两枚 chip；
   - `:207-210` 的「自定义区间」标题、`:227-234` 的「清除筛选」按钮和 `:235` 的 `</div>` 都不动。
   - 「从」这一枚：
   ```tsx
   <label className={cn("chip relative h-auto min-h-10 w-full justify-between gap-2 px-3 py-1.5 has-[:focus-visible]:outline has-[:focus-visible]:outline-1 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[color:var(--ink)]", dateFrom && "chip-on")}>
     <span aria-hidden="true">从</span>
     <span aria-hidden="true" className="readout text-[13px] text-[color:var(--ink)]">{dayFace(dateFrom)}</span>
     <input type="date" aria-label="从（开始日期）" value={dateFrom} max={dateTo || "9999-12-31"}
       onChange={e => { setDateFrom(e.target.value); setQuick("all"); }}
       onClick={e => openDatePicker(e.currentTarget)}
       onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDatePicker(e.currentTarget); } }}
       className="absolute inset-0 h-full w-full cursor-pointer opacity-0" />
   </label>
   ```
   - 「到」这一枚照此写，只换这几处：`<span aria-hidden="true">到</span>`、`aria-label="到（结束日期）"`、`value={dateTo}`、把 `max={dateTo || "9999-12-31"}` 换成 `min={dateFrom || undefined} max="9999-12-31"`、`setDateTo`、`dateTo && "chip-on"`、`{dayFace(dateTo)}`。
   - （v1.2：可见标签「从」「到」是 aria-hidden 的，可访问名称必须包含它们，否则语音控制说「点按 从」找不到控件（WCAG 2.5.3），所以 aria-label 写成「从（开始日期）」「到（结束日期）」。两个框都兜一个 `max="9999-12-31"`，年份最多 4 位。）
4. `:194` 的「全部」高亮条件改为 `quick === key && (key !== "all" || (!dateFrom && !dateTo))`。
5. `:272` 的 `{dateFrom || "—"} 至 {dateTo || "—"}` 改为 `{dayFace(dateFrom)} 至 {dayFace(dateTo)}`。

### T8 语音按钮手机状态气泡（P3-21，`VoiceButton.tsx`）

在根元素 `<div className="relative inline-flex">` 里，放在现有首次提示 `{showHint && (…)}`（:145-149）之后、`<button`（:150）之前，**新增**下面一个元素，其余代码一字不改：

```tsx
{!showHint && (holding || dictating) && (
  <span data-voice-status aria-hidden="true" className="ceramic-card pointer-events-none absolute bottom-full right-0 z-[60] mb-2 whitespace-nowrap px-3 py-2 text-xs leading-relaxed text-[color:var(--ink)] md:hidden">
    {holding ? "松开发送" : "再点一下发送"}
  </span>
)}
```

### T9 新测试（9 个文件，按文件归属分给各 agent）

总则：
- 全部离线、不依赖 git 历史、不读仓库外文件。
- 需要 node + typescript / react 的用例，照 `test_claude_agent_frontend.py:136-155` 的写法探测，缺失时 `pytest.skip`。本机依赖齐全，门禁要求 0 skipped。
- **每个新 `test_` 函数至少含一条在 HEAD 上会失败的断言**。Claude 会把新测试拿到 HEAD 上跑一遍，作正控。「仍…」「不含…」这类回归护栏允许在 HEAD 上通过，但必须和至少一条在 HEAD 上失败的断言写在同一个函数里，不得单独成函数。
- 可以只读复用既有驱动，例如 `from test_novel_p2_r1 import DRIVER`、`from test_studio_frontend_shell import probe, SETUP`、`from test_studio_kb_frontend import …`、`from test_ui_polish_settings_drawers import assert_heading_hides_when_embedded`。不得修改任何既有测试文件（T5 第 3 条除外）。
- 涉及新 hook 的行为用例，要遵守 §3.3 最后一条：模块级状态只能从 false 变成 true，所以不同场景要分开进程，或在场景之间 `cache.clear()`。

各文件：
1. `test_empty_states_identity.py`（agent A，只测 hook 本身）：
   - 源码：`useAccountIdentity.ts` 导出 `useAccountIdentityPending`；新代码不含 `useId`、`dispatchEvent`、`location`、`document`；原有 `return useSyncExternalStore(subscribeAccount, getUsername, serverIdentity);` 与 `import { ensureAccountIdentity, getUsername } from "@/lib/auth";` 原样在。
   - 行为：用 node 转译 `useAccountIdentity.ts`，自写 React 替身，以及可控的 auth 替身（`ensureAccountIdentity` 返回一个由测试控制何时落定的 promise）。每个场景新建一次模块，验证：
     - 服务端快照为 true；
     - 客户端、用户名为空、找回尚未落定时为 true；
     - 找回落定（等到微任务跑完）后为 false，且订阅回调被调用过；
     - 有用户名时为 false。
2. `test_empty_states_novel.py`（agent B，只断言 3 个书斋文件）：
   - 用 `test_novel_p2_r1.DRIVER` 的 `screen()`。造 0 本书的写法：`const o=agents.apiJson;agents.apiJson=async(u,i)=>u==='/api/novels'?[]:o(u,i);`。
   - 有用户名、0 本书时渲染 `NovelShelf`：树里 `href` 含 `/novels/new` 的 Link 元素恰好 1 个（HEAD 上是 2 个）。
   - 用户名为空的场景放进**单独一次** `probe()`：外层传给内层的 `identityPending` 为 true；树里有「正在加载身份…」，没有「请登录后查看你的书架」；刷新按钮的文字是「刷新」，且处于 disabled。
   - 源码：
     - NovelShelf、NovelWorkbench 两处「前往登录」带 `target={embedded ? "_top" : undefined}`；
     - 三个文件各有 `useAccountIdentityPending()`、`identityPending={identityPending}`、`identityPending = false`；
     - 「正在加载身份…」在原登录文案之前，原登录文案仍恰好 1 次；
     - `loading && owner ? "刷新中…"` 与 `loading && owner ? "animate-spin"` 都在。
3. `test_empty_states_studio.py`（agent C，只断言 3 个工作室文件）：
   - 调用 `assert_heading_hides_when_embedded(StudioShelf.tsx 的路径, "短片工作室")`，这条在 HEAD 上会失败。
   - 用 `test_studio_frontend_shell` 的 `probe` / `SETUP`，在 `env.search='embed=1'` 下 `screen('components/studio/StudioShelf.tsx')`：「新建项目」仍是 `button`，且 className 含 `ml-auto`。
   - 用 `test_studio_kb_frontend` 的驱动，在 `env.mode='ssr'` 下渲染 `app/studio/page.tsx`（切换模式后 `cache.clear()`）：输出含「正在加载身份…」，不含「请登录后打开工作室。」（HEAD 上相反）。
   - 源码：三个文件的接线三件套（同第 2 条）；StudioShelf 的「前往登录」带 `target`。
4. `test_empty_states_agents.py`（agent D，只断言 4 个分身文件）：
   - 源码：4 个文件各自的接线三件套，以及「正在加载身份…」在原登录文案之前，原登录文案仍恰好 1 次。
   - `AgentExchangeWorkspace.tsx` 的确认中元素用的是本地 `LoadingState`。
5. `test_empty_states_chat_openers.py`（agent E）：
   - 源码：有 `data-chat-openers`；三个开场文案在；`startChatOpener`、`startDrawOpener`、`startPhotoOpener` 各被一个 `onClick` 引用。
   - 三个函数体（从 `const startChatOpener` 等切到它之后第一个 `\n  };`）不含 `handleSend`、`apiFetch`、`fetch(`；`startChatOpener` 的守卫和「聊聊今天」的 disabled 都含 `!!input.trim()`。
   - `handleKeyDown`：从 `const handleKeyDown = (e: React.KeyboardEvent) => {` 这一行起，到它之后第一个内容为 `};` 的行（两头都含）止，逐行去掉首尾空白后，恰为 T3-3 代码块里的 8 行。另见 §10 的加固要求。
   - 全文仍无 `onClick={() => setImageMode(true)}`，`type="file"` 仍恰好 2 处。
   - 新文案：page.tsx 有「在对话列表里点「新建」，开始和自己的分身交流。」「对话加载失败，请在对话列表里重试。」，不再有完整字面量 `点击上方“新对话”`（弯引号 U+201C / U+201D）和 `请在上方重试`；ConversationPicker.tsx 有「点「新建」，开始和自己的分身交流。」，不再有 `点「新对话」`。
   - 不要只截取「新对话」两字去断言：`ConversationPicker.tsx:56、:73` 里还有合法的「新对话」。
6. `test_empty_states_match_profile.py`（agent F）：
   - 匹配页的检查，只在 `<section data-match-empty` 到它之后第一个 `</section>` 的切片里做：
     - 切片存在；
     - 含「匹配是什么」「发送打招呼」「查看公开名片设置」「不会建立真人聊天」、`href="/agents/me"`、`target={embedded ? "_top" : undefined}`；
     - 不含「匿名」「不知道你是谁」「Skill」「自动交流」「左侧」。
   - 匹配页的整文件检查：`max-md:` 0 处；无粗体写法；左栏新文案在，旧的 `text-[11px] text-muted-foreground">接受匹配后会出现在这里` 不在；`{/* 匿名头像 */}` 仍恰好 1 处。
   - 画像页：「旧社交画像」0 处；「社交画像（旧版）」不少于 3 处；`:136` 的新整句在；`.join("、")` 仍在。
   - 文档：`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md` 不含「旧社交画像」，各至少含 1 处「社交画像（旧版）」（v1.2：不要求恰好 1 处，免得以后文档再提到它时无关地变红）。
7. `test_empty_states_settings_privacy.py`（agent G）：
   - 位置：源码里有 `<details`，且位于第二个 `</fieldset>` 之后；被锁的三段都在 `<details` 与 `</details>` 之间。
   - 第一段「启用后，聊天回复会把分身设定」在 `<details` 之外，并且出现在「启用我的聊天模型」和「保存」按钮那行之前。
   - 文案：
     - 8 段各恰好 1 次；
     - summary 文案是「更多隐私与计费说明」；
     - `provider.id === "anthropic" &&` 那行说明在；
     - 「首次保存后会直接启用」在，「先保存配置，才能启用。」不在；
     - 无粗体写法。
8. `test_empty_states_history_dates.py`（agent H）：
   - `showPicker(` 全文件恰 1 处，且在 `try {` 内；`openDatePicker(e.currentTarget)` 恰 4 处；`max={dateTo || "9999-12-31"}`、`min={dateFrom || undefined} max="9999-12-31"` 都在。
   - 两个 `aria-label` 恰为 `aria-label="从（开始日期）"`、`aria-label="到（结束日期）"`，各 1 处。
   - 含「不限」与 `formatBeijingDateLong(`；含 `has-[:focus-visible]:outline`。
   - 不再有 `text-[10px] text-muted-foreground">至<`；「全部」的高亮条件含 `!dateFrom && !dateTo`。
   - 仍含 `@/lib/beijingTime` 与 `formatBeijingTime(`；新代码里没有设备时区 API。
9. `test_empty_states_voice_hint.py`（agent I）：
   - 用真实 React 做 SSR，照 `test_ui_polish_composer_controls.py` 的 `MENU_SSR_RUNNER` 写法，逐字替换 `cn` 那一行导入。用 `re.search(r'<span data-voice-status[^>]*>([^<]*)</span>', html)` 取出新元素再断言：
     - holding 态取到的文字恰好是「松开发送」；
     - dictating 态恰好是「再点一下发送」；
     - 空闲态取不到。
   - 再照 `test_ui_polish_fix_r2_controls.py` 的 `OPEN_MENU_RUNNER`，在同一个函数里渲染两次：
     - 第一次 `useState` 返回 `[false, …]`、holding 为 true：取得到新元素（HEAD 上取不到）；
     - 第二次 `useState` 返回 `[true, …]`、holding 为 true：取不到。
   - 源码检查只在新元素的开标签上做：含 `aria-hidden="true"`、`pointer-events-none`，以及用 `(?<![\w-])md:hidden` 匹配到的 `md:hidden`。
   - `try {` 仍恰好 1 处。

### T10 报告 `03-report.md`

见 §7。

## 5. 不允许的做法

- 改任何既有测试（T5 第 3 条那一行除外）、夹具或测试辅助模块；为了让测试通过去改 §3.2 的保留项。
- 新增依赖；改 `lib/auth.ts`；在共享 hook 里用 §3.3 禁止的 API；除 agent A 之外的任何人修改 `lib/useAccountIdentity.ts`。
- 开场按钮调用 `handleSend` 或发出任何请求、自动发送；在开场旁边重复费用文案；给开场 chip 加图标。
- 改 `handleSend`、`ChatScrollArea`、`ComposerImageMenu`、图片菜单 `items`；改 `handleKeyDown` 除「在 `e.preventDefault();` 与 `handleSend();` 之间插入 `if (e.repeat) return;`」以外的任何内容。
- 用 `display:none` 或条件渲染去掉工作室嵌入态的「新建项目」按钮；改 `app/novels/page.tsx`；改 `match/page.tsx:74` 的注释。
- 删除或改写被锁隐私段落的文字；给被锁的三段 `<p>` 加属性或拆行。
- 改 `VoiceButton.tsx` 的任何现有行。
- 新增粗体；新写带「·」的文案；在被嵌入的页面写 `max-md:`。
- 白名单外的任何文件改动。

## 6. 验收标准（Claude 逐条复跑，以 Claude 结果为准）

在仓库根执行（第 1–6 条你必须自己跑绿并写进报告）：

1. `cd frontend && npx tsc --noEmit` → 0。
2. `cd frontend && npm run lint` → 0 errors，warnings ≤ 25（HEAD 为 25）。
3. `cd frontend && npm run build` → 0。
4. `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` → **全量**，0 failed，0 skipped（§3.4 的 git 历史例外除外），passed ≥ 7774 + 新增用例数（既有 7774 条一条不少）。
5. 结构判据（Claude 用 `verify/gate.sh` 跑，括号内为 HEAD 基线）：
   - `grep -rn '旧社交画像' frontend/app frontend/components README.md PLAN.md docs/ARCHITECTURE.md | wc -l` = 0（6）。正控：同一组路径里「社交画像（旧版）」不少于 6 处（0）。
   - `git diff --numstat HEAD -- backend/tests/`：既有文件里只出现 `test_ui_polish_settings_drawers.py`，且为 1 增 1 删。
   - 在 `frontend/app`、`frontend/components` 下含 `useAccountIdentityPending()` 的文件 = 10（0）。
   - `grep -rho 'aria-label=' frontend/app frontend/components --include='*.tsx' | wc -l` ≥ 118（118）。
   - `page.tsx`：`onClick={() => setImageMode(true)}` = 0；`type="file"` = 2。
   - diff 新增的行里，`font-semibold`、`font-bold`、`fontWeight`、`<strong` 合计 0；「·」0。
6. 改动集合：`git status --porcelain --untracked-files=all` 只出现 §3.1 白名单路径与本规格目录。
7. 真实浏览器（Claude 在隔离实例里量，昼 / 夜 × 1440×900 / 390×844；【改】表示 HEAD 上应失败，【回归】表示 HEAD 上也应通过）：
   - P3-20：
     - 【改】带有效 Cookie 时，`/novels/new`、`/novels`、`/studio` 服务端渲染的原始 HTML 含「正在加载身份…」、不含「请登录后」；前端脚本晚到 3 秒时，1 秒和 2.5 秒的可见文字是「正在加载身份…」。
     - 【改】本地无用户名、`/api/profile` 慢 4 秒：1 秒和 2.5 秒显示「正在加载身份…」，8 秒时出现向导。
     - 【回归】`/api/profile` 返回 500：8 秒时显示「请登录后新建小说。」（已知局限，见 §1）。
     - 【回归】小说功能关闭时，恰好 1 个「小说工坊尚未开放」。
   - P2-8：
     - 【改】工作室抽屉里的 h1「短片工作室」宽高 ≤ 1px，读屏仍能读到；「新建项目」右边缘贴齐所在行。
     - 【回归】独立页 `/studio` 的 h1 可见。
     - 【改】书斋有 0 本书时，可见的「新建一本」恰好 1 个，且在空态卡里。
     - 【回归】（v1.2）嵌入书斋有 0 本书时，说明文字「留一个故事思路…」的位置在加载中、加载完、点「刷新」后都不变；嵌入工作室的「在新页面打开」在权限返回前后位置不变（HEAD 上本来不变，v1.1 会跳 40px）。
   - P2-10 开场：
     - 【改】新对话里有 3 个可点的开场，位于页头之下、输入釉片之上。
     - 【改】逐个点击，前后 3 秒内 `/api/**` 的非 GET 请求为 0；在「聊聊今天」上按住 Enter 1.2 秒，非 GET 请求也为 0。计数器先在 HEAD 上做正控：打字、回车、拦截 `/api/chat`，应数到 1。
     - 【改】点「聊聊今天」后输入框里是「聊聊今天」并获得焦点；点「帮我画一张…」后出现「生成图片」模式；点「看看我拍的这张图」会触发选择文件。
     - 【改】（v1.2）在「聊聊今天」上按住 Enter 后，输入框恰为「聊聊今天」，不留空行。
     - 【回归】（v1.2）打字后按住 Enter：`/api/chat` 只发 1 次，松开后输入框为空（HEAD 上也如此，v1.1 会留下空行）。
   - P2-10 匹配与画像：
     - 【改】匹配页右侧未选中区有「匹配是什么」和「查看公开名片设置」；左栏文字 ≥ 12px。
     - 【改】设置抽屉「账户」页的可见文字里，「旧社交画像」0 次。
     - 【改】（v1.2）820×360 的窗口里，匹配页说明区滚到底后「查看公开名片设置」完整可见。
   - P2-11：
     - 【改】「聊天模型」一节的 details 默认收起；第一段可见，且在「保存」之上；其余 7 段不可见。
     - 【回归】展开后，8 段文字与 HEAD 逐字相同。
     - 【改】手机上 summary 高 ≥ 40。
   - P3-19：
     - 【改】两个日期输入仍能用「开始日期 / 结束日期」找到，也能用可见标签「从」「到」找到，但不可见；chip 上只显示「从 / 到 / 不限 / YYYY年M月D日」；值非空但无法解析时显示原值，不显示「不限」。
     - 【改】`en-US` 与 `zh-CN` 两种上下文显示相同。
     - 【改】点 chip 会调用 `showPicker`；填入 `2026-10-27` 后显示「2026年10月27日」；只设「到」时「全部」不高亮。
   - P3-21：
     - 【改】390 宽按住语音键时，按钮上方能看到「松开发送」气泡，松开后消失。
     - 【回归】1440 宽不出现这个气泡。
   - 截图：书斋空态、新对话开场、匹配页、设置页折叠块、历史页日期 chip，昼 / 夜各一张。

## 7. 交付：变更总结（写进 `03-report.md`）

1. 修改 / 新增文件清单。
2. 实现了什么。
3. 与 T1–T9 逐项对应。
4. §6 第 1–6 条的实际结果：第 4 条写 passed / skipped 数，第 5 条逐条写实际值。
5. 未完成或需人工确认的地方，主动偏离及理由，以及 §6 第 7 条每项对应的代码依据。
6. 已知局限（照实写，不要写成已修复）：
   - 身份找回失败（500、断网）时仍显示原登录文案；
   - 生图或改图模式下，语音松开或再点一下会直接触发付费生成，气泡仍写「发送」，三种状态的说法也略有不同；
   - 「查看公开名片设置」在抽屉里会让整页跳到 `/agents/me`，未发送的草稿会丢；
   - 已启用自带模型、但不是 Claude 的用户发图时，走平台看图并扣草莓，底栏没有提示。

报告开头列 agent 拆分表，如实列出全部派出过的 agent。

## 8. 何时停下来问

只在影响「实现什么」时停下来问：
- 不改 §3.2 的保留项就做不到某项任务；
- 某个既有测试在你的改动下变红，而照本规格的写法无法让它保持绿；
- 你实测到的事实与本规格不符：以实测为准，先停下来说明。

只影响「怎么实现 / 怎么验证」的，自行决定并写进报告。任何情况下不回滚已完成的工作。

## 9. 执行方式（两阶段）

**第一阶段（串行）**：先单独派 agent A，完成 T1-1 与 `test_empty_states_identity.py`，并跑通它。主代理确认 `lib/useAccountIdentity.ts` 已导出 `useAccountIdentityPending`、新测试全绿，才进入第二阶段。

**第二阶段（并行）**：用工作流（`workflow` 工具），在脚本里用 `parallel()` 同时跑以下 agent，按文件不重叠拆分：
- agent B：`NovelWizard.tsx`、`NovelShelf.tsx`、`NovelWorkbench.tsx`（T1-2 的 1–3、T2 的第 2–3 条）+ `test_empty_states_novel.py`；
- agent C：`StudioShelf.tsx`、`StudioWorkbench.tsx`、`kb/KbWorkbench.tsx`（T1-2 的 4–6、T2 的第 1 条）+ `test_empty_states_studio.py`；
- agent D：`MyAgentWorkspace.tsx`、`AgentExchangeWorkspace.tsx`、`AgentMemoryPanel.tsx`、`app/agents/[id]/page.tsx`（T1-2 的 7–10）+ `test_empty_states_agents.py`；
- agent E：`app/page.tsx`、`ConversationPicker.tsx`（T3）+ `test_empty_states_chat_openers.py`；
- agent F：`match/page.tsx`、`profile/page.tsx`、`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`test_ui_polish_settings_drawers.py` 第 83 行（T4、T5）+ `test_empty_states_match_profile.py`；
- agent G：`ChatModelSection.tsx`（T6）+ `test_empty_states_settings_privacy.py`；
- agent H：`history/page.tsx`（T7）+ `test_empty_states_history_dates.py`；
- agent I：`VoiceButton.tsx`（T8）+ `test_empty_states_voice_hint.py`。

每个 agent 的任务说明必须自包含：把本规格里与它相关的 §2、§3、§4 原文抄进去，并写明以下几点：
1. 不得调用 subagent / subagent_fork / workflow。
2. `lib/useAccountIdentity.ts` 已由第一阶段完成，可以直接 import，不得修改；`test_ui_polish_settings_drawers.py` 第 83 行只由 agent F 修改。
3. 所有 agent 在同一个工作树里并发修改互不重叠的文件，别人的文件可能处于半成品状态。接口以本规格为准，不要读别人的文件来推断接口，也不要去改它们。
4. 共享测试文件（例如 `test_component_language.py`）里断言别人文件的用例，可能因对方没写完而暂时变红。不要代修，只跑与自己文件相关的测试。

全部完成后，主代理跑 §6 第 1–6 条。主代理只做拆分、派发、汇总、白名单检查、门禁和报告。报告开头列拆分表，如实列出全部派出过的 agent。

## 10. v1.2 修订（返修 R1）

v1.1 实施后，独立复核（千问 3.8 Max、Claude 三个视角）与 Claude 的真实浏览器实测发现下列问题。前四条是相对 HEAD 的界面回归，用 HEAD 作对照实测确认过；第 5–7 条是小改；第 8 条是新测试加固：v1.1 的新测试拦不住的几类错误实现，要补上能区分它们的断言。

1. **按住 Enter 往输入框插空行**：T3-3 的 `if (e.repeat) return;` 挪到 `e.preventDefault();` 之后（见 T3-3）。
2. **嵌入抽屉页眉跳 40px**：书斋、工作室页眉行加 `min-h-10`（见 T2-1、T2-2）。
3. **日期面静默写「不限」**：`dayFace` 对无法解析的值显示原值；两个日期框都加 `max="9999-12-31"`（见 T7-2、T7-3）。
4. **矮屏下匹配页按钮被裁**：说明区的上边距从外边距改为内边距（`mt-10` → `pt-10`，`mobile:mt-2` → `mobile:pt-2`，见 T4-3）。
5. 日期框的可访问名称带上可见标签：`aria-label="从（开始日期）"` / `aria-label="到（结束日期）"`（见 T7-3）。
6. Claude 提示句「本轮图片」改为「你在聊天里发的图片」（见 T6-2）。
7. `useAccountIdentity.ts` 新代码的第一行注释改为 T1-1 代码块里的两行；代码不变。改完后 T1-1 的整段仍要逐字一致。
8. **新测试加固**（只改 `backend/tests/test_empty_states_*.py`，既有测试仍一字不改）：
   1. identity：新增「找回失败」场景。用户名保持空串，让 `ensureAccountIdentity` 以空串落定。替身的订阅回调里同步调用一次 `getSnapshot()` 并记录结果，模拟 React 在 store 变化时重读快照。断言：
      - 通知时记录到的快照为 false；
      - 落定后再取快照仍为 false；
      - 订阅回调至少被调用 1 次。

      这条必须能拦住两种错误实现：快照只看 `!getUsername()`、不看落定标志；先通知所有订阅者、再置位落定标志。
   2. novel：
      - 0 本书时，剩下的那个 `/novels/new` 入口必须是空态卡（`Glaze` 或 `EmptyState` 节点）的后代，`<header>` 子树里没有 href 含 `/novels/new` 的元素。
      - 另用有书的默认数据、以及 `env.failures.set('GET /api/novels', …)` 造的出错状态各渲染一次，断言 `<header>` 子树里恰有 1 个 `/novels/new` 入口。
      - 身份确认中场景：外层传给内层的 `identityPending` 在 mount 之后、flush 之前读取，应为 true。flush（找回以空串落定）之后重新挂载一次外层：`identityPending` 为 false，内层出现「请登录后查看你的书架」，嵌入时「前往登录」的 `target` 为 `_top`。
      - 源码里 `<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">` 恰 1 处。
   3. 接线结构（novel、studio、agents 三个测试文件）：10 个文件，每个都要断言 `!owner ? (identityPending ? <确认中元素> : <原登录元素>)` 这一整段子串在源码里。
      - 确认中元素：书斋与工作室的 6 个文件是 `<LoadingState>正在加载身份…</LoadingState>`；分身的 4 个文件按各自现状照抄。
      - 原登录元素照抄现状，嵌入页含 `target={embedded ? "_top" : undefined}`。
      - 子串从当前源码里原样复制，不要自己改写。
   4. studio：
      - StudioShelf 的 `<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">` 恰 1 处。
      - 非嵌入态渲染一次 StudioShelf，「新建项目」button 的 className 不含 `ml-auto`。
      - 挂载 `AccountStudioWorkbench`（`{id:'project', owner:'', embedded:false, identityPending:true}`）和 `AccountKbWorkbench`（`{owner:'', embedded:false, identityPending:true}`），断言输出含「正在加载身份…」、不含「请登录后」。
   5. chat_openers：
      - 按 T9-5 新条目断言 `handleKeyDown` 的 8 行。
      - 三个开场函数各自从 `const startXxx = () => {` 起，到它之后第一个内容为 `};` 的行（含）止，把连续空白压成一个空格后，与 T3-1 代码块里对应的函数同样处理后全等。
      - 三个开场 `<button …>…</button>` 各自压缩空白后，与 T3-2 代码块里对应的那一行全等。这样也排除了额外加上的 `onKeyDown` 等处理器。
      - `composeSongSection` 四行与 HEAD 相同。把下面这四行作为字面量写进测试，不要用 git 读：
        ```
        const composeSongSection = useCallback((text: string) => {
          setInput(text);
          requestAnimationFrame(() => textareaRef.current?.focus());
        }, []);
        ```
   6. match_profile：
      - `<p className="text-xs text-[color:var(--ink2)]">双方都接受匹配后，对方会出现在这里</p>` 恰 1 处。
      - 含 `{rooms.length > 0 && <p className="mt-3">从「最近聊天」选一位`。
      - `{pendingMatches.length === 0 ? (` 之后（允许空白）紧接 `<section data-match-empty`。
      - section 开标签含 `pt-10`、`mobile:pt-2`，不含 `mt-10`、`mobile:mt-2`。
      - 画像页「暂无社交画像（旧版）」全等存在。
      - 三份文档各至少 1 处新名。
   7. settings_privacy：
      - 含第一段的那一行去掉首尾空白后，以 `<p className={noteClass}>启用后，` 开头、以 `</p>` 结尾。
      - 紧接着的下一行是 Claude 提示那一行，文字为 v1.2 新文案，并且早于「启用我的聊天模型」。
      - `<details>` 里 7 段的先后顺序为：危机复核、生图：、选 Claude 时、自带模型文字聊天、Key 加密保存、开启『聊天读小说』、Claude 的接口不对中国大陆。
   8. history_dates：
      - 按 T9-8 新条目。
      - `dayFace` 一行与 T7-2（v1.2）全等。
   9. voice_hint：
      - 所有 `subprocess.run` 加 `timeout=60`；依赖探测遇到 `CalledProcessError` 或超时时 `pytest.skip`（本机门禁仍要求 0 skipped）。
      - 新增：dictating 且首次提示显示时，取不到气泡。
   10. 名不副实的测试名改准：`test_empty_states_agents.py` 里自称检查「本地 LoadingState」的那一条，和 `test_empty_states_settings_privacy.py` 里自称检查「可见」的那一条。要么补上真正的检查，要么改名。

T9 总则仍适用：每个新增或改写的 `test_` 函数至少含一条在 HEAD 上会失败的断言。另加一条：每个加固项都要做至少一个变异，证明它能变红（例如把 `if (e.repeat) return;` 挪回第一行、去掉 `min-h-10`、把 `dayFace` 改回 v1.1 写法、把落定通知与置位对调），变异前后按字节备份、还原并校验 sha256，结果写进报告。

**已知局限的补充**（写进 `03-report.md`，不在本批处理）：
- 本页第一次身份检查结束后，另一个标签清掉本地用户名、而 Cookie 仍有效时，会先显示登录提示，再恢复。
- 401 跳转登录页之前，会先闪一下「请登录后…前往登录」。
- 日期框是透明的原生控件。键盘 Tab 会在年、月、日分段间停留，每个框 4 次，HEAD 上同样如此，只是现在看不见分段。直接键入会改值，日期面要等三段都填完才更新。实测鼠标或触屏点击时，日期框也匹配 `:focus-visible`，所以不能用「键盘聚焦时显出原生框」来解决，留给作者决定做法。
