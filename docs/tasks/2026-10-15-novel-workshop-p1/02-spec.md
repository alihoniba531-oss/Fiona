# 小说工坊 P1：后端（数据库、后台运行器、计费、接口）

> 任务等级：L3，涉及新增数据模型和新路由。本规格需经作者确认后才能派给实施方。
> 工作目录：Fiona 仓库，路径相对仓库根。基线分支见第 13 节待拍板项 D3。
> **本阶段只做后端**，不做前端页面（前端在 P2）。

## 0. 背景（必读）

Fiona 要新增「小说工坊」：用户只给一个故事思路，由多个智能体共同推演每章怎么写、何时收尾、何时完结；用户在关键节点拍板。目标是中篇（10–30 万字），并且方便改编成 AI 短剧。

P0 已经在 `backend/novel/` 写好一个离线原型，并用真实模型跑了 4 组实验，结论如下：

- **默认推演模式是 `critique`（主编出方案、顾问挑错）**。每章流程为：主编初案 → 顾问并行挑错（不打分，反转设计师必须给出替代走向）→ 主编定稿（逐条回应）。两轮盲读里，作者都选了这种模式；把多个提案合并的旧模式（merge）输给了主编独自构思。
- 故事圣经（锁定区 + 动态区 + 伏笔账本）、阶段感知、写到 85% 强制收尾、完结守卫、审校证据校验、档案员增量更新，这些机制在实验 B（12 章完结、伏笔全部回收）里都验证可用。
- 真跑成本：critique 模式约 ¥1.7/章，主编独自构思（solo）约 ¥0.8/章；写手用 `deepseek-flash`，主编用 Claude Sonnet 5.5。
- 引擎代码在 `backend/novel/`，包括 `agent_pool`、`schemas`、`bible`、`context`、`deliberation`、`writing`、`llm_router`、`fake_llm`、`report`，已有约 900 条离线测试。`run_store.py` 是给离线脚本用的文件存储。

**P1 的目标**：把这套引擎接进 Fiona 后端。用户登录后可以：

1. 建书，并自选智能体和模型；
2. 由后台按章自动推演和写作，在关键节点暂停等用户拍板；
3. 平台模型按调用扣草莓，用户自带 Key 的模型不扣；
4. 随时查看进度、正文和推演记录，可以暂停、继续、插话、改稿、确认完结、导出。

## 1. 修改范围

**新增**（全部放在 `backend/` 下）：

- `novel/store_db.py`：`DbStepStore`，基于 SQLite 的步骤存储。
- `novel/billing.py`：草莓价目、预扣、结算、退款。
- `novel/byok_bridge.py`：把用户自带模型转成引擎可用的调用。
- `novel/runner.py`：后台运行器，包括状态机、关卡和恢复。
- `novel/service.py`：给路由用的业务层。
- `novel/safety.py`：小说创作安全底线。
- `routers/novel.py`
- `tests/test_novel_p1_*.py`
- `docs/tasks/2026-10-15-novel-workshop-p1/03-report.md`

**修改**（只做最小插入，不重构）：

- `backend/database.py`
  - 在 `init_db()` 中，以 `CREATE TABLE IF NOT EXISTS` 新建第 3 节的表。**不新增迁移版本号**，`/health` 保持不变，做法参照 `USER_MODEL_CONFIGS_DDL`。
  - 在 `delete_account_data()` 的同一事务里，于删除 users 之前删掉所有小说表中属于该用户的行。
- `backend/main.py`
  - `include_router(novel.router)`。
  - 在 lifespan 启动阶段、`recover_interrupted_exchanges` 之后，调用小说运行器的恢复函数。
  - 关闭阶段先取消小说任务，再调用 `shutdown_background_tasks`。
- `backend/rate_limit.py`：在 `_DAILY_SETTINGS` 中新增 `novel_chapter`，环境变量为 `FIONA_DAILY_NOVEL_CHAPTERS`，默认 30；同时补上对应的中文文案。
- `backend/novel/llm_router.py`、`backend/novel/agent_pool.py`，以及运行时需要的其他 `novel/` 模块：只改第 4 节点名的地方。
- 文档同步，这是仓库约定（CLAUDE.md）：
  - `README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、`backend/.env.example`：写清新路由、环境变量、数据表，以及数据会发给哪些厂商。
  - `CLAUDE.md`：新增一个「小说工坊」小节。

**不得改动**：

- P0 离线脚本的行为：`python -m novel.pilot` 的四份配置在 dry-run 下的输出和步骤键必须与改动前一致。
- 已有的全部测试的输入和断言。
- 聊天、交流、BYOK 等现有功能的行为。

## 2. 技术约束

- Python 3.14，FastAPI + aiosqlite，不用 ORM，沿用现有手写 SQL 风格。**不新增依赖**。
- 所有模型调用都在后台 asyncio 任务里完成，HTTP 请求只负责启动、查询和下发指令，不阻塞等待模型返回。
- 后台任务用 `utils/background_tasks.create_background_task` 启动，登记在运行器的任务表里，可以取消。
- 引擎沿用 `backend/novel/` 的现有实现，**禁止复制粘贴出第二份推演或写作逻辑**。
- 密钥规则：
  - 平台模型的密钥只从服务器环境变量读取，分别是 `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`ARK_API_KEY`。
  - 用户自带的 Key 只通过 `byok.store.get_internal_config(username)` 在内存中取用。
  - 密钥不得落库，不得写日志，不得出现在接口返回里。
- 用户的思路和正文会发给所选厂商；日志里不得记录思路、正文或提示词（只记录 novel_id、章号、角色、模型、token 数、耗时和状态）。
- 测试一律离线：只用 fake 提供方，不联网。**测试不得读取仓库以外的任何文件。**

## 3. 数据模型（`init_db` 中新建，全部带 `user` 外键语义的 `username TEXT NOT NULL`）

```
novels(
  id TEXT PRIMARY KEY,                 -- uuid4
  username TEXT NOT NULL,
  title TEXT,                          -- 立项后由罗盘填入
  seed_idea TEXT NOT NULL,             -- ≤ 2000 字
  status TEXT NOT NULL,                -- 见 §5
  pause_reason TEXT,                   -- 暂停或等待的原因枚举，见 §5
  config_json TEXT NOT NULL,           -- 智能体、模型、panel_mode、自动化档位、批大小、目标篇幅、改编参数
  compass_json TEXT,                   -- 立项后写入
  bible_version INTEGER NOT NULL DEFAULT 0,
  chapters_done INTEGER NOT NULL DEFAULT 0,
  words_done INTEGER NOT NULL DEFAULT 0,
  budget_strawberries INTEGER NOT NULL,
  spent_strawberries INTEGER NOT NULL DEFAULT 0,
  reserved_strawberries INTEGER NOT NULL DEFAULT 0,
  run_token TEXT,                      -- 正在运行的任务令牌，防止两个任务并跑
  created_at, updated_at, completed_at
)
novel_bible_versions(novel_id, version, bible_json, source TEXT, created_at, PRIMARY KEY(novel_id, version))
  -- source 取值：setup | archive:<章号> | user_edit | rearchive:<章号>
novel_chapters(
  novel_id, chapter INTEGER, status TEXT,   -- planning|awaiting_plan_approval|writing|done|stale
  title TEXT, body TEXT, flags_json TEXT, meeting_json TEXT, review_json TEXT, archive_json TEXT,
  ending_status TEXT, edited_by_user INTEGER NOT NULL DEFAULT 0,
  created_at, updated_at, PRIMARY KEY(novel_id, chapter)
)
novel_steps(
  novel_id, step_key TEXT, role TEXT, model TEXT, status TEXT,   -- ok|failed|interrupted|budget_exhausted|decision_invalid|step_failed
  request_digest TEXT,                 -- 请求消息的 sha256；不存完整提示词
  raw_response TEXT, result_json TEXT, errors_json TEXT, stop_reason TEXT,
  attempts INTEGER, input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER,
  duration_ms INTEGER, strawberries_reserved INTEGER NOT NULL DEFAULT 0, strawberries_charged INTEGER NOT NULL DEFAULT 0,
  billing_status TEXT NOT NULL,        -- free|reserved|settled|refunded
  created_at, updated_at, PRIMARY KEY(novel_id, step_key)
)
novel_notes(id INTEGER PRIMARY KEY AUTOINCREMENT, novel_id, text TEXT, status TEXT,  -- pending|delivered
  delivered_chapter INTEGER, response_json TEXT, created_at)
```

每张表都要按 `novel_id` 建索引，`novels` 表另按 `(username, status)` 建索引。删号时，按该用户的 `novels.id` 把其余四张表中对应的行一并删除。

## 4. 引擎改造（只改这些点）

1. **存储协议**：把 `LLMRouter` 和编排代码对存储的依赖抽成一个最小协议，包括：
   - 读取或写入步骤（按 step_key）；
   - 追加用量记录；
   - 预算锁，以及「已用 / 已预留 / 上限」三个计数；
   - 写入章节产物。

   现有的 `RunStore`（文件）和新增的 `DbStepStore`（SQLite）各实现一份。`LLMRouter` 只依赖这个协议。**P0 离线脚本照常使用 `RunStore`，行为不变**；这一点用改动前后同一份 dry-run 的步骤键和产物对比来验证。
2. **计费钩子**：`LLMRouter` 在每次「真实调用」前后调用计费接口，接口为 `reserve(call) -> 预扣数`、`settle(call, usage) -> 实扣数`、`refund(call)`。具体规则：
   - 平台模型照规则计费；
   - 自带 Key 和 fake 提供方不计费；
   - 命中步骤缓存（续跑）时不计费；
   - 预扣失败（余额不足）时不发出调用，抛出可区分的 `InsufficientStrawberries`。
3. **新增提供方 `byok`**：模型规格写作 `byok:self`，含义是「使用该用户在 Fiona 里已启用的自带模型」。
   - `byok_bridge` 用 `get_internal_config(username)` 取得 provider、model、base_url、api_key。只允许 `anthropic`、`dashscope`、`deepseek` 三种预设厂商；`custom`、`moonshot`、`zhipu` 在 P1 不开放。
   - 构造对应的非流式调用，复用 `llm_router` 现有的 anthropic 和 openai 兼容分支：Claude 关闭思考的映射照旧，DeepSeek 和千问也关闭思考。
   - 用户的模型不在 `llm_router` 已知型号表里时，报「该模型暂不支持用于小说工坊」，不发出调用。
   - Key 只在调用期间留在内存里，用完即丢。
4. **安全底线**：新增 `novel/safety.py::NOVEL_SAFETY_RULES`，追加到所有角色系统提示的末尾，放在防注入句之前。内容为小说创作场景下的底线：
   - 不写涉及未成年人的性内容或性暗示；
   - 不写露骨性描写；
   - 不以真实存在的具体个人为对象捏造丑闻；
   - 犯罪、武器、毒品、自伤只做情节层面的叙述，不给可操作的步骤、配方或方法；
   - 不宣扬仇恨或极端主义。

   离线脚本（P0）也会带上这些规则，这是允许的提示词变化；但 P0 的步骤键和结构不得改变。
5. **默认推演模式**：P1 建书时 `panel_mode` 默认 `critique`，并允许选 `solo`（只有主编）。`merge` 在 P1 接口中**不开放**，代码保留。
6. **上下文压缩**（新增，属于成本红线）：
   - **问题**：P0 实验 B 的实测显示，每次调用的平均输入从第 1 章的约 5100 token 涨到第 12 章的约 15400 token，每章大约增加 850 token。原因是简报和圣经里放了全部章节摘要、全部伏笔（包括已回收的）、全部已用桥段和人物状态。照这个速度，到第 60 章每次调用约 5.5 万 token，一部 60 章中篇光输入就约 3000 万 token，不可接受。
   - **规则**：把下面的规则做成纯函数，放在 `context.py`，简报、写手上下文包、审校和档案员拿到的圣经都按这套规则裁剪：
     - **章节摘要**：只保留最近 10 章的逐章摘要。更早的章节每 10 章合成一段「卷摘要」，不超过 600 字。卷摘要在第 10、20、30……章归档后，由档案员的新任务 `arc_summary` 生成（计费，结果存进圣经动态区的 `arc_summaries`）。
     - **伏笔账本**：open 状态的伏笔全部保留；已回收的只保留最近 5 条。
     - **时间线**：只保留最近 10 条。
     - **已用桥段**：只保留最近 30 条。
     - **人物**：主要人物的卡片和状态全部保留；配角只保留最近 3 章出场过的，加上本章细纲点名的。
     - **锁定区与罗盘**：不裁剪。
   - **目标**：不论写到第几章，单次调用的输入都控制在约 2 万 token 以内。测试要用 fake 生成 60 章规模的圣经来验证：裁剪后序列化的字符数有上限，并且不随章数增长。
   - **缓存友好**：把用户消息拆成两条。
     - 第一条只放稳定内容，即锁定区、罗盘和创作准则，按固定顺序序列化；
     - 第二条放本章会变化的内容。

     对 Anthropic，在系统提示和第一条消息上加 `cache_control: ephemeral`；千问和 DeepSeek 依靠各自的前缀隐式缓存。用量记录要记下缓存命中的 token 数。
   - **P0 离线脚本的兼容**：裁剪阈值对 P0 的小实验（不超过 12 章）基本不触发。消息拆分和排序的变化允许影响 P0 的提示词内容，但 P0 的**步骤键和流程**必须保持不变。

## 5. 后台运行器与状态机（`novel/runner.py`）

**状态**（`novels.status`）：

| 状态 | 含义 |
|---|---|
| `setup_running` | 正在生成罗盘和设定 |
| `awaiting_setup` | 等用户确认立项（可修改锁定区） |
| `running` | 正在推演、写作 |
| `awaiting_plan` | 只在「每章确认」档位出现：等用户确认本章定稿细纲 |
| `awaiting_review` | 批次写完，等用户审阅 |
| `awaiting_end` | 智能体判定完结，等用户确认 |
| `paused` | 暂停，原因见 `pause_reason` |
| `completed` | 已完结 |
| `failed` | 不可恢复的错误（附原因） |

`pause_reason` 枚举：

- `user`：用户手动暂停
- `budget_80`：本书已花费达到预算的 80%
- `insufficient_strawberries`：草莓余额不足
- `locked_conflict`：档案员报告与锁定设定冲突
- `step_failed`：步骤重试后仍失败
- `decision_invalid`：主编裁决两次不合规
- `daily_cap`：达到当日章节上限
- `server_restart_failed`：重启后恢复失败

**每章流程**：调用引擎现有的 `deliberate`（critique 或 solo）→ `write_chapter` → 写入章节和圣经新版本 → 推进计数，全部在同一事务里完成。

**关卡**：

- **立项关卡（固定）**：setup 完成后进入 `awaiting_setup`。用户可以修改以下内容，修改按 setup 的 schema 校验：
  - 罗盘的书名、一句话梗概、主题、候选结局、主线；
  - 锁定区的人物（外形、性格、动机）、世界规则、文风指南。

  确认后，圣经版本 +1（source 记为 `user_edit`），状态进入 `running`。
- **自动化档位**：
  - `per_batch`（默认）：每写完 `batch_size` 章（默认 5，可选 1–10）进入 `awaiting_review`。
  - `per_chapter`：每章主编定稿后进入 `awaiting_plan`。用户可以选择：
    - 直接批准；
    - 修改细纲，经 `validate_decision` 校验后批准；
    - 附一条留言要求重新定稿，这会重跑 finalize（critique）或 decision（solo），重跑同样计费。
  - `full_auto`：不在章节之间停。
- **完结关卡（固定）**：本章裁决为 `end` 且归档完成后，进入 `awaiting_end`。
  - 用户确认 → `completed`。
  - 用户拒绝 → 必须同时给出 `extend_chapters`（1–10）和可选留言。目标篇幅上限相应加长，然后回到 `running`，留言进入下一章简报。

**暂停触发**：

- 预扣前发现本书「已花费 + 本次预扣」将超过预算的 80% → `paused/budget_80`。
- 余额不足 → `paused/insufficient_strawberries`。
- 档案员报告锁定冲突 → 完成本章之后暂停。
- 引擎抛出 step_failed 或 decision_invalid → 对应暂停原因。
- 当日章节上限 → `paused/daily_cap`。北京时间零点后由用户手动继续，**不自动续跑**。

审校修订两轮仍未通过（`review_unresolved`）时**不暂停**，只记录在章节 flags 里，前端会提示。

**并发**：

- 每个用户同时最多一本书处于 `running` 或 `setup_running`。
- 全局同时运行的书不超过 `FIONA_NOVEL_MAX_RUNNING`，默认 3。超出时，新任务排队（状态保持 `running`，等待全局槽）。
- 同一本书由 `run_token` 保证只有一个任务在跑。

**重启恢复**：在 lifespan 启动阶段扫描 `setup_running` 和 `running` 状态的书。

- 对 `novel_steps` 中 `billing_status=reserved` 的记录**退还预扣**（平台承担这部分成本），并把该步骤标为 `interrupted`。
- 然后按全局并发上限重新启动任务。
- 引擎的步骤缓存保证已完成的步骤不重复调用，也不重复计费。
- 恢复失败时进入 `paused/server_restart_failed`。

**取消**：用户暂停或删书时，取消后台任务；正在进行中的调用照「中断」处理并退还预扣。

**用户留言**：`novel_notes` 中 `pending` 状态的留言，在下一章简报中作为 `user_notes` 下发；主编回应后转为 `delivered`，回应内容存进 `response_json`。

**改稿**：

- 用户修改**最新一章**的正文时：保存正文并设 `edited_by_user=1`；在后台用上一版圣经重新运行档案员（计费），生成新的圣经版本（source 记为 `rearchive:<n>`）；在此之前不得开始写下一章。
- 用户修改**更早的章节**时：只保存正文，并把它之后的所有章节标为 `stale`，**不自动重写，也不重算圣经**。接口返回值中要明确告诉用户这一点。

## 6. 计费（`novel/billing.py`）

- **价目表**：放在代码常量里，可以被环境变量 `FIONA_NOVEL_PRICE_JSON` 整体覆盖（覆盖值非法时回落到默认值，并只告警一次）。格式为「模型规格 → 每千 token 输入/输出的草莓数」。默认值见第 13 节 D1。
- **单次调用的草莓数**：`ceil(input_tokens/1000 × 输入价 + output_tokens/1000 × 输出价)`，最少 1 颗。
- **预扣**：调用前按上界预扣，上界为「输入字符数视作 token 数 + 该角色的 max_tokens」。
  - 先调用 `reserve_strawberries(username, n)`，返回 None 即视为余额不足。
  - 成功后，在同一事务里累加 `novels.reserved_strawberries`，并把 `novel_steps.billing_status` 记为 `reserved`。
- **结算**：调用成功后，按真实 usage 计算实扣数。实扣数不超过预扣数，差额退还；`spent += 实扣`，`reserved -= 预扣`，状态改为 `settled`。
  - 校验修正重试（解析失败或 schema 不通过）**属于实际发生的调用，照常计费**。
  - 网络失败、未拿到 usage 的调用**全额退还**。
- **免费**：自带 Key、fake 提供方、`DEV_MODE=1` 时都不预扣。`DEV_MODE` 的处理与聊天一致；测试里通过切换 `DEV_MODE=0` 来测计费。
- **估算接口**：根据所选智能体和模型，用「最近 20 条真实步骤的平均 token；没有历史时用内置基线」估算每章草莓的区间。内置基线来自 P0 实验 A2 实测（前 5 章）：critique 每章约 11 万输入 / 1.9 万输出 token，solo 约 5.5 万输入 / 1 万输出 token。做了第 4 节第 6 点的上下文压缩之后，第 10 章以后的输入量趋于平稳，估算按「第 1–10 章线性增长到基线的 2 倍，此后保持不变」计算；成本表要标明这是估算口径。

## 7. 接口（`routers/novel.py`，前缀 `/novels`，全部需要登录，统一用 `Depends(get_current_user)`）

开关 `FIONA_NOVEL` 默认为 `0`。只有值为字面 `1` 时开启；关闭时所有 `/novels` 接口返回 404。开启后还要检查白名单 `FIONA_NOVEL_USERS`（逗号分隔的用户名），不在名单内返回 403；**白名单为空时视为无人可用**。

| 方法与路径 | 作用 | 要点 |
|---|---|---|
| `GET /novels/catalog` | 智能体池与可选模型 | 返回智能体卡片（id、中文名、类别、是否必选、一句话说明，**不返回系统提示**）、平台模型清单及价目、该用户可用的 `byok:self` 描述（厂商与型号，不含 Key）、每个必选角色允许的模型 |
| `POST /novels/estimate` | 估算 | 输入与建书相同，返回每章草莓区间与整本区间 |
| `POST /novels` | 建书 | 输入：`seed_idea`、`agents`（角色→模型规格）、`panel_mode`（critique/solo）、`automation`（per_batch/per_chapter/full_auto）、`batch_size`、`target`（min/max 章、每章字数 1000–4000）、`budget_strawberries`。校验后建行，启动 setup，返回 201 和 novel 摘要 |
| `GET /novels` | 我的书列表 | 只返回本人的书；返回状态、进度、预算与花费 |
| `GET /novels/{id}` | 详情 | 状态、暂停原因、罗盘、圣经锁定区和动态区摘要、章节列表（章号、标题、状态、flags、字数）、待处理关卡、待回应留言数 |
| `GET /novels/{id}/chapters/{n}` | 章节 | 正文、推演记录（初案、意见、替代走向、回应、定稿）、审校结论（保留与丢弃条数）、档案摘要 |
| `POST /novels/{id}/setup/approve` | 确认立项 | 可附带对罗盘和锁定区的修改 |
| `POST /novels/{id}/plan/approve` | 每章档位：批准或改细纲 | `beat_sheet` 可选；提供时按 `validate_decision` 校验 |
| `POST /novels/{id}/plan/redo` | 每章档位：附留言重新定稿 | 计费 |
| `POST /novels/{id}/continue` | 审阅后继续 | 只在 `awaiting_review` 状态下有效 |
| `POST /novels/{id}/pause` / `resume` | 暂停或继续 | resume 会重新检查预算和余额，因 `budget_80` 暂停时须先调高预算 |
| `PATCH /novels/{id}` | 调整预算、自动化档位、批大小 | 预算不得低于已花费 |
| `POST /novels/{id}/notes` | 插话 | ≤ 500 字，每本书待处理的留言最多 5 条 |
| `PUT /novels/{id}/chapters/{n}` | 改稿 | 规则见第 5 节「改稿」 |
| `POST /novels/{id}/end/confirm` / `end/reject` | 完结关卡 | reject 必须带 `extend_chapters` |
| `GET /novels/{id}/export` | 导出 Markdown | 书名 + 各章正文，`Content-Disposition` 为附件形式 |
| `DELETE /novels/{id}` | 删书 | 先取消任务、退还预扣，再在一个事务里删除该书在五张表中的全部行 |

**通用规则**：

- 访问不属于自己的书一律返回 404，不泄露这本书是否存在。
- 状态不对的操作返回 409，附中文原因。
- 所有输入用 Pydantic 校验，各字段有长度和数值上限。
- 每个写操作接口加 `@limiter.limit("20/minute")`。
- 每写完一章，计一次 `check_daily_cap("novel_chapter", user)`。达到上限后暂停，不报错。

## 8. 必选角色与模型约束

- 必选角色：`editor`、`writer`、`archivist`。`reviewer` 推荐，可选。推演顾问可以在 `plot_architect`、`character_advocate`、`reader_rep`、`twist_designer`、`pacing_advisor`、`adaptation_advisor` 中任选 0–5 个。选 0 个时等同于 solo。
- `editor`、`archivist`、`reviewer` 只允许下面两类模型，因为这几个角色需要稳定输出 JSON：
  - 平台的 `dashscope:qwen3.8-max`、`ark:doubao-seed-2-1-pro-260915`；
  - `byok:self`，且用户的自带厂商是 anthropic、dashscope 或 deepseek。
- `writer`：平台的 `deepseek:deepseek-flash`、`dashscope:qwen3.8-max`，或 `byok:self`。
- 平台模型清单与 Claude 的提供方式见 D2。

## 9. 删号、隐私与安全

- `delete_account_data` 在同一事务里删除该用户全部小说数据。删号之前先取消该用户正在运行的小说任务，并退还预扣，参照现有删号流程的顺序。
- 防止删号后数据被重建：后台任务每次写库前，都要用 `run_token` 和用户是否仍存在做条件判断；不满足就静默退出，不写入。
- 文档中写明数据流：思路、圣经和正文会发给所选厂商，可能包括阿里云百炼、DeepSeek、火山方舟，以及用户自带的厂商。

## 10. 测试要求（`tests/test_novel_p1_*.py`，全部离线）

用现有 conftest 的 `client` 夹具和临时库。模型一律用引擎的 fake 提供方注入，构造方式为「替换运行器的路由工厂」。必须覆盖：

1. **开关与白名单**：开关关闭 → 404；不在白名单 → 403；白名单为空 → 403。
2. **建书校验**：缺必选角色、模型不在允许清单、byok 厂商不被支持、预算低于估算下限的 1 章份额时，返回 422 或 409，并附中文原因。
3. **主流程**：完整走一遍 setup → 立项确认 → 写完 5 章，期间 `awaiting_review` → continue → 写到完结 → `awaiting_end` → confirm → `completed`。每一步都核对状态、计数和圣经版本。
4. **critique 与 solo**：两种模式都要跑。critique 模式的章节推演记录里要有初案、意见、替代走向和回应。
5. **每章确认档位**：approve、修改细纲后 approve（细纲非法时返回 422）、redo（计费）。
6. **计费**：
   - 切换到 `DEV_MODE=0` 后核对：预扣 → 结算 → 退差额，余额与 `spent`/`reserved` 一致；
   - 校验重试照常计费，网络失败全额退；
   - 自带 Key 不扣；
   - 续跑命中缓存时不重复扣费；
   - 余额不足时不发出调用，状态转为 `paused/insufficient_strawberries`；
   - 达到 80% 预算时暂停，调高预算后可以继续。
7. **重启恢复**：在第 N 次调用注入中断，模拟进程重启后调用恢复函数。处于 reserved 的预扣被退还，任务从断点继续；最终正文与一次跑完逐字节相同，fake 调用计数证明已完成的步骤没有重跑。
8. **并发**：同一用户的第二本书无法同时运行（409）；全局上限下，第 4 本书排队等待。
9. **完结关卡**：reject 必须带 `extend_chapters`，加长上限后继续；最后一章的守卫照常生效。
10. **留言**：下发一次并得到回应；待处理留言超过 5 条时返回 409。
11. **改稿**：改最新一章会触发重新归档，并生成新的圣经版本；改更早的章节会把之后的章节标为 `stale`，且不触发任何模型调用。
12. **删书与删号**：删除后五张表中没有残留；删号时运行中的任务被取消；删号之后后台任务不再写入数据（用条件写入来证明）。
13. **越权**：对别人的书执行所有接口，一律返回 404。
14. **密钥与日志**：把 `byok:self` 的 Key 设成哨兵字符串，跑一章后在库、日志和接口返回中都找不到它；日志中没有思路和正文。
15. **P0 不变**：四份 P0 配置的 dry-run 步骤键和流程与改动前一致。比对用的「改动前」数据要冻结成测试数据，写在测试文件里；**不得读取仓库外的文件**，也不得依赖 git 历史。
17. **上下文压缩**：
    - 用 fake 构造一份 60 章规模的圣经，验证裁剪后的简报、写手上下文包、审校和档案员的输入字符数都有上限，而且第 30 章和第 60 章的输入大小差不超过 10%；
    - 卷摘要在第 10 章和第 20 章各生成一次，并且计费；
    - open 状态的伏笔一条都不丢；
    - 用户消息拆成稳定块和变化块，并且对 Anthropic 加上 `cache_control`（用 MockTransport 截获请求体验证）。
16. **`/health` 不变**：启动后 `/health` 仍然通过，迁移版本集合没有变化。

## 11. 验收

1. `python -m pytest -q`（在 `backend/` 下）全量通过，没有新增失败。派单前在本工作树测得的基线是 4760 passed、3 skipped；沙箱内禁止绑定回环端口的 6 项不计入。小说相关测试全部通过。解释器固定为 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。
2. 在 `--depth 1` 浅克隆里跑本任务新增的测试，全部通过（证明测试不依赖 git 历史，也不依赖本机文件）。
3. 用 DEV_MODE 启动后端，再用 fake 提供方注入的测试替身端到端跑通一本 3 章的小书。这一条由测试覆盖，不需要启动真实服务。
4. `git status --porcelain` 中被修改的文件只能是第 1 节列出的那些。
5. 03-report.md 写明以下内容：每一条规格的落实位置、测试清单、文档改动点、待人工确认的事项。

## 12. 何时停下来问

- 只有遇到影响「做什么」的问题才停下，例如条款之间互相矛盾、和现有行为冲突且无法同时满足。
- 「怎么实现、怎么测试」由实施方自行决定，在报告里说明理由即可。
- 不回滚已完成的工作。

## 13. 作者拍板结果（2026-10-15，实施方以此为准）

- **D1 草莓价目：成本价 × 1.5**。默认价目按「1 草莓 ≈ ¥0.01 成本」折算后再乘 1.5，写进 `billing.py` 的常量。各模型的每千 token 草莓数以官方单价折算（美元按 7.2 换算人民币），结果向上取到 0.01：
  - `dashscope:qwen3.8-max`：输入 ¥12、输出 ¥36（每百万 token）
  - `deepseek:deepseek-flash`：输入 $0.30、输出 $1.20（按高峰价计）
  - `ark:doubao-seed-2-1-pro-260915`：输入 ¥6、输出 ¥30

  `byok:self` 不计费。报告里列出折算结果。
- **D2 平台模型：不含 Claude**。平台模型清单为上面三种；Claude 只能通过 `byok:self` 使用。`/novels/catalog` 要为没有启用自带 Claude 的用户写明：「主编可选千问或豆包；使用自带 Claude 担任主编的效果经过实测」。
- **D3 基线：已处理**。作者已同意先合入本机监控：main 为 `d92530f`（本机监控），小说分支 `novel-workshop-p0` 已变基到它之上（`820fff1`，即 P0 原型）。P1 在这个工作树里继续做。`database.py`、`main.py`、`rate_limit.py` 和各文档里已有本机监控的改动；**插入小说相关内容时，不得改动或移动本机监控已有的任何行**。

---

以下是派单前的原始待拍板说明，留作记录：

- **D1 草莓价目**：
  - 默认方案：按成本折算，1 草莓 ≈ ¥0.01 成本，再乘 1.5 倍加成。
  - 按这个方案估算：
    - critique 模式：前几章约 250 草莓/章，第 10 章以后随上下文增长到约 500 草莓/章并稳定在这个水平（已经计入上下文压缩）。
    - solo 模式：约为 critique 的一半。
    - 一部 60 章的中篇约 2.5 万草莓（作为参照，一次聊天扣 10 颗）。
    - 主编使用用户自带的 Claude 时，Claude 这部分不扣草莓，每章大约能省三分之一。
  - 可选方案：按成本价不加成；或按章固定价。
- **D2 平台模型清单**：
  - 默认方案：平台只提供千问 qwen3.8-max、DeepSeek deepseek-flash、豆包 Seed 2.1 Pro；Claude 只能通过用户自带 Key 使用。理由是大陆服务器连不上 Claude，平台垫付成本也高。
  - 这意味着没有自带 Claude 的用户，主编只能选千问或豆包，而这两种模型担任主编的质量还没有实测过。
- **D3 基线分支**：
  - 主检出里有未提交的「本机监控（local watch）」改动，改的是 `database.py` 的同一区段、删号函数、路由注册、`rate_limit` 和全部文档。P1 也要改这些位置。
  - 推荐方案：先由作者决定把本机监控提交合入 main，再把小说分支变基到最新 main，P1 在此基础上做，避免两边大面积冲突。
  - 另一种方案：直接在当前分支上做，日后再解决冲突。
