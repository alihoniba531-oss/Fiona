# 小说工坊 P1 后端实施报告

实施日期：2026-10-15（验收运行跨至 UTC 2026-10-16）。以 `02-spec.md` 第 13 节作者最终拍板为准。使用指定 Python 3.14 解释器；全部命令在对应检出的 `backend/` 执行。未联网、未读取真实密钥、未调用真实提供方、未新增依赖、未提交 commit。

## 1. 文件清单

新增业务文件：

- `backend/novel/store_db.py`
- `backend/novel/billing.py`
- `backend/novel/byok_bridge.py`
- `backend/novel/runner.py`
- `backend/novel/service.py`
- `backend/novel/safety.py`
- `backend/routers/novel.py`

新增测试（共95项）：

- `backend/tests/test_novel_p1_store.py`
- `backend/tests/test_novel_p1_billing.py`
- `backend/tests/test_novel_p1_byok.py`
- `backend/tests/test_novel_p1_context.py`
- `backend/tests/test_novel_p1_runner.py`
- `backend/tests/test_novel_p1_api.py`
- `backend/tests/test_novel_p1_p0.py`

修改既有文件：`backend/database.py`、`backend/main.py`、`backend/rate_limit.py`；引擎中 `backend/novel/agent_pool.py`、`context.py`、`deliberation.py`、`fake_llm.py`、`llm_router.py`、`run_store.py`、`writing.py`，仅涉及存储协议、计费/BYOK、安全、P1 solo 与上下文压缩/卷摘要。

文档：`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、`CLAUDE.md`、`backend/.env.example`，以及本报告。

上述三个接入模块和六个文档文件均只有新增行，没有删除或移动原有行；已有 local watch 内容保持原样。既有测试文件未修改。任务规格 `02-spec.md` 在开始时已是未跟踪文件，本次未修改它。

## 2. 功能与实现决定

- SQLite 五表保存小说、圣经版本、章节、步骤及留言；步骤只保存提示词 SHA-256，不保存完整提示词。模型产物和 token/缓存用量可查询；章节、圣经和进度在同一事务提交。
- HTTP 只启动/查询/发送指令。运行器复用 P0 的 `build_setup`、`deliberate`、`write_chapter`，没有第二份推演或写作引擎。写作和用户改稿共同使用 `apply_archived_chapter`，避免重复归档/卷摘要逻辑。
- 立项、每章细纲、批次审阅、完结四类关卡；支持批准、校验后改细纲、只重跑主编定稿、暂停/恢复、预算调整、留言、改稿、延长完结、导出和删除。
- 每用户一本运行书，全局默认三槽；排队保留 running。run_token 与账号存在检查在 SQLite 写事务内完成，防止旧任务或删号后重建数据。关卡切换时先等待旧任务清理，再启动新令牌，避免竞态。暂停与setup完成相撞时，恢复仍回到awaiting_setup，不绕过固定立项确认。
- 取消和恢复退还 reserved，并标 interrupted；已成功步骤命中缓存，不调用、不重复计费。缺表恢复仅用于初始化被替换为空操作等场景，无小说表时直接返回，其他数据库异常不会被吞掉。
- 每次真实尝试分别预扣和结算，校验修正重试计费；网络失败或没有完整 usage 全额退还。BYOK、fake、DEV_MODE 免费。预算暂停保存当时预算，原预算恢复返回 409，必须先提高预算。
- 平台只有千问、DeepSeek、豆包；BYOK 仅允许三个预设厂商及引擎已知型号。临时取得 Key 后复用原非流式调用分支，调用结束关闭临时客户端并清除引用。Claude 保持原思考映射；千问和 DeepSeek 关闭思考。
- 所有角色附加安全规则，置于防注入句之前，同时保留已有 JSON 引号规则及注入守卫的结尾契约。
- P1 开启 `enable_context_compression` 与 `enable_arc_summaries`：稳定/变化两条 user 消息，Anthropic 系统及首条 user 使用 ephemeral；P0 保持既有消息形状与调用步骤。第 10、20……章归档生成至多 600 字卷摘要；最新整十章改稿也重新归档和重做卷摘要。进度与章节字数统一使用P0不计空白的统计口径。

## 3. 规格逐节对应

| 规格 | 落实位置及验证 |
|---|---|
| §0 P0 复用 | runner 调用既有 deliberation/writing；P0 四配置步骤键及正文 SHA-256 冻结比对通过。 |
| §1 范围 | 本报告文件清单；git diff 范围审计、既有测试零改动、受保护接入和文档零删除行。 |
| §2 技术/隐私 | FastAPI、aiosqlite、统一 create_background_task；无 ORM/新依赖；日志只含小说 ID、角色/模型、章号、token、耗时和状态；Key 不落小说库/日志/响应。 |
| §3 数据模型 | store_db.NOVEL_TABLES_DDL，database.init_db 幂等建表；全部表有 username，关联索引、复合主键及 username/status 索引；删号同事务清理五表。 |
| §4.1 存储协议 | run_store.StepStore、RunStore 与 DbStepStore；LLMRouter 不依赖文件路径。 |
| §4.2 计费钩子 | LLMRouter 每次平台真实 attempt 调用 NovelBilling.reserve/settle/refund；余额不足抛独立异常；缓存、BYOK、fake、DEV_MODE 免费。 |
| §4.3 BYOK | byok_bridge.ByokBridge 与 llm_router 共用 provider seam；拒绝 custom/moonshot/zhipu/未知型号；内存临时 Key。 |
| §4.4 安全 | safety.NOVEL_SAFETY_RULES + agent_pool 全角色提示；覆盖所有底线与防注入顺序。 |
| §4.5 模式 | CreateNovel 默认 critique，只允许 critique/solo；零顾问按 solo，merge 不开放。 |
| §4.6 压缩/缓存 | context 纯函数裁剪、稳定消息拆分；writing 共用归档 helper 和 arc_summary；30/60 章代表样例与极限保留测试，边界见 §7。 |
| §5 状态/原子推进 | runner 全状态机、setup/plan/batch/end 关卡；store_db 原子提交正文、圣经、计数与留言回应。 |
| §5 暂停/限额 | 用户、80%预算、余额、锁定冲突、步骤/裁决失败、daily_cap；review_unresolved 只加 flag；北京时间零点后手动恢复。 |
| §5 并发/恢复/取消 | 每用户运行互斥、全局队列、run_token；取消退款，恢复 reserved 退款、缓存续跑；恢复失败暂停 server_restart_failed。 |
| §5 留言/改稿 | pending N{id} 下发并回应后 delivered；最新章后台以原归档前圣经重归档，新 source=rearchive:n；早期改稿仅标后续 stale，响应明确不自动重写/重算。 |
| §6 计费/估算 | billing 默认价目/完整覆盖/一次告警、ceil 且最少1、字符及 max_tokens 预扣、实扣不超预扣、差额退款；最近20真实步骤按尝试数归一，无历史用 A2 基线与1–10章增长/其后稳定口径。 |
| §7 全部 API | routers/novel + service；登录/字面开关/白名单、输入上限、所有写操作20/minute、所有书操作验证所属、状态冲突409、越权404、导出附件。 |
| §8 角色/型号 | service.validate_selection；必选三角色、可选审校、六顾问最多选五个；JSON角色/写手分别使用规格允许清单。 |
| §9 删号/隐私 | database.delete_account_data 先取消退款再同事务删五表；后台条件写入测试证明账号删除与令牌失效后写入为 no-op；文档列明数据厂商。 |
| §10 测试 | 七份新增离线测试，覆盖表格下方1–17项；不读取仓库外输入、不依赖 git 历史。 |
| §11 验收 | 固定解释器全量、剔除六项已知回环绑定限制的全量、新增测试浅克隆、三章 fake 端到端和范围检查，结果见 §5。 |
| §12 执行 | 按文件无重叠并行，最后统一集成；没有回滚完成工作或提交 commit。上下文极限约束冲突已向作者提出口径选择。 |
| §13 D1/D2/D3 | 按作者拍板折算价格；平台无 Claude，catalog 含指定提示；本机监控所有既有行原样保留。 |

## 4. 测试覆盖清单

| §10 项 | 测试位置 |
|---|---|
| 1 开关与白名单 | api：关闭/非法开关、名单外/空名单。 |
| 2 建书校验 | api：缺角色、错模型、预算不足、merge/长度/批大小、四种不支持 BYOK。 |
| 3 主流程 | api/runner：setup版本1、批准版本2、5章版本7、继续及完结版本核对；三章 DEV/fake 端到端。 |
| 4 critique/solo | api/runner：两模式全书，初案/意见/替代走向/逐条回应。 |
| 5 每章确认 | api/runner/billing：直接批准、合法细纲修改、非法422、只重定稿且计费。 |
| 6 计费 | billing：生产模式余额/账目核对、差额、重试收费、网络/无usage退款、免费/BYOK、缓存、余额/预算暂停及提高预算后恢复。 |
| 7 恢复 | runner/billing：中断时退款、保留成功缓存、fake调用计数和一次跑完正文逐字节相同。 |
| 8 并发 | runner：同用户第二本409、四用户三槽与第四本排队。 |
| 9 完结 | api/runner：缺extend 422、加长后继续和最终守卫。 |
| 10 留言 | api/runner：五条上限、下发一次、持久回应、待处理清零。 |
| 11 改稿 | api/runner：最新重归档增版本，早期stale且不增加模型调用；第10章改稿重做卷摘要。 |
| 12 删除 | api/runner/store/既有account_deletion：五表无残留、删号取消退款、删除账号/书/令牌后条件写不重建。 |
| 13 越权 | api：对别人的书执行全部15类详情/章节/写操作/导出/删除，一律404。 |
| 14 密钥/日志 | api/byok/billing：哨兵 Key 在库/日志/响应与步骤产物中均不存在，思路/正文不进入日志；MockTransport 不接外网。 |
| 15 P0不变 | p0：改动前四份配置全部步骤键与正文SHA-256直接冻结在测试常量；不读取git历史或外部基线文件。 |
| 16 health/迁移 | api/store/既有health：/health成功、迁移集合冻结不变、启动清理旧行为兼容。 |
| 17 压缩 | context/byok/billing：60章裁剪、30/60代表样例差≤10%、open不丢、10/20卷摘要各一次且收费、双user及Anthropic请求体cache_control、缓存token。 |

## 5. 验证命令与输出

所有测试使用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，以下以 `$PY` 表示这个固定路径。工作目录均为各检出的 `backend/`。没有启动真实服务。

### 新增测试

```bash
$PY -m pytest -q tests/test_novel_p1_*.py
```

输出末尾：

```text
95 passed, 28 warnings in 6.70s
```

### 全量（原命令）

```bash
$PY -m pytest -q
```

输出末尾：

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 4843 passed, 9 skipped, 28 warnings, 5 errors in 136.56s (0:02:16)
```

六项均为当前沙箱绑定 `127.0.0.1` 被拒绝（`PermissionError: [Errno 1] operation not permitted`），按规格不计入新增失败；其余没有失败。

### 排除六项已知沙箱端口限制的全量

```bash
$PY -m pytest -q -k 'not test_stop_disconnects_async_upstream_and_releases_user_slot and not test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive and not test_drip_response_obeys_total_wall_clock_deadline and not test_fast_response_and_redirect_still_work and not test_drip_headers_obey_total_wall_clock_deadline and not test_four_stuck_resolutions_do_not_block_another_fetch'
```

输出末尾：

```text
4843 passed, 9 skipped, 6 deselected, 28 warnings in 120.51s (0:02:00)
```

没有修改测试输入、断言或增加跳过标记。9项跳过均由既有测试决定，新增95项没有跳过；28条为既有slowapi依赖的弃用提示。

### depth 1 浅克隆

使用 `git clone --depth 1 file://<当前工作树> <临时目录>/repo`；文件协议只读取本地仓库，没有联网。由于禁止 commit，将相同的未提交改动与新增文件复制进浅克隆后测试；没有创建临时提交。验证 `git rev-parse --is-shallow-repository` 为 `true`，`git rev-list --count HEAD` 为 `1`。这些 git 命令仅属于验收流程，测试自身不使用 git。

```bash
# cwd: <浅克隆>/backend
$PY -m pytest -q tests/test_novel_p1_*.py
```

输出末尾：

```text
95 passed, 28 warnings in 6.65s
```

### 范围/格式

`git diff --check` 通过。范围审计通过，共31个任务文件，全部处于§1授权范围（任务开始时已存在的未跟踪02-spec.md另计）。既有测试零修改；database.py、main.py、rate_limit.py与六份文档共9个受保护文件的diff均无删除行，因此local watch已有内容没有改动或移动。

## 6. D1 价格折算与文档同步

按 `官方每百万token人民币价 × 100草莓/元 × 1.5 ÷ 1000` 得每千 token 草莓；美元先按 7.2 换算人民币，各方向向上取到 0.01。

| 模型 | 输入草莓/千token | 输出草莓/千token |
|---|---:|---:|
| dashscope:qwen3.8-max | 1.80 | 5.40 |
| deepseek:deepseek-flash | 0.33 | 1.30 |
| ark:doubao-seed-2-1-pro-260915 | 0.90 | 4.50 |
| byok:self | 0 | 0 |

价格来源使用规格第13节给出的最终数值，未联网核价。默认开关关闭、空名单无人可用。六份文档分别补入 API、环境变量、SQLite 五表和数据流：思路、圣经、正文及留言会发送给所选阿里云百炼、DeepSeek、火山方舟或 BYOK 厂商（含 Anthropic）。CLAUDE 新增「小说工坊」小节；未改原有 local watch 段落。

## 7. 未完成与人工确认

1. 上下文极限约束需要作者确认验收口径。实现严格保留锁定区、全部 open 伏笔、主角全部状态及历史卷摘要；代表性60章样例四类上下文均少于2万字符，30/60差不超过10%。另有极限保留测试：每卷600字、主角知识每章累积、合法最长正文/修订稿，四类实际输入约1.3–2.1万字符，30/60增长约14%–21%。这些必须完整保留的内容可以增长，因此无法同时承诺“任意内容固定上界或增长≤10%”。已向作者提供“优先保留事实并明示边界”与“允许进一步压缩累计事实”两种口径；未授权前不丢弃或截断这些事实。字符数不等同厂商token数，约2万token目标仅能作成本目标，不能作任意输入的数学保证。
2. 依规格全部测试离线。平台千问/豆包担任主编的真实质量、厂商服务可达性、真实usage/缓存计费及BYOK端到端质量未使用真实Key核验，需作者另行验收。
3. 六项既有测试在当前沙箱不允许绑定回环端口；原命令结果和排除这六项的完整回归均保留在上方。没有更改它们的输入、断言或跳过行为。
4. P2前端、生产开关开启和真实提供方试跑不属于本阶段；本次没有执行。


## 第 1 轮返修

依据 `05-fix-r1.md` 的 F1–F7、O1/O2，以及 `04-review-a.md`、`04-review-b.md` 的证据实施。上一轮测试覆盖了顺序计费路径，未覆盖取消跨越提交的窗口，资金安全结论不足；本轮以事务取消、混沌守恒和重复结算回归补齐。此节记录返修后的实现，并覆盖此前关于人物卡不裁剪、知识全部下发及80%边界的旧描述。

### 本轮修改文件

共16个文件，未修改 `database.py`、`main.py`、`rate_limit.py`、原有 local watch 内容、规格及复核文档。

- 资金：`backend/novel/billing.py`、`backend/novel/llm_router.py`、`backend/novel/store_db.py`。
- 状态与BYOK：`backend/novel/service.py`、`backend/novel/runner.py`、`backend/novel/byok_bridge.py`。
- 上下文：`backend/novel/context.py`、`backend/novel/deliberation.py`、`backend/novel/writing.py`。
- P1测试：`backend/tests/test_novel_p1_billing.py`、`test_novel_p1_api.py`、`test_novel_p1_runner.py`、`test_novel_p1_byok.py`、`test_novel_p1_context.py`。
- 新增正式混沌测试：`backend/tests/test_novel_p1_chaos.py`。
- 本报告只追加此节。P0/既有非P1测试的输入与断言未改；P1上下文断言按F5新的裁剪规则更新，其余回归主要以追加测试实现。

### F1–F7、O1/O2逐条落实

| 项 | 实现 | 正式测试 |
|---|---|---|
| F1 原子预扣/退款/提交防取消 | `NovelBilling._reserve_transaction` 在同一连接的 `BEGIN IMMEDIATE` 内执行现有 `database._apply_daily_refill`、条件扣用户余额、写步骤reserved、增加书reserved。未修改 `database.reserve_strawberries`。`_finish_transaction` 和 `_refund_reserved_transaction` 同事务修改用户/书/步骤。`_drain` shield整个短数据库事务并等待连接清理完成，才响应取消；预扣已提交时按持久reserved行幂等退款，不做无凭据余额补偿。 | billing：`test_reserve_statement_failure_rolls_back_refill_balance_and_book`、`test_novel_reservation_reuses_existing_daily_refill_semantics`、`test_cancel_inside_reserve_transaction_preserves_conservation`、`test_cancel_after_reserve_commit_drains_then_refunds_once`、`test_settle_and_refund_commit_cancellation_drain_atomic_ledger`；chaos三种子×20轮。 |
| F2 结算与成功缓存同事务 | 响应先经既有解析/schema校验，`LLMRouter._complete_response` 只保护拿到响应后的短验证/持久化阶段，网络等待仍可取消。有效平台结果由 `settle(..., step_record=...)` 在结算事务中调用 `DbStepStore.write_step_on_connection` 写ok/raw/result/usage；费用和成功缓存一起提交或回滚。校验失败的真实attempt仍收费；没有完整usage则退款。P0及测试计量器保留原接口兼容。 | billing：`test_cancel_between_settlement_and_step_ok_never_recharges`（before_ok、after_ok、after_settle × 有/无前置坏JSON，共6例），断言续跑fake调用数不增、余额及charged不再变化；`test_step_ok_statement_failure_rolls_back_settlement_before_refund` 验证ok写入失败整体回滚。 |
| F3 最新章改稿竞态 | 启动claim至TASKS登记、设置改稿标记共用逐书操作锁。改稿设置标记后先取消并等待worker停止，再在写事务内重读chapters_done判断最新章；若worker已提交N+1，则改N按早期章节处理，仅标后续正文stale，保留N+1归档。编辑期间激活与启动被拦截，避免resume/continue重新拉起；仍为running的书在编辑操作结束后恢复正常调度。 | runner：`test_edit_rechecks_latest_after_worker_commits_while_cancel_drains`、`test_edit_waits_for_claimed_worker_to_be_registered_before_cancelling`（精确claim提交到登记窗口）、`test_edit_blocks_activation_until_worker_has_drained`（resume/continue）。 |
| F4 早期改稿与待批细纲 | stale仅标已有正文的后续章节，并排除planning/awaiting_plan_approval。approve/redo找不到合法待批行时返回中文409，避免None解引用500。 | api：`test_early_edit_keeps_pending_plan_usable_and_missing_plan_is_409`，approve与redo各一例，覆盖改早章后仍可用，以及缺行409。 |
| F5 配角卡片/knows漏裁 | 所有四类输入统一来自trim后的locked和dynamic：保留全部主要人物、近3章出场配角、本章细纲点名配角；每个人物knows仅下发最近30条。critique初案后按点名人物重建顾问与定稿简报，卷摘要输入也裁卡。完整圣经不改，档案员ID校验和应用增量仍用完整圣经。 | context：`test_sixty_chapter_context_views_stay_bounded_and_preserve_open_ledger`（实际引擎fake连跑60章）、`test_supporting_cards_and_states_use_recent_appearances_or_explicit_current_beat`、`test_plan_named_card_reaches_all_inputs_and_archive_validation_uses_full_bible`、`test_full_length_arcs_are_retained_and_knowledge_is_bounded_in_actual_messages`。 |
| F6 BYOK失效可恢复 | `ByokUnavailable` 固定中文异常映射到paused/byok_unavailable，中文原因存 `_last_error` 并在详情顶层 `last_error` 返回；重填/服务不可用异常也转换固定文案，不回显原异常。重新启用后resume续跑。PATCH允许完整agents映射，仅paused/awaiting_*可改，并复用§8全部角色/型号校验；可切平台模型后继续。成功激活清除旧last_error。 | runner：`test_byok_disabled_mid_run_pauses_and_reenabled_resume_reuses_steps`（重新启用/切平台两例）；byok：`test_internal_byok_store_failures_become_fixed_recoverable_messages`（重填/服务不可用）；api：`test_patch_agents_requires_pause_or_gate_and_validates_selection`。 |
| F7 BYOK明确文案 | describe不再吞掉校验异常。未启用：「请先启用可用的自带模型」；厂商不支持：「小说工坊仅支持自带 Anthropic、千问或 DeepSeek」；未知型号：「该模型暂不支持用于小说工坊」。建书/估算422，运行期按F6暂停，catalog仍安全捕获不可用状态。 | api：`test_byok_create_preserves_the_specific_unavailability_reason` 三种精确detail断言；byok既有厂商/型号拒绝测试保持。 |
| O1 精确80%边界 | 按返修单「达到80%暂停」采用 `spent + reserved + 本次预扣上界 >= budget × 0.8`。包括在途预扣，按上界判断，可能早于实际spent达到80%时暂停。此处>=以返修单为准。 | billing：`test_budget_exact_79_and_80_percent_boundary`，budget=10000，精确构造预扣7900放行/8000拒绝；内存变异改为×1.0后80%例必失败，79%例仍通过。 |
| O2 同用户第二书冲突 | 所有激活路径检查同用户其他running/setup_running书，resume明确在激活前检查；仍在同一SQLite写事务中判断。 | api：`test_same_user_running_book_blocks_another_create_and_resume`，已有运行书时另建书、resume另一本均409中文原因。 |

### 混沌守恒正式测试

`test_novel_p1_chaos.py` 完全在仓库内构造场景，不读取复核scratchpad、仓库外输入或git历史。通过运行器路由工厂注入FakeLLM响应，但用DEV_MODE=0走真实计费代码；关闭每日补给以单独核对资金。三位顾问用屏障确保实际并行；混合网络异常、坏JSON、缺usage，以及随机pause、cancel_novel和直接任务取消。每个固定种子7/11/23各20轮，每轮停止并排空任务、幂等退完预留后检查：

```text
初始余额 - 当前余额 == sum(该用户各书spent) == sum(各步骤strawberries_charged)
每本书reserved == 0
所有billing_status=reserved步骤的预扣合计 == 0
```

并断言三种故障全部实际命中、三种停止方式全部执行、并行峰值至少3。一次正式运行的输出：

```text
CONSERVATION seed=7 rounds=20 PASS balance_delta=166 spent=166 charged=166 reserved=0 peak_parallel=3 faults={'missing_usage': 14, 'network': 9, 'bad_json': 5}
CONSERVATION seed=11 rounds=20 PASS balance_delta=196 spent=196 charged=196 reserved=0 peak_parallel=3 faults={'network': 11, 'bad_json': 8, 'missing_usage': 14}
CONSERVATION seed=23 rounds=20 PASS balance_delta=186 spent=186 charged=186 reserved=0 peak_parallel=3 faults={'missing_usage': 15, 'network': 11, 'bad_json': 8}
3 passed in 5.74s
```

### 验证命令和输出末尾

解释器仍固定为 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`，以下`$PY`指这个完整路径；全部命令在相应检出的backend/下执行。全程离线、不读真实密钥、不运行真实提供方、不增加依赖、不提交commit。

```bash
$PY -m pytest -q -s tests/test_novel_p1_chaos.py
# 3 passed in 5.74s；三个种子各20轮PASS，详见上方守恒行。

$PY -m pytest -q tests/test_novel_p1_billing.py tests/test_novel_p1_store.py
# 52 passed in 2.39s

$PY -m pytest -q tests/test_novel_p1_runner.py tests/test_novel_p1_api.py tests/test_novel_p1_byok.py
# 60 passed, 28 warnings in 5.71s

$PY -m pytest -q tests/test_novel_p1_context.py tests/test_novel_state.py tests/test_novel_r1_pilot_report.py
# 58 passed in 1.48s

$PY -m pytest -q tests/test_novel_*.py
# 1027 passed, 28 warnings in 15.49s
```

O1变异只修改内存中的预算阈值，不改仓库源码或测试断言；对相同79/80正式测试运行：

```text
FAILED ...::test_budget_exact_79_and_80_percent_boundary[80]
1 failed, 1 passed in 0.97s
O1 MUTATION KILLED: 79% passes; exact 80% assertion fails with threshold *1.0
```

完整回归原命令：

```bash
$PY -m pytest -q
```

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 4881 passed, 9 skipped, 28 warnings, 5 errors in 141.62s (0:02:21)
```

六项均为既有测试绑定127.0.0.1被当前沙箱拒绝（PermissionError），依原规格不计入新增失败；无其他失败。

按原规格排除当前沙箱无法绑定回环端口的六项，完整回归命令：

```bash
$PY -m pytest -q -k 'not test_stop_disconnects_async_upstream_and_releases_user_slot and not test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive and not test_drip_response_obeys_total_wall_clock_deadline and not test_fast_response_and_redirect_still_work and not test_drip_headers_obey_total_wall_clock_deadline and not test_four_stuck_resolutions_do_not_block_another_fetch'
```

```text
4881 passed, 9 skipped, 6 deselected, 28 warnings in 141.63s (0:02:21)
```

当前沙箱下9项跳过均来自既有测试；本轮P1测试133项无跳过。与复核环境的4855 passed/3 skipped相比，本轮增加38个正式用例；此环境另有6项既有测试跳过及上述6项端口限制，故通过数为4881。28条警告来自既有slowapi依赖。

附加本地浅克隆验证：`git clone --depth 1 file://<工作树> <临时目录>/repo`，将当前未提交改动覆盖进去（不创建临时commit），确认is-shallow=true、HEAD提交数=1；在浅克隆backend/执行同一固定解释器 `-m pytest -q tests/test_novel_p1_*.py`。测试自身不使用git或读取外部探针。

```text
133 passed, 28 warnings in 15.11s
```

范围检查：`git diff --check`通过；`git diff 820fff1 -- database.py main.py rate_limit.py`及六份文档没有删除/移动任何既有行；受保护九文件仍为原P1仅新增行（13/0、6/0、2/0及各文档新增行），本轮未触及它们。既有非P1测试零改动。P0冻结测试未经修改，四份配置均退出0、步骤键和正文SHA-256保持不变。

### 上下文实测与待确认事项

60章成长场景每章新增知识、每4章新增配角、种植/回收伏笔，对比时open固定6条；最终正典保留16张人物卡、主角61条知识。第30/60章四种实际调用输入为：

| 输入 | 第30章字符 | 第60章字符 | 增长 |
|---|---:|---:|---:|
| 简报/plan | 7722 | 7893 | 2.21% |
| writer | 8189 | 8300 | 1.36% |
| review | 8360 | 8488 | 1.53% |
| archive | 8355 | 8483 | 1.53% |

配角卡片与knows无限增长已修复，F5验收样例均≤10%，open一条不丢。仍保留上一轮已提的独立边界：若每个历史卷摘要均取允许的600字上限，累计卷摘要本身会增长；四类输入30→60分别为12541→14723（17.40%）、17844→19976（11.95%）、18306→20438（11.65%）、18320→20452（11.64%）。未私自删除或截断这些卷摘要；若作者要求此极端场景也严格≤10%，仍需确认更早卷摘要的二次合并策略。此边界不再归因为卡片或知识漏裁。

F1–F7、O1/O2均已落实，无其他返修遗留。真实厂商质量、可达性和真实Key试跑仍按原任务留给作者，本轮没有执行。复核A/B其余「可优化」建议未扩展为本轮额外改动。

## 第 2 轮返修（冒烟）

依据 `05-fix-r2.md` 修复 G1/G2。原真实冒烟的计费、暂停与账目已由返修单确认正确；本轮只完善回应 ID 的报错与主编输入，不改计费、暂停、schema 接受规则或 P0 步骤流程。两名子代理按文件分工实施，另由一名子代理只读复核，通过后统一回归。

### 修改文件与逐条落实

| 条目 | 修改文件 | 实现与对应测试 |
|---|---|---|
| G1 具体 ID 报错 | `backend/novel/schemas.py`；新增 `backend/tests/test_novel_r2_response_errors.py` | `_responses` 保留原总述并放在该回应字段错误的最前面，分别追加「缺少」「多出」「重复」及具体 ID；详情按 O/A/N 和编号稳定显示。仅显示形如 O/A/N 加数字、长度不超过32的 ID，不回显回应内容或伪装成 ID 的正文。原有校验条件不变，显示过滤不限制原本可接受的 ID。30项测试覆盖意见与留言的三类错误、混合错误、内容不回显、异常类型和长 ID，以及真正经过 `LLMRouter` 的修正重试：第二次收到具体错误并成功，缓存 attempts=2、status=ok。 |
| G2 按序待回应清单 | `backend/novel/deliberation.py`、`backend/novel/agent_pool.py`、`backend/novel/runner.py`；新增 `backend/tests/test_novel_r2_required_responses.py` | 共用纯函数构造 `required_response_ids`，先 O、再 A、最后 N，组内保留代码分配顺序。critique finalize、merge decision、solo decision 及三种 redo 均下发该字段；plan 同步下发当前 N 清单，使其共用提示自洽。默认、plan、finalize 三张主编卡片均加入返修单原句。10项测试覆盖12个 O、2个 A、N1/N2/N10、顾问乱序完成、三种模式与 redo；故意逆序输出全部合法回应仍校验成功，证明未新增顺序校验。 |
| G2 允许的冻结期望调整 | `backend/tests/test_novel_r1_pilot_report.py`、`backend/tests/test_novel_r1_workflow.py` | 下列两处只在 decision payload 的期望键集合中追加 `required_response_ids`，保留精确集合相等断言。 |
| 报告 | `docs/tasks/2026-10-15-novel-workshop-p1/03-report.md` | 仅在原报告末尾追加本节。 |

三张主编卡片增加的原句为：

> `objection_responses` 必须按 `required_response_ids` 中 O 与 A 的顺序逐条回应，条数与清单一致；`user_note_responses` 按其中 N 的顺序回应。

按 G2「只允许为这个新字段做相应调整」的明确例外，既有测试改动逐条列出：

1. `test_novel_r1_pilot_report.py::test_r1_meetings_and_execution_inputs_have_no_duplicate_outer_context`：`stages["decision"]` 期望集合仅增加 `"required_response_ids"`。
2. `test_novel_r1_workflow.py::test_deliberation_payload_has_one_brief_and_only_phase_fields[decision-extras2]`：decision 参数的期望集合仅增加同一字段。

其余既有测试输入与断言不变，`test_novel_p1_p0.py` 的冻结步骤键及正文 SHA-256 基准未修改。两处例外所在测试文件单独回归为 `58 passed in 1.34s`。

### 验证命令与输出末尾

以下命令均在 `backend/` 下执行，`PY` 固定为指定解释器；新增测试只使用仓库内代码、构造数据及本次测试生成的临时产物，不读取仓库外预存输入、复核探针或 git 历史。所有模型响应使用 fake，未联网、未读密钥、未运行真实提供方、未增加依赖、未提交 commit。

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
$PY -m pytest -q tests/test_novel_*.py
```

```text
1067 passed, 28 warnings in 18.02s
```

本轮增加40项正式测试；小说回归包含未修改的 `test_four_frozen_p0_runs`，A/A2/B/C 四份 dry-run 均退出0，步骤键和正文 SHA-256 与冻结基准一致。

单独复跑新增用例和四份 P0 冻结 dry-run：

```bash
$PY -m pytest -q tests/test_novel_r2_response_errors.py tests/test_novel_r2_required_responses.py tests/test_novel_p1_p0.py
```

```text
41 passed in 1.10s
```

全量原命令：

```bash
$PY -m pytest -q
```

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 4921 passed, 9 skipped, 28 warnings, 5 errors in 135.64s (0:02:15)
```

上述六项与第1轮相同，均在绑定 `127.0.0.1` 时被当前沙箱以 `PermissionError: [Errno 1] Operation not permitted` 拒绝，没有新增失败。按原规格排除这六项后执行全量：

```bash
$PY -m pytest -q -k 'not test_stop_disconnects_async_upstream_and_releases_user_slot and not test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive and not test_drip_response_obeys_total_wall_clock_deadline and not test_fast_response_and_redirect_still_work and not test_drip_headers_obey_total_wall_clock_deadline and not test_four_stuck_resolutions_do_not_block_another_fetch'
```

```text
4921 passed, 9 skipped, 6 deselected, 28 warnings in 135.63s (0:02:15)
```

相对第1轮本环境的4881通过，增加40项通过；与返修单独立复核环境的4893通过、3跳过相比，差额仍是本环境额外6项既有跳过和上述6项回环绑定限制。28条警告来自既有 slowapi 依赖。

### 范围检查与待确认事项

`git diff --check` 通过。以本轮开始时的文件摘要核对，本轮只改4个小说源码文件、2处明确获准的旧测试期望和本报告，新增2个 `test_novel_r2_*.py` 文件。`database.py`、`main.py`、`rate_limit.py` 与既有文档中的本机监控内容本轮均未改；本报告原有字节完整保留，只追加本节。

G1/G2 无实现遗留。依本轮离线红线，没有再次调用千问或其他真实提供方；真实千问冒烟是否不再触发该质量问题，留待作者后续实际复测。当前沙箱不能完成上述六项端口绑定测试的成功验证，其余全量已通过。

## 第 3 轮返修（冒烟复测）

依据 `05-fix-r3.md` 实现 H1：critique 定稿用独立的 `alternative_responses` 回应替代走向，同时继续接受旧的 A* 混合回应。三名子代理按源码与测试文件互不重叠分工，其中一名完成报告/API工作后只读复核其他改动；主代理负责 fake、整体验证与本节。全程离线，不读取密钥、不调用真实提供方、不增加依赖、不提交 commit。

### 修改文件

- 源码6份：`backend/novel/schemas.py`、`deliberation.py`、`agent_pool.py`、`runner.py`、`fake_llm.py`、`report.py`。
- 新增测试4份：`backend/tests/test_novel_r3_alternative_schema.py`、`test_novel_r3_alternative_payloads.py`、`test_novel_r3_alternative_fake.py`、`test_novel_r3_alternative_records.py`，共83项。
- 必要调整既有测试3份：`backend/tests/test_novel_r2_required_responses.py`、`test_novel_r5_deliberation.py`、`test_novel_r5_pilot_report.py`，具体位置与理由逐条列于下方。
- 文档：仅在本 `03-report.md` 末尾追加本节。

### H1 逐条对应

| 返修单条目 | 落实方式与对应验证 |
|---|---|
| H1.1 新输出字段 | finalize 提示新增 `alternative_responses: [{alternative_id, decision, response}]`；`decision` 只接受 adopt/partial/reject，理由必须非空。schema测试覆盖三种合法值及非法枚举、空白/非字符串理由、缺字段与错误容器类型。 |
| H1.2 新旧兼容、联合计数 | `validate_decision` 增可选 `alternative_ids=()`；旧调用把 A 混在 objection_ids 中时仍能识别。每个 A 可在任一回应字段中出现，联合计数恰好一次；跨字段重复失败，未下发 A9/A10 跨字段出现也明确报「多出」和「重复」。O/N 错放新字段不抵消原字段缺少。无 A 时新字段允许缺失或 []。旧输出不强制迁移，新输出保留独立字段；G1现有30项诊断测试未改且通过，错误继续只列安全 ID，不回显内容。 |
| H1.3 输入与提示 | finalize 的 objection_ids 只含 O，alternative_ids 只含 A；required_response_ids 仅 O 后 N，均保持代码分配顺序。原 meeting.objections 混合记录保留以兼容历史数据。runner 的 critique redo 也拆分列表；三张主编卡片去掉过时的 O/A 混合清单说法，finalize 明确三个回应字段、采纳决定与理由。payload测试覆盖未压缩/压缩输入、顾问逆序完成、旧记录 redo、无替代走向，以及 O10/N10 不被字典序重排。 |
| H1.4 merge/solo | 不增加 alternative_ids 或 alternative_responses，保持原 decision 结构。fake 仅在 finalize 输入含 alternative_ids 时输出新格式，无此字段的旧 finalize 请求继续生成旧格式。新测试对 merge/solo 的精确 payload 键集合与输出无新增字段作断言。 |
| H1.5 报告与接口 | report.py 按 A ID 展示采纳/部分采纳/不采纳及理由，同时兼容旧回应和新旧混合。章节接口原本完整反序列化 meeting_json，无需改 service.py 或路由；正式离线 HTTP 测试验证引擎实际生成、写正文、归档、落库后 GET 与 DB 完全一致。逐章审批额外验证待批 A 新字段已落库，作者改细纲后 plan/approve 200，归档后决定和理由保留。 |
| H1.6 冒烟形状回归 | 在仓库内构造同样的9条 O 回应，先断言缺少 A1、A2、A3，再只追加3条独立 alternative_responses 通过校验，9条原 O 回应逐字不变；不读取真实冒烟产物或仓库外输入。其他测试覆盖全新、全旧、混合格式、具体缺少/多出/重复、无 A、决定枚举和内容不回显。 |

只读复核发现的「未知 A 跨字段重复未明确列入重复」诊断边界已补齐，并新增 A9/A10 回归；错放 N 不抵消缺留言也有正式测试。实现继续复用 P0 推演、写作、归档与运行器，未复制第二套逻辑。

### 既有测试必要调整清单

以下仅因 H1 将 A 移到新字段、required 清单排除 A 而调整；原有任务参数、顾问意见、故事输入、流程键与失败断言保持。没有放宽成子集或忽略 A：

1. `test_novel_r2_required_responses.py::test_three_editor_cards_include_the_exact_response_order_instruction`：共用精确提示期望由 O/A 混合清单改为仅 O，条数对应 O 清单；旧文案与 H1 明确冲突。
2. 同文件 `test_response_checklist_groups_prefixes_without_sorting_or_mutating_assigned_ids`：期望列表移除 A，仍逐项验证 O/N 顺序和输入不变。
3. 同文件 `test_finalize_checklist_follows_assignment_after_out_of_order_advisor_completion`：required 与 objection_ids 期望移除 A，新增 alternative_ids 与独立 A 回应的精确期望；共用逆序输出辅助函数也逆转新字段，以继续证明回应顺序仅是提示要求。
4. 同文件 `test_redo_editor_uses_the_same_checklist_for_finalize_and_decision`：required 期望不再包含 A；critique redo 精确验证独立 A 清单，其他模式明确没有 alternative_ids；原三种模式输入、步骤键和会议不变断言保留。
5. `test_novel_r5_deliberation.py::test_critique_runs_plan_then_parallel_advisors_then_finalize`：原单字段覆盖全部 O/A 的期望，改为两个回应字段各自精确覆盖对应 O 或 A，保持所有流程和并发断言。
6. 同文件 `test_whitespace_only_optional_alternative_does_not_get_an_a_id`：同样拆开 O/A 回应期望；空白替代走向不分配 ID、唯一 A1 作者等原断言不变。
7. 同文件 `test_finalize_requires_exactly_one_response_to_every_objection_and_alternative`：A 的缺失/重复故障注入随结构迁移到 alternative_responses/alternative_id；仍删除或复制同一条已生成回应，保留原有 O/A × missing/duplicate 参数和「恰好回应一次」失败断言。旧数组中已无 A，继续从旧数组找 A 只会触发 StopIteration，不能检验原目标。
8. `test_novel_r5_pilot_report.py::test_a2_five_chapters_use_plan_consultants_finalize_and_keep_solo`：原单数组 ID 集合等于全部 O/A，改为新旧两数组 ID 并集精确等于同一全集；其余五章流程、solo、盲稿等期望不变。

其余既有测试输入与断言本轮未改。特别是 `test_novel_r5_cards_fake.py` 的旧输入及回应断言、`test_novel_r2_response_errors.py` 的精确诊断断言、`test_novel_p1_p0.py` 四份冻结 dry-run 的步骤键和正文 SHA-256 基准均未改。

### 验证命令与输出末尾

全部命令在 `backend/` 下执行，解释器固定：

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
```

新增 schema 与既有 G1/schema 回归：

```bash
$PY -m pytest -q tests/test_novel_r3_alternative_schema.py tests/test_novel_r2_response_errors.py tests/test_novel_schemas.py tests/test_novel_r1_schemas.py
```

```text
278 passed in 0.39s
```

新增 fake 与四份未修改的 P0 冻结 dry-run：

```bash
$PY -m pytest -q tests/test_novel_r3_alternative_fake.py tests/test_novel_p1_p0.py
```

```text
8 passed in 1.05s
```

A/A2/B/C 均退出0，原步骤键和正文 SHA-256 不变。另有正式测试验证 critique 默认 dry-run 的 finalize 步骤 result 与 chapter_record.decision 完全一致，均包含新 alternative_responses，生成的 report.md 展示决定与理由，solo 不新增该字段。

最终全部小说测试：

```bash
$PY -m pytest -q tests/test_novel_*.py
```

```text
1150 passed, 28 warnings in 16.44s
```

全量原命令：

```bash
$PY -m pytest -q
```

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 5004 passed, 9 skipped, 28 warnings, 5 errors in 138.92s (0:02:18)
```

这六项仍与前两轮相同：当前沙箱禁止绑定 `127.0.0.1`，报 `PermissionError: [Errno 1] Operation not permitted`；没有新增失败。按原规格排除同六项后的全量命令与输出末尾：

```bash
$PY -m pytest -q -k 'not test_stop_disconnects_async_upstream_and_releases_user_slot and not test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive and not test_drip_response_obeys_total_wall_clock_deadline and not test_fast_response_and_redirect_still_work and not test_drip_headers_obey_total_wall_clock_deadline and not test_four_stuck_resolutions_do_not_block_another_fetch'
```

```text
5004 passed, 9 skipped, 6 deselected, 28 warnings in 138.87s (0:02:18)
```

相对本单4921通过基线，新增83项全部通过；9项既有跳过与28条既有 slowapi 警告均未增加。正式全量结果使用补齐诊断边界和逐章审批测试之后的最终代码；此前为补修而中止的回归不作为验收结果。

### 范围检查与待确认事项

`git diff --check` 通过。以本轮开始时的文件摘要核对，共14个文件变化，严格限定于上述6份小说源码、4份新测试、3份列明的旧测试和本报告。`database.py`、`main.py`、`rate_limit.py` 及既有文档本机监控内容本轮均未改。本报告原有字节完整保留，仅追加本节；测试不读仓库外预存文件或 git 历史。

H1 无实现遗留。真实千问复测未执行，依本轮不联网、不读密钥的红线留待作者后续实际验证；当前沙箱的六项端口绑定用例仍需在允许绑定的环境验证。没有其他待人工确认事项。
