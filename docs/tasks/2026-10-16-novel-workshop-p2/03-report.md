# 小说工坊 P2 实施报告

日期：2026-10-16。实施范围以同目录 `02-spec.md` 为准，第 0 节作者拍板已落实。三个子代理分别负责后端、类型/书架/向导、工作台关卡；主代理负责三栏内容、导航/抽屉、源码测试、文档和最终门禁。同一文件由同一负责人修改。

功能已实现。Lint、TypeScript、webpack 补充生产构建及新增 57 条测试通过；指定的默认 Turbopack 构建、后端全量门禁未能在本沙箱完全通过，具体阻塞均为本地端口绑定权限，见下文，不将其记为通过。未联网、读取密钥、安装/升级/删除依赖或提交 commit。

## 1. 文件清单

### 新增前端文件

| 文件 | 职责 |
| --- | --- |
| `frontend/app/novels/page.tsx` | 客户端书架路由和 Suspense |
| `frontend/app/novels/new/page.tsx` | 客户端建书向导路由和 Suspense |
| `frontend/app/novels/[id]/page.tsx` | 客户端动态工作台路由、id/embed 参数和 Suspense |
| `frontend/lib/novels.ts` | 类型、完整接口封装、状态/模型/中文错误/嵌入链接辅助函数 |
| `frontend/components/novel/NovelShelf.tsx` | 书架、状态、进度、待处理提示、空态/访问限制 |
| `frontend/components/novel/NovelWizard.tsx` | 三步表单、校验、估算、余额和提交汇总 |
| `frontend/components/novel/NovelModelFields.tsx` | 角色、顾问、平台模型价格与 BYOK 选择 |
| `frontend/components/novel/NovelWorkbench.tsx` | 工作台数据、账户隔离、轮询、操作和三栏/手机标签页 |
| `frontend/components/novel/NovelSettingsDialog.tsx` | 原生 dialog，调整预算、节奏及模型 |
| `frontend/components/novel/GateBanner.tsx` | 各状态关卡说明和操作 |
| `frontend/components/novel/SetupEditor.tsx` | 立项卡与差量提交 |
| `frontend/components/novel/PlanEditor.tsx` | 细纲编辑、原样批准、改完批准与收费重定稿 |
| `frontend/components/novel/ChapterList.tsx` | 目录、写作进度及六种标记 |
| `frontend/components/novel/ChapterReader.tsx` | 正文、标题剥离、改稿和审校摘要 |
| `frontend/components/novel/DeliberationTimeline.tsx` | 初案、顾问、替代走向、回应、定稿差异与留言回应 |
| `frontend/components/novel/BiblePanel.tsx` | 完整圣经的折叠分块 |
| `frontend/components/novel/NotesPanel.tsx` | 留言、五条待处理限制和主编回应 |
| `frontend/components/novel/NovelContent.tsx` | 结构化内容的纯文本展示和中文字段名 |
| `frontend/components/novel/NovelStates.tsx` | 沿用已有 ErrorNotice/EmptyState/LoadingState 的结构与令牌 |
| `frontend/components/novel/NovelShell.tsx` | iframe 内 Escape 关闭抽屉，原生 dialog 打开时保持其键盘行为 |

### 新增测试与报告

- `backend/tests/test_novel_p2_api.py`：11 条只读接口测试。
- `backend/tests/test_novel_p2_frontend.py`：46 条前端源码契约断言。
- `docs/tasks/2026-10-16-novel-workshop-p2/03-report.md`：本报告。

### 修改文件

- `frontend/components/Sidebar.tsx`：只追加第六项「书斋」、回调、高亮和 `novel-drawer` 映射，原导航样式不变。
- `frontend/app/page.tsx`：新增 `novel` 抽屉和常驻 iframe、同源设置/关闭消息、焦点返回。
- `backend/routers/novel.py`、`backend/novel/service.py`：仅新增完整圣经和全部留言两个只读接口。
- `README.md`、`docs/ARCHITECTURE.md`、`CLAUDE.md`、`PLAN.md`：同步路由、入口、数据流、验证和后续验收事项。

`frontend/proxy.ts` 无需修改。`globals.css`、`package.json`、lockfile、既有测试、运行器与计费模块均无改动。`02-spec.md` 在任务开始时已经是未跟踪文件，本次未编辑。

## 2. 与规格逐节对应

| 规格 | 实现与验证 |
| --- | --- |
| §0 入口与承载 | 侧栏/手机底栏第六项「书斋」；三个独立路由；主页 iframe `/novels?embed=1`；关闭保留 iframe；独立打开移除 embed。 |
| §0 工作台与推演 | 桌面目录/正文/资料三栏；手机三标签；页头下方关卡；完整时间线按拍板顺序展示。失败重试计费逻辑保持 P1。 |
| §1 修改范围 | 文件均在白名单内；最终 `git status --porcelain --untracked-files=all` 与 `git diff --check` 核对。 |
| §2 文档与技术栈 | 写前端前读取 `frontend/AGENTS.md` 及本地 Next 文档的 layouts-and-pages、server-and-client-components、dynamic-routes、use-search-params。客户端页面用 Suspense 包裹查询参数读取。未增加依赖。 |
| §2 请求与隔离 | 共享 `apiFetch`、`apiJson`、`ApiError`；按 owner/id 重挂载，`useAccountRequest` 取消旧请求并检查 isCurrent。未生成圣经时合法 JSON null 单独经 apiFetch 接收。 |
| §2 轮询 | 仅 setup_running/running 用 3000ms setTimeout 链，visibilitychange 隐藏暂停，离开运行态停止；写操作后立即刷新。书架同样只在存在运行书时继续轮询。 |
| §2 正文/导出/对话框 | 无 Markdown 库；正文 whitespace-pre-wrap，剥离首行章节标题；Blob 校验 text/markdown 后创建下载链接并释放 URL；调整用原生 dialog，删除用 confirm。 |
| §2 嵌入 | 三页内链保留 embed；独立打开 target=_blank；所有新增小说布局使用 mobile:，遵从 html[data-shell]。 |
| §3 视觉 | 现有 Glaze/ceramic-card、btn/chip/tag/readout 和主题令牌；无新颜色值、字体或全局样式；书籍状态不用朱印。正文 max-w-[38em]、行距 1.95；输入 16px，可点操作至少 40px，手机底部留安全区。四主题截图尚待人工验证。 |
| §4 完整圣经 | GET /novels/{id}/bible 返回当前版本完整 locked/dynamic 及 compass；立项尚未生成时为 null；不调用 trim_bible。60 章测试核对全部摘要、六卷摘要、60 伏笔、时间线、已用桥段、人物状态与知识。 |
| §4 全部留言 | GET /novels/{id}/notes 按 created_at/id 排序，返回所需字段及 adopted/response，未下发为 null；60 条完整验证。两个接口均测试越权/缺失404、关闭404、白名单403。 |
| §5.1 书架 | 书名/状态/章数上限/预算消耗/更新时间；awaiting_* 与 paused 提示待你处理；规定空态、加载/错误及404/403开放提示。 |
| §5.2 第一步 | 思路2000字与计数/真实示例；章数1–200与顺序校验；每章1000–4000默认2000；折叠改编参数默认6/3。 |
| §5.2 第二步 | catalog 驱动；critique/solo；三必选、默认审校、六顾问最多五；允许模型限制、中文模型名、千token价格、可用BYOK与notice。solo顾问置灰且不提交。 |
| §5.2 第三步 | 三种节奏、每批1–10默认5、预算、600ms防抖估算、规定估算口径、GET /strawberry余额、提交汇总与开始立项；可返回并保留填写；前端就近错误，后端422/409经ErrorNotice。 |
| §5.3 页头与操作 | 书名/罗盘梗概/状态/读数/预算刻线；合法状态暂停或继续；调整预算/节奏及等待状态模型；导出、更多菜单删除二次确认、嵌入独立打开。 |
| §5.3 目录/正文 | 默认最新章、章名/六标记及说明/正在写；改稿30000字、PUT保存后显示后端message；审校保留/丢弃计数、可展开阻断问题和evidence。 |
| §5.3 推演 | 主编初案→分顾问重轻意见及keep→A替代原文及决定/理由→O数字顺序回应→字段原→新/节拍新增删除数→留言回应；兼容旧A文字回应；solo仅显示主编裁决和理由。依据历史meeting识别模式，避免当前solo配置隐藏旧记录。 |
| §5.3 圣经/留言 | 罗盘默认展开，其余折叠；人物状态、open/已回收伏笔及章号、卷/章摘要、时间线，另可查世界规则/文风/已用桥段。留言500字，五条pending禁提交；展示下发章号、采纳与回应。 |
| §5.3 手机 | 目录/正文/推演·圣经·留言三个标签；资料内再分推演/圣经/留言；关卡位于页头与栏目之间。360/390无横滚和截断仍待实际截图。 |
| §5.4 全状态 | 下表逐项对应，源码测试覆盖全部状态标签及关卡文案。操作中禁重复并显示loading，错误用ErrorNotice。 |
| §6 抽屉 | novel-drawer 使用设置抽屉同款Glaze结构、尺寸与drawerStyle；aria/inert/焦点、iframe常驻；BYOK横幅可同源通知主页打开设置，消息同时验证origin与source。 |
| §7 测试 | 新增57条测试通过；全局Lint/tsc通过；webpack生产构建含三路由；默认构建/后端全量的环境限制详见门禁原始末尾。 |
| §8 停止条件 | 未新增全局令牌；现有接口缺少的书架上限/改稿标记经已有详情接口取得，未扩充P1语义。360px底栏源码计算可容纳，未擅改原五项样式，但未宣称截图通过。 |

### §5.4 状态与关卡

| 状态/原因 | 行为 |
| --- | --- |
| setup_running | 立项中及生成罗盘/设定进度，无关卡横幅。 |
| awaiting_setup | 规定提示、罗盘/锁定区编辑器；只提交有变化的字段；422格式提示和前端字段定位。 |
| running | 写作中，无横幅。 |
| awaiting_review | 批次章号、插一句话切到留言、继续下一批。 |
| awaiting_plan | 进入状态自动选待批章，显示细纲；原样/改完批准、附话重定稿及再次扣费提示。 |
| awaiting_end | 确认完结或再写1–10章，可附500字以内说明。 |
| completed | 全书章/字数与导出。 |
| paused / user | 已暂停、继续。 |
| paused / budget_80 | 80%提示、调高预算并继续；保存后调用resume。 |
| paused / insufficient_strawberries | 草莓不足提示、继续。 |
| paused / byok_unavailable | 后端原因、去设置启用或调整为平台模型。 |
| paused / decision_invalid、step_failed | 定稿或步骤失败提示、再次计费说明、重试resume与last_error。 |
| paused / locked_conflict | 冲突提示、定位冲突章、继续。 |
| paused / daily_cap | 北京时间零点提示、继续。 |
| paused / server_restart_failed | 恢复失败提示、继续。 |
| failed | 显示原因，横幅不提供操作。 |

## 3. 实现决定与边界

- P1列表不含章数上限，书架逐本取详情；P1目录不含edited_by_user，工作台首次补读已完成章节并缓存，后续按章数/状态/标记变化失效。本次同字数改稿也在刷新前主动失效缓存，正确显示「你改过」。代价是长书首次打开有逐章读取开销，未改P1接口。
- 现有 ErrorNotice/EmptyState/LoadingState 位于 AgentExchangeWorkspace 内部且未导出；在允许的 novel 目录沿用其结构与已有令牌封装，不改原组件。
- 旧格式替代走向若只有文字回应，保留全文；明确出现采纳/部分采纳/不采纳时显示相应标签，无法明确判断则显示「旧版文字回应」，不编造决定。
- 设置和章节读取有独立账户请求通道，普通刷新保持改稿草稿；切换书籍/账号/章节时重挂载，防止旧请求与草稿污染。

## 4. 门禁命令与输出末尾

所有前端命令均在 `frontend/`，后端命令均在 `backend/` 执行。完整日志仅写入本任务临时目录 `/tmp/fiona-novel-p2-*.log`，不依赖 git 历史或仓库外测试输入。

### Lint：通过

命令：`npm run lint`，退出码0，警告25（不超过38，未增加基线警告）。末尾：

```text
frontend/app/plaza/page.tsx
  602:21 warning Using <img> could result in slower LCP ... @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
```

### TypeScript：通过

命令：`npx tsc --noEmit`，退出码0，输出为空。生产构建完成后再次运行亦为0。

### 指定默认构建：环境阻塞，未通过

命令：`npm run build`，退出码1。末尾核心内容：

```text
> next build
▲ Next.js 16.3.3 (Turbopack)
> Build error occurred
Error [TurbopackInternalError]: [project]/app/globals.css [app-client] (css)
Caused by:
- creating new process
- binding to a port
- Operation not permitted (os error 1)
```

Turbopack 的本地 CSS 处理进程绑定被沙箱拒绝。未修改构建脚本、依赖、Next配置或全局样式来规避验收命令；本环境不允许提权，故原命令仍须在可绑定本地端口的环境复跑。

### webpack补充生产构建：通过，含三路由

依据随包本地 Next CLI 文档的 `--webpack` 选项，命令：`NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack`，退出码0。末尾：

```text
✓ Compiled successfully in 2.4s
  Finished TypeScript in 2.3s ...
✓ Generating static pages using 17 workers (16/16) in 136ms
  Finalizing page optimization ...
  Collecting build traces ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /agents
├ ƒ /agents/[id]
├ ○ /agents/me
├ ○ /community
├ ○ /history
├ ○ /login
├ ○ /manifest.webmanifest
├ ○ /match
├ ○ /novels
├ ƒ /novels/[id]
├ ○ /novels/new
├ ○ /plaza
├ ○ /profile
└ ○ /settings

ƒ Proxy (Middleware)
○ (Static) prerendered as static content
ƒ (Dynamic) server-rendered on demand
```

构建实际显示预置 node_modules 的 Next 版本为16.3.3，package.json声明为^16.3.8；按只读依赖约束保持原样。webpack成功是补充证据，不替代默认构建结果。

### 后端全量：已执行，受本地端口权限阻塞

命令：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q`，退出码1。末尾：

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 5064 passed, 6 skipped, 28 warnings, 5 errors in 129.18s (0:02:09)
```

上述1失败+5错误全部在既有测试创建回环监听时遇到 `PermissionError: [Errno 1] Operation not permitted`：失败用例停在 `asyncio.start_server(..., '127.0.0.1', 0)`，五个setup错误停在 `ThreadingHTTPServer` 的bind，尚未到相关业务断言。既有测试未改动；新增P2测试无失败/错误/跳过。

另以固定解释器在backend执行 `-m pytest -q -rs tests/test_byok_client.py -k 'r1_watchdog_real_loopback or r2_loopback_interrupt_race'` 核对跳过原因，末尾：

```text
SKIPPED [2] tests/test_byok_client.py:652: R1-6 loopback bind is denied by sandbox permissions
SKIPPED [4] tests/test_byok_client.py:882: R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun
6 skipped, 124 deselected in 0.75s
```

### 本次新增测试：全部通过

命令：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_novel_p2_api.py tests/test_novel_p2_frontend.py`，退出码0。末尾：

```text
......................................................... [100%]
57 passed, 28 warnings in 1.29s
```

后端代理亦执行P1接口回归：同一固定解释器 `-m pytest -q tests/test_novel_p1_api.py tests/test_novel_p2_api.py` → `36 passed, 28 warnings in 3.96s`。警告来自既有slowapi弃用提示。

### 文件边界：通过

`git diff --check` 退出码0、无输出；`git status --porcelain --untracked-files=all` 中改动均属于§1范围（另有任务开始时已存在的02-spec.md）。`git diff --name-only -- frontend/package.json frontend/package-lock.json frontend/proxy.ts frontend/app/globals.css` 无输出。未改既有测试、依赖和其他页面。

## 5. 未完成验收与人工确认

1. 在允许回环端口绑定的环境重新执行原样 `npm run build` 与后端全量 `python -m pytest -q`。本次两个机械门禁不能记为完全通过；未通过修改测试、跳过失败用例或变更构建默认选项掩盖。
2. 按§7用P1临时库、tester01和真实推演记录完成1440×900、390×844、360×740的页面/关卡/抽屉截图，以及昼/夜和素瓷两种退路的可读性检查。本会话电脑工具未发现可用浏览器，未启动实际浏览器截图，也未读真实用户库或密钥。
3. **360px手机底栏六项是否放得下：源码尺寸判断可以，尚无实测截图。**原样flex六等分，每项60px；原text-sm为14px，两字与0.2em字距约34px，保留whitespace-nowrap，未添加截断。没有发现必须改动原五项样式的证据，也没有擅改；人工需确认思源宋体实际渲染、字距、六个点击区及无横滚。
4. 长书首屏逐章元数据补读的体验、原生dialog/下载在手机Safari的行为、真实模型输出下的长内容换行仍需实机验收；真实厂商质量、可达性与计费验收沿用P1人工流程，本次未调用任何外部模型。

## 第 1 轮返修

依据 `05-fix-r1.md` 完成 F1–F9。三名子代理继续按文件分工：后端/请求与书架/模型展示、工作台、向导/设置/立项；主代理负责阅读内容、Esc/抽屉、回归测试、文档和门禁。以下记录取代上文中已被返修修正的 N+1 请求、固定三栏和校验处理说明；原报告正文未改。

### 本轮修改文件

本轮共修改或新增19个文件：

- 后端：`backend/novel/service.py`、`backend/tests/test_novel_p2_api.py`。
- 请求与书架/模型：`frontend/lib/novels.ts`、`frontend/components/novel/NovelShelf.tsx`、`frontend/components/novel/NovelModelFields.tsx`。
- 工作台/表单：`frontend/components/novel/NovelWorkbench.tsx`、`NovelWizard.tsx`、`NovelSettingsDialog.tsx`、`SetupEditor.tsx`（后三项同属该组件目录）。
- 内容/抽屉：`frontend/components/novel/ChapterList.tsx`、`ChapterReader.tsx`、`NotesPanel.tsx`、`BiblePanel.tsx`、`NovelShell.tsx`（后四项同属该组件目录），以及 `frontend/app/page.tsx`。
- 测试/文档：只追加用例的 `backend/tests/test_novel_p2_frontend.py`、新增 `backend/tests/test_novel_p2_r1.py`、更新 `docs/ARCHITECTURE.md`，以及追加本节的 `03-report.md`。

未改依赖、锁文件、全局样式、侧栏原样式、其他页面或既有测试，未联网、读密钥、提交commit。本轮新增后端数据仅为获授权的两个字段；单章接口已有的整数型改稿标记保持不变。

### F1–F9 改法与证据

| 项目 | 改法 | 文件:行号与验证 |
| --- | --- | --- |
| F1 容器布局 | 三栏外设 `@container`，1040px及以上显示三栏，下限180/480/300px加两条20px间距；低于阈值显示三标签，面板按容器查询切换。保留38em阅读上限、min-w-0和长文本换行。页头/横幅位置不变。 | `frontend/components/novel/NovelWorkbench.tsx:265`、`:267`、`:268`；`backend/tests/test_novel_p2_frontend.py:127`。webpack产出CSS核实实际存在 `container-type:inline-size`、`@container (min-width:1040px)` 和三栏下限，无需配置或插件。 |
| F2 手机价格 | option文案保持原样，每个select下新增只在mobile显示、可换行的当前价格说明；平台数字readout，BYOK显示完整厂商/型号及不扣草莓。 | `frontend/components/novel/NovelModelFields.tsx:23`、`:32`；实际组件元素树回归 `backend/tests/test_novel_p2_r1.py:295` 验证全部角色价格数字和BYOK文案。 |
| F3 请求数量 | summary增加整数max_chapters；detail目录增加布尔edited_by_user，原字段不变。书架每轮仅GET列表；工作台移除逐章补读与无条件revision刷新。detail轮询驱动圣经版本/首次开启、留言可见/提交/状态章数变化、当前章四字段签名/切章读取。改稿摘要与强刷计数一次发布，只取当前章一次。 | `backend/novel/service.py:159`、`:204`、`:207`；`NovelShelf.tsx:30`、`:49`；`NovelWorkbench.tsx:26`、`:74`、`:131`、`:149`、`:162`、`:179`、`:273`。新增API强断言 `backend/tests/test_novel_p2_api.py:177`；动态请求探针 `test_novel_p2_r1.py:189`、`:200`、`:209`。 |
| F4 独立页侧栏 | 独立模式外层h-dvh/overflow-hidden，内层main overflow-y-auto，侧栏不随正文拉长；嵌入仍沿用原文档滚动。 | `frontend/components/novel/NovelWorkbench.tsx:235`、`:238`；源码契约 `test_novel_p2_frontend.py:127`。 |
| F5 错误处理 | read与operation错误分开；子组件操作传errorTarget=local，页顶不重复。轮询成功只清对应read错误，operation仅下次操作或手动关闭清除。404只有英文Not Found映射未开放，中文原样；403统一账号未开通，三页一致。 | `frontend/lib/novels.ts:149`；`NovelWorkbench.tsx:53`、`:188`、`:204`、`:243`、`:270`。动态回归 `test_novel_p2_r1.py:141`、`:236`、`:287`，覆盖本地错误不重复、页顶操作错误跨成功轮询保留、三个页面关闭态404。 |
| F6 估算/预算/立项 | estimateInput完全不含预算，估算固定传必填预算1，改预算不重发；继续最低预算为max(当前预算+1,ceil(spent×1.25)+1,有效暂停时预算+1)，先就近校验再PATCH/resume；同时覆盖用户先调低预算的边界。立项按Python compact去引号/Unicode空白/折叠省略号，再按Unicode码点计数；422按字段路径定位，未给路径时标出本次改动字段。 | `NovelWizard.tsx:74`、`:107`、`:113`；`NovelSettingsDialog.tsx:10`、`:24`、`:30`；`SetupEditor.tsx:19`、`:23`、`:93`、`:103`（均位于 `frontend/components/novel/`）。动态回归 `test_novel_p2_r1.py:171`、`:252`、`:322`，包括暂停预算1000时当前预算100仍要求1001，以及引号/省略号/特殊空白/补充平面字符。 |
| F7 默认配置 | critique默认；只默认三顾问：情节架构师、人物代言人、反转设计师。主编/档案员/审校/情节用千问，写手/反转用DeepSeek，人物用豆包；不可用退角色首项。选项遵守allowed_models顺序，无限制按catalog.models。 | `frontend/components/novel/NovelWizard.tsx:20`、`:89`；`frontend/lib/novels.ts:160`；动态回归 `test_novel_p2_r1.py:157` 精确核对七个角色、三顾问与排序/回退。 |
| F8 章名去重 | 共享显示辅助函数只剥章名前缀及紧随空白/标点；目录和正文标题使用，存储/正文草稿/导出不改。 | `frontend/lib/novels.ts:169`；`frontend/components/novel/ChapterList.tsx:27`、`ChapterReader.tsx:34`；回归 `test_novel_p2_r1.py:141`、`:295`，覆盖阿拉伯/中文章号及非章号标题。 |
| F9 七项细节 | 留言UTC规范串转本地时间且time保留ISO dateTime；伏笔0章显示立项时；Esc在输入/组字/dialog中不关抽屉；关闭按钮class逐字照抄设置，面板outline-none；embed不留tabbar空间；六个tabs控制目标常驻且tabpanel，当前章aria-current=true；六目录标记换lucide并保留文字/title。 | `NotesPanel.tsx:30`、`BiblePanel.tsx:21`、`NovelShell.tsx:5`（同属 `frontend/components/novel/`）；`frontend/app/page.tsx:2734`、`:2747`；`NovelWorkbench.tsx:238`、`:268`、`:280`；`ChapterList.tsx:3`、`:25`、`:28`。回归 `test_novel_p2_r1.py:209`、`:268`、`:295` 与 `test_novel_p2_frontend.py:141`。 |

### 本轮验证

新增17条用例：API新增1条、原源码测试追加2条、新离线运行行为探针14条；此前57条完整保留。行为探针在内存中转译当前工作树TypeScript，执行实际effect、事件处理器和请求封装，API/定时器均在内存模拟，无真实网络、浏览器依赖、仓库外测试输入或git历史。它不能代替真实浏览器尺寸/截图验收。

已验证的请求行为：60章完结书首屏只取当前章一次；书架初次及三次轮询共4个列表请求；运行书连续三轮不重取未变版本圣经、未变签名章节、隐藏留言；版本/章节签名变化后各取一次；留言可见时刷新；改稿后当前章只取一次；改预算不重发估算，改批次才重发。

**Lint**（frontend）：`npm run lint`，退出码0。末尾：

```text
frontend/app/plaza/page.tsx
  602:21 warning Using <img> ... @next/next/no-img-element
✖ 25 problems (0 errors, 25 warnings)
```

**TypeScript**（frontend）：`npx tsc --noEmit`，退出码0，无输出；补充构建后再次执行通过。

**P2及R1测试**（backend）：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_novel_p2_api.py tests/test_novel_p2_frontend.py tests/test_novel_p2_r1.py`，退出码0。末尾：

```text
........................................................................ [ 97%]
..                                                                       [100%]
74 passed, 28 warnings in 4.19s
```

后端代理另跑P1 API/billing/runner回归：固定解释器 `-m pytest -q tests/test_novel_p1_api.py tests/test_novel_p2_api.py tests/test_novel_p1_billing.py tests/test_novel_p1_runner.py` → `103 passed, 28 warnings in 8.07s`。

**默认生产构建**（frontend）：`NEXT_TELEMETRY_DISABLED=1 npm run build`，退出码1，仍为沙箱限制，未记通过。末尾核心原因：

```text
Error [TurbopackInternalError]: [project]/app/globals.css [app-client] (css)
Caused by:
- creating new process
- binding to a port
- Operation not permitted (os error 1)
```

**webpack补充构建**（frontend）：`NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack`，退出码0。末尾摘要：

```text
✓ Compiled successfully in 1665ms
  Finished TypeScript in 2.7s ...
✓ Generating static pages using 17 workers (16/16) in 148ms
  Finalizing page optimization ...
  Collecting build traces ...
├ ○ /novels
├ ƒ /novels/[id]
├ ○ /novels/new
ƒ Proxy (Middleware)
```

直接检查本次构建产出的CSS亦通过：`container-type:inline-size`、`@container (min-width:1040px)`、`grid-template-columns:minmax(180px,.65fr) minmax(480px,2fr) minmax(300px,1fr)` 均存在。未改变默认构建脚本或配置。

**边界与断言保持**：以本轮动手前的工作树内容做哈希/文本比较（非git历史）：157个既有测试文件全无变化；`test_novel_p2_api.py`原23个assert、`test_novel_p2_frontend.py`原33个assert及其所在原文件全文前缀逐字保留，只有末尾新增测试。`git diff --check`为0；依赖、锁文件、globals.css无diff。04-review-a/b及05-fix-r1为用户提供的本轮输入，未修改。

**后端全量**（backend）：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q`，退出码1。原始末尾：

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 5081 passed, 6 skipped, 28 warnings, 5 errors in 131.73s (0:02:11)
```

端口类问题单列：上述1个失败在 `asyncio.start_server(..., '127.0.0.1', 0)`，5个setup错误在共享 `ThreadingHTTPServer` fixture的socket.bind，均抛 `PermissionError: [Errno 1] Operation not permitted`，没有进入对应业务断言。六个跳过另以固定解释器 `-m pytest -q -rs tests/test_byok_client.py -k 'r1_watchdog_real_loopback or r2_loopback_interrupt_race'` 确认：

```text
SKIPPED [2] tests/test_byok_client.py:652: R1-6 loopback bind is denied by sandbox permissions
SKIPPED [4] tests/test_byok_client.py:882: R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun
6 skipped, 124 deselected in 1.04s
```

相对返修单5076条基线，本轮新增17条，共5093条；当前沙箱5081通过，其余12条均为以上端口绑定限制（6个失败/错误、6个跳过）。没有新增的功能测试失败或跳过，未修改测试去规避环境限制。完整本轮门禁日志保留于 `/tmp/fiona-p2-r1-*.log`。

### 未完成验收与人工确认

1. F1–F9没有已知未完成的实现项。需由验收方按F1指定的768/1024/1280/1440/1920宿主抽屉、1024/1280/1440独立页，以及360/390手机宽度、昼/夜主题复拍：确认文档和各滚动容器无横向溢出，正文宽度达到420px或进入三标签布局。已验证容器查询生成正确，但本轮未将CSS/元素树探针当作实际浏览器截图。
2. 360px手机六项底栏沿用本轮复核B已确认可容纳的原样式，本轮未修改Sidebar。模型价格新增独立可换行说明已用实际组件元素树验证，仍需360px实拍确认视觉完整可见。
3. 在允许回环端口绑定的环境复跑原样 `npm run build` 和后端全量测试；本沙箱的默认构建及全量结果不能记为全部通过。webpack补充构建不替代默认命令。
4. 继续保留上一轮的真实厂商质量/成本、手机Safari原生dialog和下载验收事项；本轮未调用外部模型、未读取真实用户库或密钥，未提交commit。

## 第 2 轮返修

依据 `05-fix-r2.md` 完成 R2-1、R2-2、R2-3。本轮仅修改以下四个文件，已有测试输入与断言保留；未改依赖、联网、读取密钥或提交commit。

| 文件 | 修改与证据 |
| --- | --- |
| `backend/tests/test_novel_p2_r1.py:130` | R2-1：probe开始时检查本工作树的 `frontend/node_modules/typescript`，缺失时按指定文案skip；保留无Node时的原有skip。R2-3：`:150`、`:151` 新增「第二章」与「第三章节的秘密」两条边界断言，没有放宽或删除已有断言。 |
| `frontend/components/novel/NovelWorkbench.tsx:270` | R2-2：ChapterReader加载条件恢复为 `chapterLoading || (selectedChapter != null && !currentChapter)`，切章首帧尚未取得对应正文时直接显示加载态。 |
| `frontend/lib/novels.ts:169` | R2-3：章号后必须接空白、标点或字符串结尾才剥离；剥离结果为空时回退原章名，避免误改「第三章节的秘密」及只含章号的标题。只影响显示。 |
| `docs/tasks/2026-10-16-novel-workshop-p2/03-report.md` | 只在末尾追加本节，原报告保持完整。 |

### 验证结果

**无node_modules临时目录：已实际执行。**在 `/tmp` 创建临时根，按相对结构复制测试文件、`frontend/lib`、`frontend/components/novel`；为测试收集阶段的纯schema导入，另外复制本仓库的 `backend/novel/__init__.py`、`schemas.py` 两个文件。执行前断言临时树内没有任何node_modules目录、系统Node存在。未借用原工作树的前端依赖，临时目录在验证结束后清理。

在临时树的backend目录执行：

```text
/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -rs tests/test_novel_p2_r1.py
ssssssssssssss                                                           [100%]
=========================== short test summary info ============================
SKIPPED [14] tests/test_novel_p2_r1.py:132: frontend/node_modules/typescript is unavailable
14 skipped in 0.01s
```

退出码0，0 failed。输出另存于 `/tmp/fiona-p2-r2-no-node-modules.log`。

**正常工作树：14条全部通过，无skip。**在backend目录使用相同固定解释器执行：

```text
/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_novel_p2_r1.py
..............                                                           [100%]
14 passed in 2.70s
```

**前端检查**：frontend目录 `npm run lint` 退出码0，末尾 `✖ 25 problems (0 errors, 25 warnings)`；`npx tsc --noEmit` 退出码0，无输出。`git diff --check` 退出码0。按本轮开始时的工作树快照校验，改动仅在本单四个文件；原报告字节前缀保持。本轮为小返修，验证范围为以上定向测试、Lint和TypeScript，未重复生产构建与后端全量。

### 待人工确认

R2-1两种环境均已实测通过，三项修改无已知未完成项。可在实际浏览器切换章节复验加载观感；本轮没有新增截图或外部模型验收项。
