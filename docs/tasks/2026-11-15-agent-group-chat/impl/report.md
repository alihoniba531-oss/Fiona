# 讨论群第三期（聊天互通）实施报告

规格：`docs/tasks/2026-11-15-agent-group-chat/02-spec.md`（v1.0，作者已确认）。基线 `eb9ec55`，分支 `feat/agent-group-chat`。报告中的命令都在 `frontend/` 或 `backend/` 下执行，并按规格加了 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`（本机 `NO_PROXY` 自带 `[::1]`，不加前缀时 httpx 会报 Invalid port）。

## 1. 拆分表与变更文件

### 1.1 派出过的全部代理

| 代理 | 负责范围 | 产出文件 |
|---|---|---|
| `foundation-core` | 规格 4.2、4.3、4.4、4.6.5/4.6.6 校验与卡片形状、4.8 视图 | `backend/discuss/config.py`、`backend/discuss/chat.py`（新）、`backend/discuss/cards.py`（新）、`backend/rate_limit.py`、`test_discuss_chat_readonly.py`、`test_discuss_chat_switches.py`、`test_discuss_chat_cards_unit.py` |
| `foundation-db` | 规格 4.7.1–4.7.5、4.9.1–4.9.2 | `backend/database.py`、`backend/agent_store.py`、`test_discuss_chat_db.py` |
| `foundation-frontend-lib` | 规格 4.10.1、4.10.7 纯函数 | `frontend/lib/discuss.ts`、`frontend/lib/discussLogic.ts` |
| `platform` | 规格 4.5、4.7.4、6.1、6.4 | `backend/intent_router.py`、`backend/services/chat_service.py`、`test_discuss_chat_platform.py` |
| `cards-api` | 规格 4.8、4.9.3、6.7、6.8 | `backend/discuss/service.py`、`backend/discuss/store.py`、`backend/routers/discuss.py`、`test_discuss_chat_cards_api.py` |
| `frontend-chat` | 规格 4.10.2–4.10.4 | `frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/lib/useConversations.ts`、`test_discuss_chat_frontend.py` |
| `frontend-cards` | 规格 4.10.5、4.10.6 | `frontend/components/DiscussTaskCard.tsx`（新）、`frontend/components/DiscussNoteCard.tsx`（新）、`test_discuss_chat_card_components.py` |
| `prefill` | 规格 4.10.7 | `frontend/app/discuss/new/page.tsx`、`frontend/components/discuss/DiscussCreateForm.tsx`、`test_discuss_chat_prefill.py` |
| `docs` | 规格 4.11、作者已定第 2 条、6.10、6.11 | `README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example`、`CLAUDE.md`、`frontend/components/ChatModelSection.tsx`、`backend/tests/test_empty_states_settings_privacy.py`（仅两处数字）、`test_discuss_chat_docs.py` |
| `claude` | 规格 4.2、4.6、4.7.4、6.1、6.5 | `backend/services/claude_agent.py`、`test_discuss_chat_claude.py` |
| 主代理（本人） | 拆分、派发、集成、验收、自检、报告 | 修正新建测试两处断言；`read_progress` 超过 200 条消息时补分页取真正最近 8 条；本报告 |

### 1.2 新增文件

生产代码 4 个：

- `backend/discuss/chat.py`
- `backend/discuss/cards.py`
- `frontend/components/DiscussTaskCard.tsx`
- `frontend/components/DiscussNoteCard.tsx`

新测试 11 个（全部以 `test_discuss_chat_` 开头，共 221 条）：

- `backend/tests/test_discuss_chat_readonly.py`（47）
- `backend/tests/test_discuss_chat_switches.py`（7）
- `backend/tests/test_discuss_chat_cards_unit.py`（25）
- `backend/tests/test_discuss_chat_db.py`（12）
- `backend/tests/test_discuss_chat_platform.py`（42）
- `backend/tests/test_discuss_chat_cards_api.py`（9）
- `backend/tests/test_discuss_chat_frontend.py`（5）
- `backend/tests/test_discuss_chat_card_components.py`（10）
- `backend/tests/test_discuss_chat_prefill.py`（14）
- `backend/tests/test_discuss_chat_docs.py`（15）
- `backend/tests/test_discuss_chat_claude.py`（35）

### 1.3 修改文件

- 后端：`backend/discuss/config.py`、`backend/discuss/service.py`、`backend/discuss/store.py`、`backend/routers/discuss.py`、`backend/database.py`、`backend/agent_store.py`、`backend/intent_router.py`、`backend/services/chat_service.py`、`backend/services/claude_agent.py`、`backend/rate_limit.py`
- 前端：`frontend/lib/discuss.ts`、`frontend/lib/discussLogic.ts`、`frontend/lib/useConversations.ts`、`frontend/components/ChatBubble.tsx`、`frontend/components/ChatModelSection.tsx`、`frontend/app/page.tsx`、`frontend/app/discuss/new/page.tsx`、`frontend/components/discuss/DiscussCreateForm.tsx`
- 文档与配置：`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example`、`CLAUDE.md`
- 既有测试（仅规格「作者已定」第 2 条允许的两处）：`backend/tests/test_empty_states_settings_privacy.py`

规格作者放的三个未跟踪文件 `01-investigation.md`、`02-spec.md`、`03-dispatch.md` 未改、未删。

## 2. 实现与第 5 节任务清单

### 2.1 开关与只读服务（规格 4.2、4.3、4.4）

- `backend/discuss/config.py`：`chat_enabled(username, crisis=False)` 要求非危机、用户名非空、`FIONA_DISCUSS=="1"`、用户名精确命中 `FIONA_DISCUSS_USERS`、`FIONA_DISCUSS_CHAT=="1"`；`chat_cards_enabled(username)` 再加 `FIONA_DISCUSS_CHAT_CARDS=="1"`。均调用时读取。
- `backend/discuss/chat.py`：`status_label` 覆盖全部状态与 7 个暂停原因；`display_title`；`list_groups_text`（最多 20 行、0 轮写「立项」、无成果写「还没有成果」）；`resolve_group`（id 精确、显示名 casefold 包含、空查询、0 个/多个、最多列 8 个名字）；`read_progress`（方案目标/完成标准、成员类别、最近 8 条、300 字截断、未知种类不写种类名、验收结论）；`read_output`（最新一版、6000 字分段、continuation、offset 校验）；两种数据块包装和 `DATA_NOTICE` 均按规格，正文含引号、换行、`</discuss_data>` 时 `model_text` 仍是合法 JSON。
- `read_progress` 额外处理了 `service.detail` 最多 200 条消息的窗口：超过 200 条时用 `discuss_store.list_messages(after=...)` 继续翻页，取真正的最近 8 条，并新增用例覆盖。
- `backend/rate_limit.py`：新增 `discuss_read`（`FIONA_DAILY_DISCUSS_READS`，默认 60），文案「今天看讨论群的次数已用完，明天再来。」；平台路径先预检、成功后才计数。

### 2.2 平台意图（规格 4.5）

- `intent_router.py`：`DISCUSS_INTENTS`、`DISCUSS_INTENT_PROMPT`（固定开头、两个意图、group/part/offset、5 个示例）；system 内容按 `INTENT_PROMPT + 小说片段 + 讨论群片段` 拼接；`normalize_intent_result` 放行 `discuss_list`/`discuss_read`，`part` 非 `output` 归 `progress`，`group` 去空白可为空且不产生 `missing`，`offset` 只收 0 以上真整数或纯数字字符串。
- `chat_service.py`：`recognize_intent_with_fallback` 支持 `crisis` 并在小说或讨论群任一开启时传用户名；`execute_intent` 新增讨论群分支（开关拒绝文案、每日上限、`read_progress`/`read_output`）；`_stream_discuss_intent` 发文字、落库、发 `done`，不设 pending、不扣草莓；`ChatState` 新增 `discuss_task_id`/`discuss_note_id`，`_save_response` 传给 `save_message`；两者都关时调用形状、请求、事件、落库、退款保持原样。

### 2.3 Claude 工具与卡片后端（规格 4.6、4.7、4.8、4.9）

- `claude_agent.py`：四个工具定义与描述按规格；`client_tools_for_turn` 顺序为常量 5 个 → 小说（原条件原顺序）→ `list_discuss_groups`、`read_discuss_group` → `draft_discuss_task`、`draft_discuss_note` → 写歌；全关时仍返回 `CLAUDE_CLIENT_TOOLS` 对象本身；危机轮不追加。两个只读工具映射平台意图、走 `run_slow`、回灌 `model_text`、不进 SSE 文字与正文；两个出卡工具在主循环 `await`，每轮各一张，卡片 dict/回灌文案/异常文案/50 张上限均按规格，成功时设置 `state.discuss_*_id`。
- `database.py`：`discuss_task_cards`、`discuss_note_cards` 两表与 `owner_username` 索引由 `init_db` 无条件幂等创建；`messages` 补 `discuss_task_id`、`discuss_note_id`；`save_message` 两个仅关键字参数与两段附加校验放在「# 写歌归属只做附加校验」之前，只对本人本会话写入，否则 NULL；`clear_message_history`、`delete_account_data` 同事务删卡。
- `agent_store.py`：`get_conversation_messages` 带出两列；`delete_conversation` 同事务删卡。
- `discuss/cards.py`：任务卡/意见卡校验、建卡、计数、读卡视图、事务内消费、意见卡送出（`run_write` 内插入插话 + 条件 `message_id IS NULL` 更新，两次点击只产生一条；检查与 `add_note` 文案一致）。
- `discuss/service.py`：`CreateGroup.task_id`，建群同一事务消费任务卡，失败 422「任务卡不存在或已使用」并回滚；`discuss/store.py`：拆出 `post_user_note_in_txn`，原 `post_user_note` 行为不变；`delete_group` 同事务把两张卡的 `group_id` 置 NULL。
- `routers/discuss.py`：三条卡片路由，均只用 `discuss_user` 门控，不读聊天开关。

### 2.4 前端（规格 4.10）

- `lib/discuss.ts`：两卡类型与 `getDiscussTaskCard`、`getDiscussNoteCard`、`sendDiscussNoteCard`，`DiscussCreateInput.task_id`。
- `lib/discussLogic.ts`：`applyDiscussTaskPrefill` 纯函数（请求/材料原样、建议轮数/预算夹上下限、缺省保留默认值、不修改入参），仍只 `import type`。
- `app/page.tsx`：两段 `const card` 各拷 `task_id`/`note_id`；`openDiscussAt` 只放行两种路径并检查 `discussAllowed`，打开抽屉并对 iframe `location.replace`；`onOpenDiscuss` 传给 `ChatBubble`；BOM 与旅行规划尾段哈希保持。
- `ChatBubble.tsx`：两个新分支、两个新属性、两个 `<ChatCard … />` 标签各传 `onOpenDiscuss`，标签内无 `>`；`useConversations.ts` 在写歌→草稿→意见后按外键重建两种卡。
- `DiscussTaskCard.tsx` / `DiscussNoteCard.tsx`：三态、任务卡建议行与去建群/打开、意见卡送进群/已送出/读到未读到/群删除/群结束/5 条未读/返工提示，失败显示后端文案并重读；均无加粗写法、无 `dangerouslySetInnerHTML`、无原生确认框。
- 新建页：`task` 参数只接受 36 位 `[0-9a-f-]`；表单读取任务卡、404/403 提示可直接新建、已用过提示、可用时预填并在提交带 `task_id`。

### 2.5 文档（规格 4.11）

六份文档均新增「讨论群聊天互通（第三期）」：README 写用途/开关/免费与每日上限/隐私；ARCHITECTURE 写两条通道、四个工具与两个意图、两张表与两个消息外键、三个接口、清理与已知局限，并同步 `messages` 可空列说明；PLAN 新增 2026-11-15 条目与全部已知局限；DEPLOYMENT 新增三个变量与运行规则；`.env.example` 加注释头、两个开关与注释的每日上限行；CLAUDE.md 末尾新增 193 字节小节（总大小 69,219 ≤ 69,300）。设置页隐私句按原文插在小说句之后、Claude 地区句之前；既有隐私测试只改两处 7→8。

### 2.6 测试与自检

新增 11 个测试文件、221 条用例，覆盖规格 6.1–6.11。自检表见下一节。

### 2.7 报告

即本文件。

## 3. 新用例清单与自检表

### 3.1 新用例清单

| 文件 | 条数 | 覆盖 |
|---|---:|---|
| `test_discuss_chat_readonly.py` | 47 | 状态/暂停原因、显示名、列群、找群、进展、300 字截断、空方案、验收、成果分段/续读、数据块 JSON/XML、超过 200 条消息取真正最近 8 条、每日上限 |
| `test_discuss_chat_switches.py` | 7 | 两个开关的全部条件、调用时读取、默认关、`discuss_read` 默认/覆盖/成功才计数 |
| `test_discuss_chat_cards_unit.py` | 25 | 任务参数一次报全/边界/超长字数、意见文本、建卡/计数/读卡/消费、两卡视图、群删除后 `group_id` 归零 |
| `test_discuss_chat_db.py` | 12 | 两表/索引/精确列、`messages` 两列与开关无关、旧库升级、两次 init 仍 5 迁移、`save_message` 归属与表缺失、读消息带列、删号/清空/删会话清理 |
| `test_discuss_chat_platform.py` | 42 | 提示词开关矩阵、规范化、execute 拒绝与上限顺序、平台事件/落库/退款、全关时请求字节不变、调用形状、`_save_response` 外键 |
| `test_discuss_chat_cards_api.py` | 9 | 三路由门控与归属、建群消费/回滚/不带 task_id、意见卡两次只进一条、群删除/结束/5 条未读、删群释放任务卡 |
| `test_discuss_chat_frontend.py` | 5 | 两段字段拷贝、BOM/尾段哈希、`openDiscussAt` Node 执行、`toMessages` 顺序、ChatBubble 两分支两标签 |
| `test_discuss_chat_card_components.py` | 10 | 两组件存在、全部状态文案/路径、无加粗/危险写法/确认框、防重复与重读 |
| `test_discuss_chat_prefill.py` | 14 | 新建页正则/参数、表单读取/提示/提交、纯函数原样/夹上下限/缺省/不改入参 |
| `test_discuss_chat_docs.py` | 15 | 六份文档、`.env.example` 三行与中文注释、CLAUDE 大小/小节、设置页隐私句位置、既有测试数字 |
| `test_discuss_chat_claude.py` | 35 | 工具顺序/对象同一性/危机、只读回灌与预算、任务卡/意见卡精确 dict 与回灌、每轮一张、50 张、异常、落库外键 |

### 3.2 自检表（关键实现逐处改坏）

共改坏 25 处，25 处都由 pytest 以 `failed`（断言失败，非 `error`）发现。每处改坏后立即恢复原文件并重跑。

| # | 组 | 故意改坏 | 发现用例（结果均 `failed`） |
|---:|---|---|---|
| 1 | 开关 | `chat_enabled` 去掉 `FIONA_DISCUSS_CHAT` 判断 | `test_chat_enabled_requires_every_condition` |
| 2 | 每日上限 | `discuss_read` 默认 60 改成 61 | `test_discuss_daily_cap_is_registered_and_defaults_to_60` |
| 3 | 只读 | paused 不再按原因映射 | `test_status_label_paused_reasons`（6 failed） |
| 4 | 只读 | 去掉 `offset >= len(content)` | `test_read_output_rejects_bad_offsets`（2 failed） |
| 5 | 只读 | `model_text` 的 JSON 键 `discuss_content` 改成 `content` | `test_read_output_wraps_and_preserves_json_content` |
| 6 | 平台 | 讨论群关时仍拼讨论群提示词 | `test_intent_system_content_matches_switches`（8 failed） |
| 7 | 平台 | `part` 不再默认 `progress` | `test_normalize_discuss_results` |
| 8 | 平台 | 落库正文改用 `model_text` | `test_platform_discuss_intent_events_history_refund` |
| 9 | Claude | 只读工具追加顺序对调 | `test_only_discuss_read_appends_two_tools_in_order` |
| 10 | Claude | 任务卡 points 多一项 | `test_task_card_success_creates_real_row` |
| 11 | 数据库 | 任务卡附加校验不再比对会话 | `test_save_message_keeps_only_own_conversation_card_ids` |
| 12 | 数据库 | 不建任务卡表与索引 | `test_init_db_creates_card_tables_columns_and_owner_indexes` |
| 13 | 数据库 | 清空历史不删任务卡 | `test_account_and_history_cleanup_remove_only_own_cards[history]` |
| 14 | 接口 | 建群不消费任务卡 | `test_create_group_consumes_task_card_once` |
| 15 | 接口 | 意见卡重复送出不再短路 | `test_send_note_card_twice_inserts_one_note` |
| 16 | 清理 | 删群不把任务卡 `group_id` 置 NULL | `test_delete_group_releases_task_card_and_keeps_note_card` |
| 17 | 前端 | 群 id 正则 32 位改成 31 位 | `test_page_open_discuss_at_accepts_only_two_shapes` |
| 18 | 前端 | 任务卡 subtype 写成 `discuss_note` | `test_use_conversations_rebuilds_discuss_cards_after_existing_three` |
| 19 | 前端 | 第一处 `<ChatCard>` 不传 `onOpenDiscuss` | `test_chat_bubble_has_two_discuss_branches_and_two_wired_tags` |
| 20 | 前端 | 任务卡按钮文案改短 | `test_task_card_copy_paths_classes_and_branches` |
| 21 | 前端 | 预填轮数不再夹上限 | `test_prefill_clamps_values_above_maximum` |
| 22 | 前端 | 新建页正则 36 位改成 35 位 | `test_new_page_only_passes_thirty_six_char_task_ids` |
| 23 | 文档 | 设置页删掉讨论群隐私句 | `test_settings_privacy_sentence_is_once_and_between_novel_and_region` |
| 24 | 文档 | CLAUDE 小节入口路径写错 | `test_claude_md_size_and_third_phase_section_limits` |
| 25 | 文档 | `.env.example` 聊天开关默认值改 1 | `test_env_template_declares_chat_switches_and_daily_cap` |

## 4. 第 8 节验收

### 4.1 前端（第 1 条）

```bash
cd frontend
npm run lint -- --max-warnings=25
npx tsc --noEmit
npm run build
```

- lint：退出码 0；`✖ 25 problems (0 errors, 25 warnings)`，与基线一致。
- tsc：退出码 0，无输出。
- build：退出码 0；`✓ Compiled successfully in 619ms`，`✓ Generating static pages (20/20)`；路由表含 `/discuss`、`/discuss/[id]`、`/discuss/new`。

### 4.2 新用例（第 2 条）

```bash
cd backend
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_chat_*.py
```

结果：`221 passed, 48 warnings in 7.42s`；0 failed、0 error、0 skip。

### 4.3 全量（第 3 条）

```bash
cd backend
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8917 passed, 48 warnings in 557.96s (0:09:17)`；0 failed、0 error、0 skip。`8917 = 8696 + 221`，与新增用例数一致。

### 4.4 既有测试 diff（第 4 条）

`git diff -- backend/tests` 只有以下两行变化，其余全部是未跟踪的新测试文件：

```diff
diff --git a/backend/tests/test_empty_states_settings_privacy.py b/backend/tests/test_empty_states_settings_privacy.py
index 052d75c..524cf23 100644
--- a/backend/tests/test_empty_states_settings_privacy.py
+++ b/backend/tests/test_empty_states_settings_privacy.py
@@ -123,8 +123,8 @@ def test_eight_privacy_paragraphs_appear_once_and_stay_unadorned():
     details_start = source.index("<details")
     details_end = source.index("</details>")
     fold = source[details_start:details_end]
-    assert fold.count("<p>") == 7
-    assert fold.count("</p>") == 7
+    assert fold.count("<p>") == 8
+    assert fold.count("</p>") == 8
     for paragraph in ALL_PARAGRAPHS:
         assert source.count(paragraph) == 1
     assert f"<p>{FIRST}</p>" not in source
```

### 4.5 白名单（第 5 条）

`git status --porcelain --untracked-files=all` 显示的全部改动都在规格 4.1 两张表、第 6 节新测试文件、本报告，以及作者放置的三个未跟踪任务文档（`01-investigation.md`、`02-spec.md`、`03-dispatch.md`，未改未删）内。没有 `globals.css`、`Sidebar.tsx`、书斋/工作室文件、依赖清单或规格/调查的改动。

### 4.6 CLAUDE.md 大小（第 6 条）

```text
wc -c CLAUDE.md
69219 CLAUDE.md
```

≤ 69,300。新节 193 字节 ≤ 260 字节。

### 4.7 两个开关都不设（第 7 条）

手工脚本（清掉 `FIONA_NOVEL*`、`FIONA_DISCUSS*`、`FIONA_SONG*`）：

```text
tools_is_constant: True
tool_names: ['get_weather', 'plan_travel', 'plan_route', 'get_hot_topics', 'generate_image']
intent_system_is_today: True
intent_system_bytes: 8423
```

对应用例均在最终全量中通过：

- `test_discuss_chat_claude.py::test_all_switches_off_return_the_constant_object`
- `test_discuss_chat_platform.py::test_intent_system_content_matches_switches`

真实浏览器走查按规格由作者完成，本次未跑。

## 5. 未完成或需人工确认

- 规格第 8 节要求的真实浏览器走查（平台分身看进展/成果；Claude 分身出任务卡、去建群预填、卡片变已建群；意见卡送出与重复点击；删群后的卡片表现；刷新重建；关开关后旧卡可用）由规格作者执行，本次只做了离线测试与静态检查。
- 新建测试 `test_discuss_chat_cards_unit.py` 中原有两处断言（删群后 `group_id` 仍保留）与规格 4.9.3 冲突，主代理在验收时改为 `None`；这是本次新增的测试文件，不属于「既有测试一字不改」的范围。
- `read_progress` 原先只从 `service.detail` 的 200 条窗口取尾部；主代理补了超过 200 条时的继续翻页，确保「最近 8 条」是真正的最近 8 条，并加了一条用例。
- 两个聊天开关对非 `1` 的非法值按关闭处理，不告警；DEPLOYMENT 的措辞按此实现写（每日上限变量仍按 `rate_limit` 既有规则「非法值回落默认并只告警一次」）。
- CLAUDE.md 因 260 字节限制只写开关名、入口文件和架构文档链接；完整数据流、隐私与清理写在 `docs/ARCHITECTURE.md`、README、PLAN 与 DEPLOYMENT。
- 未调用任何真实模型、未访问外网、未读真实 `.env`/数据库；所有测试使用临时库与模拟传输。
