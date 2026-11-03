# 实现记录 E：文档（§4.4）

- 代理：E（workflow `parallel()` 派发）
- 负责文件：`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`
- `.env.example` 由 B 负责；未触碰代码/测试；未运行 git 写操作。

## 实现

1. `CLAUDE.md`：
   - 已知局限改为「其余卡片不落库；写歌卡与书斋草稿卡例外：`messages` 新增可空 `song_project_id` 与 `novel_draft_id`…」；
   - 聊天读小说段后新增「聊天建书」段，覆盖独立开关、白名单、`draft_novel`、免费不建书、向导预填、主人确认、`novel_drafts`/`novel_draft_id`（列与表均由 `init_db` 幂等创建/补列）、五道迁移、四类清理、平台路径不支持、每轮一份/50 上限。
2. `README.md`：已知局限同步例外；小说工坊段新增「聊天建书」小段。
3. `docs/ARCHITECTURE.md`：已知局限同步；小说聊天段末尾加一句聊天建书架构说明。
4. `docs/DEPLOYMENT.md`：只同步「卡片不落库」句，说明写歌卡与草稿卡例外及 `novel_draft_id`。
5. `PLAN.md`：只同步已知局限句。
- 五份均保留子串「卡片不落库」；未改第 18 行「5 个客户端工具」。

## 自检

- `tests/test_claude_agent_docs.py` → 13 passed。
- 五份文档均含「卡片不落库」；`CLAUDE.md`/`README.md` 含开关、工具、表、列；`ARCHITECTURE.md` 含聊天建书与列。
- 无本机绝对路径；`git diff --check` 干净。

## 决定与风险

- `GET /novels/drafts/{id}` 的本人隔离/404 细节未写进文档，规格 §4.4 未要求。
- 文档测试读取 `.env.example`，最终由主代理在全部改动后复跑。
