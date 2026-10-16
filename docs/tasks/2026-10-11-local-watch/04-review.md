# 独立复核（后端与前端）

日期：2026-10-11。Opus 5.5 只读复核，范围为后端与前端（watcher-mac 由真机验收）。必须修复项转入 [05-fix-r2.md](05-fix-r2.md)。

## 本机监控（local-watch）后端 + 前端独立复核

基线 129b32a，改动未提交。只看后端与前端，未看 watcher-mac/。
已复跑：5 个 `test_local_watch_*.py` 共 128 passed。受保护文件 `git diff --exit-code` 为 0。`backend/tests` 下既有测试零改动。`database.py` / `main.py` / `rate_limit.py` 的 numstat 分别是 199/0、18/0、11/0，没有删除行。
离线探针在 `probe/`（socket/DNS 已拦截）：`probe1.py`、`test_probe_caplog.py`。

## 必须修复

### M1. AI 判断「不需要提醒」被一律记成判断失败
- **位置**：`backend/services/local_watch.py:82-89`（`_parse_decision`），以及 :150-155、:200-202。
- **触发 → 结果**：按 §2.6 提示词，模型正常返回 `{"alert": false, "summary": ""}`。此时 `_parse_decision` 因 summary 长度为 0 抛出 `ValueError("Invalid watch summary")`。结果是：
  - 每一次正常的「不提醒」都打一条 WARNING `local_watch exception_type=ValueError`；
  - trace 写入 `success=False, exception_type=ValueError`。

  探针 `test_probe_caplog.py::test_negative_alert_is_failure` 实测 `failure == ["ValueError"]`。不会多发或漏发提醒，但「判断失败」这个指标完全失真：真实的超时、异常和正常否定混在一起，日志里每次观察都有一条告警。
- **规格**：§2.3 写「summary 去空白后为 1–80 字」，§2.6 提示词又要求「不需要时为空串」，两处互相矛盾。实现取了字面意思，把冲突落到了运行时。
- **改法（需作者拍板）**：
  - `alert` 必须是 bool。
  - `alert=true` 时，summary 去空白后为 1–80 字。
  - `alert=false` 时，summary 只校验是字符串，内容忽略，并作为成功的否定结果返回。
  - 补测试：`{"alert":false,"summary":""}` 返回 `{"alert": False}`，`failure` 为空，trace 中 `success=1`。

### M2. 数值规则不认 Unicode 负号，导致正负颠倒、误报
- **位置**：`backend/services/local_watch.py:57`（`_NUMBER`），:70-71。
- **触发 → 结果**：行情软件和 OCR 常输出 `−`（U+2212）或全角 `－`（U+FF0D）。探针 `probe1.py` 实测：
  - `涨幅 −5.2%`、`涨幅 －5.2%` 都被解析成 `+5.2`；
  - 规则 `涨幅 >= 3` 因此**误报**「涨幅 当前 5.2%，已 >= 3」；
  - 规则 `涨幅 <= -3` 因此**漏报**。

  ASCII `-` 是正常的。
- **规格**：§2.3 number「支持负号」。§0 明确把行情软件列为目标场景。
- **改法**：
  - 匹配前把 `−`、`－`、`‒-―`（数字前的那个字符）规范成 `-`，把全角 `＋` 规范成 `+`；或者把正则的符号类扩成 `[-+−－＋]`，`float()` 前再替换。
  - 补参数化测试：`−5.2%`、`－5.2` 在 `>=3` 下不命中，在 `<=-3` 下命中。

### M3. 前端插入的提醒正文与数据库正文不一致
- **位置**：`frontend/lib/localWatch.ts:120-126`（`localWatchMessage`）；后端 `backend/services/local_watch.py:194-196`。
- **触发 → 结果**：后端落库正文为 `【本机提醒 · <app_name 或规则名>】<summary>（规则：<规则名>）`，只要窗口缓存匹配到窗口，标签就是应用名，例如「微信」。前端则一律用 `rule_name` 拼两处。由此出现以下情况：
  - 当前会话里实时插入的是「【本机提醒 · 盯老板】…（规则：盯老板）」，刷新后变成「【本机提醒 · 微信】…（规则：盯老板）」。
  - 规则被改名后，前端显示新名字，库里是旧名字。
  - 规则被删除后，前端显示「【本机提醒 · 已删除规则】…（规则：已删除规则）」。

  `test_local_watch_frontend.py` 第 110 行断言的正是前端这种拼法，测试把不一致固化了下来。
- **规格**：§2.4 第 2 条规定了正文格式；§3.2 要求插入时「内容用 `【本机提醒 · …】` 的正文格式」，意思是与落库那条一致。
- **改法（二选一）**：
  - `save_watch_alert` 返回或保存实际写入的 `content`（或 `label`），`/alerts` 多返回一个 `content` 字段，前端直接使用。这会改 §2.2 的字段清单，需作者同意。
  - 不改接口：前端插入后对该会话做一次 `GET /conversations/{id}/messages` 静默刷新，用库里那条替换。

  同时修改 frontend 测试第 110 行的期望值。

### M4. 未鉴权的设备接口每次请求都抢 SQLite 写锁，且没有任何 IP 限流
- **位置**：`backend/database.py`（新增的 `authenticate_watch_device`，在 diff 中位于 `BEGIN IMMEDIATE` 后紧跟 SELECT）；`backend/main.py` 中 `require_auth` 对 `/local-watch/heartbeat|observations` 直接放行；`backend/routers/local_watch.py:120-127`。
- **触发 → 结果**：公网任何人带一个随意的 `Authorization: Bearer x` 请求 `/local-watch/heartbeat`，都会走 `BEGIN IMMEDIATE`（RESERVED 写锁）→ SELECT → 失败返回。路径上：
  - 没有 slowapi 限制；
  - 不经过 require_auth 的 JWT 快速拒绝。

  洪泛时会与全站所有写事务争锁：聊天落库、扣草莓、trace 都要排队等 `SQLITE_BUSY_TIMEOUT`。这是本单新增的、无需登录的写锁放大面。令牌本身 256 bit，无法爆破，问题只在 DoS。
- **规格**：§2.2 设备侧「用哈希查找有效设备，同时更新 last_seen_at」。用户要求重点查「限流可绕过」。
- **改法**：
  - `authenticate_watch_device` 先用普通 SELECT 查找（不开事务），命中后再单独执行 `UPDATE … last_seen_at`。可选：距上次更新不足 30 秒就不写。
  - 给 `current_device` 的 401 分支加按 IP 的 slowapi 或内存限流，例如每 IP 每分钟 30 次失败。

## 可优化

1. **缺索引**（`backend/database.py` 新增 DDL）。
   - `latest_watch_alert_time` 每次观察都执行 `WHERE username=? AND rule_id=? ORDER BY id DESC`，`list_watch_alerts` 执行 `WHERE username=? AND id>?`，`list_watch_rules` 按 username 查询，三张表除主键和 `token_hash UNIQUE` 外都没有索引。
   - `watch_alerts` 没有保留期限，会一直增长，每分钟最多 60 次全表扫描。
   - 建议新增 `CREATE INDEX IF NOT EXISTS idx_watch_alerts_user_rule ON watch_alerts(username, rule_id, id)`、`idx_watch_alerts_user_id ON watch_alerts(username, id)`、`idx_watch_rules_user ON watch_rules(username)`。这属于「只新增」。
2. **设备侧限流与请求体上限偏松**（`backend/routers/local_watch.py:208-249`）。
   - 设备接口沿用全局 25MB 请求体上限，`request.json()` 会先整体解析再校验；heartbeat 没有频率限制，200 个标题、每个最多 10000 字也能通过解析。建议设备路径单独限制到约 256KB，heartbeat 加约每分钟 6 次的限流。
   - observations 的 60 次/分钟计数放在 body 校验和查规则之后。422 请求和 404（不存在或已停用的规则）都不计数，可以无限刷 DB 查询。建议鉴权后立即计数。
   - 吊销后再建设备能拿到新的限流桶，`watch_devices` 也会被无限加行（只限有效设备数）。影响只限本人账号。
3. **数值解析的边角**（`_NUMBER`，:57）。
   - `价格 1,2345` 解析为 1234，吞掉了一位数字。建议千分位分支加 `(?![\d])` 前瞻，不满足就退回 `\d+`。
   - 全角逗号 `，`、全角数字后的 `％` 也不支持。
4. **删除会话或消息后，`watch_alerts.summary` 仍然保留**，`/alerts` 也继续返回。摘要里可能含有 OCR 原文，例如关键词规则摘要就是整行。规格只要求删号时清理，但用户删会话时预期内容会消失。建议删除会话时同步删除对应的 `watch_alerts`，或设定保留期。
5. **Claude 判断没有显式控制 effort / thinking**（`services/local_watch.py:117-124`），`max_tokens=300`。如果所选型号默认会思考，输出可能被截断，导致永远「判断失败」。BYOK 聊天会显式传 `output_config.effort`。建议在 `output_config` 中同时传 `"effort": "low"`，或用真 Key 验证（报告 §6 第 4 条已列入）。
6. **同一账号的观察被一把 asyncio.Lock 串行处理**，锁在 8 秒 AI 调用期间一直持有（:161-204）。多条 AI 规则并发上报时，请求会在服务端排队，可能触发 Mac 端超时后重试，排队继续堆积。可改为按 `(username, rule_id)` 加锁；额度和冷却本来就按规则或原子计数实现。
7. **前端 404 文案**（`frontend/lib/localWatch.ts:61`）：所有 404 都显示「本机监控暂未开启」。在两个标签页里先后删除同一规则、吊销同一设备时，会误报「暂未开启」。建议只在 `/rules`、`/devices` 列表 GET 时这样映射。
8. **窗口预填**（`LocalWatchSection.tsx:223`）：`app_name` 可能超过 60 字，后端允许 200 字。预填进去后保存会得到笼统的 422。建议 `.slice(0, 60)`。
9. **隐私断言没有正控**：`test_local_watch_backend.py:185/194`、`test_local_watch_service.py:77-86/146/161` 只断言「不在 caplog.text 里」。探针已证实 caplog 能捕获、过滤器也生效，所以这些断言目前不是恒真。仍建议每处加一条正控，例如断言 `exception_type=` 或 `local_watch rule_id=` 出现在 caplog.text 中，防止以后静默失效。
10. **删号时没有清理进程内的 `_windows[username]`**（`routers/local_watch.py:19`）。有 5 分钟 TTL，加上 retired_usernames 机制，实际影响极小，可在删号路由里顺手 pop 掉。

## 已核实无问题的要点

### 令牌与鉴权
- `secrets.token_bytes(32).hex()` 生成 256 bit 令牌。库里只存 sha256 十六进制；列表接口不返回 `token` 和 `token_hash`；明文只出现在创建响应里。
- 校验通过 UNIQUE 哈希等值查询完成，攻击者无法控制哈希前缀，等价于常量时间比较。
- `revoked=0` 并且 JOIN users：吊销或删号后立即 401。
- 有效设备上限 3 台，规则上限 20 条，都在 `BEGIN IMMEDIATE` 内计数，没有并发超额。

### 两套鉴权不会混用
- 用户侧接口：设备令牌不是 JWT，`authenticate_token` 解码失败后只回落到 Cookie，所以设备令牌拿不到任何用户侧数据。
- 设备侧：`current_device` 只认 Bearer，用户 JWT 的哈希不在表中，返回 401。
- 设备侧响应只含规则的 `id/app_match/title_match/interval_seconds` 和 `{"alert", "alert_id"}`，不含 `params` 和其他用户数据。
- Cookie 为 SameSite=Lax，CORS 只允许 localhost:3000，跨站无法伪造用户侧写请求。

### 越权
- 规则、提醒、窗口清单、观察上报全部按 username 过滤。
- 用别人的 rule_id 上报得到 404。
- 规则里填写别人的 conversation_id 时，`_owned_conversation` 拒绝，回落到默认会话，不会跨用户写入。

### 开关与响应头
- `private_local_watch` 中间件位于 require_auth 外层：`FIONA_LOCAL_WATCH=0` 时，未登录、设备和 OPTIONS 请求都直接 404。
- 所有 `/local-watch/*` 响应（包括 401 和 422）都覆盖为 `Cache-Control: private, no-store`。

### 隐私
- 422 和 404 的 detail 都是固定文案，不回显输入。
- `judge_ai` 吞掉异常，只记录类型。
- trace payload 白名单为 `rule_id/kind/alert/elapsed_ms/exception_type`。
- SDK 的 DEBUG 日志由 ContextVar 加 handler 过滤器屏蔽。探针证实：线程内的 openai DEBUG 被屏蔽，线程外仍正常输出。
- 写库的正文和摘要包成 `WatchPrivateText`，aiosqlite 的 DEBUG 日志里只有脱敏 repr。
- 窗口标题只放在进程内存，5 分钟过期，截到 80 字，不落库、不写日志。

### 数据库
- 三张表都用 `CREATE TABLE IF NOT EXISTS`，紧跟在 `USER_MODEL_CONFIGS_DDL` 之后，旧库启动时会自动创建。
- 删号在同一事务内清理三张表。
- `database.py` 只有新增，0 行删除。

### 判定
- 关键词用 casefold 匹配，摘要取首条命中行、截到 80 字。
- 数值解析支持 ASCII 负号、小数、千分位、末尾 `%` 和四种比较符，label 后没有数字时会继续看下一行。
- 冷却检查在调用模型之前，并且与每日额度一起处在按账号加的锁内，同一规则并发上报不会重复提醒，已有对应测试。
- 每日额度使用独立的 `check_watch_daily_cap`，在 DEV_MODE 下同样生效。
- 平台模型的参数（qwen3.8-flash、JSON 模式、300 tokens、关闭思考、8 秒、不重试、线程执行、外层 8 秒）与 plan_image 一致。
- Claude 路径：
  - 通过 `get_internal_config` 解密，含 `ensure_available` 检查和 FORBIDDEN_ENV 检查；
  - 用 `validate_model` 校验型号，非流式，不带 tools，使用 `output_config.format` json_schema；
  - BYOK 不可用时判定失败，不回退到平台；
  - SDK 1.12.1 接受 `output_config` 参数。
- AI 判断期间规则被修改、停用或删除时，旧的判断结果会被丢弃。

### 落库
- 走 `save_message(..., "assistant", ...)`。会话失效时回落到默认会话，并处理了竞态时的二次回落。
- 消息 id 按「本人 + 会话 + 正文 + id>before」精确反查。
- 不调用画像提取、匹配检测、扣草莓，也不进入危机流程，测试中这些函数都打了桩。
- 后续聊天历史里，提醒是 assistant 角色。`convert_messages` 会跳过开头的 assistant 消息，把连续的 assistant 字符串合并；智能体模式下 `preserve_blocks` 也会合并字符串内容。所以提醒不会被当成用户消息或 tool_result。

### 前端
- 轮询每 10 秒一次。
- 页面隐藏时中止进行中的请求，并跳过后续 tick。
- 收到 404 后永久停止。
- 首次加载会翻页建立基线，不回放历史提醒。
- 有回复进行中、对话正在加载或会话已切换时，提醒先留在收件箱，按 dbId 去重后再插入。
- 其他会话的提醒以「有新的本机提醒」提示呈现，点击后切换到该会话。
- 浏览器通知默认关闭，需要按账号显式开启并授权。
- 令牌只在本次生成后显示，可一键隐藏，吊销时清空。
- 隐私说明与 §3.1 第 5 条逐字一致。

### 测试纪律
- 新测试全部离线：模块级拦截 socket 和 DNS，千问和 Claude 都打桩。
- 前端逻辑用 node 抽取函数体执行，缺 node 时 skip，不依赖 node_modules。
- 不依赖 git 历史。

---

# 第 2 轮复核（R2、R3 返修）

## 本机监控 第 2 轮独立复核（R2-1~R2-5、R3-1~R3-3、作者两处小改）

复核日期：2026-10-11。仓库 Fiona，基线 129b32a（HEAD 未动），改动未提交。只读复核：未改仓库文件，未做 git 写操作，未启动服务，未碰 127.0.0.1:8056，未联网。

## 结论（通过/不通过）

**通过。** R2-1~R2-5、R3-1~R3-3 以及作者方两处小改，全部按条文完成，没有必须修复项。另有 7 条「可优化」，都不影响本轮验收。

本轮实测：
- 后端：`backend/.venv/bin/python -m pytest -q tests/test_local_watch_*.py` 结果 **308 passed**，即 Codex 报告的 307 项加作者新增的完整域名用例 1 项。
- 独立探针：`scratchpad/wo8/review/r2/test_r2probe.py`，离线运行，**43 passed**。
- Swift：把 watcher-mac 复制到 `scratchpad/wo8/review/r2/watcher-mac/`，用标准命令跑。`swift test` 在 CLT 下 **9 + 8 = 17 项全过**，含旧 OCR 用例；`swift build -c release` 显示 Build complete，退出码 0。`--show-bin-path` 实际给出 `.build/out/Products/Release/fiona-watcher`，说明 README 改用 `--show-bin-path` 写法是对的。

## 逐项核验

### R2-1 alert=false 时空 summary 视为成功 —— 通过
- 代码：`backend/services/local_watch.py:86-97`。`_parse_decision` 先要求 alert 是严格布尔；为 false 时直接返回 `{"alert": False}`，不校验 summary；为 true 时，summary 须为字符串，strip 后 1–80 字。
- trace：`process_observation` 用 `success=not failure` 记录（:208-210）。alert 为 false 时 failure 为空，所以记为成功。
- 探针输出（已含正控）：
  - `{"alert": false, "summary": ""}`、`{"alert": false}`、`{"alert": false, "summary": null}` 都返回 `{'alert': False}`，failure=[]，warn=False；
  - `{"alert": true, "summary": ""}` 和 `"   "` 都返回 None，failure=['ValueError']，warn=True；
  - 端到端走 `/local-watch/observations`：trace 为 `[(1, '{"rule_id": 1, "kind": "ai", "alert": false, "elapsed_ms": 0}')]`，success=1，没有 WARNING。
- 测试：`test_local_watch_service_r2.py` 已覆盖两种模型下 false 成功、true 失败。

### R2-2 五种负号与全角数字 —— 通过
- 代码：`services/local_watch.py:58-61` 的转换表。我用码位逐个核对过：U+2212、U+FF0D、U+FE63、U+2012、U+2013 都转成 `-`；全角数字、全角 `．`、`％`、`＋`、`，` 都转成半角。转换在 :71，取数之前执行。
- 探针：五种负号加 ASCII，与「半角/全角数字」「半角/全角百分号」组合，共 24 例。每例都满足：`>=3` 不命中，`<=-5` 命中且显示 `-5.2%`，`<-5.3` 不命中。全角正数 `１２３．５` 解析为 123.5。

### R2-3 alerts 返回 content，前端直接使用 —— 通过
- 后端：新增 `database.list_watch_alerts_with_content`（`backend/database.py:1931-1943`），从 messages 按 message_id、同用户、同会话、role='assistant' 取正文；路由 `routers/local_watch.py:300-302` 改用它。
- 前端：`frontend/lib/localWatch.ts:51-53` 中 `content` 是必填字段；`localWatchMessage` 用 `content: alert.content`（:128-135），前端不再拼接。
- 测试：`test_alert_content_is_exact_stored_message_after_application_label_rule_rename_and_delete`、`test_alert_content_join_never_discloses_...`、前端 `test_inserted_message_uses_exact_stored_content_after_rule_rename_or_delete`、`test_alert_contract_requires_content_and_has_no_reconstructed_fallback`。
- 两份任务内测试的契约改动属于 R2-3 授权范围，改动内容见 `acceptance/r2-contract-tests.diff`。

### R2-4 伪造令牌不写库、IP 限流、last_seen 节流、计数在校验前 —— 通过
- 只读拒绝：`database.authenticate_watch_device_throttled`（`database.py:1899-1928`）先用一条 SELECT 联 users 查询。查不到就直接返回 None，不做 BEGIN、UPDATE 或 commit。只有 `needs_touch` 为真（距上次更新至少 60 秒，用数据库时钟）才执行带条件的 UPDATE。
- IP 限流：`routers/local_watch.py:42-45` 的 `authentication_failed`。超过每 IP 每分钟 30 次后返回 429，带 Retry-After 头（:26-39）。缺少认证头、令牌超长、令牌无效三种情况都会计数（:213-219）。
- 计数位置：heartbeat 和 observations 的第一行都是 `count_device_request`（:307、:335），在 `body()` 的 JSON 和参数校验之前，也在查规则之前。
- 探针：
  - 伪造令牌发 32 次，前 30 次 401，后 2 次 429；之后不带头的 observations 也返回 429；
  - 有效设备发坏 JSON：heartbeat 前 10 次 422，第 11 次 429；observations 前 60 次 422，第 61 次 429。
- 测试：
  - `test_forged_bearer_authentication_never_takes_write_lock_or_updates`：mock 了 execute 和 commit，断言没有 BEGIN/UPDATE，commits 为空；
  - `test_valid_device_last_seen_updated_once_then_read_only_within_sixty_seconds`：5 次请求只有 1 次 UPDATE；
  - `test_concurrent_authentication_does_not_refresh_database_value_more_than_once`；
  - `test_all_authentication_failures_count_by_real_client_ip_before_body_or_rule_validation`。

### R2-5 小修 —— 通过
1. 索引：`database.py:313-315` 新增三条 `CREATE INDEX IF NOT EXISTS`，分别是 `watch_rules(username)`、`watch_alerts(username,id)`、`watch_alerts(rule_id,id)`。`token_hash` 的 UNIQUE 未改动。测试：`test_three_watch_indexes_are_added_to_existing_database_idempotently_without_changing_data`。
2. 心跳限流：每设备每分钟 10 次（:307），探针结果见上文。
3. 预填截断：`LocalWatchSection.tsx:239-240` 中 app_match 和 title 都用 `Array.from(...).slice(0, 60)`，按码位截断，与后端 `len()` 的计数方式一致。测试：`test_window_click_prefills_both_matches_at_most_60_unicode_characters`。
4. 千分位：正则见 `services/local_watch.py:57`，`\d{1,3}(?:,\d{3})+(?!\d|,\d)|\d+`。探针结果：`1,234` 得 1234，`1,234,567.89` 正确，`-1,234.5%` 正确，`1,2345` 得 1，`1,23,456` 得 1，`12,34` 得 12，全角逗号 `1，234` 得 1234。没有吞掉数字。
5. 隐私正控：`test_privacy_assertion_positive_control_then_real_processing`（service_r2:165）先故意把文字写进日志，确认同一断言函数会抛 AssertionError；清空日志后，再用两种模型桩走真实处理验证不泄漏。

### R3-1 Swift 日志节流与 capture_status 结构 —— 通过
- 状态机：`watcher-mac/Sources/FionaWatcherCore/CaptureStatus.swift`。
  - `failed` 按「规则 → 错误身份 `domain/code`」节流 60 秒（:50-61）。日志格式是 `规则 id=<id>，应用=<app>，截图失败：<域>/<码>`，只用 NSError 的 domain 和 code，不读 localizedDescription。
  - `succeeded` 只在从错误状态转为成功时记一次 `规则 id=<id>，截图已恢复`（:67-71）。
  - `windowNotFound` 写入 `window_not_found`（:63-65）。
  - `since` 只在状态切换时更新（:77-83）。
  - `error` 为 nil 时显式编码成 null（:13-23）。
- 接线：`Watcher.swift`。
  - 每次心跳都带 `capture_status: captureStatus.reports()`（:124-127、:204-206）；
  - 截图失败走 `failed`（:271-279），成功走 `succeeded`，并且在「画面未变化跳过 OCR」之前执行（:287）；
  - 找不到窗口时 `windowNotFound`（:249-253）；
  - 枚举窗口失败时保持心跳，并把原始错误记到每条规则（:189-202、:243-248）。
- 测试：独立 target `FionaWatcherCaptureStatusTests`（`Package.swift:12-13`）的 8 项用例。用注入的 NSError 和时钟验证：60 秒边界、多规则隔离、A→B→A 错误切换、恢复只记一次、重置匹配条件不能绕过节流、JSON 的四个键与 null、ISO8601 格式、localizedDescription 中的「窗口文字」不进入日志或 JSON。本轮 `swift test` 实测 8/8 通过。

### R3-2 后端保存、过期、中文映射、隔离，设置页逐条显示 —— 通过
- 保存与校验：`routers/local_watch.py:82-106` 严格校验四个键、类型、长度和 ISO8601 时区。:316-329 只保留本用户已启用的规则，然后按 `(DB_PATH, username, device_id)` 整体替换该设备的快照。:124-127 以服务器单调时钟为准，300 秒过期。
- 规则返回：GET rules 中每条规则都有 `capture`（:248-253）。没有状态或已过期时，严格返回 `{"ok": false, "message": "监控程序未在运行"}`。
- 中文映射：`capture_message`（:109-121）。
- 作者小改：比较错误域的最后一段，`short = domain.rpartition(".")[2]`；另外域中含 `ScreenCaptureKit` 也算。新增用例 `com.apple.ScreenCaptureKit.SCStreamErrorDomain/-3811` 位于 `test_local_watch_capture_backend_r3.py:93`，本轮通过。
- 探针结果：
  - 完整域名映射到「截图失败：屏幕可能已锁定或显示器已休眠，也可能缺少屏幕录制权限」；
  - `window_not_found` 映射到「没有找到匹配的窗口（窗口可能已关闭或最小化）」；
  - `NSOSStatusErrorDomain/-50` 映射到「截图失败，请查看监控程序日志」；
  - 299.9 秒时仍显示「监控中」，300 秒时变为「监控程序未在运行」；
  - 其他用户看不到本设备的状态；上报他人的规则 id 会被丢弃；不带 capture_status 的旧心跳返回 200。
- 隔离与生命周期：吊销设备会清掉它的状态（:244）；删号或设备不再有效时，读取时会过滤掉（:137-142）。测试：`test_capture_isolation_between_users_and_foreign_status_is_discarded`、`test_directly_revoked_device_and_deleted_user_cannot_retain_active_status`、`test_capture_cache_is_scoped_to_database_...`。
- 前端：`LocalWatchSection.tsx:251` 在每条规则下显示 `localWatchCaptureMessage(rule)`。正常时为「监控中」（普通灰色），异常时用 `var(--seal)` 醒目色。可见页面每 10 秒刷新，切换账号或卸载时清理定时器（:104-109）。

### R3-3 锁屏无法监控的说明 —— 通过
`系统设置 → 锁定屏幕 中延长自动锁定时间，但要自行权衡安全` 这句在以下 8 处各出现 1 次（grep 计数）：
- 02-spec 第 4 节的六份文档：README.md:306、CLAUDE.md:147、PLAN.md:450、docs/ARCHITECTURE.md:302、docs/DEPLOYMENT.md:742、backend/.env.example:167-168；
- watcher-mac/README.md:62；
- 设置页 `LocalWatchSection.tsx:202`。

文档中没有本机绝对路径（grep `<本机路径>`、`/private/tmp` 零命中）。测试：`test_capture_outage_and_lock_screen_security_guidance`（7 个参数）、`test_settings_explains_locked_screen_limitation_and_security_tradeoff`。

### 作者两处小改 —— 通过
1. `capture_message` 只比较错误域最后一段，并补了完整域名用例。核验见 R3-2。
2. `watcher-mac/README.md:15、:37`：可执行文件路径改为 `"$(swift build -c release --show-bin-path)/fiona-watcher"`，并注明 TestingMacros 插件报错时先 `rm -rf .build`。在副本中实测，`--show-bin-path` 给出的路径下确实有可执行文件；这个路径不是旧写法的 `.build/release`，所以不写死路径是必要的。

### 约束 —— 通过
- `backend/database.py`：`git diff 129b32a --numstat` 显示 `249 0`，没有任何删除行。
- 受保护文件：对 llm/intent_router/mode_switcher/crisis_model/safety、byok/、chat_service、claude_agent、routers/chat.py、tools/、desktop/ 执行 `git diff --exit-code 129b32a`，退出码 0；`git status --porcelain` 中这些路径为 0 行。
- 既有测试：`git diff --name-only 129b32a -- backend/tests` 输出为空；backend/tests 下没有 `test_local_watch_` 以外的未跟踪测试文件。
- 与 `acceptance/r3-start-sha256.json` 比对 1064 个文件：自 R3 开始以来，没有任何测试文件改变。有变化的只有实现、文档、报告，以及 tsc 缓存 `tsconfig.tsbuildinfo`。
- 附带说明：仓库 `watcher-mac/.build` 当前存在，生成时间是 12:48–12:53，晚于 Codex 清理时间 12:44，应是作者真机构建所留，已被 .gitignore 忽略，不属于 Codex 遗留。

## 必须修复（仅限条文未完成或改错的）

无。

## 可优化

1. **失败限流用的是对端地址，不是真实客户端 IP**（`routers/local_watch.py:43`，用 `request.client.host`）。生产环境在 Nginx 后面，uvicorn 若没有按 XFF 改写对端，所有来源会共用 127.0.0.1 这一个桶，「每 IP 30 次」实际变成全局 30 次。合法设备不受影响，因为只有失败的请求才计数和返回 429。建议改用现有的 `rate_limit._client_ip`，它已经实现了按 `FIONA_TRUSTED_PROXIES` 信任代理头。
2. **新规则尚未截图时被显示为失败**。Swift 端新规则的初始状态是 `ok=false, error=null`（`CaptureStatus.swift:35-37`），后端映射为「截图失败，请查看监控程序日志」（`local_watch.py:115-121`），但这时并没有对应的日志。建议后端把 `error is None` 映射成「等待首次截图」之类的中性文案。
3. **监控程序刚启动的约 30 秒内显示「监控程序未在运行」**。首个心跳发出时状态表还是空的（reconcile 在拿到响应后才执行，`Watcher.swift:204-231`），后端收到空快照后会清掉该设备的状态（:327-329）。
4. **已停用的规则也显示「监控程序未在运行」**（:252），容易误导，可以改为显示「已停用」。
5. **「截图已恢复」日志不节流**（`CaptureStatus.swift:67-71`）。截图在失败和成功之间反复切换时，失败日志受 60 秒节流，但每次恢复都会记一条；从 `window_not_found` 恢复也会记「截图已恢复」。不违反条文，但抖动时日志会偏多。
6. **一条状态非法会让监控程序整体退出**。capture_status 中任意一条非法，后端就对整个心跳返回 422（:82-106），Swift 端 `postWithRetry` 遇到 422 会抛错，监控程序随之退出（`Watcher.swift:348-349`）。目前 Swift 生成的数据都合法，属于防御性问题。
7. **watcher-mac/README.md:46 的说法已过时**。这里仍写「日志只包含规则 id、窗口应用名、新增行数和 HTTP 状态」，而 :71 已新增截图失败的错误域/码和恢复日志，建议把 :46 合并改写。

另外，设置页每 10 秒刷新时，会顺带请求 `/conversations` 和 chat model（`LocalWatchSection.tsx:60-67`）。如果只是为了刷新状态，可以只拉 `/rules`。
