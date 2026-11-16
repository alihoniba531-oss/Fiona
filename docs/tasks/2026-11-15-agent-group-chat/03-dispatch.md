# 派单说明：讨论群第三期（分身聊天互通）

请实现 `docs/tasks/2026-11-15-agent-group-chat/02-spec.md`（规格 v1.0，作者已确认）。先把规格从头到尾读一遍，再读同目录的 `01-investigation.md`（写规格前的调查，A–J 十节，带路径与行号；标「推断」的条目没有实跑，以你读到的代码为准），然后动手。

## 一、工作区现状

- 分支 `feat/agent-group-chat`，HEAD 是 `eb9ec55`，与 main 一致。
- `git status --porcelain --untracked-files=all` 现在只有三个未跟踪文件：`01-investigation.md`、`02-spec.md` 与本说明 `03-dispatch.md`，都是规格作者放的，不要改、不要删。
- 基线（规格作者在本提交上实测）：前端 lint 25 个警告、0 个错误；`npx tsc --noEmit` 无输出；`npm run build` 成功；后端全量 `8696 passed`，0 跳过。

## 二、规矩

1. 允许新增或修改的文件只有规格 4.1 的两张表、第 6 节的新测试文件，加上报告（规格第 9 节）。别的文件一律不动。
2. 既有测试的输入、断言与夹具一字不改，新测试放新文件。唯一的例外是规格「作者已定」第 2 条：`backend/tests/test_empty_states_settings_privacy.py` 里那两处数字 7 改成 8，别的都不动。
3. 这次要改的几个文件被很多既有测试按源码文字锁着。动手之前，先读调查 H 节列出的那些既有用例，弄清它们断言了什么，尤其是：
   - `backend/services/claude_agent.py`：什么都没开时必须原样返回 `CLAUDE_CLIENT_TOOLS` 这个对象；只开小说或写歌时工具的有序列表不变；新工具名不能落到分发链最后的 else 分支。
   - `backend/intent_router.py`、`backend/services/chat_service.py`：讨论群关着时，意图识别的提示词与调用形状逐字节不变。
   - `backend/database.py` 的 `save_message`：三行注释标记之间、以及「书斋草稿」那段与 `INSERT INTO messages` 之间不能插入新代码；新校验放在「写歌」那段之前。
   - `frontend/app/page.tsx`：两段 `const card: CardData = {…}` 各拷一次新字段；从 `// 旅行规划卡：` 到 `if (data.done)` 的尾段一个字符都不能动；讨论群抽屉的 `src="/discuss?embed=1"` 字面量不变；文件以 UTF-8 BOM 开头，保存时保留。
   - `frontend/components/ChatBubble.tsx`：恰好两个 `<ChatCard … />` 标签，标签内不能出现 `>`。
   - `frontend/components/discuss/`、`frontend/app/discuss/`、`frontend/lib/discuss.ts`、`frontend/lib/discussLogic.ts` 会被 `test_discuss_frontend_guards.py` 整目录扫描（不加粗、`discussLogic.ts` 只能 `import type`、返修时钉住的那些类名与写法）。
   - `CLAUDE.md` 现在 69,025 字节，上限 69,300。
4. 界面上的中文文案与回灌给模型的固定文案以规格为准，一个字都不要改（测试会按原文断言）。
5. 不 commit / stash / checkout / reset；不装依赖；不读 `.env`、`.env.local`、数据库文件；不访问外网；不调用真实模型。临时脚本放在仓库外的临时目录，用完删掉。
6. 什么时候停下来问：见规格第 7 节。任何情况不回滚已完成的工作。

## 三、怎么并行

用工作流（workflow 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好。

- 先单独做完「地基」：规格 4.2（开关函数）、4.3（`backend/discuss/chat.py`）、4.4（每日上限）、4.7 第 1–3 条（两张表、`messages` 两列、`save_message`）、`backend/discuss/cards.py` 的函数签名，以及前端 `frontend/lib/discuss.ts` 的类型与请求函数、`frontend/lib/discussLogic.ts` 里预填用的纯函数。其余任务都依赖这些名字；做完再并行派出其余任务。
- 同一个文件及其测试只归一个 agent。下面这些文件各自只能由一个 agent 改：`backend/services/claude_agent.py`；`backend/services/chat_service.py` 与 `backend/intent_router.py`（归同一个）；`backend/database.py` 与 `backend/agent_store.py`（归同一个）；`backend/discuss/service.py`、`store.py`、`routers/discuss.py`（归同一个）；`frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/lib/useConversations.ts`（归同一个）；两个卡片组件；新建页预填；六份文档与设置页隐私句。
- 每个 agent 的任务说明必须自包含：写明规格与调查的路径、它负责的章节号、它可以改的文件清单、它依赖的函数名与类型从哪个文件读、它必须先读哪些既有用例；并写明「不得调用 subagent / subagent_fork / workflow」。agent 看不到你的对话。
- agent 失败时先读它的结果再决定，不要盲目重派。
- 你自己只做拆分、派发、汇总、白名单检查、验收与报告。

## 四、验收与报告

- 规格第 8 节的第 1–7 条逐条实际执行，把命令与输出摘要写进报告。真实浏览器里的走查由规格作者做，你不用跑，但实现要满足。
- 全量测试里如果有失败，先判断是不是你的改动碰到了既有的结构锁（调查 H 节）；是的话改实现去满足既有测试，不要改既有测试。
- 报告写进 `docs/tasks/2026-11-15-agent-group-chat/impl/report.md`，内容见规格第 10 节，开头是拆分表（如实列出派出过的全部 agent）。不写本机绝对路径。
- 最后一条回复给出变更总结五项：修改了哪些文件；实现了哪些功能；与规格第 5 节任务清单的逐项对应；测试结果；未完成或需人工确认的地方。
