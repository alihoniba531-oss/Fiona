# 只读调查:为「聊天建书(Claude 智能体从聊天建立书斋小说)」准备规格事实表

你是只读调查员。当前目录是 Fiona(FastAPI + SQLite 后端 `backend/`,pytest;Next.js 16 + React 19 前端 `frontend/`,tsc / eslint)。之后会有人根据你的事实表写实施规格,再交给执行者实现。**你不实现任何东西,只调查、只汇报事实。**

## 原始需求

用户在聊天里对自带的 Claude 模型说(2026-11-02 截图原话):「长篇小说,宋朝背景,少年到中年类型的武侠小说。然后帮我去我的书斋里面进行」。模型只在聊天里搭了框架,没有进书斋。用户反馈原话:「现在我的聊天主模型无法与我的书斋进行互通」。

用户已接受的方案(规格作者提案原文,用户回复「第 2 条写规格」):「给聊天加一个「建书」工具,模型把聊天里定下的题材、背景、人物写成简报,调用书斋的建书接口,回你一张卡片,点开就是那本书的工作台;是否开始写、用哪种推演方式仍在书斋里确认,因为写作是按章扣费的,不能让模型代扣。」

约束:不新增依赖;不改小说工坊既有建书接口的语义与计费;不得从聊天触发任何扣草莓的步骤;既有测试的输入、断言与夹具一字不改(新测试放新文件);CLAUDE.md 里关于 Claude 智能体工具数、写歌工具、聊天读小说的陈述有测试锁定,要查清。

## 工作规则

- 只读。不要修改任何文件,不要尝试绕过沙箱。
- **不得调用 subagent / subagent_fork / workflow 工具**,全部由你自己完成。
- 沙箱是 read-only,不能写文件,所以**事实表直接写在你的最终回复里**。
- **只看当前目录。** 不读取、不列出、不 `cd` 进当前目录之外的路径(例外:系统命令本身、`node_modules` 等依赖源码、系统临时目录)。git 只看当前 HEAD 及其祖先,不看其他分支、其他 worktree。
- 可以运行只读命令(grep、rg、sed -n、cat、ls、git log/show/grep 等);构建产物在 `backend/.venv` 与 `frontend/node_modules`,可直接跑既有测试观察环境(单次不超过 5 分钟):后端在 `backend/` 下 `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider <文件>`;前端 `cd frontend && npx tsc --noEmit`。被拒绝或 skip 的要贴原文输出。
- 仓库里 `docs/tasks/` 有历次任务的规格、实施报告和复核记录(写歌工具见 `docs/tasks/2026-10-15-song-agent*`,聊天读小说见含 `novel-chat` / `novel_chat` 的任务目录,用 `ls docs/tasks` 找),`CLAUDE.md` 是当前约定,可以当证据读。
- **篇幅上限约 3 万字**;每条原文最多 5 行;同一件事只写一次。宁可在「未核实清单」里点名,也不要堆砌整段代码。

## 输出格式

按下面的题号组织。每条事实一行编号,格式:

```
F<题号>.<序号> [已核实|推断] 一句话陈述
  证据:<文件路径>:<起行>-<止行>
  ```
  <最多 5 行原文>
  ```
```

- 「已核实」只用于你读到原文或实测过的;其余一律标「推断」并写明依据。
- 回答「没有」「不适用」「未找到」时,必须附所用的搜索命令和命中条数,例如:`rg -n "xxx" backend frontend` → 0 条。

## 必答题

**Q1 需求定位与调用链**:(a) Claude 智能体的客户端工具是怎样定义、按轮次追加(`client_tools_for_turn`)、执行与回灌的(`backend/services/claude_agent.py`,含 `_novel_tool_params`、`_tool_result_text`、工具结果如何变成聊天卡片);写歌四个工具与聊天读小说三个工具各自的开关、白名单、每轮上限;(b) 书斋建书的完整链路:`routers/novel.py` 的 `workshop_user` 门控 → `service.create` → 落库 → 之后状态机(`novel/runner.py`)什么时候开始跑、谁触发、哪一步开始扣草莓;(c) 平台(非 Claude)聊天的小说意图(`intent_router.py` 的 `NOVEL_INTENTS`、`chat_service.py` 的分发)怎样接入。

**Q2 输入输出与分支**:`service.CreateNovel` 的全部字段、类型、默认值与校验(`validate_selection`、`estimate`);`service.create` 的每个分支(并发限制、每日上限、余额检查、是否立即进入 `setup_running` 并发起付费推演、失败怎么退);`detail` 返回结构;前端 `lib/novels.ts` 的 `NovelCreateInput` 与向导 `components/novel/NovelWizard.tsx` 三步各收集什么、默认值是什么、哪些是必填。

**Q3 既有测试怎样搭环境**:`test_claude_agent_*.py`、`test_novel_chat*.py`、`test_novel_p1_api.py`、`test_novel_p1_billing.py` 怎样搭环境(临时库、假传输、环境变量、DEV_MODE、白名单),怎样模拟 Claude 的 tool_use 回合与工具结果,怎样断言请求体里的工具表。

**Q4 现状与需求的差距**:现在从聊天到书斋只有哪些路径;「建书」缺哪几段(工具定义、参数→`CreateNovel` 的映射、调用点、卡片、落库字段、刷新重建、前端渲染、文档)。

**Q5 辅助函数与夹具**:可复用的测试辅助(模拟 Claude 流、构造 ctx/state、建临时用户与余额、开关补丁)的名称、位置、签名、是否导出。

**Q6 导入、导出、构建与测试收集**:新后端/前端文件放哪、怎么命名才被收集;tsc / eslint / pytest 命令;`CLAUDE_CLIENT_TOOLS` 的个数在哪些测试/文档里被锁定(贴断言原文)。

**Q7 数据与状态**:`messages` 表与写歌卡片相关的列(`song_project_id`)怎样写入、前端刷新后怎样按它重建 `SongProjectCard`;小说没有对应列时,聊天消息怎样携带「某本书」的引用(现有 `novel_*` 工具结果落库成什么);`novels` 表结构;删号/删会话/清空历史对这些引用的处理。

**Q8 运行环境与沙箱限制**:workspace-write 沙箱与 worktree 下跑这些测试会不会 skip / 失败,条件在哪。

**Q9 平台行为**:聊天页嵌入书斋的方式(`novel-drawer` iframe `/novels?embed=1`、`novelHref`、`data-shell`);从聊天卡片跳到某本书的工作台,现有组件(写歌卡、`NovelFilmDialog`、工作室提醒 chip)是怎么做跳转/打开抽屉的,贴原文。

**Q10 恒真风险**:针对「工具只在开关+白名单下追加」「不扣费」「卡片刷新后仍在」「参数校验」四条,新测试可能的恒真/假阳性写法与依据。

**Q11 区分力怎么证明**:每条需求对应的变异(改哪一行、改成什么)与期望的红绿。

**Q12 其他规格作者需要知道的**:每轮 4 次客户端工具、整轮预算、工具结果文本上限、提示词前缀缓存(改提示词会否破坏缓存与既有逐字节断言)、隐私条款(建书参数会发给谁)、CLAUDE.md / README / docs 哪些段落要同步。

**Q13 规格会依赖的「不存在」**:没有的检查、分支、调用者、保护(如:建书接口没有并发锁?没有同名去重?聊天侧没有防止一轮建多本?`novel_to_film` 已有的「优先复用未归档项目」逻辑有没有可照搬的去重)。每条附搜索命令和命中条数。

**Q14 每条断言的取值**:Q10/Q11 里每条断言在正确与错误实现下取值是否真的不同;取值来自环境的说明环境影响。

**Q15 结构与落点**:写歌工具(`backend/song/`、`routers/songs.py`、`SongProjectCard.tsx`、`lib/songs.ts`)与聊天读小说(`novel/sources` 或 `studio.sources`、`_novel_tool_params`)各是怎样分层与命名的;新「建书」工具最自然的落点是哪几个文件;贴落点文件的骨架(导出与函数签名,不贴实现);那里已有的重复或别扭之处。

**最后一节「未核实清单」**:列出你没能核实、需要人工确认的点。
