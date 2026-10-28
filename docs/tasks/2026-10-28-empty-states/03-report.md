# 03 实施记录：空态与文案（UI 复核第三批）

- 规格：`docs/tasks/2026-10-28-empty-states/02-spec.md`，v1.1（2026-10-28）
- 基线：`main` @ `f6adca6`；工作分支 `feat/empty-states`（本工作树）
- 级别：L2；未改接口、数据模型、依赖
- 执行：dsh（DeepSeek Flash，max）负责实现与 §6 第 1–6 条；真实浏览器实测由 Claude 按 §6 第 7 条执行
- 本报告只记录本工作树中的实际结果；没有提交 git

## 0. Agent 拆分表

| 阶段 | Agent | 负责文件 | 新增测试 | 结果 |
|---|---|---|---|---|
| 第一阶段（串行） | A | `frontend/lib/useAccountIdentity.ts`（只追加 `useAccountIdentityPending`） | `test_empty_states_identity.py`（5） | 5 passed，0 skipped |
| 第二阶段（并行） | B | `NovelWizard.tsx`、`NovelShelf.tsx`、`NovelWorkbench.tsx`（T1-2 的 1–3、T2 第 2–3 条） | `test_empty_states_novel.py`（8） | 8 passed，0 skipped |
| 第二阶段（并行） | C | `StudioShelf.tsx`、`StudioWorkbench.tsx`、`kb/KbWorkbench.tsx`（T1-2 的 4–6、T2 第 1 条） | `test_empty_states_studio.py`（3） | 3 passed，0 skipped |
| 第二阶段（并行） | D | `MyAgentWorkspace.tsx`、`AgentExchangeWorkspace.tsx`、`AgentMemoryPanel.tsx`、`app/agents/[id]/page.tsx`（T1-2 的 7–10） | `test_empty_states_agents.py`（4） | 4 passed，0 skipped |
| 第二阶段（并行） | E | `app/page.tsx`、`ConversationPicker.tsx`（T3） | `test_empty_states_chat_openers.py`（4） | 4 passed，0 skipped |
| 第二阶段（并行） | F | `match/page.tsx`、`profile/page.tsx`、`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`test_ui_polish_settings_drawers.py:83`（T4、T5） | `test_empty_states_match_profile.py`（4） | 4 passed，0 skipped |
| 第二阶段（并行） | G | `ChatModelSection.tsx`（T6） | `test_empty_states_settings_privacy.py`（4） | 4 passed，0 skipped |
| 第二阶段（并行） | H | `history/page.tsx`（T7） | `test_empty_states_history_dates.py`（4） | 4 passed，0 skipped |
| 第二阶段（并行） | I | `VoiceButton.tsx`（T8） | `test_empty_states_voice_hint.py`（3） | 3 passed，0 skipped |

新增测试合计 39 条：5 + 8 + 3 + 4 + 4 + 4 + 4 + 4 + 3。

派发过程说明（如实记录）：

- 第一阶段单独派 agent A 完成后，主代理确认 `frontend/lib/useAccountIdentity.ts` 导出 `useAccountIdentityPending`，并独立复跑 5 条测试全绿，才进入第二阶段。
- 第二阶段按规格使用 `workflow` 工具的 `parallel()` 同时派 B–I 共 8 个 agent。首次 workflow 脚本因提示词内一处模板插值未转义，在**派发任何 agent 之前**就失败（0 agents），未产生任何文件改动；修正脚本后重新派发成功。另有一次 0 agent 的 workflow 冒烟校验。因此实际派出并执行工作的 agent 为上表 A–I 共 9 个。
- 每个 agent 都被告知：不得调用 subagent / subagent_fork / workflow；`lib/useAccountIdentity.ts` 由第一阶段完成、不得修改；`test_ui_polish_settings_drawers.py` 第 83 行只由 F 修改；所有 agent 在同一工作树并发修改互不重叠的文件。

## 1. 修改与新增文件清单

修改（22 个）：

1. `frontend/lib/useAccountIdentity.ts`（只追加，原有代码未动）
2. `frontend/components/novel/NovelWizard.tsx`
3. `frontend/components/novel/NovelShelf.tsx`
4. `frontend/components/novel/NovelWorkbench.tsx`
5. `frontend/components/studio/StudioShelf.tsx`
6. `frontend/components/studio/StudioWorkbench.tsx`
7. `frontend/components/studio/kb/KbWorkbench.tsx`
8. `frontend/components/MyAgentWorkspace.tsx`
9. `frontend/components/AgentExchangeWorkspace.tsx`
10. `frontend/components/AgentMemoryPanel.tsx`
11. `frontend/app/agents/[id]/page.tsx`
12. `frontend/app/page.tsx`
13. `frontend/components/ConversationPicker.tsx`
14. `frontend/app/match/page.tsx`
15. `frontend/app/profile/page.tsx`
16. `frontend/components/ChatModelSection.tsx`
17. `frontend/app/history/page.tsx`
18. `frontend/components/VoiceButton.tsx`
19. `README.md`（只改第 11 行一处名称）
20. `PLAN.md`（只改第 54 行一处名称）
21. `docs/ARCHITECTURE.md`（只改第 126 行一处名称）
22. `backend/tests/test_ui_polish_settings_drawers.py`（只改第 83 行的标题参数）

新增（10 个）：

1. `backend/tests/test_empty_states_identity.py`
2. `backend/tests/test_empty_states_novel.py`
3. `backend/tests/test_empty_states_studio.py`
4. `backend/tests/test_empty_states_agents.py`
5. `backend/tests/test_empty_states_chat_openers.py`
6. `backend/tests/test_empty_states_match_profile.py`
7. `backend/tests/test_empty_states_settings_privacy.py`
8. `backend/tests/test_empty_states_history_dates.py`
9. `backend/tests/test_empty_states_voice_hint.py`
10. `docs/tasks/2026-10-28-empty-states/03-report.md`（本文件）

## 2. 实现了什么

### 2.1 身份确认中（P3-20）

`useAccountIdentityPending()` 的服务端快照恒为 `true`；客户端在「本地没有用户名且本页还没完成过一次身份找回」时为 `true`。首次 effect 调用 `ensureAccountIdentity()`，在它落定（成功、401 或失败）后把模块级 `identityRecoverySettled` 置为 `true` 并通知所有订阅者，客户端快照随即变为 `false`。10 个页面/组件据此把 `!owner` 分支拆成「身份确认中」和「确认失败/未登录」两种：确认中显示「正在加载身份…」，落定后仍空串则回到原「请登录后…」文案。NovelShelf、NovelWorkbench、StudioShelf 三处 iframe 页面的「前往登录」加 `target={embedded ? "_top" : undefined}`。

### 2.2 抽屉重复标题与双入口（P2-8）

- 工作室：嵌入时 h1 加 `sr-only`，「新建项目」按钮加 `ml-auto`，仍是原生 `button`；独立页 h1 可见。
- 书斋：页眉「新建一本」只在「空态卡会出现」时隐藏（`owner && !error && !loading && books.length === 0`），加载中、出错、有书时照常显示；空态卡里的「新建一本」原样保留。未登录时刷新按钮不再一直显示「刷新中…」并禁用。

### 2.3 新对话空态（P2-10）

新会话且有会话时渲染三个可点的开场：「聊聊今天」「帮我画一张…」「看看我拍的这张图」。三者分别只预填输入框并聚焦、打开生成图片模式、打开文件选择器，都不发请求。`handleKeyDown` 第一行 `if (e.repeat) return;`，按住 Enter 的自动重复不会落到发送。空态/错误文案改为指向「对话列表」里的「新建」。`:962` 的语音注释改成实际行为。

### 2.4 匹配页空态与画像改名（P2-10）

- 匹配页未选中联系人且没有推荐卡时，右侧渲染 `data-match-empty` 说明区，讲清匹配是什么、推荐卡为什么可能一直是空的、公开分身名片与「广场」这条替代路径，并给出「查看公开名片设置」入口（嵌入时 `_top`）。左栏文案改为 12px 的「双方都接受匹配后，对方会出现在这里」。
- 画像页标题、空态、隐私说明统一为「社交画像（旧版）」，并说明「清空记忆与个人画像」会一并清空这份旧画像。三份文档同一行同步改名。

### 2.5 设置页隐私说明（P2-11）

- 第一段「启用后，聊天回复会把分身设定…」从底部说明块移到「启用我的聊天模型」开关和「保存」之前，常显。
- 选 Claude 时多显示一句「已选 Claude：本轮图片和工具结果也会发送给 Anthropic…」。
- 开关说明改为「首次保存后会直接启用；之后可以用这个开关停用或重新启用。」。
- 其余 7 段原顺序、原文字收进默认收起的 `<details>`，summary 为「更多隐私与计费说明」。

### 2.6 历史页日期筛选（P3-19）

两个原生日期框改为「从 / 到」两枚 chip：可见文字是中文日期或「不限」，原生 `input type="date"` 透明覆盖在 chip 内，仍可用「开始日期 / 结束日期」找到；点击或键盘 Enter/Space 调 `showPicker()`，失败时沿用原生点按。两枚 chip 互相限制 `max` / `min`。「全部」只在两个日期都为空时高亮；右栏摘要也改用中文日期。

### 2.7 语音按钮手机状态气泡（P3-21）

在根元素内、首次提示之后新增 `data-voice-status` 气泡：仅 `md:hidden`（手机显示），按住时「松开发送」、录音中「再点一下发送」，松开/停止后随 `holding`/`dictating` 消失；桌面不显示。

## 3. 与 T1–T9 逐项对应

| 任务 | 实现位置 | 新测试 |
|---|---|---|
| T1-1 | `lib/useAccountIdentity.ts` 追加 `useAccountIdentityPending`（服务端 true；客户端按 `getUsername` + `identityRecoverySettled`） | `test_empty_states_identity.py` |
| T1-2 | 10 个外层组件加 `const identityPending = useAccountIdentityPending()` 并传入内层；内层可选 `identityPending = false`；登录分支插「正在加载身份…」；三处 iframe 登录链接加 `target` | novel/studio/agents 三组测试 |
| T2-1 | `StudioShelf.tsx` h1 `sr-only` 条件、按钮 `ml-auto` 条件 | `test_empty_states_studio.py` |
| T2-2 | `NovelShelf.tsx` 页眉 Link 条件包裹 | `test_empty_states_novel.py` |
| T2-3 | `NovelShelf.tsx` 刷新按钮 `disabled`、文案、图标条件都加 `owner` | `test_empty_states_novel.py` |
| T3-1 | `page.tsx` 三个普通箭头函数放在 `handleNewChat` 之后 | `test_empty_states_chat_openers.py` |
| T3-2 | `page.tsx` 空态 JSX 换成三开场块 | 同上 |
| T3-3 | `handleKeyDown` 第一行 `if (e.repeat) return;` | 同上 |
| T3-4 | `page.tsx:962` 注释改为「轻点录音：再点一下停止，识别后直接发送（不填进输入框）」 | 源码检查（E 的测试间接覆盖） |
| T3-5 | `ConversationPicker.tsx:91` 改为「点「新建」」 | `test_empty_states_chat_openers.py` |
| T4 | `match/page.tsx` 新增 `Link`、左栏文案、右侧 `data-match-empty` 说明区 | `test_empty_states_match_profile.py` |
| T5 | `profile/page.tsx` 三处改名与整句；三份文档；`test_ui_polish_settings_drawers.py:83` | 同上 |
| T6 | `ChatModelSection.tsx` 第一段前移、Claude 条件句、开关说明、`<details>` 折叠 | `test_empty_states_settings_privacy.py` |
| T7 | `history/page.tsx` 导入、`openDatePicker`、`dayFace`、两枚 chip、「全部」条件、右栏摘要 | `test_empty_states_history_dates.py` |
| T8 | `VoiceButton.tsx` 新增 `data-voice-status` 气泡 | `test_empty_states_voice_hint.py` |
| T9 | 9 个测试文件，共 39 条 | 全部新测试 |
| T10 | 本报告 | — |

## 4. 门禁结果（§6 第 1–6 条）

执行环境备注：本沙箱的 `NO_PROXY` 含带方括号的 `[::1]`，httpx 在收集阶段会把它当 URL 解析并报 `InvalidURL: Invalid port: ':1]'`。这不是代码问题；第 4 条用 `env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy` 清掉代理变量后执行，测试本身全部离线。

1. `cd frontend && npx tsc --noEmit` → **0 错误**。
2. `cd frontend && npm run lint` → **0 errors、25 warnings**（与 HEAD 基线 25 一致）。
3. `cd frontend && npm run build` → **exit 0**（Next.js 16.4.3；Build 输出 19 条 Route，含 `/_not-found` 与 `/manifest.webmanifest`）。
4. `cd backend && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider` → 执行者交付时此处留的是占位符，没有写结果。以下由 Claude 补入，是沙箱外的门禁结果（`verify/gate-record.md` 第 1 节）：**7813 passed、0 skipped、0 failed**；其中新测试 39 条，7813 = 7774 + 39，既有 7774 条一条不少。
5. 结构判据（实测值）：
   - `grep -rn '旧社交画像' frontend/app frontend/components README.md PLAN.md docs/ARCHITECTURE.md | wc -l` = **0**（HEAD 6）。
   - 同一组路径「社交画像（旧版）」= **8 处，分布在 7 行**（其中 profile 第 136 行含两处；≥ 6）。
   - `git diff --numstat HEAD -- backend/tests/` → 只有 `1 1 backend/tests/test_ui_polish_settings_drawers.py`。
   - `frontend/app`、`frontend/components` 下含 `useAccountIdentityPending()` 的文件 = **10**（HEAD 0）。
   - `grep -rho 'aria-label=' frontend/app frontend/components --include='*.tsx' | wc -l` = **119**（HEAD 118，未减少）。
   - `page.tsx`：`onClick={() => setImageMode(true)}` = **0**；`type="file"` = **2**。
   - diff 新增行里 `font-semibold`、`font-bold`、`fontWeight`、`<strong` 合计 **0**；「·」**0**。
6. `git status --porcelain --untracked-files=all` → 只出现 §3.1 白名单路径与本规格目录（22 个修改文件、9 个新测试、`02-spec.md`、本报告）。未提交 git。

## 5. §6 第 7 条视觉判据对应的代码依据

本沙箱没有浏览器，以下只列代码依据；真实浏览器量测由 Claude 执行。

| 视觉判据 | 代码依据 |
|---|---|
| P3-20 SSR 原始 HTML 含「正在加载身份…」、不含「请登录后…」 | `useAccountIdentityPending` 的 `serverIdentityPending = () => true`；10 个内层在 `!owner` 时先判 `identityPending`。`/studio` 的 SSR 探针见 `test_empty_states_studio.py` |
| 脚本晚到 3 秒时 1s/2.5s 仍显示「正在加载身份…」 | 客户端快照在 `identityRecoverySettled` 为 false 时恒为 true；`ensureAccountIdentity` 未落定前不翻转 |
| `/api/profile` 慢 4 秒时 1s/2.5s 显示「正在加载身份…」，8s 出现向导 | 同一个 `identityRecoverySettled` 只在 `ensureAccountIdentity().finally` 置 true；落定后 `getUsername` 有值，登录分支让位给正常内容 |
| `/api/profile` 500 时 8s 显示原登录文案 | `ensureAccountIdentity` 其他错误返回空串；`finally` 仍把 settled 置 true，客户端快照变 false，回到原登录分支。这是已知局限 |
| 小说功能关闭时恰好 1 个「小说工坊尚未开放」 | `NovelWizard.tsx` 的 `!catalog ? <ErrorNotice …>` 分支未动；`test_novel_p2_r1.py` 14 passed |
| 工作室抽屉 h1「短片工作室」≤1px、读屏可读 | `StudioShelf.tsx:70` 的 `sr-only` 条件类名 |
| 工作室「新建项目」右边缘贴齐 | `StudioShelf.tsx:71` 的 `ml-auto` 条件类名；仍是原生 `button` |
| 独立页 `/studio` h1 可见 | `embedded` 为 false 时不加 `sr-only` |
| 书斋 0 本书时可见「新建一本」恰好 1 个且在空态卡 | `NovelShelf.tsx:60` 页眉 Link 被 `!(owner && !error && !loading && books.length === 0)` 隐藏；空态卡 Link 在 `:65` |
| 新对话 3 个可点开场位于页头之下、输入釉片之上 | `page.tsx:2614-2621` 的 `data-chat-openers` 块位于消息滚动区内、`Glaze as="footer"` 之前 |
| 点击开场 3 秒内 `/api/**` 非 GET 为 0；按住 Enter 1.2 秒也为 0 | 三个函数只调 `composeSongSection` / `setImageMode(true)` / `fileInputRef.click()`，函数体不含 `handleSend`、`apiFetch`、`fetch(`；`handleKeyDown` 第一行 `if (e.repeat) return;`（`page.tsx:2236`） |
| 点「聊聊今天」输入框是「聊聊今天」并聚焦 | `startChatOpener` 调 `composeSongSection("聊聊今天")`；该函数 `setInput` + `requestAnimationFrame` 聚焦 |
| 点「帮我画一张…」出现生成图片模式 | `startDrawOpener` 调 `setImageMode(true)` 并聚焦输入框 |
| 点「看看我拍的这张图」触发选择文件 | `startPhotoOpener` 调 `fileInputRef.current?.click()` |
| 匹配页右侧有「匹配是什么」「查看公开名片设置」 | `match/page.tsx:349-356` 的 `data-match-empty` 区块 |
| 匹配页左栏文字 ≥ 12px | 左栏改为 `text-xs`（12px）`text-[color:var(--ink2)]`（`match/page.tsx:324`） |
| 设置抽屉可见文字里「旧社交画像」0 次 | `profile/page.tsx` 三处改名；画像页被设置抽屉 iframe 复用，`grep` 为 0 |
| 设置 details 默认收起 | `<details>` 无 `open`；summary 文案「更多隐私与计费说明」 |
| 第一段可见且在「保存」之上 | 第一段 `<p className={noteClass}>` 位于第二个 fieldset 的开关块之前（`ChatModelSection.tsx:345` 前后），保存按钮在开关块之后 |
| 其余 7 段不可见、展开后与 HEAD 逐字相同 | 7 段原文原顺序放在 `details > div` 内；第一段文字未改 |
| 手机 summary 高 ≥ 40 | `summary` 的 `min-h-10`（2.5rem = 40px）加 `py-2` |
| 两个日期输入仍可用「开始日期 / 结束日期」找到但不可见 | `history/page.tsx:221-228`、`:235-242` 的透明覆盖 `input type="date"`；两个 aria-label 各 1 处 |
| chip 上只显示「从 / 到 / 不限 / YYYY年M月D日」 | chip 可见文字为 `从`/`到` + `dayFace(...)`；`formatBeijingDateLong(beijingDayStart(key))` 输出「2026年10月27日」，空值「不限」 |
| en-US 与 zh-CN 上下文显示相同 | 显示文本不来自原生日期框，全部由 `formatBeijingDateLong` 生成；原生输入被 `opacity-0` 覆盖 |
| 点 chip 会调用 `showPicker`；填入 `2026-10-27` 显示「2026年10月27日」 | `openDatePicker` 在 `onClick` / Enter / Space 中调用 `input.showPicker()`（`try` 包裹）；日期值来自 `input type="date"` 的 `value` |
| 只设「到」时「全部」不高亮 | `quick === key && (key !== "all" || (!dateFrom && !dateTo))` |
| 390 宽按住语音键能看到「松开发送」，松开消失；1440 宽不出现 | `VoiceButton.tsx:150-154` 的 `!showHint && (holding || dictating)` 气泡，`md:hidden` 控制手机可见；`holding` 由父组件录音态驱动 |
| 截图（书斋空态、新对话开场、匹配页、设置折叠块、历史日期 chip，昼夜各一张） | 由 Claude 在真实浏览器执行；本报告只提供上表代码依据 |

## 6. 已知局限（照实记录，不写成已修复）

1. 身份找回失败（`/api/profile` 返回 500 或断网）后，`identityPending` 会落定为 false，页面仍显示原来的「请登录后…」文案。本批只修「身份确认中」这段时间。
2. 生图或改图模式下，语音松开或再点一下会直接触发付费生成，手机气泡仍写「发送」；三种状态的按钮短字与气泡措辞也略有不同。
3. 「查看公开名片设置」在抽屉里会让整页跳到 `/agents/me`，未发送的草稿会丢失。
4. 已启用自带模型、但不是 Claude 的用户发图时，走平台看图并扣草莓，底栏没有提示。

## 7. 偏差、实现说明与人工确认项

- **hook 追加位置**：规格要求在 `useAccountIdentity` 之后追加。实际追加在整个文件末尾（`useAccountRequest` 之后），仍在 `useAccountIdentity` 之后；既有代码零改动，追加内容逐字一致。
- **测试替身兼容**：`test_empty_states_identity.py` 的 Node 替身额外提供最小 `window.addEventListener/removeEventListener`，因为既有 `subscribeAccount` 订阅需要它；没有改源码。
- **测试环境代理**：见 §4 备注。全量测试是在清空代理变量后跑的；这是执行环境差异，不是仓库改动。
- **HEAD 正控**：每个新 `test_` 函数都含至少一条在 HEAD 上会失败的断言。E、G、H、I 等 agent 用 `git show HEAD:…` 的临时副本实际跑过正控并报告失败；其余为源码断言，HEAD 上必然缺失。主代理没有回滚工作树。
- **未做视觉实测**：沙箱无浏览器，§6 第 7 条由 Claude 执行；截图也由 Claude 产出。
- **git 历史相关测试**：若全量结果中出现 §3.4 列出的 7 条跳过，原因是沙箱读不到主仓库 `.git`；除这些之外不应有跳过。（Claude 补注：沙箱外的全量门禁实际为 0 skipped，7 条 git 历史相关测试也都执行并通过，见 `verify/gate-record.md` 第 1 节。）

## 8. 返修 R1（规格 v1.2）

本节是 R1 的增量记录；§0–§7 保留 v1.1 交付时的内容，Claude 已补入的 §4 第 4 条与 git 历史测试说明均未改动。

### 8.1 逐项对应（返修单第 1–9 条）

| 返修单 | 规格 | 实际改动 |
|---|---|---|
| 1 | T3-3 / §10 第 1 条 | `page.tsx` 的 `if (e.repeat) return;` 从函数体第一行移到 `e.preventDefault();` 与 `handleSend();` 之间，函数体恰为 v1.2 的 8 行；page.tsx 其余未动（R1 时曾误删文件开头的 UTF-8 BOM，R2 已补回） |
| 2 | T2-2 / §10 第 2 条 | `NovelShelf.tsx` 页眉行改为 `<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">`，源码恰 1 处 |
| 3 | T2-1 / §10 第 2 条 | `StudioShelf.tsx` 页眉行同样加 `min-h-10`，源码恰 1 处 |
| 4 | T7-2、T7-3 / §10 第 3、5 条 | `history/page.tsx`：`dayFace` 改为无法解析时回退原值；「从」`aria-label="从（开始日期）"`、`max={dateTo || "9999-12-31"}`；「到」`aria-label="到（结束日期）"`、`min={dateFrom || undefined} max="9999-12-31"` |
| 5 | T4-3 / §10 第 4 条 | `match/page.tsx` 的 `data-match-empty` 开标签去掉 `mt-10`、`mobile:mt-2`，改为 `pt-10`、`mobile:pt-2` |
| 6 | T6-2 / §10 第 6 条 | Claude 提示句从「本轮图片」改为「你在聊天里发的图片」，该行其余未动 |
| 7 | T1-1 / §10 第 7 条 | `useAccountIdentity.ts` 新代码第一行注释替换为 v1.2 的两行，第三行「测试替身…」保留；代码一字未动，整段与 T1-1 代码块逐字一致 |
| 8 | §10 第 8.1–8.10 条 | 9 个新测试文件全部加固，见上面 §10 第 8 条逐小项表；与源码改动对应的断言同步更新 |
| 9 | 本报告 | 追加本节；§4 的两处精度同时修正（见 8.5） |

§10 第 8 条逐小项：

| 小项 | 加固内容 | 测试落点 |
|---|---|---|
| 8.1 | 新增「找回失败」场景：用户名空串、恢复以空串落定；订阅回调同步重读快照并记录；通知时快照 false、落定后仍 false、通知至少 1 次 | `test_empty_states_identity.py::test_failed_recovery_with_empty_username_never_reports_pending` |
| 8.2 | 0 本书时唯一 `/novels/new` 入口是 `EmptyState` 后代、`<header>` 内 0 个；默认有书与 500 出错时 `<header>` 恰 1 个；`identityPending` 在 mount 后、flush 前为 true，落定后重挂为 false 且嵌入登录链接 `target="_top"`；页眉 `min-h-10` 行恰 1 处 | `test_empty_states_novel.py` 的 `test_novel_shelf_new_book_entry_sits_in_header_unless_the_shelf_is_empty`、`test_novel_shelf_pending_identity_settles_to_embedded_login_link`、`test_novel_shelf_header_row_reserves_min_height`、`test_novel_pages_wire_the_verbatim_pending_identity_branch` |
| 8.3 | 10 个文件的 `!owner ? (identityPending ? <确认中> : <原登录>)` 整段子串逐字断言 | novel 的 `test_novel_pages_wire_the_verbatim_pending_identity_branch`、studio 的 `test_studio_identity_pending_wiring_and_embedded_login_target`、agents 的 4 条接线测试 |
| 8.4 | StudioShelf 页眉 `min-h-10` 恰 1 处；非嵌入态「新建项目」className 不含 `ml-auto`；直接挂 `AccountStudioWorkbench` / `AccountKbWorkbench` 且传 `identityPending: true` 时显示「正在加载身份…」、不显示「请登录后」 | `test_empty_states_studio.py` 的 3 条新增/加固测试 |
| 8.5 | `handleKeyDown` 8 行逐行全等；三个开场函数压缩空白后与 T3-1 全等；三个开场 button 压缩空白后与 T3-2 全等；`composeSongSection` 四行与 HEAD 字面量全等（测试内硬编码，不读 git） | `test_empty_states_chat_openers.py` 的 `test_enter_key_ignores_auto_repeat`、`test_chat_opener_bodies_match_the_spec_exactly`、`test_chat_opener_buttons_match_the_spec_exactly` |
| 8.6 | 左栏精确 `<p …>` 恰 1 处；`rooms.length > 0 && …` 前缀；`{pendingMatches.length === 0 ? (` 后紧接 section；section 含 `pt-10`/`mobile:pt-2`、不含 `mt-10`/`mobile:mt-2`；「暂无社交画像（旧版）」全等；三份文档各至少 1 处新名 | `test_empty_states_match_profile.py` 的 6 条测试 |
| 8.7 | 第一段源码行以 `<p className={noteClass}>启用后，` 开头、`</p>` 结尾；下一行精确等于 v1.2 Claude 提示行且早于「启用我的聊天模型」；`<details>` 内 7 段顺序为危机复核、生图：、选 Claude 时、自带模型文字聊天、Key 加密保存、开启『聊天读小说』、Claude 的接口不对中国大陆 | `test_empty_states_settings_privacy.py` 的 4 条测试 |
| 8.8 | `showPicker(` 恰 1 处且在 `try` 内；`openDatePicker(e.currentTarget)` 恰 4 处；两个 max/min 精确；两个新 aria-label 各 1 处；`dayFace` 一行与 T7-2 v1.2 全等；设备时区 API 0 处 | `test_empty_states_history_dates.py` 的 4 条测试 |
| 8.9 | 2 处 `subprocess.run` 均带 `timeout=60`；依赖探测遇 `CalledProcessError`/`TimeoutExpired` 跳过；新增 dictating + 首次提示时无气泡；测试内自检 timeout 计数 | `test_empty_states_voice_hint.py` 的 3 条测试 |
| 8.10 | `test_agent_exchange_workspace_pending_identity_uses_local_loading_state`：补 `function LoadingState(` 恰 1 处且 import 中无 LoadingState 的真检查；`test_first_privacy_paragraph_is_outside_fold_before_switch_and_save`：原「可见」改名为「在折叠块外」，不再声称做过浏览器可见性检查 | 上述两条测试 |

### 8.2 拆分表（R1 派出的全部 agent）

| Agent | 负责文件 | 结果 |
|---|---|---|
| A | `useAccountIdentity.ts`（注释）+ `test_empty_states_identity.py` | 6 passed |
| B | `NovelShelf.tsx` + `test_empty_states_novel.py` | 14 passed |
| C | `StudioShelf.tsx` + `test_empty_states_studio.py` | 5 passed |
| D | `test_empty_states_agents.py` | 4 passed |
| E | `page.tsx` + `test_empty_states_chat_openers.py` | 6 passed |
| F | `match/page.tsx` + `test_empty_states_match_profile.py` | 6 passed |
| G | `ChatModelSection.tsx` + `test_empty_states_settings_privacy.py` | 4 passed |
| H | `history/page.tsx` + `test_empty_states_history_dates.py` | 4 passed |
| I | `test_empty_states_voice_hint.py` | 3 passed |

9 个 agent 由 `workflow` 的 `parallel()` 同时派发，未调用其他 subagent；主代理只做拆分、派发、汇总、白名单检查、门禁、变异自检与报告。R1 新测试合计 **52** 条（6 + 14 + 5 + 4 + 6 + 6 + 4 + 4 + 3 = 52）。

### 8.3 门禁结果（R1 后）

- `cd frontend && npx tsc --noEmit` → **0 错误**。
- `cd frontend && npm run lint` → **0 errors、25 warnings**（与 HEAD 基线 25 一致）。
- `cd frontend && npm run build` → **exit 0**（Next.js 16.4.3，Build 输出 19 条 Route）。本轮补交按要求未重跑 build；以上 tsc / lint / build 是 R1 实现完成后的实测值。
- 全量 `pytest`（清空代理变量）→ **7826 passed、0 failed、0 skipped**（Claude 门禁 v2 实测，见 `verify/gate-record.md`；本轮 R1 补交未重复跑全量，52 条新测试已在本轮前台复跑）。
- R1 新测试 52 条；既有 7774 条一条不少。

### 8.4 变异自检

主代理按返修单要求串行做变异：每个加固项至少 1 个变异；每次先把文件按字节备份到仓库外的临时目录，记录 sha256，改完运行对应测试，再按字节拷回并复核 sha256。全部 16 个变异都至少让一条新测试变红（存活 0 条）；11 个被变异文件全部按字节还原，最终 sha256 与变异前基线完全一致。

| 加固项 | 变异 | 变红测试 | 还原 sha256 |
|---|---|---|---|
| 8.1 | 交换 `identityRecoverySettled = true;` 与 `identityPendingListeners.forEach(...)` 两行 | `test_failed_recovery_with_empty_username_never_reports_pending` | `612a1b54f895ef63` → `612a1b54f895ef63`，一致 |
| 8.1 | `clientIdentityPending` 改成 `() => !getUsername()` | `test_failed_recovery_with_empty_username_never_reports_pending` | `612a1b54f895ef63` → `612a1b54f895ef63`，一致 |
| 8.2 | 去掉 NovelShelf 页眉行的 `min-h-10` | `test_novel_shelf_header_row_reserves_min_height` | `1a7a4b0655b2a127` → `1a7a4b0655b2a127`，一致 |
| 8.3 | AgentMemoryPanel 的确认中分支与原登录分支对调 | `test_agent_memory_panel_shows_pending_identity_before_login` | `644aa5b1c31664c3` → `644aa5b1c31664c3`，一致 |
| 8.4 | 去掉 StudioShelf 页眉行的 `min-h-10` | `test_shelf_header_reserves_height_and_non_embedded_button_is_not_right_aligned` | `63480c505ebb49d8` → `63480c505ebb49d8`，一致 |
| 8.4 | StudioWorkbench 的「正在加载身份…」改成「正在打开项目…」 | `test_studio_identity_pending_wiring_and_embedded_login_target`<br>`test_identity_pending_workbenches_show_loading_instead_of_login` | `b338cb6ba107439f` → `b338cb6ba107439f`，一致 |
| 8.5 | `if (e.repeat) return;` 挪回 `handleKeyDown` 第一行 | `test_enter_key_ignores_auto_repeat` | `38348cc0e7867dbd` → `38348cc0e7867dbd`，一致 |
| 8.5 | 给「帮我画一张…」按钮加 `onKeyDown={handleKeyDown}` | `test_chat_opener_buttons_match_the_spec_exactly` | `38348cc0e7867dbd` → `38348cc0e7867dbd`，一致 |
| 8.6 | section 的 `pt-10` 改回 `mt-10` | `test_match_empty_section_moves_top_spacing_from_margin_to_padding` | `d01cae9a2caf7837` → `d01cae9a2caf7837`，一致 |
| 8.7 | 隐私第一段包进 `{needsKey && …}` | `test_first_privacy_paragraph_is_outside_fold_before_switch_and_save` | `3182fe0599421100` → `3182fe0599421100`，一致 |
| 8.7 | 交换折叠里「Key 加密保存」与「自带模型文字聊天」两段 | `test_privacy_fold_follows_second_fieldset_and_holds_locked_paragraphs` | `3182fe0599421100` → `3182fe0599421100`，一致 |
| 8.8 | `dayFace` 改回 v1.1 的 `(key && …) || "不限"` | `test_date_chips_render_chinese_day_faces_and_drop_native_placeholder` | `303a522b6205b2ba` → `303a522b6205b2ba`，一致 |
| 8.8 | 去掉「到」的 `max="9999-12-31"` | `test_date_chips_open_native_picker_and_bound_each_other` | `303a522b6205b2ba` → `303a522b6205b2ba`，一致 |
| 8.8 | `aria-label="从（开始日期）"` 改回 `aria-label="开始日期"` | `test_date_labels_stay_accessible_and_existing_history_contracts_survive` | `303a522b6205b2ba` → `303a522b6205b2ba`，一致 |
| 8.9 | 气泡条件改成 `dictating || (holding && !showHint)` | `test_voice_status_bubble_respects_first_use_hint` | `427de6565d25ebda` → `427de6565d25ebda`，一致 |
| 8.10 | 给 AgentExchangeWorkspace 加一行 `import { LoadingState } ...` | `test_agent_exchange_workspace_pending_identity_uses_local_loading_state` | `b136ecf3f811854d` → `b136ecf3f811854d`，一致 |

还原核对三项全部通过：

- 前台复跑 52 条新测试：**52 passed、0 failed、0 skipped**；
- `(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256 | cut -c1-16` = **7c4aa5ca5c3c3510**（与 Claude 记录的 R1 快照一致）；
- `git status --porcelain --untracked-files=all` 除 `03-report.md` 外与变异前完全相同。

`ALL_RESTORED = True`，`STATUS_EQUAL_EXCEPT_REPORT = True`；16 个变异的 `results.json` 与逐次备份在仓库外临时目录，未进入工作树。

### 8.5 报告原文的两处精度修正

- §4 第 3 条：原「18 个路由生成成功」改为「Build 输出 19 条 Route，含 `/_not-found` 与 `/manifest.webmanifest`」。按本次 build 的实际输出行数计。
- §4 第 5 条：原「7 行」改为「8 处，分布在 7 行」。实测 `grep` 命中 7 行，其中 `profile/page.tsx` 第 136 行含两处，故共 8 处；此前的「7 行」少算了同一行的第二处。

### 8.6 已知局限（在原有 4 条后补充）

5. 本页第一次身份检查结束后，另一个标签清掉本地用户名、而 Cookie 仍有效时，会先显示登录提示，再恢复。
6. 401 跳转登录页之前，会先闪一下「请登录后…前往登录」。
7. 日期框是透明的原生控件。键盘 Tab 会在年、月、日分段间停留，每个框 4 次，HEAD 上同样如此，只是现在看不见分段。直接键入会改值，日期面要等三段都填完才更新。实测鼠标或触屏点击时，日期框也匹配 `:focus-visible`，所以不能用「键盘聚焦时显出原生框」来解决，留给作者决定做法。

### 8.7 未完成或需人工确认的地方

- 真实浏览器实测与截图由 Claude 执行；本报告只给出代码与测试依据，不把浏览器量测写成本地实测。
- 变异自检由主代理在沙箱内完成，变异期间未运行其他测试；还原后已重新跑 52 条新测试，全量门禁采用 Claude v2 实测结果。
- 除上表列出的文件外，未改任何源码、既有测试、夹具或配置；`docs/tasks/2026-10-28-empty-states/verify/` 下 Claude 的文件未触碰。

## 9. 返修 R2

R1 改 `frontend/app/page.tsx` 时误删了文件开头的 UTF-8 BOM：HEAD 的前三字节是 `efbbbf`，R1 后变成 `227573`，相对 HEAD 因此多出第 1 行的 hunk（5 个，本该是 4 个）。运行时没有影响，但违反了 R1 第 1 条「page.tsx 其余一字不动」。

### 9.1 补回内容

只执行一次字节级前置，文件其余字节不动：

```
python3 -c "p='frontend/app/page.tsx';b=open(p,'rb').read();assert not b.startswith(b'\xef\xbb\xbf');open(p,'wb').write(b'\xef\xbb\xbf'+b)"
```

### 9.2 自检（全部前台执行）

- `head -c3 frontend/app/page.tsx | xxd -p` → `efbbbf`。
- `git diff HEAD -- frontend/app/page.tsx | grep -c '^@@'` → `4`。
- `cd backend && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_empty_states_*.py` → `52 passed`，0 failed，0 skipped。
- 补回后的快照：`(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256 | cut -c1-16` = `0705c76b88785496`。

R2 只改了 `frontend/app/page.tsx` 的字节 0–2 与本报告；未做 git 写操作，未跑 build、未起服务器、未用浏览器、未调用 subagent / subagent_fork / workflow。
