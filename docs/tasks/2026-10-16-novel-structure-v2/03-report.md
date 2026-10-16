# 小说推演结构 v2 第一期实施报告（含 R1、R2）

日期：2026-10-16。分支：`novel-structure-v2`，基线 HEAD：`85888d5`。

**T1–T7 已按规格及 §7 R1、§8 R2 完成。** 第一阶段默认 v1，v2 显式启用，volume_gate 默认 false；没有修改前端、已有测试、数据库列、计费实现或依赖，没有使用 git stash，没有提交 commit。完整测试的非通过项均为沙箱拒绝监听本地端口，详见第 5 节。

## 1. 修改文件

| 文件 | 修改内容 |
|---|---|
| `backend/novel/schemas.py` | 类型承诺、卷规划、v2 决策硬规则与实际归档预算校验 |
| `backend/novel/context.py` | 全历史结构统计、卷与里程碑简报、爽点历史、主线停滞和中文红灯 |
| `backend/novel/bible.py` | 类型承诺落罗盘、卷规划新版本、里程碑状态与独立结构历史 |
| `backend/novel/deliberation.py` | v2 提示词选择、固定卷会议、独立重做步骤键 |
| `backend/novel/writing.py` | P1 审校段落差异、复审降级、R2 空集兼容和 v2 归档元数据 |
| `backend/novel/agent_pool.py` | 类型承诺、卷会议、读者/节奏/爽点保护及 P1 审校追加提示词 |
| `backend/novel/runner.py` | 卷触发、持久化、恢复、关卡顺序、重做与重归档集成 |
| `backend/novel/service.py` | 默认 v1、类型承诺审批、卷接口业务与旧书升级生命周期 |
| `backend/novel/fake_llm.py` | 仅扩展离线 v2 新字段及新任务输出，原 v1/P0 输出不变 |
| `backend/routers/novel.py` | 三个卷接口和升级接口 |
| `backend/tests/test_novel_v2_core.py` | 72 项结构校验、统计、预算、里程碑与不可变性用例 |
| `backend/tests/test_novel_v2_review.py` | 53 项审校收敛、R2 三种情况、P0 与角色卡用例 |
| `backend/tests/test_novel_v2_api.py` | 32 项建书、审批、卷接口、升级、计费与取消恢复用例 |
| `backend/tests/test_novel_v2_compat.py` | 8 项真实引擎基线字节快照、默认结构及保护契约用例 |
| `backend/tests/test_novel_v2_runner.py` | 11 项 25 章计费验收、断点、关卡优先级及升级边界用例 |
| `CLAUDE.md` | 仅更新小说工坊一节的 v2 配置、接口和约束 |
| `README.md` | 第一期后端能力、默认值、卷接口与升级说明 |
| `docs/ARCHITECTURE.md` | 数据流、版本、计费复用、结构历史及审校兼容机制 |
| `PLAN.md` | 第一期交付与第二期、真实模型对比实验边界 |
| 本目录 `03-report.md` | 重写最终报告，保留两次停止记录 |

`02-spec.md` 为用户提供并修订的规格，本次没有修改；整个任务目录在首次开始时已经未跟踪。所有本次实现改动均在 §2 允许范围内。三个子代理按文件互不重叠分工，分别负责结构、审校提示词、服务路由；主代理负责推演/runner/fake/集成测试与文档。同一文件的后续修正仍交原负责人串行完成。

## 2. T1–T7 逐项对应

| 任务 | 实现与验证 |
|---|---|
| T1 + R1 | `CreateNovel.structure` 默认 `v1`，显式 `v2` 落 config；缺键旧书按 v1。新建 config 写 `volume_gate=false`，该字段不开放 CreateNovel 或 PATCH。默认建书、v1 原状态/版本/步骤及字节快照通过。 |
| T2 | v2 setup 必须返回 genre_contract，逐字段校验数量、整数、非空与 core_thread 引用；build_setup 写入 compass。立项提示要求从作者思路提炼承诺、变强诉求指向成长线；setup/approve 支持有效修改并拒绝不存在的主线。 |
| T3 + R1 | 第 1/11/21 章前运行固定卷会议：主编初案、已选择的 pacing_advisor/reader_rep 意见、主编定稿。每步复用原路由计费，计划原子写入 `dynamic.volumes` 和 `source=volume:n` 新版本。volume_gate=false 自动批准；true 且非全自动时先停 awaiting_volume。三个接口、重做、暂停恢复、全自动不停、已完成步骤不重复调用均覆盖。 |
| T4 | 简报增加类型承诺、当前卷/里程碑、爽点历史、主线停滞、开放伏笔与 red_flags。v2 决策增加顶层 genre_payoff/milestones_advanced；爽点、核心主线、到期里程碑、逐章/净新增/全卷伏笔预算由代码硬校验，具体数值进入修复错误。归档再次校验实际预算，milestones_done 只能引用本章 advanced；完成置 done、卷末剩余 open 置 missed、后卷红灯提示。v2 顾问/主编增加爽点保护。 |
| T5 + R2 | 所有 P1（包括 v1）使用追加的首审最多 8 条、旧问题逐条复核、细纲整场缺失才可阻断等规则。difflib 按段落提取新增/修改正文，约 3000 字截断并注明；复审新 evidence 不在改动段落内则 blocking=false/outside_changes=true，旧 evidence 不受改动范围限制。空集省略字段但内部仍降级，P0 不启用。原冻结四例与新增空/有改动/截断用例均通过。 |
| T6 + R1 | upgrade-structure 只接受 awaiting_review/paused，复用编辑互斥与状态校验；主编一次生成裸类型承诺，复用原预扣/结算/退款和 token 保护。升级只更新罗盘与结构配置，不写章节或圣经版本，保留原状态，volume_gate=false。下一章先开截短卷。成功、失败、取消、同输入断点复用、摘要变化后重新调用及原始章节/圣经字节不变均测试。 |
| T7 | 新增 5 个离线测试文件，共 176 项；旧测试 diff 为空。保护五个服务签名、novel_chapters 原 DDL、原圣经键与 P0 冻结流程，并完成实际两版引擎字节比对及 25 章验收。 |

新增接口：

- `GET /novels/{id}/volumes`：返回全部卷规划及里程碑状态。
- `POST /novels/{id}/volume/approve`：省略 body 或传空对象可直接批准；可传 `{"volume_plan": 完整规划}` 编辑后批准，按规则验证，编辑另建 user_edit 版本。
- `POST /novels/{id}/volume/redo`：`{"text": "一句话指示"}`，生成新的付费卷会议步骤。
- `POST /novels/{id}/upgrade-structure`：无请求体，生成类型承诺并升级，不自动推进章节。

## 3. §4.3：25 章 v2 小书实测

用例：`test_novel_v2_runner.py::test_25_chapter_paid_fake_acceptance`，显式 structure=v2、full_auto、每卷十章。隔离临时库中设 DEV_MODE=0，使用平台型号和原 NovelBilling，**仅将提供方网络响应替换为本地 FakeLLM**，因此覆盖真实预扣与原子结算路径，而非以 dry_run 零花费证明守恒。没有真实模型调用或真实用户扣费。

| 指标 | 实测数字 |
|---|---|
| 完成章数、末状态、圣经版本 | 25 章，awaiting_end，版本 30 |
| 卷会议 | 3 次，开会章为 1、11、21；source 为 volume:1、volume:2、volume:3，各一次 |
| 卷范围 | [1,10]、[11,20]、[21,25] |
| 全部模型步骤 | 190 个，190 个唯一步骤键，全部结算；无重复调用 |
| 类型爽点 | 8 次，章号 3、6、9、12、15、18、21、24；3 种 |
| 三章爽点滑窗 | 23 个完整窗口全部有爽点；最长连续无爽点 2 章 |
| 核心主线 T1 | 推进 25 次；最长连续空缺 0 章；23 个完整三章窗口全部合格 |
| 里程碑 | 6/6 done，0 missed |
| 每卷实际新埋伏笔 | [1,1,1]，预算分别为 [4,4,4] |
| 每章最大新埋、预算违规 | 最大 1 条；逐章、净新增及卷累计违规均为 0 |
| 未回收伏笔 | 峰值 2，最终 0；初始 1 条，后续新埋 3、回收 4 |
| 账目 | spent=2837 草莓；步骤实扣总和=2837；账户余额减少=2837；reserved=0，无待结算步骤 |

原始结果日志：`/tmp/novel-v2-25-acceptance.log`，末行指标 JSON：

```json
{"calls": 190, "chapters": 25, "core_advanced": 25, "final_open": 0, "maximum_open": 2, "milestones_done": 6, "payoff_chapters": [3, 6, 9, 12, 15, 18, 21, 24], "payoff_types": ["主动反击", "揭露真相", "确认关键证据"], "reserved": 0, "spent": 2837, "step_charges": 2837, "volume_chapters": [[1, 10], [11, 20], [21, 25]], "volume_meetings": 3, "volume_planted": [1, 1, 1]}
```

这些是固定 fake 故事的机械验收与模拟账本数字，不代表真实模型质量或供应商账单；修仙类型的质量对比仍属 §5 另单。

## 4. 默认 v1 逐字节一致与不变量证据

将 `85888d5` 的 novel 包通过 git archive 提取至临时目录，明确将其放在 import 路径首位，实际执行原版 `deliberate` 和 `write_chapter`。随后用相同离线 RecordingRouter/FakeLLM、相同输入执行新代码；比较步骤键列表、每条 user payload 原始字符串及完整会议/正文/审校/归档输出的 UTF-8 SHA256。

覆盖 solo、critique、merge 各三章，分别测试缺 structure 键和显式 v1，共 6 组；圣经版本均为 5，全部一致。P1 reviewer system 提示词仅按 T5 有意追加，仍保留原句；上述 user payload 比对没有忽略字段。

| 模式 | 步骤数 | user payload SHA256（两版相同） |
|---|---:|---|
| solo | 12 | `3c9ca72b2901741829c4a97e7973f6932507a1591f8471c52840c8cf9dbdb0e0` |
| critique | 24 | `47e40b678068fc1e363fca15c03f6382da65b5edc8c622b6ed40c6ccc4b44170` |
| merge | 30 | `d9884049454ba56b6cbfb3bd03a8e4cff80145f11e262e680225fff4b5f8fddb` |

步骤键及完整输出的 SHA256 也固定在 `test_novel_v2_compat.py::BASELINE`；测试运行不依赖 git 历史或仓库外文件。默认 CreateNovel 仍为 v1、不能传 volume_gate 另有独立测试；原 API/runner 建书测试未改输入或断言而通过。

- `list_books/detail/bible/chapter/owned` 的签名保持原样，新增测试逐项核对。
- `store_db.py` 未修改；novel_chapters 的原 DDL SHA256 固定为 `45d349c739527b2f972656a498be004a12ea9065ef6f283479f8bb08db3a64d4`。
- 原 locked、chapter_summaries、arc_summaries、character_states 结构不变；v2 另增 dynamic.volumes/structure_history。
- completed/done/stale 的语义、计费代码与原子事务不变；P0 A/A2/B/C 冻结流程、步骤键和正文哈希测试及 P0 审校 payload 测试通过。
- `git diff --exit-code -- backend/tests` 为空（新增文件未跟踪，全部为 test_novel_v2_*.py）；`git diff --check` 通过。没有前端或依赖改动。

## 5. 测试结果（新增、全量与沙箱端口分别列出）

所有命令均使用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，在对应仓库的 `backend/` 下执行 `-m pytest`。

| 检查 | 最终结果 |
|---|---|
| 当前工作树新增测试：`-m pytest -q tests/test_novel_v2_*.py` | 176 passed, 32 warnings in 7.22s |
| 无 frontend/node_modules 副本中同命令 | 176 passed, 32 warnings in 7.61s |
| 当前工作树全量：`-m pytest -q` | 1 failed, 5416 passed, 6 skipped, 32 warnings, 5 errors in 150.51s (0:02:30) |
| 25 章单项带指标输出 | 1 passed in 1.82s |
| 静态检查 | git diff --check 通过，已有测试 diff 为空，改动范围符合 §2 |

无 node_modules 副本路径为 `/tmp/novel-v2-r2-no-node-modules`，通过基线 archive 加本次源文件/新增测试覆盖构建，确认不存在 frontend/node_modules。新增测试需要的夹具均在仓库内；同一外部虚拟环境只提供解释器和依赖。

全量中的 6 个非通过项均由当前沙箱禁止本地端口 bind 导致，**没有因此修改、跳过或放宽既有测试**：

| 结果 | 用例 | 直接原因 |
|---|---|---|
| failed | test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot | asyncio 创建监听服务时，bind(127.0.0.1,0) 返回 PermissionError/Errno 1 |
| error | test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive | 本地 HTTP server 夹具 bind 被拒绝 |
| error | test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline | 本地 HTTP server 夹具 bind 被拒绝 |
| error | test_safe_http_deadline.py::test_fast_response_and_redirect_still_work | 同上 |
| error | test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline | 同上 |
| error | test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch | 同上 |

全量日志为 `/tmp/novel-v2-full-tests-final.log`；新增与副本日志分别为 `/tmp/novel-v2-new-tests-final.log`、`/tmp/novel-v2-no-node-modules-tests.log`。32 条 warning 为既有 slowapi 对 asyncio.iscoroutinefunction 的 Python 3.14 弃用提示。6 skipped 保持既有测试自己的跳过决定，未改它们的输入、断言或标记。

验收 §4.1 的“全量零失败”在当前禁止监听端口的沙箱内未达成；除上述端口项外，全量无其他失败。§4.2 改动与旧测试保护、§4.3 25 章机械与账目验收均已完成；§4.4 真实对比实验未执行。

实现过程还修复了新增测试初稿中对历史 strawberries_reserved 字段的误解：步骤结算后该列保留原预扣数作审计，不能要求每条历史列为 0。最终改为检查书级 reserved=0、无 billing_status=reserved、spent/步骤实扣/余额减少三方一致，未改计费实现或既有测试。

## 6. 实现选择与待确认事项

- 核心主线采用每三章滑窗：前两章均未推进则本章必须推进。thread_staleness 是当前章号减上次推进章号；因此距离 3 时红灯说明已空缺 2 章，保证 §4.3 无连续三章空缺。爽点在第一个完整周期到来前允许为空，间隔 1 时每章必有。
- genre_payoff.beat_index 使用从 1 开始的节拍序号，并校验不超过节拍数量。
- 结构统计先看完整历史再裁模型上下文；新增独立 structure_history，不改变原章节摘要条目。升级后的首章、细纲重做与作者审批也读取旧 v1 decision 历史，避免误报停滞。
- 卷与批关卡同时到达时，先提交章、发布下卷规划/卷关卡，再发布待处理批关卡；pending 标记可断点恢复。切全自动会自动批准待批卷、清除旧批次等待。重归档最新章会保留其后已付费发布的卷规划。
- 卷重做计数持久化，使用独立 -redoN 步骤键；升级步骤键附输入摘要，相同输入断点复用、章节摘要变化后重新生成。原计费规则和原子性不变。
- 升级卷号严格按 ceil(chapters_done/10)+1，范围从下一章到下一个整十章并截于目标上限；例如已写 15 章时卷号为 3、范围为 [16,20]。若升级时已经写到目标尾章，后续扩章会按新目标刷新范围。
- difflib 按空行划分段落，changed_passages 为当前正文的新增/修改段落列表；纯删除没有可引用的当前段落，集合为空，按 R2 省字段并降级新问题。截断说明计入约 3000 字上限。
- 作者编辑卷规划时，里程碑重置 open，完成状态由归档拥有，防止通过计划字段伪造完成。

**需要外部复验**：在允许绑定回环端口的环境重新运行上述 6 项，或完整 `-m pytest -q`。没有未完成的 T1–T7 实现，也没有新出现且待裁定的 §6 冻结冲突。第二期前端、默认改 v2、真实模型质量/成本对比均按规格留待另单；真实对比开跑前仍需单独报价和作者批准。

## 7. 首次停止记录（保留，已由 R1 解决）

首次原规格 D6/T1 要求新书默认 v2，而既有 P1 测试未传 structure，仍冻结直接进入 awaiting_plan/awaiting_review 和原圣经版本号。证据为 test_novel_p1_runner.py:22、62、88、114 及 test_novel_p1_api.py:20、61、80。三个子代理只读复核后按 §6 停止，未修改代码/旧测试，仅新增报告。

当时基线相关测试为 4 passed in 2.39s。首次命令曾误用不存在节点 test_batch_gate_continues_and_extension，退出码 4、未运行测试，更正后通过。R1 裁定第一期默认 v1、volume_gate 默认 false、不向建书开放、升级不开卷关卡，解除冲突。

## 8. 第二次停止记录（保留，已由 R2 解决）

R1 后发现 test_novel_p21_writing.py:104–116 对 P1 复审全部 user payload 做 UTF-8 字节冻结，旧 payload 不含 changed_passages。四例的 fake 正文无改动，即使追加 changed_passages:[] 也失败。保留原提示词并追加规则的隔离最小复现得到 4 failed in 0.19s；原实现四例为 4 passed in 0.20s。按 T5.4/§6/§7.5 再次停止，将当时尚未接完的三个后端文件修改撤回，相关原测试恢复 94 passed in 0.99s。

R2 采纳空改动省字段、内部仍按空集降级的兼容方式，并要求追加对应提示词。本次按 R2 完整实施，原冻结四例与新增审校测试均通过。以上历史失败不是当前代码的测试结果。


## 第 1 轮返修

依据：`05-fix-r1.md`、`04-review-a.md`、`04-review-b.md`。F1–F7 全部完成；本节更新前文的复审判定、爽点统计、卷延长和 v1 config 口径，前文保留为初次交付及两次停止的历史记录。

### 本轮文件与断言保护

本轮修改 8 个后端文件：`novel/writing.py`、`schemas.py`、`context.py`、`bible.py`、`runner.py`、`fake_llm.py`、`service.py`、`agent_pool.py`；修改本期新增的 `test_novel_v2_review.py`、`test_novel_v2_core.py`、`test_novel_v2_api.py`、`test_novel_v2_runner.py`，并仅在本报告末尾追加本节。`test_novel_v2_compat.py` 未改；推演/路由文件及四份说明文档在本轮未再修改，其工作树 diff 属于初次交付。

三个子代理继续按文件互不重叠分工：审校代理独占 writing/review tests，结构代理独占 schemas/context/bible/core tests，服务代理独占 service/agent_pool/API tests；主代理负责 runner/fake/runner tests、探针和报告。

基线 85888d5 的已有测试一律未改，`git diff --exit-code -- backend/tests` 为空。对本轮开始前保存的五份新增测试做断言审计：

- F1 明确授权的截断测试改为“截掉区域内证据仍阻断、不带 outside_changes”，并相应改名。
- F7.3 点名的配置语义改为 v1 config 不含 structure/volume_gate；创建、升级失败、升级中断的相关断言同步改为缺键。
- F4 归档输入按返修单补 payoff_delivered=true，原结构历史的整条精确相等断言新增确认字段，是收紧；25 章用例保留原全部断言，额外要求实际归档确认及每个三章窗口真实兑现。
- 其余已有断言未删除或放宽；补了新用例及参数，未改前端、依赖、数据库列或计费实现。未使用 git stash，未提交 commit。

### F1–F7 逐条改法与证据

| 项目 | 改法 | 证据 |
|---|---|---|
| F1 必修 | `changed_passages(..., limit=None)` 先计算全集，再由 `_passages_payload` 截约 3000 字给模型；复审代码兜底仅使用全集。空行分段若仅 1–2 段且正文至少 6 行，则退化为按单换行分段。截断说明不进入兜底匹配。 | 授权截断断言已纠正；新增末段硬伤/超 3000 字/单换行用例；probe3 Case B/C 均保留阻断。 |
| F2 必修 | 全部 evidence/正文/段落匹配统一 `schemas.compact()`；互为子串、正文定位区间相交、同一段落，任一满足即旧问题复报；可选 1-based previous_issue_index 有效时直接归类，提示词追加说明。 | 新增缩短/扩大跨度、区间相交、同段、直弯引号、有效/无效索引及真新问题降级用例；probe3 Case A 与等价 probe9 均阻断。 |
| F3 必修 | decision 无 genre_payoff 键时不套用 v2 预算与实际新埋≤计划；保留里程碑子集检查。旧章重归档不套 v2 角色输出、不新增 structure_history 或空 volumes。v2 章重归档继续严格校验。 | probe8 恢复 awaiting_review、1 次归档无修复；新增对照两本书 raw bible_json 字节完全相等、均保留旧章 3 条伏笔；另有 v2 章 3 条伏笔重归档仍失败的反例。 |
| F4 应修 | v2 写手上下文携带 genre_payoff/milestones_advanced，提示写出可见场面；审校接收计划爽点，缺失按整条节拍缺失阻断；计划非空时 archive 必填严格 bool payoff_delivered。结构历史、正常推演、redo 和审批均优先按档案确认统计，false 不算爽点，缺字段旧数据回退计划。fake 写出可见场面，并按最终正文核实。 | 新增正文未兑现→archive=false→下一章硬校验要求补爽点的 runner 反例；字段类型/历史优先级用例；25 章的 8 次计划均有 archive=true，23 个完整三章窗口都有确认。 |
| F5 应修 | open 里程碑 due_chapter<=当前章时持续进入 advanced 硬要求；逾期红灯明确“已逾期 N 章”。done/missed 后不再硬压。 | 新增连续逾期、缺失/包含 ID 的正反例及 done/missed 解除要求用例。 |
| F6 应修 | 本卷新埋额度用尽或 open>20，红灯加入“本章章末钩子不得引入新的未解谜团，只能使用已有线索或正面冲突”；v2 主编提示同步，保持仅提示。 | 新增两类触发与未触发对照；角色卡含对应规则，v1 提示词不加该规则。 |
| F7 应修 | v2 critique_plan 明确 genre_payoff 及保护；升级距整十边界不足 3 章则合并下一边界并截于 max；reject_end 延长原末卷并补齐最小 payoff_plan，保留里程碑状态、同步 gate，写 volume_extend:n 版本；重归档保留这次同卷扩展。v1 配置不落 structure/volume_gate。升级中的 pause 精确返回 409“正在升级结构，请稍后再试”。 | 新增 7/8/9 章后升级、末卷 3→4/9→13、延长后改稿不另开卷、暂停/继续并发守卫、精确爽点窗口边界、只走 runner 的 awaiting_volume 恢复用例；严格 probe5 包含原始 config_json 完全相同。 |

组合回归曾暴露前台异步工具与 TestClient 后台任务不在同一事件循环的取消竞态：`cancel_novel` 现在先跳过已结束任务；活跃任务在其所属循环取消并排空，之后仍按原顺序退款和清 token。新增跨循环排空测试通过，未放宽旧测试，也未修改计费口径或原子事务。

### 探针复跑输出

均在 backend/ 下使用指定解释器，并显式设置四家 API Key=placeholder、PYTHON_DOTENV_DISABLED=1，全部离线。

probe3 原脚本：

```text
CASE A: blocking=True outside_changes=None passed=False rounds=3 flags=['review_unresolved']
CASE B: payload_passages_chars=3000 full_changed_chars=4400 evidence_in_full_changed=True blocking=True outside_changes=None passed=False
CASE C: passages=2 chars=290 blocking=True outside_changes=None passed=False
PROBE3 false-negatives: A(old-issue-respan)=False B(truncation)=False C(single-newline)=False
```

Case B/C 后续确实进入下一轮，探针脚本在 r2 才返回空问题；因此其最终 flags 可以为空，r1 没有再静默放行。

probe8 原脚本：

```text
v1 re-archive after edit: status awaiting_review pause_reason None planted now 3
v2 re-archive of the v1 chapter after upgrade: status awaiting_review pause_reason None archive attempts 1 repair errors [] last_error None
```

提供的 a/ 目录没有独立 probe9 文件；按 review-a 的 Case D 在同一辅助函数上重建等价探针（直引号 evidence、弯引号正文、改动内新硬伤）：

```text
PROBE9 equivalent Case D: kept=True blocking=True outside_changes=None passed=False
```

b/mut/backend/tests/test_zz_probe_runner.py 的原断言故意固定旧缺陷（paused/step_failed 与 [10,10]）。本次未修改原探针，在 /tmp 复制同样输入和流程，仅将修复后的期望改为 awaiting_review/None 与 [10,12]，结果：

```text
AFTER REARCHIVE: awaiting_review None None
UPGRADE MARKER: {'end_chapter': 12, 'start_chapter': 10, 'volume': 2}
VOLUMES: [(2, [10, 12], 2, 1)]
STATUS: awaiting_end 12
2 passed in 1.25s
```

这里 max=12，所以不足 3 章合并到下一边界后再截于 12；max 足够时，第 9 章后升级得到 [10,20]，已由 API 新用例覆盖。

日志：`/tmp/fix-r1-probe3_t5_review.log`、`/tmp/fix-r1-probe8_rearchive_after_upgrade.log`、`/tmp/fix-r1-probe9-equivalent.log`、`/tmp/fix-r1-b-probes.log`。修复后的 b 探针副本为 `/tmp/test_fix_r1_b_probe_runner.py`，原 scratchpad 文件未改。

### v1 逐字节对比（包括 config_json）

probe1 原脚本使用两套真实 LLMRouter/RunStore、deliberate/write_chapter，在 solo/critique/merge × 缺键/显式v1 × drama关/开共 12 组十章场景，以及 1 组无 reviewer 的三章场景对比；全部 13 组 OK，末行 `PROBE1 PASS`。每个十章场景步骤数分别 41、91、121；步骤键、正文、圣经和全部 user 消息逐字节一致，仅 P1 reviewer system 允许 T5/F1/F2 追加。

probe5 按原生命周期执行，但使用更严格的 /tmp 副本：**移除新版本创建后手工 pop structure 的动作**，并额外保留 SQL 读出的原始 config_json 字符串。基线与现版的 12 次状态记录、52 个步骤键、10 个版本、7 章、全部章节/档案/圣经 JSON、罗盘、留言、导出和原始 config_json 均 BYTE_EQ。并发顾问调用按 step_key 对齐后比较消息内容，不忽略任何 user 字节；仅 7 次 P1 reviewer system 有授权追加。

```text
config_json BYTE_EQ
config_json_sha256=c91cf3f611f1581732c9837481721d9f55d0a9c5b7d4f066cc8d0bf7790d4875
config_json_keys=adaptation,agents,automation,batch_size,budget_strawberries,critique_rounds,drama_adaptation,enable_arc_summaries,enable_context_compression,experiment,panel_mode,seed_idea,target
steps=52 lifecycle_states=12 versions=10 chapters=7
P1_reviewer_system_only_differences=7
STRICT_PROBE5_PASS
```

probe5 严格副本、两版快照和比较日志分别为 `/tmp/fix-r1-probe5-strict.py`、`/tmp/fix-r1-probe5-{base,new}.json`、`/tmp/fix-r1-probe5-comparison.log`。仓库内的兼容性测试仍使用原 BASELINE 哈希，未修改快照去迁就实现。

### 测试与 25 章复验

| 检查 | 本轮最终结果 |
|---|---|
| 五个新增测试文件 | 230 passed, 32 warnings in 9.36s |
| 不含 frontend/node_modules 的独立副本 | 230 passed, 32 warnings in 10.11s |
| 后端全量 `-m pytest -q` | 1 failed, 5470 passed, 6 skipped, 32 warnings, 5 errors in 144.88s (0:02:24) |
| 原始 v1 引擎 probe1 | 13 组 OK，PROBE1 PASS |
| 严格生命周期 probe5 | 全部持久化内容和 config_json BYTE_EQ |
| 25 章 paid fake 路由 | 1 passed in 1.92s |
| diff 检查 | git diff --check 通过，基线旧测试/前端无 diff |

本期新增测试由 176 项增至 230 项（本轮新增 54 项）：core=101、review=65、API=39、runner=17、compat=8。无 node_modules 副本为 `/tmp/novel-v2-fix-r1-no-node-modules`。测试均使用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，显式占位环境变量，未读取真实密钥或调用真实模型。

25 章复验结果：190 个步骤、3 次卷会议、25 次核心主线推进；爽点章仍为 3/6/9/12/15/18/21/24，8 次都有档案员实际兑现确认；里程碑 6/6 done，三卷新埋 [1,1,1]，开放伏笔峰值 2、终值 0；spent=2918=步骤实扣总和=余额减少，reserved=0。比初次交付多出的模拟草莓来自新增提示词、正文兑现场面、确认字段及上下文，非真实模型费用。

```json
{"calls": 190, "chapters": 25, "core_advanced": 25, "final_open": 0, "maximum_open": 2, "milestones_done": 6, "payoff_chapters": [3, 6, 9, 12, 15, 18, 21, 24], "payoff_types": ["主动反击", "揭露真相", "确认关键证据"], "reserved": 0, "spent": 2918, "step_charges": 2918, "volume_chapters": [[1, 10], [11, 20], [21, 25]], "volume_meetings": 3, "volume_planted": [1, 1, 1]}
```

合规 fake 小书证明管线、实际确认传递和账目守恒，不单独证明校验拦截力；后者由预算/窗口/里程碑正反例、缺少实际爽点后下一章强制重试、原生 v2 重归档仍拒绝 3 条伏笔等反例覆盖。未运行 §5 真实模型对比实验。

### 端口类失败单列与待确认项

本轮全量的非通过项与初次交付相同，均在 bind(127.0.0.1,0) 时遇到 PermissionError/Errno 1 Operation not permitted：

- failed：`test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`。
- errors：`test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`，以及 `test_safe_http_deadline.py` 的 `test_drip_response_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_four_stuck_resolutions_do_not_block_another_fetch`。

没有为端口限制改测试、取消断言或修改标记。32 条 warning 为既有 slowapi 弃用提示；6 skipped 保持原用例自身决定。完整日志为 `/tmp/novel-v2-fix-r1-full-tests.log`，新增/副本日志为 `/tmp/novel-v2-fix-r1-new-tests.log`、`/tmp/novel-v2-fix-r1-copy-tests.log`，25 章日志为 `/tmp/novel-v2-fix-r1-25.log`。

F1–F7 没有未完成实现或新的 §6 冻结冲突。待外部复验：允许回环端口监听的环境下复跑上述 6 项或全量；独立 probe9 原文件未在提供目录找到，本次已完成同一 Case D 等价验证，验收方可再用其原脚本复跑。真实模型质量及成本仍按原规格另单报价与批准。
