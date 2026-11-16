# 讨论群第三期门禁返修第 1 轮报告

规格：`docs/tasks/2026-11-15-agent-group-chat/02-spec.md` 的「v1.1 修订」。基线 `eb9ec55`，分支 `feat/agent-group-chat`。本轮不 commit，不 stash/checkout/reset。命令均带 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

## 1. 拆分表与改动文件

### 1.1 派出过的全部代理

| 代理 | 负责 | 允许文件 / 产出 |
|---|---|---|
| `chat-reader-v11` | v1.1 4.3 第 4、6 条；6 第 12、14 条；R14/R30/R38/R45 | `backend/discuss/chat.py`、`backend/tests/test_discuss_chat_readonly.py` |
| `platform-v11` | v1.1 4.5 第 4 条；6 第 13、14 条；P27 | `backend/intent_router.py`、`backend/services/chat_service.py`、`backend/tests/test_discuss_chat_platform.py` |
| `claude-assert-r1` | 补强 A4/A28/A29/A30，不改实现 | `backend/tests/test_discuss_chat_claude.py` |
| `cards-assert-r1` | 补强 K1/K22/K38/K39，不改实现 | `backend/tests/test_discuss_chat_cards_unit.py`、`test_discuss_chat_cards_api.py` |
| `db-assert-r1` | 补强 D4/D5/D21/D22，不改实现 | `backend/tests/test_discuss_chat_db.py` |
| `frontend-assert-r1` | 补强 F11/F52/F53，不改实现 | `backend/tests/test_discuss_chat_frontend.py` |
| `card-prefill-assert-r1` | 补强 F26/F31/F34/F35/F43，不改实现 | `test_discuss_chat_card_components.py`、`test_discuss_chat_prefill.py` |
| `docs-v11` | v1.1 4.11；X6；文档用例 | `README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`、`test_discuss_chat_docs.py` |
| 主代理（本人） | 拆分派发、集成、`.env.example` 误改恢复、自检、验收、本报告 | 本报告；两处临时误改恢复 |

### 1.2 实现改动（本单允许的实现文件）

- `backend/discuss/chat.py`
  - `resolve_group`：去空白；整体成对书名号只去一对再 `strip`；空查询规则不变；按 id → 显示名 `casefold` 精确（多个同名只列同名群）→ 显示名 `casefold` 包含查找。
  - `read_output`：成功返回 `group_id`；`model_text` 保留带数字的「还有后文，接着读请从 {offset} 开始。」；`text` 改为「还有后文，说『继续读』接着念。」；两者都在数据块外。
- `backend/intent_router.py`
  - 新增 `get_discuss_read_position` / `set_discuss_read_position`（`chat_slot_state`，`kind='discuss_read'`，30 分钟过期，`None` 删除）。
  - 新增 `discuss_read_position_is_newer`（按 `updated_at` 严格比较；小说位置缺失、过期、payload 坏或时间不可解析都视为没有）。
  - `DISCUSS_INTENT_PROMPT` 删除 `offset=6000` 示例，换成不带 offset 的示例；offset 说明补「一般省略，『继续读』由系统接着上次的位置读」。
- `backend/services/chat_service.py`
  - `_stream_discuss_intent` 在 `discuss_read` + `part=output` + `success` 时存位置；有 `continuation` 存 `{group, part:"output", offset}`，没有则删除；失败、progress、discuss_list 不动位置。
  - 在小说「继续读」段之前新增讨论群快捷续读：开关开、无图、整句匹配、有位置，且小说没开/没有小说位置/讨论群位置更新时，走 `stream_intent` 的 `discuss_read`；小说段本身未改。
  - Claude 路径直接走 `execute_intent`，不经过这里，不存位置。
- `README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`：按 v1.1 4.11 补续读、30 分钟、找群顺序、已知局限。`CLAUDE.md` 未改。

### 1.3 测试文件（全部为本期新文件）

11 个 `backend/tests/test_discuss_chat_*.py`。本轮从 221 条增至 **269 条**（+48）；其中：

- `test_discuss_chat_readonly.py` 47→56（v1.1 同名/书名号/group_id/提示/R14/R30/R38/R45）
- `test_discuss_chat_platform.py` 42→58（P27、v1.1 13/14、位置存取与新旧比较）
- `test_discuss_chat_claude.py` 35→38（A4/A28/A29/A30 完整工具定义与顺序）
- `test_discuss_chat_cards_unit.py` 25→26（K1）
- `test_discuss_chat_cards_api.py` 9→12（K22/K38/K39）
- `test_discuss_chat_db.py` 12→15（D4/D5/D21/D22）
- `test_discuss_chat_frontend.py` 5→7（F11/F52/F53）
- `test_discuss_chat_card_components.py` 10→16（F26/F31/F34/F35）
- `test_discuss_chat_prefill.py` 14→16（F43）
- `test_discuss_chat_docs.py` 15→18（X6、v1.1 文档）
- `test_discuss_chat_switches.py` 7→7（未改）

既有测试（基线 `eb9ec55` 中就有的文件）本轮一字未改；`backend/tests/test_empty_states_settings_privacy.py` 仍是上一轮授权的两处 7→8，本轮未触碰。

## 2. 补强用例钉住什么

### 2.1 26 处门禁改坏

| 编号 | 新增/加强的钉法 | 发现用例（均 `failed`） |
|---|---|---|
| A4 | 讨论群+写歌、小说+讨论群+写歌两种精确有序列表 | `test_discuss_read_then_cards_then_song_keep_the_exact_order`、`test_novel_then_discuss_then_song_keep_the_exact_order` |
| A28 | 四个工具逐字段等于规格定义，`required == ["part"]` | `test_discuss_tool_definitions_match_the_spec_field_by_field` |
| A29 | budget 属性 `minimum/maximum` 精确 | 同上 |
| A30 | 工具描述逐字等于规格 | 同上 |
| P27 | 开关关时 `_stream_discuss_intent` 交给 `stream_normal`、不调 `execute_intent` | `test_discuss_stream_switch_off_falls_back_without_execute` |
| R14 | 英文显示名大小写不敏感精确匹配 | `test_resolve_group_exact_name_is_case_insensitive` 等 |
| R30 | 正文恰好 6000/12000 时最后一段无 continuation/提示 | `test_read_output_chunk_boundaries_have_no_continuation` |
| R38 | `DATA_NOTICE` 与规格原文逐字比较（写死原文） | `test_data_notice_matches_spec_verbatim` |
| R45 | `model_text` 原样中文、无 `\u` 转义且可 JSON 还原 | `test_read_output_wraps_and_preserves_json_content` |
| K1 | request 9 字被拒、10 字通过 | `test_validate_task_args_request_minimum_is_ten_characters` |
| K22 | 危机文本送卡 400、文案同 `add_note`、无插话、`message_id` 仍 NULL | `test_send_note_card_rejects_crisis_text_like_add_note` |
| K38 | 群 round=3 时插话 `round == 3` | `test_send_note_card_uses_current_group_round` |
| K39 | 20 次 200、第 21 次 429 | `test_send_note_card_route_allows_twenty_then_rate_limits` |
| D4/D5 | 他人卡但 `conversation_id` 等于本人会话时，`save_message` 两列存 NULL | `test_save_message_drops_cards_owned_by_other_in_same_conversation` |
| D21/D22 | `PRAGMA table_info` 逐列核对 name/type/notnull/default/pk | `test_task_card_table_column_definitions`、`test_note_card_table_column_definitions` |
| F11 | `page.tsx` 的 `<ChatBubble` 块内 `onOpenDiscuss={openDiscussAt}` 恰一次、全文件恰一次 | `test_page_chat_bubble_passes_open_discuss_once` |
| F26 | 只有预算时精确整行 `预算 ${budget} 颗`；只有轮数时 `建议 ${maxRounds} 轮` | `test_task_card_copy_paths_classes_and_branches` 等 |
| F31 | catch 分支内 `setActionError(message);` 恰一次 | `test_note_card_copy_paths_classes_and_branches` 等 |
| F34 | 已读/未读精确表达式方向 | `test_note_card_copy_paths_classes_and_branches` 等 |
| F35 | 群名 `(group ? group.title : view.group_title)` 精确 | `test_note_card_copy_paths_classes_and_branches` 等 |
| F43 | `if (card.task.group_id) {` 分支内提示、else 分支才预填/提交 task_id | `test_form_reads_task_card_prefills_and_submits_task_id` 等 |
| F52/F53 | 三请求函数的方法与路径原文（GET task/note、POST send） | `test_discuss_card_requests_keep_get_and_post_and_exact_paths` |
| X6 | `.env.example` 三行各自紧邻上一行是中文专属注释 | `test_env_template_declares_chat_switches_and_daily_cap` |

### 2.2 v1.1 新用例

- 找群：精确同名优先（前缀群不干扰）、多个同名只列同名群、书名号去掉、书名号内空白、大小写不敏感。
- `read_output`：成功带 32 位 `group_id`，失败不带；`text` 提示无数字，`model_text` 保留数字；6000/12000 边界无续读提示；JSON 原样中文。
- 平台续读：位置 30 分钟过期、按会话隔离；三句续读短语逐段拼接等于原文；最后一段删位置；过期忽略；开关关、带图、非整句都不走；开关关时不读数据库；小说与讨论群位置并存取较新；只有小说位置保持原行为；Claude 直接 `execute_intent` 不存位置；续读照常计每日次数。
- 文档：README/ARCH/PLAN 的 v1.1 说明与 X6 紧邻注释。

## 3. 自检表

### 3.1 乙表 26 处（逐处改坏 → 跑全部 `tests/test_discuss_chat_*.py` → 还原）

26/26 均为 `failed`，无 `error`。

| 编号 | 改坏 | 结果 | 首条发现用例 |
|---|---|---|---|
| A4 | 讨论群工具移到写歌后 | `failed` | `test_discuss_read_then_cards_then_song_keep_the_exact_order` |
| A28 | read 工具 `required` 改 `[]` | `failed` | `test_discuss_tool_definitions_match_the_spec_field_by_field` |
| A29 | budget minimum 100→0 | `failed` | 同上 |
| A30 | 意见卡描述删「不会直接送进群」 | `failed` | 同上 |
| P27 | 开关关时仍执行 | `failed` | `test_discuss_stream_switch_off_falls_back_without_execute` |
| R14 | `needle = query`（区分大小写） | `failed` | `test_resolve_group_prefers_exact_name_over_prefixed_groups` |
| R30 | `<` 改 `<=` | `failed` | `test_read_output_chunk_boundaries_have_no_continuation` |
| R38 | 数据声明删尾句 | `failed` | `test_data_notice_matches_spec_verbatim` |
| R45 | JSON 去掉 `ensure_ascii=False` | `failed` | `test_read_output_wraps_and_preserves_json_content` |
| K1 | request 下限 10→9 | `failed` | `test_validate_task_args_request_minimum_is_ten_characters` |
| K22 | 送出时不查危机 | `failed` | `test_send_note_card_rejects_crisis_text_like_add_note` |
| K38 | 插话轮次恒 0 | `failed` | `test_send_note_card_uses_current_group_round` |
| K39 | 送出路由去掉限流 | `failed` | `test_send_note_card_route_allows_twenty_then_rate_limits` |
| D4 | 意见卡校验加 `OR 1=1` | `failed` | `test_save_message_drops_cards_owned_by_other_in_same_conversation` |
| D5 | 任务卡校验加 `OR 1=1` | `failed` | 同上 |
| D21 | materials 去默认值 | `failed` | `test_task_card_table_column_definitions` |
| D22 | group_title 可空 | `failed` | `test_note_card_table_column_definitions` |
| F11 | 删 `<ChatBubble>` 上的跳转函数 | `failed` | `test_page_chat_bubble_passes_open_discuss_once` |
| F26 | 只有预算时写成「建议 … 颗」 | `failed` | `test_task_card_copy_paths_classes_and_branches` |
| F31 | 删 `setActionError(message);` | `failed` | `test_note_card_copy_paths_classes_and_branches` |
| F34 | 已读/未读对调 | `failed` | `test_note_card_copy_paths_classes_and_branches` |
| F35 | 群名只用卡上旧名 | `failed` | `test_note_card_copy_paths_classes_and_branches` |
| F43 | `if (false)` 跳过已用卡判断 | `failed` | `test_form_reads_task_card_prefills_and_submits_task_id` |
| F52 | send 改 PUT | `failed` | `test_discuss_card_requests_keep_get_and_post_and_exact_paths` |
| F53 | task-cards 路径改 task_cards | `failed` | 同上 |
| X6 | 删卡片开关上方中文注释 | `failed` | `test_env_template_declares_chat_switches_and_daily_cap` |

### 3.2 v1.1 新实现 9 处（覆盖要求 8 类）

9/9 均为 `failed`，无 `error`。

| 改坏 | 结果 | 首条发现用例 |
|---|---|---|
| 去掉同名精确优先 | `failed` | `test_resolve_group_prefers_exact_name_over_prefixed_groups` |
| 不去书名号 | `failed` | `test_resolve_group_prefers_exact_name_over_prefixed_groups` |
| `read_output` 不返回 `group_id` | `failed` | `test_platform_output_hint_has_no_number_but_model_hint_does` |
| `text` 换回带数字提示 | `failed` | 同上 |
| 不存讨论群位置 | `failed` | `test_discuss_stream_keeps_state_free_and_saves_text` |
| 读完不删位置（存 `{}`） | `failed` | 同上 |
| 快捷续读去掉开关条件 | `failed` | `test_discuss_continuation_switch_off_never_reads_position` |
| 快捷续读去掉图片条件 | `failed` | `test_discuss_continuation_skipped_for_image_turn` |
| 新旧比较恒真 | `failed` | `test_discuss_position_roundtrip_ttl_expiry_and_recency` |

所有改坏均在仓库外脚本中施加，`finally` 写回原文；未用 `git stash/checkout/reset`。

## 4. 验收

### 4.1 前端（验收第 1 条，未改前端，确认没碰坏）

- `npm run lint -- --max-warnings=25`：退出码 0；`✖ 25 problems (0 errors, 25 warnings)`。
- `npx tsc --noEmit`：退出码 0，无输出。
- `npm run build`：退出码 0；`✓ Compiled successfully in 538ms`；`✓ Generating static pages (20/20)`。

### 4.2 新用例（验收第 2 条）

```bash
cd backend
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_chat_*.py
```

结果：`269 passed, 48 warnings in 9.50s`；0 failed、0 error、0 skip。

### 4.3 全量（验收第 3 条）

```bash
cd backend
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8965 passed, 48 warnings in 539.70s (0:08:59)`；0 failed、0 error、0 skip。`8965 = 8696 + 269`。

### 4.4 白名单（验收第 4 条）

`git status --porcelain --untracked-files=all` 中，本轮相对派单时的生产实现变动只有 `backend/discuss/chat.py`、`backend/intent_router.py`、`backend/services/chat_service.py`；测试变动只在 11 个 `backend/tests/test_discuss_chat_*.py`；文档变动只有 `README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`；新增只有本报告。`backend/.env.example` 在自检中曾被临时删掉卡片开关上方注释，验收前已按原文恢复，最终 diff 与派单时一致（仍只有上一轮新增的第三期配置段）；前端所有文件、`claude_agent.py`、`cards.py`、`database.py`、`CLAUDE.md`、规格与调查均未在本轮改动。作者放置的 `05-fix-r1.md` 未改。

### 4.5 既有测试 diff（验收第 5 条）

`git diff -- backend/tests` 仍只有上一轮授权的两行数字变化，本轮未新增任何既有测试改动：

```diff
@@ -123,8 +123,8 @@ def test_eight_privacy_paragraphs_appear_once_and_stay_unadorned():
     details_start = source.index("<details")
     details_end = source.index("</details>")
     fold = source[details_start:details_end]
-    assert fold.count("<p>") == 7
-    assert fold.count("</p>") == 7
+    assert fold.count("<p>") == 8
+    assert fold.count("</p>") == 8
```

## 5. 未完成 / 需人工确认

- 规格 v1.1 的真实浏览器走查由规格作者执行；本轮只做离线测试、静态检查与全量回归。
- 验收前发现 `.env.example` 的一条中文注释被并行自检临时改坏且未还原，主代理已按原文恢复并单跑 `test_env_template_declares_chat_switches_and_daily_cap` 通过；该文件最终与派单时逐字节一致（本报告不把这次临时改坏算作实现改动）。
- 平台快捷续读先判讨论群开关、再读位置；开关关着时测试确认 `get_discuss_read_position` 不会被调用。
- `read_output` 的 `data` 用 `if continuation else None`；`continuation` 只可能是正的下一段 offset，因此没有实际差异，测试覆盖了“读完删位置”。
- 未调用真实模型、未访问外网、未读真实 `.env`/数据库；临时脚本与结果文件在仓库外，已删除。
