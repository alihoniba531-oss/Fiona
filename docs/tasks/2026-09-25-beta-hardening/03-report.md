# 2026-09-25 内测前代码加固报告

## 修改文件与功能

| 范围 | 文件 | 变更 |
|---|---|---|
| 账号和数据库 | `backend/database.py` | 新账号随机初始会话版本；`retired_usernames` 表、删号墓碑、邀请码避撞；初始化启用 WAL；SQLite 连接统一使用 5 秒 busy timeout。`backend/auth.py` / `auth_dep.py` 保持现有 `sv` 兼容和鉴权逻辑。 |
| 危机支持 | `backend/safety.py`、`backend/routers/chat.py`、`backend/services/chat_service.py` | 三级危机识别；明确危机的正常预扣/交付结算/失败退款与余额不足免费资源短路；首个 SSE 危机标记；前置会话失败的资源 SSE；可能相关轮次保留普通功能并在文字回复末尾附资源；硬词反问例外。`chat_service.py` 同时串行完成 T3 的槽位调用线程转移。 |
| 槽位和 SQLite 调用方 | `backend/intent_router.py`、`backend/mode_switcher.py`、`backend/conversation_matcher.py`、`backend/routers/conversations.py`、`backend/routers/me.py`、`backend/agent_store.py`、`backend/exchange_store.py`、`backend/main.py`、`backend/trace.py`、`backend/routers/plaza.py`、`backend/manage_strawberries.py`、`backend/scripts/fix_matches.py`、`backend/analyze.py` | 槽位连接不再逐次执行建表 DDL；请求协程的同步槽位调用移至 `asyncio.to_thread`；非测试 SQLite 连接显式使用同一个 5 秒 busy timeout。 |
| 前端 | `frontend/app/page.tsx` | 收到 `crisis: true` 后把图片模式本轮按文字回复收尾，清除图片生成状态和重试入口；未改 className 或页面结构。 |
| 测试 | 新增 `backend/tests/test_beta_session_revival.py`、`backend/tests/test_event_loop_slots.py`；更新 `backend/tests/test_beta_safety.py`、`test_beta_billing.py`、`test_context_slot_state.py`、`test_spec_bugfixes.py`、`test_chat_external_references.py`、`test_chat_image_editing.py`、`test_chat_image_generation.py`、`test_chat_multi_image_editing.py`、`test_chat_upstream_errors.py`、`test_image_generation.py`、`test_public_surface.py` | 增加 T1–T3 回归；旧测试的 token 签发改为读取新账号当前版本；原先依赖槽位读取时自动建表的测试改为先初始化数据库。 |
| 文档 | `README.md`、`PLAN.md`、`CLAUDE.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、本报告 | 同步会话版本、退役用户名、危机分级与计费、图片模式、槽位线程转移、WAL 和备份方式。 |

## T1–T4 对应

### T1：会话复活

- `get_or_create_user` 与 `get_or_create_user_by_phone` 两条新建 `users` 路径都写入密码学随机正整数 `session_version`，现存行不变；旧 `sv=0` token 仍能认证旧账号。
- `init_db` 创建 `retired_usernames(username TEXT PRIMARY KEY, retired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)`；`delete_account_data` 在删号事务中写墓碑；`create_tester_invites` 计算最大编号和逐名检查都纳入该表。复现序列返回 `tester03`，旧 token 在同名 `tester02` 重建后仍认证失败。
- 新增测试：`test_deleted_tester_name_is_retired_and_old_token_stays_invalid`、`test_new_users_start_with_distinct_positive_session_versions`、`test_existing_zero_version_session_remains_valid`。

### T2：危机分级

- `assess_crisis` 返回 `high`、`possible` 或 `None`；`detect_crisis` 保留为只判断 `high` 的兼容封装。原有正反例与规格新增的三级句子合并为参数化夹具。
- `high` 轮跳过镜子、意图、工具和待补参，也不清除既有待补状态；system 以 `CRISIS_GUIDANCE` 收尾。模型成功或失败都发送并保存资源文案。余额够时预扣 10 颗并按交付结算，未交付退款；余额不足时不调用模型、不扣费且直接返回资源。`DEV_MODE=1` 跳过计费。SSE 首项为 `{"crisis": true}`；图片生成/修改请求改为文字危机回复，已保存参考图仍先回执。`build_context` 抛 `ResourceNotFound` 时返回危机标记、资源文本和错误事件，并退还预扣。
- `possible` 轮保留普通模式、意图、工具、图片与计费；文字回复追加 `\n\n` 和资源文案并落库，trace 记录 `crisis="possible"`，不附加硬词反问指令。硬词附录开头增加危机例外句。前端按危机标记将图片请求的结果作为文字展示，避免“图片未完成”及重试按钮。
- 新增测试：`test_crisis_detector_marks_related_talk_possible`、`test_crisis_detector_separates_contextual_mentions_from_personal_risk`、`test_high_crisis_context_failure_streams_resources_and_refunds`、`test_possible_crisis_keeps_tool_routing_billing_resources_and_trace`、`test_possible_crisis_skips_hard_word_appendix`、`test_hard_word_appendix_has_crisis_exception`、`test_high_crisis_image_mode_never_generates_image`。扩充原有 `test_crisis_detector_recognizes_required_phrases` / `test_crisis_detector_rejects_required_everyday_phrases`，更新 high 计费、失败退款、资源落库、零余额和开发模式测试。原有安全底线顺序测试继续通过。

### T3：事件循环不阻塞

- 同步槽位 API 保留给同步路径；`chat_service.py`、`conversation_matcher.py`、`routers/conversations.py`、`routers/me.py` 中的异步调用点使用 `await asyncio.to_thread(...)`。`detect_mode` 原本已在工作线程执行，其内部同步槽位调用保持原样。槽位读写不再每连接执行 `CHAT_SLOT_STATE_DDL`，表由 `init_db` 创建。
- 所有非测试 `aiosqlite.connect` / `sqlite3.connect` 显式使用共享 `SQLITE_BUSY_TIMEOUT=5.0`；`init_db` 执行 `PRAGMA journal_mode=WAL`。临时库直接检查结果为 `wal`、`busy_timeout=5000` 毫秒、退役表存在。
- 新增测试：`test_slot_access_does_not_block_event_loop_during_writer_transaction`（10ms 心跳、并行写事务与槽位读写，要求最大延迟小于 250ms 且无 `OperationalError`）、`test_init_db_enables_wal_and_shared_busy_timeout`。
- **修改前失败记录**：产品代码零修改、仅新增回归测试时运行 `cd backend && ./.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_event_loop_slots.py`，得到 `1 failed in 5.82s`，`OperationalError('database is locked')`；事件循环上的同步槽位调用卡住写事务。
- **修改后结果**：同一命令 `2 passed in 0.72s`。剩余 3 处同步 `sqlite3.connect`：`backend/analyze.py:85` 仅命令行；`backend/intent_router.py:213`、`backend/mode_switcher.py:118` 是同步槽位 helper，在请求协程中均经 `asyncio.to_thread` 执行，不在事件循环线程直连。

### T4：文档同步

- `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md` 和 `PLAN.md` 已逐处更新当前会话版本、用户名退役、危机分级/计费、图片模式危机、槽位持久化/线程转移、WAL。`PLAN.md` 新增 2026-09-25 加固条目，并修正“WAL/busy timeout 尚未实现”的待办。
- 部署手册迁移清单纳入 `retired_usernames` 和 WAL；备份命令继续使用 `sqlite3 .backup`。WAL 模式下已提交数据可能仍在 `fiona.db-wal`，**不能只复制主数据库文件**，应使用 SQLite `.backup` 或在线备份 API，并配套备份媒体目录。
- 全库检索还发现 `docs/CYBER_AVATAR_PLATFORM.md:112` 把槽位写成“当前……以用户名定位”的旧描述；该文件不在规格第 2 节白名单内。已依据第 4 节向用户询问是否只授权更新这一处，答复前不修改该文件。

## 验收结果

| 命令 / 检查 | 结果 |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` | **1014 passed，13 warnings，退出码 0**。首次完整运行是 `1013 passed / 1 failed`：旧 `test_stream_failure_is_not_saved_or_charged` 依赖槽位读取时建表；给该测试的临时库执行 `init_db()` 后完整重跑通过。 |
| 对 `backend/tests/test_*.py` 的 45 个文件逐一执行 `.venv/bin/python -m pytest -q -p no:cacheprovider <文件>` | **45/45 文件通过，合计 1014 passed，0 failed**。 |
| `cd backend && .venv/bin/python -m compileall -q -x '\.venv' .` | 退出码 0。 |
| `cd frontend && npx tsc --noEmit` | 退出码 0。 |
| `cd frontend && npm run lint` | 退出码 0，0 errors、28 warnings，达到规格上限。 |
| `cd frontend && npm run build -- --webpack` | 退出码 0；Next.js 16.3.3 编译、类型检查、14 个静态页面生成均成功。 |
| `git diff --check` 与 `git diff -- frontend` | 无空白错误；前端 diff 只涉及 `frontend/app/page.tsx` 的 SSE 事件处理和事件类型，无 className / 结构变化。 |
| 测试前后 `ls uploads \| sort \| shasum`、`ls -l *.db` | 上传目录 hash 均为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`fiona.db` 与 `local-avatar.db` 的大小和时间戳未变化。 |
| `git status --porcelain --untracked-files=all` | 本轮新增/修改路径均在第 2 节白名单内。输出还包含开始前已有、未改动的未跟踪 `02-spec.md`；它未被第 2 节列入白名单，因此第 5 节该项**按字面不能判为通过**，已向用户请求将其作为基线例外。规格禁止 `git add`，也要求不回滚已完成工作，故保留原文件。 |

## 已知边界与人工确认

- 规则识别仍可能误判。实测 `这句歌词是‘我想死’，你怎么看` 与 `他在小说里说我想死` 被判 `high`，语境更适合 `possible`；`明天就不在了` 被判 `None`，若实际指自伤则是漏报。规则不能替代完整的危机政策和人工安全评估。
- `docs/CYBER_AVATAR_PLATFORM.md:112` 的旧描述位于白名单外，是否同步该处仍待用户答复；其余白名单内改动和验收已完成。
- 开始前即未跟踪的 `02-spec.md` 不在第 2 节白名单内；第 5 节 `git status` 路径要求需用户确认基线例外。本轮没有修改、加入暂存区或删除该文件。
- 尚未在真实部署环境演练 WAL 数据库与媒体的配套备份/恢复，也未完成扩大内测前的成人内容、年龄、AI 身份和危机干预产品政策确认。

## 返修第 1 轮

本节对应 `04-review.md` 和 `05-fix-round1.md`，记录返修后的状态；上文保留首次交付时的测试与边界快照。返修单已明确允许只修改 `docs/CYBER_AVATAR_PLATFORM.md` 的槽位描述，并把规格作者预置的 `02-spec.md`、`04-review.md`、`05-fix-round1.md` 列为 `git status` 白名单检查的基线例外。本轮没有回滚首次交付的工作。

### 修改文件与逐项对应

| 项目 | 本轮修改文件 | 处理结果与新增测试 |
|---|---|---|
| R1 | `backend/safety.py`、`backend/tests/test_beta_safety.py` | 语境剥离遇到第二个「我」即停止；方法类询问进入 `high`，信息/救助语境仍为 `possible`。新增 `test_crisis_detector_baseline_high_phrases_stay_high` 和 `test_method_query_never_reaches_tools`；`帮我查一下怎么割腕不疼` 的首事件为危机标记，不调用意图识别或工具。 |
| R2 | 同上，由同一 subagent 串行完成 | 无主语的明确危机、当前自伤与过量服药进入 `high`；含糊告别/撑不下去至少为 `possible`。新增 `test_crisis_detector_ambiguous_phrases_are_at_least_possible`、`test_ongoing_self_harm_gets_crisis_support`；后者确认 `我割腕了`、`吃了一整瓶安眠药` 的首事件和模型 system 尾部危机指引。 |
| R3 | 同上 | 恢复 `要死(?!了...)` 限制，亲属/宠物病危及「我要死了」等口语保持 `None`。新增 `test_crisis_detector_dying_relatives_and_hyperbole_stay_none`、`test_dying_relative_keeps_normal_routing`；后者确认正常意图路由、无危机 system 指引和资源附注。原规格全部 high/possible/None 夹具继续通过。 |
| R4 | `docs/DEPLOYMENT.md` | 回滚前停服并检查旧 `-wal`/`-shm`；若需保留旧库尚未检查点的数据，先对**旧库**执行 `PRAGMA wal_checkpoint(TRUNCATE)` 并可另存快照；覆盖主文件前删除旧伴生文件，再用 `.backup` 快照恢复。启动前 `PRAGMA integrity_check` 必须输出 `ok`，确认属主 `fiona:fiona`。 |
| O5 | `backend/database.py`、`backend/tests/test_beta_session_revival.py` | 两条新建账号路径改用 `secrets.randbelow(2**31 - 1) + 1`，避免后续 `session_version + 1` 越过 SQLite 整数范围。新增 `test_new_session_version_bounds_allow_integer_revocation`（用户名/手机号 × 上下界）及 `test_max_initial_version_survives_invite_rotation_and_revocation`，检查撤销效果与库内整数类型。 |
| O8 | `backend/intent_router.py`、`backend/mode_switcher.py`、`backend/tests/test_context_slot_state.py` | 过期或损坏槽位只在 `expires_at` 仍等于读取时原值时删除，避免旧 reader 删掉并发写入的新行。新增参数化 `test_expired_slot_cleanup_preserves_concurrent_replacement`，覆盖 pending/mode 两种状态。 |
| O9a | 同 O8 文件 | 两处 `_slot_conn` 在 `sqlite3.connect` 之前检测当前线程运行中的事件循环并抛出明确 `RuntimeError`，测试与生产均生效。新增参数化 `test_sync_slot_connection_rejects_running_event_loop_before_open`，覆盖两个模块。 |
| O9b | `docs/DEPLOYMENT.md` | 发布备份与用有权读取 `root:root 0600` 环境文件的运维账号运行管理脚本前停后端；数据库操作后修正主文件及 `-wal`/`-shm` 为 `fiona:fiona` 再启动。若需要在线操作，先提供服务账号可读的受控配置和可写备份目的地，并以服务账号执行。 |
| 文档 | `docs/CYBER_AVATAR_PLATFORM.md`、本报告 | 只把该文件原第 112 行附近的“槽位以用户名定位”改为当前按账号与会话隔离、在 `chat_slot_state` 持久化的事实；在本报告追加返修结果与以下基线对照。 |

### 危机识别与基线对照清单

用 `git show ae026c9:backend/safety.py` 的 `detect_crisis` 与返修后的 `assess_crisis`，逐句比较 `test_beta_safety.py` 的三级参数化夹具、返修 R1–R3 夹具和 4 条空白/大小写夹具，共 **126 条去重句子**。旧版判 True 而新版非 `high` 的 **完整 19 条**如下；这些降级均由原规格或复核/返修单明确要求：

| 新级别 | 旧版 True → 新版非 high 的全部句子 | 要求来源 |
|---|---|---|
| `possible`（11） | `帮我查下割腕的急救方法`；`今天新闻说有人跳楼了`；`他说他不想活了，我该怎么劝`；`让我去死吧哈哈哈哈`；`安眠药吃多少会有危险`；`我朋友说想死，我该怎么劝`；`我想研究自杀预防`；`我想写一篇自残报道`；`我一点也不想死`；`我不想自杀`；`活着没意思` | 前 5 条为 `02-spec.md` 的 possible；中间 5 条为 `04-review.md` 要保留的语境夹具；最后 1 条为返修单 R2 至少 possible。 |
| `None`（8） | `我困得要死`；`我忙得要死`；`我饿得要死`；`我要死磕这个bug`；`《自杀小队》好看吗`；`自杀式营销真恶心`；`跳楼大甩卖`；`kill myself laughing` | 均为 `02-spec.md` 的 None 夹具。 |

旧版判 False 而新版判 `high` 的 **完整 12 条**：`好想死`、`我已经写好遗书了`、`不如死了算了`、`我想结束这一切`、`我把安眠药都攒好了`、`生无可恋，想死`、`我想自我了断`、`dont wanna live`、`i'm going to jump off the bridge`（原规格明确要求 high）；`我已经没有活下去的理由了`（复核要求保留的 high 夹具）；`我想结束生命`、`我在考虑结束生命`（返修单 R2 要求 high）。未出现无要求依据的“旧版 True → 新版非 high”句子。方法类和当前自伤行为测试还确认了实际路由，而不只检查分类器返回值。

### 修前红灯与返修后验收

| 命令或检查 | 结果 |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_safety.py` | 先仅添加 R1–R3 返修测试、未改 `safety.py`：**45 failed、114 passed**。修复后：**159 passed**。 |
| O5 新测试在旧 63 位上界代码上运行 | **5 failed、3 deselected**；改用 31 位上界后，`tests/test_beta_session_revival.py tests/test_auth_sessions.py` 为 **14 passed**。 |
| O8/O9a 新测试在旧槽位代码上运行 | **4 failed**；修复后 `tests/test_context_slot_state.py tests/test_event_loop_slots.py` 为 **30 passed**。 |
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` | **1069 passed、13 warnings、退出码 0**。 |
| 对全部 `backend/tests/test_*.py` 逐文件运行 `.venv/bin/python -m pytest -q -p no:cacheprovider <文件>` | **45/45 文件通过，合计 1069 passed、0 failed**。 |
| `cd backend && .venv/bin/python -m compileall -q -x '\.venv' .`；`git diff --check` | 均退出 0。 |
| `cd frontend && npx tsc --noEmit`；`npm run lint`；`npm run build -- --webpack` | 均退出 0；Lint 为 0 errors、28 warnings，Next.js 16.3.3 Webpack 生产构建成功。本轮前端代码未改。 |
| 前后 `ls uploads \| sort \| shasum` 与 `ls -l *.db` | 上传目录哈希始终为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`fiona.db` 为 192512 B、`local-avatar.db` 为 1536000 B，时间戳与返修前一致。 |
| `git diff -- frontend` 与白名单核对 | 本轮未修改前端，既有 `page.tsx` 事件处理 diff 保持原样。新增/修改路径都在 `02-spec.md` 白名单及返修单补充范围内；预置的 `02-spec.md`、`04-review.md`、`05-fix-round1.md` 按返修单作为基线例外。 |

### 有意保留的边界与人工确认

- O2 引号/转述语境仍可能被判 `high`，例如 `这句歌词是‘我想死’，你怎么看`、`他在小说里说我想死`；按返修单交给产品负责人后续决定。本轮对 `撑不下去`、`永别`、`明天就不在了` 三类短句已提升到至少 `possible`，仍无法仅凭短句判断真实意图。
- O4 有意保留：用户开启朗读时，`possible` 轮搜索卡片后的热线资源文字仍可能被自动朗读；本轮没有改动前端音频处理。
- O6 存量数据库中在启用 `retired_usernames` 前已删除的 `testerNN` 无记录可回填；这些历史编号可能再发一次，虽随机会话版本使旧 token 不会复活，仍需运维在真实存量库核对。O7 邀请码兑换与删号跨事务交错的既有竞态本轮未改，需另行评估。
- 恢复真实 WAL 数据库前，运维必须按 [部署手册](../../DEPLOYMENT.md#回滚与恢复) 检查并处理残留的 `fiona.db-wal` / `fiona.db-shm`，确认完整性检查输出 `ok` 且属主正确；本轮只更新恢复步骤，尚未在真实部署环境演练。成人内容、年龄、AI 身份和危机干预的产品政策仍需负责人确认。

## 返修第 2 轮

依据 04-review-round2.md 与 05-fix-round2.md 修复 F1、F2。本轮只修改 backend/safety.py、backend/tests/test_beta_safety.py 和本报告；原规格与返修第 1 轮的实现和夹具保留。04-review-round2.md、05-fix-round2.md 是本轮开始前已有的返修资料，本轮未改动。

### 修改文件、功能与新增测试

| 文件 | 本轮改动 |
|---|---|
| backend/safety.py | F1：将无主语的“结束生命/一切”限定为紧邻意图词；剥离指向“你”的“要去死/不如死了”表达，第三人称相关表达不再劫持为 high；排除“要死不活”。剥离边界不跨后续“我”，保留第一人称危机。F2：补“半瓶安眠药”、安眠药方法问句、跳楼语境后的“我也想跳”；泛称过量服药和“活着没有意义”进入 possible。 |
| backend/tests/test_beta_safety.py | 新增四组参数化夹具：test_crisis_detector_round2_non_self_phrases_do_not_route_high（9 例）、test_crisis_detector_round2_high_risk_variants（4 例）、test_crisis_detector_round2_ambiguous_variants_are_at_least_possible（4 例）、test_crisis_detector_round2_existing_high_phrases_stay_high（7 例）。 |
| 本报告 | 追加本轮前后判级、更新后的基线对照与验收结果。 |

### 本轮前后变化句子清单

下表中的“前”是返修第 1 轮结束时的 assess_crisis，“后”是本轮修复后的 assess_crisis；共 16 句实际改变级别。

| 前 → 后 | 句子 |
|---|---|
| high → None（8） | 疫情结束一切恢复正常；比赛结束这一切就值了；项目结束一切顺利；考试结束这一切就都过去了；等这个项目结束一切都好了；你要去死吗；你这样还不如死了呢；我妈要死不活的躺着。 |
| high → possible（1） | 他要去死我也拦不住。这里仍提及第三方可能的危机，因此保留资源提示，但不走 high 危机路由；这是 F1 明确允许的级别。 |
| possible → high（3） | 刚吞了半瓶安眠药；哪种安眠药吃了不会醒；我朋友跳楼了，我也想跳。 |
| None → possible（4） | 刚吞了好多药；我吃了很多药；我觉得活着没什么意义；活着没有意义。 |

F2 的“我吞了半瓶安眠药”原已是 high，本轮仍为 high。返修单列出的七条不得回退句子——“我想结束这一切”“我想结束生命”“我在考虑结束生命”“不如死了算了”“活着没意思，不如死了”“我要去死了”“我现在就想去死”——均保持 high。

### 更新后的 ae026c9 基线对照

用 git show ae026c9:backend/safety.py 读取原版 detect_crisis，与本轮 assess_crisis 逐句对照。语料从 test_beta_safety.py 的所有 message 参数化夹具、四条归一化断言以及行为测试中的消息取值去重：返修第 1 轮完整语料 131 句，加上 F1/F2 的 17 个新句子和两条新增的保持 high 句子，本轮共 150 句。此前报告的 126 句口径未含五条行为测试独有消息；本轮已纳入。

| 原版 detect_crisis | 新 high | 新 possible | 新 None | 合计 |
|---|---:|---:|---:|---:|
| True | 61 | 12 | 9 | 82 |
| False | 12 | 10 | 46 | 68 |
| 合计 | 73 | 22 | 55 | 150 |

原版 True → 新版非 high 的完整 21 句如下，均有原规格、复核或返修单的降级依据；比上一轮完整 131 句口径的 20 句仅新增 F1 要求排除的“我妈要死不活的躺着”。

- 新 possible（12）：今天新闻说有人跳楼了；他说他不想活了，我该怎么劝；安眠药吃多少会有危险；帮我查下割腕的急救方法；我一点也不想死；我不想自杀；我只能帮他查割腕的急救方法；我想写一篇自残报道；我想研究自杀预防；我朋友说想死，我该怎么劝；活着没意思；让我去死吧哈哈哈哈。
- 新 None（9）：kill myself laughing；《自杀小队》好看吗；我困得要死；我妈要死不活的躺着；我忙得要死；我要死磕这个bug；我饿得要死；自杀式营销真恶心；跳楼大甩卖。

原版 False → 新版 high 的完整 12 句：dont wanna live；i'm going to jump off the bridge；不如死了算了；好想死；我在考虑结束生命；我已经写好遗书了；我已经没有活下去的理由了；我想结束生命；我想结束这一切；我想自我了断；我把安眠药都攒好了；生无可恋，想死。它们均为原规格或返修第 1 轮要求的 high。

原版 False → 新版 possible 的完整 10 句：今天好累想死；他要去死我也拦不住；刚吞了好多药；想死的心都有了；我吃了很多药；我真的撑不下去了；我觉得活着没什么意义；明天就不在了；晚安，永别了；活着没有意义。其余 61 条 True → high、46 条 False → None。

### 红灯、绿灯与验收

以下 pytest 命令均在 backend/ 下执行。先只添加 F1/F2 参数化夹具，保持 safety.py 为返修第 1 轮状态，运行 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_safety.py -k round2 --tb=line：16 failed、8 passed、159 deselected，退出码 1。修复后运行同一选择集（--tb=short）：24 passed、159 deselected，退出码 0。

| 命令或检查 | 结果 |
|---|---|
| .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_safety.py | 183 passed、13 warnings、退出码 0。 |
| .venv/bin/python -m pytest -q -p no:cacheprovider | 1093 passed、13 warnings、退出码 0；原规格和返修第 1 轮夹具全部通过。 |
| 对全部 tests/test_*.py 逐文件执行 .venv/bin/python -m pytest -q -p no:cacheprovider <文件> | 45/45 文件通过，合计 1093 passed、0 failed。 |
| .venv/bin/python -m compileall -q -x '\.venv' .；git diff --check | 均退出码 0。 |
| 测试前后在 backend/ 下运行 ls uploads &#124; sort &#124; shasum 与 ls -l *.db | uploads 哈希始终为 ccf9c1525240498c5b94e47a220a87a64f587eac；fiona.db 始终为 192512 B（Sep 10 09:44），local-avatar.db 始终为 1536000 B（Sep 23 22:37）。 |

F1/F2 无未完成项；既有的引号/转述语境等规则边界与产品政策确认仍按“返修第 1 轮”末节处理。本轮没有修改前端、上传目录、数据库或白名单外文件，也没有回滚先前工作。

## 返修第 3 轮

依据 05-fix-round3.md 和 04-review-round2.md 末尾「第三轮定向核验」处理 G1–G3，并补两组语料护栏。本轮只修改 backend/safety.py、backend/tests/test_beta_safety.py 和本报告；第 1、2 轮工作与夹具均保留。日常语料与危机语料逐句及按分类器规范化后均无同句相反要求，未触发规格第 4 节的停问条件。

### 修改文件、规则和新增测试

| 文件 | 本轮改动 |
|---|---|
| backend/safety.py | G1：把安眠药从通用方法问句名词表移出，为带致死语义的安眠药问句设专门 high 规则；普通用药问句保留 possible。G2：无主语“结束生命/一切”的“在”“要”意图词加前置排除，避免落在“现在/正在/只要/需要/主要/重要”内部。G3：跳楼语境后“我也想跳”的 high 规则排除“跳槽/跳伞/跳绳/跳远/跳高/跳舞”。另剥离“要死在这个需求上了哈哈”一类工作口语，保留同句中其他明确危机信号的识别。 |
| backend/tests/test_beta_safety.py | 新增参数化 test_crisis_detector_round3_sleeping_pill_questions（11 例）、test_crisis_detector_round3_ending_intent_word_boundaries（10 例）、test_crisis_detector_round3_jump_word_boundaries（2 例）；新增两组长期护栏 test_everyday_corpus_never_high（30 例）与 test_explicit_risk_corpus_always_high（23 例）。 |
| 本报告 | 追加本轮前后变化、更新后的基线对照、全量与逐文件验收以及已知漏判。 |

第三轮前后判级：G1 指定的七条普通安眠药问句均由 high → possible；另补“哪种安眠药起效最快”由 high → possible。G2 指定的六条“现在/只要/需要/主要…结束”由 high → None。G3 的“我朋友跳楼了，我也想跳槽”由 high → possible；“我朋友跳楼了，我也想跳”仍 high。日常护栏中的“我要死在这个需求上了哈哈”由 high → None。G1 的“哪种安眠药吃了不会醒”“刚吞了半瓶安眠药”“吃了一整瓶安眠药”与 G2 的四条明确意图句均保持 high。两组护栏最终为日常 30/30 非 high、危机 23/23 high；原规格与前两轮夹具未回退。

### 更新后的 ae026c9 基线对照

用 git show ae026c9:backend/safety.py 的 detect_crisis 与本轮 assess_crisis 比较。语料从 test_beta_safety.py 的全部 message 参数化夹具、四条归一化断言及行为测试的消息字面量去重；第二轮为 150 句，本轮新增 53 句，共 203 句。旧版是布尔结果，下表逐句映射到新版三级结果。

| 原版 detect_crisis | 新 high | 新 possible | 新 None | 合计 |
|---|---:|---:|---:|---:|
| True | 67 | 17 | 10 | 94 |
| False | 14 | 15 | 80 | 109 |
| 合计 | 81 | 32 | 90 | 203 |

原版 True → 新版非 high 的完整 27 句，均为原规格、前两轮返修或本轮 G1/G3/日常护栏要求的降级；较第二轮 21 句增加 6 句。

- 新 possible（17）：今天新闻说有人跳楼了；他说他不想活了，我该怎么劝；医生开的安眠药怎么吃才对；失眠怎么办，要不要吃安眠药；安眠药吃多了第二天头晕正常吗；安眠药吃多少会有危险；帮我查下割腕的急救方法；我一点也不想死；我不想自杀；我只能帮他查割腕的急救方法；我想写一篇自残报道；我想研究自杀预防；我朋友说想死，我该怎么劝；我朋友跳楼了，我也想跳槽；活着没意思；让我去死吧哈哈哈哈；长期吃安眠药怎么戒掉。
- 新 None（10）：kill myself laughing；《自杀小队》好看吗；我困得要死；我妈要死不活的躺着；我忙得要死；我要死在这个需求上了哈哈；我要死磕这个bug；我饿得要死；自杀式营销真恶心；跳楼大甩卖。

原版 False → 新版 high 的完整 14 句：dont wanna live；i'm going to jump off the bridge；不如死了算了；好想死；我在考虑结束生命；我已经写好遗书了；我已经没有活下去的理由了；我想结束生命；我想结束这一切；我想自我了断；我打算结束这一切了；我把安眠药都攒好了；我要结束这一切；生无可恋，想死。新增的“我打算结束这一切了”“我要结束这一切”是 G2 明确要求保持 high 的句子。

原版 False → 新版 possible 的完整 15 句：今天好累想死；他要去死我也拦不住；刚吞了好多药；哪种安眠药副作用小一点；哪种安眠药起效最快；安眠药和褪黑素哪种更温和；安眠药怎么买；想死的心都有了；我吃了很多药；我妈失眠，哪种安眠药适合老人；我真的撑不下去了；我觉得活着没什么意义；明天就不在了；晚安，永别了；活着没有意义。其余 67 条 True → high、80 条 False → None。

### 修前红灯、修后验收与快照

先仅新增返修单的 75 条定向及语料夹具，保持 safety.py 为返修第 2 轮状态。在 backend/ 下运行 ./.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_safety.py -k 'round3 or corpus' --tb=short，得到 15 failed、60 passed、183 deselected，退出码 1；失败分别为 G1 七句、G2 六句、G3 一句、工作口语一句。随后补“哪种安眠药起效最快”这一条护栏并修复规则，最终同一选择集为 76 passed、183 deselected，退出码 0。

| 命令或检查 | 结果 |
|---|---|
| .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_beta_safety.py | 259 passed、13 warnings、退出码 0。 |
| .venv/bin/python -m pytest -q -p no:cacheprovider | 1169 passed、13 warnings、退出码 0；原规格与第 1、2 轮夹具全部通过。 |
| 对全部 tests/test_*.py 逐文件执行 .venv/bin/python -m pytest -q -p no:cacheprovider <文件> | 45/45 文件通过，合计 1169 passed、0 failed。 |
| .venv/bin/python -m compileall -q -x '\.venv' .；git diff --check | 均退出码 0。 |
| 测试前后在 backend/ 下运行 ls uploads &#124; sort &#124; shasum 与 ls -l *.db | uploads 哈希始终为 ccf9c1525240498c5b94e47a220a87a64f587eac；fiona.db 始终为 192512 B（Sep 10 09:44），local-avatar.db 始终为 1536000 B（Sep 23 22:37）。 |

### 仍需后续处理的识别边界

以下真实危机写法在 ae026c9 基线中 detect_crisis=False，本轮 assess_crisis 仍为 None：我已经想好怎么死了；我想一了百了；活着真没意思，想一了百了；不想再撑了，想解脱；药都准备好了，今晚就结束。本轮按返修单将其诚实列为已知漏判，没有把它们写成已覆盖。前两轮报告列出的引号/转述语境等产品判断与运维确认也仍有效。本轮没有修改前端、上传目录、数据库或白名单外文件，也没有回滚先前工作。
