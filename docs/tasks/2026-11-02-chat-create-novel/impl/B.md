# 实现记录 B：后端 Claude 智能体（T3）

- 代理：B（workflow `parallel()` 派发）
- 负责文件：`backend/studio/sources.py`、`backend/services/claude_agent.py`、`backend/services/chat_service.py`、`backend/.env.example`
- 未触碰 `novel/drafts.py`、数据库、路由、前端、既有测试；未运行 git 写操作。

## 实现

1. `studio/sources.py` 紧邻 `novel_chat_enabled` 新增：
   `novel_create_enabled(username) = os.getenv("FIONA_NOVEL_CHAT_CREATE","0") == "1" and novel_chat_enabled(username)`。
2. `claude_agent.py` 新增 `NOVEL_DRAFT_TOOL`；`client_tools_for_turn` 在 `list_novels/read_novel/start_film` 之后、写歌工具之前追加；新开关 0/未设/非法时返回值与对象同一性不变。
3. 执行分支 `elif name == "draft_novel"`：
   - 每轮 `draft_written` 计数器，第二次直接回文本「本轮已写过一份草稿，请直接回答主人」，不计错误；
   - `validate_draft_args` 失败 → 原文回灌 + `agent_tool_errors += 1`；
   - 草稿模块在 `draft_novel` 分支内普通延迟导入 `from novel.drafts import count_open_drafts, create_draft, validate_draft_args`（R1 后；v1.1 授权的 AST 分支放行这三个名字）；
   - 会话缺失时懒解析 `resolve_chat_conversation`；
   - `count_open_drafts >= 50` → 「未使用的草稿太多，请先到书斋建书或删除」，不建草稿；
   - 成功 → `create_draft`、卡片（`subtype=novel_draft`、两条 points、`draft_id`、`url=/novels/new?draft=<id>`、`error=False`）、SSE `append=True`、正文 `［卡片：…］`、`delivered=True`、`state.novel_draft_id=id`；
   - 不设置 billable、不扣草莓、不建 `novels` 行，仍占 4 次工具名额。
4. `ChatState.novel_draft_id`；`_save_response` 传给 `save_message`。
5. `.env.example` 小说段新增 `FIONA_NOVEL_CHAT_CREATE=0` 与开关说明；未改「卡片不落库」行。

## 自检

- `py_compile` 三文件退出码 0。
- `tests/test_novel_chat.py tests/test_claude_agent_runtime.py tests/test_song_agent_tools.py` → 117 passed。
- `tests/test_claude_agent_docs.py` → 13 passed。
- 补充回归 `test_novel_p1_api.py`、`test_claude_agent_integration.py`、`test_claude_agent_r1_integration.py`、`test_byok_chat.py` → 142 passed。
- 临时开关矩阵与执行分支脚本通过（含对象同一性、危机/白名单、二次调用、50 上限、异常路径）。

## 决定与风险

- 第二次调用判断放在参数校验之前，确保「直接回答」语义。
- 读库异常按「书斋草稿暂时不可用」计一次工具错误。
- 新开关为 0 时 `client_tools_for_turn` 的既有返回路径与请求逐字节不变；`CLAUDE_CLIENT_TOOLS` 未动。
