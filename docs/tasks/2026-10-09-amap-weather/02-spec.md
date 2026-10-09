# 天气意图改用高德地图 MCP（百炼托管）（L2）

基线：`main` @ `9857846`（已合并「搜索与旅行真实来源」）；后端 `python -m pytest -q` 为 **2164 passed**；前端 `npx eslint .` 为 **0 errors / 25 warnings**。本文引用代码位置时以**函数名和原文片段**为准，行号仅供参考（上一单合并后可能漂移）。

## 1. 产品目标

现在 Chloe 查天气的方式有三个问题：
- 只有用户这句话里**恰好含「天气」两个字**，搜索工具才会转去英文天气服务 wttr.in；「明天会下雨吗」「要带伞吗」出不了天气卡。
- 没说城市时**写死查宁波**（`backend/tools/visual_search.py` 的 `city = "Ningbo"`）。
- 天气状况是**英文**（如 Partly cloudy），前端「带伞」提醒靠英文单词判断。

**目标**：
1. 新增独立的 `weather` 意图：能识别问句式天气（「明天会下雨吗」「杭州冷不冷」「要带伞吗」），带 `city` 参数；**没说城市就追问「哪个城市？」**，不默认任何城市，不做 IP 定位，不读用户画像里的城市。
2. 天气数据改用**阿里云百炼托管的高德地图 MCP**（Amap Maps，用户已在百炼控制台开通，目前限时免费），全中文。
3. 用户对追问回「算了」时取消；回一句明显不是城市名的话时，不把它当城市发给高德，而是当作新消息正常处理。
4. 每个用户每天的天气查询有上限；超限、失败都不扣草莓。
5. 意图识别出口统一做格式规范化（待修清单 C10），防止模型返回畸形 JSON 导致之后 10 分钟每句报错。
6. 删除已无调用方的旧天气/视觉搜索代码 `backend/tools/visual_search.py`。

**用户场景**：
- 「明天杭州会下雨吗」→ 天气卡：杭州市，今天/明天/后两天，每天白天与夜间天况、最高最低温、风向风力；气泡说「杭州市今天晴，17~26°；明天小雨，记得带伞。」
- 「明天会下雨吗」→ Chloe 问「哪个城市？」→ 用户答「宁波吧」→ 宁波天气卡。
- 追问后用户答「算了」→「好，已取消。」，不扣草莓。
- 追问后用户发「帮我搜一下今天的新闻」→ 不查天气，按搜索正常处理。

**本单不做**：路线（`route`，仍是现有 OSRM 实现，一行不改）、周边地点搜索（`poi_search` 不新增）、天气卡持久化（卡片仍不落库，既有限制）。

## 2. 已实测的真实接口事实（2026-10-09）

端点：`https://dashscope.aliyuncs.com/api/v1/mcps/amap-maps/mcp`（Streamable HTTP），请求头 `Authorization: Bearer <DASHSCOPE_API_KEY>`、`Content-Type: application/json`、`Accept: application/json, text/event-stream`。

1. **无状态调用可用**：不做 `initialize`、不带 `Mcp-Session-Id`，直接发 `tools/call` 即返回结果（约 0.2 秒）。响应头 `Content-Type: application/json;charset=utf-8`，响应体是单个 JSON-RPC 对象：
   ```json
   {"jsonrpc":"2.0","id":8,"result":{"content":[{"type":"text","text":"{\"city\":\"杭州市\",\"forecasts\":[...]}"}],"isError":false}}
   ```
2. `maps_weather` 入参 `{"city": "<城市名或 adcode>"}`，成功时 `text` 解析后为：
   ```json
   {"city":"杭州市","forecasts":[
     {"date":"2026-10-09","week":"5","dayweather":"晴","nightweather":"晴","daytemp":"26","nighttemp":"17",
      "daywind":"东","nightwind":"东","daypower":"1-3","nightpower":"1-3","daytemp_float":"26.0","nighttemp_float":"17.0"},
     ... 共 4 天 ...]}
   ```
   - **没有实时温度、体感温度、湿度**。`week` 为 `"1"`–`"7"`（周一=1，周日=7）。温度是字符串。
3. 城市名无效（如「算了」）或英文城市名（如「Hangzhou」）：**不报错**，返回 `{"city":null,"forecasts":null}`（`isError:false`）。
4. 上游业务错误：`isError:true`，`text` 形如 `API 调用失败：USER_DAILY_QUERY_OVER_LIMIT`、`API 调用失败：ENGINE_RESPONSE_DATA_ERROR`。
5. 工具名不存在：HTTP 200，JSON-RPC 错误 `{"error":{"code":-32603,"message":"Tool not found: no_such_tool"}}`。
6. Key 无效：HTTP 401，`{"code":"InvalidApiKey","message":"Invalid API-key provided.",...}`。
7. 未开通该 MCP：HTTP 404，响应体为纯文本「未开通该MCP或非可用开通状态」。

本单客户端按上述「无状态 `tools/call`」实现，不做 `initialize` 握手；**同时**要能解析 `text/event-stream` 形式的响应（协议允许服务端改用 SSE），只取 `id` 等于本次请求 id 的那条 JSON-RPC 消息。

## 3. 技术约束

- 沿用现有栈，不引入新依赖（不装 `mcp` SDK），不做无关重构。
- **不得改动**：`backend/tools/route.py`、`backend/tools/native_search.py`、`backend/tools/travel_plan.py`、`backend/tools/card_detail.py`、`backend/tools/topic_expand.py`、`backend/utils/safe_http.py`、`execute_intent(intent, params)` 的签名（多个测试用两参数 lambda 打桩）。
- 外部 HTTP 只用 `urllib.request`，并以**模块属性**方式调用 `urllib.request.urlopen(...)`（测试断网夹具靠替换这个属性）；不用 `requests.post`、`httpx`、`safe_http`（后者只允许 GET/HEAD 且会剥掉 Authorization 头）。
- 端点写成模块常量，**不允许用环境变量覆盖端点**（防止 Bearer Key 被发到别的主机）。
- 新模块不调用 `load_dotenv`，也不 `import llm`（llm 导入时会构造客户端）；Key 在调用时用 `os.environ.get("DASHSCOPE_API_KEY", "").strip()` 读取。
- **隐私**：城市名、用户原话不得写进日志、trace payload、异常文案；日志只记工具名、异常类型和耗时，格式参照 `backend/crisis_model.py` 的 `print(f"[crisis-model] failed type=... ms=...", flush=True)`，例如 `print(f"[amap-mcp] failed tool={name} kind={kind} ms={ms:.1f}", flush=True)`。给用户看的失败文案用固定中文，不带供应商原文。
- 危机处理约定（`CLAUDE.md`「当前重要边界」中的私聊危机段）除第 5.6 节明确修改的那一点外，全部保持不变；任何错误路径都必须保证危机资源恰好送达一次（参照 `chat_service.py` 中生图忙碌拒绝的写法：先 `_needs_crisis_resource` / `_crisis_resource_event` 再发错误）。
- 前端颜色只用现有设计 token；改前端前先读 `frontend/AGENTS.md`。
- 请用多个 subagent 并行，按文件不重叠分工（建议：①MCP 客户端+天气工具+其测试；②意图识别+chat_service+rate_limit+其测试；③前端两个文件；④文档）。同一文件的改动交给同一个 subagent。

## 4. 配置项（全部在调用时读取，不合法回退默认值）

| 变量 | 默认 | 规则 |
|---|---|---|
| `FIONA_AMAP_ENABLED` | `1` | 只有字面 `"0"` 关闭（照 `FIONA_CRISIS_MODEL_ENABLED` 的写法）；关闭时天气返回失败卡「天气服务暂未开启」，不发请求 |
| `FIONA_AMAP_TIMEOUT_SECONDS` | `8` | 浮点，合法范围 1–30，否则回退 8（照 `crisis_model._timeout_seconds` 的写法，`nan`/`inf`/空串/非数字都回退） |
| `FIONA_DAILY_WEATHER` | `30` | 加进 `rate_limit._DAILY_SETTINGS`，kind 名 `weather`；规则与现有四项每日上限一致（正整数，不合法回退并只警告一次） |

在 `backend/.env.example` 末尾追加这三项及一行中文注释（说明需在百炼控制台开通 Amap Maps、使用 `DASHSCOPE_API_KEY`）。同时把该文件第 16 行附近「模型请求默认 60 秒超时，失败最多重试 1 次」的注释补一句例外：搜索、旅行规划、热点展开、卡片详情走原生联网接口，固定 30 秒、不重试，不受这两个变量控制。不得改动任何变量的值。

## 5. 任务清单

### 5.1 MCP 客户端：新模块 `backend/tools/amap_mcp.py`

```python
AMAP_MCP_URL = "https://dashscope.aliyuncs.com/api/v1/mcps/amap-maps/mcp"
MAX_RESPONSE_BYTES = 1_000_000

def call_tool(name: str, arguments: dict) -> dict:
    """返回 {"ok": True, "data": <解析后的对象>} 或 {"ok": False, "error": <错误码>}。"""
```

1. `FIONA_AMAP_ENABLED == "0"` → `{"ok": False, "error": "disabled"}`，不发请求。
2. Key 为空 → `error="missing_key"`，不发请求。
3. 请求体：`{"jsonrpc":"2.0","id":<本次唯一整数>,"method":"tools/call","params":{"name":name,"arguments":arguments}}`，POST，请求头见第 2 节。
4. 超时：总预算 `FIONA_AMAP_TIMEOUT_SECONDS`；`urlopen` 的 `timeout` 取剩余预算；读取响应体时最多读 `MAX_RESPONSE_BYTES + 1` 字节，超过 → `error="too_large"`；读取完成后若已超出总预算 → `error="timeout"`；`socket.timeout` / `TimeoutError` / `urllib.error.URLError(reason=timeout)` → `error="timeout"`。
5. HTTP 错误：401/403 → `error="auth"`；404 → `error="not_enabled"`（未开通）；其他 → `error="http"`。不读取、不返回、不记录错误响应体。
6. 解析：
   - `Content-Type` 含 `text/event-stream` → 按 SSE 规范解析（空行分隔事件；`data:` 后可有可无空格；同一事件多行 `data` 用 `\n` 连接；`:` 开头为注释行），逐个事件 `json.loads`，取第一个 `id` 与本次请求 id 相等的对象；找不到 → `error="bad_response"`。
   - 否则按 JSON 解析整个响应体；不是 dict 或 `id` 不等 → `error="bad_response"`。
   - JSON-RPC 对象带 `error` → `error="rpc_error"`。
   - `result.isError` 为真：`text` 中含 `OVER_LIMIT` → `error="quota"`；否则 `error="tool_error"`。
   - 取 `result.content` 里第一个 `type=="text"` 的 `text`；尝试 `json.loads`，成功则 `data` 为解析结果，失败则 `data` 为原文字符串。缺失 → `error="bad_response"`。
7. 任何其他异常 → `error="exception"`。所有失败都按第 3 节格式打印一行日志（不含参数、不含响应体）。
8. 函数不得抛异常。

### 5.2 天气工具：新模块 `backend/tools/weather.py`

```python
def weather(city: str) -> dict:
```

1. `city` 先经 `utils.city_name.normalize_city`（5.4）规范化；为空 → 失败卡「没说是哪个城市」。
2. 调 `amap_mcp.call_tool("maps_weather", {"city": city})`。通过**模块级名字**调用（`from tools import amap_mcp` 后 `amap_mcp.call_tool(...)`），便于测试替换。
3. 失败卡统一形状：`{"type": "card", "source": "天气", "points": [<中文原因>], "error": True}`，**不带 `subtype`**（否则前端两个分支都不渲染）。原因映射：
   - `disabled` → 「天气服务暂未开启」
   - `missing_key` / `auth` / `not_enabled` → 「天气服务暂不可用」
   - `quota` → 「天气服务今天的查询额度用完了，晚点再试」
   - `timeout` → 「天气服务响应超时，稍后再试」
   - 其他 → 「天气服务暂时出错了，稍后再试」
   - 成功但 `data` 不是 dict，或 `forecasts` 不是非空 list → 「没找到「{city}」的天气，换个城市名试试」（`city` 截前 10 字）
4. 成功卡：
   ```python
   {"type": "card", "subtype": "weather", "source": f"天气 · {location}",
    "points": [], "error": False,
    "weather": {"location": location,  # data["city"]，非字符串时用规范化后的 city
                "forecast": [ {"date": "2026-10-09", "day": "周五",
                               "dayWeather": "晴", "nightWeather": "晴",
                               "high": "26", "low": "17",
                               "dayWind": "东风 1-3级", "nightWind": "东风 1-3级"}, ... ]}}
   ```
   - 最多取 4 天；逐项校验：`date` 必须是 `YYYY-MM-DD`，否则丢弃该天；`day` 由 `date` 计算（周一起算，「周一」…「周日」），不信任 `week` 字段；天况字段非字符串时为空串；温度只接受可解析为数字的字符串，否则为空串；风向 + 「风」+ 空格 + 风力 + 「级」，任一缺失则省略对应部分（例如只有风向时为「东风」，都缺时为空串）。
   - 每个字符串字段截到 20 字（防异常数据撑破卡片）。
   - 全部天都被丢弃 → 按「没找到」失败卡处理。
5. 不读取 `daytemp_float` 等其他字段，卡片里不出现上游原文以外的字段。

### 5.3 删除旧天气分流与 `visual_search.py`

1. `backend/tools/web_search.py`：删除「`if "天气" in query:` → `_search_weather_direct`」那段分流及文件头注释里「天气走专门的 wttr.in 直通车」的说法；含「天气」的 query 从此和其他搜索一样走原生搜索。函数其余部分一字不改。
2. 删除整个 `backend/tools/visual_search.py`（全仓已无其他调用方；先 grep 确认，若发现其他调用方则停下来在总结里说明）。

### 5.4 意图识别：`backend/intent_router.py`

1. **INTENT_PROMPT**：
   - 意图清单加一行：`weather  查天气（今天/明天/未来几天，下雨、冷热、穿衣）  params: city(城市名，只填用户明确说出的城市)`。
   - 把三处「天气 → web_search」的示例（「帮我查一下今天天气」「帮我看下明天的天气」以及输出格式里的 `{"intent": "web_search", "params": {"query": "今天天气"}, ...}`）改为 `weather`；输出格式示例改成一个不涉及天气的 web_search 例子。
   - 在「核心原则」之后补一段**天气例外**：「问天气的问句（会不会下雨、冷不冷、要不要带伞、穿什么）属于查询请求，返回 weather，这是原则 3 的例外」，并给出正例：「明天会下雨吗」→ weather, missing=[city]；「杭州明天冷不冷」→ weather, city=杭州；「要带伞吗」→ weather, missing=[city]；「那上海呢」（上一轮刚查过天气）→ weather, city=上海。反例：「最近天气不好心情差」→ null；「天气预报 API 哪个好」→ web_search；「今天天气真好」→ null。
   - **不得改动**生图相关段落和 `tests/test_image_intent_precision.py::test_intent_prompt_distinguishes_image_discussion_from_current_command` 断言的那些原文。
   - 城市只能来自用户本轮或最近对话里**明确说出的城市**；不得猜测或使用默认城市。
2. **`MISSING_QUESTIONS`** 加 `"city": "哪个城市？"`。
3. **`normalize_city(text) -> str`**（新增纯函数，放在新模块 `backend/utils/city_name.py`，不导入任何业务模块；`intent_router`、`tools/weather.py`、`chat_service` 都从这里导入，供 5.2、5.4.4、5.6 共用）：
   - 去掉首尾空白与标点；去掉前缀「在」「是」「查」「查一下」「就」「那」「换成」「改成」「去」，以及后缀「吧」「呢」「啊」「呀」「的天气」「天气」「的」，可重复剥离直到不变；
   - 剩余部分必须完全由 2–10 个汉字组成（`^[一-鿿]{2,10}$`），否则返回空串；
   - 不做城市库匹配（真伪由高德返回的 `forecasts` 是否为空来判定）。
4. **`fill_param`**：当缺失键是 `city` 时，填入 `normalize_city(message)`（其余键行为不变，`minutes` 的特殊处理保持原样）。
5. **出口规范化（C10）**：在 `recognize_intent` 内部、返回之前，调用新增纯函数 `normalize_intent_result(raw) -> dict`：
   - 意图白名单 = 提示词中列出的意图：`web_search`、`hot_topics`、`route`、`travel_plan`、`get_datetime`、`fetch_card`、`generate_image`、`weather`。`intent` 为 None、空串、非字符串、不在白名单 → `{"intent": None}`。
   - 每个意图允许的参数键：`web_search:{query}`、`hot_topics:{source}`、`route:{origin,destination}`、`travel_plan:{query}`、`get_datetime:{}`、`fetch_card:{query}`、`generate_image:{prompt,aspect_ratio}`、`weather:{city}`。`params` 不是 dict → `{}`；只保留允许的键（值原样保留，**不**额外规范化 generate_image 的参数）。
   - `missing` 不是 list → `[]`；只保留是字符串且在该意图允许键里的元素，去重保序。
   - `weather`：`params["city"]` 经 `normalize_city`；为空则删除 `city` 并确保 `missing == ["city"]`；不为空则 `missing` 去掉 `city`。
   - 返回 `{"intent", "params", "missing"}` 三键。
   - **白名单只在 `recognize_intent` 内部生效**；不得在 `recognize_intent_with_fallback`、`stream_intent`、`stream_pending`、`execute_intent` 或 pending 存取层（`set_pending`/`get_pending`）加白名单或改写载荷（多个基线测试用白名单外的意图如 `set_reminder`、`open_app`、`unknown_intent` 经这些路径）。
   - 兜底正则（`chat_service.recognize_intent_with_fallback` 里「帮我查/我搜…」→ web_search）**保持不变**，不增加任何天气规则。

### 5.5 分派、计费与落库摘要：`backend/services/chat_service.py`

1. `execute_intent`：在 route 分支之后、`return "不知道怎么执行这个"` 之前加 `if intent == "weather": return weather_query(params.get("city", ""))`（顶部 `from tools.weather import weather as weather_query`）。
2. `_BILLABLE_TOOLS` 加 `"weather"`（成功卡计费，失败卡因 `error: True` 自动退款）。
3. `_summarize_card_for_history` 的天气分支改为读新形状，**全部用 `.get` 并容错**（旧形状卡、空 forecast、字段缺失都不得抛异常）：输出形如「[天气 · 杭州市]\n• 周五 晴转小雨 17~26°\n• 周六 小雨 18~25°…」（白天夜间天况相同只写一个，不同写「A转B」；温度缺失则省略温度）。旧形状（含 `currentTemp` 的卡，例如 `tests/test_chat_branches.py` 里用 fetch_card 发的那张）也要能输出不报错的摘要。

### 5.6 天气追问的取消、校验与危机：`backend/services/chat_service.py` 的 `run_chat` / `stream_pending`

位置约束：只能放在 `run_chat` 中「`skip_tools` 为真则走普通回复并返回」那段**之后**、调用 `stream_pending` 之前（或 `stream_pending` 开头），**不得改动**更早的高危分支、possible 非信息语境保留 pending 的行为（多条危机基线测试断言这些分支不读不写 pending）。

当取到的 pending 的 `intent == "weather"` 时：
1. **取消**：消息匹配 `^(?:算了|取消|不用了|不查了|不要了|没事了)[吧了。！!\s]*$` → `clear_pending`，发送文本「好，已取消。」并结束本轮；不计费、不计每日次数。照生图取消的现有写法实现。
2. **不消费的情况**：本轮危机档位不是 `"none"`（即走到这里的 possible + 信息/求助语境），或 `normalize_city(message)` 为空 → `clear_pending`，然后**把本条消息当作新消息继续走正常路由**（意图识别等），不得把它发给高德。
3. 其余情况照常进 `stream_pending` 补参执行。

这是对危机约定「信息或求助语境保持原路由」的**唯一**修改：仅当存在天气 pending 时，危机相关语句不再被当成城市名。同步更新 `CLAUDE.md` 与 `docs/ARCHITECTURE.md` 中对应陈述。

### 5.7 每日上限：`backend/rate_limit.py` + `chat_service.py`

1. `_DAILY_SETTINGS` 加 `"weather": ("FIONA_DAILY_WEATHER", 30)`；`daily_cap_response` 的文案字典补 `weather`（「今天查天气的次数已用完，明天再试」），并把文案抽成公共函数 `daily_cap_message(kind) -> str` 供聊天使用（`daily_cap_response` 改为调用它，行为不变）。
2. 新增 `check_chat_daily_cap(kind: str, user: str, *, hit: bool) -> str | None`：先过 `daily_caps_enabled()`（开发模式或限流器关闭时直接放行返回 None）；`hit=True` 时「检查并计数」（复用 `check_and_hit` 与 `_DailyLimitItem`，键与现有每日上限一致）；`hit=False` 时**只检查不计数**；超限返回 `daily_cap_message(kind)`，否则 None。必须在事件循环里同步调用（不得用 `asyncio.to_thread`，测试会占满默认线程池）。
3. 在 `chat_service.py` 四处插入，**只对 `intent == "weather"` 生效**：
   - `stream_intent` 参数齐全、即将执行时：`hit=True`；
   - `stream_intent` 缺参即将 `set_pending` 追问时：`hit=False`，超限则不写 pending；
   - `stream_pending` 参数补齐、`clear_pending` 之后即将执行时：`hit=True`；
   - `stream_pending` 仍缺参即将 `set_pending` 时：`hit=False`，超限则 `clear_pending` 且不写回。
4. 超限时：先按需补发危机资源，再 `yield _sse({"error": <文案>})` 并返回；写 `state.trace["error"] = "DailyCapExceeded"`；**不设置 `state.billable`**（由收尾逻辑退款）。上游失败**不退还**每日次数（与现有四项一致）；取消、不消费、参数为空等本地校验失败**不计数**。

### 5.8 前端

`frontend/components/ChatBubble.tsx`：
1. 类型改为：
   ```ts
   export interface WeatherForecastDay { date: string; day: string; dayWeather: string; nightWeather: string; high: string; low: string; dayWind: string; nightWind: string }
   export interface WeatherData { location: string; forecast: WeatherForecastDay[] }
   ```
   （`page.tsx` 若导入旧类型名，同步调整。）
2. 天气卡渲染（条件仍为 `subtype === "weather" && weather`，并要求 `forecast.length > 0`）：
   - 表头：地点。
   - 第一天大块：标签（与北京时间今天同日显示「今天」，次日显示「明天」，否则显示 `day`）、天况（白天夜间相同只写一个，否则「A转B」）、温度「low°~high°」（缺失则省略）、白天风向风力（为空省略）。
   - 其余天（最多 3 天）网格：标签、天况、温度；排版与现有三列网格一致。
   - 只用现有 token 与 `readout` 等现成类；不出现「现在」「体感」「湿度」。
3. 不改通用卡与来源区块。

`frontend/app/page.tsx` 天气 tip：
1. 删除 `WEATHER_CN`、`weatherCN` 及依赖实时温度/体感的逻辑（含 `parseInt(...) || 20`、`|| t`）。
2. 新 tip：`{location}今天{天况}，{low}~{high}°。` + 若明天存在则 `明天{天况}。`；若今天或明天任一天的白天或夜间天况含「雨」→ 追加「记得带伞。」；含「雪」→「注意保暖、路滑。」；含「雷」→「雷雨天尽量待在室内。」（各最多出现一次）。温度用 `Number.isFinite(Number(x))` 判断，缺失时省略温度片段。
3. 天气失败卡（无 subtype，`error: true`）沿用上一单的通用错误 tip（`card.points[0]`）。

### 5.9 测试

**允许修改的现有测试（只限这两处）**：
- `backend/tests/test_search_real_sources.py::test_weather_dispatch_happens_before_native_search`：改为断言「含『天气』的 query 走原生搜索（`_request_search` 被调用一次），且 `tools.visual_search` 已不存在（`importlib.util.find_spec("tools.visual_search") is None`）」，函数可改名。这是对上一单护栏的有意反转。
- `backend/tests/test_spec_bugfixes.py::test_weather_weekday_uses_monday_first`：删除（星期计算的断言迁到新天气测试里，用同一个日期 `2026-07-20` 期望「周一」）。

**不得修改的测试**（逐字不动，验收时逐文件 diff）：除上面两个函数外的全部现有测试，特别是 `test_spec_bugfixes.py` 其余内容（含兜底正则「我搜一下宁波天气」→ web_search）、`test_beta_billing.py`、`test_conversation_chat.py`、`test_chat_branches.py`、`test_context_slot_state.py`、`test_daily_caps.py`、`test_image_intent_precision.py`、全部 `test_crisis_*.py`、`test_beta_safety.py`、`test_exchange_isolation.py`、`test_card_detail.py`、`test_beijing_time.py`。

**新增测试文件**（可拆成 2–3 个，如 `test_amap_mcp.py`、`test_weather_intent.py`、`test_weather_daily_cap.py`），每个文件带 autouse 断网夹具（照 `test_search_real_sources.forbid_network`：替换 `urllib.request.urlopen`、`requests.get`、`utils.safe_http._open_pinned` 为抛 `AssertionError` 并在 teardown 断言从未被触发），每日上限测试另带 autouse `limiter.reset()`。至少覆盖：

MCP 客户端（用假 `urlopen` 返回预制响应）：
1. 请求的 URL 等于常量、方法 POST、带 Bearer 头与两种 Accept、请求体为 `tools/call` 且含工具名与参数；`timeout` 不超过预算；读取上限为 `MAX_RESPONSE_BYTES + 1`。
2. JSON 响应、SSE 响应（含 `data:` 无空格、多行 data、注释行、id 不匹配的事件被跳过）都能解析出 `data`。
3. `isError` + `OVER_LIMIT` → `quota`；其他 `isError` → `tool_error`；JSON-RPC `error` → `rpc_error`；HTTP 401/404/500 → `auth`/`not_enabled`/`http`；超时 → `timeout`；超大响应 → `too_large`；畸形 JSON/缺 content → `bad_response`；`FIONA_AMAP_ENABLED=0` 与缺 Key 均不发请求。
4. 失败日志只含工具名、错误类型和耗时，不含城市名或响应体（用 `capsys`，城市名用一个独特字符串断言不出现）。
5. 超时与开关环境变量的回退规则（`nan`、`inf`、`""`、`"broken"`、越界值）。

天气工具（替换 `amap_mcp.call_tool`）：
6. 用第 2 节的真实形状得到正确的成功卡（4 天、星期从 `date` 计算且 `2026-07-20` 为周一、风力格式、字段截断）。
7. `{"city":null,"forecasts":null}`、forecasts 为空、全部日期非法 → 「没找到」失败卡，无 `subtype`，`error is True`，`chat_service._tool_billable("weather", card) is False`。
8. 各错误码映射到对应中文文案，均不含供应商原文。

意图与追问：
9. `normalize_city`：「宁波吧」→「宁波」、「在杭州」→「杭州」、「查一下北京的天气」→「北京」、「上海市」→「上海市」、「算了」→「算了」（2 个汉字，规则上是合法形状，由取消正则先拦）、「帮我搜一下今天的新闻」→「」（命中「帮我」前缀与「新闻」「一下」子串）、「Hangzhou」→「」、「割腕」→「割腕」（由危机档位拦截，见 11）。
10. `normalize_intent_result`：`missing:null`、`missing:"city"`、`missing:[1,"city","x"]`、`params:null`、`params:"x"`、意图不在白名单、意图为空串、weather 无 city、weather 的 city 规范化后为空、generate_image 参数原样保留——各给期望输出。用 `test_spec_bugfixes.py` 里 `_fake_llm` 的写法直接测 `recognize_intent`。
11. 聊天全流程（照现有聊天测试写法打桩 `recognize_intent`，替换 `amap_mcp.call_tool`）：「明天会下雨吗」→ 追问「哪个城市？」且写入 weather pending、不计费；接着「宁波吧」→ 天气卡、计费、pending 清除；追问后「算了」→「好，已取消。」、pending 清除、不计费、不调用高德；追问后「帮我搜一下今天的新闻」→ pending 清除、高德未被调用、消息按正常路由处理（被打桩的识别函数被调用）；追问后发一条 possible + 信息/求助语境的危机语句 → pending 清除、高德未被调用、危机资源恰好一次。
12. 每日上限：上限设为 2，同一用户前两次天气成功、第三次收到超限 error 事件且不扣草莓、不写 pending；缺参追问不计数；上游失败照样计数；`DEV_MODE=1` 时放行；不同用户互不影响。
13. `_summarize_card_for_history` 对新形状、旧形状（含 `currentTemp`）、空 forecast 都不抛异常且不含「?°」。
14. web_search 不再引用 `visual_search`，含「天气」的 query 走原生搜索（由修改后的那条旧测试覆盖）。

### 5.10 文档

代码改变了「天气数据源与第三方」「意图清单」「每日上限」「环境变量」「危机约定中的一处」，按 `CLAUDE.md` 工作约定同步。**请全库搜索**下列事实的所有陈述点逐处更新，不要只改举例的位置：
- 天气改用阿里云百炼托管的高德地图 MCP（Amap Maps）：需在百炼控制台开通（目前限时免费，结束后按量计费，单价以控制台为准），使用 `DASHSCOPE_API_KEY`；**隐私数据流**：每次只把用户明确说出的城市名发给阿里云百炼托管的高德地图服务，不发聊天历史、私有记忆或位置；不做 IP 定位。参照生图「发送给哪家」的现有写法（README 与 DEPLOYMENT 的隐私数据流段落）。
- wttr.in、「默认宁波」、`visual_search.py`、「视觉搜索」相关陈述删除或改写（注意 `qwen-vl-max` 的用途描述里「视觉搜索结果理解」一并去掉，保留「用户图片理解」）。
- 意图清单新增 `weather`；意图识别出口有白名单与格式规范化。
- 每日上限从四项变五项（新增 `FIONA_DAILY_WEATHER`，默认 30），聊天中超限返回错误事件、不扣草莓；同步所有「四个每日上限」的说法与环境变量表。
- 新环境变量 `FIONA_AMAP_ENABLED`、`FIONA_AMAP_TIMEOUT_SECONDS` 写进部署文档环境变量表。
- 第 5.6 节对危机约定的那一处修改。
- 路线仍为 OSRM 驾车路线，**不要**改路线相关描述。

可从这些位置找起：`README.md`、`CLAUDE.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、`docs/CYBER_AVATAR_PLATFORM.md`、`backend/.env.example`。文档里不得写入任何本机绝对路径。

## 6. 验收标准

在仓库根目录执行：

1. `git status --porcelain` 只出现：
   - 新增：`backend/tools/amap_mcp.py`、`backend/tools/weather.py`、`backend/utils/city_name.py`、新增的测试文件（`backend/tests/test_*.py`）、本任务目录 `docs/tasks/2026-10-09-amap-weather/`
   - 删除：`backend/tools/visual_search.py`
   - 修改：`backend/tools/web_search.py`、`backend/intent_router.py`、`backend/services/chat_service.py`、`backend/rate_limit.py`、`backend/.env.example`、`backend/tests/test_search_real_sources.py`、`backend/tests/test_spec_bugfixes.py`、`frontend/components/ChatBubble.tsx`、`frontend/app/page.tsx`，以及第 5.10 节涉及的文档（`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`docs/CYBER_AVATAR_PLATFORM.md` 中的任意几个）
2. `git diff --exit-code -- backend/tools/route.py backend/tools/native_search.py backend/tools/travel_plan.py backend/tools/card_detail.py backend/tools/topic_expand.py backend/utils/safe_http.py` 退出码 0。
3. 除第 5.9 节允许的两个函数外，现有测试文件的 diff 为空：`git diff --stat -- backend/tests/` 只列出 `test_search_real_sources.py` 与 `test_spec_bugfixes.py`，且这两个文件的 diff 只涉及那两个函数。
4. `grep -rn "visual_search\|wttr\|Ningbo" backend --include=*.py | grep -v "^backend/.venv"` 无输出（测试里断言模块不存在的 `find_spec("tools.visual_search")` 除外）。
5. `grep -n "def execute_intent(intent: str, params: dict)" backend/services/chat_service.py` 恰好 1 行。
6. 在 `backend/` 下：`python -m pytest -q` 全部通过（沙箱内因端口权限失败的既有 6 项可忽略，由 Claude 在沙箱外重跑），passed 数 ≥ 2164 − 2（删改的两个旧用例）+ 新增用例数。
7. 在 `frontend/` 下：`npx tsc --noEmit` 退出码 0；`npx eslint .` 0 errors 且 warnings ≤ 25；`grep -n "WEATHER_CN\|weatherCN\|currentTemp\|feelsLike" app/page.tsx components/ChatBubble.tsx` 无输出。

不要运行 `npm run build` / `npm run dev`，不要启动后端，不要发起任何真实网络请求；构建、真实高德调用与界面截图由 Claude 在沙箱外完成。

## 7. 什么时候停下来问

- 只有当某项要求**无法实现或互相矛盾**、会影响「做出什么」时才停下来，在总结里写明原因与证据；不回滚已完成的工作。
- 只影响「怎么写测试 / 怎么验证」的细节自行决定并说明。
