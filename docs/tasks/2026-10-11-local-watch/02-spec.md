# 规格：本机界面监控与提醒（macOS）

日期：2026-10-11。基线：`main` 的 `129b32a`。等级：L3。作者已批准方案，规格写完后直接实施。

## 0. 目标

用户在自己的 Mac 上运行一个监控小程序，盯住指定程序窗口，例如：
- 微信电脑版、企业微信、钉钉；
- 行情软件；
- 任意窗口。

监控程序在本机截图并做 OCR，把**新出现的文字**交给 Fiona 后端。后端按用户设定的规则判断，符合条件时，由分身在 Fiona 聊天里主动发一条提醒。

**原则**：
- 只被动读取屏幕，不操作任何程序。
- 截图和整页文字不离开本机，只上报新增的行。
- 新增文字只在内存中用于判断，不落日志、不写 trace。
- 落库的只有提醒摘要。

**不在范围**：
- Windows 版；
- 手机推送；
- 自动回复或操作微信；
- 改动现有聊天路由；
- 改动 `desktop/`（Windows Tauri 外壳）。

## 1. Mac 监控程序 `watcher-mac/`（新目录）

**基本要求**：
- Swift Package，可执行目标名为 `fiona-watcher`，最低系统 macOS 14。
- 不引入任何第三方依赖，只用 ScreenCaptureKit、Vision、CoreGraphics、Foundation。
- `swift build -c release` 必须通过。

### 1.1 子命令

- **`fiona-watcher list-windows`**
  - 用 `SCShareableContent.current` 列出屏幕上的窗口。
  - 输出 JSON 数组：`{"window_id", "app_name", "bundle_id", "title"}`。
  - 过滤掉标题为空且面积小于 200×200 的窗口。
- **`fiona-watcher ocr <png路径>`**
  - 对图片做 OCR，输出 JSON：`{"lines": ["..."]}`，按从上到下、从左到右的顺序。
  - 用于测试。
- **`fiona-watcher run --server <URL> --token-file <路径>`**
  - 常驻运行。`--server` 默认 `http://127.0.0.1:8010`；`--token-file` 默认 `~/.fiona/watcher.token`。
  - 令牌文件权限必须是 600，否则拒绝启动并给出提示。

### 1.2 run 的行为

- **心跳**：每 30 秒 `POST /local-watch/heartbeat`，上报 `list-windows` 的结果，并取回启用的规则。
- **窗口匹配**：对每条启用的规则，按 `app_match` 和 `title_match`（都可为空；子串匹配，不区分大小写）找到窗口，取第一个匹配项。
- **截图**：每 `interval_seconds`（2–60 秒，默认 3 秒）截一次。
  - 用 `SCScreenshotManager.captureImage`，配合 `SCContentFilter(desktopIndependentWindow:)` 截单个窗口。
  - 截图只放在内存里，不写入磁盘。
- **跳过未变化的帧**：把图片缩到 64×64 灰度，计算哈希；与上一帧相同就跳过 OCR。
- **OCR**：
  - `VNRecognizeTextRequest`，`recognitionLevel = .accurate`；
  - `recognitionLanguages = ["zh-Hans", "en-US"]`；
  - `usesLanguageCorrection = true`。
- **规范化**：
  - 每行去掉首尾空白，连续空白合并为一个。
  - 丢弃以下内容：长度小于 2 的行；纯数字、纯时间（如 `12:30`、`昨天`、`星期一`）、纯标点的行。
- **新增判定**：本次某行不在**最近 3 次快照**的行集合中，才算新增。
- **首次截图**：作为基线，不上报。
- **上报**：有新增行时，`POST /local-watch/observations`。
  - 请求体：`{"rule_id", "new_lines": [...], "captured_at": ISO8601}`。
  - 每次最多 50 行、4000 字，超出部分截断。
- **异常**：
  - 网络错误按指数退避重试，最长 60 秒，且不丢弃基线。
  - 返回 401 时停止运行，并提示令牌失效。
  - 首次没有「屏幕录制」权限时，打印清楚的中文指引后退出：打开 系统设置 → 隐私与安全性 → 屏幕录制，勾选运行它的终端或程序本身。
- **日志**：
  - 只打印规则 id、窗口应用名、新增行数、HTTP 状态。
  - **不打印**识别出的文字。

### 1.3 附带文件

- `watcher-mac/README.md`（中文），写清以下内容：
  - 编译方法；
  - 授权屏幕录制；
  - 写入令牌文件：`umask 077`，从 Fiona 设置页复制；
  - 运行与停止；
  - 已知局限。
- `watcher-mac/launchd/com.fiona.watcher.plist.example`：开机自启的示例。
- `watcher-mac/Tests/`：
  - 至少对「规范化」和「新增判定」两段纯逻辑写 XCTest（需要把逻辑抽成可测的模块）；
  - 对 OCR 写一条测试：在测试中用 CoreGraphics 绘制含中文「张三：今晚开会」和英文「Download complete」的图片，识别结果包含这两段文字。
  - `swift test` 必须通过。如果在沙箱里无法运行，报告中写明，由作者方在沙箱外执行。

## 2. 后端

### 2.1 数据库（`backend/database.py`，本单只允许新增，不改现有表）

参照 `user_model_configs` 的写法，在 `init_db` 中用 `CREATE TABLE IF NOT EXISTS` 新增以下 3 张表。用户现有的长期使用库启动时会自动建表，这一点要写测试验证：用一个已有其他表、但没有这 3 张表的旧库启动，表会被建出来，其他数据不变。

- `watch_devices`
  - `id` INTEGER PK
  - `username` TEXT NOT NULL
  - `token_hash` TEXT NOT NULL UNIQUE：sha256 十六进制
  - `name` TEXT
  - `created_at`
  - `last_seen_at`
  - `revoked` INTEGER DEFAULT 0
- `watch_rules`
  - `id` INTEGER PK
  - `username`
  - `name` TEXT：1–30 字
  - `app_match` TEXT、`title_match` TEXT：都 ≤ 60 字，不能同时为空
  - `kind` TEXT：取值 `keyword` / `number` / `ai`
  - `params` TEXT：JSON，见 2.3
  - `interval_seconds` INTEGER：默认 3
  - `cooldown_seconds` INTEGER：默认 60，范围 10–3600
  - `enabled` INTEGER：默认 1
  - `conversation_id` TEXT：可空，空时写入默认会话
  - `created_at`、`updated_at`
- `watch_alerts`
  - `id` INTEGER PK
  - `username`
  - `rule_id`
  - `created_at`
  - `summary` TEXT：≤ 200 字
  - `message_id` INTEGER
  - `conversation_id` TEXT

**上限**：每个用户最多 3 台有效设备、20 条规则。

**删号**：用户删号时，删除这 3 张表中属于该用户的全部数据。要在现有删号流程里补上，并写测试。

### 2.2 路由（新文件 `backend/routers/local_watch.py`，在 `main.py` 注册）

**用户侧**（用现有 Cookie 鉴权 `get_current_user`）：

- `POST /local-watch/devices`
  - 请求体 `{name}`。
  - 生成 32 字节随机令牌，**明文只在这次响应中返回一次**，库里只存哈希。
- `GET /local-watch/devices`：返回列表，不含令牌。
- `DELETE /local-watch/devices/{id}`：吊销设备。
- `GET /local-watch/rules`、`POST /local-watch/rules`、`PATCH /local-watch/rules/{id}`、`DELETE /local-watch/rules/{id}`：规则的增删改查，参数严格校验。
- `GET /local-watch/windows`：返回该用户最近一次心跳上报的窗口清单。
  - 存在进程内存里，按用户分开，保存 5 分钟。
  - 字段只包括 `app_name`、`bundle_id`、`title`，标题截到 80 字。
- `GET /local-watch/alerts?after=<id>`：返回该用户 id 大于 `after` 的提醒，最多 50 条。字段：`id`、`rule_name`、`summary`、`created_at`、`conversation_id`、`message_id`。

**设备侧**（`Authorization: Bearer <令牌>`，用哈希查找有效设备，同时更新 `last_seen_at`）：

- `POST /local-watch/heartbeat`
  - 请求体 `{windows: [...]}`，最多 200 个窗口。
  - 返回该用户启用的规则：`id`、`app_match`、`title_match`、`interval_seconds`。**不返回** `params`，判断条件留在服务端。
- `POST /local-watch/observations`
  - 请求体 `{rule_id, new_lines, captured_at}`。
  - 校验：规则属于该设备的用户且已启用；`new_lines` 不超过 50 行、4000 字。
  - 按设备限流，每分钟 60 次，超出返回 429。

**响应头**：设备侧和用户侧接口都设置 `Cache-Control: private, no-store`。

### 2.3 判定（新文件 `backend/services/local_watch.py`）

- **`keyword`**
  - params：`{"keywords": [1–10 个，每个 1–20 字]}`。
  - 任一新增行包含任一关键词（不区分大小写）即命中。
  - 摘要取第一条命中的行，截到 80 字，格式为「命中『关键词』：<该行>」。
- **`number`**
  - params：`{"label": 1–20 字, "op": ">"|">="|"<"|"<=", "threshold": 数字}`。
  - 在包含 `label` 的新增行中，取 label 之后的第一个数字（支持负号、小数点、千分位逗号、末尾 `%`）进行比较。
  - 命中时摘要为「<label> 当前 <数值>，已 <op> <阈值>」。
- **`ai`**
  - params：`{"condition": 2–200 字, "model": "platform"|"claude"}`，`model` 默认 `platform`。
  - **platform**：照搬 `services/image_tool.plan_image` 的做法：
    - 复用 `llm.QWEN_CLIENT`，模型 `qwen3.8-flash`；
    - JSON 模式，`max_tokens=300`；
    - 关闭思考（`extra_body` 与现有设置一致）；
    - SDK 超时 8 秒，`max_retries=0`；
    - 在线程中执行，外层总时限 8 秒；
    - 提示词见 2.6。
  - **claude**：仅当该用户已启用 Anthropic BYOK 时可选，复用 `byok` 的解密与客户端。
    - 非流式，`model` 取用户配置，`max_tokens=300`；
    - `output_config.format` 按 JSON schema 输出 `{alert: boolean, summary: string}`；
    - 不带工具；
    - 不可用时按「判断失败」处理，不回退到平台模型。
  - 输入：新增行按顺序拼接，截到 2000 字。
  - 输出：`alert` 必须是布尔值；`summary` 去空白后为 1–80 字。不合法、超时或异常都算判断失败。
  - 判断失败时不提醒，只在 trace 里记录异常类型。
- **冷却**：同一规则距离上次提醒不足 `cooldown_seconds` 时，直接丢弃，并且**不调用模型**。
- **每日上限**：AI 判断每个用户每天最多 `FIONA_DAILY_WATCH_JUDGE` 次（默认 500），在 `backend/rate_limit.py` 的 `_DAILY_SETTINGS` 中新增。超限时不调用模型、不提醒。
- **不扣草莓。**

### 2.4 提醒落库与送达

- 命中后：
  1. 用现有 `database.save_message(username, "assistant", content, conversation_id=...)` 写入目标会话。`conversation_id` 为空时由它写入默认会话。会话已被删除或无效时，改写默认会话。
  2. 消息正文：`【本机提醒 · <app_name 或规则名>】<summary>（规则：<规则名>）`。
  3. 插入一条 `watch_alerts` 记录。
- **不得**触发以下任何一项：画像提取、匹配检测、危机流程、计费。
- **trace / log**：只记录 `rule_id`、`kind`、`alert`（布尔）、判断耗时、异常类型。**不记录**新增文字和摘要。

### 2.5 开关

- 环境变量 `FIONA_LOCAL_WATCH`：默认 `1`，取 `0` 时所有 `/local-watch/*` 接口返回 404。
- `backend/tests/conftest.py` **不需要改动**。本单不改变任何现有路由。

### 2.6 AI 判断提示词（逐字使用，作为 system）

```
你是屏幕提醒判断器。下面是用户电脑上某个程序窗口里新出现的文字（由 OCR 识别，可能有错字）。根据用户设定的提醒条件判断现在是否需要提醒用户。只依据给出的文字判断，不要猜测看不到的内容。只输出 JSON：{"alert": true或false, "summary": "需要提醒时用一句话说明发生了什么（不超过 60 字），不需要时为空串"}
```

user 消息格式为：`提醒条件：<condition>\n新出现的文字：\n<拼接后的文字>`。

## 3. 前端

### 3.1 设置页「本机监控」区块

在 `frontend/app/settings/page.tsx` 中新增组件 `frontend/components/LocalWatchSection.tsx`，样式沿用 `ChatModelSection.tsx`。区块内容：

1. **说明**：用途，以及只支持 macOS。
2. **设备**：
   - 「生成设备令牌」：令牌只显示一次，附带一键复制；同时给出写入命令示例：`mkdir -p ~/.fiona && umask 077 && pbpaste > ~/.fiona/watcher.token`。
   - 设备列表：显示名称、最后在线时间，可吊销。
3. **最近发现的窗口**：调用 `GET /local-watch/windows`。点某个窗口，就用它的应用名预填新建规则表单。
4. **规则**：
   - 列表：名称、类型、匹配条件，可启用/停用、编辑、删除。
   - 新建或编辑表单按类型切换，每种类型都给出示例：
     - 关键词：「@我」「老板的名字」；
     - 数值：标签「价格」 `>=` 100；
     - AI：「下载完成或出现报错时提醒我」。
   - 选「claude」需要已启用 Anthropic BYOK，否则禁用该选项并说明原因。
5. **隐私说明**（逐字使用）：
   ```
   监控程序只在你的 Mac 上截图并识别文字，截图和整页文字不会上传；只有窗口里新出现的文字会发给 Fiona 用于判断，不落日志。AI 判断规则会把新出现的文字发给阿里云千问（选 Claude 时发给 Anthropic）。只会保存提醒摘要。
   ```

### 3.2 聊天页（`frontend/app/page.tsx`）

- 登录后，页面可见时每 10 秒请求一次 `GET /local-watch/alerts?after=<最后一条 id>`。
  - 首次加载只记录最新 id，不回放历史提醒。
  - 页面不可见时暂停请求。
  - 请求返回 404（功能关闭）时停止轮询。
- 有新提醒且 `conversation_id` 等于当前会话、当前没有正在进行的回复时：把它作为一条 assistant 消息追加进当前列表，内容用 `【本机提醒 · …】` 的正文格式。
- 不属于当前会话时：在会话列表对应条目或页面顶部显示小提示「有新的本机提醒」，点击后切换到该会话。
- 浏览器通知：用户在设置区块里点「允许浏览器通知」后，新提醒同时弹出 `Notification`。默认不弹。

## 4. 文档

在 README.md、CLAUDE.md、PLAN.md、docs/ARCHITECTURE.md、docs/DEPLOYMENT.md、backend/.env.example 中写明：

- 功能说明与数据流（本机 OCR → 只上报新增行 → 判断 → 写进聊天）；
- 环境变量 `FIONA_LOCAL_WATCH`、`FIONA_DAILY_WATCH_JUDGE`；
- 设备令牌的安全须知；
- 已知局限：
  - 只支持 macOS；
  - 窗口最小化后截不到；
  - OCR 可能有错字；
  - 只能看到窗口当前显示的内容；
  - Fiona 页面关闭时不会实时弹出，但提醒照样落库。

文档里不得出现本机绝对路径。

## 5. 约束

- **受保护文件**，本单不得修改：
  - `backend/llm.py`、`backend/intent_router.py`、`backend/mode_switcher.py`、`backend/crisis_model.py`、`backend/safety.py`；
  - `backend/byok/`（只调用，不修改）、`backend/services/chat_service.py`、`backend/services/claude_agent.py`、`backend/routers/chat.py`；
  - `backend/tools/`；
  - `desktop/`。
- `backend/database.py` **只允许新增**：新建表、删号清理、新的读写函数。不得修改现有表结构或现有函数的行为。
- **测试纪律**：
  - 任务前已有的测试一律不改；新测试放在新文件里，文件名前缀为 `test_local_watch_`。
  - 新测试不依赖 git 历史，不依赖 `frontend/node_modules`（用到时缺包就跳过），全部离线运行（模块级拦截 socket 与 DNS）。
  - 千问和 Claude 都要打桩。
- **依赖**：后端不新增依赖；Swift 不引入第三方包。
- 不发起真实网络请求，不启动服务；先写会失败的测试，再改代码。
- 使用多个 subagent 并行，按文件分工，互不重叠。派子代理时不要传 model 和 reasoning_effort 参数。

### 必须覆盖的测试点

1. **设备令牌**：明文只返回一次；库里只有哈希；吊销后返回 401；最多 3 台；错误令牌返回 401；其他用户的令牌访问不到本用户的规则。
2. **规则**：增删改查及参数校验覆盖每种类型的边界；每人最多 20 条；跨用户无法访问。
3. **心跳**：返回的规则不含 `params`；窗口清单按用户隔离，5 分钟后过期，标题截断。
4. **observations**：
   - 规则不存在、未启用或不属于本人时被拒；
   - 行数和字数超限被拒或截断；
   - 设备限流返回 429。
5. **判定**：
   - 关键词：大小写、多关键词、未命中；
   - 数值：负号、小数、千分位、百分号、四种比较符、label 后没有数字；
   - AI：
     - 平台模型的请求参数（模型、JSON 模式、`max_tokens`、超时、不重试）；
     - 返回不合法、超时；
     - 选 claude 但未启用 BYOK；
     - 冷却期内不调用模型；
     - 每日上限。
6. **落库**：
   - 正文格式正确；
   - 写入指定会话，会话失效时改写默认会话；
   - 有 `watch_alerts` 记录；
   - 不触发画像提取，不扣草莓（余额不变）；
   - 日志和 trace 中不出现新增文字和摘要（用 `caplog` 设为 DEBUG 级别断言）。
7. **alerts 接口**：`after` 语义、最多 50 条、跨用户隔离。
8. **开关**：`FIONA_LOCAL_WATCH=0` 时全部 404。
9. **数据库**：旧库自动建表；删号时清理三张表。
10. **前端**：
    - 首次只记录 id 不回放；
    - 页面不可见时暂停；
    - 404 后停止轮询；
    - 属于当前会话的提醒被插入；
    - 隐私文案逐字出现。

    实现方式沿用现有前端逻辑测试：用 node 抽取逻辑执行，或做源码断言；需要包的部分缺包时跳过。
11. **文档**：六个文件中都有关键说明。
12. **Swift**：`swift build` 通过；`swift test` 中规范化、新增判定、OCR 三组测试通过。

### 停下来的条件

只有当规格自相矛盾，或必须修改受保护文件才能实现时，才停下来。此时在 `03-report.md` 写明冲突、可选方案及其影响，然后停止，不要回滚已完成的工作。

## 6. 验收（输出与退出码写入 `03-report.md`）

1. `git status --porcelain` 中只出现允许范围内的文件。
2. 受保护文件零 diff：
   ```
   git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/byok backend/services/chat_service.py backend/services/claude_agent.py backend/routers/chat.py backend/tools desktop
   ```
3. `git diff -- backend/database.py` 只包含新增内容（没有删除行；如有删除，必须逐条说明理由）。
4. `git diff --name-only -- backend/tests` 为空，即既有测试没有被改动。
5. 默认全量 `python -m pytest -q` 通过，沙箱无法绑定端口的测试单独列出。
6. 本任务新测试全部通过。
7. `python -m pip check` 通过。
8. 前端 `npx tsc --noEmit`、`npx eslint .` 都是 0 errors。
9. 在 `watcher-mac/` 下运行 `swift build -c release` 和 `swift test`；沙箱里跑不了时写明原因。
10. 报告写明：修改了哪些文件、与各节的逐项对应、上述各项的实际结果、需要作者方在沙箱外或真机上验证的点。原始 traceback 存到 `acceptance/`，不要整段贴进报告。
