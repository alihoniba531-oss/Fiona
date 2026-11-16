# 讨论群第二期（界面）独立复核

复核对象：基线 `acd04b6` 上叠加的待审改动（已跟踪文件的 diff 加未跟踪文件清单），规格 `docs/tasks/2026-11-15-agent-group-ui/02-spec.md`（含 v1.1、v1.2 修订）与一期规格 `docs/tasks/2026-11-14-agent-group/02-spec.md`。结论只依据落盘的代码和我自己跑出来的结果；实现方报告只当线索。真实浏览器里的数值采信 `.cache/review/gate-evidence.md`。

## 1. 结论

**不通过。** 有 4 项必须修复：

1. 插话之后，下一次轮询会跳过引擎在上一次轮询与插话之间发出的消息（群聊里永久少消息，直到整页重新加载）。
2. 新建页里自定义成员的模型下拉默认显示「千问 3.8 Max」，实际跑的是 DeepSeek Flash，而且选不了千问。
3. 方案只读视图不显示自定义调研成员的分工。
4. 字重守卫抓不住带属性的 `<strong …>` / `<b …>` 和 `[font-weight:…]`。

其余部分（入口、抽屉、后端 `answers`、状态判断、文档渲染与安全、布局修订）核验通过。

## 2. 验收标准逐条核验

### 2.1 机械验收（规格第 8 节）

| 项 | 结果 | 证据 |
|---|---|---|
| 1 lint | 通过 | 在 `frontend/` 跑 `npm run lint -- --max-warnings=25`：`✖ 25 problems (0 errors, 25 warnings)`，退出码 0。只对讨论群文件和 `components/Sidebar.tsx` 跑 `npx eslint`：无输出，退出码 0，所以讨论群文件没有新增警告 |
| 2 类型检查 | 通过 | `npx tsc --noEmit` 无输出，退出码 0 |
| 3 构建 | 未复跑 | 派单只让跑 lint 与 tsc；采信门禁证据（路由表有 `/discuss`、`/discuss/new`、`/discuss/[id]`） |
| 4、5 用例 | 通过 | 派单给的命令（`test_discuss_frontend_*.py test_discuss_ui_api.py test_ui_polish_page_contracts.py test_ui_closeout_dialog_scrim.py test_studio_frontend_*.py`）：`105 passed`。一期 7 个讨论群后端文件：`210 passed`。`test_discuss_docs.py test_claude_agent_docs.py test_novel_p2_frontend.py`：`81 passed`。新用例共 46 条（`--collect-only`），0 跳过 |
| 6 全量 | 未跑 | 按派单要求不跑 |
| 7 改动范围 | 通过 | `git status --porcelain --untracked-files=all`：只有规格 4.1 两张表里的文件、两份授权的既有测试、`docs/tasks/2026-11-15-agent-group-ui/` 与 `.cache/` |

### 2.2 约束（规格第 3 节）

| 约束 | 结果 | 证据 |
|---|---|---|
| 不新增依赖 | 通过 | `package.json`、`package-lock.json`、`requirements*.txt` 都不在 diff 里 |
| 界面文字不加粗 | 代码通过，守卫有洞 | 在讨论群新文件里 grep `font-(medium\|semibold\|bold\|extrabold\|black)\|font-\[\|fontWeight\|font-weight\|<b[ >]\|<strong\|dangerouslySetInnerHTML`：零命中；`th` 带 `font-normal`（`frontend/components/discuss/DiscussDocument.tsx:182`）；标题用的 `h3`–`h5` 由 Tailwind 预置样式继承字重。守卫本身的漏洞见必须修复 4 |
| `backend/discuss/` 只改一处 | 通过 | `git diff backend/discuss/service.py` 只有 `:610-611` 两行 |
| 既有测试只改两份授权的 | 通过 | `git diff --stat` 里只有 `backend/tests/test_ui_polish_page_contracts.py`（`DRAWER_IDS` 加 `"discuss"`、计数 6→7、函数名 six→seven、新增一行顺序断言）与 `backend/tests/test_ui_closeout_dialog_scrim.py`（`expected_count` 14→15），与 `05-fix-r1.md` A、B 写明的完全一致；新增的原生 `<dialog` 只有 `frontend/components/discuss/DiscussDialogs.tsx:46` 一个 |
| 侧栏不自己请求、手机底栏六项 | 通过 | `frontend/components/Sidebar.tsx` 没有引入 `@/lib/discuss`；替身只放行 `/api/strawberry` 与 `/api/studio/access`；底栏过滤在 `Sidebar.tsx:152`；用例 `test_mobile_tabbar_stays_six_links_without_discuss` |
| 提交的文件里没有本机路径或隐私 | 基本通过 | 扫新文件、四份文档与 `docs/tasks/2026-11-15-agent-group-ui/`：没有用户目录、邮箱、密钥、内网地址。只有 `docs/tasks/2026-11-15-agent-group-ui/07-fix-r3-tests.md:47` 一处指向系统临时目录的绝对路径（变异脚本 `r2_mutation.py`，见可优化 9） |
| 文档只新增、字节数 | 通过 | `CLAUDE.md` 68,922 字节（≤69,300）；第一期一节 1,133 字节（≤1,800）；第二期一节由守卫量（≤700）；`test_discuss_docs.py` 通过，第一期固定短语都在 |

### 2.3 规格 4.2 入口：书签与抽屉

| 要求 | 结果 | 证据 |
|---|---|---|
| 三个新属性，`=== true` 才追加，排在工作室之后 | 通过 | `Sidebar.tsx:117-122`；`test_discuss_bookmark_is_appended_last_only_when_allowed` |
| `navItems` 仍六项、底栏不显示 | 通过 | `test_sidebar_source_has_no_discuss_request_helper`；`Sidebar.tsx:152` |
| 高亮、`aria-controls`、`aria-expanded` | 通过 | `Sidebar.tsx:124-130`；两条高亮用例 |
| 书签区滚动、不显示滚动条 | 通过 | `Sidebar.tsx:133`（`[scrollbar-width:none]!`）、`:141`（底部块 `shrink-0`）；门禁 C 的实测数值 |
| 主页类型、访问检查、作废旧请求、不允许时关抽屉 | 通过 | `frontend/app/page.tsx:484`、`:681-697`（与工作室那段同构） |
| 抽屉外壳、iframe 只在允许时挂、`key={username}`、关闭后不卸载 | 通过 | `page.tsx:3095-3124` |
| 打开聚焦、关闭还焦点 | 通过 | `page.tsx:549-553`；`focusVisibleDrawerTrigger("discuss-drawer")` |
| `fiona-discuss-close` 同时核对 `origin` 与 `source` | 通过 | `page.tsx:580-589`；变异 M26 被用例抓到 |

### 2.4 规格 4.3 后端 `answers`

通过。`backend/discuss/service.py:610-611`：字符串原样返回，否则空字符串。`backend/tests/test_discuss_ui_api.py` 三条用例覆盖默认、往返、六种非字符串；变异 M33（非字符串原样透出）、M34（恒为空串）都被断言失败抓到。

### 2.5 规格 4.4 `frontend/lib/discuss.ts` 与后端返回形状

逐个类型对照后端：

- `DiscussSummary` 对 `service.py:336-349` 的 `_summary`；`DiscussMember` 对 `:352-389`（调研成员带 `focus`，固定席位的 `does` 是身份设定）；`DiscussMessage` 对 `:581-591`；`DiscussDetail` 对 `:593-616`（含 `answers`、`reserved_strawberries`、`plan_revision`）；`DiscussOutputSummary.words` 对 `backend/discuss/store.py:499-510`；`DiscussOutput` 对 `service.py:979-986`；`DiscussSource` 对 `:965-969`；`DiscussCatalog` 对 `:396-440`。验收载荷的字段名（`verdicts[].id/pass/evidence`、`citation_issues[].quote/problem`、`rework`）与 `backend/discuss/schemas.py:413-451` 和 `engine.py:750-761` 一致。
- 请求：`pause`、`accept`、`close` 不带请求体，与 `backend/routers/discuss.py` 里这三个路由不收请求体一致；`resume`、`continue` 的请求体与 `ResumeGroup`、`ContinueGroup` 一致；群 ID 一律 `encodeURIComponent`（`discuss.ts:373`）；列表与详情带 `cache: "no-store"`；导出校验 `text/markdown` 并解析 `filename*=UTF-8''…`（`discuss.ts:438-468`），与路由的 `Content-Disposition` 写法一致。
- 唯一不一致：目录的 `defaults` 只有固定席位、八个角色池代号和 `avatar`（`service.py:413-415`），没有 `general`；`discuss.ts:276-280` 的注释和 `DiscussCreateForm.tsx:188` 都假定它存在。后果见必须修复 2。

### 2.6 规格 4.5 `discussLogic.ts`（对照一期 4.5 状态与 4.6 流程）

- `discussStatusLabel`、`discussStopHint`（`discussLogic.ts:21-94`）：一期 4.5 的 8 个状态、`paused` 的 7 个原因、`done` 的两个原因一一对上，不认识的状态原样返回。
- `discussActions`（`:109-145`）：界面给出的每个按钮，后端在该状态下都接受——`pause` 只在 `planning`/`running`（`service.py:790`），`resume` 在 `paused`/`failed`（`:810`），`continue`/`rework` 在 `awaiting_user`/`done`（`:850`），`accept` 在 `awaiting_user`/`paused` 且有成果（`:907-910`），`close` 不在 `planning`/`running`（`:930`）。没有会必然 409 的按钮。`done` 不给 `close`、`failed` 不给 `accept` 是规格的取舍。
- `applyPendingNotes` 依据的「未读插话永远是最新那几条」成立：开工与两个读取点都一次读走全部未读（`store.py:394-401` 的 `claim_notes`）。
- `splitDiscussDocument`、`splitDiscussCitations`、`safeExternalUrl`、`validateDiscussCreate`、`buildDiscussCreateBody`、`buildDiscussPlanPatch`、`discussPlanPatchIsEmpty`、`discussErrorMessage`、`discussHref`、`discussModelLabel`：逐条对照规格 4.5 第 1–20 条一致；15 处逻辑变异（M01–M15）全部被断言失败抓到。
- 只有 `import type`：守卫 `test_discuss_logic_only_imports_types`；Node 转译时 `require` 一律抛错，有运行时依赖会直接失败。

### 2.7 规格 4.6–4.8 外壳、列表、新建

| 要求 | 结果 | 证据 |
|---|---|---|
| 嵌入时不显示侧栏与背景，独立页 `<Sidebar discussAccessAllowed />` | 通过 | `frontend/components/discuss/DiscussShell.tsx:20` |
| Esc 关闭走 `canCloseNovelDrawer`，目标源是本站 | 通过 | `DiscussShell.tsx:8-17` |
| 身份加载、未登录（嵌入时 `target="_top"`）、403/404、其他失败、`key={owner}` | 通过 | `DiscussShelf.tsx:14,70-71`、`DiscussCreateForm.tsx:79,139-146`、`DiscussRoom.tsx:121-133,606-638` |
| 列表页头、空状态不重复新建按钮、卡片内容、嵌入时「在新页面打开」 | 通过 | `DiscussShelf.tsx:56-90` |
| 列表轮询（有进行中的群且页面可见，3 秒） | 通过 | `DiscussShelf.tsx:41-53`（与 `NovelShelf.tsx` 同款写法） |
| 新建：目录驱动、目录失败不显示表单、表单项与文案、提交前校验、防重复提交、成功带 `embed` 跳转、失败保留内容 | 通过 | `DiscussCreateForm.tsx:96-124,144-146,214-237,278,370,420,422` |
| 新建：各成员模型的默认值取目录 | **不通过** | 自定义成员没有取到目录默认值，见必须修复 2 |

### 2.8 规格 4.9 群聊页

| 要求 | 结果 | 证据 |
|---|---|---|
| 顶栏三行、主操作在左且第一个 `btn-primary`、右侧 `btn-quiet`/`btn-danger`、进行中全部禁用并显示「…中」 | 通过 | `DiscussRoom.tsx:653-697` |
| 开工：有未保存修改时拦截并切到方案；409 提供「重新加载方案」 | 通过 | `DiscussRoom.tsx:481-494,405-407,441-461` |
| 继续（预算对话框）、追加轮数、按意见返工（无插话时提示、切群聊、聚焦插话框）、接受/结束/删除确认框文案、导出文件名 | 通过 | `DiscussRoom.tsx:498-558,415-439,859-893`；`DiscussDialogs.tsx` |
| 首次读取分页到少于 200 条 | 通过 | `DiscussRoom.tsx:183-224` |
| 轮询：进行中且可见才读、隐藏停、可见立刻读、操作中不覆盖、失败只出一行 | 通过 | `DiscussRoom.tsx:246-290,717-719` |
| 轮询的 `after` 取已有消息里最大的 ID | **按字面做了，但与插话合起来会丢消息** | 见必须修复 1 |
| 404 显示「讨论群不存在」与「返回列表」 | 通过 | `DiscussRoom.tsx:614-620` |
| 宽窄布局、`ResizeObserver` 量内容区、宽屏标签条只在右栏 | 通过 | `DiscussRoom.tsx:369-379,731-739`；门禁 E/F/G/H/J 的实测数值 |

### 2.9 规格 4.10 群聊标签

成员条、工作中图标与「…正在工作…」/「正在安排下一步…」、按轮分组、插话底色与「已读到/还没读到」、空状态、80px 判据与「有新消息」：`DiscussTimeline.tsx:72-205`，通过。插话框：500 字、Enter/Shift+Enter、输入法组合、空内容、防重复、`closed`/`failed` 改文字、`pending_notes`、`done`/`awaiting_start` 两句提示、失败保留输入：`DiscussComposer.tsx`，通过。偏差：「看这一版成果」没有判断 `kind === "draft"`（可优化 1）。

### 2.10 规格 4.11 方案标签

- 没有方案时两种文案（`DiscussPlanPanel.tsx:159-163`）、目标、成果形式与提纲、完成标准编号、主持人提问与「还没有回答。」、默认收起的原始诉求（`:630-686`）：通过。
- 成员与分工：**不通过**，自定义调研成员的分工不显示（必须修复 3）。
- 编辑：只在 `awaiting_start`（`:380-391`）、目录失败时不能进入并给「重新加载」（`:392-394`）、可改的字段齐全、空 PATCH 直接退出（`:265`）、409 给「重新加载方案」并丢弃本地修改（`:283,290-310`）、422 留在编辑、离开标签不丢（面板常驻、只用 `hidden` 切换）：通过。

### 2.11 规格 4.12 成果与来源

成果：空状态、版本下拉/单版文字、轮次、字数（与后端同按码点计）、验收标签、导出与「导出的是最新一版」、验收明细（未通过默认展开、坏条目跳过）、正文 720px、切换版本的加载与失败、「有新的一版」只在看的是之前最新版时出现：`DiscussOutputPanel.tsx:103-317`，通过。来源：进入时请求一次、进行中每次打开标签重请求（`DiscussRoom.tsx:331-347`）、空状态、编号/标题/站点、安全链接、「只看成果引用到的」与「共 n 条」：`DiscussSourcesPanel.tsx`，通过。

### 2.12 规格 4.13 文档渲染与安全

- 先拆块、普通块交 `parseMessageMarkdown`、标题与着重不加粗、表格细线、所有文字过 `splitDiscussCitations`：`DiscussDocument.tsx:17-229`，通过。
- 注入路径：所有模型文字都作为 React 文本节点或由 React 转义的属性（`title`）输出；新文件里没有 `dangerouslySetInnerHTML`（守卫加 grep）。
- 外链：编号链接（`DiscussDocument.tsx:23-36`）与来源列表（`DiscussSourcesPanel.tsx:68,78`）都先过 `safeExternalUrl`，只放行 `http:`/`https:`（变异 M07 被抓）；所有 `target="_blank"` 都带 `rel="noopener noreferrer"`（守卫，变异 M17 被抓）；「在新页面打开」是站内 `/discuss`。
- 未知编号补请求、同一时刻只发一个：`DiscussRoom.tsx:349-367`，带签名去重，不会循环请求。
- `postMessage`：子页只发 `{ type }`，目标源是本站（`DiscussShell.tsx:13`）；主页核对来源（2.3）。
- 前端与文档里没有写账号、密钥或本机路径。

### 2.13 规格 4.14 文档

四份文档都有「讨论群界面（第二期）」，内容与实现相符；`CLAUDE.md` 一节只写入口文件与两条约定。一处说法不准，见可优化 8。

### 2.14 v1.1、v1.2 修订

| 条目 | 结果 | 证据 |
|---|---|---|
| v1.1-1 两份既有测试的例外 | 通过 | 见 2.2 |
| v1.1-2 `th` 写 `font-normal` | 通过 | `DiscussDocument.tsx:182`；守卫；变异 M32 被抓 |
| v1.1-3 表格跟容器走、自动换行 | 通过（作者已记下 `table-fixed` 的取舍） | `DiscussDocument.tsx:174-175`；门禁 D |
| v1.1-4 第一次显示停在最新、开发模式两遍 effect 仍成立 | 通过 | `DiscussTimeline.tsx:77-88`：rAF 在 cleanup 里取消，成功滚动后才把「第一次」标记清掉；严格模式第一遍被取消、第二遍执行；门禁 E |
| v1.1-5、v1.2-1、v1.2-2 高度、底部留白、最小高度 | 通过 | `DiscussShell.tsx:21-22`、`DiscussRoom.tsx:654,731-773`、`DiscussTimeline.tsx:143,161-166`；门禁 H/J 的九条判据 |
| v1.1-6 宽布局标签条在右栏 | 通过 | `DiscussRoom.tsx:739` |
| v1.1-7 侧栏隐藏滚动条用带 `!` 的写法 | 通过 | `Sidebar.tsx:133` |
| v1.2-3 对话框只在点遮罩时关闭 | 通过 | `DiscussDialogs.tsx:46-63`（`<dialog>` 自身无内边距，内容层 `p-6`）；门禁第 9 条 |

## 3. 必须修复项

### 必须修复 1：插话之后，轮询会永久跳过一段引擎消息

- 现象：群在跑（`planning`/`running`）时，作者发一条插话；如果引擎在「上一次轮询」与「这条插话」之间发过消息，这些消息再也不会出现在群聊里，直到整页重新加载。
- 位置：`frontend/components/discuss/DiscussRoom.tsx:575-586`（`sendNote` 把返回的插话并进 `detailRef.current.messages`）；`:253`（`poll` 用 `maxMessageId(current.messages)` 当 `after`）；`:235`（操作完成后的 `refreshDetail` 同样如此）。后端 `backend/discuss/store.py:187` 只返回 `id > after` 的消息，`discuss_messages.id` 是自增主键（`store.py:40`），按写入先后编号。
- 为什么是问题：插话的 ID 大于它之前写入、但前端还没读到的引擎消息的 ID。插话并入后本地最大 ID 变成插话的 ID，下一次 `after` 就越过了那几条引擎消息。规格 4.9「读取与轮询」第 2 条（`after` 取已有消息里最大的 ID）和 4.10 插话框第 5 条（把返回的消息并进列表）各自没错，合在一起就丢消息。插话本来就是在讨论进行中用的（规格第 1 节第 3 条），每一步模型调用要几十秒，轮询间隔 3 秒，这个窗口在正常使用里会碰到。
- 复现（我在副本里用临时用例实测过，跑完已删除）：建群并等到 `awaiting_start`，`GET …?after=0` 得到最大 ID 1；直接往库里写一条引擎消息（ID 2）；`POST …/notes` 返回 ID 3；`GET …?after=3` 返回 `[]`，`GET …?after=1` 返回 `['引擎在两次轮询之间发的消息', '我插一句话']`。
- 建议：维护一个只由服务器读回的消息列表推进的游标（`loadInitial`、`poll`、`refreshDetail`、`reloadPlan` 各自取「旧游标」与「本次返回消息的最大 ID」中较大的；方案 PATCH 返回的是 `after=0` 的前 200 条，也只取较大值），`sendNote` 并入插话但不推进游标；所有 `getDiscussGroup(id, after)` 的 `after` 都用这个游标。插话会在下一次读取时再回来一次，`mergeDiscussMessages` 去重并以服务器版本为准。把「下一次 `after` 怎么算」写成 `discussLogic.ts` 的纯函数，并加用例：游标 1，本地并入 ID 3 的插话后，下一次 `after` 仍是 1。

### 必须修复 2：新建页自定义成员的模型默认显示千问，实际跑 DeepSeek，且选不了千问

- 现象：「我来组队」里添加自定义成员后，「更多设置 → 各成员的模型」里它的下拉显示「千问 3.8 Max」。作者不动它，建群后这位成员用的是 DeepSeek Flash；作者想要千问，下拉本来就停在千问，选不出变化，也就发不出去。
- 位置：`frontend/components/discuss/DiscussCreateForm.tsx:188`（`catalog.defaults.general ?? catalog.models[0]?.id`，目录里没有 `general`，于是回落到 `models[0]`，即千问）；`buildDiscussCreateBody` 只在 `model !== default_model` 时带上（`frontend/lib/discussLogic.ts:389-394`），两者都是千问，所以不带；后端没收到时用 `_model_for` 的回落 DeepSeek（`backend/discuss/service.py:245-250`）。注释 `frontend/lib/discuss.ts:276-280` 写的「通常取 `catalog.defaults.general`，也就是 DeepSeek Flash」与目录实际形状不符。
- 实测（Node 里转译真实的 `discussLogic.ts`，目录形状照 `service.py:396-440`）：下拉显示「千问 3.8 Max」；不改时请求体 `models` 为 `undefined`；改成 DeepSeek 再改回千问，请求体 `models` 仍是 `undefined`。
- 为什么是问题：违反规格 4.8 第 6 条「默认值取目录的 defaults」的本意，界面显示的模型与实际调用的模型不一致（不同模型的价目不同，作者据此估算花费），且作者无法在建群时为自定义成员选千问。
- 建议：自定义成员的默认模型取目录里角色池成员的默认值（`catalog.roles` 中 `kind === "lens"` 的任一 `id` 在 `catalog.defaults` 里的值，现在都是 DeepSeek Flash，与后端回落一致）；把这个取值写成 `discussLogic.ts` 的纯函数并加用例（用 `service.py:catalog()` 的真实形状断言返回 `deepseek:deepseek-flash`）；同步改正 `discuss.ts` 的注释。

### 必须修复 3：方案只读视图不显示自定义调研成员的分工

- 现象：作者自己组队带了自定义成员，主持人立项后给每位成员写了分工；方案标签的「成员与分工」里，角色池成员显示「分工：…」，自定义成员不显示。
- 位置：`frontend/components/discuss/DiscussPlanPanel.tsx:371`，条件是 `member.kind === "lens" && !!member.focus`。后端对自定义调研成员返回 `kind: "custom"` 且带 `focus`（`backend/discuss/service.py:253-254,363-373`）。
- 为什么是问题：规格 4.11 第 4 条「分工（`focus`，调研成员才有）」；自定义成员就是调研成员（一期规格 4.4「调研成员 … 自定义：`role` 是 `custom1`…」）。开工前看不到主持人给自定义成员派的分工，只能进编辑模式才看得到。
- 建议：条件改成 `(member.kind === "lens" || member.kind === "custom") && !!member.focus`（或只看 `focus` 非空）。

### 必须修复 4：字重守卫抓不住带属性的标签和任意属性写法

- 现象：在 `DiscussOutputPanel.tsx` 里把 `<span className="…">有新的一版</span>` 改成 `<strong className="…">…</strong>`（变异 M18），或给它加 `[font-weight:600]`（变异 M19），67 条相关用例全部通过。
- 位置：`backend/tests/test_discuss_frontend_guards.py:26-38`，`<b>`、`<strong>` 按字面整串匹配，只能抓到不带属性的写法；没有覆盖 `font-weight`。
- 为什么是问题：规格 3.3 明确禁止 `<b>`、`<strong>`，「界面文字不加粗」是作者跨任务的硬约束；守卫对最可能出现的写法（带 `className` 的 `<strong>`）抓不住，等于这条约束没有用例保护。
- 建议：正则改成匹配 `<(?:b|strong)\b`，再加上 `font-weight`（同时覆盖 `[font-weight:…]` 与内联样式）；在用例里先对一段含 `<strong className="x">` 和 `[font-weight:600]` 的样例文本断言正则能命中，证明守卫真能抓到，再扫描真实文件。

## 4. 可优化项（12 项）

1. 「看这一版成果」只看 `payload.version`，没判断 `kind === "draft"`（`frontend/components/discuss/DiscussTimeline.tsx:24-27,41`）。现在只有成稿消息的载荷带 `version`（`backend/discuss/engine.py:699`），没有实际影响，但与规格 4.10 第 4 条不一致。
2. 轮询在「请求在途时切换页面可见性」会叠出第二条定时链：`onVisibility` 直接调 `tick()`，在途那一轮结束后各自 `schedule()`，`timer` 变量被覆盖（`DiscussRoom.tsx:265-290`，`DiscussShelf.tsx:41-53`）。两条链互相作废请求，功能不错但请求翻倍。与 `NovelWorkbench.tsx`、`NovelShelf.tsx` 同款写法，可一起改（加一个「在途」标记）。
3. 插话发送中把输入框设成 `disabled`（`DiscussComposer.tsx:95`），浏览器会把焦点移走；发送后焦点不回输入框，键盘用户要从头 Tab 回来，此时按 Esc 会关掉抽屉。建议发送中用 `readOnly`，或发送成功后把焦点放回输入框。
4. 渲染路径没有用例钉住 `safeExternalUrl`：把编号链接改成直接用 `source.url`（变异 M16）不会让任何用例变红。现在代码是对的，但这是安全相关路径，建议加一条守卫：讨论群部件里每个带 `target="_blank"` 的标签，`href` 都来自 `safeExternalUrl` 的返回值。
5. 窄布局下停在别的标签时到达的新消息，回到群聊既不提示「有新消息」，位置也不在最新（`DiscussTimeline.tsx:95-102`，隐藏时只更新了 `lastMessageIdRef`）。建议隐藏期间有新消息时，回来后显示「有新消息」按钮。
6. 进入「修改方案」但没改任何字段时可以直接开工，开工后面板仍停在编辑态（`DiscussPlanPanel.tsx:396` 只看 `editing`），这时点「保存修改」只会得到 409。建议状态离开 `awaiting_start` 时退出编辑。
7. 方案编辑里新增的自定义成员没有模型下拉（`DiscussPlanPanel.tsx:320-322` 只列有 `role` 的成员）；清空某位成员的名字或职责时只得到后端笼统的「成员内容不合法」（`backend/discuss/service.py:112-122`）。可在前端先给出具体提示。
8. `README.md` 新增一节最后一句「访问检查通过才会出现书签，否则显示「暂未开放」」不准：检查不通过时书签根本不出现；独立页显示的是「讨论群尚未开放」或「你的账号暂未开通讨论群」。
9. 任务文档：`docs/tasks/2026-11-15-agent-group-ui/07-fix-r3-tests.md:47` 写了一个指向系统临时目录的绝对路径（变异脚本 `r2_mutation.py`），建议改成「仓库外的临时目录」；`impl/report.md` 第 2 节 4.2 末条与第 6 节前两条（`"drawer" + "-panel"` 拼接、`role="dialog"` 手写弹层）已被返修 1 推翻，仍按现状陈述。建议在报告里加一句「已被返修 1 取代」。
10. 来源面板每次重新请求都整张换成「正在加载来源…」，请求失败时已有的列表也被换成报错（`DiscussSourcesPanel.tsx:40-41`）；进行中补请求较频繁时会闪。可在已有数据时保留列表，只在旁边提示。
11. `splitDiscussDocument` 只认行首的三个反引号（`discussLogic.ts:242`），`parseMessageMarkdown` 认 0–3 个空格缩进（`frontend/lib/messageMarkdown.ts:16`）。缩进的围栏里出现像表格的行时，会被拆成表格，前后两段各自变成没闭合的代码块。罕见，可让两边判据一致。
12. 窄布局下群聊是两层同名区域：外层 `section aria-label="群聊"`（`DiscussRoom.tsx:763-765`）里又套一层 `section aria-label="群聊"`（`DiscussTimeline.tsx:143`），读屏会念两遍。可去掉内层的名字。

## 5. 需要在浏览器里补测的项（9 项）

1. **插话丢消息（必须修复 1 的现场确认与修后回归）**：抽屉，1440×900，一个 `running` 的群停在群聊标签。在某条引擎消息刚出现在服务器、前端还没轮询到时（可在开发者工具里把轮询请求临时阻塞 3 秒）发一条插话。修前：那条引擎消息不出现；修后：下一次轮询它出现在插话之前，且不重复。
2. **新建页自定义成员模型（必须修复 2 的回归）**：`/discuss/new`，「我来组队」加一位自定义成员，展开「更多设置」。修后下拉默认显示「DeepSeek Flash」；选千问建群后，方案标签里这位成员显示「模型：千问 3.8 Max」。
3. **插话后的焦点**：抽屉群聊标签，在插话框里输入后按 Enter。看 `document.activeElement` 是否还在插话框；如果不在，再按 Esc，抽屉是否被关掉。
4. **矮屏侧栏书签的高度**：主页，1280×620，工作室与讨论群都有权限。书签按钮带 `min-h-16`，书签区现在是滚动容器，三字书签（「工作室」「讨论群」）可能被压到 64px（视口 1200 高时约 79px）。量每个 `.bookmark-nav` 的 `offsetHeight` 与文字的 `getClientRects()`：文字不越出按钮、相邻两个按钮的文字不重叠。
5. **多列表格**：成果里放一张 8 列以上、单元格有长句的表格，抽屉宽度（1280 与 1440）。`table-fixed` 下表格不会横向滚动，看每列是否窄到只剩两三个字一行、是否还能读；规格 v1.1 第 3 条要求「列太多时才横向滚动」。
6. **可见性切换叠出的轮询**：抽屉里一个 `running` 的群，在一次轮询请求在途时快速切走再切回标签页三次，之后在网络面板里数每 3 秒的 `GET /api/discuss/groups/{id}` 次数（应为 1）。
7. **别的标签期间到达的新消息**：抽屉 1280×900（窄布局），停在群聊最底，切到成果标签，等两条新消息到达后切回群聊：位置与是否出现「有新消息」。
8. **对话框关闭后的焦点去向**：抽屉里 `paused/budget` 的群点「继续」，在对话框里提交成功。成功后「继续」按钮会消失（状态变成进行中），看焦点落在哪里，键盘能否继续操作。
9. **长时间轮询的开销**：230 条以上消息的群在进行中，用性能面板录 30 秒，看每次轮询后的重渲染（每条消息的 Markdown 都会重新解析）是否出现超过 50ms 的长任务。

## 6. 给执行者的二次修改指令

只改下面写到的文件；界面上的中文文案不改；既有测试一字不改；不装依赖、不提交 git、不用 `git stash`/`git checkout` 还原。

1. 必须修复 1（`frontend/components/discuss/DiscussRoom.tsx`、`frontend/lib/discussLogic.ts`、`backend/tests/test_discuss_frontend_logic.py`）：引入只由服务器读回的消息列表推进的游标，`poll`、`refreshDetail`、`reloadPlan` 的 `after` 都用它；`sendNote` 并入插话但不推进游标；方案 PATCH 的返回只取较大值。游标计算写成纯函数并加用例（游标 1、并入 ID 3 的插话后下一次 `after` 仍为 1；服务器返回 2、3 后游标为 3）。
2. 必须修复 2（`frontend/components/discuss/DiscussCreateForm.tsx`、`frontend/lib/discussLogic.ts`、`frontend/lib/discuss.ts` 的注释、`backend/tests/test_discuss_frontend_logic.py`）：自定义成员的默认模型取目录里角色池成员的默认值，写成纯函数并用 `backend/discuss/service.py` 里 `catalog()` 的真实形状测它返回 `deepseek:deepseek-flash`。
3. 必须修复 3（`frontend/components/discuss/DiscussPlanPanel.tsx`）：只读视图里自定义调研成员也显示「分工：…」。
4. 必须修复 4（`backend/tests/test_discuss_frontend_guards.py`）：守卫匹配 `<(?:b|strong)\b` 和 `font-weight`；先对样例文本自检能命中，再扫描真实文件。
5. 自检：把上面每一处改回原样，确认对应用例是断言失败（`failed`），把输出摘要写进报告；再跑 `npm run lint -- --max-warnings=25`、`npx tsc --noEmit`、`npm run build` 与派单里的 pytest 命令。可优化项不要求本轮处理；如果顺手改了，逐条写明。

## 7. 变异与结果

做法：临时脚本放在仓库外，逐处做唯一匹配的字符串替换，跑相关用例（前端类变异跑 `test_discuss_frontend_logic.py`、`test_discuss_frontend_guards.py`、`test_discuss_frontend_navigation.py`、`test_ui_polish_page_contracts.py`、`test_ui_closeout_dialog_scrim.py`、`test_studio_frontend_navigation.py`，共 67 条；后端类跑 `test_discuss_ui_api.py`），再用原始字节写回。结束后对 16 个被改过的文件做 SHA-256 比对，全部与改前一致。另做过一个临时后端用例（必须修复 1 的复现），跑完已删除。

| 编号 | 文件 | 改坏方式 | 结果 | 抓到它的用例 |
|---|---|---|---|---|
| M01 | `discussLogic.ts` | `paused` 有成果时不给 `accept` | 抓到（failed） | `test_actions_for_all_states_and_output_versions` |
| M02 | `discussLogic.ts` | `export` 门槛 `>= 1` 改 `>= 0` | 抓到（failed） | 同上 |
| M03 | `discussLogic.ts` | 未读插话按 ID 升序取（标成最旧的几条） | 抓到（failed） | `test_apply_pending_notes_marks_latest_user_messages_unread` |
| M04 | `discussLogic.ts` | 合并时旧值覆盖新值 | 抓到（failed） | `test_merge_messages_dedupes_by_id_sorts_and_keeps_inputs_untouched` |
| M05 | `discussLogic.ts` | 围栏代码块不再生效 | 抓到（failed） | `test_split_document_tables_fences_padding_and_plain_text` |
| M06 | `discussLogic.ts` | 编号放宽到 1–5 位 | 抓到（failed） | `test_split_citations_accepts_only_four_digit_uppercase_ids` |
| M07 | `discussLogic.ts` | 除 `javascript:` 外都放行 | 抓到（failed） | `test_safe_external_url_only_allows_http_and_https` |
| M08 | `discussLogic.ts` | `picks` 总是整份带上 | 抓到（failed） | `test_build_plan_patch_only_sends_changed_fields` |
| M09 | `discussLogic.ts` | 自定义成员模型键按总成员数编号 | 抓到（failed） | `test_build_create_body_members_models_and_identities` |
| M10 | `discussLogic.ts` | 任何 404 都当「尚未开放」 | 抓到（failed） | `test_error_message_reads_plain_properties_only` |
| M11 | `discussLogic.ts` | `closed` 有成果时不默认停在成果 | 抓到（failed） | `test_default_tab_for_each_rule` |
| M12 | `discussLogic.ts` | 未知暂停原因的提示不再为空 | 抓到（failed） | `test_stop_hints_cover_every_status_and_pause_reason` |
| M13 | `discussLogic.ts` | 标题总是带上 | 抓到（failed） | `test_build_plan_patch_only_sends_changed_fields` |
| M14 | `discussLogic.ts` | 回答永远不带 | 抓到（failed） | 同上 |
| M15 | `discussLogic.ts` | 未读数接受字符串与小数 | 抓到（failed） | `test_apply_pending_notes_marks_latest_user_messages_unread` |
| M16 | `DiscussDocument.tsx` | 编号链接不过 `safeExternalUrl` | **存活** | 无（可优化 4） |
| M17 | `DiscussSourcesPanel.tsx` | 来源链接去掉 `rel` | 抓到（failed） | `test_target_blank_tags_carry_noopener_noreferrer` |
| M18 | `DiscussOutputPanel.tsx` | 加 `<strong className=…>` | **存活** | 无（必须修复 4） |
| M19 | `DiscussOutputPanel.tsx` | 加 `[font-weight:600]` | **存活** | 无（必须修复 4） |
| M20 | `DiscussRoom.tsx` | 轮询 `after` 恒为 0、操作中也覆盖 | 存活 | 无（组件行为，靠浏览器） |
| M21 | `DiscussRoom.tsx` | 去掉轮询的 `mutating` 判断 | 存活 | 无（组件行为） |
| M22 | `DiscussRoom.tsx` | 去掉「有未保存修改时不开工」 | 存活 | 无（组件行为；首轮走查验过） |
| M23 | `DiscussComposer.tsx` | 去掉输入法组合判断 | 存活 | 无（组件行为） |
| M24 | `DiscussDialogs.tsx` | 点对话框任何位置都关闭 | 存活 | 无（组件行为；门禁第 9 条验过） |
| M25 | `DiscussShell.tsx` | `postMessage` 目标源改 `"*"` | 存活 | 无（只发 `{ type }`，风险低） |
| M26 | `app/page.tsx` | 关闭消息不核对 `event.source` | 抓到（failed） | `test_page_discuss_close_message_checks_origin_and_source` |
| M27 | `Sidebar.tsx` | 手机底栏不排除讨论群 | 抓到（failed） | `test_mobile_tabbar_stays_six_links_without_discuss` |
| M28 | `app/page.tsx` | 不允许或失败时不关抽屉 | 抓到（failed） | `test_page_drawer_type_and_discuss_access_scope` |
| M29 | `DiscussPlanPanel.tsx` | 空 PATCH 也发请求 | 存活 | 无（组件行为） |
| M30 | `DiscussCreateForm.tsx` | 去掉防重复提交 | 存活 | 无（组件行为；首轮走查验过双击） |
| M31 | `DiscussTimeline.tsx` | 新消息总是滚到底 | 存活 | 无（组件行为） |
| M32 | `DiscussDocument.tsx` | `th` 去掉 `font-normal` | 抓到（failed） | `test_discuss_table_headers_carry_font_normal` |
| M33 | `backend/discuss/service.py` | 非字符串回答原样透出 | 抓到（failed） | `test_detail_treats_non_string_answers_as_empty` |
| M34 | `backend/discuss/service.py` | 回答恒为空串 | 抓到（failed） | `test_patch_plan_answers_round_trips_through_detail` |

小结：34 处变异，22 处被抓、12 处存活。纯函数、导航、主页源码契约、后端接口这四类用例对它们负责的逻辑有区分力（对应的 22 处全部以断言失败被抓，没有 `error`）；守卫里字重一条有洞（M18、M19）。组件内部行为（M20–M25、M29–M31）规格第 6 节没有要求用例覆盖，只能靠浏览器核验，已列入第 5 节或由门禁走查覆盖。
