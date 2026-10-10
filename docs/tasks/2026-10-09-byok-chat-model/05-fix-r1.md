# 返修单 R1（回应 04-review.md）

日期：2026-10-09。与 `02-spec.md`、`05-fix-r0.md` 同等效力，冲突处以本单为准。复核记录见本目录 `04-review.md`（编号 S/B/C/F/D 对应其中各条）。

## 0. 约束（不变 + 补充）

- 第 7.1 条文件白名单、7.2 受保护文件、「不得修改 `backend/tests/` 下任何**本任务之前就存在**的文件」、不安装包、不发起真实网络请求，全部不变。
- 本任务新建的 `backend/tests/test_byok_*.py` 可以追加用例。**已有断言**只允许在它恰好编码了本单要改的行为时修改（例如 R1-2 的守卫位置、R1-3 的空 system、R1-5 的变量清单），其他断言不得放宽；每处修改都要在报告里列出「原断言 → 新断言 → 依据本单哪一条」。
- 每条修复先写会失败的测试，确认它在修复前变红，再改生产代码（报告里写明各新测试修复前的失败输出摘要）。

## 1. 必须修复

### R1-1 中文域名自定义地址永远连不上（S0）

`backend/byok/url_safety.py` 中 `PinnedTransport.handle_request` 的主机比较用了 `request.url.host`（httpx 会把 `xn--` 主机解码成 Unicode），与保存时规范化得到的 punycode `self.hostname` 永远不等，导致用 Unicode 或 punycode 填写的合法地址在保存成功后，测试连接和聊天全部报「连不上该服务」。

- 改为按 ASCII 形式比较：`request.url.raw_host.decode("ascii").lower()` 对比 `self.hostname.lower()`。scheme 与端口检查保持不变。
- 新测试：分别用 `https://例子.com/v1` 和 `https://xn--fsqu00a.com/v1` 构造 `PinnedTransport` + 记录型 MockBackend，经真实 `openai.OpenAI(http_client=...)` 流式调用成功。断言 `targets == [("8.8.8.8", 443)]`，`server_names == ["xn--fsqu00a.com"]`。

### R1-2 零余额 BYOK 用户被残留的待补参数卡死（B0）

现状：`stream_pending` 顶部守卫连免费的取消分支也拦掉；`run_chat` 与 `stream_mirror` 多处 `clear_pending` 被 `if not ctx.byok_unreserved` 包住；天气取消前多了一个 `_unreserved_error`。后果是零余额 + 启用 BYOK + 残留 pending 时，「换个话题」「算了」和普通聊天都返回「草莓不足」，自带模型一次也不被调用。

按规格 6.5.6 的原意，守卫只放在**真正会花钱的动作之前**：

1. `stream_pending`：把顶部守卫移到「参数补全，执行」分支里、该分支的 `clear_pending` 之前（守卫命中时不清 pending）。取消分支（「好，已取消。」）和「还缺参数、继续追问」分支照平台原逻辑执行，都免费；追问分支的天气额度检查仍是 `hit=False`，不计数。
2. 恢复与平台一致的 `clear_pending`，即去掉 `if not ctx.byok_unreserved` 包裹：
   - `run_chat` 中界面生图/修图模式分支（该分支在未预扣时不可达，按原样还原）；
   - 「缺少修图参考的固定引导」分支；
   - generate_image pending 遇到讨论、致谢、「先聊/换个话题/算了/取消」、疑问句时清 pending 的分支；
   - 天气 pending 遇到危机档位或非城市消息时清 pending 的分支；
   - `stream_mirror` 中手动镜子触发的清 pending。
3. 删除天气 pending「算了/取消」分支前的 `_unreserved_error`，该分支照平台逻辑：清 pending、回「好，已取消。」、免费。
4. **保留**一处包裹：generate_image pending 期间识别出新的工具意图、即将进入 `stream_intent` 的那一处 `if not ctx.byok_unreserved: clear_pending`。这是规格 6.9 第 11 条「让它走工具时 pending 原样保留」的要求，并在代码注释里写明这个理由。
5. 新测试：零余额（余额 0）、已启用 BYOK、DEV_MODE=0、真实走 `/chat`。用例 5 先用真实接口制造残留 pending，例如有余额时说「帮我画张图」、平台追问，再把余额设为 0。用例 1–4 可直接 `set_pending`。

   | # | 前置 pending | 发送消息 | 期望结果 |
   |---|---|---|---|
   | 1 | generate_image | 「换个话题」 | pending 被清；`open_reply_stream` 调用 1 次，回复带 `reply_model`；余额不变 |
   | 2 | generate_image | 「算了」 | 回「好，已取消。」；pending 被清；余额不变 |
   | 3 | generate_image | 「一只橘猫」（补全参数） | 恰好收到路由一致的「草莓不足」；生图桩未调用；pending 原样保留 |
   | 4 | weather | 「算了」 | 回「好，已取消。」，pending 被清 |
   | 4 | weather | 「上海」 | 「草莓不足」；天气额度未计数；pending 保留 |
   | 4 | weather | 「今天心情不好」 | pending 被清；最终由 BYOK 回复 |
   | 5 | generate_image | 「查一下北京明天天气」 | 「草莓不足」；工具桩未调用；pending 原样保留 |

   对照组：余额 10 的同配置用户，行为与基线平台路径一致。

### R1-3 测试连接发出空的 system（C0）

`convert_messages` 在没有任何 system 消息时（测试连接只传一条 user 消息），OpenAI 兼容厂商仍拼出 `{"role":"system","content":""}`，Claude 仍传 `system=""`。

- OpenAI 兼容：system 为空串时不生成 system 消息。
- Claude：只有 system 非空时才往 kwargs 里放 `system`，否则不传，让 SDK 自动省略。
- dashscope 行为不变。
- 新测试用真实 SDK + MockTransport 抓请求体，断言：
  - deepseek、moonshot、zhipu、custom 的测试连接请求里没有空 content 的消息；
  - Claude 测试连接请求体没有 `system` 键；
  - 普通聊天请求仍恰好一条非空 system（Claude 为顶层 `system`），且基础安全规则恰好一次、在末尾。

### R1-4 自定义上游没有响应字节上限（S1）

`_TrackedStream.read` 不计字节。恶意公网上游持续推送无换行 SSE 或无限错误体，可以在总时限内把进程内存打爆（复核实测 50 MiB 推送 → 214 MiB 峰值）。

- 在 `_TrackedStream` 中累计该连接已读字节，上限为常量 `4 * 1024 * 1024`（含 TLS 之上的全部 HTTP 字节）。
- 超限时调用 `self.backend.abort()`，并抛出能经 `_map_errors` 映射的 httpcore 读错误。用户看到的文案必须是第 6.4 节错误映射里的固定文案之一，建议归入「调用失败」或「连不上该服务」，在报告里写明选了哪个。
- 只作用于 custom（PinnedTransport），预设厂商不变。
- 新测试：MockBackend 持续返回 64 KiB 无换行块，以及 401 + 无限错误体两种情况。断言流在已读 ≤ 上限 + 一个读块时中止，抛出预期的固定错误类别，且 MockBackend 实际送出的字节数不超过上限 + 一个读块。

### R1-5 `ANTHROPIC_CUSTOM_HEADERS` 未列入违规环境变量（C2）

anthropic 1.12.1 的 `_client.py` 会读取 `ANTHROPIC_CUSTOM_HEADERS`，并把它注入每个请求的头里，与已拦截的 `OPENAI_CUSTOM_HEADERS` 对称。

- 把它加入 `byok/crypto.py` 的 `FORBIDDEN_ENV`。
- 另请通读 `.venv` 中 `anthropic`（1.12.1）与 `openai`（2.37.0）的客户端构造与 `_base_client` 源码，列出所有 `os.environ` / `os.getenv` 读取。凡是在我方显式传入 `api_key`、`base_url`、`http_client`（或 `timeout`）后仍会改变请求目标、请求头、凭据或代理的变量，一并加入 `FORBIDDEN_ENV`。
- 在报告里给出完整清单：每个变量注明「加入 / 不加入 + 理由」，例如 `ANTHROPIC_API_KEY` 被显式 `api_key` 覆盖，故不加入。
- 同步更新文档里的违规变量数目与清单（README / CLAUDE / ARCHITECTURE / DEPLOYMENT / `.env.example` 中凡提到「十项」处）。

### R1-6 预设厂商与 Claude 的看门狗打断不了阻塞读（C1）

到时只对 custom 做 socket `shutdown`，预设 OpenAI 兼容与 Claude 只调 `close()`，消费线程会一直阻塞到 60 秒读超时。实际总时限因此变成 `TOTAL_SECONDS + 60`，在规格允许的 240 秒配置下等于 Nginx 的 300 秒。

1. 到时（以及取消/客户端断开时）对预设与 Claude 也先中断底层 socket：从 SDK 流对象持有的 `httpx.Response`（Claude 为 `httpx2.Response`）的 `extensions["network_stream"]` 取 `get_extra_info("socket")`，调用 `shutdown(socket.SHUT_RDWR)`，再 `close()`。
   - 只用公开 API，不访问私有属性。
   - 取不到 socket 时退回现有 `close()`，不得抛错。
2. custom 在取消（非超时）路径也执行 `abort()`。
3. `services/chat_service.py` 中 BYOK 调用被取消时，**先**触发上述中断，再等待 worker 线程返回，使槽位与上游连接及时释放。
4. 新测试：本地 `127.0.0.1` 起一个真实挂起的 HTTP 服务器（发一个片段后不再发送）。测试内可 monkeypatch 预设的 `base_url` 指向它。看门狗设 2–3 秒，对 deepseek（openai SDK）与 claude-haiku-5-5（anthropic SDK）断言：
   - 在看门狗时长 + 2 秒内返回超时错误；
   - 已发片段的处理符合 6.4.5。

## 2. 一并修复的低成本改进

### R1-7 会话中途被删时的错误归因（B1）

把 `_stream_byok_reply` 中的 `_save_text_reply` 与 `done` 事件移出 BYOK 的 `try/except`。只有建流和逐块读取期间的异常才映射为「你的模型调用失败…」。落库异常交给 `run_chat` 既有的 except 处理，文案与平台一致，日志不出现 `[byok] reply failed`。补一条测试。

### R1-8 错误分类更贴切（C4）

- 连接类：httpx / httpx2 的 `NetworkError`、`ReadError`、`WriteError`、`RemoteProtocolError`（含流迭代阶段直接抛出的）归「连不上该服务」。
- 额度类：openai `APIError` 的 `code` 为 `insufficient_quota`、`rate_limit_exceeded`、`billing_not_active` 时，归「额度不足或请求过于频繁」。
- 繁忙类：Anthropic 529 / `OverloadedError` 与流中 `overloaded_error`，新增固定类别「服务繁忙，请稍后再试」，完整文案为「你的模型调用失败：服务繁忙，请稍后再试。本条没有改用平台模型。」。
- 仍不得把上游 message 或正文带入文案。补对应测试。

### R1-9 前端（F0–F3）

- **F0**：`ChatModelSection` 监听 `storage` 事件里的 `CHAT_MODEL_REV_KEY`，并在 `visibilitychange` 变为可见时也刷新，按 `useAccountRequest` 作废旧请求后重新 `getChatModel`。
  - 刷新只更新服务端状态（config、enabled、available），不覆盖用户正在编辑的厂商、模型名、地址、Key 草稿。
  - 表单在 dirty 或 busy 时不重置草稿，但开关状态与说明文字要更新。
- **F1**：fetch 网络失败（TypeError 等非接口错误）一律显示「网络错误，请重试」，涉及设置分区各操作、初次加载与底栏切换。初次加载失败时给一个「重试」按钮。
- **F2**：任何 429 响应显示「操作太频繁，请稍后再试」。slowapi 的 429 响应体是 `{"error": "..."}`，没有 `detail`。
- **F3**：删除配置成功后，把表单重置为空态基线（第一家厂商、其默认模型、空地址），不再显示「有未保存的修改。」。
- 前端改动后 `npx tsc --noEmit` 退出码 0，`npx eslint .` 0 errors 且 warnings ≤ 25。

### R1-10 补测试锁定防线（S2、D0、D1）

- 断言 custom 构造的 `httpx.Client` 参数：`follow_redirects is False`、`trust_env is False`、`timeout == 60.0`，transport 为 `PinnedTransport`。
- 直接调用 `stream_generated_image` 的零余额守卫用例（复核 D0 的修法）。
- 路由层 `has_enabled_config` 读取出错时「按草莓不足原样返回」的用例，断言 `build_context` 未被调用、未写入用户消息（复核 D1 的修法）。
- 以上三条都要先做变异确认：把对应生产代码改坏后测试变红，并在报告里写明变异内容与失败输出。

### R1-11 文档（D2、D3 + 本单引起的变化）

- **D2**：`docs/DEPLOYMENT.md` 写明需要长期归档（超出日常 14 天保留）的数据库副本，在另存前必须对**副本**执行：

  ```bash
  sqlite3 <副本路径> "DELETE FROM user_model_configs; VACUUM;"
  ```

  这样归档副本里没有任何用户 Key 密文。README / CLAUDE / PLAN / ARCHITECTURE 中「数据库备份中最多保留 14 天」处补一句「长期归档副本须先清除 Key 密文」。
- **D3**：`FIONA_DAILY_BYOK_TESTS` 一行改为「本地校验失败不计次，上游连接测试计次」。
- 同步写清本单带来的变化：
  - 违规环境变量清单；
  - 自定义上游 4 MiB 响应上限；
  - 看门狗对所有厂商中断 socket，总时长即 `FIONA_BYOK_TOTAL_SECONDS`；
  - 新增「服务繁忙」错误类别。

  文档里不得写入本机绝对路径。

## 3. 不处理（无需改动）

S3（第三方库 INFO/DEBUG 日志）、B2、C3、D4，理由见 `04-review.md`。

## 4. 验收

- 第 7 节第 1–6 条全部重跑。白名单 = 7.1 + `05-fix-r0.md`，本单不新增文件类别。
- 全量 `python -m pytest -q` passed ≥ 2675 + 本轮新增数（沙箱内既有的 6 项端口权限失败可忽略）。
- 覆盖重写 `03-report.md`，要求：
  - 保留首轮内容中仍然成立的部分；
  - 新增「R1 返修」一节，逐条对应 R1-1 至 R1-11，写明改了什么、新测试名、修复前的失败摘要、修改了哪些既有 byok 断言及依据；
  - 写明 R1-5 的环境变量审计清单和 R1-4 选用的错误类别。
