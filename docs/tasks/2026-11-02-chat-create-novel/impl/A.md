# 实现记录 A：后端数据层（T1 / T2）

- 代理：A（workflow `parallel()` 派发）
- 负责文件：`backend/database.py`、`backend/agent_store.py`、`backend/novel/drafts.py`（新）、`backend/novel/service.py`、`backend/routers/novel.py`
- 未触碰其他文件；未新增测试；未运行 git 写操作。

## 实现

1. `database.init_db` 在 `song_project_id` 迁移后一行新增 `messages.novel_draft_id`；`novel_drafts` 表与 `idx_novel_drafts_owner` 索引在 `NOVEL_TABLES_DDL` 循环后**无条件**幂等创建，不写 `schema_migrations`。R1 已按 v1.1 撤销首轮的开关 gating 与运行期守卫。
2. 新建 `novel/drafts.py`：`validate_draft_args`、`create_draft`、`get_draft`、`count_open_drafts`、`consume_draft`，均为 async；title 1–60、seed 1–2000、整数只收真 int、缺省 50/70/2000、min≤max；`target_json` 读回坏 JSON 回落 `{}`。
3. `save_message` 新增 keyword-only `novel_draft_id`，非空时核对 `owner_username + conversation_id`，不匹配或异常存 NULL；INSERT 列补该列。
4. `clear_message_history`、`delete_account_data` 在同一事务删除本人草稿；`agent_store.delete_conversation` 在同一事务删除本会话草稿；顺序紧邻既有写歌清理。
5. `CreateNovel.draft_id`；`config = model_dump(exclude={'draft_id'})`；插入 `novels` 后、commit 前 `consume_draft`，失败 rollback 并 422「草稿不存在或已使用」；`service.delete` 同事务把草稿 `novel_id` 置回 NULL。
6. 新增 `GET /novels/drafts/{draft_id}`，只返回本人草稿，非本人/不存在 404；返回 `target` 已解析为 dict。

## 自检

- `py_compile` 五个文件退出码 0。
- 临时库脚本覆盖 init_db 幂等、五道迁移、表/索引/列、草稿 CRUD、坏 JSON、`save_message` 归属、`service.create` 消费/回滚、`service.delete` 复位、三类删除清理，输出 `ALL DRAFT CHECKS PASSED`。
- 既有定向测试：`test_agent_conversations.py`、`test_account_deletion.py`、`test_history_cleanup.py`、`test_novel_v2_compat.py`、`test_novel_router.py`、`test_health_and_startup.py`、`test_novel_p1_store.py`、`test_song_store.py`、`test_novel_p1_api.py`、`test_song_agent_tools.py`、`test_novel_chat.py`、`test_claude_agent_runtime.py`、`test_migrate_and_backup.py` 全绿。
- `git diff --check` 干净。

## 决定与风险

- 草稿默认值在 `drafts.py` 内维护，避免 `service` ↔ `drafts` 循环导入；`consume_draft` 顺带更新 `updated_at`。
- `service.create` 用真值判断 `draft_id`，空字符串视为未提供。
- 50 份上限不是原子计数；规格未要求并发原子化。
- **规格/源码事实冲突已由 R1 裁决**：T1.1 要求 `init_db` 无条件建 `novel_drafts`；v1.1 授权 `test_studio_sources_readonly_integration.py` 只改两处（表集合加入 `novel_drafts`；AST 分支放行 `novel.drafts` 三个名字）。本轮已恢复无条件建表，删掉 `table_exists`/`ensure_schema`/全部运行期守卫。
- 未实现「已消费草稿不能再被消息引用」；规格 T1.3 只要求归属与会话校验。
