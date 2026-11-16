# 讨论群第二期：界面（规格 v1.0）

分级：L3（新入口、新页面、界面结构）。

作者 2026-11-15 确认按本文动工，并定了四件事（本文已按此写）：

1. 群聊页的布局：标签切换，内容区够宽时自动两栏（4.9）。
2. 来源编号点了之后直接在新标签页打开原文（4.13）。
3. 除主页和讨论群自己的页面外，其他独立页面的侧栏先不显示「讨论群」书签，不为此改动既有测试（4.2）。
4. 其余按 v0.1 草稿，不改。

## v1.1 修订（2026-11-15，依据首轮门禁与真实浏览器走查）

以下各条覆盖正文里与之不同的说法。

1. **既有测试的两处例外（作者 2026-11-15 定）。** 第 3 节第 6 条「既有测试一字不改」有且只有这两处例外，改动范围写死在返修单 `05-fix-r1.md` 里：
   - `backend/tests/test_ui_polish_page_contracts.py`：抽屉名单加上讨论群，`drawer-panel` 的计数从 6 改成 7，并断言讨论群抽屉排在工作室抽屉之后。主页源码里直接写完整的 `drawer-panel` 类名，不再拆开拼接。
   - `backend/tests/test_ui_closeout_dialog_scrim.py`：原生对话框的个数从 14 改成加上本单新增个数之后的实际数。追加轮数、追加预算这两个对话框改用原生 `dialog`（写法照 `frontend/components/novel/NovelSettingsDialog.tsx`，类名带 `scrim-dialog`），不再手写弹层。
2. **字重。** 第 3 节第 3 条禁止的是加粗；`font-normal` 允许，而且表头 `th` 必须写上它（浏览器默认把表头加粗）。
3. **表格（4.13 第 3 条）。** 表格宽度跟着容器走，单元格里的文字自动换行；只有列太多、换行后仍放不下时才横向滚动。真实成果里两三列、带长句子的表格，在抽屉里不应该出现横向滚动。
4. **群聊第一次显示时停在最新一条（4.10）。** 不管默认选中的是哪个标签，第一次看到群聊（包括从别的标签切过来）时，消息区停在最新一条；之后在标签之间来回切换，保持离开时的位置。开发模式下 React 会把 effect 执行两遍，实现不能依赖「effect 只跑一次」。
5. **群聊的高度（4.9、4.10）。**
   - 窄布局的群聊标签：群聊面板占满顶栏与标签条以下的全部高度，页面本身不滚动，只有消息区滚动；插话框始终完整可见，默认两行高。
   - 宽布局（两栏）：左右两栏等高、占满剩余高度，各自在自己内部滚动，页面本身不滚动。
   - 窄布局的方案、成果、来源标签：照旧随页面滚动。
   - 可视高度实在太小、消息区不足 120px 时，允许退回整页滚动。
6. **宽布局的标签条（4.9）。** 两栏时，方案、成果、来源这三个标签放在右栏的上方，不横跨左栏。
7. **侧栏不显示滚动条（4.2 第 6 条）。** `frontend/app/globals.css:458-461` 有一条全局规则 `html, * { scrollbar-width: thin !important; }`，会盖过不带 `!` 的工具类。书签区隐藏滚动条的类必须用带 `!` 的写法（本项目的写法是在类名末尾加 `!`，例如同文件里的 `max-md:w-screen!`）。

## v1.2 修订（2026-11-15，依据返修 1 的真实浏览器复测）

以下各条覆盖正文与 v1.1 里与之不同的说法。v1.1 的七条在返修 1 里已全部合格，不得回退。

1. **底部留白（4.9，新增）。** 讨论群的任何一页，只要页面本身能纵向滚动，滚到底之后，最后一段内容的下边缘与可视区下边缘之间，要留着内容容器的下内边距（现在是 20px，不得小于 16px）。手机宽度下「可视区下边缘」指底部导航栏的上边缘：最后一段内容不能被导航栏挡住。
2. **消息区的最小高度（收紧 v1.1 第 5 条最后一句）。** 窄布局的群聊标签里，消息区的可视高度不得小于 120px；可视高度不够时，消息区保持 120px，页面改为可以纵向滚动，滚到底后插话框完整可见，并满足上一条。宽布局里两栏区域的高度不得小于 320px，不够时同样改为页面滚动。可视高度够用时的表现不变：页面不滚动，消息区占满剩余高度。
3. **对话框只在点遮罩时关闭。** 追加轮数、追加预算两个对话框：点在对话框方框以内的任何位置（包括内边距、控件之间的空隙）都不关闭；点方框以外的遮罩才关闭，提交中不关。

## v1.3 修订（2026-11-15，依据独立复核 `04-review.md` 与复核后的浏览器补测）

以下各条覆盖正文与 v1.1、v1.2 里与之不同的说法。v1.1、v1.2 的各条已全部合格，不得回退。

1. **读取游标（改 4.9「读取与轮询」第 2 条）。** 轮询与操作之后的补读，`after` 不再取「已有消息里最大的 `id`」，改用一个单独维护的游标：它只随「从服务器读回的消息列表」前进，每次取旧游标与这次读回的最大 `id` 中较大的；插话接口返回的那一条照旧并进列表，但不推动游标。原因：插话的 `id` 比「已经写入、前端还没读到」的引擎消息大，按本地最大 `id` 续读会永久跳过那几条。游标怎么前进写成 `discussLogic.ts` 里的纯函数。
2. **自定义成员的模型（补 4.8 第 6 条）。** 目录的 `defaults` 里没有自定义成员。新建页里自定义成员的下拉，初始值取角色池成员的默认模型（目录 `roles` 里 `kind` 为 `lens` 的成员在 `defaults` 里的值），并且**总是**把所选模型随建群请求发给后端（`models.customN`），不依赖后端的回落。界面显示的模型必须就是实际使用的模型。
3. **方案只读视图里的分工（明确 4.11 第 4 条）。** 「调研成员」包括角色池成员与自定义成员；`focus` 非空时两者都显示「分工：…」。
4. **字重守卫（明确第 6 节第 3 条）。** 守卫要抓得到带属性的 `<b …>`、`<strong …>`，以及任何写法的 `font-weight`（含 `[font-weight:600]` 这类任意属性类）。
5. **列多的表格（明确 v1.1 第 3 条）。** 每列的宽度不小于 8em；列多到容器放不下时，表格在自己的容器里横向滚动，页面不被撑宽。列少时照旧跟着容器走，不出现横向滚动。
6. **发送插话之后的焦点（补 4.10 插话框第 5 条）。** 发送成功或失败之后，焦点都留在插话框里，可以接着打字。
7. **不在群聊标签时到达的新消息（补 4.10 消息第 6 条与 v1.1 第 4 条）。** 窄布局下停在别的标签时有新消息到达，回到群聊标签时：离开前停在底部附近（距底不超过 80px）的，滚到最新；否则位置不动，显示「有新消息」按钮。

依据：第一期规格 `docs/tasks/2026-11-14-agent-group/02-spec.md`（下称「一期规格」，接口见它的 4.13，状态见 4.5，流程与消息种类见 4.6）。第一期与验收后的小单已合入 main（提交 `acd04b6`）。

## 1. 产品目标

作者在电脑上点侧栏的「讨论群」书签，打开抽屉，在里面完成这些事：

1. 看自己的群，新建一个群（写诉求、选队伍、定预算与轮数）。
2. 主持人出方案后，看方案、改方案、回答主持人的问题，然后开工。
3. 讨论进行时，看每一轮谁说了什么、谁正在干活；随时插话、暂停。
4. 停下来之后，读成果与验收结论、点开来源；接受成果、追加轮数，或写下意见让它返工；导出成果。

范围之外：

- 手机上不提供入口（作者 2026-11-14 定：书签先只在电脑上显示）。页面在窄屏下不要求打磨，只要求不报错、内容不溢出屏幕。
- 分身聊天里查看进展、任务卡、意见卡是第三期。
- 引擎、流程、提示词、计费一律不动。

## 2. 现状事实（2026-11-15 在提交 `acd04b6` 上实测）

前端：

1. 技术栈：Next 16.4.3、React 19.2.4、Tailwind v4、TypeScript 5、lucide-react。`frontend/AGENTS.md` 写明：这一版 Next 有破坏性变化，写代码前先读 `frontend/node_modules/next/dist/docs/` 里相关章节。
2. 前端没有自己的测试运行器。前端测试写在 `backend/tests/` 里，由 pytest 驱动，两种写法：
   - 在 Node 里用项目自带的 typescript 转译并执行真实的 TS 模块，例如 `backend/tests/test_desk_logic_frontend.py`（纯函数）与 `backend/tests/test_studio_frontend_navigation.py`（带一个极简的 React 替身跑 `Sidebar.tsx`）。缺 node 或缺 `frontend/node_modules` 时整组 skip。
   - 直接读源码文本做静态检查。
3. 线上检查（`.github/workflows/quality.yml`）的前端三步：`npm run lint -- --max-warnings=38`、`npx tsc --noEmit`、`npm run build`。在提交 `acd04b6` 上实测：lint 0 个错误、25 个警告；类型检查无输出；构建成功，路由表里有 `/novels`、`/novels/[id]`、`/novels/new`、`/studio`、`/studio/[id]`、`/studio/kb`。后端全量 8562 条通过（其中讨论群 210 条），0 跳过。
4. 侧栏 `frontend/components/Sidebar.tsx`：
   - `navItems` 六项：对话、分身、广场、世界、设置、书斋。
   - 「工作室」只在电脑上、且通过访问检查后追加：`studioAccessAllowed` 由主页传入；没传时侧栏自己请求 `GET /api/studio/access`。
   - 手机底栏用 `items.filter(item => item.href !== "/studio")` 去掉工作室。
   - 既有用例 `test_studio_frontend_navigation.py` 的替身对侧栏发出的每个请求做断言：除了 `/api/strawberry`，只允许 `/api/studio/access`。**所以侧栏自己不能再发别的请求**，否则这些既有用例会变红。
   - 既有用例还按源码文字做了几处断言，改动时必须保住：`navItems` 数组里恰好是这六项（`test_studio_frontend_navigation.py`、`test_novel_p2_frontend.py`）；手机底栏恰好六个链接；主页源码里有 `"studio" | "novel" | null` 这一段原文；四个抽屉的 `id` 在源码里的先后是 plaza、settings、novel、studio（`test_ui_polish_page_contracts.py`）。
5. 主页 `frontend/app/page.tsx`（3072 行）：
   - 抽屉名字的类型在 `:483`：`"agent" | "exchange" | "plaza" | "settings" | "studio" | "novel" | null`。
   - 书斋与工作室的抽屉是同一种外壳加一个 iframe（`:2998-3058`，两个抽屉的 `id` 分别在 `:3000` 与 `:3031`）：书斋 `src="/novels?embed=1"`，工作室 `src="/studio?embed=1"`、`key={username}`、只在通过访问检查后挂载，否则显示「暂未开放」。
   - 工作室的访问检查在 `:649-665`（`checkStudioAccess`，不允许时顺手关掉抽屉）。
   - iframe 里按 Esc 关闭抽屉靠 `postMessage`：主页在 `:564-573` 监听 `fiona-studio-close`，校验 `event.origin` 与 `event.source`。
6. 嵌入页的写法：`frontend/app/novels/page.tsx`、`frontend/app/novels/[id]/page.tsx`（`"use client"`、`Suspense`、`useSearchParams().get("embed") === "1"`）；外壳 `frontend/components/studio/StudioShell.tsx`；链接带 `embed=1` 用 `novelHref` / `studioHref`。
7. 可复用的部件：
   - 请求：`apiJson`、`ApiError`（`frontend/lib/agents.ts:26-45`），`apiFetch`（`frontend/lib/auth.ts`），`API_BASE`（`frontend/lib/config.ts`）。
   - 账号与请求作废：`useAccountIdentity`、`useAccountIdentityPending`、`useAccountRequest`（`frontend/lib/useAccountIdentity.ts`）。
   - 确认框 `useConfirm`（`frontend/components/ConfirmDialog.tsx`）；带表单的对话框写法见 `frontend/components/novel/NovelSettingsDialog.tsx`（原生 `dialog`）。
   - 状态部件 `ErrorNotice`、`EmptyState`、`LoadingState`（`frontend/components/novel/NovelStates.tsx`）。
   - 标签页的键盘操作 `useRovingTabs`（`frontend/lib/useRovingTabs.ts`）。
   - Markdown 解析 `parseMessageMarkdown`（`frontend/lib/messageMarkdown.ts`）：支持段落、三级以内标题、两层列表、引用、代码块、分隔线，行内支持着重与行内代码。**不支持表格，也不认识来源编号。**
   - 时间 `formatNovelDate`（`frontend/lib/novels.ts:184`）。
   - 样式类（`frontend/app/globals.css:348-370`）：`ceramic-card`、`readout`、`btn`、`btn-primary`、`btn-quiet`、`btn-danger`、`tag`；颜色用 `var(--ink)`、`var(--ink2)`、`var(--rule)`、`var(--carve)`、`var(--slip)`、`var(--seal)` 等变量；字号用 `text-fs-11` … `text-fs-30`。
8. 书斋的轮询写法：`frontend/components/novel/NovelWorkbench.tsx:119-136`（进行中每 3 秒一次，页面不可见时停）。

后端（第一期）：

9. 接口前缀 `/discuss`，十七个，见一期规格 4.13。开关关着时全部 `404`「Not Found」；账号不在名单里 `403`。`GET /discuss/access` 通过时返回 `200`。
10. 详情 `GET /discuss/groups/{id}?after=N` 一次最多返回 200 条消息（ID 升序）。详情**没有返回作者对主持人问题的回答**（存在 `config_json.answers`，目前只能写、不能读）。成员里 `kind == "avatar"` 的那一项存在，就表示分身在群里。
11. 插话的 `consumed` 只会从未读变成已读，而且读取点每次都把「当时所有未读的插话」一起读走。所以未读的插话永远是最新的那几条，条数等于详情里的 `pending_notes`。
12. 成果是 Markdown。真实走查的成果（`docs/tasks/2026-11-14-agent-group/verify/walk-final/report.md`）里有 13 个标题、12 行表格、80 处来源编号，编号都是 `[S26]` 这种单个编号的写法，连续引用写成 `[S26][S119]`，表格单元格里也有编号。没有粗体，没有链接。
13. 文档用例 `backend/tests/test_discuss_docs.py` 要求六份文档里都保留「讨论群（第一期，仅后端）」这个短语；`CLAUDE.md` 全文不超过 69,300 字节（现在 68,497），其中「## 讨论群（第一期）」一节不超过 1,800 字节。

## 3. 约束

1. 不新增依赖，不改 `package.json`、`package-lock.json`、`requirements*.txt`。
2. 写 Next 相关代码前，先读 `frontend/node_modules/next/dist/docs/` 里与你要用的写法对应的章节（页面与动态路由、客户端组件、`useSearchParams` 与 `Suspense`），在报告里列出读了哪几篇。
3. **界面文字不加粗。** 本单新增的前端文件里不出现任何字重写法：`font-medium`、`font-semibold`、`font-bold`、`font-extrabold`、`font-black`、`font-[数字]`、`fontWeight`、`<b>`、`<strong>`。层次只靠字号与灰度（`var(--ink)` 与 `var(--ink2)`）。
4. 样式沿用现有的类与变量（第 2 节第 7 条），不写新的颜色值，不用渐变、阴影、大圆角卡片堆叠。像一个安静的工具页，不像营销页。
5. 不修改 `backend/discuss/` 里除第 4.3 节写明的那一处之外的任何代码；不修改 `backend/novel/`、`backend/studio/`。
6. 既有测试的输入、断言与夹具一字不改。新测试放新文件。
7. 文档只新增，不删改第一期已有的小节标题与固定短语（第 2 节第 13 条）。
8. 不提交 `.env`、数据库、上传文件、备份或 `fiona.config.json`。不 commit / stash / checkout / reset。不读 `.env`。不访问外网，不调用真实模型。
9. 仓库是公开的：代码、测试、文档与报告里不写本机绝对路径和个人信息。

## 4. 设计

### 4.1 文件

新增：

| 文件 | 内容 |
|---|---|
| `frontend/lib/discuss.ts` | 类型与接口调用（4.4） |
| `frontend/lib/discussLogic.ts` | 纯函数（4.5）。只允许 `import type`，不引入任何运行时依赖 |
| `frontend/app/discuss/page.tsx` | 群列表页 |
| `frontend/app/discuss/new/page.tsx` | 新建页 |
| `frontend/app/discuss/[id]/page.tsx` | 群聊页 |
| `frontend/components/discuss/*.tsx` | 界面部件。怎么拆由你定，建议：`DiscussShell`（外壳）、`DiscussShelf`（列表）、`DiscussCreateForm`（新建）、`DiscussTeamEditor`（队伍编辑，新建与改方案共用）、`DiscussRoom`（群聊页总装）、`DiscussTimeline`（消息）、`DiscussComposer`（插话）、`DiscussPlanPanel`、`DiscussOutputPanel`、`DiscussSourcesPanel`、`DiscussDocument`（文档渲染）、`DiscussDialogs` |
| `backend/tests/test_discuss_frontend_*.py`、`backend/tests/test_discuss_ui_api.py` | 新用例（第 6 节） |

修改：

| 文件 | 改什么 |
|---|---|
| `frontend/components/Sidebar.tsx` | 书签与三个新属性（4.2） |
| `frontend/app/page.tsx` | 访问检查、抽屉、关闭消息（4.2） |
| `backend/discuss/service.py` | 详情多返回一个字段（4.3） |
| `README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md` | 4.14 |

### 4.2 入口：书签与抽屉

侧栏 `Sidebar.tsx`：

1. 新增三个可选属性：`onDiscussClick`、`discussActive`、`discussAccessAllowed`。
2. 只有 `discussAccessAllowed === true` 时，在电脑侧栏的末尾追加「讨论群」（`href="/discuss"`）。顺序：对话、分身、广场、世界、设置、书斋、工作室（有权限时）、讨论群（有权限时）。
3. **侧栏自己不为讨论群发任何请求**（第 2 节第 4 条），也不引入 `lib/discuss.ts`。没有传 `discussAccessAllowed` 的页面不显示这个书签。`navItems` 数组保持六项不变，讨论群与工作室一样在数组之外按条件追加。
4. 手机底栏不显示讨论群，写法与工作室一致。手机底栏的项目数不变。
5. 高亮：抽屉打开时高亮；独立页面上路径是 `/discuss` 或以 `/discuss/` 开头时高亮。`aria-controls="discuss-drawer"`。
6. 书签多了一个之后，矮屏幕放不下。要求（在真实浏览器里量，判据见第 8 节第 8 条）：
   - 视口足够高时，原有书签的位置与改动前完全一样。
   - 放不下时，书签区自己可以上下滚动（不显示滚动条），底部的昼夜按钮与草莓余额始终留在屏幕里，不被挤出、不与书签重叠。
   - 实现方式由你定（例如书签区 `min-h-0 flex-1 overflow-y-auto`、底部块 `shrink-0`），但不许缩小书签的字号，不许改动书签之间在足够高的视口下的间距。

主页 `app/page.tsx`，每一步都照工作室现有的写法做，改动尽量小：

1. 抽屉名字的类型加上 `"discuss"`，加在 `"studio"` 之前，`"studio" | "novel" | null` 这一段保持原样（第 2 节第 4 条）。
2. 访问检查：`checkDiscussAccess`（4.4）在账号确定后请求一次，账号切换时重新请求并作废旧请求；不允许或请求失败时 `discussAllowed` 为假，并且如果当前打开的是讨论群抽屉就关掉它。
3. 给 `Sidebar` 传 `onDiscussClick`（允许时切换抽屉）、`discussActive`、`discussAccessAllowed`。
4. 抽屉：写在工作室抽屉之后（不改变已有四个抽屉在源码里的先后）。`id="discuss-drawer"`，`aria-label="讨论群"`，标题栏文字「讨论群」，关闭按钮 `title` 与 `aria-label` 为「收起讨论群」。允许时挂载 `<iframe key={username} title="讨论群工作区" src="/discuss?embed=1">`，不允许时显示「暂未开放」。外壳的类名、宽度、`inert`、`aria-hidden`、Esc 关闭都与工作室抽屉相同。关闭抽屉后 iframe 不卸载，页面状态保留。
5. 打开抽屉时把焦点移到抽屉上；关闭后把焦点还给书签（现有的 `focusVisibleDrawerTrigger`）。
6. 监听 `fiona-discuss-close` 消息：必须同时校验 `event.origin === window.location.origin` 与 `event.source` 是讨论群 iframe 的窗口，通过才关抽屉并把焦点还给书签。

### 4.3 后端小补充：详情返回作者的回答

`backend/discuss/service.py` 的 `detail` 返回值加一个字段 `answers`：`config_json.answers` 是字符串时原样返回，否则返回空字符串。其他接口与字段不变。

理由：开工前作者要回答主持人的问题（一期规格 4.13 第 4 条的 `answers`）。不返回的话，保存之后页面上就看不到自己写过什么。

### 4.4 `frontend/lib/discuss.ts`：类型与接口

写法照 `frontend/lib/novels.ts`。

类型（字段名与后端一致，见一期规格 4.13 的细则 0、1、3、13、14）：`DiscussStatus`、`DiscussSummary`、`DiscussMember`、`DiscussMessage`、`DiscussPlan`、`DiscussDetail`（含 `answers`）、`DiscussCatalog`、`DiscussSource`、`DiscussOutput`、`DiscussOutputSummary`（含 `words`）。

接口函数，每个都接受可选的 `AbortSignal`：

| 函数 | 请求 |
|---|---|
| `checkDiscussAccess` | `GET /discuss/access`，返回「状态码是否为 200」，写法照 `checkStudioAccess` |
| `getDiscussCatalog` | `GET /discuss/catalog` |
| `listDiscussGroups` | `GET /discuss/groups` |
| `createDiscussGroup` | `POST /discuss/groups` |
| `getDiscussGroup(id, after)` | `GET /discuss/groups/{id}?after=N` |
| `updateDiscussPlan` | `PATCH /discuss/groups/{id}/plan` |
| `startDiscussGroup` | `POST …/start` |
| `addDiscussNote` | `POST …/notes` |
| `pauseDiscussGroup`、`resumeDiscussGroup`、`continueDiscussGroup`、`acceptDiscussGroup`、`closeDiscussGroup` | 对应的 `POST` |
| `deleteDiscussGroup` | `DELETE …` |
| `listDiscussSources` | `GET …/sources` |
| `getDiscussOutput(id, version?)` | `GET …/output` |
| `exportDiscussGroup` | `GET …/export`，返回 `Blob`；响应不是 `text/markdown` 时报错，写法照 `exportNovel` |

路径里的群 ID 一律 `encodeURIComponent`。列表与详情请求带 `cache: "no-store"`。

### 4.5 `frontend/lib/discussLogic.ts`：纯函数

这个文件不引入任何运行时依赖（只允许 `import type`），这样测试可以在 Node 里直接转译执行。界面里凡是「按状态决定显示什么」的判断都走这里，不在组件里各写一遍。

1. `discussStatusLabel(group)`：状态的中文。
   - `planning` 立项中；`awaiting_start` 等你开工；`running` 讨论中；`awaiting_user` 等你决定；`closed` 已结束；`failed` 出错了。
   - `done`：`stop_reason` 为 `accepted_by_user` 时「你已接受」，否则「验收通过」。
   - `paused` 按 `stop_reason`：`user` 已暂停；`budget` 预算用完；`insufficient_strawberries` 草莓不足；`byok_unavailable` 自带模型不可用；`step_failed` 有一步没跑通；`search_unavailable` 联网搜索暂不可用；`server_restart_failed` 恢复失败；其他或为空「已暂停」。
   - 不认识的状态原样返回。
2. `discussStopHint(group)`：停下来之后给作者的一句话，没有可说的返回空字符串。
   - `awaiting_start`：「方案已经出来了。看一眼、改一改，回答主持人的问题，然后开工。」
   - `awaiting_user`：「轮数用完了，验收还没通过。你可以接受现在的成果，或者追加轮数让它继续。」
   - `paused`：`budget`「预算用完了。继续之前先追加预算。」；`insufficient_strawberries`「草莓不够了。补充草莓后点继续。」；`byok_unavailable`「自带模型用不了。到设置里检查后点继续。」；`step_failed`「有一步连着几次没跑通。点继续会从断的地方接着跑。」；`search_unavailable`「联网搜索暂时拿不到结果。过一会儿点继续。」；`server_restart_failed`「服务重启后没能自动接上。点继续会从断的地方接着跑。」；`user` 返回空字符串。
   - `failed`：「出了意料之外的错误。点继续会从断的地方接着跑。」
   - `done` 且不是 `accepted_by_user`：「验收通过了。想再改，先在群聊里写下意见，再点按意见返工。」
3. `discussIsActive(status)`：`planning` 或 `running` 为真。
4. `discussNeedsAuthor(group)`：`awaiting_start`、`awaiting_user`、`paused`、`failed` 为真。
5. `discussActions(group)`：返回按顺序排好的可用操作数组，取值 `"start" | "pause" | "resume" | "continue" | "rework" | "accept" | "close" | "export" | "delete"`。
   - 按状态：`planning` → `pause`；`awaiting_start` → `start`、`close`；`running` → `pause`；`paused` → `resume`、（`output_version >= 1` 时）`accept`、`close`；`awaiting_user` → `continue`、（`output_version >= 1` 时）`accept`、`close`；`done` → `rework`；`failed` → `resume`、`close`；`closed` → 无。
   - 之后 `output_version >= 1` 时追加 `export`。
   - 最后总是追加 `delete`。
6. `discussDefaultTab(group)`：`awaiting_start` → `"plan"`；`awaiting_user`、`done`、`closed` 且 `output_version >= 1` → `"output"`；其余 → `"chat"`。
7. `discussKindLabel(kind)`：`plan` 方案；`brief` 主人背景；`note` 调研笔记；`notice` 说明；`critique` 质疑；`decision` 裁决；`draft` 成稿；`view` 主人视角；`verdict` 验收；`rework` 返工安排；`user` 插话；不认识的返回空字符串。
8. `mergeDiscussMessages(current, incoming)`：按 `id` 合并去重（同一个 `id` 以 `incoming` 为准），结果按 `id` 升序。不修改传入的数组。
9. `applyPendingNotes(messages, pendingNotes)`：返回新数组。`sender === "user"` 的消息里，`id` 最大的 `pendingNotes` 条标成 `consumed: false`，其余标成 `consumed: true`；别的消息不变（依据见第 2 节第 11 条）。`pendingNotes` 不是正整数时按 0 算。
10. `groupDiscussRounds(messages)`：把相邻且 `round` 相同的消息归成一组，返回 `[{ round, label, messages }]`，`label` 在 `round === 0` 时是「立项」，否则是「第 N 轮」。不排序，按传入顺序。
11. `splitDiscussDocument(text)`：把 Markdown 拆成块，返回 `[{ kind: "markdown", text } | { kind: "table", header: string[], rows: string[][] }]`。
    - 表格的判定：一行以 `|` 开头（行首可有空白），紧接着的下一行是分隔行（只含 `|`、`-`、`:` 与空白，且至少有一段三个以上的 `-`），就是表头与分隔行；其后连续的以 `|` 开头的行是数据行。
    - 单元格：去掉首尾的 `|` 后按 `|` 切开，各自去首尾空白。数据行的列数多于表头时截断，少于表头时补空字符串。
    - 围栏代码块（以三个反引号开头的行到下一个这样的行）里面不找表格。
    - 表格之外的连续文本合成一个 `markdown` 块，内容原样保留（含换行）；空白的块丢掉。
    - 传入的不是字符串时返回空数组。
12. `splitDiscussCitations(text)`：把一段文字按来源编号切开，返回 `[{ kind: "text", text } | { kind: "cite", id }]`。编号的写法是 `[S` 加 1–4 位数字加 `]`，`id` 是 `S` 加数字（例如 `S26`）。没有编号时返回一个 `text` 块；空字符串返回空数组。相邻的两个编号之间不产生空的 `text` 块。
13. `safeExternalUrl(url)`：是字符串且能解析成 `http:` 或 `https:` 的网址时返回规范化后的网址，否则返回 `null`。
14. `validateDiscussCreate(form, limits)`：返回第一条错误文案，没有错误返回空字符串。按这个顺序检查：
    - 诉求去首尾空白后不足 `request_min` 或超过 `request_max` 字：「诉求需要 10–2000 字」（数字取 `limits`）。
    - 材料超过 `materials_max`：「补充材料最多 20000 字」。
    - 预算不是整数或不在范围内：「预算需要 100–20000 颗」。
    - 轮数不是整数或不在范围内：「轮数需要 1–6 轮」。
    - 自己组队时：成员数不在 `members_min`–`members_max`：「调研成员需要 1–5 位」；自定义成员缺名字或职责：「自定义成员要写名字和职责」；名字超过 `name_max`：「名字最多 12 字」；自定义成员的职责超过 `custom_does_max`：「职责最多 200 字」；去首尾空白后名字有重复：「成员的名字不能重复」。
    - 固定席位的名字超过 `name_max`：「固定席位的名字最多 12 字」；身份设定超过 `persona_max`：「身份设定最多 300 字」。
15. `buildDiscussCreateBody(form)`：生成 `POST /discuss/groups` 的请求体。
    - `request`、`materials` 去首尾空白；`budget_strawberries`、`max_rounds`、`avatar` 原样。
    - 队伍方式是「主持人点将」时不带 `members`；是「自己组队」时带 `members`：角色池成员是 `{ role }`，改过名字或职责时带上 `name`、`does`；自定义成员是 `{ name, does }`。
    - `models` 只带作者改过的成员；一个都没改时不带这个键。
    - `identities` 只带名字或身份设定非空的席位；一个都没有时不带这个键。
16. `buildDiscussPlanPatch(detail, draft)`：生成 `PATCH …/plan` 的请求体。总是带 `expected_revision: detail.plan_revision`；其余字段只在与当前值不同的时候才带（`title`、`criteria`、`picks`、`identities`、`budget_strawberries`、`max_rounds`、`avatar`、`models`、`answers`）。`picks` 只要有任何一项的 `role`、`name`、`does`、`focus` 或顺序变了，就整份带上（后端是整份替换）；已有成员带 `role`，新增的自定义成员不带 `role`。
17. `discussPlanPatchIsEmpty(patch)`：除 `expected_revision` 外没有别的键时为真。
18. `discussErrorMessage(error)`：`status === 404` 且文案是 `Not Found` → 「讨论群尚未开放」；`status === 403` → 「你的账号暂未开通讨论群」；其他错误：文案里有汉字就用原文，否则「请求未完成，请稍后重试。」。判断 `status` 与 `message` 时只看对象上有没有这两个属性，不引入 `ApiError`。
19. `discussHref(path, embedded)`：`embedded` 为真时给路径加上 `embed=1`（路径已有查询串时用 `&`）。
20. `discussModelLabel(id)`：`dashscope:qwen3.8-max` 千问 3.8 Max；`deepseek:deepseek-flash` DeepSeek Flash；`ark:doubao-seed-2-1-pro-260915` 豆包 Seed 2.1 Pro；`byok:self` 我的模型；其余原样返回。

### 4.6 外壳与嵌入

三个页面都是客户端组件，都读 `embed=1`，写法照书斋的页面。

`DiscussShell`（写法照 `StudioShell.tsx`）：

1. 嵌入时不显示侧栏与背景画；独立打开时显示 `<InkLandscape variant="page" />` 与 `<Sidebar discussAccessAllowed />`（能打开这个页面就说明有权限）。
2. 嵌入时监听键盘：Esc 且满足 `canCloseNovelDrawer`（焦点不在输入框里、没有打开的对话框、不在输入法组合中）时，向父窗口发 `{ type: "fiona-discuss-close" }`，目标源用 `window.location.origin`。
3. 页面之间的链接用 `discussHref`，嵌入时一直带着 `embed=1`。

三个页面共同的状态：

- 身份还没加载完：`LoadingState`「正在加载身份…」。
- 没登录：`EmptyState`「请登录后使用讨论群。」加「前往登录」链接（嵌入时 `target="_top"`）。
- 接口返回 `404`「Not Found」或 `403`：用 `discussErrorMessage` 的文案，不显示重试按钮以外的操作。
- 其他读取失败：`ErrorNotice` 加「重新加载」。
- 账号切换：用 `key={owner}` 重新挂载，并用 `useAccountRequest` 作废旧请求（写法照 `NovelShelf.tsx`）。

### 4.7 群列表（`/discuss`）

1. 页头：标题「讨论群」（嵌入时标题只留给读屏，写法照 `app/novels/page.tsx`）、「新建讨论群」按钮（主按钮，去 `/discuss/new`）、一句说明「提一个诉求，一组智能体分工调研、互相质疑，写出带来源的成果。」、「刷新」按钮；嵌入时另有「在新页面打开」（`href="/discuss"`、新标签页）。
2. 每个群一张卡片（两列，窄时一列），整张卡片是去 `/discuss/{id}` 的链接：
   - 标题（没有标题时后端已经给了诉求的前 20 个字）与状态标签（`discussStatusLabel`）。
   - `discussNeedsAuthor` 为真时显示一行「待你处理」。
   - 进度「第 r / max 轮」（`round` 为 0 时显示「立项」）、草莓「已花 / 预算」、成果「第 n 版」或「还没有成果」。
   - 最近更新时间（`formatNovelDate`）。
3. 空状态：标题「建你的第一个讨论群」，说明「写下想查清或想做成的事，剩下的交给他们。」，主按钮「新建讨论群」。有空状态时页头不再重复显示「新建讨论群」按钮。
4. 轮询：只要有群处于 `planning` 或 `running`，且页面可见，每 3 秒刷新一次；写法照 `NovelShelf.tsx`。

### 4.8 新建（`/discuss/new`）

进入时请求目录（`getDiscussCatalog`），表单里的上限、默认值、角色池、模型与说明都取自目录，不写死。目录请求失败时显示错误与「重新加载」，不显示表单。

表单自上而下：

1. **诉求**（必填，多行）。占位文字「例如：帮我查清楚面向东南亚做 AI 短剧值不值得做，给出结论和起步方案」。右下角字数「n / 2000」。
2. **补充材料**（选填，多行，默认收起，点「添加补充材料」展开）。字数「n / 20000」。
3. **队伍**，二选一：
   - 「主持人点将」（默认）：说明「主持人按你的诉求，从角色池里挑 2–4 位调研成员。开工前你还能改。」
   - 「我来组队」：列出角色池里 `kind === "lens"` 的角色（名字与职责），可勾选；每个勾选的角色可以改名字与职责；「添加自定义成员」加一行（名字、职责）。已选人数「n / 5」。
4. **分身参与**（开关，默认开）：说明「分身会带着你的背景进群，替你看稿。」
5. **预算与轮数**：预算（数字，默认与范围取目录；旁边注明「颗草莓」），轮数（下拉 1–6，默认 3）。下面一行小字：「联网搜索每次另扣 {search_price} 颗。」
6. **更多设置**（默认收起）：
   - 固定席位的名字与身份设定（主持人、反方质疑、撰稿人、验收人，各两个输入框；不填就用默认）。
   - 各成员的模型（下拉；选项是目录里的平台模型，加上 `byok` 不为空时的「我的模型」；默认值取目录的 `defaults`）。主持人点将时只列固定席位与分身；自己组队时再加上所选的调研成员。
7. 目录里的 `notice` 原文（隐私说明），小字，放在提交按钮上方。
8. 按钮：「建群并立项」（主按钮）、「取消」（回列表）。

行为：

- 点提交先跑 `validateDiscussCreate`，有错就在表单上方显示（`role="alert"`），不发请求。
- 请求体用 `buildDiscussCreateBody`。提交中按钮显示「正在建群…」并禁用，重复点击不发第二次请求。
- 成功后跳到 `/discuss/{id}`（带上 `embed`）。
- 失败时显示后端的中文文案（`discussErrorMessage`）。几种要能看懂的情况：`400` 是危机提示（原文显示）、`409` 已有一个群在进行、`429` 今天到上限、`422` 填写不合要求。失败后表单内容保留。

### 4.9 群聊页（`/discuss/{id}`）

#### 布局

自上而下：

1. **顶栏**：
   - 第一行：「返回列表」链接、标题、状态标签。
   - 第二行（小字，`readout`）：`第 r / max 轮`（`round` 为 0 时「立项」）· `草莓 已花 / 预算` · `成果第 n 版`（没有成果时不显示这一段）。
   - 第三行：操作按钮（见下）。
2. **提示条**：`discussStopHint` 非空时显示它；`last_error` 非空时在它下面显示（`role="alert"`）。
3. **标签**：群聊、方案、成果、来源（`role="tablist"`，键盘操作用 `useRovingTabs`）。
   - 内容区宽度不足 1080px 时：四个标签，一次显示一个。
   - 内容区宽度达到 1080px 时：左栏固定显示群聊，右栏在方案、成果、来源三个标签之间切换；这时标签条里不再有「群聊」。
   - 宽度用 `ResizeObserver` 量内容区（写法参考 `NovelWorkbench.tsx` 的 `wideLayout`），不用视口宽度（抽屉只占屏幕的三分之二）。
   - 第一次拿到详情时，按 `discussDefaultTab` 选中标签；之后不再自动切换，除非下面写明的两处。

#### 操作

按钮来自 `discussActions`，文案与行为：

| 操作 | 按钮文字 | 行为 |
|---|---|---|
| `start` | 开工 | 主按钮。方案面板里有未保存的修改时不发请求，提示「先保存或放弃修改」并切到方案标签。请求体 `expected_revision` 取当前的 `plan_revision`。`409` 时显示后端文案并提供「重新加载方案」 |
| `pause` | 暂停 | 直接请求 |
| `resume` | 继续 | `stop_reason === "budget"` 时先弹对话框填「追加预算」（至少 1 颗，默认 200，加上后总预算不超过 20000）；其他情况直接请求（`add_budget: 0`） |
| `continue` | 追加轮数 | 对话框：追加几轮（1–3，且追加后总轮数不超过 10）、追加预算（默认 0）。总预算必须大于已花，否则在对话框里提示「预算已经用完，请先调高预算」不发请求 |
| `rework` | 按意见返工 | `pending_notes === 0` 时不发请求：提示「先在群聊里写下你的意见，再点按意见返工」，切到群聊标签并把焦点放进插话框。有未读插话时弹出与「追加轮数」相同的对话框，标题换成「按意见返工」 |
| `accept` | 接受成果 | 确认框「接受第 n 版成果，讨论到此结束？」 |
| `close` | 结束 | 确认框「结束这个讨论群？结束后不能再继续。」 |
| `export` | 导出 | 下载 Markdown。文件名取响应头里的附件名，取不到时用「讨论群成果.md」 |
| `delete` | 删除 | 确认框「删除这个讨论群？讨论记录、成果与来源都会删掉，不能恢复。」成功后回列表 |

- 主操作（`start`、`pause`、`resume`、`continue`、`rework`、`accept`）排在第三行左侧，第一个用 `btn-primary`，其余用 `btn`；`close`、`export`、`delete` 排在右侧，用 `btn-quiet`（`delete` 用 `btn-danger`）。不做下拉菜单。
- 任何一个操作进行中，所有操作按钮禁用，正在进行的那个显示「…中」；完成后重新读取详情。
- 操作失败：在顶栏下方显示后端的中文文案（`role="alert"`），不清空页面内容。

#### 读取与轮询

1. 第一次读取：`after=0`；如果一次返回了 200 条消息，就用最后一条的 `id` 作为 `after` 接着读，直到某一次少于 200 条。
2. `discussIsActive(status)` 为真且页面可见时，每 3 秒读一次，`after` 取已有消息里最大的 `id`。新消息用 `mergeDiscussMessages` 并入，再用 `applyPendingNotes` 按最新的 `pending_notes` 更新插话的已读标记。群字段、成员、成果摘要每次都用新值整体替换。
3. 页面不可见时停；重新可见时立刻读一次。状态不再是进行中时停止轮询。
4. 轮询中的一次失败不清空页面，只在顶栏下方显示一行提示；下一次成功后提示消失。
5. 作者自己的操作进行中时，轮询结果不覆盖页面（写法参考 `NovelWorkbench.tsx` 的 `mutating`）。
6. 详情返回 `404`：显示「讨论群不存在」与「返回列表」。

### 4.10 群聊标签

自上而下：成员条、消息、插话框。

**成员条**：按详情里 `members` 的顺序列出名字；`working` 为真的成员名字后面带一个转动的小图标。成员条下面一行小字：有人在工作时显示「{名字、名字} 正在工作…」，状态是进行中但没有人在工作时显示「正在安排下一步…」，其他状态不显示。

**消息**：

1. 用 `groupDiscussRounds` 分组，每组前面一条分隔线，写「立项」或「第 N 轮」。
2. 每条消息：第一行是发言人名字（`sender_name`）、种类标签（`discussKindLabel`，为空时不显示）、时间；下面是正文，用 4.13 的文档渲染（正文里的来源编号同样可以点）。
3. 作者自己的插话（`sender === "user"`）用 `var(--slip)` 做底色区分；名字后面标「已读到」或「还没读到」（取 `consumed`）。
4. `kind === "draft"` 的消息下面有一个「看这一版成果」按钮：切到成果标签并选中 `payload.version` 那一版（`payload.version` 不是正整数时不显示按钮）。
5. 还没有消息：进行中显示 `LoadingState`「主持人正在看你的诉求…」；其他状态显示「还没有消息。」
6. 自动滚动：新消息到来时，如果作者停在底部附近（距底不超过 80px），滚到最新；否则不动，并在消息区右下显示「有新消息」按钮，点了滚到最新。

**插话框**：

1. 多行输入，最多 500 字，右下角字数「n / 500」，「发送」按钮。
2. Enter 发送，Shift+Enter 换行。输入法组合中按 Enter 不发送。内容去首尾空白后为空时不发送。发送中再按 Enter 不重复提交。
3. 状态是 `closed` 或 `failed` 时不显示输入框，改显示一行「这个群已经结束，不能再插话。」（`failed` 时是「出错停下了。点继续之后可以再插话。」）
4. `pending_notes > 0` 时在输入框上方显示「还有 n 条插话没被读到。」
5. 发送成功：清空输入框，把返回的消息并进列表，`pending_notes` 加 1，滚到最新。失败：显示后端文案，输入内容保留。
6. 状态是 `done` 时，输入框上方显示「写下意见后，点上面的按意见返工。」；状态是 `awaiting_start` 时显示「开工前写的话，成员开工时都能看到。」

### 4.11 方案标签

没有方案（`plan === null`）：进行中显示「主持人正在立项…」，其他状态显示「还没有方案。」

有方案时，只读内容自上而下：

1. **目标**：`plan.goal`。
2. **成果形式**：`deliverable.kind` 的中文（`report` 调研报告、`plan` 行动方案、`comparison` 对比分析，其他原样）与提纲 `outline`（列表）。
3. **完成标准**：`criteria`，每条前面带编号（`C1`…）。
4. **成员与分工**：详情里的全部成员，每位一行：名字、类别（`core` 固定席位、`lens` 调研、`custom` 自定义、`avatar` 分身）、职责或身份（`does`，为空不显示）、分工（`focus`，调研成员才有）、模型（`discussModelLabel`）。
5. **主持人想问你**：`plan.questions`（为空时整段不显示）；下面是「你的回答」，显示 `answers`，为空时显示「还没有回答。」
6. **原始诉求**：`request`，默认收起。

状态是 `awaiting_start` 时，标签顶部多一个「修改方案」按钮，点了进入编辑：

1. 可改：标题；完成标准（3–6 条，可增删、改文字）；调研成员（1–5 位：改名字、职责、分工，删除，从角色池添加还没选的角色，添加自定义成员；队伍编辑与新建页共用一个部件）；固定席位的名字与身份设定；预算；轮数；分身是否参与；各成员的模型；你的回答（最多 1000 字）。
2. 按钮「保存修改」「放弃修改」。保存时用 `buildDiscussPlanPatch`；`discussPlanPatchIsEmpty` 为真时不发请求，直接退出编辑。
3. 保存成功：用返回的详情更新页面，退出编辑。`409`：显示后端文案与「重新加载方案」（重新读取详情并丢弃本地修改）。`422`：显示后端文案，留在编辑里。
4. 编辑中有未保存的修改时离开方案标签不丢内容；点「开工」见 4.9。
5. 目录请求失败时不能进入编辑，显示错误与「重新加载」。

其他状态没有「修改方案」按钮。

### 4.12 成果标签与来源标签

**成果**：

1. 没有成果（`output_version === 0`）：「成果还没写出来。撰稿人交稿后会出现在这里。」
2. 有成果：
   - 顶部一行：版本下拉（第 1 版 … 第 n 版，默认最新；只有一版时显示文字不显示下拉）、`第 r 轮`、字数、验收标签（`verdict` 为空「等待验收」，`passed` 为真「验收通过」，否则「验收未通过」）、「导出」按钮（只导出最新一版，选中的不是最新版时按钮旁注明「导出的是最新一版」）。
   - 「验收明细」（默认收起；验收未通过时默认展开）：`verdict.verdicts` 每条一行「C1 通过 / 未通过：依据」；`verdict.citation_issues` 非空时列出「引用问题」；`verdict.rework` 非空时列出「返工要求」。字段缺失或类型不对的条目跳过，不报错。
   - 正文：用 4.13 渲染，阅读宽度不超过 720px。
3. 切换版本时请求 `getDiscussOutput(id, version)`；加载中显示 `LoadingState`，失败显示 `ErrorNotice` 加「重新加载」。
4. 群在进行中、`output_version` 变大时：如果作者正在看的是之前的最新版，在顶部提示「有新的一版」并提供「看最新版」按钮，不自动跳走。

**来源**：

1. 第一次打开这个标签时请求 `listDiscussSources`；群在进行中时，每次打开标签都重新请求。
2. 没有来源：「还没有登记来源。调研开始后会出现在这里。」
3. 每条一行：编号、标题、站点。`safeExternalUrl(url)` 不为空时，标题是链接（新标签页，`rel="noopener noreferrer"`）；为空时标题是纯文字。
4. 顶部一个开关「只看成果引用到的」（有成果时才显示）：只留下当前所选版本正文里出现过编号的来源。旁边写「共 n 条」。

### 4.13 文档渲染（`DiscussDocument`）

成果正文与群聊消息都用它。输入是 Markdown 文本和一张「编号 → 来源」的表。

1. 先用 `splitDiscussDocument` 拆块。
2. `markdown` 块：用 `parseMessageMarkdown` 解析后自己渲染（段落、标题、列表、引用、代码块、分隔线、着重、行内代码；样式参考 `frontend/components/MessageText.tsx`，但标题与着重不加粗）。
3. `table` 块：渲染成表格，细线分隔，放在一个可以横向滚动的容器里，表格不把页面撑宽。
4. 所有文字（段落、列表项、标题、引用、单元格）都过一遍 `splitDiscussCitations`。编号渲染成一个小标记（`tag` 样式、不换行）：
   - 来源表里有这个编号且 `safeExternalUrl` 不为空：是链接，新标签页打开，`rel="noopener noreferrer"`，`title` 是「标题（站点）」。
   - 否则：纯文字标记，`title` 是「来源未登记」。
5. 不使用 `dangerouslySetInnerHTML`。模型写的任何内容都只作为文字渲染。
6. 来源表：群聊页进入时请求一次 `listDiscussSources`；轮询中发现消息或成果里出现了表里没有的编号时再请求一次（同一时刻只发一个请求）。

### 4.14 文档

只新增，不删改第一期的内容（第 3 节第 7 条）。文字口语、简短，不写本机路径。

- `README.md`：在第一期那一节后面加「讨论群界面（第二期）」：入口在哪、只在电脑上、能做什么、怎么开（沿用第一期的两个开关）。
- `docs/ARCHITECTURE.md`：在讨论群那一节里加一小节「界面」：页面与文件、抽屉怎么嵌入、轮询、文档渲染与来源编号。
- `PLAN.md`：新增 2026-11-15 的条目与已知局限：手机上没有入口；除主页与讨论群自己的页面外，其他独立页面的侧栏不显示讨论群书签；分身聊天互通未做。
- `CLAUDE.md`：新增一节「## 讨论群界面（第二期）」，不超过 700 字节，只写入口文件与两条约定（侧栏不自己请求访问检查；按状态的判断都在 `discussLogic.ts`）。改完后全文不超过 69,300 字节。

## 5. 任务清单

按文件不重叠拆分，用工作流（workflow 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent；每个 agent 的任务说明自包含，并写明不得调用 subagent / subagent_fork / workflow。同一个文件及其测试只归一个 agent。主代理只做拆分、派发、汇总、白名单检查、门禁与报告。建议的拆法（先做 1，其余并行）：

1. `lib/discuss.ts` 与 `lib/discussLogic.ts`，加 `test_discuss_frontend_logic.py`。其余任务都依赖它的类型与函数名，先做完。
2. `Sidebar.tsx` 与 `app/page.tsx`，加 `test_discuss_frontend_navigation.py`。
3. 外壳、群列表、新建页（含队伍编辑部件）。
4. 群聊页总装、顶栏操作、对话框、轮询。
5. 群聊标签（成员条、消息、插话框）与文档渲染。
6. 方案标签、成果标签、来源标签。
7. 后端 `detail` 的 `answers` 与 `test_discuss_ui_api.py`。
8. 文档，加静态守卫用例 `test_discuss_frontend_guards.py`。

## 6. 测试要求

新用例全部放在 `backend/tests/` 的新文件里，离线运行，不访问网络。

1. **`test_discuss_frontend_logic.py`**：在 Node 里转译执行 `frontend/lib/discussLogic.ts`（写法照 `test_desk_logic_frontend.py`，含「缺依赖时在起 Node 之前就 skip」的自检）。对 4.5 的每个函数直接调用真实导出、断言精确结果，至少覆盖：
   - `discussStatusLabel`：八个状态；`paused` 的七个原因加一个不认识的原因；`done` 的两种原因。
   - `discussActions`：八个状态各一例（`done` 没有 `close`）；`paused` 与 `awaiting_user` 在 `output_version` 为 0 与 1 时的差别；`export` 与 `delete` 的位置。
   - `discussDefaultTab`：每条规则一例，含「`done` 但 `output_version` 为 0」。
   - `mergeDiscussMessages`：重复的 `id` 以新值为准、结果升序、不修改入参。
   - `applyPendingNotes`：三条插话里未读 0、1、3 条；`pendingNotes` 比插话多；不是数字。
   - `groupDiscussRounds`：0 轮与多轮、同一轮被别的轮隔开时不合并。
   - `splitDiscussDocument`：没有表格；一个表格夹在两段文字中间；数据行列数多于与少于表头；代码块里长得像表格的内容不拆；只有表头没有分隔行时不算表格；入参不是字符串。
   - `splitDiscussCitations`：没有编号；编号在开头、中间、结尾；两个编号相邻；`[S12345]`（五位）与 `[s3]`、`[S]` 不算编号。
   - `safeExternalUrl`：`https`、`http` 通过；`javascript:`、`data:`、相对路径、空字符串、非字符串返回 `null`。
   - `validateDiscussCreate`：4.5 第 14 条的每一句文案各一例，加一例全部合法；两处错误同时存在时返回排在前面的那一句。
   - `buildDiscussCreateBody`：主持人点将时没有 `members`；自己组队时三种成员（原样的角色池成员、改过名字的角色池成员、自定义成员）各自的形状；`models` 与 `identities` 为空时没有这两个键。
   - `buildDiscussPlanPatch` 与 `discussPlanPatchIsEmpty`：什么都没改；只改标题；只改一位成员的分工（`picks` 整份带上且已有成员带 `role`）；新增自定义成员（不带 `role`）；调换两位成员的顺序。
   - `discussErrorMessage`：`404`「Not Found」、`403`、带中文文案的 `409`、英文文案的 `500`、不是对象。
   - `discussHref`：带与不带查询串、嵌入与不嵌入。
2. **`test_discuss_frontend_navigation.py`**（写法照 `test_studio_frontend_navigation.py`）：
   - 用替身跑真实的 `Sidebar.tsx`：`discussAccessAllowed` 为 `true` 时电脑侧栏最后一项是「讨论群」，为 `false`、没传时没有；三种情况下手机底栏的项目都与改动前相同；`discussActive` 为真时这一项高亮且 `aria-expanded` 为真；路径是 `/discuss/abc` 时高亮；点它会调用 `onDiscussClick`。
   - 侧栏在这三种情况下发出的请求里都没有 `/api/discuss/`。
   - 主页源码的静态检查：抽屉类型含 `"discuss"`；讨论群 iframe 的 `src` 是 `/discuss?embed=1` 且只在允许时渲染；关闭消息的监听同时比较了 `event.origin` 与 iframe 的 `contentWindow`；不允许时会关掉讨论群抽屉。
3. **`test_discuss_frontend_guards.py`**：扫描 `frontend/lib/discuss.ts`、`frontend/lib/discussLogic.ts`、`frontend/app/discuss/` 与 `frontend/components/discuss/` 下的全部文件。每条守卫先断言扫到的文件数大于 0。
   - 没有第 3 节第 3 条列出的任何字重写法。
   - 没有 `dangerouslySetInnerHTML`。
   - `discussLogic.ts` 里的 `import` 全是 `import type`。
   - 每个 `target="_blank"` 的同一个标签里都有 `rel="noopener noreferrer"`。
   - 三个页面文件都以 `"use client"` 开头。
   - 文档：`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`CLAUDE.md` 都有「讨论群界面（第二期）」；`CLAUDE.md` 的这一节不超过 700 字节。
4. **`test_discuss_ui_api.py`**：详情默认返回 `answers == ""`；改方案写入回答后，详情返回同样的文字；`config_json.answers` 不是字符串时返回空字符串。
5. 每条新用例都要能发现对应的错误实现。报告里给一张自检表：把实现改坏（至少 12 处，覆盖上面四个文件）后，由哪条用例靠断言失败发现；必须是 `failed`，不能是 `error` 或超时。

## 7. 何时停下来问

只有影响「实现什么」才停下来在报告里说明：规格自相矛盾、照规格做不出来、或者照规格做会让既有用例变红。只影响「怎么实现、怎么验证」的，自己决定并在报告里写明理由。你实测到的事实优先于本文的说法，不符就停下来说明。任何情况不回滚已完成的工作。

## 8. 验收标准

命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. 在 `frontend/`：`npm run lint -- --max-warnings=25` 退出码 0（现在是 25 个警告，本单不新增）。
2. 在 `frontend/`：`npx tsc --noEmit` 退出码 0。
3. 在 `frontend/`：`npm run build` 退出码 0，输出的路由表里有 `/discuss`、`/discuss/new`、`/discuss/[id]`。
4. 在 `backend/`：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py` 全部通过、0 跳过。
5. 在 `backend/`：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_studio_frontend_*.py tests/test_discuss_*.py` 全部通过、0 跳过（既有的侧栏与主页用例、讨论群用例都不变红）。
6. 在 `backend/`：全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`，通过数 = 8562 + 本单新增的用例数，0 失败、0 跳过。如果唯一的失败是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`（已知的旧用例，机器忙时偶发，与本单无关），单独重跑这一条并把两次的输出都贴出来，不要为它改任何文件。
7. `git status --porcelain --untracked-files=all`：只有 4.1 列出的文件有变动，另加报告。
8. 以下由规格作者在真实浏览器里核验，你不需要跑，但实现要满足：
   - 侧栏（8 个书签，含工作室与讨论群）：视口 1440×900 与 1280×620 下，每一个书签都能看到或滚动到，昼夜按钮与草莓余额始终在视口内，任何两个元素不重叠；视口高 1200 时，原有 7 个书签的位置与改动前相同。
   - 抽屉宽度下（视口 1440 与 1280）四个标签都没有横向溢出；视口 1920 时群聊页是两栏。
   - 一份带表格与来源编号的成果正确渲染：表格是表格，编号是可点的标记。
   - 空状态、加载中、读取失败、没有权限四种情况各有明确的界面。
   - 浅色与深色下文字都看得清。

## 9. 白名单

允许新增或修改的文件就是 4.1 的两张表，另加报告 `docs/tasks/2026-11-15-agent-group-ui/impl/report.md`。其他文件一律不动，包括 `frontend/app/globals.css`、`frontend/lib/messageMarkdown.ts`、`frontend/components/MessageText.tsx`、`frontend/components/novel/`、`frontend/components/studio/`、既有测试与任务目录下的规格。

如果实现侧栏的滚动确实需要一条全局样式，停下来在报告里说明要加什么、为什么，不要自己改 `globals.css`。

## 10. 交付报告

写进 `docs/tasks/2026-11-15-agent-group-ui/impl/report.md`，不写本机绝对路径。开头是拆分表（如实列出派出过的全部 agent、各自负责的文件）。然后：

1. 修改与新增了哪些文件。
2. 实现了哪些功能，与第 4 节逐条对应。
3. 读了 Next 文档的哪几篇。
4. 新用例的文件、数量与自检表（第 6 节第 5 条）。
5. 验收 1–7 的命令与输出摘要。
6. 没做完、与规格不一致、或需要人工确认的地方。
