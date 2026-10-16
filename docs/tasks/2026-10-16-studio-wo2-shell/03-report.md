# WO2 实现与验收报告

1. 修改文件

前端请求层：`frontend/lib/studio.ts`。

页面：`frontend/app/studio/page.tsx`、`frontend/app/studio/[id]/page.tsx`。

组件：`frontend/components/studio/{StudioShell,StudioShelf,StudioWorkbench,StudioBudget,ClipComposer,QuoteDialog,ShotWall,ShotCard,StudioAssetImage}.tsx`；整合 `frontend/components/Sidebar.tsx`、`frontend/app/page.tsx`。

后端：`backend/database.py`、`backend/routers/studio.py`、`backend/studio/{store,scheduler,notices}.py`。

新增测试：`backend/tests/test_studio_frontend_components.py`、`test_studio_frontend_navigation.py`、`test_studio_frontend_shell.py`、`test_studio_wo2_backend.py`。

文档：全库搜索现有工作室描述后更新 `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`frontend/README.md`，并新增本报告。`02-spec.md` 在任务开始时已是未跟踪文件，未修改。

`package.json`、lockfile、`globals.css` 和所有已有测试均未修改；未新增依赖、未发起真实供应商网络请求、未 commit。没有启动浏览器或生成截图。

2. 实现功能

作者门禁后的项目列表、新建项目、项目详情、今日占用/上限/剩余，以及五阶段工作台。默认「④镜头」可用，其他四阶段仅显示后续开放的空态。

单镜首帧上传及本地格式/20MB 校验、鉴权 blob 预览与 objectURL 回收；提示词、双模型、分辨率、整数时长、音频开关；报价区间、剩余额度、有效期倒计时与确认锁。422/409 中文 detail 原样展示。

镜头墙完整呈现 13 状态、费用和成片播放；排队取消、人工复查、关联任务号、不确定任务警示与二次确认释放；重新报价只回填参数。在途时每 5 秒刷新任务和额度，隐藏暂停、操作中跳过、终态停表，操作后立即刷新；账号切换和卸载取消请求。补测并修复隐藏/显示发生于请求中途时的重复轮询链。

桌面入口与主页抽屉通过 access=200 门控；embed 内链、Esc、原生 dialog 守卫与同源/source 校验沿用小说写法。聊天每 10 秒可见轮询，首次只建完整基线、404 永久停表、错误保留游标；空闲当前会话按 dbId 去重插入，其他会话提供项目名 chip，共用本机提醒系统通知开关。

后端新增 owner 隔离的只读项目/素材接口和通知游标接口；六类通知终态通过默认会话的普通 assistant 消息保存，job 唯一去重、失败独立补写、删号同事务清理。新增故障注入验证已保存消息复用、同正文任务并发不误关联、通知失败后状态变化仍补首个提醒、删号后不复活。

3. 与规格第 3–5 节逐条对应

| 规格项 | 实现位置与验证 |
| --- | --- |
| 3.1 全部请求、13 状态/错误中文、embed 链接、解析字段 | `lib/studio.ts`；shell 请求/标签/回填探针 |
| 3.2 列表、额度、新建 dialog、三态、access 404、动态 id、五阶段、嵌入关闭 | studio 两页与 Shelf/Workbench/Shell/Budget；shell 与 navigation 探针 |
| 3.3 试拍上传、提示词、默认模型/参数、报价防重复 | ClipComposer/StudioAssetImage；components 上传/成功路径/422/账号取消与 blob 回收探针 |
| 3.3 报价区间、剩余额度、倒计时、过期禁用、确认锁、409、取消无请求 | QuoteDialog；components SSR 与真实事件/定时器探针 |
| 3.3 镜头墙 13 状态、首帧、费用、视频、取消/复查/关联/释放/回填 | ShotWall/ShotCard；13 状态 SSR、video URL 与二次确认/只回填行为探针 |
| 3.3 五秒轮询、隐藏暂停、忙时跳过、终态停止、操作刷新、账号取消 | StudioWorkbench/useAccountRequest；shell 定时器/操作/账号与中途可见性变化探针 |
| 3.4 静态六项、运行时门禁入口、手机底栏、主页 iframe 门禁与关闭校验 | Sidebar/app/page；navigation 200/404/错误/账号切换探针及抽屉合同；保留 `"novel" | null` 子串 |
| 3.5 提醒基线/永久 404/游标重试、当前会话标准消息与 dbId 去重、跨会话 chip、共用通知开关 | lib/studio/app/page；shell poller 分页/错误/暂停/去重探针与 navigation 合同；原 localWatch 实现未改 |
| 4.1 两个只读接口、owner 隔离、别人的资源 404、素材不返 rel_path | routers/studio/store；wo2_backend 门禁与隔离测试 |
| 4.2 studio_notices 表、job_id 唯一、summary ≤200、删号同事务 | studio/store/database；wo2_backend 表约束/删号测试 |
| 4.3 六类终态、仅一条、失败不影响状态结算、下 tick 补写、默认真实会话/消息、隐私模板 | studio/notices/scheduler/database；wo2_backend 六态、并发、故障注入、会话/messages、正文隐私测试 |
| 4.4 notices 游标、50 条、owner、private/no-store、完整返回字段 | routers/studio/database；wo2_backend 分页、门禁与响应头测试 |
| 5.1 侧栏 | 新增 navigation 测试；原小说前端测试保持通过 |
| 5.2 ShotCard | 新增 components 13 状态 SSR/操作/警示/释放/回填/video 测试 |
| 5.3 QuoteDialog | 新增 components 金额/按钮/倒计时/取消/409/双击锁测试 |
| 5.4 任务轮询 | 新增 shell 五秒、终态、隐藏、忙时、重复链防护测试 |
| 5.5 提醒轮询 | 新增 shell 首次基线、分页、游标重试、暂停、永久404、dbId去重测试 |
| 5.6 后端 | 新增 wo2_backend 18 个用例（含参数化） |
| 5.7 全量回归，已有测试不改 | 见第 4 项，未使用 deselect；沙箱绑定端口失败单列 |

4. 检查结果

所有后端命令均在 `backend/` 使用指定解释器 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python` 执行。

新增四个测试文件合跑：`-m pytest -q tests/test_studio_frontend_shell.py tests/test_studio_frontend_components.py tests/test_studio_frontend_navigation.py tests/test_studio_wo2_backend.py`，**45 passed，29 warnings，7.01s**。后端新增及原 api/store/scheduler 回归 **221 passed**；导航及原小说/本机提醒前端回归 **68 passed**。

最终全量 `-m pytest -q`：**5916 passed、6 skipped、1 failed、5 errors、29 warnings，155.38s**，退出码 1。未达到全量 0 failed；失败均为下述沙箱端口限制，未传任何 deselect/忽略参数。以下六个既有用例均因沙箱禁止绑定本机端口（`PermissionError: [Errno 1] Operation not permitted`）无法运行完成：

| 类别 | 用例 |
| --- | --- |
| failed | `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot` |
| error | `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive` |
| error | `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline` |
| error | `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work` |
| error | `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline` |
| error | `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch` |

前端均在 `frontend/` 执行：`npm run lint` **exit 0，0 errors、25 条既有 warnings**；`npx tsc --noEmit` **exit 0**。

`npm run build` **exit 1**：Turbopack 处理 `app/globals.css` 时内部 PostCSS 子进程尝试绑定端口，沙箱拒绝，报 `binding to a port / Operation not permitted (os error 1)`；没有修改该 CSS 文件。

补充构建 `NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack` **exit 0**，完成编译、TypeScript、17 个静态页面生成与动态 `/studio/[id]` 构建。此补充结果不替代默认命令的失败记录。

`git diff --check` 通过；`git diff --exit-code -- frontend/package.json frontend/package-lock.json frontend/app/globals.css backend/tests` 通过，确认禁止修改的文件和全部已有测试未改。

5. 未完成或需要人工确认

手机底栏保留原六项，不加入工作室第七项；工作室可从桌面侧栏或直接 URL 访问。360px 空间不再增加一个入口。

截图按要求留给主控：仍需在 1440/1024/768/390/360 五种宽度下人工确认视觉与无横向滚动。没有进行真实付费生成或访问供应商控制台。

默认 Turbopack 构建及全量测试中需要绑定端口的既有用例，需在允许本地端口的环境复验，具体失败见第 4 项。
