# 内测后端阻断修复报告

日期：2026-09-23

## 修改文件

- 计费、补给和邀请码事务：`backend/database.py`、`backend/routers/chat.py`、`backend/routers/auth.py`、`backend/services/chat_service.py`、`backend/tools/fetch_card.py`、`backend/tools/travel_plan.py`、`backend/tools/web_search.py`、`backend/tests/test_beta_billing.py`、`backend/tests/test_chat_upstream_errors.py`、`backend/tests/test_spec_bugfixes.py`。
- 管理脚本：`backend/admin_env.py`、`backend/seed_invites.py`、`backend/manage_invites.py`、`backend/manage_strawberries.py`、`backend/tests/test_beta_admin_scripts.py`。
- 安全与分身交流：`backend/safety.py`、`backend/persona.py`、`backend/services/exchange_service.py`、`backend/exchange_workflow.py`、`backend/tests/test_beta_safety.py`。
- 测试隔离：`backend/tests/conftest.py`、`backend/trace.py`、`backend/conversation_matcher.py`、`backend/main.py`、`backend/scripts/fix_matches.py`、`backend/tests/test_beta_test_isolation.py`。
- 文档：`backend/.env.example`、`README.md`、`PLAN.md`、`CLAUDE.md`、`docs/DEPLOYMENT.md`、`docs/ARCHITECTURE.md`、`docs/CYBER_AVATAR_PLATFORM.md`、本报告。

## T1–T6 对应关系

### T1 草莓原子预扣与按交付结算

统一使用 `STRAWBERRY_COST_PER_REPLY = 10`。余额判断与预扣由单条条件 `UPDATE ... RETURNING` 完成；未交付时退款。普通/镜子/看图回复须非空且落库，生成图须保存，真实工具须返回结构化成功，才标记 `billable`。失败、占位工具、缺参追问、未知意图、会话删除及异常均不结算。`build_context` 出错、流提前关闭/取消、ASGI 在生成器启动前失败都会退还预扣；`DEV_MODE=1` 跳过预扣与结算。模型成功回复后的统计异常不会在 `done` 后追加错误事件。

新增测试：`test_parallel_chat_only_one_reservation_reaches_model`、`test_five_strawberries_cannot_buy_ten_strawberry_reply`、`test_tool_delivery_settlement`（参数化）、`test_model_error_refunds_reservation`、`test_post_delivery_accounting_error_does_not_follow_done_with_error`、`test_context_error_refunds_before_stream`、`test_early_stream_aclose_refunds_reservation`、`test_asgi_failure_before_generator_start_refunds_reservation`、`test_unstructured_tool_model_reply_is_explicitly_non_billable`（参数化）、`test_fetch_card_summary_failure_has_structured_error`。两处旧测试的扣费断言已按预扣/退款语义更新。

### T2 草莓补充路径

新增 `STRAWBERRY_DAILY_REFILL`，非法或超 SQLite 整数范围的值按 0 处理并打印不含原值的警告。新增可空列 `users.strawberry_refill_date`。按 Asia/Shanghai 自然日首次读取余额或预扣时，在写事务中把余额提升到设定下限，同日不重复且不降低高余额；时区不可用时回退 UTC+8。登录余额、`GET /strawberry` 和管理脚本读取均应用补给；`routers/me.py` 原本已调用统一余额函数，因此无需改动。新增 `manage_strawberries.py list/grant/set`，余额不足的 SSE 文案改为联系管理员，不再引导充值。

新增测试：`test_daily_refill_crosses_shanghai_day_once_without_lowering_balance`、`test_refill_changes_balance_endpoint_and_login_response`、`test_refill_enabled_insufficient_balance_message`、`test_refill_and_concurrent_reservation_share_atomic_transaction`、`test_invalid_refill_is_disabled_without_exposing_value`、`test_out_of_range_refill_is_disabled`、`test_manage_strawberries_grant_set_list_and_missing_user`、`test_manage_strawberries_list_applies_cross_day_refill`、`test_manage_strawberries_grant_and_set_apply_refill_before_change`、`test_manage_strawberries_rejects_invalid_amounts`（参数化）。管理列表对未补给过的日期显示 `-`。

### T3 管理脚本连库与邀请码避撞

三个管理脚本在导入 `database` 前按 `--env-file`、`FIONA_ENV_FILE`、可读的 `/etc/fiona/fiona.env`、`backend/.env` 的顺序加载配置，保留进程显式环境变量的优先级；stderr 显示配置文件与数据库绝对路径。数据库不存在时退出码 2，只有明确 `--init-db` 才建库。`create_tester_invites` 在同一个 `BEGIN IMMEDIATE` 中查看两表最大 `testerNN` 编号、逐名避撞并插入；发码脚本仅输出本次新码及总量统计。`manage_invites.py` 的 list/revoke/rotate 保持原有功能。

新增测试：`test_tester_invites_skip_existing_account_and_invite_names`、`test_admin_scripts_refuse_missing_database_without_init`（参数化）、`test_seed_invites_uses_deletion_safe_names_and_lists_only_new_codes`、`test_seed_invites_parallel_runs_allocate_unique_usernames`、`test_admin_env_precedence_and_process_override`、`test_manage_invites_preserves_rotate_and_revoke`、`test_seed_invites_rejects_count_outside_one_to_two_hundred`（参数化）。

### T4 危机与提示词安全底线

新增中英文危机短语识别、最高优先级 `CRISIS_GUIDANCE` 和固定 `CRISIS_RESOURCE_NOTE`。危机轮跳过镜子、工具与待补参数，不清除既有待补状态；有普通图片时走看图，否则走普通回复。模型失败也先发送资源文案再发送错误；落库的助手内容包含资源文案。低余额危机轮（含 DEV 模式）直接返回资源且不调用模型，不计费。非危机私聊在最终装配处把 `BASE_SAFETY_RULES` 恰好一次放到 system prompt 末尾，镜子与硬词附录位于其前；危机轮则以 `CRISIS_GUIDANCE` 收尾。真人、官方、总结、主创、审稿及修订的每条交流 system 消息都附基础安全规则。`mode_switcher.py` 的镜子附录无需直接修改，由私聊最终装配处理顺序。

新增测试：`test_crisis_detector_recognizes_required_phrases`（11 例）、`test_crisis_detector_rejects_required_everyday_phrases`（11 例）、`test_crisis_detector_normalizes_case_and_whitespace`、`test_persona_growth_stages_end_with_one_safety_block`（参数化）、`test_custom_persona_ends_with_one_safety_block`、`test_exchange_every_system_path_ends_with_safety`（9 路径）、`test_exchange_provider_payment_error_directs_user_to_platform_admin`、`test_crisis_chat_final_guidance_resource_persistence_and_no_charge`、`test_crisis_chat_provider_error_still_sends_resources_before_error`、`test_crisis_chat_bypasses_existing_mirror_mode`、`test_zero_balance_crisis_returns_resources_without_model`、`test_zero_balance_crisis_skips_model_in_dev_mode`、`test_crisis_with_image_uses_vision_branch_and_keeps_final_guidance`、`test_non_crisis_chat_every_reply_prompt_ends_with_one_safety_block`（参数化）。

### T5 测试隔离

`conftest.py` 在后端模块导入前强制设置会话临时 `FIONA_DB_PATH` 与 `FIONA_UPLOADS_DIR`，保留逐用例数据库打桩。`trace.py`、`conversation_matcher.py` 与维护脚本在调用时读取当前 `database.DB_PATH`；`main.py` 不再导入上传目录值的副本。

新增测试：`test_import_time_paths_use_session_temporary_directory`、`test_trace_uses_current_database_path`。

### T6 文档同步

已同步草莓价格与补给、管理脚本参数及连库顺序、邀请码编号规则、危机分流、交流安全底线、迁移列和测试隔离；`PLAN.md` 把草莓并发扣减改为已完成，持久化成本控制继续暂缓。T6 由文档差异检查和全库旧陈述搜索验收，无新增单测。

## 测试与验收结果

在 `backend/` 下执行：

| 命令或检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q` | **920 passed，0 failed**，13 条依赖弃用警告 |
| `for test_file in tests/test_*.py; do .venv/bin/python -m pytest -q "$test_file"; done` | **42 个文件分别通过，合计 920 passed** |
| `.venv/bin/python -m compileall -q -x '\.venv' .` | 退出码 0 |
| `grep -rn "请充值" --include='*.py' . \| grep -v '\.venv'` | 无命中（grep 退出码 1） |
| `git diff --check` | 退出码 0 |

测试前后 `ls backend/uploads | sort | shasum` 均为 `ccf9c1525240498c5b94e47a220a87a64f587eac  -`；`ls -l backend/*.db` 前后逐字一致（`fiona.db` 和 `local-avatar.db` 均未变化）。用临时库单独验证管理脚本：缺库发码退出 2 且不建文件；`--init-db` 发 2 码；建两账号后删除 `tester01`，新码绑定 `tester03`；`grant tester02 50` 增加 50；`grant nobody 1` 退出 1。

## 未完成与人工确认

- 本任务代码项均已完成；未触碰生产数据库。运维需决定 `STRAWBERRY_DAILY_REFILL` 的生产值，核对实际服务环境文件与数据库路径，并按部署手册备份后应用新增列。
- 危机识别是短语规则，可能漏掉隐晦表达或未列语言，也可能把讨论自杀主题的文字识别为危机；扩大内测前仍需产品政策和人工验证。
- 网页搜索、旅行规划与网页提炼由模型输出结构化 `success`；模型误报成功仍可能误计。缺失该字段或非 JSON 回退保守免费；热榜旧缓存（`stale=True`）也免费。这是本次工具结算的明确取舍。
- 共享工作区中，`docs/tasks/2026-09-23-beta-blockers-backend/02-spec.md` 在开始时已未跟踪；执行期间另出现 `docs/tasks/2026-09-23-mobile-layout/02-spec.md` 和并行 `frontend/**` 修改。它们不是本任务写入，本任务没有触碰或回滚。因这些白名单外路径，第 5.8 条按整个共享工作区的 `git status` 无法成立；本任务实际修改的文件均在第 2 节白名单内。

## 返修第 1 轮

本轮依据 `04-review.md` 与 `05-fix-round1.md` 修复 R1–R4、O1/O2/O6–O10。上文 T2 的“管理脚本读取均应用补给”现修正为：`manage_strawberries.py list` 只读原始余额与补给日期，`grant/set` 仍先应用当日补给。上文 T4 的“低余额危机轮含 DEV 模式均不调用模型”现修正为：生产环境余额不足时只返回资源；`DEV_MODE=1` 跳过余额拦截。非危机朗读轮的基础安全规则位于尾随 system 消息末尾，而非主 system 末尾。

### 修改文件与功能对应

| 项目 | 文件 | 修复内容与新增/修改测试 |
|---|---|---|
| R1 | `backend/services/chat_service.py`、`backend/routers/chat.py`、`backend/tests/test_beta_billing.py` | `run_chat` 的退款/埋点收尾、路由预流退款及 `_ReservedChatResponse.__call__` 的关闭/退款均放入 `anyio.CancelScope(shield=True)`；新增 `test_asgi_disconnect_after_first_chunk_refunds_reservation`，参数化覆盖 ASGI 2.3 断线与 2.4 正控。 |
| R2 | `backend/safety.py`、`backend/tests/test_beta_safety.py` | 收紧亲昵用语、程度补语、死记硬背、英文专名与“跳楼价/跳楼机”的误报；`test_crisis_detector_rejects_required_everyday_phrases` 新增 13 条反例。 |
| R3 | `backend/safety.py`、`backend/tests/test_beta_safety.py` | 补充中英文直白自伤、自残、跳河与求死表达；`test_crisis_detector_recognizes_required_phrases` 新增 12 条正例，`test_crisis_detector_normalizes_case_and_whitespace` 增加 `dont`/`im` 无撇号断言。原 22 条与新增 25 条夹具合计 47 条均通过。 |
| R4 | `backend/services/chat_service.py`、`backend/tests/test_beta_safety.py` | 恢复 HEAD 的朗读强约束原文和位置：当前 user 后独立追加 system，仅非危机轮使用。所有 system 合计只有一份基础安全规则，置于最后一条 system 末尾；看图分支在多模态 user 后追加该 system。修改 `test_non_crisis_chat_every_reply_prompt_ends_with_one_safety_block`，覆盖朗读、朗读+镜子、朗读+看图的消息顺序和规则唯一性。 |
| O1 | `backend/services/chat_service.py`、`backend/tests/test_beta_billing.py` | 退款异常只打印类型名，设置 `trace["refund_failed"] = True`，不覆盖原 SSE，并继续写 `log_event`；新增 `test_refund_failure_keeps_sse_error_and_records_trace`。 |
| O2 | `backend/routers/chat.py`、`backend/tests/test_beta_billing.py` | `DEV_MODE=1` 危机轮跳过余额拦截，允许走模型与资源追加；旧测试改为 `test_zero_balance_crisis_reaches_model_in_dev_mode`。 |
| O6 | `backend/admin_env.py`、`backend/manage_invites.py`、`backend/seed_invites.py`、`backend/manage_strawberries.py`、`backend/tests/test_beta_admin_scripts.py` | 邀请码管理脚本 docstring 改为含 `--env-file` 的示例；三个脚本顶层及子命令帮助显示 `--env-file`、`--init-db`。新增参数化 `test_admin_scripts_help_shows_shared_options`。 |
| O7 | `backend/manage_strawberries.py`、`backend/tests/test_beta_admin_scripts.py` | 默认 `list` 跳过 `init_db`，以 SQLite 只读连接查询原始余额与日期，避免迁移回填旧帖；旧库无补给日期列时显示 `-`，无余额列时明确报错退出 2。显式 `--init-db` 仍可初始化。旧跨日测试改为 `test_manage_strawberries_list_preserves_raw_balance_and_refill_date`；新增 `test_manage_strawberries_default_list_does_not_backfill_legacy_posts`、`test_manage_strawberries_default_list_reads_old_schema_without_migration`、`test_manage_strawberries_default_list_reports_missing_balance_without_migration`。 |
| O8 | `backend/tests/test_beta_admin_scripts.py` | 子进程环境构造时清除继承的 `STRAWBERRY_DAILY_REFILL`；新增 `test_admin_script_subprocess_environment_ignores_parent_refill`。 |
| O9 | `backend/database.py`、`backend/tests/test_account_deletion.py` | `delete_account_data` 在同一事务删除该账号的 `chat_slot_state`；新增 `test_direct_account_deletion_clears_chat_slots_before_username_reuse`，核对重建同名用户后不继承旧待补参数/镜子模式，其他用户槽位仍在。 |
| O10 | `docs/DEPLOYMENT.md` | 管理脚本章节明确三个脚本进入初始化路径时会执行与服务相同的兼容 DDL（只加列/索引），还可能回填旧帖及运行版本化迁移，运行前需备份；默认草莓 `list` 是跳过初始化的只读例外。文档核对，无新增单测。 |

本轮还同步了 `backend/.env.example`、`CLAUDE.md`、`docs/ARCHITECTURE.md` 中关于管理列表、开发模式危机轮及朗读 system 消息的陈述，并追加本报告。共涉及 `backend/database.py`、`backend/routers/chat.py`、`backend/services/chat_service.py`、`backend/safety.py`、`backend/admin_env.py`、三个管理脚本、四个测试文件，以及上述四份说明文档与本报告。未触碰或回滚并行任务的 `frontend/**` 和 `docs/tasks/2026-09-23-mobile-layout/**`。

### R1 先失败后通过

在 `backend/` 下，先添加回归测试、保持 R1 生产代码未修，运行：

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_billing.py::test_asgi_disconnect_after_first_chunk_refunds_reservation
```

结果为 **1 failed、1 passed、13 warnings in 0.52s**：ASGI 2.3 用例余额为 `0`，断言预期 `10`，退款被取消；ASGI 2.4 正控通过。随后修复取消屏蔽路径，重跑同一命令，结果为 **2 passed、13 warnings in 0.47s**。O9 的新测试也曾在删槽位前以 `assert 4 == 0` 失败，修复后所在文件 3 项通过。

独立复核发现默认草莓 `list` 原先仍通过 `init_db` 回填旧帖。先添加 `test_manage_strawberries_default_list_does_not_backfill_legacy_posts`，旧代码单测 **1 failed**（`owner_username` 从 `NULL` 变为 `tester02`）；改为只读连接后同一单测 **1 passed**。另加两个旧库列兼容测试。

### 测试与隔离验收

在 `backend/` 下执行：

| 命令或检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_billing.py tests/test_beta_safety.py` | **102 passed**，13 warnings |
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_admin_scripts.py` | **26 passed** |
| `.venv/bin/python -m pytest -q tests/test_account_deletion.py` | **3 passed** |
| `.venv/bin/python -m pytest -q` | **960 passed、0 failed**，13 warnings |
| `for test_file in tests/test_*.py; do .venv/bin/python -m pytest -q "$test_file"; done`（逐文件执行并汇总） | **42 个文件全部通过，合计 960 passed** |
| `.venv/bin/python -m compileall -q -x '\.venv' .` | 退出码 0 |
| `grep -rn "请充值" --include='*.py' . \| grep -v '\.venv'` | 无命中（退出码 1） |
| `git diff --check` | 退出码 0 |

测试前后 `ls backend/uploads | sort | shasum` 均为 `ccf9c1525240498c5b94e47a220a87a64f587eac  -`；`ls -l backend/*.db` 前后逐字一致：`fiona.db` 为 192512 字节、Sep 10 09:44，`local-avatar.db` 为 1507328 字节、Sep 21 12:57。测试未修改真实上传目录与数据库文件。

### 未完成与人工确认

- R1–R4 和 O1/O2/O6–O10 均已完成。O3 的新闻/剧情提及是否进入危机流程，以及 O4、O5，按返修单留给产品负责人决定；危机词表仍需真实场景人工复核。
- O1 的退款失败会留下 `refund_failed` 埋点供运维排查，本轮未加入自动重试。生产运行管理脚本前仍需由运维备份数据库，确认服务环境文件、数据库路径和每日补给数值。
