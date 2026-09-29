# 规格：恢复内测前的代码加固 —— 会话复活、危机分级、事件循环阻塞

日期：2026-09-25　级别：L2（含一张新表与账号创建行为变化）　基线：`main` @ `ae026c9`，工作区干净

## 0. 背景（你看不到之前的对话，这里是全部上下文）

Fiona 是个人 AI 分身平台，后端 FastAPI + SQLite（`backend/`，虚拟环境 `backend/.venv`），前端 Next.js 16（`frontend/`）。2026-09-25 的重新观察（16 个代理 + 人工复现）确认了三组必须在恢复内测前修掉的缺陷：

### A. 删号后用户名复用 → 旧登录凭证复活（已在临时库复现）

- `database.create_tester_invites`（`backend/database.py` 约 599–640 行）按「`users` ∪ `invite_codes` 中现存最大 `testerNN` + 1」分配用户名。`delete_account_data` 删除这两张表里该用户的行，**没有墓碑**，所以删掉编号最大的账号后，下一次发码会把同一个用户名发给新人。
- 新账号的 `users.session_version` 默认从 0 开始（`database.py:137` 的 DEFAULT 0；`get_or_create_user` 在 `database.py:342-349`，`get_or_create_user_by_phone` 在约 `:1551`）；JWT 只含 `sub` 与 `sv`（`backend/auth.py:31-56`），鉴权只比对用户名与 `session_version`（`backend/auth_dep.py:28`）。
- 结果：删号者旧设备上的 JWT（`sv=0`）对新人账号同样有效，能读到新人的私聊与记忆。复现脚本逻辑：发 2 码 → 兑换 tester02 并签 token → 删除 tester02 → 再发 1 码（仍是 tester02）→ 新人兑换 → 旧 token 认证为 tester02。
- 任何「删号后同名账号被重新创建」的路径（发码、测试登录、手机号登录）都有同样问题。

### B. 危机识别误报 + 漏报 + 成为免费通道

`backend/safety.py` 的 `detect_crisis` 是 15 条正则、单一布尔：

- **误报**（实测为 True）：`我困得要死`、`我忙得要死`、`我饿得要死`、`我要死磕这个bug`、`帮我查下割腕的急救方法`、`《自杀小队》好看吗`。命中后本轮跳过镜子/工具/待补参，回复末尾强塞热线——用户的查天气、画图等请求被吞掉。
- **漏报**（实测为 False）：`好想死`、`我已经写好遗书了`、`不如死了算了`、`我想结束这一切`。漏报时若消息含硬词（`services/chat_service.py` 的 `HARD_WORDS`，含「只能」等），`build_hard_word_appendix` 仍注入「本轮核心动作是反问」的附录。
- **免费通道**：`routers/chat.py` 约 108–114 行对危机轮不预扣草莓，只要消息带「自杀」等词即可无限免费调用主模型（仅受每 IP 30 次/分钟限流）。
- **图片模式不一致**：`mode=image`/`image_edit` 时危机轮只发 `text`/`done`，前端 `frontend/app/page.tsx` 约 1389 行在未收到 `generated_image` 时抛出「图片生成未完成，请重试。」，把热线回复显示成错误并带重试按钮。
- **前置失败**：危机轮里 `build_context` 抛 `ResourceNotFound`（会话已删等）时直接返回 404，用户拿不到求助资源。

### C. 同步 sqlite3 阻塞事件循环（G7，已实测 5.2 秒）

- `backend/intent_router.py` 的 `_slot_conn`（约 205–214 行）与 `backend/mode_switcher.py` 的 `_slot_conn`（约 110–119 行）用同步 `sqlite3.connect(timeout=5.0)`，每次连接还执行一遍 `CHAT_SLOT_STATE_DDL`。它们被 `services/chat_service.py`、`routers/conversations.py`、`conversation_matcher.py` 等**在事件循环线程上直接调用**（`get_pending`/`set_pending`/`clear_pending`/`get_user_mode`/`clear_user_mode` 等）。
- 自 7161868 起每条生产 `/chat` 都先开一个 `BEGIN IMMEDIATE` 的预扣事务（`database.reserve_strawberries`）。aiosqlite 事务提交前多次 await 时，事件循环上的同步写入忙等写锁，整个进程卡约 5.2 秒并抛 `database is locked`。复现要点：一个协程执行 `database.reserve_strawberries(...)`，另一个协程在循环里直接调用 `intent_router.clear_pending(...)`，测量单次调用耗时与 OperationalError 次数。
- 数据库没有开启 WAL，也没有统一的 busy timeout。

## 1. 目标

1. 任何删号后重新出现的同名账号，都不会被旧凭证登录；测试邀请码分配的用户名永不回收。
2. 危机识别分级：明确的第一人称危机走危机支持；只是「可能相关」的不劫持正常功能但附上求助资源；日常口语不受影响。危机支持永不因余额被拦截，但也不再是免费调用模型的通道。图片模式下危机回复正常显示。
3. 请求处理路径上不再有同步 sqlite3 调用阻塞事件循环；并发写入不再出现秒级卡顿。

## 2. 技术约束

- 沿用现有技术栈与写法（`aiosqlite`、`_safe_migrate` 加列/建表、现有测试夹具）；**不新增依赖**。
- **允许修改（白名单）**：`backend/**`（不含 `.env*`、`*.db`、`uploads/**`）、`frontend/app/page.tsx`（**只**为 B 的危机事件处理，其余不动）、`README.md`、`PLAN.md`、`CLAUDE.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`，以及本目录 `03-report.md`。
- **禁止修改**：其他前端文件、`desktop/**`、`.github/**`、依赖与锁文件、数据库文件、`backend/uploads/**`。不读 `.env`/`.env.local`，不打印密钥。不得 `git add/commit/push/stash/reset/checkout`。
- 前端改动必须保持桌面与手机现有渲染不变（只改流式事件处理逻辑，不改任何 className/结构）。
- 修改前端前先读 `frontend/AGENTS.md`。

## 3. 任务清单

请使用多个 subagent 并行，按文件不重叠分工（建议：A 组 = `database.py` 账号/邀请码部分 + `auth*.py` + A 的测试；B 组 = `safety.py` + `routers/chat.py` + `services/chat_service.py` 危机与硬词部分 + `frontend/app/page.tsx` + B 的测试；C 组 = `intent_router.py`、`mode_switcher.py`、其调用方（与 B 组共用 `services/chat_service.py` 时由同一个 subagent 串行完成，或 C 先完成后再交给 B）+ `database.py` 的 WAL/busy timeout 部分 + C 的测试；文档最后统一做）。**同一文件的多处修改由同一个 subagent 串行完成**；`database.py` 由同一个 subagent 负责全部改动。

### T1（A）会话复活

1. **随机初始会话版本**：所有创建 `users` 行的路径（全库搜索 `INSERT` 到 `users` 的语句，至少 `get_or_create_user`、`get_or_create_user_by_phone`）在新建账号时把 `session_version` 设为密码学随机的正整数（如 `secrets.randbelow(2**31 - 1) + 1`）。已有账号的 `session_version` 不变（不做迁移、不强制重登）。`auth.py` 的 token 解析与现有兼容逻辑保持（`sv` 必须是非负整数）。
2. **用户名退役表**：新增表 `retired_usernames(username TEXT PRIMARY KEY, retired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)`（沿用 `init_db` 建表/迁移写法）。`delete_account_data` 在同一事务里写入被删用户名（`INSERT OR IGNORE`）。`create_tester_invites` 在计算最大编号与逐名避撞时把 `retired_usernames` 一并纳入，保证 `testerNN` 永不回收。
3. 测试：
   - 复现上文 A 的场景：发 2 码 → 兑换 tester02 并签 token → 删除 tester02 → 再发 1 码 → 新用户名为 `tester03`；
   - 即使通过 `get_or_create_user("tester02")` 等路径重新创建同名账号，旧 token 也认证失败；
   - 新账号 `session_version` 非 0 且两次新建的值不同（可 monkeypatch 随机源做确定性断言）；
   - 旧账号（迁移前已存在、`session_version=0`）的现有 token 仍有效。

### T2（B）危机分级

1. `safety.py` 提供 `assess_crisis(text) -> "high" | "possible" | None`（保留 `detect_crisis(text)` 作为 `assess_crisis(text) == "high"` 的兼容封装）。规则设计自定，但**必须通过下列夹具**（写成参数化测试，与现有夹具合并）：
   - **high**：现有 `test_crisis_detector_recognizes_required_phrases` 的全部正例；以及 `好想死`、`我已经写好遗书了`、`不如死了算了`、`我想结束这一切`、`活着好累，不想再活了`、`我把安眠药都攒好了`、`生无可恋，想死`、`我想自我了断`、`dont wanna live`、`i don't want to live anymore`、`i'm going to jump off the bridge`。
   - **possible**：`帮我查下割腕的急救方法`、`今天新闻说有人跳楼了`、`他说他不想活了，我该怎么劝`、`让我去死吧哈哈哈哈`、`安眠药吃多少会有危险`。
   - **None**：现有 `test_crisis_detector_rejects_required_everyday_phrases` 的全部反例；以及 `我困得要死`、`我忙得要死`、`我饿得要死`、`热得我要死`、`我要死磕这个bug`、`《自杀小队》好看吗`、`自杀式营销真恶心`、`跳楼大甩卖`、`i'm dying to see it`、`kill myself laughing`。
   - 在报告里列出已知仍会误判的写法（诚实披露）。
2. **high** 轮行为：保持现有危机支持（跳过镜子/工具/待补参且不清除待补参、system 以 `CRISIS_GUIDANCE` 收尾、模型成败都送达 `CRISIS_RESOURCE_NOTE`、落库包含资源文案），另外：
   - **计费**：与普通轮一致——生产环境余额够时预扣，交付后结算，未交付退款；余额不足时**不拦截**：不调用模型，直接返回资源文案（不扣费）。`DEV_MODE=1` 跳过计费（与普通轮一致）。
   - **事件**：流的第一个事件是 `{"crisis": true}`（包括余额不足的短路返回），便于前端识别。
   - **图片模式**（`mode=image`/`image_edit`）：不生成/不修改图片，按危机回复处理，不发参考图回执以外的图片事件（参考图回执照旧发送，以免客户端重传）。
   - **前置失败**：`build_context` 抛 `ResourceNotFound` 时，不再返回 404，而是返回 SSE：`{"crisis": true}`、资源文案 `text`、`{"error": 原错误文案}`；若已预扣要退款。
3. **possible** 轮行为：按普通轮完整处理（镜子、意图、工具、待补参、图片模式、计费全部照常），不追加硬词附录；若本轮是文字回复（非图片生成/修改），回复结束后追加一段文本事件 `\n\n` + `CRISIS_RESOURCE_NOTE` 并随回复落库。trace 记 `crisis="possible"`。
4. **硬词附录兜底**：`build_hard_word_appendix` 生成的附录开头加一句明确例外：对方流露自伤、自杀、绝望或危机信号时忽略本附录的反问要求，按安全底线处理。附录仍只在 `None` 级别轮次追加。
5. **前端**（`frontend/app/page.tsx` 的流式处理）：收到 `data.crisis === true` 后，本轮视为普通文字回复——不再因未收到 `generated_image` 抛「图片生成未完成/图片修改未完成」，不显示重试按钮，文字正常显示。不改任何 className 与结构。
6. 测试（后端）：三级夹具；high 轮余额充足时扣 10、交付失败退款、余额不足时不调用模型且不扣费并收到资源文案；`DEV_MODE=1` 不计费；possible 轮 `帮我查下割腕的急救方法` 仍走意图识别与工具分支（打桩断言工具被调用）且末尾有资源文案、正常计费；图片模式 high 轮不调用生图、事件序列以 `{"crisis": true}` 开头；前置 `ResourceNotFound` 返回 SSE 而非 404；硬词附录含例外句；原有安全底线顺序测试继续通过。

### T3（C）事件循环不阻塞

1. 请求处理路径（`async` 函数里）**不得直接调用**同步 sqlite3。把 `intent_router` 与 `mode_switcher` 的槽位读写改为 aiosqlite 异步实现，或在所有 async 调用点用 `await asyncio.to_thread(...)` 包裹（全库搜索调用点，包括 `routers/conversations.py`、`conversation_matcher.py`、`services/chat_service.py`；在工作线程里被调用的同步路径，如 `detect_mode` 内部，可保持同步）。选择哪种方式自定，但必须覆盖**所有**调用点。
2. 每次连接不再执行 `CHAT_SLOT_STATE_DDL`（它已在 `init_db` 中建表）。
3. 所有 SQLite 连接（aiosqlite 与同步 sqlite3）使用一致的 busy timeout（不低于 5 秒）；`init_db` 开启 WAL（`PRAGMA journal_mode=WAL`，持久生效），并在报告与 `docs/DEPLOYMENT.md` 说明对备份的影响（备份必须用 `sqlite3 .backup` 或在线备份 API，不能只拷贝主文件）。
4. 回归测试：一个心跳协程每 10ms 记录事件循环延迟；同时一个协程执行 `database.reserve_strawberries`（或等价的 `BEGIN IMMEDIATE` 事务，事务内含多次 await），另一个协程在循环里执行槽位读写（`clear_pending`/`set_pending`/`get_user_mode` 等的新调用方式）。断言：最大循环延迟 < 250ms，且无 `OperationalError`。**先在未修改的代码上运行该测试并确认失败**，把两次结果写进报告。

### T4 文档同步

凡改变事实（会话版本随机、退役表、危机三级与计费、图片模式危机、WAL 与备份方式、槽位读写方式），**全库搜索该事实的所有陈述并逐处更新**，至少包括 `CLAUDE.md`、`docs/ARCHITECTURE.md`（含其关于槽位状态的描述）、`docs/DEPLOYMENT.md`（迁移清单新增 `retired_usernames` 表与 WAL；备份命令）、`PLAN.md`（新增 `2026-09-25` 条目）。

## 4. 何时停下来问

- **必须停**：某条要求只能通过改动白名单外文件或改变前端渲染才能达成；或夹具之间存在逻辑上不可能同时满足的矛盾（此时列出冲突的具体句子，其余部分照常完成）。
- **不要停、自己定**：正则/规则的具体写法、函数命名、异步化方式、测试组织。
- 任何情况下不回滚已完成的工作。

## 5. 验收标准（Claude 会逐条独立执行）

在 `backend/` 下：
1. `.venv/bin/python -m pytest -q -p no:cacheprovider` 全部通过；逐个测试文件单独运行也全部通过；运行前后 `ls uploads | sort | shasum` 与 `ls -l *.db` 一致。
2. `compileall -q -x '\.venv' .` 退出 0。
3. T1 复现场景：旧 token 认证失败、新用户名 `tester03`。
4. T2 三级夹具全部通过；high/possible/None 的行为测试通过。
5. T3 循环延迟测试通过，且报告中有「修改前失败」的输出。
6. 全库 `grep -rn "sqlite3.connect" --include='*.py' backend | grep -v '\.venv\|tests/'` 的每个剩余调用点，都不在事件循环线程的请求路径上（报告逐一说明）。

在 `frontend/` 下：
7. `npx tsc --noEmit` 退出 0；`npm run lint` 0 error 且 warning ≤ 28；`npm run build` 成功（沙箱内 Turbopack 受限可用 `--webpack` 并说明）。
8. `git diff -- frontend` 只包含 `frontend/app/page.tsx` 的流式事件处理改动，无 className 变化。

全局：
9. `git status --porcelain --untracked-files=all` 中的路径都在第 2 节白名单内。

## 6. 交付

把变更总结写入 `docs/tasks/2026-09-25-beta-hardening/03-report.md`：修改文件、T1–T4 逐项对应（含新增测试名）、测试结果、T3 修改前后对比、已知危机识别误判写法、需要人工确认的地方。
