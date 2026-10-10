# 每用户自带聊天模型（BYOK）（L3）

基线：`main` @ `a70e7d7`；后端 `python -m pytest -q` 为 **2428 passed**；前端 `npx eslint .` 为 **0 errors / 25 warnings**。本文引用代码位置以**函数名与原文片段**为准，行号仅供参考。

## 1. 产品目标与已拍板的决定

用户原话：「界面上面增加一个主力模型切换的功能，由使用者自行填写模型 API 接入」。用户想用 Claude 的 API 测试，「图片生成或者其他的 MCP 都不变」。

已由用户拍板：
1. **每个用户自己配**，只影响自己的对话；不配就用平台默认（`qwen3.8-omni-flash`）。
2. **用自带模型产生的聊天回复不扣草莓**；搜索、天气、旅行等工具，看图，生图照常扣。
3. **用户模型只接管聊天回复**（普通回复与镜子模式两条路径）；意图识别、模式判定、危机复核、看图（`qwen-vl-max`）、全部工具、生图、朗读（TTS）、画像提取、分身交流 / 官方创作搭档**全部仍用平台**。**明确危机（high）轮的支持回复也仍用平台模型**。
4. **接入方式**：预设厂商（通义、DeepSeek、Kimi、智谱、Claude）+ 自定义 OpenAI 兼容地址（只允许公网 HTTPS，服务端做 SSRF 防护）。
5. **新增依赖已获批**：`anthropic==1.12.1`（Claude 走 Anthropic 官方 Python SDK，不走 OpenAI 兼容垫片），并把已在环境中的 `cryptography==50.0.0` 正式写进 `requirements.txt`。两者已由 Claude 装进 `backend/.venv`（沙箱无网络，**不要尝试安装任何包**），新增的间接依赖为 `httpx2`、`httpcore2`、`docstring_parser`、`truststore`，`pip check` 通过。

规格作者（Claude）另作的设计决定（实现方照做，不要改）：
- **用户模型失败绝不静默改用平台模型**（任何失败都报错，本条不扣费）。用户自己关掉开关则正常用平台。
- **零余额用户也能用自带模型聊天**：采用「能扣就先扣，扣不到时降级为只能用自带模型聊天」方案（第 6.5 节）。
- 为控制平台辅助调用成本，自带模型聊天有**每日上限**（默认 200 次/人/天）。
- 发给第三方的系统提示里，**账号名替换为「（账号已隐藏）」**（手机号登录的账号名就是手机号）。
- Claude 的 Opus 5.5 / Sonnet 5.5 默认开启官方「拒答自动换模型」兜底（`fallbacks="default"`，只在 Anthropic 内部换型号）。

**用户场景**：
- 在设置页选「Claude」、选 `claude-opus-5-5`、填 Key、点「测试连接」通过 → 保存 → 回到聊天，输入区下方显示「聊天：Claude · claude-opus-5-5（不扣草莓）」和「改用平台」切换。之后普通聊天的回复由 Claude 生成，气泡上标注「由你的模型回复」；查天气照常由平台工具处理并扣草莓。
- Key 失效 → 这条消息报「你的模型调用失败：Key 无效。本条没有改用平台模型。」，不扣草莓。
- 余额 0 的用户启用自带模型后仍能聊天；让它查天气时提示「草莓不足」。

## 2. 已核实的外部事实（Claude 用 Anthropic 官方 Python SDK，均来自官方文档与本机实测）

### 2.1 Claude 型号白名单与请求写法

白名单（保存时拒绝其他型号）：`claude-opus-5-5`（默认）、`claude-sonnet-5-5`、`claude-haiku-5-5`。模型 ID 原样使用，**不得加日期后缀**。

- 这三个型号**不能传** `temperature`、`top_p`、`top_k`（anthropic 1.x 已从方法签名删除，传了直接 `TypeError`）；**不能传 `thinking`**（思考始终开启，Opus 5.5 传 `disabled` 会 400）；用 `output_config={"effort": "low"}` 控制思考深度（聊天场景用 `low`，降低首字延迟）。
- **`max_tokens` 同时限制思考与正文**，必须给足（见 6.4）。
- 不允许 assistant 预填（最后一条不能是 assistant）；首条消息必须是 `user`；相邻同角色合并后再发；本规格**不使用**会话中途 system 消息（统一合并进顶层 `system=`，见 6.4.3）。
- 流式写法（官方）：
  ```python
  import anthropic
  client = anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com", max_retries=0, timeout=60.0)
  with client.messages.stream(model=..., max_tokens=..., system=..., messages=..., output_config={"effort": "low"}) as stream:
      for text in stream.text_stream:
          ...
      final = stream.get_final_message()   # final.stop_reason: "end_turn" / "max_tokens" / "refusal" ...
  ```
- **拒答兜底**（仅 `claude-opus-5-5`、`claude-sonnet-5-5`）：改用 beta 端点并加两个参数（本机已核实 SDK 1.12.1 的 `client.beta.messages.stream` 有 `fallbacks` 参数，类型为 `Iterable[BetaFallbackParam] | Literal["default"]`）：
  ```python
  client.beta.messages.stream(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")
  ```
  头必须是 `server-side-fallback-2026-07-01`（与 `"default"` 形式配套，不能写成别的日期）。`claude-haiku-5-5` **不加**这两个参数。流式时兜底在同一条流里继续，`text_stream` 拼接即可。
- **拒答处理**：最终 `stop_reason == "refusal"` 表示整条链都拒答，按 6.4.6 报错。读结果先看 `stop_reason`，不按位置读 `content`。
- 异常类（`anthropic` 顶层）：`AuthenticationError`(401)、`PermissionDeniedError`(403)、`NotFoundError`(404)、`RateLimitError`(429)、`BadRequestError`(400)、`APIStatusError`（其他状态，有 `status_code`）、`APITimeoutError`、`APIConnectionError`。按「最具体优先」的顺序捕获。
- anthropic 1.x 底层是 `httpx2`（不是 `httpx`）。**禁止调用 `httpx2.alias_httpx()`**，**不得**把 `httpx` 的对象传给 anthropic 客户端；本规格不给 anthropic 客户端注入自定义 transport（Claude 地址固定，不需要 SSRF 防护）。
- 地域：Anthropic API **不对中国大陆提供服务**；服务器在大陆时 Claude 预设基本连不上（文档与设置页要写明，代码不需要特殊处理）。

### 2.2 其他预设厂商（OpenAI 兼容，用现有 `openai==2.37.0`）

| id | 显示名 | base_url | 关思考 extra_body | 推荐模型（前端可点填，可手填） |
|---|---|---|---|---|
| `dashscope` | 通义千问（阿里云百炼） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `{"enable_thinking": False}` | `qwen3.8-omni-flash`、`qwen3.8-max`、`qwen3.8-flash` |
| `deepseek` | DeepSeek | `https://api.deepseek.com` | `{"thinking": {"type": "disabled"}}` | `deepseek-v4-pro` |
| `moonshot` | Kimi（月之暗面） | `https://api.moonshot.cn/v1` | 无 | 无（手填） |
| `zhipu` | 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | 无 | 无（手填） |
| `anthropic` | Claude（Anthropic） | `https://api.anthropic.com` | —（见 2.1） | 白名单三项，默认 `claude-opus-5-5` |
| `custom` | 自定义 OpenAI 兼容地址 | 用户填写（6.3） | 无 | 无（手填） |

前两行的地址与参数在仓库里已有出处（`llm.make_dashscope_client`、`exchange_models` 的 DeepSeek 客户端）；Kimi、智谱只用地址、不传任何厂商专用参数。

## 3. 技术约束

- **不改 `backend/llm.py`**；`_create_stream_with_fallback` 的签名与行为不变，平台路径对它的调用必须继续通过 `services.chat_service` 模块全局名运行时查找（约 15 个测试打桩它）。**BYOK 回复绝不调用 `_create_stream_with_fallback`。**
- 不改 `exchange_service.py`、`exchange_models.py`、`intent_router.py`、`mode_switcher.py`、`crisis_model.py`、`safety.py`、`persona.py`、`tools/` 下任何文件。
- 新代码放在新包 `backend/byok/`，只由 `services/chat_service.py`、`routers/chat.py`、新路由与 `database.py`（建表、删号）引用。
- 日志与 trace **只记异常类型名、厂商 id（预设 id 或 `custom`）、错误类别、耗时**；不得出现 Key、`str(e)`、用户填的模型名或 URL、用户消息。trace 里 `model` 记 `"byok"`，另加 `byok_provider`。
- **所有新接口与聊天流都不得返回 HTTP 401**（前端 `apiFetch` 遇 401 会把用户踢回登录页）；厂商 401 映射成 400 或流内错误。
- Pydantic 请求模型只做最宽松的类型检查（字段用 `str | None` / `bool | None`），长度、格式、白名单校验放在处理函数里，失败抛 `HTTPException(400, 固定中文文案)`——**避免 FastAPI 默认 422 把 Key 原样回显**。
- 读取用户配置出错、解密失败、服务端密钥缺失时，**不得当作「未配置」走平台**，一律报错。
- 构造 BYOK 客户端前若发现以下任一环境变量非空，视为「BYOK 不可用」（聊天报错、设置接口 `available:false`），不得构造客户端：`OPENAI_ORG_ID`、`OPENAI_PROJECT_ID`、`OPENAI_CUSTOM_HEADERS`、`OPENAI_BASE_URL`、`ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_PROFILE`、`ANTHROPIC_FEDERATION_RULE_ID`、`ANTHROPIC_IDENTITY_TOKEN`、`ANTHROPIC_IDENTITY_TOKEN_FILE`。客户端一律显式传 `api_key`、`base_url`、`timeout`、`max_retries=0`。
- 客户端**按请求新建、用完关闭**，不缓存（不得用 `lru_cache`），明文 Key 不在内存里长期保留。
- 危机约定（`CLAUDE.md`「当前重要边界」私聊危机段）全部保持：基础安全规则在发出的系统提示里恰好一次且在末尾；possible 轮回复后由平台追加一次求助资源；所有错误路径资源恰好一次且在错误之前；high 轮仍由平台回复；余额不足时 high 免费送资源且不落库。
- 前端：改前端前先读 `frontend/AGENTS.md`；颜色只用现有 token；**Key 与任何厂商配置都不得写进 localStorage**（最多写一个不含机密的版本号用于跨 iframe 同步）；不得在 effect 里同步 setState（项目 lint 规则）；TS strict，不用 `any`。
- 请用多个 subagent 并行，按文件不重叠分工（建议：①`backend/byok/` 存储+加密+地址校验+客户端适配及其测试；②`routers/chat.py`、`services/chat_service.py`、`rate_limit.py`、`database.py`、`main.py`、新路由及其测试；③前端；④文档与 `requirements.txt`、`.env.example`）。同一文件只交给一个 subagent。②依赖①的接口，先由①给出函数签名再并行。

## 4. 配置项（全部调用时读取，不合法回退默认值，只告警一次，不打印值）

| 变量 | 默认 | 说明 |
|---|---|---|
| `FIONA_BYOK_SECRET` | 无 | url-safe base64 编码的 32 字节，用于 AES-256-GCM 加密用户 Key。缺失或非法 → BYOK 整体不可用（设置接口 `available:false`、保存返回 503、已启用的聊天报错），**不在导入时 raise**，DEV_MODE 也**不提供固定回退值**。 |
| `FIONA_BYOK_SECRET_PREVIOUS` | 空 | 逗号分隔的旧密钥，只用于解密（轮换期间）；用户下次保存时用当前密钥重新加密。 |
| `FIONA_DAILY_BYOK_CHATS` | `200` | 每人每天自带模型聊天次数，加进 `rate_limit._DAILY_SETTINGS`，kind `byok_chat`。 |
| `FIONA_DAILY_BYOK_TESTS` | `20` | 每人每天「测试连接」次数，kind `byok_test`。 |
| `FIONA_BYOK_MAX_STREAMS` | `8` | 全进程同时进行的自带模型流上限（1–64）。 |
| `FIONA_BYOK_TOTAL_SECONDS` | `120` | 单条自带模型回复总时长上限（10–240，须小于 Nginx 300 秒）。 |

`backend/.env.example` 追加以上变量与注释，并给出生成命令：`python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`。

## 5. 隐私数据流（文档与设置页必须按此逐条写明）

启用后，每条聊天回复会把以下内容发给用户选择的厂商：分身设定、用户的私有长期记忆、本会话最近 60 条消息（含平台看图生成的图片描述）、本条消息；账号名替换为「（账号已隐藏）」。仍由平台处理并读取对话内容的：危机复核、意图识别、模式判定、看图、工具、生图、朗读、画像提取（会读到用户模型的回复）。明确危机轮由平台回复。用户模型失败时不改用平台模型。Key 加密保存，删除 Key 或删号时删除，数据库备份中最多保留 14 天（无服务端密钥无法解密）。

## 6. 任务清单

### 6.1 依赖

`backend/requirements.txt` 追加 `anthropic==1.12.1` 与 `cryptography==50.0.0`（与现有写法一致）。不要运行任何安装命令。

### 6.2 存储与加密（`backend/byok/store.py`、`backend/byok/crypto.py`）

1. **表**（模块常量 DDL，在 `database.init_db()` 中、`retired_usernames` 附近直接 `await db.execute(...)`；不加迁移版本号；`/health` 与「五道迁移」不改；存取函数内不得执行 DDL）：
   ```sql
   CREATE TABLE IF NOT EXISTS user_model_configs (
       username        TEXT PRIMARY KEY,
       provider        TEXT NOT NULL,
       base_url        TEXT DEFAULT NULL,   -- 仅 custom 非空；预设地址留在代码常量
       model           TEXT NOT NULL,
       key_ciphertext  BLOB NOT NULL,       -- 版本字节 0x01 || nonce(12) || 密文 || tag(16)
       key_id          TEXT NOT NULL,       -- HMAC-SHA256(密钥, b"fiona:byok:key-id:v1") 前 16 位十六进制
       key_last4       TEXT NOT NULL,
       enabled         INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
       created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   )
   ```
2. **加密**：`cryptography` 的 AES-256-GCM，每次随机 12 字节 nonce；AAD = `"fiona:byok:v1|" + username + "|" + provider + "|" + (base_url or "")`（UTF-8）。改厂商或改地址必须重新填 Key（AAD 不同，旧密文无法沿用）；改模型名不影响。解密按 `key_id` 选当前或 PREVIOUS 密钥；失败抛专用异常。
3. **写入**：`BEGIN IMMEDIATE` → 用户存在性检查（照 `database.py` 里 `_users_exist` 的现有写法）→ upsert；用户不存在则不写（防删号后迟到请求复活）。
4. **读取**：对外函数只返回白名单字段（`provider`、`base_url`、`model`、`key_last4`、`enabled`、`status`（`ok` / `needs_reentry`）、`updated_at`）；内部取明文 Key 的函数只给聊天回复与测试连接用，不缓存。解密失败时对外 `status="needs_reentry"`。
5. **删号**：`database.delete_account_data` 在同一事务、`DELETE FROM users` 之前加 `DELETE FROM user_model_configs WHERE username = ?`。

### 6.3 自定义地址校验与 DNS 固定（`backend/byok/url_safety.py`）

1. **纯函数 `normalize_custom_base_url(raw) -> str`**（保存时与每次调用前都跑）：只接受 `https`；端口不写或 `443`；拒绝 userinfo、任何 IP 字面量（含 `127.1`、十进制/十六进制整数写法、`[v6]`）；主机名 IDNA 转小写去尾点，必须含点，字符集 `[a-z0-9.-]`，每段不以 `-` 开头结尾，最后一段不是纯数字或 `0x` 开头，长度 ≤253、每段 ≤63；拒绝后缀 `.localhost .local .internal .lan .home.arpa .test .invalid .example .onion .alt .arpa .corp .home .intranet`；路径为空或以 `/` 开头，字符集 `[A-Za-z0-9._~/-]`，不含 `..`、`//`、`%`，≤256，去掉末尾 `/`；禁止 query 与 fragment；整条 ≤512；拒绝空白、控制字符、`\x7f`、反斜杠、非 ASCII（主机名 IDNA 之外）。返回从组件重建的 `https://{host}{path}`。失败抛 `UnsafeUrlError`，对外统一文案「须为可公网访问的 HTTPS 地址」，不回显 IP。
2. **保存时 DNS 校验**：复用 `utils/safe_http` 的 `_resolve_public_ips` 思路（带独立解析线程池与超时），全部应答都是公网才允许保存；另外额外拒绝 `is_multicast` 与 NAT64 `64:ff9b::/96`（取低 32 位还原 IPv4 再判 `is_global`）。**不修改 `utils/safe_http.py`**（可以导入其中函数）。
3. **调用时 DNS 固定**：给 openai 客户端传 `http_client=httpx.Client(transport=PinnedTransport(...), follow_redirects=False, trust_env=False, timeout=...)`。`PinnedTransport` 为自写的 `httpx.BaseTransport`（只用公开 API，**不得访问 `_pool` 等私有属性**），内部持有 `httpcore.ConnectionPool(network_backend=PinnedPublicBackend(), http1=True, http2=False, retries=0)`；`PinnedPublicBackend(httpcore.NetworkBackend)` 在每次 `connect_tcp` 时重新解析并校验主机名，只连接通过校验的第一个公网 IP（TLS 的 SNI 与证书校验仍用原主机名，由 httpcore 完成）；`connect_unix_socket` 一律拒绝。httpcore 异常映射成对应 httpx 异常（超时类 → `httpx.TimeoutException` 子类），使 openai 能区分 `APITimeoutError` 与 `APIConnectionError`。transport 记录本次连接的 socket，供 6.4.5 的总时限看门狗强制断开。
4. 本机若有代理假 IP（198.18.0.0/15），自定义地址会被拒，这是预期行为，**不得加任何放行开关**。预设厂商不走这套 transport。

### 6.4 客户端与流适配（`backend/byok/client.py`、`backend/byok/providers.py`）

1. **`providers.py`**：第 2 节的表做成代码常量（id、显示名、kind `openai`/`anthropic`、base_url、extra_body、推荐模型、Claude 白名单与默认）；提供公开元数据函数供设置接口下发。模型名校验：1–100 字符，`[A-Za-z0-9._:/@-]`；Claude 必须在白名单。
2. **入口** `open_reply_stream(config: 内部配置含明文 Key, messages: list[dict], *, mirror: bool, username: str) -> ReplyStream`：同步函数（在专用线程池里调用，见 6.5.3），返回一个可迭代对象，**每个元素与现有平台 chunk 形状兼容**：有 `choices` 列表，`choices[0].delta.content` 为文字片段，`choices[0].finish_reason` 在截断时为 `"length"`；非文字事件不产出；必须有 `close()`，关闭底层流**和**本次新建的客户端。另提供 `stop_reason` / `refused` 等结束信息供 6.4.6 使用。这样 `chat_service._iter_sync_stream` 与现有消费循环可直接复用。
3. **消息转换**（输入是平台路径同样拼好的 `[system…] + ctx.messages`）：
   - `dashscope` 预设：结构保持与平台完全相同（包括末尾的朗读 system 消息，原写法就是为 qwen 设计的）。
   - 其余全部（`anthropic`、`deepseek`、`moonshot`、`zhipu`、`custom`）：把所有 `system` 消息的内容按原顺序用 `"\n\n"` 合并成**一条**（合并后 `BASE_SAFETY_RULES` 恰好一次且仍在末尾——现有拼法保证首条 system 已去掉安全规则、末尾朗读 system 以安全规则结尾）；非 system 消息：丢掉内容为空的、丢掉开头连续的 `assistant`、相邻同角色用 `"\n\n"` 合并；最后一条必为 `user`。OpenAI 兼容：`[{"role":"system","content": 合并后}] + 规整后的消息`；Claude：`system=合并后`，`messages=规整后的消息`。
   - **所有厂商（含 dashscope）**：系统提示中出现的账号名（`username`，长度 ≥3 时）全部替换为「（账号已隐藏）」。
   - 平台路径的消息与参数**完全不动**。
4. **参数**：
   - OpenAI 兼容：只传 `model`、`messages`、`stream=True`、`max_tokens`（普通 2048、镜子 512）、预设的 `extra_body`（若有）；**不传** `temperature`、`top_p`、`frequency_penalty`、`presence_penalty`。客户端 `timeout=60`（单次读取）、`max_retries=0`。
   - Claude：按 2.1 写法；`max_tokens`（普通 4096、镜子 2048），`output_config={"effort": "low"}`，Opus 5.5 / Sonnet 5.5 带拒答兜底；不传 `thinking` 与任何采样参数。
5. **资源上限**：
   - 总时长 `FIONA_BYOK_TOTAL_SECONDS`：从建流开始计时，超时即关闭流（自定义地址通过 6.3 记录的 socket 执行 `shutdown(SHUT_RDWR)` 再关闭，参照 `utils/safe_http._abort_pool_socket`；其他厂商调用 `close()`），按「超时」报错。
   - 正文字符上限：普通 4000 字、镜子 600 字；超出即停止读取并关闭流，已产生的文字保留，`finish_reason` 记为 `"length"`。
6. **结束语义**（在 chat_service 消费完流之后判断）：
   - 正文为空（包括 Claude `stop_reason` 为 `refusal` 或 `max_tokens` 且无正文）→ 报错（6.5.6），不扣费，不落库 assistant。
   - Claude 最终 `stop_reason == "refusal"` 且已有部分正文 → 保留已显示的文字，追加一句「（Claude 中止了这条回复）」后按正常回复落库。
7. **错误映射**（固定中文，结尾统一加「本条没有改用平台模型。」）：401/403 → 「Key 无效或没有权限」；404 → 「模型名或地址不存在」；402、429、额度/限流 → 「额度不足或请求过于频繁」；400 → 「请求参数不被接受」；超时 → 「响应超时」；连接失败、地址被拦截 → 「连不上该服务」；拒答 → 「模型拒绝回答这条消息」；空回复 → 「模型没有返回内容」；解密失败/需重填 → 「配置需要重新填写 Key」；BYOK 不可用（服务端密钥缺失、违规环境变量）→ 「服务器暂未开启自带模型」；其他 → 「调用失败」。完整形如「你的模型调用失败：Key 无效或没有权限。本条没有改用平台模型。」

### 6.5 聊天接入（`routers/chat.py`、`services/chat_service.py`、`rate_limit.py`）

1. **分流条件**：只有同时满足以下三条才走用户模型——用户配置存在且 `enabled=1`；`not state.crisis`（只有 high 轮为真）；当前分支是 `stream_mirror` 或 `stream_normal`。看图、工具、生图、意图、模式、画像提取、TTS 全部原样。
2. **接入点**：在 `stream_mirror` 与 `stream_normal` 里，把建流那一处改为「BYOK 条件满足 → 调 BYOK 入口；否则原样 `await asyncio.to_thread(_create_stream_with_fallback, ...)`」。BYOK 分支：给后续代码用到的 `_actually_qwen` 赋一个确定值；跳过 `token_budget.add`；**不设 `state.billable = True`**（让收尾退还预扣）；`state.trace["model"]="byok"`、`state.trace["byok_provider"]=<id>`。BYOK 失败沿用现有「先送资源再报错」写法，文案用 6.4.7；**不调用** `_upstream_error_message`。
3. **并发与线程**：BYOK 的建流与逐块读取使用**专用有界线程池**（`FIONA_BYOK_MAX_STREAMS`，线程名前缀 `fiona-byok`），不占默认的 `fiona-chat` 池；满了直接报「自带模型通道繁忙，请稍后再试」。每个用户同时最多 1 条 BYOK 流（照 `_IMAGE_GENERATION_USERS` 的写法），第二条报「你的模型正在回复上一条消息，请稍候」。
4. **每日上限**：开 BYOK 流之前（并发检查之后）调用 `rate_limit.check_chat_daily_cap("byok_chat", user, hit=True)`；超限按「先资源再 error」返回「今天用自带模型聊天的次数已用完，明天再试，或在输入框下方改用平台」。`rate_limit` 的文案字典补 `byok_chat`、`byok_test`。
5. **配置读取**：
   - `build_context` 新增关键字参数（带默认值），在函数内读取用户配置（含解密需要的内部信息）存进 `ChatContext` 新字段；**新字段一律加在 `ChatContext` 末尾并带默认值**（测试按位置构造它）。
   - 读取或解密出错：若用户配置为启用状态，则本轮在 BYOK 分支报 6.4.7 的对应错误，**不得走平台**。
6. **零余额降级（方案 C′）**：
   - `routers/chat.py` 余额不足分支中，在 `crisis == "high"` 早返回**之后**：若 `req.mode == "chat"` 且该用户有启用的自带模型配置（在此分支内读一次配置；读取出错按「草莓不足」原样返回），则**不返回**，以「未预扣」继续：通过关键字参数把「未预扣」标记传给 `build_context` / `run_chat`（路由层不得访问 ctx 的任何字段——有测试把 `build_context` 打桩成返回 `SimpleNamespace()`）；未预扣路径用普通 `StreamingResponse`（与 DEV_MODE 相同）。`image` / `image_edit` 模式不降级，保持原返回。
   - 「草莓不足」文案从路由内联处抽成共享函数（放在 `database.py` 的 `strawberry_daily_refill` 旁边），路由与守卫共用，文案与现有完全一致。
   - **守卫**（只在「未预扣」标记为真时生效；DEV_MODE 下该标记永远为假，守卫为空操作；标记不得用 `not reserved` 推断）：在以下位置之前，先按需补发危机资源，再 `yield {"error": 草莓不足文案}` 并返回：生图/修图入口（`stream_generated_image` 忙锁之前）；`stream_pending` 的 `clear_pending` 之前（不清 pending）；`stream_intent` 执行工具之前且**在天气每日上限检查之前**（不消耗天气额度）；`stream_image` 调看图模型之前。high 轮不会到达这里（路由已早返回）。
   - 「未预扣」时若到了回复阶段却没有可用的自带模型（配置被删、被关、需重填），报「草莓不足」，**不得**用平台模型。
7. **空回复**：BYOK 路径正文为空时，发错误事件（possible 轮先送资源），不再只发 `done`。平台路径不变。
8. **回复模型标注**：BYOK 路径在第一个 `text` 事件之前发一条 `{"reply_model": {"source": "byok", "label": "<显示名> · <模型名>"}}`。平台路径**不发**（现有测试断言精确事件序列）。
9. **不得修改的行为**：非 BYOK 用户的全部计费、危机、错误、事件序列与现在逐字节一致。

### 6.6 设置接口（新文件 `backend/routers/chat_model.py`，在 `main.py` 注册）

全部需要登录（默认中间件），不加入公开路径；响应头 `Cache-Control: private, no-store`；保存/修改/删除/测试加 `@limiter.limit("10/minute")`（需要 `request: Request` 参数，照 `routers/agent_exchanges.py` 写法）。

1. `GET /chat-model` → `{"available": bool, "providers": [...公开元数据...], "config": null | {provider, model, base_url, key_last4, enabled, status, updated_at}}`。`available` 为假的原因（密钥缺失/违规环境变量）只给固定文案字段 `unavailable_reason`。
2. `PUT /chat-model`，body `{provider, model, base_url?, api_key?}`：校验厂商 id、模型名（Claude 白名单）、`custom` 时地址（6.3 纯函数 + 保存时 DNS 校验），`api_key` 长度 8–512、不含空白与控制字符。首次保存或改了厂商/地址时 `api_key` 必填；否则可省略（保留原 Key，只改模型）。保存后返回 `config`。BYOK 不可用 → 503。首次保存 `enabled=1`，再次保存保持原值。
3. `PATCH /chat-model`，body `{enabled: bool}`：无配置 → 404；`status=needs_reentry` 时不允许开启（400）。
4. `DELETE /chat-model` → 204，删除整行。
5. `POST /chat-model/test`，body 同 PUT（全部可选）：带 `api_key` 时测表单草稿；不带时用已保存的 Key（若厂商/地址与已保存不同则 400「更换厂商或地址需要重新填写 Key」）。调用前先过每日上限 `byok_test`。发一次最小请求：OpenAI 兼容 `max_tokens=16`、内容「只回复：好」；Claude `max_tokens=1024`、`output_config={"effort":"low"}`、同样内容。**总是返回 200** `{"ok": bool, "message": 固定中文}`（失败文案用 6.4.7 的类别），不保存任何东西，不回显 Key。

### 6.7 前端

1. 新组件 `frontend/components/ChatModelSection.tsx` + `frontend/lib/chatModel.ts`（类型与请求函数，严格收窄服务端 JSON）。在 `app/settings/page.tsx` 「外观」与「数据管理」之间加一个分区「聊天模型」，外层 `key={username}` 以便换账号重挂载；复用该页现有的 `sectionClass`、`headingClass`、chip 单选组、输入框、开关、`btn` / `btn-primary` / `btn-danger`、`role="alert"` / `role="status"` 写法。内容：
   - 厂商 chip 单选（由 `GET /chat-model` 下发，不在前端写死）；
   - 模型名输入框 + 该厂商推荐模型 chip（点一下填入；Claude 只能从白名单选）；
   - 仅「自定义」时显示地址输入框（`type="url"`、`inputMode="url"`、placeholder `https://…/v1`）；
   - API Key 输入框（`type="password"`、`autoComplete="off"`、`spellCheck={false}`、`autoCapitalize="none"`），永不回填；已有 Key 时显示「已保存：••••{末 4 位}」与「更换 Key」「删除」（删除先 `confirm`）；保存成功、切换厂商、卸载时清空输入；
   - 启用开关（未配好时禁用并说明原因；`status=needs_reentry` 时提示重新填写）；
   - 「测试连接」「保存」按钮，忙碌态、错误态、成功态；有未保存修改时提示；
   - 固定的隐私与计费说明（第 5 节内容精简为 3–5 句，并说明「Claude 的接口不对中国大陆提供服务」）；`available:false` 时整个表单禁用并显示原因。
   - 保存或开关后写 `localStorage["fiona_chat_model_rev"] = String(Date.now())`（只此一个不含机密的值，try/catch）。
2. 删号确认文案（`settings/page.tsx` 中列出删除范围的那句）补上「自带模型配置与 Key」；页头副标题补「模型」。
3. `app/page.tsx` 聊天输入区底栏：拉取 `GET /chat-model`（登录后、设置抽屉关闭时、收到 `fiona_chat_model_rev` 的 `storage` 事件时重新拉取）。
   - 有配置且启用、处于聊天模式：显示「聊天：{显示名} · {模型}（不扣草莓）」+ 按钮「改用平台」（`PATCH enabled=false`）；
   - 有配置但关闭：显示「聊天：平台 · 每条 10 颗草莓」+「改用我的模型」（`status` 正常时才可点）；
   - 无配置：保持现有「每条消息消耗 10 颗草莓」文案；生图/参考图模式保持现有扣费文案。
   - 草莓余额的 `title` 文案（`page.tsx` 与 `components/Sidebar.tsx` 两处「每条消息消耗 10 颗」）改为「平台模型每条消息消耗 10 颗；自带模型聊天不扣」。
4. 收到 SSE `reply_model` 事件时，把 label 记在该条消息上；`components/ChatBubble.tsx` 的分身名标签后显示「· 由你的模型回复」（悬停显示 label）。不持久化（刷新后消失，属已知限制）。
5. 聊天流错误沿用现有「错误：…」气泡显示，无需新分支。

### 6.8 文档

按 `CLAUDE.md` 工作约定同步。**请全库搜索**下列事实的所有陈述点逐处更新：自带模型功能与接管范围；第 5 节隐私数据流（参照生图「发送给哪家」的写法）；计费规则变化（「每次实际交付结算 10 颗」仅指平台模型回复；零余额降级）；新环境变量与生成命令；每日上限从五项变七项（`byok_chat`、`byok_test`）；新表 `user_model_configs`（表清单、删号验证清单）；「朗读强约束作为当前 user 后的独立 system 消息」只适用于平台模型与 dashscope 预设；Claude 不对中国大陆服务；密钥单独保管、不进备份、丢失只需用户重填。`docs/DEPLOYMENT.md` 环境变量表与部署后抽查清单补充对应条目。文档里不得写入本机绝对路径。

### 6.9 测试

**不得修改的现有测试**（逐字不动，验收逐文件 diff 为空）：`backend/tests/` 下全部现有文件。新行为一律写在新文件里。

**新增测试**（可拆为 `test_byok_store.py`、`test_byok_url_safety.py`、`test_byok_client.py`、`test_byok_chat.py`、`test_byok_api.py` 等），每个文件带 autouse 断网夹具（照 `tests/test_search_real_sources.py::forbid_network`，额外把 `socket.getaddrinfo` 与 `httpcore` 的同步网络后端连接替换为抛 `AssertionError`，teardown 断言从未触发），用 `monkeypatch.setenv("FIONA_BYOK_SECRET", ...)`，涉及限流的调用 `limiter.reset()`。至少覆盖：

存储与加密：
1. 加解密往返；AAD 绑定（换用户名/厂商/地址解密失败）；`key_id` 选钥；PREVIOUS 密钥可解；密钥缺失/非法时不可用且不在导入时报错。
2. 删号清除配置；同名重建拿不到旧配置；删号后迟到的保存不复活。
3. 对外读取不含密文与完整 Key。

地址与传输：
4. 非法地址参数化（`http://`、`:8443`、`:0`、各种 IP 字面量写法、单段主机名、黑名单后缀、userinfo、反斜杠、换行、`?q`、`#f`、`/../`、`//`、`%2e`、超长）；合法地址规范化（大写、尾点、Unicode 主机名）。
5. DNS 应答含 `198.18.0.5`、`127.0.0.1`、`64:ff9b::a9fe:a9fe`、`224.0.0.1` 时拒绝。
6. 用 `httpcore.MockBackend` 子类记录 `connect_tcp` 的目标与 `start_tls` 的 `server_hostname`，通过真实 `OpenAI(http_client=...)` 流式调用：连接目标是校验过的 IP、SNI 是原主机名；第二次解析变成内网 IP 时拒绝（重绑定）；`302` 不跟随；设置 `HTTPS_PROXY` 不影响连接目标；超时映射为 `openai.APITimeoutError`。

客户端与消息：
7. 消息转换：对每种厂商断言**真正发给客户端的请求体**——安全规则恰好一次且在最后一条 system 末尾（Claude 为 `system` 参数）；Claude/非 dashscope 只有一条 system；首条为 user、无相邻同角色、末条为 user；dashscope 保留末尾朗读 system；账号名被替换；不含 `temperature` 等采样参数；Claude 带 `output_config` 且 Opus 5.5 / Sonnet 5.5 带 `betas=["server-side-fallback-2026-07-01"]` 与 `fallbacks="default"`、Haiku 5.5 不带；`max_tokens` 取值正确。（Claude 测试替换 `anthropic.Anthropic` 或 `client.messages.stream` 为假对象，不联网。）
8. 流适配：文字片段转成兼容 chunk；`max_tokens` → `"length"`；refusal 有/无部分正文的两种处理；字符上限截断；总时长超时关闭；`close()` 同时关闭流与客户端。
9. 违规环境变量（如 `ANTHROPIC_BASE_URL`）存在时 BYOK 不可用。

聊天集成：
10. 启用 BYOK 的用户普通回复与镜子回复都走用户客户端，`_create_stream_with_fallback` 调用次数为 0；余额 10 时结束后余额仍为 10；三个并发请求（同一用户）第二、三个收到「正在回复上一条」。
11. 零余额 / 余额 5 的 BYOK 用户：聊天成功、余额不变；让它走工具、生图（`mode=chat` 的自然语言生图）、看图时：工具/生图/看图桩未被调用、天气额度未计数、pending 原样保留、收到与路由完全一致的「草莓不足」文案；`mode=image` 时保持原返回。
12. 有余额的 BYOK 用户走工具、生图、看图：照常扣 10。
13. high 轮：走平台、用户客户端调用 0 次；有余额扣 10；零余额时事件恰好为 `[{"crisis": true}, {"text": 资源}, {"done": true}]` 且不落库。
14. possible 轮：走用户模型，回复后资源恰好一次；用户模型失败时资源在错误之前、恰好一次。
15. 用户模型失败（401、404、429、超时、连接失败、需重填、BYOK 不可用）：错误文案正确、不调用平台模型、有余额时退款、日志与响应里无 Key/URL/模型名。
16. 空回复报错；`reply_model` 事件只在 BYOK 路径出现；非 BYOK 用户的事件序列不变。
17. 每日上限 `byok_chat` 超限报错且不扣草莓；DEV_MODE 下放行且守卫为空操作。
18. 分身交流（`agent_exchanges`）在用户启用 BYOK 后仍不调用用户客户端。

接口：
19. GET 不含密文/完整 Key 且带 `no-store`；PUT 各类非法输入返回 400 固定文案且**响应体不含提交的 Key**（含故意构造的超长/非字符串 Key）；改厂商/地址未带 Key → 400；PATCH/DELETE；`needs_reentry` 不可开启；任何情况都不返回 401；测试连接总返回 200，失败分类正确，受 `byok_test` 每日上限约束，不保存任何数据。

## 7. 验收标准

在仓库根目录执行：

1. `git status --porcelain` 只出现：新增 `backend/byok/`、`backend/routers/chat_model.py`、新增的 `backend/tests/test_byok_*.py`、`frontend/components/ChatModelSection.tsx`、`frontend/lib/chatModel.ts`、本任务目录；修改 `backend/requirements.txt`、`backend/.env.example`、`backend/database.py`、`backend/main.py`、`backend/rate_limit.py`、`backend/routers/chat.py`、`backend/services/chat_service.py`、`frontend/app/settings/page.tsx`、`frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/components/Sidebar.tsx`，以及第 6.8 节涉及的文档（`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md` 中的任意几个）。
2. `git diff --exit-code -- backend/llm.py backend/exchange_service.py backend/services/exchange_service.py backend/exchange_models.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/persona.py backend/tools backend/utils/safe_http.py backend/tests` 退出码 0（该命令里不存在的路径可忽略报错，以实际存在的文件为准）。
3. `grep -rn "alias_httpx\|lru_cache" backend/byok` 无输出；`grep -rn "str(e)\|str(exc)\|str(error)" backend/byok backend/routers/chat_model.py` 无输出。
4. `grep -n "^anthropic==1.12.1$" backend/requirements.txt` 与 `grep -n "^cryptography==50.0.0$" backend/requirements.txt` 各 1 行。
5. 在 `backend/` 下：`python -m pip check` 通过；`python -m pytest -q` 全部通过（沙箱内因端口权限失败的既有 6 项可忽略，由 Claude 在沙箱外重跑），passed ≥ 2428 + 新增用例数。
6. 在 `frontend/` 下：`npx tsc --noEmit` 退出码 0；`npx eslint .` 0 errors 且 warnings ≤ 25。

不要运行 `npm run build` / `npm run dev`、不要启动后端、不要安装任何包、不要发起任何真实网络请求；构建、真实 Claude 调用与界面截图由 Claude 在沙箱外完成。

## 8. 什么时候停下来问

- 只有当某项要求**无法实现或互相矛盾**、会影响「做出什么」时才停下来，在总结里写明原因与证据，例如：某个现有测试必须改才能实现、`anthropic` SDK 的实际接口与第 2.1 节不符、`httpcore` 公开 API 无法实现 6.3.3。不回滚已完成的工作。
- 只影响「怎么写测试 / 怎么验证」的细节自行决定并说明。
