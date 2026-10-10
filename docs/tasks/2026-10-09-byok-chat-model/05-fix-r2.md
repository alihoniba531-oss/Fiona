# 返修单 R2（回应 04-review-r1.md）

日期：2026-10-09。本单与 `02-spec.md`、`05-fix-r0.md`、`05-fix-r1.md`、`05-fix-r1b.md` 同等效力，冲突处以本单为准。编号 K/C/F 对应 `04-review-r1.md`。

## 0. 约束

`05-fix-r1.md` 第 0 节全部继续有效：

- 白名单、受保护文件不变；
- 本任务之前已有的测试一行都不改；
- 本任务新建的 `test_byok_*.py` 里，已有断言只有在它恰好编码了本单要改的行为时才能改，并且要在报告中列出；
- 先写会失败的测试、确认它变红，再改生产代码；
- 不安装任何包，不发起真实网络请求（只允许连 127.0.0.1 的本地桩）。

## 1. 必须修复

### R2-1 中断线程里先 shutdown 再立刻 close 有竞态（K0）

**现象**：看门狗到期（`expire`）、`ReplyStreamControl.abort()`、取消路径，以及 custom 的 `PinnedPublicBackend.abort()`，都在中断线程里先 `shutdown(SHUT_RDWR)`、紧接着 `sock.close()`。之后还会在同一线程关闭 stream、client、http_client 和 manager。

**后果**：worker 线程如果还没被 shutdown 唤醒，fd 就已经被关闭，这次唤醒会丢失，worker 一直阻塞到 60 秒读超时。复核实测：
- 同一回环测试连跑 120 次，失败 2 次；
- 预设取消竞态漏 13/150；
- 本机全量测试也失败过一次。

**改法**："中断"和"关闭"分开做：
- **中断线程**只做两件事：
  1. 置 closed / timed_out / aborted 标志；
  2. 对公开 `network_stream` 的 socket，以及 `PinnedPublicBackend` 已记录的 socket 执行 `shutdown(SHUT_RDWR)`。
- **中断线程不得调用**：`sock.close()`、`stream.close()`、`client.close()`、`http_client.close()`、`manager.__exit__`、连接池 `close`。
- **关闭由属主（worker）线程完成**，时机是阻塞调用返回之后，位置包括：
  - `ReplyStream._consume` 的 `finally`；
  - `_open` 的 `except`；
  - `chat_service` 中 `_byok_call(pool, stream.close)`。
- 读取超限路径（`_TrackedStream.read` 内部，属主线程同步执行）可以保持现状。

**新测试**：
- 把 SDK 读超时临时调成约 3 秒；
- 回环挂起服务器上，deepseek 与 anthropic 两家 × 看门狗、取消两种方式，各循环至少 20 次；
- 断言每次都在阈值内返回；
- 这组新测试合计耗时 ≤ 60 秒。

修复前要确认它变红：可以用复核员描述的最小 socket 复现，或者先只改测试、对原代码跑。

### R2-2 gzip 可绕过 4 MiB 上限（K1）

**现象**：`PinnedTransport` 原样转发了 httpx 默认的 `Accept-Encoding: gzip, deflate`，并保留上游的 `Content-Encoding`。httpx 会自动解压，而 4 MiB 上限只统计线上（压缩后）的字节。复核实测：261 KB 的 gzip 响应把内存峰值推高约 1.17 GiB。

**改法**（只影响 custom）：
1. 发请求时把 `Accept-Encoding` 强制改为 `identity`，即使 SDK 或调用方传了别的值也覆盖。
2. 收到的响应若 `Content-Encoding` 非空且不是 `identity`，立即 `self.backend.abort()` 并抛读错误。用户看到的仍是「连不上该服务」这一类别。

**新测试**：
- MockBackend 返回 gzip 炸弹（例如 64 MiB 明文），断言报固定错误类别，且没有把明文解压进内存。可以断言解压后读到的字节数为 0，或峰值远低于明文大小。
- 断言发出的请求头里 `Accept-Encoding` 为 `identity`。
- 做一次变异确认：去掉这道检查后测试应变红。

### R2-3 天气 pending 的关键词正则改变了有余额 BYOK 用户的路由（C0）

**现象**：R1 在 `run_chat` 的天气 pending 分支新加了下面这个条件。它按"是否启用 BYOK"生效，于是有余额的 BYOK 用户在天气 pending 下发「开心」「今天心情不好」时，路由也和平台不一样了。这违反规格 6.5.1：BYOK 只换回复模型，路由不变。

```python
conversational = bool(ctx.byok_config and ctx.byok_config.get("enabled")) and re.search(...)
```

**改法**：删除这个 `conversational` 条件，恢复基线判断：

```python
if state.crisis_level in {"high", "possible"} or not normalize_city(ctx.message):
```

**说明**：`05-fix-r1.md` 表格 4c 的测试消息「今天心情不好」本身是规格方的选错。`normalize_city` 会把它当作合法城市，与「照平台原逻辑」矛盾。现在把 4c 的消息改为「我今天心情不好」（`normalize_city` 对它返回空串），期望不变：pending 被清，最终由 BYOK 回复。

**新测试**：本轮新增的用例 `[weather_chat-10]` 改为与平台对照组一致。余额 10 的 BYOK 用户在天气 pending 下发「开心」时，以下几项应与未配置 BYOK 的用户完全一致：
- 事件序列；
- 工具调用，包括天气工具的参数；
- 余额；
- 是否调用了 BYOK。

### R2-4 其他 pending 下零余额 BYOK 用户仍被卡住（C1，规格方裁定）

**现象**：route、web_search、travel_plan、fetch_card 等 pending 下，零余额 BYOK 用户说任何话都只得到「草莓不足」，连「算了」都不行，最长卡 600 秒。

**改法**：在 `stream_pending` 的「参数补全，执行」分支里、零余额守卫之前加一段。仅当以下两个条件同时满足时生效：
- `ctx.byok_unreserved` 为真；
- pending 意图不是 `generate_image`，也不是 `weather`（这两种已有免费出口）。

| 消息 | 处理 |
|---|---|
| 匹配 `^(?:算了\|取消\|不用了\|不要了\|不查了\|没事了)[吧了。！!\s]*$` | 清 pending，回「好，已取消。」，并按现有取消分支的方式落库 |
| 匹配 `^(?:先聊\|聊点\|换个话题\|先不)` | 清 pending，转入 `stream_normal`，由 BYOK 回复 |
| 其他消息 | 维持现状：返回「草莓不足」，pending 保留（规格 6.9 第 11 条） |

平台路径与有余额用户的行为不变。

**新测试**：
- 走真实接口：余额 10 时用「怎么去机场」造出 route pending（分类桩返回 route，missing=[origin]），再把余额置 0。
  - 发「算了」：得到「好，已取消。」，pending 被清，余额不变。
  - 发「换个话题」：pending 被清，调用 1 次 BYOK，带 `reply_model`。
  - 发「从家出发」：得到「草莓不足」，pending 原样保留，工具桩未被调用。
- web_search pending 至少再覆盖「算了」一种。
- 对照组：余额 10 的 BYOK 用户与未配置用户的行为一致。

### R2-5 后台刷新清掉了用户正在看的失败文案（F0）

**现象**：`ChatModelSection` 的 refresh 成功后会无条件执行 `setError("")`。切回标签页或其他文档写入版本号时，测试连接、保存等操作的失败原因会凭空消失。

**改法**：refresh 只清除它自己产生的加载错误：
- refresh 失败时，记一个标志（例如 `refreshError` ref）再 `setError`；
- refresh 成功时，只有该标志为真才清错误；
- save、test、toggle、remove 开始时，把该标志复位。

**新测试**：用 Playwright 或组件级测试验证以下两种情况：
- 测试连接失败后，派发 `visibilitychange`，失败文案仍在；
- 测试连接失败后，在另一文档写入 `CHAT_MODEL_REV_KEY`，失败文案仍在。

## 2. 一并修复的低成本改进

### R2-6

1. **K2 / C2 / F1 文档更正**：「总时长即 `FIONA_BYOK_TOTAL_SECONDS`」不准确，改为：「响应头到达后，所有厂商在总时限或取消时立即中断；上游在返回响应头之前挂起时，预设厂商最多再等 60 秒读超时，custom 会立即中断。」涉及 README、CLAUDE、ARCHITECTURE、DEPLOYMENT 中凡出现此说法的地方。
2. **C3**：中途取消时，asyncio 每次都会打一条 ERROR 级的「exception in shielded future」日志。
   - 第一次等待改为 `await asyncio.wait({future})` 再取 `future.result()`；
   - 取消分支在 abort 之后，于 shield 作用域内等待 future 结束，并显式调用 `future.exception()` 把它取走；
   - 补一条断言：取消后 caplog 中没有这条日志。
3. **F2**：`/chat-model/test` 撞上平台自身 10 次/分钟限流时，HTTP 200 保持不变，但 message 改为平台侧文案「操作太频繁，请稍后再试」，不再以「你的模型调用失败」开头。同步更新对应的测试断言与文档。
4. **F3**：底栏 `ChatModelFooter` 初次加载失败时，给出一个可点击的「重试」入口，并在 `visibilitychange` 变为可见时自动刷新。

## 3. 验收

- 重跑第 7 节第 1–6 条。
- 全量 `python -m pytest -q` 的通过数 ≥ 2778 + 本轮新增数；沙箱内既有的端口权限失败和需要回环的跳过项可以忽略，由主控在沙箱外重跑。
- 前端：`npx tsc --noEmit` 为 0；`npx eslint .` 为 0 errors，warnings ≤ 25。
- 更新 `03-report.md`，新增「R2 返修」一节，逐条对应 R2-1 至 R2-6，写明：
  - 改了什么；
  - 新测试名；
  - 修复前的失败摘要；
  - 修改了哪些既有 byok 断言，以及依据。
