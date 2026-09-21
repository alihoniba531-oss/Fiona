# 完成报告：聊天上下文优化 P0/P1（T1 / T2 / T4）

> **来源声明（重要）**：本报告**不是**实施方自报。
> 实施方（Codex CLI + qwen3.8-max，session `01a08b6b`）在跑完整个测试套件之后、写本报告之前，
> 因百炼账户欠费被中断（`HTTP 400 / code: "Arrearage"`，退出码 1，累计消耗 350,726 tokens）。
> 代码与测试已全部落盘，仅本文件缺失。
> 因此本文件由 Claude 代为补写，**所有数字均来自 Claude 与独立复核者各自的实测，没有一条引用实施方的自述**。
> 独立复核结论见同目录 `04-review.md`。

---

## 1. 修改了哪些文件

相对派单前基线快照 `c4ec44f`（`git stash create` 产出的悬空 commit，仅作基线，未改动工作区）：

| 文件 | 性质 | 净增删 |
|---|---|---|
| `backend/model_router.py` | 修改 | +80 −7 |
| `backend/database.py` | 修改 | +60 |
| `backend/intent_router.py` | 修改 | +141 |
| `backend/mode_switcher.py` | 修改 | +177 |
| `backend/services/chat_service.py` | 修改 | +43 |
| `backend/tests/test_context_routing.py` | 新建 | 215 行 |
| `backend/tests/test_context_slot_state.py` | 新建 | 412 行 |
| `backend/tests/test_context_vision.py` | 新建 | 236 行 |

合计 5 个源文件修改、3 个测试文件新建。

## 2. 实现了哪些功能

- **T1**：模型路由不再拿"当前消息字数"当难度代理。新增指代信号识别（51 词表 + `其他/其它/吉他` 误伤剔除）与会话深度阈值（`CONTEXT_DEPTH_MAIN_THRESHOLD`，默认 6，置 0 关闭），使 `"那他呢？"` 这类短指代句改走主力模型。预算闸门仍在最前，成本红线未被新规则捅穿。
- **T2**：视觉分支不再丢弃历史（拼入最近 10 条纯文本），且 VL 看图产生的那句回复会作为 `image_summary` 挂回该条 user 消息，从下一轮起以 `［图中：…］` 注入模型上下文——"发一张图=对话砍两段"两半都修上了。
- **T4**：pending 追问槽位与 mode 模式状态从进程内裸 dict 改为落 SQLite `chat_slot_state` 表，带过期时间（pending 10 分钟可调、mode 24 小时兜底）。几天前没答完的追问不再劫持今天的第一句话；重启与多进程下状态一致。

## 3. 与规格 §3 任务清单的逐项对应

12 项全部实现，无半实现、无与规格不一致者。逐项证据（文件:行号）见 `04-review.md` 第一节的核验表。

| 项号 | 状态 | 关键证据 |
|---|---|---|
| T1.1 指代识别函数 | ✅ | `model_router.py:72`；词表 `:37-52` 实测与规格逐字一致（51 vs 51，缺 0 超 0 重 0）；误伤剔除 `:54,:79-81` |
| T1.2 可调阈值 | ✅ | `:57-58,:61-69`，每次现读 `os.getenv`，解析失败回落 6，≤0 整体关闭 |
| T1.3 签名与接线 | ✅ | `:123-127` 第 4 位置参数带默认值；调用点 `chat_service.py:578,:802` **均为位置传参** |
| T1.4 六条优先级 | ✅ | `:146→:150→:154→:158→:162-165→:167-168`，预算闸门在最前 |
| T1.5 docstring 同步 | ✅ | `:6-18` 已改写为六条，无旧描述残留 |
| T2a 视觉带历史 | ✅ | `chat_service.py:58` `_VL_HISTORY_TURNS=10`；`:628-639` 三段拼装，只取 role/content |
| T2b.1 数据层 | ✅ | `database.py:101` 加列；`:502` SELECT 含新列；`:509-537` `set_message_image_summary`（截断 120、限 `role='user'`、异常吞掉返 False） |
| T2b.2 写入 | ✅ | `chat_service.py:311,:485` 新字段；`:662-668` 在 `_save_response` 之后、`try/except` 包住、不额外调模型 |
| T2b.3 注入 | ✅ | `chat_service.py:444-450` 只改 `messages` 副本，`ctx.history` 与 DB `content` 零改写 |
| T4.1 表结构 | ✅ | `database.py` `CHAT_SLOT_STATE_DDL`，`owner_username` 单独成列 |
| T4.2 键序列化 | ✅ | `\x1f` 拼接；按用户清空用 `WHERE kind=? AND owner_username=?` **等值匹配，未用 LIKE/GLOB** |
| T4.3 接口不变落库 | ✅ | 8 个函数签名全未变；同步 `sqlite3`；每次访问前 DDL 兜底；函数体内现读 `database.DB_PATH` |
| T4.4 过期语义 | ✅ | pending TTL 可调默认 600s；mode 24h 兜底；`since` 返回 naive `datetime`，`detect_mode` 减法零异常 |

## 4. 验收命令的真实输出

**解释器**：`./.venv/bin/python`（非交互 shell 里 `python` 不存在，系统 `python3` 无 fastapi）。
**退出码取法**：先重定向到文件、立刻取 `$?`，避免被管道吞成 0。

### §4.0 门禁

```
$ cd backend && ./.venv/bin/python -m pytest -q > /tmp/pytest.txt 2>&1; echo "exit=$?"; tail -2 /tmp/pytest.txt
exit=0
829 passed, 13 warnings in 20.21s
```

对比派单时刻基线 **746 passed**：净增 83（= 三个新测试文件的用例数），**一条未减少**，精确闭合。
变异测试全部还原后复跑仍为 `829 passed / exit=0`。

### §4.1 / §4.2 / §4.3

三个测试文件共 83 个用例全部通过（含在上面的 829 内）。
逐条与规格验收项的对应关系见 `04-review.md` 第二节。

### 正控有效性（规格 §4 六处「正控要求」）

规格反复强调的是"测试必须证明它真的扫到了东西"。为此做了两轮变异测试：

**Claude 的 6 个变异**（把实现逐处改坏，看测试是否变红）：

| 变异 | 结果 |
|---|---|
| 删掉会话深度阈值规则 | ✅ 8 failed |
| 删掉单字指代误伤剔除 | ✅ 6 failed |
| 删掉指代信号规则 | ✅ 2 failed |
| VL 分支退回不拼历史 | ✅ 1 failed |
| 图片摘要不注入上下文 | ✅ 1 failed |
| pending 退回永不过期 | ✅ 8 failed |

6/6 被抓到，全部还原后源文件与备份逐字节一致。

**独立复核者的 31 个变异探针**：应红的 29 个全红、应绿的 2 个全绿、**0 个漏网**。
其中 M22（把 `get_pending` 退回进程内 dict）正是规格 §4.3-2 要求的自证——**该测试对旧实现确实是红的**。

结论：**六处正控全部真实有效，无一条被写成恒真断言，无一条被省略。**

### 重点风险专项（规格未要求，复核者主动加做）

- **T4 线程安全**：`_slot_conn()` 每次新建连接、`contextlib.closing` 显式关闭、连接不逃逸出函数，事件循环与 `to_thread` 工作线程各用各的。60+60+60 三方并发探针实测 **23 线程、0 错误、0 连接泄漏**；探针自带对照（故意跨线程复用会抛 `ProgrammingError`），证明它抓得到问题。
- **T4.4 时区**：穷举 13 种 payload 形状（+08:00 / −05:00 / Z 后缀 / 垃圾串 / 缺键）**全部返回 naive datetime，`detect_mode` 零 `TypeError`**。
- **T2b 三重隔离**：DB 只 `UPDATE image_summary` 从不碰 `content`；前端走 `agent_store.get_conversation_messages` 的独立 SELECT，压根没选该列且本单未改动该文件；`ctx.history` 零污染（人为加一行污染代码，正控当场抓红）。

## 5. 范围核验结果

```
$ git diff --stat <基线快照>
 backend/database.py              |  60 ++++-
 backend/intent_router.py         | 141 +++++++++++++--
 backend/mode_switcher.py         | 177 +++++++++++++++-----
 backend/model_router.py          |  80 ++++++++--
 backend/services/chat_service.py |  43 ++++--
 5 files changed, 454 insertions(+), 47 deletions(-)

新增未跟踪文件：backend/tests/test_context_{routing,slot_state,vision}.py
```

逐条对照规格 §1.3 白名单：

| 约束 | 结果 |
|---|---|
| 只动白名单内文件 | ✅ 5 源文件 + 3 新测试，**零白名单外文件** |
| `backend/tests/` 既有测试零改动 | ✅ `git diff` 对该目录为空 |
| 前端零改动 | ✅ `frontend/` 未动 |
| 无新依赖 | ✅ `requirements*.txt` 未动 |
| §1.6 现读 `database.DB_PATH` | ✅ `from database import DB_PATH` 命中 **0**；`database.DB_PATH` 命中 **2**（正控，证明"0"不是因为压根没写 DB 访问） |

## 6. 未完成 / 需人工确认

### 未完成

- 无代码项未完成。唯一缺口是本报告原本应由实施方自写，因欠费中断，现由 Claude 代补（见顶部来源声明）。

### 需人工确认（不阻塞本单验收，建议后续单处理）

1. **O1 — 本单新引入的一类阻塞风险**。aiosqlite 的写跑在自己的线程里，不阻塞事件循环；而 T4 新增的同步 `sqlite3` 写**跑在事件循环里**，一旦撞上长写事务，会把整个 event loop 卡住最长 5 秒（实测 `set_pending` 等待 5.42s 后抛 `sqlite3.OperationalError: database is locked`）。
   规格 T4.3 明文授权了"在事件循环里直接调用可接受"——**这是写规格时的判断失误**：该判断在无锁竞争时成立，在有写锁竞争时不成立。
   建议后续单：给库开 `PRAGMA journal_mode=WAL`（最省事），或把 `_slot_conn` 的 `timeout` 降到 0.5～1.0s 并给四个写函数加 `except sqlite3.OperationalError` 兜底（pending 写失败退化成"这轮不记槽位"，比 500 强）。

2. **O2 — T2a 留了半步**。`stream_image` 拼的历史来自 `ctx.history`（原始行），不是已注入摘要的 `ctx.messages`，所以连发两张图时第二轮的 VL 看不到第一张图的摘要。**完全符合 T2a 的字面要求**（规格写的就是 `ctx.history`），但从 §0 的产品目标看没走完。

3. **O3 — 两处测试覆盖缺口**（均不影响本单验收）：T2a 的"跳过空 content 历史条目"无人守（删掉该过滤，测试仍 5 passed 全绿）；`\x1f` 分隔符本身无人守（换成 `:` 仍 24 passed 全绿，但行为层面已被 §4.3-4 覆盖）。

4. **真库副作用（已清除，如实备案）**：复核过程中的变异探针 M24 为验证 §1.6，曾故意绕开 `database.DB_PATH` 往真库 `backend/fiona.db` 写入一行测试数据，事后已删除。
   Claude 独立复验结果：`chat_slot_state` 表**存在于真库但为 0 行**（探针的 DDL 兜底所建，无害，下次 `init_db()` 本也会建）；`messages` 仍为 **96 行**，用户数据完好；真库尚未跑过 `init_db()`，故 `messages` 表**还没有 `image_summary` 列**——该列会在后端下次启动时由 `_safe_migrate` 自动补上。
