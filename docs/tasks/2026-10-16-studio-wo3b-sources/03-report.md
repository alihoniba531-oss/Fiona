# WO3b 作品接入与聊天读小说实施报告

工作区：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`，分支：`short-film-studio`。全程离线，不新增依赖，不提交。采用三个子代理分别负责后端来源、两条聊天路径、前端，主代理负责文档、交叉审查及统一验收；分工按文件隔离。

## 1. 修改文件

共 34 个实现、测试和报告文件（不含用户提供的 `02-spec.md`）：

- 后端新增：`backend/studio/sources.py`、`backend/studio/novel_chat.py`。
- 后端修改：`backend/studio/store.py`、`backend/routers/studio.py`、`backend/database.py`、`backend/services/claude_agent.py`、`backend/services/chat_service.py`、`backend/intent_router.py`、`backend/rate_limit.py`、`backend/routers/chat.py`。
- 前端新增：`frontend/components/studio/CreateProjectDialog.tsx`、`SourceChoices.tsx`、`SourcePanel.tsx`（后三者均在同目录），以及 `frontend/components/novel/NovelFilmDialog.tsx`。
- 前端修改：`frontend/components/studio/StudioShelf.tsx`、`StudioWorkbench.tsx`、`frontend/lib/studio.ts`、`frontend/components/novel/NovelWorkbench.tsx`、`GateBanner.tsx`、`frontend/components/ChatBubble.tsx`、`ChatModelSection.tsx`。
- 测试新增：`backend/tests/test_studio_sources.py`、`test_studio_sources_readonly_integration.py`、`test_studio_sources_frontend.py`、`test_novel_chat.py`、`test_novel_chat_frontend.py`（均在 `backend/tests/`）。
- 测试修改：`backend/tests/conftest.py`、`backend/tests/test_studio_frontend_shell.py`、`backend/tests/test_studio_brain_frontend.py`。
- 文档与配置：`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example`、`docs/tasks/2026-10-16-studio-wo3b-sources/03-report.md`（本报告）。

## 2. 实现功能

- 小说工坊只读候选查询、改编作品优先、合格判定与 flags 提示；完整正文、圣经、罗盘和精简细纲生成版本化快照，支持一致性重读、原作改动检测、乐观版本同步与哈希校验。
- 上传 txt/md/docx、粘贴文本及本人短视频创意搭档成稿统一为版本化快照；保留全文偏移，支持 UTF-8/BOM、GB18030、标题优先切分及约万字切块，限制文件、XML 和正文大小。文件 fsync/rename 后事务写库，失败回滚，旧版归档保留，删号同步清理新表。
- Claude 与平台两条聊天路径共用 `sources` 公开的列书、当前原文读取、免费做成片；`novel_chat` 承载共享内部实现。默认关闭，动态添加工具/意图，按工坊白名单、危机及工作室身份准入；6000 字正文上限、状态提示、书名消歧、每日成功读取上限、原文数据声明及 JSON 模型数据块、30 分钟会话隔离续读、预扣退款均有测试。
- 工作室新建来源选择、项目来源面板、小说做成片对话框与聊天卡片。

## 3. 与规格逐项对应

| 规格项 | 对应实现与验证 |
| --- | --- |
| T1-1–3 只读准入、候选与查找 | `sources.novel_access/list_candidates/find_candidates`；16 组与 workshop_user 一致性、资格原因、flags、改编优先、唯一精确匹配和本人项目列表测试。 |
| T1-4 小说快照与一致性重读 | `take_novel_snapshot`；分批至多 50 章、限定元信息/六项细纲、递归去内部 config 键、全量圣经与独立罗盘、缺章/空正文指明章号、变化重读一次后 409。原始章文件与哈希逐字验证。 |
| T1-5–6 编码、docx、清理和切分偏移 | `normalize_text/split_text`；严格两种编码、C0 清理、段落/tab/br、UTF-8/16/32 DOCTYPE 拒绝及 XML 大小限制；四类标题、优先级、前言、行/段/句末切分和全文切片等值验证。 |
| T1-7 文本及交流快照 | `take_text_snapshot/take_exchange_snapshot`；10 MB/50 万字上限、full.txt/字符偏移、交流归属/固定官方搭档/完成/成稿条件及旧 summary 回退。 |
| T1-8–10 差异检测、同步及快照读取 | `source_status/sync_source/read_snapshot`；正文与标题变更、增删章、圣经升级、unavailable、expected_no、在途 brain 拒绝、新版递增且旧目录保留、篡改记日志并 500。实际数据库集成亦验证原作删除后快照仍可读。 |
| T2 路由、模型校验、建项目回滚、返回增字段 | 8 个新接口沿用 studio gate；JSON extra=forbid、multipart 拒绝未知/重复字段、严格画幅、空白项目原行为、失败不留空项目；DDL 与补列迁移同增三个项目字段和 snapshots 表，删号事务同删新表。 |
| T3 准入、免费读取与每日上限 | `FIONA_NOVEL_CHAT` 默认 0，字面 1 + 工坊白名单 + 非危机；做成片额外用 auth_method/studio gate；新增 novel_read 每日成功读取默认 60，未加入计费集合，列书/建项目不计。 |
| T3 Claude 动态工具及关闭兼容 | `client_tools_for_turn` 逐请求追加三个工具，关闭/不准入返回原 CLAUDE_CLIENT_TOOLS 对象；整数严格排除 bool，非法参数返回工具结果。实测关闭与白名单外请求序列化字节、SSE、历史及退款一致，保留每轮四工具与可见字数守卫。 |
| T3 平台意图、直接回复、历史与会话续读 | 三个意图仅准入时追加提示并归一化；缺 book 追问；直接显示保留换行的原文、保存历史及续读提示；chat_slot_state 按用户+会话保存位置 30 分钟，继续读/接着念不串会话。模型数据采用单独 JSON 文本，原文有明确数据声明。 |
| T3 前端工作室卡片及隐私说明 | ChatCard 新分支仅接受受限 /studio/ 链接，用普通 a；error 仅显示原因；独立隐私段落。SSR 覆盖合法/非法 URL 与错误态；app/page.tsx 拷贝逻辑和旧固定段落不变。 |
| T4 四份配置与架构文档 | 已全库搜索相关配置及功能说明位置，更新 `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example`；补开关、上限、来源、快照目录、准入、隐私与删号清理说明。 |
| F1 多来源新建对话框 | `CreateProjectDialog/SourceChoices/StudioShelf`；五种来源、小说筛选与不可选原因、中文 flags、已有项目链接、上传限制、实时字数、画幅、加载/错误/空状态、建立快照忙态与 embed 跳转，离线组件与 SSR 覆盖。 |
| F2 来源状态面板与同步确认 | `SourcePanel/StudioWorkbench`；只在拆解页挂载时检查一次、手动重查不轮询，显示摘要/flags/差异/不合格/不可访问/空白态；原生 dialog 带 expected_no 同步。BrainTrial 文件未改。 |
| F3 小说页头及完结横幅做成片 | `NovelWorkbench/GateBanner/NovelFilmDialog`；完结且单次访问检查通过才显示两个入口，共用原生 dialog、候选资格、已有项目打开/再建、标题画幅、成功 embed 跳转；非作者 404 隐藏。 |

## 4. 测试结果

后端使用现有虚拟环境 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`（系统无 `python`，系统 `python3` 未安装 pytest），不安装任何依赖。统一验收日志保存在 `/private/tmp/`。两轮均在 `backend/` 执行 `python -m pytest -q -ra --junitxml=<日志路径>`，没有 deselect；通过 PATH 选择上述现有虚拟环境。

前端 lint 修改前基线：**0 errors、25 warnings**。

- 来源专项：85 passed。
- 聊天新专项 + Claude runtime/routing + chat_image_tool：256 passed（新增聊天专项 48 项）。
- 真实库只读/漂移/归属/静态扫描/重复取消集成：5 项，通过；与 sources 和前端新专项合跑 **131 passed**。
- 前端新增专项最终 41 项（初版 39 项，加 URL 尾随 LF/CRLF 两项），全部通过；原文档固定段落与聊天拷贝契约由既有回归保留。
- 缺依赖环境末轮额外复跑 sources：85 passed，覆盖未命名立项作品的候选标题回退；最后复查还确认 expected_no 为 0/-1 等不符整数时返回规格要求的 409（bool 仍 422），来源专项再跑 85 passed。

| 验收 | 结果 | 日志 |
| --- | --- | --- |
| 临时隐藏 node_modules 的完整 pytest（无 deselect） | **6521 passed、103 skipped、1 failed、5 errors**，32 warnings，170.91 秒 | `/private/tmp/fiona-wo3b-hidden.log`、`.xml` |
| 恢复 node_modules 的完整 pytest（无 deselect） | **6618 passed、6 skipped、1 failed、5 errors**，32 warnings，188.75 秒 | `/private/tmp/fiona-wo3b-restored.log`、`.xml` |
| `npm run lint` | **通过：0 errors、25 warnings**，等于基线 | `/private/tmp/fiona-wo3b-lint.log` |
| `npx tsc --noEmit`（实际以 `--no-install` 禁止下载） | **通过：exit 0** | `/private/tmp/fiona-wo3b-tsc.log` |
| `npm run build` | **受沙箱限制失败**：Turbopack/PostCSS worker 绑定端口被拒绝 | `/private/tmp/fiona-wo3b-build.log` |
| 补充 `npm run build -- --webpack` | **通过：exit 0**，全部页面生成完成 | `/private/tmp/fiona-wo3b-build-webpack.log` |
| `git diff --check` | **通过** | 最终现场检查 |

缺依赖环境中，本期新增测试为 **147 passed、32 skipped、0 failed、0 errors**；两个新 Node 测试入口实际需要的 TypeScript、React、jsx-runtime、react-dom/server 缺失时均先 skip。32 个依赖驱动用例全部跳过（来源前端 15、聊天卡片 17），8 个依赖缺失守卫元测试和独立隐私文案静态测试继续通过。两轮没有新增 skip 或 deselect 来避开后端失败。

恢复依赖后，本期新增 **179 项全部通过**；全部工作室测试 **1078 passed、0 failed、0 errors**。缺依赖时全部工作室测试 **1015 passed、63 skipped、0 failed、0 errors**。已逐个解析两份 JUnit XML，确认两轮唯一未通过项是同一组既有端口绑定失败，全部含 PermissionError/operation not permitted：

- failed：`test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`。
- error：`test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`。
- errors：`test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_four_stuck_resolutions_do_not_block_another_fetch`。

因此后端全量尚未达到 0 failed/0 error，必须由主控在允许本机端口绑定的环境复跑。两轮共同的 6 skipped 是既有 BYOK 回环绑定测试自行跳过；没有改动这些测试。32 条警告均为既有 slowapi 在 Python 3.14 的 asyncio 弃用告警。

目录隐藏使用 try/finally，恢复前后 inode 均为 **63204392**（`/private/tmp/fiona-wo3b-hidden-control.log`）；已核对原 `frontend/node_modules` 存在且 `frontend/node_modules.__hidden` 不存在。首轮修复 DOM 契约和最终取消/安全 URL 边界后，重新执行统一验收；曾并行运行 tsc 与 webpack 导致 `.next/types` 生成竞争，已在构建完成后单独重跑 tsc 并通过。

## 5. 非工作室测试固定值变更

**没有修改非工作室测试的固定值、哈希或断言。** `conftest.py` 仅设 `FIONA_NOVEL_CHAT` 默认值为 0。

两处工作室旧测试因 F2 明确增加来源面板而更新：

- `test_studio_frontend_shell.py::test_workbench_stages_and_access_404_do_not_fetch_project`：原本精确断言拆解页占位文案，现精确验证 SourcePanel 的 projectId 为 project、owner 为当前用户，并保留仅一个活动 tabpanel 及门禁检查。
- `test_studio_brain_frontend.py::test_workbench_legacy_project_keeps_wo2_stage_empty_state`：旧项目仍不挂载 BrainTrial；精确验证拆解页两个子项依次为归属正确的 SourcePanel、含原占位文案的 EmptyState，并验证仅一个活动 tabpanel。首轮全量揭示此旧 DOM 结构契约需要同步，修正后专项 19 passed。

没有删除测试或放宽断言。最终复查另修复 URL 尾随 LF/CRLF、长书名自动增高，以及 SQLite 已提交但 awaiter 连续取消时保留快照目录的问题；补充两个 URL SSR 参数和真实数据库重复取消用例。

## 6. 未完成或需要人工确认

无已知功能缺项。仍需人工确认的验收项：

1. 在允许绑定本机端口的沙箱外环境复跑完整后端测试。此环境既有回环测试的 `PermissionError: [Errno 1] Operation not permitted` 没有通过 deselect、删测试或新增 skip 规避；最终两轮具体结果在上节列出。
2. 在沙箱外复跑默认 `npm run build`。当前 Next 16 Turbopack 在 `app/globals.css` 的 PostCSS worker 创建过程中绑定端口失败，报 `Operation not permitted (os error 1)`；没有改依赖、构建脚本或全局样式来掩盖。补充的 `npm run build -- --webpack` 已通过。
3. 390px 真实浏览器响应式烟测及作者真实账号流程尚未人工执行。组件采用视口宽度约束、min-w-0、换行与长书名自动高度，关键状态已由离线组件/SSR 测试覆盖；未将静态验证描述为浏览器实测。真实厂商请求和付费调用不属于本次离线验收。

## 7. 二次修改（R1）

本节对应 `04-review.md` 末尾第 1–9 条返修指令及本轮补充要求。沿用 `short-film-studio` 工作区，按文件并行分工：来源与快照、聊天原文处理、前端交互；主控负责文档、交叉审查和统一验收。未联网、未新增依赖、未提交，未修改非工作室测试的固定值。

### 修改文件

- `backend/studio/sources.py`、`backend/studio/novel_chat.py`。
- `frontend/components/studio/SourceChoices.tsx`、`frontend/components/studio/StudioWorkbench.tsx`、`frontend/components/novel/NovelFilmDialog.tsx`。
- `backend/tests/test_studio_sources.py`、`backend/tests/test_studio_sources_frontend.py`、`backend/tests/test_studio_frontend_shell.py`；新增 `backend/tests/test_studio_novel_chat_threads.py`。
- `docs/CYBER_AVATAR_PLATFORM.md`、本报告。

### 指令对应与额外异步路径检查

| 指令 | 本轮修改 |
| --- | --- |
| 1 阻塞 I/O 线程化 | 点名的 normalize_text、split_text、_write_snapshot 全部通过 asyncio.to_thread；额外线程化清单/章节读取校验、整书哈希和组装、漂移比较、交流文本检查及失败目录清理。保持路径校验、错误转换、原文及归档语义；线程写入/清理在连续取消后也等待真实完成。 |
| 2 整卡选中态 | 小说候选卡片选中时整卡加 ring，与成稿卡片一致；保持 chip 的 aria-pressed。 |
| 3 默认页签 | 只在项目首次成功读取时初始化：source_kind 非空落①拆解，空白项目保持④镜头；鼠标/键盘手动切换标记 touched，刷新不得重置。 |
| 4 rename 竞争 | EEXIST/ENOTEMPTY/EISDIR 转工作室 409「快照已更新，请重新检查」，清理本次 part 目录。 |
| 5 目录 fsync | rename 后打开父目录、fsync 并 finally 关闭 fd；仅 Windows 不支持目录操作的 errno 可忽略，EIO 等真实错误继续传播，POSIX 错误清理本次已 rename 目录后回滚。 |
| 6 文档残留 | CYBER_AVATAR_PLATFORM 中每日上限改为八项，补 novel_read 默认60、只计成功读取、不扣草莓。 |
| 7 旧工作流成稿回退 | artifact 空白时，只有 workflow_version 为空/0 的旧交流可回退 summary；新工作流摘要不充当成稿。 |
| 8 按钮主次 | 做成片对话框有已有项目时，「打开」为 primary、「再建一个」为普通 btn；其他调用点保留原默认样式。 |
| 9 测试与报告 | 本节追加本轮文件、逐条实现、测试清单与验收结果；非工作室测试固定值零变更。 |

本轮逐个检查 `sources.py` 与 `novel_chat.py` 的 async 函数，实际线程化清单：

- `normalize_text`：上传/粘贴、交流列表、交流导入的解码、换行与控制字符清理、docx 解压/XML 解析。
- `_validate_text_source`、`split_text`、`_assemble_text_snapshot`：大文本空白检查、标题/段落切分、块清单与各块 UTF-8/SHA-256。
- `_assemble_novel_snapshot`：缺章/空章校验、总字数、全章哈希、精简细纲、递归配置过滤、圣经/罗盘与清单组装。
- `_exchange_artifact`：成稿空白检测及旧工作流 summary 回退。
- `_write_snapshot`：目录与文件写入、JSON 编码、哈希、逐文件 fsync、rename、父目录 fsync 及写入中失败清理。
- `_discard_directory`：数据库失败或取消后的快照递归删除、空父目录清理。
- `_read_manifest`：`source_status` 与 `read_snapshot` 的 manifest 读取、SHA-256 校验及 JSON 解析。
- `_compare_drift`：原作各章 UTF-8 编码、SHA-256 与增删改比较。
- `_read_snapshot_chunks`：读取范围校验、章文件读取、SHA-256 校验与 UTF-8 解码。
- `novel_chat._render_read_novel`：章节索引、最多 6000 字裁切、跨章拼接、stale/跳过/续读整理、用户可见正文及模型 JSON 数据块编码。旧返回键、正文、提示文案及数据声明保持。

其余留在事件循环上的操作只处理有限书目/章节的标题、状态、数字等轻量元数据，或调用既有异步数据库/只读小说服务；没有直接整本书文件读写或大正文解析。线程不因父协程取消而停止，因此快照写线程、清理线程、DB commit 和空项目回滚都经 `_finish_task` 反复 shield 等待真正结束，再传播取消；防止线程随后留下正式孤儿目录或清掉已提交快照。

### 测试与验收

沿用已有虚拟环境 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，不安装依赖。

新增/修改测试：

- `test_studio_sources.py`：新增30项，含 to_thread 函数调用记录、9类 worker 阻塞期间事件循环继续响应、3个连续取消时点、3种 rename 竞争 errno、已有目录保留、目录 fsync 顺序/失败/Windows 兼容，以及旧/新工作流回退矩阵。原写入/数据库失败、原文与哈希、只读等回归保留；legacy 测试显式 workflow_version=None。来源与真实库集成合跑120 passed。
- `test_studio_novel_chat_threads.py`：新增9项，验证双入口真实线程ID/调用记录、完整 human/model 返回值、50万字章的6000字裁切、stale/跳过/offset/定界符隔离、错误路径不启动正文整理，以及 worker 阻塞期间事件循环继续响应。与聊天专项、真实库集成合跑62 passed。
- `test_studio_frontend_shell.py`：新增7项参数化场景，覆盖4种来源首次默认①，鼠标/键盘切页后完整刷新及轮询保留，以及首载空白的项目不因后续字段变化重新初始化；原空白项目默认④断言保持。
- `test_studio_sources_frontend.py`：补强既有两项，精确验证整卡 selected ring/aria-pressed、无选中时无ring、已有项目打开的 primary class/embed链接、再建一个普通btn，无已有项目时创建按钮仍primary。

统一命令与结果（所有后端命令均在 backend/，前端命令在 frontend/）：

| 命令 | 结果 |
| --- | --- |
| `python -m pytest -q tests/test_studio_sources.py tests/test_novel_chat.py tests/test_studio_sources_readonly_integration.py tests/test_studio_sources_frontend.py tests/test_studio_frontend_shell.py tests/test_studio_brain_frontend.py` | **218 passed**，32 条既有 slowapi 弃用警告，13.84秒 |
| `python -m pytest -q tests/test_studio_*.py tests/test_novel_*.py -ra` | **2807 passed**，32条既有警告，67.20秒 |
| `python -m pytest -q -ra`（完整，不带 deselect） | **6664 passed、6 skipped、1 failed、5 errors**，32条既有警告，194.99秒；全部工作室测试 **1124 passed** |
| `npm run lint` | **通过，0 errors / 25 warnings**，与本轮及初版基线相同 |
| `npx tsc --noEmit`（实际加 `--no-install` 禁止下载） | **通过，exit 0** |
| 临时隐藏 node_modules 后跑 `test_studio_sources_frontend.py`、`test_studio_frontend_shell.py` | **5 passed / 31 skipped**；Node依赖缺失时先 skip，元测试正常运行 |
| `git diff --check` | **通过** |

本轮新增46项测试（来源30、聊天线程9、页签7），另补强2项既有前端用例；没有改非工作室测试固定值，也没有为规避后端失败添加 skip/deselect。缺依赖验证使用 try/finally，恢复后 inode仍为63204392，确认 node_modules存在、node_modules.__hidden不存在。

日志/XML：`/private/tmp/fiona-wo3b-r1-review-targeted.{log,xml}`、`fiona-wo3b-r1-related.{log,xml}`、`fiona-wo3b-r1-full.{log,xml}`、`fiona-wo3b-r1-node-hidden.{log,xml}`；前端日志 `fiona-wo3b-r1-lint.log`、`fiona-wo3b-r1-tsc.log`（均在/private/tmp/）。

### 未完成或需人工确认

第1–9条功能修改及补充异步路径检查均已完成，无已知功能遗留。前端lint/tsc、指定专项、全部工作室及小说专项均通过；全量未达到0 failed/0 error，仍需主控在允许绑定本机端口的沙箱外环境复跑。

已逐个解析末轮JUnit XML，唯一未通过项仍是初版同组既有回环端口测试，全部为 PermissionError / operation not permitted，未修改或屏蔽：

- failed：`test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`。
- error：`test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`。
- errors：`test_safe_http_deadline.py` 的 `test_drip_response_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_four_stuck_resolutions_do_not_block_another_fetch`。

共同的6个skip是既有BYOK回环测试自行跳过；本轮没有为失败添加skip/deselect。未进行联网或真实厂商调用，也未重新做真实浏览器视觉实测；本轮未要求重新build。最终确认node_modules已恢复、隐藏目录不存在，git diff --check通过。
