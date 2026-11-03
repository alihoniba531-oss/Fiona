# 返修单 R1：建表无条件、去掉 importlib 绕行（2026-11-03）

你首轮报告里「需人工确认」的第 2、3 条，裁决如下；规格已升 v1.1（`02-spec.md` 开头、§2.3、§4.1、§5.7 有改动说明），以 v1.1 为准。

## 裁决

1. **`novel_drafts` 建表回到规格 T1.1 的「无条件」**。「开关开启才建表」不接受：库结构不能随环境变量变化，`table_exists` / `ensure_schema` 这类守卫会把问题推到运行期。既有测试 `backend/tests/test_studio_sources_readonly_integration.py` 的表集合锁，**授权改一处**：`:28-29` 的集合加入 `"novel_drafts"`。改完该文件所有用例必须仍绿（`novel_table_bytes()` 把草稿表也纳入快照，三条聊天意图不会写它）。
2. **`claude_agent.py` 不许用 `importlib` 绕 AST 锁**。同一测试文件**授权改第二处**：`:193-195` 的 `elif node.module and node.module.startswith("novel."):` 分支改成——`novel.runner` 只许 `{"is_editing"}`，`novel.drafts` 只许 `{"validate_draft_args", "create_draft", "count_open_drafts"}`，其他 `novel.*` 仍 `assert False`。然后 `claude_agent.py` 用普通的 `from novel.drafts import validate_draft_args, create_draft, count_open_drafts`（放在 `draft_novel` 分支内部的延迟导入，与同文件 `from studio.gate import allow_studio` 的写法一致），删掉 `from importlib import import_module` 与 `import_module("novel.drafts")`。
3. 这个测试文件**只许改这两处**，`git diff -U0 HEAD -- backend/tests/test_studio_sources_readonly_integration.py` 必须恰好两个 hunk；其余既有测试仍然零 diff。

## 本轮要做

1. `backend/database.py`：`init_db` 里紧跟 `NOVEL_TABLES_DDL` 循环之后**无条件**执行 `NOVEL_DRAFTS_DDL` 与 `NOVEL_DRAFTS_INDEX`；删掉 `novel_create_enabled()`（database.py 里的那个）、`_novel_drafts_table_exists()` 以及三处 `if await ..._table_exists(db):` 守卫（`clear_message_history`、`delete_account_data` 直接 `DELETE`）；DDL 上方那段「既有只读集成测试把 novel_* 表集合锁为 P1 的五张；因此仅在开关开启时建表」的注释改成一句「聊天建书草稿；与 novel_* 五表一起由 init_db 幂等创建」。`save_message` 里的 try/except 归属校验保留。
2. `backend/agent_store.py`：`delete_conversation` 去掉 `if await database._novel_drafts_table_exists(db):`，直接 `DELETE`。
3. `backend/novel/drafts.py`：删掉 `table_exists`、`ensure_schema`；`create_draft` 不再补建；`get_draft` / `count_open_drafts` / `consume_draft` 不再判表。
4. `backend/novel/service.py`：去掉 `table_exists as novel_drafts_table_exists` 的导入与 `delete` 里的守卫，直接 `UPDATE`。
5. `backend/services/claude_agent.py`：按裁决 2 改导入。
6. `backend/tests/test_studio_sources_readonly_integration.py`：只改裁决 1、2 的两处。
7. 新测试 `test_novel_chat_create.py`：补一条——`FIONA_NOVEL_CHAT_CREATE` 未设置时 `init_db` 后 `novel_drafts` 表也存在（`sqlite_master` 查询）；如有「开关关闭时表不存在」的旧断言，删掉它。
8. 文档五份 + `CLAUDE.md`：把「表在开关开启时由 `init_db` 幂等创建（关闭时既有 `novel_*` 表集合保持不变）」改为「表由 `init_db` 幂等创建」；保留「卡片不落库」子串，`tests/test_claude_agent_docs.py` 仍绿。
9. 重跑规格 §5 全部（§5.7 按 v1.1 写法），`03-report.md` 追加「R1 记录」（裁决、改了什么、§5 各条实际输出末行、`git diff -U0` 那两个 hunk 原文），`impl/主代理.md` 追加本轮记录。

## 不要做

- 不动前端文件（C、D 两组）与其他文档内容；不改 `CLAUDE_CLIENT_TOOLS`；不新增依赖；git 只读。
- 不得调用 subagent / subagent_fork / workflow，主代理直接做。

最终回复：改了哪些文件、两处授权改动的 diff 原文、§5 各条末行、未完成或需人工确认的地方。
