# 规格：聊天上下文优化 P0/P1（T1 模型路由 / T2 视觉分支 / T4 槽位状态）

> 本规格自包含。实施者是独立进程，看不到任何对话上下文；规格里没写的，按"技术实现约束"办，不要自由发挥。
> 仓库根目录 = `Fiona/`，所有路径相对它。后端工作目录是 `backend/`。

---

## 0. 产品目标 / 使用场景

Fiona 是个人 AI 分身陪聊产品。当前用户反馈的核心症状是**「分身听不懂上下文」**：
指代解析不了（"那他呢？"）、发完图之后前面聊的全忘、几天前一个没答完的追问会劫持今天第一句话。

代码审计定位到六处独立的上下文丢弃点，本单修其中三处（编号沿用审计报告，故不连续）：

| 编号 | 症状 | 根因 |
|---|---|---|
| T1 | 越是需要历史才能理解的短句，回答越蠢 | 模型路由拿"当前这条消息的字数"当难度代理，`"那他呢？"`（4 字）被判为简单闲聊丢给轻量模型 |
| T2 | 发一张图，等于把对话砍成两段 | 视觉分支组装请求时完全不带历史；且图片消息落库成 `[发了一张图片]`，后续轮次也无从知道图里是什么 |
| T4 | 隔天回来，第一句话被当成参数填进旧追问 | 待补参槽位（pending）存在进程内裸 dict，无过期时间、无持久化 |

**验收的最终标准是这三个症状消失，不是代码写得像规格。** 若实现过程中发现规格写的做法解决不了症状，按 §6 停下来问。

---

## 1. 技术实现约束（硬约束）

1. **沿用现有技术栈**：Python 3.14 / FastAPI / SQLite（`aiosqlite` 异步 + `sqlite3` 同步）/ OpenAI 兼容 SDK。**不引入任何新的第三方依赖**，`requirements*.txt` 不得改动。
2. **不做无关重构**。不得重命名既有函数、不得调整既有文件的模块结构、不得"顺手优化"规格没点名的代码。
3. **修改范围白名单**——只允许改动/新建以下文件，动白名单外的任何文件都算越界：
   - `backend/model_router.py`
   - `backend/services/chat_service.py`
   - `backend/intent_router.py`
   - `backend/mode_switcher.py`
   - `backend/database.py`
   - `backend/tests/` 下**新建**的测试文件（命名 `test_context_*.py`）
   - 本规格所在目录下的 `03-codex-report.md`（你的完成报告）

   **特别注意：`backend/tests/` 下的既有测试文件一律不得修改。** 若你认为某个既有测试必须改才能通过，那说明你的实现破坏了既有契约——改实现，不要改测试；确实改不了就按 §6 停下来问。
4. **前端不动**。`frontend/` 整个目录不在白名单内。本单的所有改动必须对前端透明：新增的 JSON 字段前端会忽略，但不得删除或重命名任何既有字段。
5. **不读取 `.env`、密钥、用户数据**。不得连接真实数据库 `backend/fiona.db`。
6. **数据库路径规矩（会导致测试污染真库，务必遵守）**：
   `backend/tests/conftest.py` 靠 `monkeypatch.setattr(database, "DB_PATH", ...)` 做隔离，其前提是**所有数据库访问都在调用时现读模块全局 `database.DB_PATH`**。
   因此本单新增的任何数据库访问，必须写成 `import database` 后在函数体内读 `database.DB_PATH`，
   **绝对不允许** `from database import DB_PATH` 或在模块顶层/类属性里缓存该路径。

---

## 2. 现状事实（已在工作区 HEAD 实测，实现前请自行复核一遍再动手）

以下是派单时刻工作区的真实状态。**工作区有大量与本单无关的未提交改动（图片生成功能），这是正常的，不要动它们，也不要 commit / stash / checkout / reset 任何东西。**

- `backend/model_router.py:70` `choose_model(username, message, mode)` 现有三个位置参数。
- `backend/services/chat_service.py:568` 与 `:781` 是它仅有的两个生产调用点。
- **`backend/tests/test_spec_bugfixes.py:372` 用 `monkeypatch.setattr(chat, "choose_model", lambda *args: "main")` 打桩。`lambda *args` 只接受位置参数——新参数若以关键字方式传入，该测试会 `TypeError` 当场炸。**
- `backend/services/chat_service.py:618` 的 `vl_messages` 目前只有两条消息（system + 当前多模态 user），`ctx.history` / `ctx.messages` 在视觉分支里根本没被使用。
- `backend/services/chat_service.py:384` 拉历史：`get_messages(user, limit=60, conversation_id=...)`。
- `backend/database.py` 的 `save_message(...)` 返回 `bool`（成败），**不返回 message id**。
- 上传图片落库路径格式为 `/uploads/<uuid4 hex 32 位>.<ext>`（见 `backend/utils/media.py:160`），全局唯一，可作定位键。
- `backend/database.py:11` 有 `_safe_migrate(db, sql)`，专用于老库加列/加索引，重复执行安全。
- `backend/intent_router.py:9` `_pending: dict[StateKey, dict] = {}`，`backend/mode_switcher.py:23` `_mode_state: dict[StateKey, dict] = {}`。二者都是进程内裸 dict。
- `StateKey = str | tuple[str, str]`，元组形态是 `(username, conversation_id)`。

---

## 3. 任务清单

### T1 — 模型路由纳入会话深度与指代信号

**文件**：`backend/model_router.py`（本体）、`backend/services/chat_service.py`（调用点）

**T1.1** 新增指代信号识别函数：

```python
def has_context_reference(message: str) -> bool:
    """消息是否含有必须依赖上文才能解析的指代/省略信号。"""
```

判定用的词表**必须完整包含以下条目，一个不少**（可以多，但多加的要在报告里列出并说明理由）：

```
那个 那件 那条 那张 那款 那家 那位 那边
这个 这件 这条 这张 这款 这家 这位 这边
他 她 它 他们 她们 它们
刚才 刚刚 方才 上面 前面 之前 上次 上一个 上一条
第一个 第二个 第三个 第几 哪个
还是 继续 接着 然后呢 那呢 再来 再来一个 换一个 换个
一样 同样 同上 你说的 你刚说 按你说的
```

**单字指代的误伤处理（必须实现）**：`他` / `它` 用朴素 `in` 匹配会被 `其他` / `其它` / `吉他` / `其他人` 误触发。
实现时必须先把 `其他`、`其它`、`吉他` 从待匹配文本中剔除（替换为空串）再做匹配。
（`他们` / `她们` / `它们` 本身就是指代，必须保留为命中。）

**T1.2** 新增可调阈值，读环境变量：

- 变量名 `CONTEXT_DEPTH_MAIN_THRESHOLD`，默认值 `6`。
- 语义：会话已积累的历史消息条数 ≥ 该值时，走主力模型。
- **设为 `0` 或负数时该条规则整体关闭**（用于成本回退，必须支持）。
- 解析失败（非整数）时回落默认值 `6`，不得抛异常。
- 读取时机必须是**每次调用时现读** `os.getenv`，不得在模块导入时固化为常量——否则测试无法用 `monkeypatch.setenv` 覆盖。

**T1.3** 改签名并接线：

```python
def choose_model(username, message, mode, history_len: int = 0) -> Literal["main", "light"]:
```

- `history_len` 必须是**第 4 个位置参数并带默认值 `0`**。
- 两个调用点（`chat_service.py` 里 mirror 分支与 normal 分支）**必须用位置参数传入**：
  `choose_model(ctx.user, ctx.user_content, "normal", len(ctx.history))`
  **不得写成 `history_len=len(ctx.history)`** —— 理由见 §2 第 3 条（`lambda *args` 打桩）。

**T1.4** `normal` 模式的路由优先级，严格按下表实现（1 最先判，命中即返回）：

| # | 条件 | 结果 | 新旧 |
|---|---|---|---|
| 1 | `token_budget.is_over_budget(username)` 为真 且 消息不含创作关键词 | `light` | 原有，不变 |
| 2 | 消息含 `CREATIVE_KEYWORDS` 任一 | `main` | 原有，不变 |
| 3 | `len(message.strip()) > 80` | `main` | 原有，不变 |
| 4 | `has_context_reference(message)` 为真 | `main` | **新增** |
| 5 | 阈值 > 0 且 `history_len >= 阈值` | `main` | **新增** |
| 6 | 兜底 | `light` | 原有，不变 |

**注意规则 1 的位置**：预算超限时，规则 4/5 不得把请求抬回 `main`（预算闸门优先级最高，这是成本红线）。

`mirror` 与 `image` 模式**恒返回 `light`，本单不改**。

**T1.5** 同步更新 `model_router.py` 顶部 docstring 的"路由规则"段落，让它与实际实现一致（该 docstring 目前描述的是旧的四条规则）。

---

### T2 — 视觉分支拼历史 + 图片摘要落库

#### T2a 视觉请求带上历史

**文件**：`backend/services/chat_service.py`，函数 `stream_image`

把 `vl_messages` 从两条改为三段：

1. `{"role": "system", "content": vl_system}`（保持不变）
2. **新增**：`ctx.history` 的**最后 10 条**，逐条映射为 `{"role": m["role"], "content": m["content"]}` 的纯文本消息。
3. `{"role": "user", "content": [图片, 当前文字]}`（保持不变，仍是最后一条）

约束：

- 只取 `role` 与 `content` 两个字段，**不得**把历史里的图片、`image_path`、`reference_image_paths` 塞进多模态结构——本轮只发当前这一张图。
- `content` 为空或 `None` 的历史条目跳过。
- `ctx.history` 不足 10 条时有多少取多少；为空时 `vl_messages` 退化回原来的两条。
- 数量 `10` 定义为模块级常量 `_VL_HISTORY_TURNS = 10`，便于日后调整。

#### T2b 图片内容进入长期文字记录

现状：用户发图那条 user 消息落库成 `[发了一张图片]`（或用户自己配的文字），
所以**下一轮**开始，模型再也无从知道那张图里有什么。这是"发图=对话砍两段"的另一半，必须一起修。

**T2b.1 数据层** — `backend/database.py`

- 在 `init_db()` 中用既有的 `_safe_migrate` 加列：
  `ALTER TABLE messages ADD COLUMN image_summary TEXT DEFAULT NULL`
- `get_messages(...)` 的 `SELECT` 列表增加 `image_summary`，使其出现在返回的 dict 中。
- 新增函数：

  ```python
  async def set_message_image_summary(
      username: str, conversation_id: str | None, image_path: str, summary: str
  ) -> bool:
  ```

  - 按 `username` + `image_path`（+ `conversation_id`，非 None 时）定位并 `UPDATE` 该行的 `image_summary`。
  - 只更新 `role = 'user'` 的行。
  - 命中并更新返回 `True`，未命中返回 `False`（**不抛异常**——摘要写入失败绝不能影响已经成功返回给用户的回复）。
  - `summary` 入库前截断到 **120 个字符**。

**T2b.2 写入** — `backend/services/chat_service.py`，`stream_image`

- 在 `await _save_response(ctx, state)` **成功之后**，用 VL 本轮产生的 `state.full_response` 作为摘要，
  调用 `set_message_image_summary(ctx.user, ctx.conversation_id, <本轮上传图的 image_path>, state.full_response)`。
- **不得为此额外调用任何模型**（省钱、省延迟）——摘要直接复用 VL 已经生成的回复文本。
- 整个写入用 `try/except` 包住，异常只打印 `[chat] image summary write failed type=<类型名>` 并继续，**不得**中断 SSE、不得改变 `yield` 序列、不得影响扣费。
- **取图路径的坑**：`stream_image` 当前作用域里没有 `image_path` 变量（它在 `build_context` 里是局部变量，用完即弃）。
  你需要把它带到 `ChatContext` 上：新增字段 `uploaded_image_path: str | None = None`，在 `build_context` 里赋值。
  该字段仅在 `has_image` 为真时非 None。

**T2b.3 注入** — `backend/services/chat_service.py`，`build_context`

组装 `messages` 时（现为 `messages = [{"role": m["role"], "content": m["content"]} for m in history]`），
若某条历史的 `image_summary` 非空，则该条的 `content` 渲染为：

```
f"{content}［图中：{summary}］"
```

（方括号用全角 `［］`，与既有的 `[发了一张图片]` 半角占位符区分开，便于验证时精确 grep。）

约束：

- 只影响**注入给模型的** `messages`，**不得**改写数据库里的 `content`，**不得**改变 `/conversations/{id}/messages` 接口返回给前端的 `content`——前端渲染的用户气泡必须原样不变。
- `ctx.history` 本身保持原始行（`_compute_hours_since_last_user`、`_compute_length_drop`、`extract_and_update`、意图识别都在读它，改了会连锁破坏）。

---

### T4 — 槽位状态加过期时间并持久化

**文件**：`backend/database.py`、`backend/intent_router.py`、`backend/mode_switcher.py`

**T4.1 表结构** — 在 `database.py` 的 `init_db()` 中创建：

```sql
CREATE TABLE IF NOT EXISTS chat_slot_state (
    state_key       TEXT NOT NULL,
    kind            TEXT NOT NULL,
    owner_username  TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    expires_at      TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (state_key, kind)
)
```

- `kind` 取值只有两个：`'pending'`、`'mode'`。
- `owner_username` 单独存一列，是为了让"清空某用户全部槽位"能写成 `WHERE owner_username = ?`。
  **不得**改用 `LIKE` / `GLOB` 前缀匹配 `state_key`——用户名里若含 `%`、`_`、`*`、`?` 会误删他人数据。

**T4.2 键序列化**

`StateKey` 是 `str`（旧的账号级）或 `(username, conversation_id)`（会话级）：

- `str` → `state_key = username`，`owner_username = username`
- 元组 → `state_key = f"{username}\x1f{conversation_id}"`，`owner_username = username`

**T4.3 接口不变，实现改为落库**

以下 8 个函数的**签名、参数、返回类型全部保持不变**（它们是同步函数，且被 `asyncio.to_thread` 与事件循环两种上下文调用，改成 async 会连锁炸掉调用点）：

- `intent_router`：`get_pending` / `set_pending` / `clear_pending` / `clear_user_pending`
- `mode_switcher`：`get_user_mode` / `set_user_mode` / `clear_user_mode` / `clear_all_user_modes`

实现要求：

- 内部改用**同步 `sqlite3`**（标准库，不是 `aiosqlite`）读写 `chat_slot_state`。单行主键操作，微秒级，在事件循环里直接调用可接受。
- 每次访问前先执行一次 `CREATE TABLE IF NOT EXISTS chat_slot_state (...)` 作为兜底——
  部分既有测试（如 `tests/test_chat_image_generation.py:66`）不经 `client` fixture 就直接 `import` 并调用 `set_pending`，那时 `init_db()` 可能还没跑过。
- 连接路径按 §1.6：函数体内现读 `database.DB_PATH`。
- 进程内 dict `_pending` / `_mode_state` **删除**，不保留为缓存（多进程下缓存会不一致）。
- 连接用完必须关闭；建议每次操作 `with sqlite3.connect(...) as conn`（注意 `sqlite3` 的 context manager 只管事务不管关闭，仍需显式 `close()` 或用 `contextlib.closing`）。

**T4.4 过期语义**

- **pending**：写入时 `expires_at = now + PENDING_TTL_SECONDS`。
  - 环境变量 `PENDING_TTL_SECONDS`，默认 `600`（10 分钟）；解析失败回落默认；每次调用现读。
  - `get_pending` 读到已过期的行，**必须当作不存在**（返回 `None`）并顺手删除该行。
- **mode**：写入时 `expires_at = now + 24 小时`（硬编码兜底，不设环境变量）。
  - `get_user_mode` 读到已过期的行，当作不存在，回落默认值 `{"mode": "friend", "since": <当前时刻>, "last_trigger": None}`。
  - **`MIRROR_TIMEOUT_MINUTES = 30` 的既有退出逻辑一字不改。** 24 小时是兜底上限，不是替代品。
- 时间一律用 **UTC**（`datetime.now(timezone.utc)`）存取。
  `mode` 的 payload 里 `since` 是 `datetime` 对象，JSON 化时序列化为 ISO 字符串，读回时用 `datetime.fromisoformat` 还原为 `datetime`。
  **`get_user_mode` 返回的 dict 里 `since` 必须仍是 `datetime` 对象**——`mode_switcher.detect_mode` 里有 `datetime.now() - state["since"]` 的减法，返回字符串会当场 `TypeError`。
  注意既有代码用的是 naive `datetime.now()`，做减法时两边的 tz-aware 性必须一致，否则 `TypeError: can't subtract offset-naive and offset-aware datetimes`。这是本单最容易踩的坑，请显式处理并写测试覆盖。

**T4.5 不在本单范围**

- 不改 mirror 模式的进入/退出判定逻辑。
- 不改 `MIRROR_TIMEOUT_MINUTES`、不改 `max_tokens=80`。
- 不给 `chat_slot_state` 写定时清理任务（过期行在读到时顺手删即可）。

---

## 4. 验收标准

以下命令在 `backend/` 目录下执行。**每条都要实际跑、贴真实输出**，不得只写"通过"。

**解释器（已实测，照抄，否则会浪费你一轮）**：非交互 shell 里 `python` 不存在，系统 `python3` 没装 `fastapi`。
本仓库的依赖装在 `backend/.venv`，必须用 `./.venv/bin/python`：

```bash
cd backend
./.venv/bin/python -m pytest -q
```

（必须走 `-m pytest`，直接调 `pytest` 可能导入不到后端顶层模块。）

**退出码不要被管道吞掉**：`... | tail` 之后 `$?` 是 `tail` 的退出码，永远是 0，会把失败伪装成通过。
要看真实结果就先重定向到文件、立刻取 `$?`，再去读文件：

```bash
./.venv/bin/python -m pytest -q > /tmp/pytest.txt 2>&1; echo "exit=$?"; tail -20 /tmp/pytest.txt
```

### 4.0 门禁（先跑，必须全绿）

```bash
cd backend && ./.venv/bin/python -m pytest -q > /tmp/pytest.txt 2>&1; echo "exit=$?"; tail -20 /tmp/pytest.txt
```

期望：**exit=0，0 failed、0 error**。
**派单时刻的基线是 `746 passed（exit=0，耗时约 20 秒）`**——实现后测试数只允许增加（你新写的那些），一条都不许减少。
报告里必须同时贴出你跑到的数字和这个基线数字做对比。

### 4.1 T1 验收

新建 `backend/tests/test_context_routing.py`，覆盖：

1. **指代命中**：`choose_model("u", "那他呢？", "normal", 0) == "main"`
2. **反例（防止词表过宽把一切都判成 main）**：`choose_model("u", "今天天气不错", "normal", 0) == "light"`
3. **单字误伤已处理**：以下三条全部期望 `light`（若未实现 `其他`/`其它`/`吉他` 剔除，它们会因含单字 `他`/`它` 而误判为 `main`）：
   - `choose_model("u", "其他人也这么说", "normal", 0) == "light"`
   - `choose_model("u", "其它的都可以", "normal", 0) == "light"`
   - `choose_model("u", "我在弹吉他", "normal", 0) == "light"`

   同时断言剔除处理**没有把真指代一起吃掉**：`choose_model("u", "他们同意了吗", "normal", 0) == "main"`
4. **深度阈值**：`choose_model("u", "嗯", "normal", 6) == "main"`；`choose_model("u", "嗯", "normal", 5) == "light"`
5. **阈值可关闭**：`monkeypatch.setenv("CONTEXT_DEPTH_MAIN_THRESHOLD", "0")` 后
   `choose_model("u", "嗯", "normal", 999) == "light"`
6. **预算闸门优先级**（成本红线）：让 `token_budget` 超限后，
   `choose_model("u", "那他呢？", "normal", 999) == "light"`（规则 1 压住规则 4/5）
7. **mirror 恒 light**：`choose_model("u", "那他呢？", "mirror", 999) == "light"`
8. **向后兼容**：`choose_model("u", "今天天气不错", "normal")`（只传 3 个参数）不抛异常且返回 `light`

**正控要求**：第 4 条的 `>= 6` 边界，测试里必须**同时**断言 5 → light 和 6 → main。
只断言其中一侧，把阈值实现成任何常数都能过。

### 4.2 T2 验收

新建 `backend/tests/test_context_vision.py`，覆盖：

1. **T2a**：构造一个含 12 条历史的会话，调用视觉分支，断言送进视觉模型的 `messages` 长度为
   `1 (system) + 10 (history) + 1 (current) = 12`，且第 2 条的 `content` 等于历史倒数第 10 条的内容。
   **正控**：先断言在"历史为空"时长度为 2——若两种情况长度相同，说明历史根本没拼进去。
2. **T2a 隔离**：断言这 10 条历史消息里，没有任何一条的 `content` 是 list 类型（即没有混进多模态结构）。
3. **T2b 写入**：走完一次视觉分支后，查库断言该 user 消息行的 `image_summary` 非空且 ≤ 120 字符。
4. **T2b 注入**：在 `build_context` 产出的 `messages` 里，断言对应那条的 content 含 `［图中：`。
   **正控**：同时断言 `ctx.history` 里对应那条的 `content` **不含** `［图中：`（证明只改了注入副本，没污染原始历史）。
5. **T2b 前端不受影响**：`GET /conversations/{id}/messages` 返回的该条 `content` 不含 `［图中：`。

### 4.3 T4 验收

新建 `backend/tests/test_context_slot_state.py`，覆盖：

1. **pending 过期即弃**：`set_pending` 后把 `PENDING_TTL_SECONDS` 设为 `0`（或直接改库里的 `expires_at` 为过去时刻），
   断言 `get_pending` 返回 `None`，且该行已从 `chat_slot_state` 删除。
   **正控**：未过期时 `get_pending` 必须返回原 payload——否则"永远返回 None"也能过这条。
2. **跨进程持久化**：`set_pending` 后，用 `importlib.reload(intent_router)` 重新加载模块（模拟重启），
   断言 `get_pending` 仍能读到。**正控**：改造前这条必然失败（旧实现是进程内 dict），
   请在报告里说明你确认过这条测试对旧实现是红的。
3. **`since` 类型**：`set_user_mode(key, "mirror")` 后 `get_user_mode(key)["since"]` 必须是 `datetime` 实例，
   且 `datetime.now(...) - state["since"]` 能正常相减不抛 `TypeError`。
4. **元组键与字符串键互不串扰**：`set_pending("alice", A)` 与 `set_pending(("alice", "conv1"), B)` 并存，
   两者 `get_pending` 各自读回自己的值。
5. **按用户清空**：`clear_user_pending("alice")` 清掉 alice 的账号级与所有会话级 pending，
   但不影响用户名为 `alice%` 或 `alice_bob` 的其他用户（**这条专门防 LIKE 通配符误删**）。
6. **mode 24 小时兜底**：把 mode 行的 `expires_at` 改到过去，断言 `get_user_mode` 回落 `friend`。

### 4.4 范围核验（自查，报告里必须回答）

```bash
git status --porcelain
```

逐行核对：新增/修改的文件是否**全部**落在 §1.3 白名单内。
若有白名单外的文件被改动（含新建的未跟踪文件），必须在报告里逐个列出并说明原因。

---

## 5. 效率要求

按**文件不重叠**的边界拆给多个 subagent 并行处理，缩短总时长：

- **A 组**：`model_router.py` + `tests/test_context_routing.py`（T1 本体与测试）
- **B 组**：`database.py`（T2b.1 加列 + T4.1 建表 + 两个新函数）—— **此文件同时被 T2 与 T4 需要，必须由单一 subagent 串行处理，禁止两个 agent 同时改它**
- **C 组**：`intent_router.py` + `mode_switcher.py` + `tests/test_context_slot_state.py`（T4 接口层，依赖 B 组的表结构先落地）
- **D 组**：`services/chat_service.py` + `tests/test_context_vision.py`（T1 调用点 + T2a + T2b.2/3）

依赖顺序：B 先行；A 与 B 可并行；C、D 等 B 完成后并行。
`chat_service.py` 同时承载 T1 调用点与 T2 改动，**必须由 D 组一个 agent 串行完成，不得拆给两个 agent**。

---

## 6. 何时停下来问（判据）

**只有影响"实现什么"的分歧才停；只影响"怎么验证"的细节自己定，在报告里说明即可。**

必须停下来问的情形：

1. 规格要求的改动与既有测试的契约冲突，且**改实现无法两全**（例如某既有测试断言 `choose_model` 恰好三个参数）。
2. 白名单内的文件不足以完成某项任务，必须动白名单外的文件。
3. 发现规格自相矛盾，或某条验收标准在规格描述的实现下**不可能通过**。
4. 需要删除既有数据、改动既有表的列定义（加列不算）、或变更任何依赖。

自己定就行、不必问的情形：测试用例的具体构造方式、fixture 组织、日志文案、变量命名、注释措辞、辅助函数的拆分粒度。

**任何情况下都不要回滚或撤销已完成的工作，也不要 `git commit` / `git stash` / `git checkout` / `git reset`。**
工作区里有大量与本单无关的未提交改动，任何 git 状态操作都会造成不可逆的损失。**只改文件，不碰 git。**

---

## 7. 交付物

在 `docs/tasks/2026-09-10-聊天上下文优化-P0P1/03-codex-report.md` 写完成报告，必须包含：

1. 修改了哪些文件（逐个列出，标明新建/修改）
2. 实现了哪些功能
3. 与 §3 任务清单的**逐项**对应关系（T1.1～T1.5、T2a、T2b.1～T2b.3、T4.1～T4.4，一项不落）
4. §4 每条验收命令的**真实输出**（贴原文，含 pytest 的通过/失败计数）
5. §4.4 范围核验的结果
6. 未完成的、有疑虑的、需要人工确认的地方
