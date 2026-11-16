# 讨论群第三期复核返修第 1 轮报告

规格：`docs/tasks/2026-11-15-agent-group-chat/02-spec.md` 末尾「v1.2 修订」。复核：同目录 `04-review.md` 第 4、5 节。基线 `eb9ec55`，分支 `feat/agent-group-chat`。本轮不 commit，不 stash/checkout/reset。命令均带 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

## 1. 拆分表与改动文件

| 代理 | 负责 | 允许文件 / 产出 |
|---|---|---|
| `chat-v12` | v1.2 4.3 第 4/5/6 条；第 16 条 | `backend/discuss/chat.py`、`test_discuss_chat_readonly.py` |
| `chat-service-v12` | v1.2 4.5 第 4 条；第 16/17 条平台部分 | `backend/services/chat_service.py`、`test_discuss_chat_platform.py` |
| `off-turn-test` | v1.2 6.15 / 复核必须修复 1 | 新 `test_discuss_chat_off_turn.py` |
| `docs-v12` | v1.2 4.11；第 17 条文档部分 | `docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、`test_discuss_chat_docs.py` |
| `cards-empty-task-test` | v1.2 6.17 的空串 `task_id` | `test_discuss_chat_cards_api.py` |
| 主代理（本人） | 拆分派发、集成、自检、验收、本报告 | 本报告 |

### 1.1 实现改动

- `backend/discuss/chat.py`
  - `resolve_group`：去空白/去书名号后整体是 32 位十六进制、又不是本人任何群 id 时，返回「没找到这个讨论群，它可能已经删除。你有这些讨论群：…」，不回显该串；无群仍是「你还没有讨论群。」。
  - `_recent_messages`：翻页改用 `service.detail(username, group_id, after=上一页最后 id)`，最近 8 条的 `sender_name` 与群聊页完全一致，不再出现 `host/custom1/writer/policy`。
  - `_verdict_line`：`verdict` 为 `None` 或空 dict 时写「最新成果还没验收。」。
  - `read_output`：最新成果正文为空串时按「还没有成果」处理：`success=False`、`text == model_text == 《显示名》还没有成果。`、`continuation=None`。
- `backend/services/chat_service.py`
  - `_stream_discuss_intent`：`discuss_read` + `part=output` 时，成功按 v1.1 存/删；失败也删除位置；`progress`/`discuss_list` 不动。小说「继续读」段一个字符未动。
- `docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`：补隐私原文、v1.2 读取/查找/续读说明、50 个群已知局限。`README.md`、`CLAUDE.md`、`.env.example` 未改。

### 1.2 测试改动

12 个 `test_discuss_chat_*.py` 全部为本期新文件；269 → **289** 条（+20）：

| 文件 | 条数 | 本轮新增/加强 |
|---|---:|---|
| `test_discuss_chat_off_turn.py` | 3（新文件） | 三种应关组合的 Claude 整轮对照 |
| `test_discuss_chat_readonly.py` | 64（47→64） | 230 条翻页显示名、32 位 id 说明、未验收、空成果 |
| `test_discuss_chat_platform.py` | 60（58→60） | 失败删位置、失败后续读回落、crisis normalize |
| `test_discuss_chat_docs.py` | 24（18→24） | 三份文档隐私句、ARCH 清理原文、PLAN 50 群 |
| `test_discuss_chat_cards_api.py` | 13（12→13） | 空串 `task_id` 422 且不建群 |
| `test_discuss_chat_claude.py` | 38 | 上一轮工具定义/顺序用例保留 |
| `test_discuss_chat_cards_unit.py` | 26 | 上一轮 K1 保留 |
| `test_discuss_chat_db.py` | 15 | 上一轮 D4/D5/D21/D22 保留 |
| `test_discuss_chat_frontend.py` | 7 | 上一轮 F11/F52/F53 保留 |
| `test_discuss_chat_card_components.py` | 16 | 上一轮 F26/F31/F34/F35 保留 |
| `test_discuss_chat_prefill.py` | 16 | 上一轮 F43 保留 |
| `test_discuss_chat_switches.py` | 7 | 未改 |

既有测试（基线 `eb9ec55` 中就有的文件）本轮一字未改；`test_empty_states_settings_privacy.py` 仍是此前授权的两处 7→8。

## 2. 新用例各钉住什么

- **Claude 整轮对照（6.15）**：在 `test_claude_agent_runtime.harness` 上跑真实 `stream_claude_agent`；先清掉四个讨论群变量跑对照轮，再分别设「CHAT=0/CARDS=1」「白名单外」「FIONA_DISCUSS=0」三种组合；模型第一轮乱调未下发的 `draft_discuss_task`。逐项比较请求（messages 与去掉 `deadline_seconds`/`control` 后的参数 JSON）、SSE 事件、`h.saves`；并对三种组合同样断言 `client_tools_for_turn(...) is CLAUDE_CLIENT_TOOLS`。
- **读进展显示名（6.16）**：230 条消息、4 种 sender 内部代号；最近 8 条逐条等于 `service.detail` 的 `sender_name` + 种类中文名 + 正文，且不含 `host · `、`custom1 · `、`writer · `、`policy · `。
- **未验收成果（6.16）**：`passed=False` 且 `verdict=None`/`{}` 时写「最新成果还没验收。」，不写「没通过」。
- **空成果（6.16）**：`content=""` 时 `success=False`、`《显示名》还没有成果。`、`continuation=None`，不出现「续读位置不对」。
- **32 位 id（6.16）**：大小写 hex 找不到时不回显该串，说明固定；本人无群仍「你还没有讨论群。」；真实 id 仍能选中。
- **失败删位置（6.16）**：平台读成果失败后位置删除，后续「继续读」不再走快捷续读。
- **空串 task_id（6.17）**：POST 建群带 `task_id: ""` 返回 422「任务卡不存在或已使用」，不建群；随后不带 task_id 建群仍 201。
- **crisis normalize（6.17）**：`FIONA_DISCUSS=1`、白名单、CHAT=1 时，`crisis=True` 下 `discuss_list`/`discuss_read` 都归 `{"intent": None}`，非危机仍放行。
- **文档（6.17）**：README/ARCHITECTURE/DEPLOYMENT 第三期隐私段各含两句隐私原文且各一次；ARCH 清理说明原文；PLAN 50 个群局限。

## 3. 自检表

共改坏 21 处，全部由 pytest 以 `failed`（非 `error`）发现；每处改坏后立即写回原文，未用 git stash/checkout/reset。

### 3.1 复核必须修复 1

| 改坏 | 结果 | 首条发现用例 |
|---|---|---|
| G1：`discuss_read` 只看 `FIONA_DISCUSS_CHAT`，不看白名单/主开关 | `failed`（2 failed） | `test_discuss_off_turn_matches_all_variables_absent[outside-whitelist]` |
| G2：`discuss_cards` 只看 `FIONA_DISCUSS_CHAT_CARDS` | `failed`（3 failed） | `test_discuss_off_turn_matches_all_variables_absent[chat-0-cards-1-whitelisted]` |

### 3.2 v1.2 实现（5 处）

| 改坏 | 结果 | 首条发现用例 |
|---|---|---|
| 翻页又用 `discuss_store.list_messages` 原始行 | `failed` | `test_read_progress_pages_past_detail_window_for_latest_messages` |
| 未验收又写「没通过」 | `failed` | `test_read_progress_with_empty_verdict_says_not_reviewed[None]` |
| 空成果又落到「续读位置不对」 | `failed` | `test_read_output_empty_content_is_treated_as_no_output` |
| 32 位 id 又原样写进说明 | `failed` | `test_resolve_group_unknown_32_hex_hides_the_id` |
| 读成果失败时不删位置 | `failed` | `test_discuss_stream_deletes_position_for_failure_and_leaves_progress_and_list` |

### 3.3 文档（5 处）

| 删掉 | 结果 | 发现用例 |
|---|---|---|
| README 私有记忆句 | `failed` | `test_third_phase_privacy_sentences_appear_exactly_once[README.md]` |
| ARCHITECTURE 私有记忆句 | `failed` | `test_third_phase_privacy_sentences_appear_exactly_once[docs/ARCHITECTURE.md]` |
| DEPLOYMENT 私有记忆句 | `failed` | `test_third_phase_privacy_sentences_appear_exactly_once[docs/DEPLOYMENT.md]` |
| DEPLOYMENT Claude 起草句 | `failed` | 同上 |
| PLAN 50 个群局限 | `failed` | `test_plan_documents_recent_fifty_groups_lookup_limit` |

### 3.4 首轮/返修第 1 轮代表性改坏（9 处，未放松）

| 改坏 | 结果 | 发现用例 |
|---|---|---|
| A4 讨论群工具排到写歌后 | `failed` | `test_discuss_read_then_cards_then_song_keep_the_exact_order` |
| P27 开关关时仍执行 | `failed` | `test_discuss_stream_switch_off_falls_back_without_execute` |
| R14 区分大小写 | `failed` | `test_resolve_group_prefers_exact_name_over_prefixed_groups` |
| R30 正好读完仍说还有后文 | `failed` | `test_read_output_chunk_boundaries_have_no_continuation` |
| K39 送出路由去掉限流 | `failed` | `test_send_note_card_route_allows_twenty_then_rate_limits` |
| D4 意见卡外键不核对归属 | `failed` | `test_save_message_drops_cards_owned_by_other_in_same_conversation` |
| F11 主页不传跳转函数 | `failed` | `test_page_chat_bubble_passes_open_discuss_once` |
| F52 送出用 PUT | `failed` | `test_discuss_card_requests_keep_get_and_post_and_exact_paths` |
| X6 `.env.example` 卡片开关上方无注释 | `failed` | `test_env_template_declares_chat_switches_and_daily_cap` |

## 4. 验收

### 4.1 前端（第 1 条）

- `npm run lint -- --max-warnings=25`：退出码 0；25 warnings、0 errors。
- `npx tsc --noEmit`：退出码 0，无输出。
- `npm run build`：退出码 0；`✓ Compiled successfully in 581ms`，`✓ Generating static pages (20/20)`。

### 4.2 新用例（第 2 条）

```bash
cd backend
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_chat_*.py
```

结果：`289 passed, 48 warnings in 9.68s`；0 failed、0 error、0 skip。

### 4.3 全量（第 3 条）

```bash
cd backend
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8985 passed, 48 warnings in 560.15s (0:09:20)`；0 failed、0 error、0 skip。`8985 = 8696 + 289`。

### 4.4 白名单（第 4 条）

`git status --porcelain --untracked-files=all` 中本轮变动只有：`backend/discuss/chat.py`、`backend/services/chat_service.py`、12 个 `backend/tests/test_discuss_chat_*.py`（含新增 `test_discuss_chat_off_turn.py`）、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、本报告。前端全部文件、`claude_agent.py`、`cards.py`、`intent_router.py`、`database.py`、`README.md`、`CLAUDE.md`、`.env.example`、规格、调查、复核报告均未改；作者放置的 `06-fix-review-r1.md` 未改。

### 4.5 既有测试 diff（第 5 条）

`git diff -- backend/tests` 仍只有此前授权的两处数字变化，本轮未改任何既有测试：

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

- 真实浏览器走查仍由规格作者执行；本轮只做离线测试、静态检查与全量回归。
- 复核提到的 `.cache/review/proposed_test_claude_off_turn.py` 在本工作树不存在，按复核第 4 节和 harness 重写；三种应关组合的整轮对照已覆盖。
- 在正确实现下，模型调用未下发的 `draft_discuss_task` 时本轮直接结束，第二个 FakeStream 不会被消费；这不影响对照的证明力，工具表在请求参数 `tools` 中，G1/G2 两种改坏都能被请求对照拦住。
- 未调用真实模型、未访问外网、未读真实 `.env`/数据库；临时脚本与结果文件在仓库外，已删除。
