# 规格：内测阻断修复（后端）——草莓、邀请码脚本、安全底线、测试隔离

日期：2026-09-23　级别：L2（含一个新增可空列）　基线：`main` @ `54a9b57`，工作区干净

## 0. 背景（你看不到之前的对话，这里是全部上下文）

Fiona 是个人 AI 分身平台，后端 FastAPI + SQLite（`backend/`，虚拟环境 `backend/.venv`）。2026-09-23 的完成度体检发现以下问题会直接阻断受控内测，本任务只修这些问题，不做别的：

1. **草莓只出不进**：新用户 200 颗（`database.py:1474`、`database.py:220`），每条成功回复扣 10 颗（`services/chat_service.py:982-985`）。`add_strawberry`（`database.py:1512`）全仓无调用方，前端无充值入口。生产环境 `DEV_MODE=0`，每个测试者约 20 条回复后被永久卡死，提示「草莓不足，请充值后继续聊天」（`routers/chat.py:72-78`），但并不存在充值。
2. **扣费不原子**：`routers/chat.py` 先查余额 `> 0` 再放行，结束后才 `deduct_strawberry`。余额 10 时并发 3 条请求全部放行；余额 5 也能放行。工具失败、桌面占位工具、未知意图、追问缺参都照扣 10 颗。
3. **邀请码脚本会把新测试者发进别人的账号**：`seed_invites.py` 用「现有邀请码行数 + 1」生成用户名 `testerNN`。删号（`database.py:776` 删除该用户的邀请码行）后行数变少，下次发码会生成一个**已存在账号**的用户名；`invite_codes.username` 不唯一，新测试者兑换后直接登录他人账号，看得到私聊与记忆。
4. **管理脚本连错库**：`database.DB_PATH` 在导入时取 `FIONA_DB_PATH`，缺省回落 `backend/fiona.db`（`database.py:6`）。生产上 `FIONA_DB_PATH` 只写在 systemd 的 `EnvironmentFile=/etc/fiona/fiona.env`（`docs/DEPLOYMENT.md:25,83,135`）里；运维按 `docs/DEPLOYMENT.md:329-333` 在 shell 里直接跑 `manage_invites.py` / `seed_invites.py` 时，脚本会对 `backend/fiona.db` 先 `init_db()` 建一个空库再操作——撤销提示「不存在」，生产库里的码仍然有效。`seed_invites.py` 每次运行还会把**全部**邀请码明文打印到终端。
5. **危机表达被引向追问**：`HARD_WORDS`（`services/chat_service.py:206`）含「只能」，「我只能去死了」会触发 `build_hard_word_appendix`，该附录被追加在 system prompt 的**最后**（`services/chat_service.py:442`），排在安全底线 `BASE_SAFETY_RULES`（`persona.py:30`）之后，要求「本轮核心动作是反问」，没有危机例外。镜子模式附录 `MIRROR_PROMPT_APPENDIX`（`mode_switcher.py:366,387`）同样追加在安全底线之后。
6. **分身交流没有安全底线**：`services/exchange_service.py` 与 `exchange_workflow.py` 构造的所有 system 消息都不包含 `BASE_SAFETY_RULES`。
7. **测试污染真实目录**：全量 pytest 会往真实 `backend/uploads/` 写 68 字节测试 PNG；`trace.py:10` 以 `from database import DB_PATH` 在导入时绑定路径，测试打桩 `database.DB_PATH` 后埋点仍写默认库路径；按单文件运行时有用例连到默认库路径。

## 1. 产品目标

- 内测用户不会因为「草莓只出不进」被永久卡死；运维有明确、安全的补充手段；可配置每日自动补给。
- 扣费只为真正交付的回复买单，且在并发下不超扣、不透支。
- 发邀请码绝不会把新人绑定到已有账号；管理脚本操作的一定是服务实际使用的数据库，并明确告诉运维它连的是哪个库。
- 用户表达自伤/自杀意图时，模型收到的最后一条指令是危机支持，且无论模型成败，用户一定能看到固定的求助资源。所有面向用户的对话与分身交流都带安全底线。
- 跑测试不再触碰真实上传目录与数据库。

## 2. 技术约束

- 沿用现有技术栈与写法：`aiosqlite`、现有 `_safe_migrate` 加列模式、`python-dotenv`（已在 `requirements.txt`）、标准库 `zoneinfo`。**不新增任何依赖**，不改 `requirements*.txt`、`package*.json`。
- 不做无关重构，不改与本任务无关的行为；不改接口路径与返回结构（新增字段允许）。
- **允许修改的范围（白名单）**：`backend/**`（不含 `backend/.env*`、`*.db`、`backend/uploads/**`，但 `backend/.env.example` 允许）、`README.md`、`PLAN.md`、`CLAUDE.md`、`docs/DEPLOYMENT.md`、`docs/ARCHITECTURE.md`、`docs/CYBER_AVATAR_PLATFORM.md`，以及本目录下的 `03-report.md`。
- **禁止修改**：`frontend/**`、`desktop/**`、`.github/**`、任何数据库文件、`backend/uploads/**`、`.env`/`.env.local`。不要读取 `.env`、`.env.local` 的内容。不要打印任何密钥值。
- 不得 `git commit` / `push` / `stash` / `reset` / `checkout`。
- 日志与 print 不得输出用户原文（已有约定：只打印长度、计数、布尔）。

## 3. 任务清单

请使用多个 subagent 并行推进，按**文件不重叠**分工：例如 A 组负责 T1+T2（`database.py`、`routers/chat.py`、`routers/me.py`、`routers/auth.py`、`services/chat_service.py` 的计费部分），B 组负责 T3（`admin_env.py`、三个脚本、`database.py` 邀请码函数——与 A 组同改 `database.py` 时由同一 subagent 串行完成或先后合并），C 组负责 T4（`safety.py`、`persona.py`、`mode_switcher.py`、`exchange_service.py`、`exchange_workflow.py`；`services/chat_service.py` 与 A 组冲突时串行），D 组负责 T5，文档 T6 最后统一做。**同一文件的多处修改必须由同一 subagent 串行完成。**

### T1 草莓：原子预扣 + 按交付结算

1. 单一价格常量 `STRAWBERRY_COST_PER_REPLY = 10`，后端所有扣费/判断引用它（放在合适的模块，如 `database.py` 或新的小模块）。
2. 新增数据库函数（名称可调整，语义必须一致）：
   - `reserve_strawberries(username, amount) -> int | None`：**单条原子 UPDATE**（`... SET strawberry_balance = strawberry_balance - ? WHERE username = ? AND strawberry_balance >= ? RETURNING strawberry_balance`），成功返回扣后余额，余额不足返回 `None`。
   - `refund_strawberries(username, amount) -> int`：退还。
3. `routers/chat.py`（`DEV_MODE != "1"` 时）：在所有参数校验通过后、开始流式之前调用 `reserve_strawberries`；不足则返回现有 SSE 错误形式（文案见 T2.5）。预扣之后若 `build_context` 抛错（404 等）或任何异常导致流未开始，**必须退还**。
4. `run_chat` 收尾：去掉「落库即扣 10」的逻辑，改为「本轮已预扣且 `state.billable` 不为真 → 退还」。`ChatState` 新增 `billable: bool = False`，**只在真正交付时置真**：
   | 分支 | 何时 billable |
   |---|---|
   | `stream_normal`、`stream_mirror`、`stream_image`（看图） | 模型回复非空且已落库 |
   | `stream_generated_image` | 确实生成并保存了图片 |
   | `stream_intent` / `stream_pending` 执行工具 | 工具属于真实工具（`web_search`、`hot_topics`、`route`、`travel_plan`、`fetch_card`、`get_datetime`）**且成功** |
   | 追问缺失参数（`ask_missing`）、桌面占位工具（`open_app`、`send_wechat`、`wechat_voice`、`wechat_video`、`set_reminder`、`take_screenshot`、`write_clipboard`、`open_in_browser`）、未知意图、工具失败、任何错误/`ResourceNotFound`、会话已删除 | 不 billable |
   工具成败的判断：逐个读 `backend/tools/` 下真实工具的返回，找出结构化失败信号（如 `web_search` 失败返回 `{"type":"card", ..., "error": True}`）。若某工具失败时只返回自然语言字符串，改为让它/它的调用处给出结构化失败信号，**禁止通过匹配用户可见文案判断成败**。
5. 客户端中途断开（生成器被关闭/取消）时：若未 billable，预扣必须退还（注意 `finally` 中 `await` 在取消场景下的可靠性，可用 `asyncio.shield` 或等效手段），测试需覆盖「提前 `aclose()` 流 → 余额复原」。
6. `DEV_MODE=1` 时完全跳过预扣与结算（保持现有行为）。
7. `deduct_strawberry` 若不再被使用可删除；`add_strawberry` 由 T2 的管理脚本使用。

### T2 草莓补充路径

1. 新增环境变量 `STRAWBERRY_DAILY_REFILL`（非负整数，缺省 `0` = 关闭；非法值按 `0` 处理并打印一行不含值的警告）。
2. `users` 表新增可空列 `strawberry_refill_date TEXT DEFAULT NULL`，沿用 `_safe_migrate` 的 `ALTER TABLE ... ADD COLUMN` 模式（只加列，不改写已有数据）。
3. 补给规则：当 `STRAWBERRY_DAILY_REFILL = N > 0` 时，某用户在某个 **Asia/Shanghai 自然日**第一次发生余额读取或预扣时，把余额提升到 `MAX(当前余额, N)` 并把 `strawberry_refill_date` 记为当天；**绝不降低余额**；同一天只补一次。补给与预扣必须在同一事务或同一条原子语句中完成，保证并发下不重复补、不超扣。`GET /strawberry`（`routers/me.py`）与登录返回的余额（`routers/auth.py` 两处）也要先应用补给，保证界面显示正确。日期取值集中在一个可打桩的函数（如 `_today_shanghai()`），`zoneinfo` 不可用时回退固定 UTC+8。
4. 新增管理脚本 `backend/manage_strawberries.py`（使用 T3 的加载器与参数）：
   - `list`：按用户名列出 `用户名  余额  最近补给日期`；
   - `grant <username> <amount>`：`amount` 为 1–100000 的整数，用户不存在则退出码 1；
   - `set <username> <amount>`：`amount` 为 0–100000；
   - 输出只含用户名与数字。
5. 余额不足时的 SSE 错误文案改为（不再出现「充值」二字）：
   - 补给开启：`今天的草莓用完了，明天会自动补到 {N} 颗；急用请联系管理员补充 🍓`
   - 补给关闭：`草莓不足，内测期间请联系管理员补充 🍓`

### T3 管理脚本连库修正 + 邀请码不撞号

1. 新增 `backend/admin_env.py`，提供加载器（名称可调整），供三个管理脚本在**导入 `database` 之前**调用：
   - 解析顺序：命令行 `--env-file` → 环境变量 `FIONA_ENV_FILE` → `/etc/fiona/fiona.env`（存在且可读时）→ `backend/.env`（存在时）→ 都没有则不加载。
   - 用 `python-dotenv` 加载，`override=False`（进程里已显式设置的变量优先）。
   - 向 stderr 打印两行：`配置：<实际加载的文件路径或「无」>`、`数据库：<解析后的绝对路径>`。不得打印任何其他变量的值。
   - 若解析出的数据库文件不存在：除非传了 `--init-db`，否则退出码 2，提示 `数据库文件不存在：<路径>。请确认 FIONA_DB_PATH，或用 --env-file 指定服务使用的配置文件；首次初始化才加 --init-db`，且**不得创建任何文件**。
2. `seed_invites.py`、`manage_invites.py`、`manage_strawberries.py` 都支持 `--env-file` 与 `--init-db`。`seed_invites.py` 保留位置参数「数量」（默认 10，限制 1–200）。
3. `seed_invites.py` 用户名分配改为：下一个编号 = 1 + `users.username` 与 `invite_codes.username` 中所有匹配 `^tester(\d+)$` 的最大编号（没有则为 1）；每个分配出的用户名在插入前再确认不存在于 `users` 与 `invite_codes`；分配与插入在**同一个 `BEGIN IMMEDIATE` 事务**里完成（新增一个数据库函数承载，如 `create_tester_invites(count)`），并发运行两个脚本也不会发出重复用户名。编号格式保持 `tester{n:02d}`（≥100 自然变三位）。
4. `seed_invites.py` 的输出只列出**本次新建**的码与用户名，末尾只给统计（总数 / 未用 / 已用 / 已撤销的个数），不再列出其他码。
5. `manage_invites.py` 现有 `list` / `revoke` / `rotate` 行为不变。

### T4 安全：危机识别、提示词顺序、分身交流安全底线

1. 新增 `backend/safety.py`：
   - `detect_crisis(text: str) -> bool`：识别自伤/自杀意图（中英文）。规范化（去空白、小写）后匹配。必须满足下列夹具（写成参数化测试）：
     - **必须命中**：`我只能去死了`、`我不想活了`、`活着没意思，想自杀`、`想结束自己的生命`、`我想割腕`、`想从楼上跳下去`、`攒了一瓶安眠药`、`我想死`、`I want to kill myself`、`thinking about suicide`、`I want to end my life`
     - **必须不命中**：`笑死我了`、`累死了今天`、`饿死了`、`热死了`、`吓死我了`、`气死我了`、`电脑死机了`、`代码死循环了`、`这个方案必须今天定`、`我只能周末去`、`死磕这个问题`
   - `CRISIS_GUIDANCE`：追加到 system prompt 最末的危机指令（要点：本轮停止打趣、挑逗、镜像语气、反问技巧与普通陪聊；先认真回应感受，温和询问对方当前是否安全；鼓励立即联系紧急服务或身边信任的人；不评判、不说教、不承诺保密；回复简短温暖）。
   - `CRISIS_RESOURCE_NOTE`：固定求助文案，内容为：`如果你现在有伤害自己的想法，或者正处在危险中，请立即拨打 120 或 110；也可以拨打全国心理援助热线 12356，或联系身边信任的人。你不必一个人扛着。`
2. 私聊（`services/chat_service.py` 的 `run_chat` 及其分支）中，本轮 `ctx.message` 命中 `detect_crisis` 时：
   - 本轮不走镜子模式、不做意图识别与工具执行、不处理待补参数（**不清除**已有的待补参数状态）；有图片时仍走看图分支，否则走普通回复分支；
   - 不追加硬词附录与镜子附录；system prompt 顺序为 `……人格与上下文 + BASE_SAFETY_RULES + CRISIS_GUIDANCE`（危机指令在最后）；
   - 模型回复之后，服务端**无论模型成功与否**都向客户端追加发送一段文本事件：`\n\n` + `CRISIS_RESOURCE_NOTE`；若助手消息被落库，落库内容也包含这段文案；模型失败时仍先发这段文案再发错误事件；
   - 危机轮**不预扣、不计费**；余额不足时也**不得**返回「草莓不足」：此时不调用模型，直接以文本事件返回 `CRISIS_RESOURCE_NOTE` 并结束（`done`），不落库、不计费；
   - 打印/埋点只记录布尔标记（如 `trace["crisis"] = True`），不记录原文。
3. 非危机轮：`BASE_SAFETY_RULES` 必须是**每一个**私聊 system prompt 的**最后一块**——包括新分身模板、旧 Chloe 三个成长阶段模板、镜子模式、看图分支、硬词附录生效时。实现方式自定（例如各模板不再自带安全底线，在最终装配处统一在最后追加一次），但安全底线文本在最终 prompt 中**恰好出现一次**。请全库搜索所有组装 system prompt 并发往模型的位置（`grep -rn '"role": "system"'` 等），逐一确认，不要只改本规格点名的位置。
4. 分身交流：`exchange_service.py` 与 `exchange_workflow.py` 发往模型的**每一种** system 消息（真人分身轮次、官方体验轮次、两种总结、作品流程的主创/审稿/修订等所有角色）都必须包含 `BASE_SAFETY_RULES`，放在该条 system 内容的末尾。
5. 测试：
   - 夹具测试（上面的正反例）；
   - 「我只能去死了」经 `/chat`：发往模型的 system prompt 以 `CRISIS_GUIDANCE` 结尾、不含硬词附录标题、客户端收到 `CRISIS_RESOURCE_NOTE`、余额不变；模型打桩抛错时客户端仍收到资源文案；
   - 镜子模式下发危机消息：不使用镜子附录；
   - 余额为 0 时发危机消息：收到资源文案、未调用模型；
   - 对每个非危机分支（普通、镜子、看图、硬词）断言 system prompt 以 `BASE_SAFETY_RULES.strip()` 结尾且只出现一次；
   - 遍历交流的所有 system 消息构造路径，断言都包含 `BASE_SAFETY_RULES.strip()`。

### T5 测试隔离

1. `backend/tests/conftest.py` 在模块顶部、任何后端模块导入之前，**强制**（不是 `setdefault`）把 `FIONA_DB_PATH`、`FIONA_UPLOADS_DIR` 设为一个会话级临时目录下的路径（会话结束清理）。已有的逐用例打桩保留。
2. `trace.py` 不再在导入时绑定 `DB_PATH`，改为调用时读取 `database.DB_PATH`。全库检查其他在模块顶部 `from database import DB_PATH` 或复制 `UPLOADS_DIR` 值的位置，同样处理（函数内部导入的无需改）。
3. 目标：全量运行与**逐个测试文件单独运行**，都不在 `backend/uploads/` 新增/修改任何文件，不创建或修改 `backend/*.db`。

### T6 文档同步

凡本任务改变了某个事实（草莓规则、补给开关、管理脚本用法与参数、邀请码用户名分配、危机处理、交流安全底线、新增列、测试隔离），**全库搜索该事实的所有陈述点并逐处更新**，不要只改下面举例的位置。至少包括：

- `backend/.env.example`：新增 `STRAWBERRY_DAILY_REFILL=0` 及中文说明（建议值由运维决定）。
- `docs/DEPLOYMENT.md`：「邀请码与会话运维」一节改为带 `--env-file /etc/fiona/fiona.env` 的用法，新增发码（`seed_invites.py`）与草莓管理（`manage_strawberries.py`）命令；迁移清单加入 `users.strawberry_refill_date`；环境变量表加入 `STRAWBERRY_DAILY_REFILL`。
- `PLAN.md`：新增一条 `2026-09-23` 的记录说明本次修复；「本轮明确暂缓」里「草莓余额并发检查与扣减的原子性」改为已完成，「持久化成本控制」仍为暂缓。
- `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md` 中关于草莓、邀请码脚本、安全底线的陈述。
- 不要改与本任务事实无关的文档段落。

## 4. 何时停下来问（判据）

- **必须停**：某条要求会做出自相矛盾或错误的东西且没有唯一合理解（例如两处规格要求同一数据取不同值；某个真实工具完全无法区分成败且无法不改变其对外返回而加上信号）。停下时在报告中写清卡点与已完成部分。
- **不要停、自己定**：命名、模块放置、测试组织、验收命令细节、措辞等不影响「实现什么」的问题——按最合理的理解做，在报告中说明。
- **任何情况下都不回滚已完成的工作。**

## 5. 验收标准（Claude 会逐条独立执行）

在 `backend/` 下：

1. `.venv/bin/python -m pytest -q` → 全部通过，0 failed；通过数 ≥ 829 + 本任务新增用例数。
2. 隔离：记录 `ls backend/uploads | sort | shasum`、`ls -l backend/*.db`（若有）→ 跑全量 pytest → 再对 `tests/` 下每个 `test_*.py` 逐个单独运行 → 再次记录：两次结果逐字一致。
3. `.venv/bin/python -m compileall -q -x '\.venv' .` → 退出码 0。
4. `grep -rn "请充值" --include='*.py' . | grep -v '\.venv'` → 无命中。
5. 并发预扣：存在一个测试，余额 10 时并发 3 个 `/chat`（`DEV_MODE=0`），恰好 1 个进入模型、其余收到余额不足、最终余额 0；以及「余额 5 时被拒」「工具失败/占位工具/追问/模型错误后余额复原」「提前关闭流后余额复原」「补给开启时跨日补到 N、同日不重复、不降低余额」。
6. 脚本（用临时目录，不碰真实库）：
   - `printf 'FIONA_DB_PATH=%s\n' /tmp/…/x.db > env` 后 `python seed_invites.py 2 --env-file env` → 退出码 2 且 `x.db` 未被创建；
   - 加 `--init-db` → 成功，新建 2 个码，stderr 含 `数据库：` 与该绝对路径；
   - 在该库中删除 `tester01` 账号数据（调用现有删号函数）后再发 1 个码 → 新用户名为 `tester03`，且与已有用户名不重复；
   - `manage_strawberries.py grant tester02 50 --env-file env` → 余额增加 50；`grant nobody 1` → 退出码 1。
7. 安全：T4.5 所列测试全部存在且通过。
8. `git status --porcelain --untracked-files=all` 中的每个路径都在第 2 节白名单内。

## 6. 交付

完成后把变更总结写入 `docs/tasks/2026-09-23-beta-blockers-backend/03-report.md`，必须包含：
1. 修改/新增了哪些文件；
2. 实现了哪些功能；
3. 与本规格任务清单 T1–T6 的逐项对应（含新增测试名）；
4. 测试结果（命令与通过数）；
5. 未完成或需要人工确认的地方（例如某工具成败信号的取舍、危机词表的已知漏报/误报）。
