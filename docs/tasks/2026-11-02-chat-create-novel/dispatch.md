# 派单：聊天建书（Claude 智能体把聊天里定下的小说设定送进书斋）

你是实现方。当前目录是 Fiona 仓库的专用 worktree（分支 `feat/chat-create-novel`，基线 `0ca95af`），`backend/.venv` 与 `frontend/node_modules` 已就位，不要重装、不要 `npm ci`。规格是 `docs/tasks/2026-11-02-chat-create-novel/02-spec.md`（v1.0，唯一依据），事实表 `01-investigation.md` 可当证据读。**先通读规格全文再动手。**

## 白名单（只许改 / 新增这些，其他一个字节不许动）

后端：`backend/database.py`、`backend/agent_store.py`、`backend/novel/drafts.py`（新）、`backend/novel/service.py`、`backend/routers/novel.py`、`backend/studio/sources.py`、`backend/services/claude_agent.py`、`backend/services/chat_service.py`、`backend/.env.example`
前端：`frontend/components/NovelDraftCard.tsx`（新）、`frontend/components/ChatBubble.tsx`、`frontend/lib/useConversations.ts`、`frontend/app/page.tsx`（**按字节读写、保留开头 BOM `ef bb bf`**，不要用会重写整文件的编辑工具）、`frontend/components/novel/NovelWizard.tsx`、`frontend/lib/novels.ts`
文档：`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`（只按规格 §4.4 追加 / 同步）
新测试：`backend/tests/test_novel_chat_create.py`、`backend/tests/test_novel_chat_create_frontend.py`
报告：`docs/tasks/2026-11-02-chat-create-novel/03-report.md`、`impl/<代理名>.md`

**既有测试一字不改**（输入、断言、夹具都不改，新测试放新文件）；`CLAUDE_CLIENT_TOOLS` 常量不动；新开关 `FIONA_NOVEL_CHAT_CREATE` 为 0 时所有既有路径逐字节不变；不新增依赖；git 只做读操作（不 commit、不 stash、不 checkout）。

## 并行方式（硬规矩）

用工作流（`workflow` 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好；同一文件及其测试只归一个代理；每个 agent 的任务说明必须自包含（代理看不到你的对话，把规格里对应的 T 条款原文和白名单贴进去），并写明**不得调用 subagent / subagent_fork / workflow**；代理失败先读结果再决定，不许盲目重派；主代理只做拆分、派发、汇总、白名单检查、门禁、报告。建议拆分：

- A 后端数据层：`database.py`、`agent_store.py`、`novel/drafts.py`、`novel/service.py`、`routers/novel.py`（规格 T1、T2）
- B 后端智能体：`studio/sources.py`、`services/claude_agent.py`、`services/chat_service.py`、`.env.example`（T3，`novel/drafts.py` 的函数签名按规格 T1.2 约定调用，A 负责实现）
- C 前端聊天：`NovelDraftCard.tsx`、`ChatBubble.tsx`、`useConversations.ts`、`page.tsx`（T4、T5）
- D 前端向导：`NovelWizard.tsx`、`lib/novels.ts`（T6）
- E 文档：六份文档（§4.4；注意保留子串「卡片不落库」）

四个实现代理回来后，由主代理写两个新测试文件（§4.5，每一项都要有断言，自检要真的能让坏副本红）、跑验收、写报告。报告开头列拆分表，如实列出全部派出过的代理。

## 验收（规格 §5 全部 8 条，原始输出贴进报告）

pytest 在 `backend/` 下：`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider …`；全量约 5 分钟，用后台任务跑完再记结果，`passed = 7863 + 新增用例数`、0 failed、0 skipped。npm / npx 前 `export npm_config_cache=/tmp/fiona-npm-cache`。HEAD 对照用 `git archive HEAD | tar -x -C <mktemp 目录>`，只拷两个新测试进去跑（要把 `backend/.venv` 用当前 worktree 的解释器路径跑，`frontend/node_modules` 用 `cp -cR` 克隆进去，否则前端渲染用例会 skip）。§5.8 的真实走查你做不了（没有真实 Key、不许起用户端口），写明留给派单方。

## 变更总结（最终回复必须有这五项）

1. 修改了哪些文件（与白名单逐一对照，列出未动的白名单文件）；
2. 实现了哪些功能；
3. 与规格 T1–T6、§4.4、§4.5 的逐项对应；
4. 测试结果（§5 每条的实际输出末行）；
5. 未完成或需人工确认的地方。

何时停下来问：见规格 §6。只有规格与源码事实矛盾才停；只影响「怎么实现」的自行决定并写明理由；任何情况不回滚已完成的工作。报告与 impl 记录里不要写本机绝对路径。
