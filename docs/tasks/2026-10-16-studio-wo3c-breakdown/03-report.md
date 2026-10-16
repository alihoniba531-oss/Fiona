# WO3c 拆解与分集实现报告

工作区：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`；分支：`short-film-studio`。

由三个子代理按互不重叠的文件范围并行实现，主代理负责集成、独立数据层测试、费用门禁与验收。未联网、未新增依赖、未提交；未改 package.json、lockfile、requirements.txt 或 globals.css 令牌。原有 `02-spec.md` 保持不变。

## 1. 修改文件（含新增）

### 后端

修改：

- `backend/database.py`：删号事务清理新表。
- `backend/routers/studio.py`：新接口、严格请求模型、项目时长设置。
- `backend/studio/store.py`：6 张新表、项目补列和迁移、在线程中解析 JSON、旧确认接口防误用。
- `backend/studio/sources.py`：同步后 outdated 联动、来源项目按建立时间倒序。
- `backend/studio/spend.py`：导演任务人民币单次报价上限与不足金额说明。
- `backend/studio/brain.py`：新任务 300 秒超时、大文本提示词在线程中组装，沿用零自动重试的提供方实现。
- `backend/studio/brain_jobs.py`：拆解任务绑定项目和批次、依赖调度过滤、预留修正费用的原子转移、取消后不再发修正请求。
- `backend/studio/brain_tasks.py`：四个新任务的 schema、硬约束和软提示。
- `backend/studio/recovery.py`：启动时恢复拆解依赖，仅更新数据库。

新增：

- `backend/studio/breakdown.py`：报价、确认、执行依赖、重跑、取消、状态与费用汇总、结果发布。
- `backend/studio/breakdown_material.py`：结构化导入、切批、场景定位、确定性总表合并。
- `backend/studio/breakdown_plan.py`：总表编辑、分集操作、revision/G0、梗概编辑、Markdown 导出。
- `backend/studio/prompts/novel_complete.md`。
- `backend/studio/prompts/text_map.md`。
- `backend/studio/prompts/synopsis.md`。
- `backend/studio/prompts/episode_plan.md`。

### 前端

修改：

- `frontend/lib/studio.ts`：项目时长、版本和当前拆解字段。
- `frontend/components/studio/StudioWorkbench.tsx`：F1 拆解阶段布局与折叠试读。
- `frontend/components/studio/SourceChoices.tsx`：F4 最近项目主按钮、建立日期。

新增：

- `frontend/lib/studio-breakdown.ts`：拆解、总表、分集接口和类型。
- `frontend/components/studio/BreakdownStage.tsx`：页面数据、操作、错误、轮询与终态结果刷新。
- `frontend/components/studio/BreakdownPanel.tsx`：设置、批次进度、重跑、释放、取消和累计费用。
- `frontend/components/studio/BreakdownDialog.tsx`：共享原生确认对话框。
- `frontend/components/studio/BreakdownQuoteDialog.tsx`：报价明细、倒计时、确认。
- `frontend/components/studio/SynopsisPanel.tsx`：结构化梗概展示及字段编辑。
- `frontend/components/studio/BibleTable.tsx`：总表页签、筛选、行内编辑、合并、新增与归档。
- `frontend/components/studio/EpisodePlan.tsx`：分集表、窄屏卡片、操作、G0、导出。

### 测试与文档

新增：

- `backend/tests/test_studio_breakdown_budget.py`。
- `backend/tests/test_studio_breakdown_material.py`。
- `backend/tests/test_studio_breakdown_pipeline.py`。
- `backend/tests/test_studio_breakdown_plan.py`。
- `backend/tests/test_studio_breakdown_plan_sources.py`。
- `backend/tests/test_studio_breakdown_plan_review.py`。
- `backend/tests/test_studio_breakdown_integration.py`。
- `backend/tests/test_studio_breakdown_frontend.py`。
- 本报告 `docs/tasks/2026-10-16-studio-wo3c-breakdown/03-report.md`。

修改 `backend/tests/test_studio_brain_frontend.py` 的一个旧工作室空项目断言，以对应 F1 新布局。没有修改任何非工作室测试。

## 2. 实现功能

- 小说来源直接从快照导入人物设定、初始场景、结构化梗概、伏笔、时间线和改编软约束；补全按正文重建场景。
- 小说批次同时满足最多 10 章、24,000 字；超长单章继续按段落分成子批，保留章内绝对偏移。次要来源超过 12,000 字的快照块再切为最多 10,000 字的子块。
- 四类任务复用导演提供方、schema 校验、最多一次付费输出修正、每家三路并发。原文仍只经 material_prompt 的 JSON 数据块传入。
- 报价先构建完整批次与依赖计划，确认一次且 15 分钟过期；确认事务为所有批次预留首轮及允许的一次修正费用。blocked 批次不发请求，成功后组装输入再调度。
- 支持单批先报价再重跑、换提供方、uncertain 先核账释放、整次取消、重启恢复、partial 状态；取消后只结算已经发出的调用，不再新发修正。
- 精确锚点定位、偏移首尾覆盖与未命中提示。仅接收对应原文中的逐字摘录；缺外形保持待作者补充。
- 总表按规范名、别名与小说人物 ID 合并；跨批完成顺序变化不会留下重复的自动条目。作者改动、主动清空、手动合并及归档在轮询中保留。
- 分集六类确定性操作、连续编号、时长和镜头数计算、未纳入区间、出场人物/集数重算、乐观并发 revision、完整版本快照与 G0 批准。正常多段拆解只在全完时生成一次首版；partial 与其后重跑成功分别留版。项目默认时长实际影响已有集的继承目标时，也会生成 revision 并退回待批准。
- 快照同步标记当前拆解 outdated，保留已有 G0；导演任务进行中禁止同步。旧拆解迟到完成不会抢回项目当前方案。
- 完整前端设置、报价、进度、结果编辑、错误/加载/成功状态、窄屏分集卡片和 Markdown 下载。

## 3. 与规格逐项对应

| 规格项 | 对应实现 | 验证位置 |
| --- | --- | --- |
| §4.1 小说结构化导入 | `breakdown_material.structured_import`；只读 manifest 与快照，不调用小说写接口或模型 | material、integration、pipeline |
| §4.1 novel_complete | `brain_tasks`、任务提示词、`breakdown`；正文场景覆盖初始细纲，保留外形来源和原文摘录 | material、pipeline、integration |
| §4.2 次要来源切块 / text_map / synopsis | `split_block`、`batch_plan`、四任务 schema、依赖输入组装 | material、pipeline、integration |
| §4.2 场景定位 | `locate_scenes`；精确查找、单调偏移、首尾覆盖、未命中 warning，支持章内子批 | material、integration |
| §4.3 分段分集 | 小说每 10 章、次要来源每 5 个原快照块；按前段结尾串联，按实际单元计算秒数和 round(秒/3.5) | material、pipeline、plan、integration |
| §4.3 硬 / 软约束 | 重叠、乱序、越界、空范围为硬错误；时长偏离与未纳入只提示；巨大越界整数不会构造巨大 range | pipeline |
| §4.4 总表合并 | NFKC、去空白、casefold、别名等价类；原有小说 ID 优先、最早出现、首个有效摘录 | material、plan_review、integration |
| §5.1 数据表 / 补列 | `store.STUDIO_TABLES_DDL`、`migrate_schema` 同步补列；删号事务包含全部新表 | plan、plan_sources、原 store 回归 |
| §5.2 revision / G0 | 同事务 expected_revision 检查、修改加版、完整 plan_json 快照、批准版本绑定；总表和梗概编辑不影响 revision | plan、plan_review、integration |
| §5.3 快照同步 | `sources` 中标记 outdated；不自动撤销 G0；已有导演任务门禁覆盖 blocked 预留任务 | plan_sources |
| §6 报价和上限 | 全批报价、人民币单次/日上限、Claude 月剩余、409 差额、零付费调用 | budget、pipeline |
| §6 确认与全部预留 | `/breakdown/start`；报价只能确认一次，过期拒绝，依赖批也预留，任务全部绑定既有项目 | pipeline、integration |
| §6 执行和重跑 | 只解除满足依赖的批；失败阻塞下游；换模型重跑先报价；uncertain 先释放 | pipeline |
| §6 取消 / 恢复 / partial | 未执行批取消释放；在途只结算；启动不请求提供方；partial 发布已成功段且禁止 G0 | pipeline、plan_review、plan |
| §7 总表接口 | 列表、kind 过滤、字段编辑、手动新增、同类合并、软归档、归属 404 | plan、integration |
| §7 分集接口 | edit / merge / split / move_boundary / delete / insert、重排重算、409、批准 | plan、integration |
| §7 Markdown 导出 | 作品/快照/模型/版本/G0、梗概、三张总表、分集、未纳入、小说伏笔/时间线；转义及下载响应头 | plan、integration |
| §8 F1 拆解页布局 | 来源 → 拆解 → 梗概 / 总表 / 分集；试读默认折叠；空项目提示 | frontend、更新的 brain_frontend 工作室断言 |
| §8 F2 拆解面板 | 单独保存时长、可选集数、模型说明、原生报价 dialog / 倒计时、批次状态 / warning / 费用、重跑 / 释放 / 取消、outdated / partial、5 秒轮询 | frontend |
| §8 F3 梗概 / 总表 | 梗概字段修改；三个 roving 页签、待补充筛选、行内编辑、合并确认、新增归档 | frontend、plan、integration |
| §8 F3 分集方案 | 九列表格、超时文字提醒、更多菜单、拆分点选择、未纳入建集、revision / G0 / 导出、409 刷新 | frontend、plan、integration |
| §8 F3 适配与状态 | 容器小于 640px 的分集卡片、表格独立滚动；空/加载/错误/成功状态；账户变更时失效请求隔离 | frontend |
| §8 F4 | 来源项目建立时间倒序、本地日期、只有最新项目为主按钮 | frontend、plan_sources |
| §9 离线测试 / 缺依赖 | fake provider、原创夹具；新增 node 驱动测试调用前检测依赖并 skip | 各新测试文件、隐藏依赖全量 |

## 4. 测试结果

统一验收使用仓库原有虚拟环境，将其 bin 加入 PATH 后执行 `python -m pytest -q`；没有安装任何依赖。系统 PATH 原本没有 `python`，系统 `python3` 未安装 pytest。

两次全量均不带 deselect，不修改非工作室测试：

| 环境 / 命令 | 结果 |
| --- | --- |
| 保留 `frontend/node_modules`：`cd backend && python -m pytest -q` | **6825 passed、6 skipped、1 failed、5 errors**，208.18 秒；6 个异常全部是沙箱禁止本地端口绑定 |
| 临时改名 `node_modules.__hidden` 后执行同一命令 | **6706 passed、125 skipped、1 failed、5 errors**，182.68 秒；仍仅相同 6 个沙箱端口绑定异常。额外 119 个测试正确 skip；`node_modules` 已由 finally 恢复，隐藏目录不存在 |

最终树的 8 个新增测试文件合计 **134 passed**（10.43 秒）；覆盖两条来源端到端、费用上限、纯数据层、全部分集操作、独立并发/保留编辑回归与前端 SSR/交互。全部夹具使用自写素材与 fake provider。

隐藏依赖期间单独运行 `python -m pytest -q tests/test_studio_breakdown_frontend.py -rs`：**4 passed、15 skipped**。15 个 Node 驱动测试全部因缺少 typescript / react / react/jsx-runtime / react-dom/server 在启动 Node 前 skip；4 个守卫自身测试通过。

前端统一验收：

- `npm run lint`：通过，0 error / 25 warnings，与基线持平。
- `npx tsc --noEmit`：通过。
- `npm run build`：沙箱 Turbopack 失败，原因是处理 globals.css 的子进程需要绑定端口，被沙箱以 `Operation not permitted (os error 1)` 拒绝。
- `npm run build -- --webpack`：最终树再次构建通过，17 个页面生成完成。
- `git diff --check`：通过。

## 5. 设计取舍、未完成与人工确认

本期实现范围已完成。统一验收未全绿的环境原因、数据结构带来的取舍，以及仍需人工确认的事项如下。

1. **确认接口**采用 `POST /studio/projects/{pid}/breakdown/start {quote_id}`；单批重跑采用 `/retry/quote` 后 `/retry {quote_id}`。重跑提供方锁在报价中，确认不接受另换提供方。
2. **分段大小**按 10 章 / 5 个原快照块；原块的子块仍归同段。超长单章在本期切子批，沿用原章号、章内偏移及连续场号，不改快照。
3. **大约集数**填写后，小说分集等待全书补全以得到稳定的总时长，再按各段时长折算建议集数；未填写时保留逐段依赖推进。
4. **梗概可编辑**补充 `PATCH /studio/projects/{pid}/breakdown/synopsis`（兼容 PATCH `/breakdown`），落实 §1 产品目标；§7 原路由清单未单列此接口。复杂字段保留 JSON 结构并做字段级校验；不增加分集 revision。
5. **费用**批次行显示全部尝试的累计已结算金额，支持跨提供方币种；总费用包含首次、修正和手动重跑。无法确认的费用仍保留预留，不假报已结算。
6. **道具出场的集**依据首次单元与单元摘要中的规范名/别名计算；规格的 unit 未提供独立 props 列表，因此无法仅靠现有结构枚举摘要未提及的所有道具出场。作者可以编辑说明和合并条目。
7. **人工确认**：真实提供方、真实扣费和真实长篇效果没有执行，符合本次离线约束。原生 dialog 的实际浏览器观感及窄屏视觉可人工复核；已覆盖 SSR、交互和布局结构测试。
8. **沙箱外复跑**：两种环境全量中的下列相同 6 个用例受本地端口绑定限制（`PermissionError: [Errno 1] Operation not permitted`）；保留原测试、不 deselect、不修改非工作室测试，需主控在沙箱外复跑。除此以外，两轮全量没有功能失败。

| 类型 | 用例 |
| --- | --- |
| failed | `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot` |
| error | `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive` |
| error | `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline` |
| error | `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work` |
| error | `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline` |
| error | `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch` |

## 6. 二次修改（R1）

依据 `04-review.md` §4 第 1–9 条，以及作者追加的 O1/O2/O3/O4/O5/O6/O7/O9/O11 完成返修。维持离线、无新增依赖、无提交、非工作室测试零改动；未改 package.json、lockfile、requirements.txt 或 globals.css 令牌。截图按本轮指令由主控负责，本轮未拍摄或修改截图。

### 6.1 本轮改动文件

后端：

- `backend/studio/breakdown.py`：重新拆解的旧预留清理、无差异 GET 零写入、报价及批次去正文、执行时快照读取、warning 归属、准确重跑字段、逐项恢复隔离。
- `backend/studio/breakdown_material.py`：缺失锚点向后回退、切批元数据索引/偏移、总表 warning 来源映射。
- `backend/studio/brain_jobs.py`：拆解执行前按需组装素材、局部大 JSON 读取、调度只取任务 ID。
- `backend/studio/breakdown_plan.py`：可读 Markdown、中文定位与集区间、清空外形待补充、未完成方案禁改、已发布方案与活动拆解分离。
- `backend/studio/store.py`：恢复 WO3b 的 `_one/_many` 同步读取；仅拆解任务的 `_get_job` 委托拆解模块在线程中解析大 JSON。
- `backend/studio/sources.py`：新增按归属和快照号读取的 `read_snapshot_at`，保留原校验与线程 I/O。
- `backend/studio/recovery.py`：启动恢复读取导演任务的小字段；单个损坏拆解任务不阻断其它恢复或启动，不记录素材。
- `backend/studio/spend.py`：三类导演额度 409 金额文案统一四位小数。
- `backend/routers/studio.py`：报价请求增加可选目标时长草稿字段，继续 `extra='forbid'` 与严格整数范围校验。

前端：

- `frontend/lib/studio-breakdown.ts`。
- `frontend/components/studio/EpisodePlan.tsx`。
- `frontend/components/studio/SynopsisPanel.tsx`。
- `frontend/components/studio/BibleTable.tsx`。
- `frontend/components/studio/BreakdownPanel.tsx`。
- `frontend/components/studio/BreakdownQuoteDialog.tsx`。
- `frontend/components/studio/BreakdownStage.tsx`。

测试与报告：

- 修改 `backend/tests/test_studio_breakdown_pipeline.py`、`test_studio_breakdown_material.py`、`test_studio_breakdown_plan.py`、`test_studio_breakdown_frontend.py`。
- 新增 `backend/tests/test_studio_breakdown_r1_pipeline.py`、`test_studio_breakdown_r1_plan.py`、`test_studio_breakdown_r1_integration.py`。
- 在本文件追加本节。`04-review.md` 保持不变。

### 6.2 review §4 第 1–9 条对应

| 编号 | 实现与验证 |
| --- | --- |
| 1 / M1 更多菜单 | 桌面表格和窄屏卡片共用原生操作 dialog，标题“第 n 集 · 操作”，只有“关闭”按钮；六项操作先关菜单再执行或打开二级 dialog。按下一集存在、场数和是否相邻禁用相关操作，操作列 w-20。关闭恢复焦点时使用 preventScroll。SSR/交互覆盖 dialog、按钮、关闭与禁用。 |
| 2 / M2 重跑提示 | 去掉 pending_segments；接口返回 retry_needed（真正需重跑的批及状态）与 blocked_segments（等待自动继续的分集批）。界面区分被拒/失败与 blocked，uncertain 明示需先核账释放。前后端均补断言。 |
| 3 / M3 梗概与导出 | 主线显示“名称 —— 描述”，分段显示“第 a–b 章：摘要”，主题顿号连接。编辑改为每行一项，解析时保留按序对应的原键与未知字段。导出中文标签、模型中文名、伏笔/时间线逐项文本；不再序列化 JSON，Markdown 转义字符集与 exchange_exports 对齐，不转义日期短横线。测试检查可读文本及不存在 JSON 转义残片。 |
| 4 / M4 定位与集范围 | roleLabel / _role_label 中英文映射一致；formatEpisodeRanges / _episode_ranges 排序去重压缩连续集号，空列表为“未纳入”。总表和 Markdown 使用一致格式，有参数化和 SSR 测试。 |
| 5 / M5 进度条 | 删除原生 progress，改用带 progressbar ARIA 的双层 div，轨道 slip、填充 ink2、百分比宽度；不修改全局令牌。SSR 检查 role、范围和当前值。 |
| 6 / M6 时长布局 | 最短/最长/大约集数三个输入采用 w-28、同一 flex-wrap 行，行尾显示分钟折算；下一行保留有效范围说明。 |
| 7 / M7 重新拆解预留 | start 写事务在确认报价前检查旧 group 的所有尝试，任何 uncertain 都 409，报价仍 open、指针和预留不变。允许重新开始时，旧 queued/blocked job 与 chunk 取消并释放，旧拆解标 cancelled，旧结果表保留。对已付调用按实际费用保留账目；未知实际费用的失败调用不冒险清零。报价 dialog 提示旧未执行批将取消释放。测试覆盖实际费用+新报价占用、旧排队预留归零、非最新 uncertain 尝试也阻断。 |
| 8 / 顺手项 O8/O10 | 三条导演预算 409 显示四位小数；清空 appearance 时改为 none，人物 needs_author=1，并保留作者编辑标记防止后续补跑静默填回。新增回归。 |
| 9 / 报告与截图 | 本节列出文件、编号对应、两种依赖环境的专项测试、一次后端全量和前端验收结果。依作者最新指令，截图交主控拍摄，不生成 -v2 截图。 |

### 6.3 作者追加优化项对应

| 编号 | 实现与验证 |
| --- | --- |
| O1 无差异 GET 零写 | get_current 先比较 job/chunk 状态与依赖，仅脏状态触发 refresh；只有素材批新成功等真实物化变化才改写 units/bible。done/cancelled 无差异直接读表。连续 GET 测试跟踪 SQL DML，并比较 updated_at，确认零写。 |
| O2 线程边界收回 | 全局 store._one/_many 恢复原写法。拆解模块使用局部 raw-row 查询后在线程中解码大 JSON；公共 job 状态转换/释放只为四个新任务委托该局部解码。启动恢复不再为了状态读取大 params。普通查询不调 to_thread、快照读取在工作线程均有测试。 |
| O3 报价/批次不存正文 | 报价仅持计划、章块索引、范围偏移和计费估算；不再写 manifest/imported/inputs。start 锁定 snapshot_no 重读并校验当前版本，批次 source 不含 _inputs。job 初始 inputs 为空，实际执行前只读该批绑定快照，单次调用素材仅保存在对应 job。测试比较不同正文长度的报价 JSON 大小，查正文哨兵/禁用键，并验证执行时读取绑定版本。 |
| O4 缺失锚点回退 | 缺失场的起点使用下一个精确命中的位置，没有则块末；命中场不再把正文让给未命中场。首场未命中和全部未命中也按新规则，可为空，不强行占块头；精确命中的首场仍可覆盖块头。更新原测试并补首/中/尾及全缺失。 |
| O5 warning 来源 | 定位和摘录校验 warning 记录在对应来源 chunk；拆解级别的合并冲突另列 warnings，不再全压在第 1 批。第二批锚点/摘录失败只在第二批出现的回归通过。 |
| O6 未完成时只读 | running/partial 显示补跑将重生成方案的提示，禁用更多、建集和批准；后端所有六种 ops 返回 409，避免作者修改被补跑结果静默替换。 |
| O7 保留旧发布方案 | 项目活动 breakdown 与 revision 指向的已发布方案分开。新方案发布前继续返回旧 episodes、旧目标秒数与 G0，附 rebreakdown_pending 和活动拆解状态；UI提示新完成后替换，等待期间只读。发布后 revision+1 撤销旧批准；首次空方案 G0=false。取消替换任务后恢复旧方案操作，显式另存时长仍遵守加版规则。真实跨模块回归覆盖旧批准→草稿报价→开始→发布全过程。 |
| O9 恢复不阻启动 | 清单只取 id/owner，逐个拆解 try/except；损坏 import_json 或运行中 job 的 params_json 都不能阻断其它任务恢复，日志只记 ID/异常类型，原文不进入日志。新增 main recover_studio_jobs 入口测试。 |
| O11 保存时长明示 | 报价接收草稿目标时长，不再提前 PATCH 项目；报价 dialog 明示“每集目标时长将保存为 x–y 秒”，确认 start 才保存。旧批准方案仍保留到新发布，dialog 提示新发布后需重新批准。单独“保存时长”会影响已批准方案时先明确警告并确认。 |

### 6.4 本轮验收

| 命令 / 环境 | 结果 |
| --- | --- |
| 完整依赖：python -m pytest -q tests/test_studio_breakdown_*.py tests/test_studio_brain_frontend.py | 209 passed，16.13 秒，32 个既有 slowapi 弃用警告（含后补的报价体积/快照改变回归） |
| 完整依赖：python -m pytest -q tests/test_studio*frontend*.py | 112 passed，17.79 秒 |
| 临时隐藏 node_modules：拆解专项 | 173 passed / 36 skipped，10.27 秒；Node 驱动测试在启动前正确 skip |
| 临时隐藏 node_modules：工作室前端专项 | 20 passed / 92 skipped，0.37 秒；守卫自身测试通过，缺依赖的 Node 测试正确 skip。finally 已恢复 node_modules，node_modules.__hidden 不存在 |
| 后端一次全量：python -m pytest -q（不带 deselect） | 6884 passed / 6 skipped / 1 failed / 5 errors，208.66 秒；6 个异常全部为下表所列的沙箱本地端口绑定限制 |
| npm run lint | 0 errors / 25 warnings，与基线持平 |
| npx tsc --noEmit | 通过 |
| npm run build | Turbopack 因沙箱禁止绑定端口而失败（Operation not permitted） |
| npm run build -- --webpack | 通过，17 个页面生成完成 |
| git diff --check | 通过 |

后端全量的环境受限用例（与首轮相同，均为 `PermissionError: [Errno 1] Operation not permitted`，未修改或 deselect）：

| 类型 | 用例 |
| --- | --- |
| failed | `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot` |
| error | `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive` |
| error | `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline` |
| error | `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work` |
| error | `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline` |
| error | `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch` |

### 6.5 取舍与剩余人工确认

- 重新开始只释放尚未执行的预留。failed 若实际 usage 缺失，仍须按原“可能已付费则保留”规则保留账本占用；不能把这类调用伪装成未收费。uncertain 任意尝试始终要求核账释放后才可开始新拆解。
- O4 遵循作者本轮明确的新回退规则：缺失定位的场可以为空；当首场也未命中时，不强制覆盖块头，防止它吞掉已命中场的原文。
- 报价草稿只读，确认才保存时长；新发布之前旧方案/G0/目标秒数都按已发布 revision 保持，避免报价本身撤销批准。
- 真实提供方与扣费保持离线，未执行真实付费调用。界面截图（原 screens/06、07、10 对应场景）由主控拍摄；本轮仅做 SSR、交互、类型和构建验证。
- 本轮后端全量的 6 项环境异常已逐项列出，需主控沙箱外复跑；没有其它功能失败。Turbopack 同样受沙箱端口限制，webpack 构建已通过。没有已知的本单实现缺项；视觉截图仍由主控确认。

## 7. R2 小修

第 2 轮复核把三处记为可优化（(a) 分集表操作列、(b)「大约几集」标签、N3 旧拆解状态被标 cancelled），本轮逐条修完，未做其它改动，未新增依赖，未改 `package.json` / lockfile / `globals.css`。

### 7.1 改动文件

| 文件 | 改动 |
| --- | --- |
| `frontend/components/studio/EpisodePlan.tsx` | 桌面分集表最小宽 `min-w-[1180px]` → `min-w-[1040px]`；「操作」列表头与每行的操作格加 `sticky right-0 z-10 w-20 border-l border-[color:var(--carve)] bg-[color:var(--paper)]`，表格横向滚动时「更多」贴右常驻；「这集发生的变化」「终点 / 钩子」两列宽 `w-[200px]`，让出的宽度保证缩小后不挤。移动端卡片、对话框、其它列未动。 |
| `frontend/components/studio/BreakdownPanel.tsx` | 「大约几集（可不填）」标签改为「大约几集」，集数输入框加 `placeholder="可不填"`；最短秒数、最长秒数、大约几集三个标签的 `<span>` 都加 `whitespace-nowrap`，同一 flex 行内不再折行，三个输入框上沿对齐。 |
| `backend/studio/breakdown.py` | `_cancel_unexecuted` 只在旧拆解不是 `done` 时才写 `cancelled`（done 保持 done）；`start()` 给所有被新拆解替代的旧拆解写 `superseded_by` = 新拆解 id；新增 `_retired()`（`status='cancelled'` 或 `superseded_by` 非空），用于 `prepare_job`、`_status`、`_dirty`、`refresh` 的 blocked 调度与方案发布、`retry_quote`、`retry`，确保被替代的旧拆解不再执行批次、重新物化、调度、发布方案或重跑。`_published` 的原有行为（重拆期间继续显示旧方案）未改。 |
| `backend/studio/store.py` | `studio_breakdowns` 建表 DDL 加 `superseded_by TEXT`，`migrate_schema` 补列字典加 `studio_breakdowns: {"superseded_by": "TEXT"}`；同时给补列循环加「表不存在就跳过」的保护，旧库只建了部分 `studio_*` 表时补列不再报错（新表由 `STUDIO_TABLES_DDL` 负责建）。 |

### 7.2 测试增减

- 新增 `backend/tests/test_studio_breakdown_r2.py::test_restart_keeps_completed_old_breakdown_done_and_published`（对应 (a)）：旧拆解 `done` → 重新报价并开始；断言旧拆解状态仍为 `done` 且 `superseded_by` 等于新拆解 id；对旧拆解显式 `refresh` 与对项目的 `get_current` / `get_episodes` 之后，旧拆解的 units 与总表逐行不变、状态不变；旧拆解的 `retry_quote` 被 409（「拆解已取消」）拦住；新方案发布前 `get_episodes` 仍返回旧方案（`breakdown_id` 为旧拆解、`rebreakdown_pending=True`、`plan_revision` 不变、集标题一致）。
- `backend/tests/test_studio_breakdown_r1_pipeline.py::test_restart_cancels_old_unexecuted_reservations_keeps_settled_cost_and_results`（对应 (b)，现有测试）：保留原有断言，补一条 `superseded_by == 新拆解 id`。
- `backend/tests/test_studio_breakdown_frontend.py`：`test_panel_ssr_unquoted_partial_outdated_and_running` 的标签断言改为「大约几集」，并新增 `placeholder="可不填"`、不出现「大约几集（可不填）」；`test_episode_ssr_timing_menus_approval_and_narrow_cards` 保留原有断言，新增表格含 `min-w-[1040px]` 且不含 `min-w-[1180px]`、「操作」表头 class 含 `sticky`/`right-0`/`z-10`/`bg-[color:var(--paper)]`/`border-l`/`border-[color:var(--carve)]`、每行操作格 class 含 `sticky`/`right-0`/`z-10`/`bg-[color:var(--paper)]`。仍全部走 `probe()`，缺 node_modules 时 skip，未引入新依赖。

### 7.3 验收

| 命令 | 结果 |
| --- | --- |
| `cd backend && /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_studio_breakdown_*.py tests/test_studio_brain_frontend.py` | 210 passed，0 failed，0 skipped，17.28 秒（32 条既有 slowapi 弃用警告） |
| `cd frontend && npm run lint && npx tsc --noEmit` | lint 0 errors / 25 warnings（与基线持平，警告都在未改动文件），tsc 无输出，两条退出码均为 0 |
| 追加回归 `pytest -q tests/test_studio_*.py` | 1332 passed，0 failed |
| 追加回归 `pytest -q`（后端全量，沙箱内） | 6887 passed / 6 skipped / 1 failed / 5 errors，215 秒；这 1 failed + 5 errors 与 §6.4 列出的沙箱端口绑定限制逐条相同，与本次改动无关 |

### 7.4 说明

- 状态列取值不变（`draft/running/partial/done/cancelled`，CHECK 未扩），「被替代」用新的 `superseded_by` 表达：`done` 的旧拆解保持 `done`，之前是 `running`/`partial` 的旧拆解仍是 `cancelled`，被替代这件事两者都记在 `superseded_by` 上，后续工单可直接读该列。
- 「已被替代」的判定统一收在 `_retired()`，`_status` 对这类拆解返回冻结状态，因此 `_dirty` 判定为干净，`refresh` 不会改写旧拆解的 units/总表，也不会重新发布方案。
