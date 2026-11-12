# 派单：案头第一期

你在 Fiona 仓库的一个专用工作树里，分支 `feat/desk-board`，基线是 main 的 `9adf34c`。

## 要做的事

**完整阅读 `docs/tasks/2026-11-10-desk-board/02-spec.md`**（约 650 行，必须从头读到尾，不能只读开头），然后按它实现。设计参考稿在同目录的 `design/` 下。背景见 `01-brief.md`（只作了解，以规格为准）。

规格里你实测到的事实优先于规格的断言：发现不符就停下来说明，不要照着错的写。

## 环境

- Python：规格里写的 `python` 在这里是 `backend/.venv/bin/python`。例：`cd backend && .venv/bin/python -m pytest -q`。全量大约 5 分钟。
- Node 依赖已经在 `frontend/node_modules`。
- 不得运行 `pip install`、`uv`、`npm install`、`npm ci`，不得改任何依赖文件。
- 不得 `git commit`、`git stash`、`git checkout`、`git reset`、`git clean`、`git worktree`，不要切分支。改动留在工作区里即可。
- 不访问网络。
- 任务目录下的 `01-brief.md`、`02-spec.md`、`03-dispatch.md`、`design/` 是派单前就存在的未跟踪文件，不是你的改动，**不要修改它们**；做白名单检查时把它们排除在外。
- 沙箱里个别依赖进程探测的既有用例可能被跳过。如实报告跳过的数量与原因，不要为此改任何既有测试。
- 改前端代码前按 `frontend/AGENTS.md` 的要求，先读 `frontend/node_modules/next/dist/docs/` 里与你要写的东西对应的文档。

## 硬规矩（规格里都有，这里再强调一遍）

1. 只许改规格第 6 节白名单里的路径。`backend/` 下除了新增 `backend/tests/test_desk_*.py` 之外一律不动。
2. 不得修改任何既有测试的输入、断言与夹具；新测试放新文件。
3. `frontend/app/page.tsx` 只许做规格 T3 列出的七处改动；文件开头的 BOM 与规格 2.2 的七条字面量必须原样保留。
4. 不得改 `components/novel/**`、`components/studio/**`、`lib/novels.ts`、`lib/studio*.ts` 等既有源码，只 import 复用。
5. 界面文字不加粗；颜色只用现有 CSS 变量；字号只用 `text-fs-*` 令牌；所有 `<dialog>` 用 `sourceDialogClass`。
6. 只有影响「做什么」时才停下来问（规格与事实矛盾、必须越出白名单、必须改既有测试、需要新依赖）。只影响「怎么实现、怎么验证」的事自己定，并在实施记录里写明理由。任何情况下不要回滚已经完成的工作。

## 并行方式

用工作流（`workflow` 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好。每个 agent 的任务说明必须自包含（agent 看不到你的对话，要把它需要的规格段落、签名、文案、禁令原文贴给它，并告诉它规格文件的路径让它自己再读），并写明「不得调用 subagent / subagent_fork / workflow」。同一个文件及其测试只归一个 agent。agent 失败先读它的结果再决定，不要盲目重派。主代理只做拆分、派发、汇总、白名单检查、门禁与报告。

拆分建议见规格第 9 节的表。`lib/desk.ts` 的导出签名在规格 T1 里已经固定，视图组件之间没有相互依赖，所以 A–E 与 J 可以同时跑；F 等 A–E，G 等 F，H 等 B–E，I 等 G。

## 交付

全部做完后，逐条执行规格第 7 节的 9 条命令并记录实际输出，把实施记录写到 `docs/tasks/2026-11-10-desk-board/impl/主代理.md`（不写本机绝对路径、账号名、密钥），最后回复变更总结，五项缺一不可：

1. 改了哪些文件；
2. 实现了哪些功能；
3. 与规格第 5 节任务清单 T1–T9 的逐项对应；
4. 规格第 7 节每条命令的实际输出；
5. 没做完或需要人工确认的地方。

总结开头列拆分表，如实列出全部派出过的 agent 及其负责的文件。
