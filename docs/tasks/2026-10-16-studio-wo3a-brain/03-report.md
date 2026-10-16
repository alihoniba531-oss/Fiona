# WO3a 实现报告

1. **修改文件**：后端导演模块、预算/记账/API/恢复、评测脚本；前端 BrainTrial、顶栏与 WO2 打磨；新增 146 项离线测试。完整清单见下文。
2. **实现功能**：三家导演、剧本试读、分币种报价确认、预算预留与实际结算、一次独立计费修正、排队恢复，以及 WO2 九项修复。
3. **规格对应**：第 3–6 节逐条映射见下文。all 采用任一家不可用整体 409；数据库仅新增，视频与导演任务隔离。依赖、令牌、已有测试均未改，未发真实外部请求、未 commit。
4. **验证结果**：工作室 821 passed / 1 failed；全量 6061 passed / 2 failed / 5 errors / 6 skipped，无 deselect。lint、tsc、webpack 构建通过；默认 Turbopack 构建因沙箱端口限制失败。
5. **待确认**：一项旧 caps 精确断言与新增字段要求冲突；其余 1 failed、5 errors 及已有 6 skipped 来自沙箱端口限制。需要环境外复跑，以及真实 Key 核实 qwen-vl-max 和各家价格。

## 1. 修改文件

- 后端新增：`studio/brain.py`、`brain_jobs.py`、`brain_tasks.py`、`brain_schema.py`、`prompts/{read_through,style_proposals,bible_extract,frame_qc}.md`；`scripts/studio_brain_eval.py`。
- 后端修改：`studio/{config,pricing,spend,store,recovery,scheduler,notices}.py`、`routers/studio.py`、`database.py`、`.env.example`。
- 前端新增：`components/studio/BrainTrial.tsx`、`lib/useRovingTabs.ts`。修改 `app/page.tsx`、`components/Sidebar.tsx`、`components/studio/{QuoteDialog,ShotCard,StudioBudget,StudioShell,StudioWorkbench}.tsx`、`lib/studio.ts`。
- 新增测试：`backend/tests/test_studio_brain_{core,orchestration,budget_api,eval,frontend}.py`、`test_studio_wo3_notices.py`、`test_studio_wo3_polish_frontend.py`。
- 文档：`README.md`、`CLAUDE.md`、`docs/ARCHITECTURE.md`、本报告。任务规格 `02-spec.md` 是工作开始时已有的未跟踪文件，没有修改。

未新增依赖，未修改 package.json、lockfile、globals.css 或已有测试；未发起真实模型/外部网络请求，未 git commit。

## 2. 实现功能

导演模型支持 Claude BYOK、千问、DeepSeek；使用配置中的 Claude 模型，不自动降级。剧本试读包含通读、风格提案、人物/场景/道具表；顶栏切换模型并显示 Claude 月额度。页面打开后 BYOK 状态变化导致报价/提交失败，也会提供手动改用按钮，仅 PATCH、不重跑。先显示分币种最高报价，原生 dialog 确认后提交，结果按提供方分栏，展示模型、费用、耗时、警告与人物待补充标签。后台每家最多 3 个调用，其余排队；前端只在 queued/running 时按 3 秒轮询。

每次请求单独预留和结算；报价包含最多一次输出修正上限，修正实际发生时另建 job、另行检查和预留。人民币共用上海自然日日上限，Claude 按作者上海自然月计入默认 $40 上限，DEV_MODE 不豁免。uncertain 保留预留，只能核实未扣费后二次确认释放。看图的非 Claude 调用使用 qwen-vl-max，并注明视觉来源。

WO2 九项打磨已实现；提醒改用持久待写边界恢复，避免消息与提醒登记之间重启产生重复聊天消息。历史终态任务首次启动时持久占位，后续 recheck/link 改时间或状态也不会补发。

## 3. 与规格第 3–6 节对应

| 规格 | 实现与验证 |
| --- | --- |
| 3.1 统一接口、三家适配、看图 | `brain.py` 提供异步 run_brain、单次 SDK 提供方类、BrainResult；120 秒超时、max_retries=0、Claude effort/cache/fallback、2000px/3.5MB 图片处理；core 离线模拟 SDK 和真实 SDK MockTransport 验证。 |
| 3.1 schema、任务、提示词 | 只遍历 schema 位置转换，保留业务字段名和支持的 format，移除约束进 description，拒绝递归；完整 schema 本地校验。四任务共用 Markdown 提示，人物摘录要求原文子串，软约束只警告。 |
| 3.2 预算、独立账本、并发与恢复 | `pricing/spend/brain_jobs/store/recovery`：输入含完整提示按字符×1.5，输出按 max_tokens；缓存读按缓存价；未知 Claude 价格拒绝。事务原子预检/建组，每调用独立行、共享 group_id；三并发、queued 恢复、running→uncertain 均有测试。 |
| 3.3 接口与隔离 | providers、项目 PATCH、trial、group、access 月额度全部经过 gate/owner。增加无模型调用的 POST `/studio/projects/{pid}/brain/quote`。`providers=all` 采用严格策略：任一家不可用或累计额度不足，整体 409，不建 job、不发模型请求。 |
| 3.4 手动评测 | 直接调用提供方类，不经过数据库。先报价，缺少足额 `--yes-spend` 退出 2；Claude 从环境变量和模型参数构造。可选看图，报告写 `_eval/`，并排输出、逐次 usage/费用/耗时/警告/修正状态。 |
| 4 前端 | BrainTrial、导演 chips、月额度、分币种确认、可读结果、仅 PATCH 的切换按钮、uncertain 二次释放、3 秒可见轮询与账号取消均有 SSR/行为探针。旧后端项目无 brain_provider 时保留 WO2 空态以兼容滚动部署。 |
| 5.1、5.8、5.9 | 持久 cutoff 与历史终态占位；持久 pending 消息边界；直接写入/重试统一过滤归档与历史任务，表达式部分索引收窄扫描。新增历史 recheck/link、删号、两侧提交重启窗口及 EXPLAIN 测试。 |
| 5.2–5.7 | live 仅播报过期；可复用 roving tabindex hook；释放错误只显示一次；工作室 tag 局部换行；轮询只取任务/额度；主页 access 共享给 Sidebar，200 后才启动 notices。七个新增前端测试逐项覆盖这六项。 |
| 6.1–6.6 | 三家单 POST 的超时/断连/中断/500/429/400/坏响应，独立修正且无第三次、schema、不可用不降级/视觉路由、日/月预算/缓存/月界、trial 原子预检/owner/group 均由新增 core/orchestration/budget_api 测试覆盖。 |
| 6.7–6.9 | 新增 21 个前端探针和 7 个提醒测试；执行全部工作室专项、全量 pytest、lint、tsc、默认 build，另补 webpack build。全量结果与限制见下一项，没有 deselect。 |

数据库只做新增。旧 `studio_jobs.provider/status` 的 CHECK 无法通过 ADD COLUMN 扩充，因此 brain 行使用新增 `brain_provider` 作为权威提供方，旧 provider 列保留 `wan` 兼容占位；读取层统一返回真实 provider。invalid_output 在旧 status 列保存为 failed 加 invalid_output 错误码，读取时还原。视频调度与提醒查询均明确 `kind='i2v'`，不会消费 brain 行。老库补列、新库 DDL、迁移幂等均有测试。

日志保护同时覆盖 SDK 与 SQLite DEBUG：素材、产物等 JSON 绑定使用私密字符串 repr；新增探针确认不泄露原文或模型输出。

## 4. 测试和构建结果

- 后端均在 `backend/` 使用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。
- 新增核心、编排、预算接口、评测联合：118 passed；前端旧/新增专项：48 passed；WO2 后端、提醒与评测：32 passed。
- 全部工作室专项：821 passed、1 failed。唯一失败为已有 `test_studio_api.py::test_calltime_gate_and_bearer_cookie_dev`（第 103 行）：旧断言要求 caps 精确等于三个旧字段，与本规格 3.3 强制增加两个月额度字段冲突。保留新接口契约，未修改或排除旧测试；此项不是沙箱失败。
- 全量 `python -m pytest -q -ra`：6061 passed、2 failed、5 errors、6 skipped，29 条既有 slowapi 弃用警告，172.60 秒。没有 deselect。除上述 caps 契约失败外，其余 1 failed/5 errors 均在绑定本机端口时明确得到 `PermissionError: [Errno 1] Operation not permitted`：
  - failed：`test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`。
  - errors：`test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`；`test_safe_http_deadline.py` 的 `test_drip_response_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_four_stuck_resolutions_do_not_block_another_fetch`。
  - 6 skipped 为已有 `test_byok_client.py:652`（2 项）及 `:882`（4 项）自行检测到沙箱不能绑定回环端口后的跳过，没有新增跳过逻辑。
- `npm run lint`：通过，0 errors，25 条既有 warnings；`npx tsc --noEmit`：通过。
- `npm run build`：失败。Turbopack 处理 globals.css 的 PostCSS 子进程需要绑定端口，沙箱返回 `Operation not permitted (os error 1)`。`npm run build -- --webpack`：通过，包含 `/studio`、`/studio/[id]` 的生产构建成功。
- `git diff --check`：通过。已有测试、依赖清单、lockfile 和 globals.css 无改动。

## 5. 未完成或需要人工确认

- 无真实 Key 验收：需主控使用 Fiona 的配置核实 qwen-vl-max 是否可调用，以及三家真实模型行为和账单价格；平台默认价仍标为「待核实」。本轮没有花费真实模型额度。
- 「全量 0 failed」无法同时满足当前旧 caps 精确等式和规格新增字段要求；现已明确保留失败、没有 deselect、没有改旧测试。需要主控处理这条测试契约冲突。
- 默认 Turbopack build、上述 6 项回环端口失败/错误及已有 6 项环境跳过，需在允许绑定端口的环境复跑；webpack 构建已通过。
- 评测脚本的 `--yes-spend` 采用人民币总授权，美元通过 `--usd-to-cny`（默认 7.2）仅作授权折算；报告仍分 USD/CNY 展示。这不是实时汇率。

## R1

本节为返修后的结果；上方首次交付记录中的 caps 断言冲突已由 R1-H 解决。未联网、未新增依赖、未改全局令牌、未提交 Git；非工作室测试没有修改。

### 逐条对应

| 返修项 | 实现 | 离线验证 |
| --- | --- | --- |
| R1-A 截断不修正 | `_execute_brain` 在 schema 校验与修正前处理 max_tokens/length；只按实际 usage 结算一次，记录 invalid_output、max_tokens 和指定中文提示。保留旧库 failed 物理状态，以读取映射返回 invalid_output；错误码不会被覆盖。空输出但截断时也优先按截断处理。 | `test_studio_brain_r1_execution.py` 三提供方单次调用、实际费用、释放预留、状态/错误码/文案；provider 测试补 6 个空内容截断优先级用例；评测脚本同样单次终止。 |
| R1-B Claude 超时 | SDK 与底层 HTTP 客户端都使用 `min(600,max(300,ceil(3600*max_tokens/128000)+60))` 秒，max_retries=0；千问/DeepSeek 仍为120秒。queued/running 显示「长任务可能需要数分钟」，保留原状态与视觉。 | provider 测试遍历四任务、公式边界、无重试；新增前端 SSR/状态转换两个探针，终态隐藏说明。 |
| R1-C 完整失败结算 | BrainProviderError 携带 usage、实际 model、stop_reason、latency_s；Claude refusal/带usage空内容、千问/DeepSeek content_filter 记 failed，按实际用量结算并释放多余预留，不修正、不变 uncertain。拒答类别映射固定中文，空内容使用指定文案；损坏包裹/传输异常保留原 uncertain 语义。 | provider 及 execution 测试覆盖三家适配器和完整后台编排，断言单调用、failed、实际费用、预留为零与中文原因；评测同步验证。 |
| R1-D 结算精度 | 缓存创建按基础输入价1.25倍，读取仍按缓存价；按回复实际 model 计费并保存在调用行，修正请求仍使用已确认的原请求模型。未知 fallback 单价按本次预留结算，加入「fallback 模型单价未配置，按预留计」。Claude 预留同时覆盖缓存创建溢价；启用 default fallback 的 Sonnet/Opus 预留覆盖价目表中已知 Claude 的最高价，避免实际费用突破原预留。 | 精确金额用例、Sonnet→Opus、未知 fallback、未知 fallback 后单独修正、最坏缓存创建/较贵 fallback 不超过预留；评测未知快照断言更新为本次预留。 |
| R1-E 修正报价上限 | 输入上限为 `ceil(原始完整输入字符数×1.5)+图片输入估算+上次max_tokens+2048`，输出上限仍是 max_tokens；不再使用 max_tokens×8。固定错误信息最多8条、每条96字，先前输出放独立数据块，不再次JSON转义。业务报价、修正实际预留和手动评测共用 helper。 | execution 精确报价断言与修正预留 helper 对齐；provider 验证修正包装在2048 token估算之内且原输出不二次转义；eval 断言同一数值。 |
| R1-F schema 显式错误 | 新增 `UnsupportedSchema(ValueError)`，携带 JSON Pointer 的 path/position；schema-valued additionalProperties、非字符串 format、递归引用显式报错。保留完整本地校验能力，现有四任务均可转换。 | `test_studio_brain_r1_schema.py` 16项覆盖位置、嵌套、递归、业务字段名、local validator及四任务。 |
| R1-G 可用性零解密 | 新增 BYOK 公开状态只读 helper；仅取公开字段、密文长度/版本及 key_id 轮换信息，不加载完整密文、不调用解密。provider_options/GET providers/报价使用该状态；真正调用才读取内部配置并验证解密。原 get_public_config/_public 的验证语义保持。 | monkeypatch internal读取、decrypt_key、AES 解密方法为禁止调用，验证 providers 与报价不触发；覆盖启停、provider/status、密文外观、密钥轮换和原公开接口行为。 |
| R1-H 工作室旧测试 | 更新 `tests/test_studio_api.py:103` 的 caps 精确断言，加入 brain_monthly_usd 与 brain_month_used_usd。因R1行为变化同步更新本期工作室测试里的缓存费用、Claude超时、修正数据形态和eval快照金额断言。 | 原 caps 用例及全部工作室测试通过；没有修改非工作室测试或新增 deselect/skip。 |

### 报价数值示例

完整输入估算100字、max_tokens=4096时，原始输入150 token，修正输入6294 token。默认 Sonnet（覆盖服务端已知较贵fallback及缓存创建）的首次最高预留 `$0.08267`、修正 `$0.11339`、合计 `$0.19606`；千问分别为 `¥0.099204`、`¥0.136068`、合计 `¥0.235272`。这些数值都有精确断言；最终结算仍按实际模型及 usage，未知 fallback 例外按本次预留计。

### R1 修改文件

- 业务：`backend/studio/{brain,brain_jobs,brain_schema,pricing,store}.py`、`backend/byok/store.py`、`backend/scripts/studio_brain_eval.py`、`frontend/components/studio/BrainTrial.tsx`。
- 文档/配置：`backend/.env.example`、`docs/ARCHITECTURE.md`、本报告。
- 新增5份R1测试：`backend/tests/test_studio_brain_r1_{execution,provider,schema,eval,frontend}.py`，合计92项。
- 更新工作室测试：`test_studio_api.py`、`test_studio_brain_core.py`、`test_studio_brain_budget_api.py`、`test_studio_brain_eval.py`。

### R1 测试与构建

后端均在 backend/ 使用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，模型请求均为离线桩或模拟传输。

- 工作室：`python -m pytest -q tests/test_studio_*.py` → **914 passed、0 failed**，29条既有slowapi弃用警告，23.36秒，无 deselect。
- 全量 `python -m pytest -q -ra`：**6154 passed、1 failed、5 errors、6 skipped**，29条既有slowapi弃用警告，172.14秒，无 deselect。R1新增92项离线测试全部通过，原caps契约失败已消除。
  - failed：`test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`。
  - errors：`test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`；`test_safe_http_deadline.py` 的 `test_drip_response_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_four_stuck_resolutions_do_not_block_another_fetch`。
  - 上述1 failed/5 errors均在绑定本机回环端口时明确报 `PermissionError: [Errno 1] Operation not permitted`，需要沙箱外复跑；不是工作室逻辑失败。
  - 6 skipped仍是既有 `test_byok_client.py:652`（2项）、`:882`（4项）检测到回环绑定被沙箱拒绝后自行跳过，没有新增跳过逻辑。
- 附加验证：R1 provider + core + 既有BYOK store测试 **163 passed**，未修改BYOK测试。
- 前端旧/新增专项：**50 passed**；lint **0 errors / 25条既有warnings**；tsc通过。
- `npm run build`：Turbopack处理globals.css时，PostCSS子进程绑定端口被沙箱拒绝，`Operation not permitted (os error 1)`。日志：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/next-panic-9127a941622f1866870c6e553403410b.log`。
- 补跑 `NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack`：完整生产构建通过，包含studio页面。
- `git diff --check`通过；依赖清单、lockfile、globals.css无变动。

真实Key调用仍未进行。qwen-vl-max可用性、三家真实账单价格需主控核实；公开状态检查不解密验证密文auth tag，实际调用的内部读取会验证。

## R2

已阅读 `06-eval.md`：作者账号不提供旧的 `qwen-vl-max`，`qwen3-vl-plus` 已由作者真实评测成功。本轮不联网、不调用真实 Key、不新增依赖、不提交；聊天看图代码和相关文档、非工作室测试均未修改。

### 逐条对应

| 返修项 | 实现 | 离线验证 |
| --- | --- | --- |
| R2-1 视觉模型可配置 | 新增 `FIONA_STUDIO_VISION_MODEL`，默认 `qwen3-vl-plus`，普通看图调用每次读取。空字符串为合法值，使用默认且不告警；非空值严格匹配 `^[a-z0-9][a-z0-9.\-]{1,63}$`，非法值回落默认并只告警一次。千问、DeepSeek看图路由和模型白名单读取配置；`vision_via` 返回配置模型；警告为「看图由千问视觉（实际模型）完成」。已报价调用及其修正锁定原模型，下一次新调用再读配置，防止配置热切换导致报价与付费请求不一致。 | 新增provider测试29项，覆盖默认/空/合法覆盖/非法值/边界长度/告警一次、复用实例动态读取、两家实际请求体、实际回复模型警告、providers信息、报价后切换及DeepSeek转交。 |
| R2-2 价目表 | 新增 `qwen3-vl-plus` 输入¥1/输出¥10每百万token（待核实），支持 `FIONA_STUDIO_PRICE_QWEN3_VL_PLUS` 覆盖；保留 `qwen-vl-max` 旧价结算旧job。自定义平台视觉价格计入CNY日额度。没有单价时，统一入口、直接提供方类和评测均在SDK创建/付费请求前返回409并提示价格环境变量；若报价后价格被移除，则拒绝且释放预留，不误记uncertain。 | 新增pricing测试7项，验证新旧价格及覆盖、自定义模型的CNY实际结算、两家缺价409/零SDK请求/零job、报价锁定与下一次读取新配置、报价后移除价格释放预留。 |
| R2-3 评测脚本 | plan及看图提供方使用同一配置和价格闸，确认后锁定已报价模型，报告写入实际视觉模型及完整警告；仍需足额 `--yes-spend` 才调用。 | 新增eval测试9项，覆盖默认/覆盖/下一次配置变化、缺价双重拒绝、未授权零请求、实际snapshot报告、报价后锁定及空值默认。 |
| R2-4 文档 | 全库搜索后逐处更新 `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example` 的工作室说明，补配置规则、待核实价目和覆盖示例。 | 搜索核对及diff检查通过。CLAUDE开头的聊天模型说明、ARCH聊天图片理解列表、PLAN聊天引用、`services/chat_service.py`/`model_router.py`保持原样；历史规格、复核和评测记录保留历史事实。 |
| R2-5 测试更新 | 原core/orchestration/eval工作室业务测试不再固定断言旧默认模型，改为读取配置；新测试仍显式覆盖选择旧模型的兼容行为。WO0的 `test_studio_probe.py` 只验证历史探针 `_studio_probe_brain.py` 的固定SDK协议参数，不是当前工作室业务路由，连同历史探针保留。 | R2新增45项离线测试全部通过；工作室全量959 passed。未修改非工作室测试、未新增skip/deselect。 |

### R2 修改文件

- 业务：`backend/studio/{config,brain,brain_jobs,pricing}.py`、`backend/scripts/studio_brain_eval.py`。
- 更新工作室测试：`test_studio_brain_core.py`、`test_studio_brain_orchestration.py`、`test_studio_brain_eval.py`；新增 `test_studio_brain_r2_{provider,pricing,eval}.py`。
- 文档：`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example`、本报告。

### R2 验证结果

后端均在 `backend/` 使用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，模型请求使用离线桩或模拟传输。

- R2新增：**45 passed**；相关核心/编排/评测定向：114 passed。
- 工作室 `python -m pytest -q tests/test_studio_*.py`：**959 passed、0 failed**，29条既有slowapi弃用警告，23.64秒，无deselect。
- 全量 `python -m pytest -q -ra`：**6199 passed、1 failed、5 errors、6 skipped**，29条既有slowapi弃用警告，177.86秒，无deselect。
  - failed：`test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`。
  - errors：`test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`；`test_safe_http_deadline.py` 的 `test_drip_response_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_four_stuck_resolutions_do_not_block_another_fetch`。
  - 上述1 failed/5 errors均在绑定本机回环端口时被沙箱以 `PermissionError: [Errno 1] Operation not permitted` 拒绝。
  - 6 skipped仍由已有 `test_byok_client.py:652`（2项）、`:882`（4项）自行检测回环绑定被拒绝后跳过，没有新增skip逻辑。需在允许绑定端口的环境复跑这些用例。
- 本轮前端源码无改动，因此按返修要求未重复运行前端lint/tsc。
- `git diff --check`通过；聊天看图、非工作室测试、依赖清单、lockfile、globals.css本轮均无变动。

### 需要人工核实

`qwen3-vl-plus` 的真实可用性以作者 `06-eval.md` 为证据，本轮没有重新请求模型。新增¥1/¥10单价仍为暂定值，需按账单核实或用价格环境变量覆盖。空值语义采用“使用默认且不告警”，已在配置注释、文档及测试中明确。

## R3

### R3-1 Node 入口与依赖检查

已阅读本地 main 提交 `57cf1c8` 与 `test_novel_p2_r1.py` 的 `probe()`，并逐一检查 `backend/tests/test_studio_*.py`。工作室测试只有三个实际启动 Node 的入口，均在每次 `subprocess.run` 前检查当前 checkout 中实际 require 的依赖入口文件；缺失时执行 `pytest.skip("frontend dependencies unavailable: ...")`，不启动 Node。Node 可执行文件缺失时另行跳过。

| 入口 | 实际依赖检查 | 复用这些入口的测试 |
| --- | --- | --- |
| `test_studio_frontend_shell.py::probe` | `typescript/lib/typescript.js` | shell、brain frontend、WO3 polish |
| `test_studio_frontend_navigation.py::probe` | `typescript/lib/typescript.js`；React/Next 等由 driver 模拟 | navigation、WO3 polish |
| `test_studio_frontend_components.py::probe` | `typescript/lib/typescript.js`、`react/index.js`、`react/jsx-runtime.js`、`react-dom/server.js`，缺失项逐一列入提示 | components、brain frontend、R1 frontend、WO3 polish |

`test_studio_brain_frontend.py`、`test_studio_wo3_polish_frontend.py`、`test_studio_brain_r1_frontend.py` 均通过上述入口调用，无需改动其测试内容。其他工作室 subprocess 为备份 shell 或 ffprobe 模拟，不涉及 Node。通过 AST 对比 HEAD，确认三个入口文件的原有测试函数内容（含 Python 与内嵌 JavaScript 断言）全部保持不变；非工作室测试未修改。

新增 `test_studio_frontend_dependencies.py`，9 项离线回归覆盖三个入口缺少整个 node_modules、SSR 的四项依赖分别缺失，以及 TypeScript 目录存在但入口文件缺失；均将 `subprocess.run` 替换为失败桩，确保缺依赖时零 Node 调用。

### R3-2 两种环境全量验证

后端均在 `backend/` 使用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。两次均执行完整 `-m pytest -q -ra --junitxml=...`，没有 deselect，没有修改或屏蔽非工作室测试。

先将 `frontend/node_modules` 原子改名为 `frontend/node_modules.__hidden` 后执行全量；使用 `try/finally` 保证测试结束即恢复目录，并核对恢复前后的目录 inode 相同。随后确认原名存在、隐藏名不存在，再执行第二轮全量。

| 环境 | 全量结果 | 其中工作室结果 | 用时 |
| --- | --- | --- | --- |
| node_modules 临时隐藏 | **6143 passed、71 skipped、1 failed、5 errors** | **920 passed、48 skipped、0 failed、0 errors** | 170.87 秒 |
| node_modules 恢复 | **6208 passed、6 skipped、1 failed、5 errors** | **968 passed、0 skipped、0 failed、0 errors** | 175.83 秒 |

隐藏时的48项工作室 Node 用例均按要求跳过：brain frontend 14项、R1 frontend 2项、components 9项、navigation 7项、shell 9项、WO3 polish 7项（45个测试函数，参数化后48项）。已将 XML 结果与源码中的全部 Node probe 测试逐一核对，全部匹配。源码静态检查和新增依赖回归正常运行。另有17项既有非工作室前端测试因缺依赖自行跳过；两轮均有6项既有BYOK测试因沙箱端口限制自行跳过。两份日志均无 `MODULE_NOT_FOUND` 或 `Cannot find module`。

**全量没有达到0 failed：两轮均为同一组既有沙箱端口限制。** 已逐项核对 XML 错误内容，全部为本机回环地址绑定遭 `PermissionError: [Errno 1] Operation not permitted` 拒绝：

- failed：`test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`。
- errors：`test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`；`test_safe_http_deadline.py` 的 `test_drip_response_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_four_stuck_resolutions_do_not_block_another_fetch`。

这些用例需在允许绑定本机端口的环境复跑，本轮没有通过新增 skip、deselect 或修改非工作室测试规避。

附加验证：新增依赖回归 **9 passed**；所有工作室前端专项（含新增回归）**59 passed**；`git diff --check` 通过。前端源码本轮无改动，未重复运行 npm 检查。无联网、无新增依赖、无提交。

日志及 XML：`/private/tmp/fiona-studio-r3-hidden.{log,xml}`、`/private/tmp/fiona-studio-r3-restored.{log,xml}`。最终再次确认 **`frontend/node_modules` 已恢复原样，`frontend/node_modules.__hidden` 不存在**。
