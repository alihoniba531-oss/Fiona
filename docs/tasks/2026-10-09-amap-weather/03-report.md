# 高德地图 MCP 天气实现报告

规格：[02-spec.md](./02-spec.md)，修订：[05-fix-r1.md](./05-fix-r1.md)、[06-fix-r2.md](./06-fix-r2.md)。基线：`main` @ `9857846`。日期：2026-10-09。

**R1 与 R2 已完成。** R1 原三条失败用例的输入和期望未改，持续通过；R2 修复天气失败卡覆盖危机资源、上游空城市与 SSE 分行，补齐追问路径的每日额度回归及反向验证。最新三个新增测试文件联合结果为 `265 passed, 11 warnings in 1.30s`，退出码 `0`；最新全量为 `1 failed, 2422 passed, 11 warnings, 5 errors in 57.62s`，退出码 `1`，六项均为原规格允许的既有端口用例，由离线护栏在真实监听前阻止。TypeScript 退出 `0`，ESLint 为 `0 errors / 25 warnings`、退出 `0`。第 4、6 节保留首次与 R1 验收历史；R2 当前逐项结论及全部实际输出见第 7 节。

## 1. 文件变更与分工

使用四个子代理按文件独占实现，派发时均未传 `model` 或 `reasoning_effort`。根代理负责交叉复核、统一验收和本报告；没有多人编辑同一实现文件。

| 文件 | 状态 | 负责分工与改动 |
|---|---|---|
| `backend/tools/amap_mcp.py` | 新增 | MCP/天气子代理；固定端点、无状态 POST、JSON/SSE、总预算及安全错误映射 |
| `backend/tools/weather.py` | 新增 | MCP/天气子代理；中文四日预报卡、字段校验、固定错误卡 |
| `backend/utils/city_name.py` | 新增 | MCP/天气子代理；共享纯函数城市规范化；R1 在形状校验前拒绝指定句式，剥离保护剩余两字 |
| `backend/tests/test_amap_mcp.py` | 新增 | MCP/天气子代理；首轮 93 个，R1 增至 160 个，R2 增至 170 个参数化离线用例 |
| `backend/tools/web_search.py` | 修改 | MCP/天气子代理；只删除旧天气分流与对应文件头说明 |
| `backend/tools/visual_search.py` | 删除 | MCP/天气子代理；全库搜索确认没有其他业务调用方后删除 |
| `backend/tests/test_search_real_sources.py` | 修改 | MCP/天气子代理；仅改获准天气函数，验证原生搜索调用一次及旧模块不存在 |
| `backend/tests/test_spec_bugfixes.py` | 修改 | MCP/天气子代理；仅删除获准的旧天气星期测试，日期断言迁入新测试 |
| `backend/intent_router.py` | 修改 | 意图/聊天/限额子代理；weather 提示词、city 补参及识别出口规范化 |
| `backend/services/chat_service.py` | 修改 | 意图/聊天/限额子代理；天气分派、计费、摘要、pending 路由及四处每日检查 |
| `backend/rate_limit.py` | 修改 | 意图/聊天/限额子代理；weather 每日限额、公共文案和同步检查 |
| `backend/tests/test_weather_intent.py` | 新增 | 意图/聊天/限额子代理；识别、聊天、取消、危机、计费和历史摘要测试 |
| `backend/tests/test_weather_daily_cap.py` | 新增 | 意图/聊天/限额子代理；额度、账户隔离、同步检查及危机资源顺序测试；两个新文件首轮合计 75 用例，R1 增至 94 用例，R2 增至 95 用例 |
| `frontend/components/ChatBubble.tsx` | 修改 | 前端子代理；新天气类型、北京时间标签、首日详情及其余三天网格 |
| `frontend/app/page.tsx` | 修改 | 前端子代理；中文天气 tip、雨雪雷提醒及缺失温度处理 |
| `README.md` | 修改 | 文档子代理；当前能力、第三方隐私数据流、意图、限额和危机例外 |
| `CLAUDE.md` | 修改 | 文档子代理；开发约束、天气配置、五项每日上限和危机例外 |
| `PLAN.md` | 修改 | 文档子代理；当前实现与边界，移除旧天气分流/视觉搜索陈述 |
| `docs/ARCHITECTURE.md` | 修改 | 文档子代理；天气数据流、出口规范化、每日额度、卡片摘要和危机例外 |
| `docs/DEPLOYMENT.md` | 修改 | 文档子代理；开通、费用、环境变量、隐私数据流及人工验收 |
| `docs/CYBER_AVATAR_PLATFORM.md` | 修改 | 文档子代理；当前内置天气能力、额度、配置及危机例外 |
| `backend/.env.example` | 修改 | 文档子代理；追加规定三变量和中文注释，补原生联网超时例外 |
| `docs/tasks/2026-10-09-amap-weather/03-report.md` | 新增 | 根代理；变更、逐项对照、实际验收输出及未完成事项 |

首轮合计新增 7 个文件、修改 15 个文件、删除 1 个文件。任务目录及 `02-spec.md` 在开始时已经是未跟踪状态；首轮未改写规格，R1 按作者修订仅修正 5.9.9 的一句说明。R1 五个修改文件另列于第 6 节，R2 七个修改文件另列于第 7 节。六个受保护实现文件、其他现有测试、既有环境变量值和路线相关描述均保持不变。

## 2. 已实现功能

- 独立 `weather` 意图和“哪个城市？”追问；不默认城市、不读画像城市、不做 IP 定位。
- 百炼托管高德 `maps_weather` 调用，只发送规范化城市；中文四日预报，校验日期、温度、风向风力及字段长度。
- JSON 与 SSE 响应处理、请求 id 匹配、大小上限、超时总预算、固定错误码和无原文失败日志。
- 天气成功卡计费；失败卡、取消、追问和每日超限退款。上游失败仍消耗每日查询次数。
- 天气 pending 取消、规范化结果为空时转新消息，以及 possible 信息/求助语境的专门拦截；天气失败先发送 card，再由保存逻辑追加一次危机资源 text；每日超限 error 仍先发送资源。保存摘要中资源均恰好一次。
- 五项每日上限中的新天气额度，默认每账号每个北京时间自然日 30 次；缺参只检查，实际执行检查并计数，事件循环内同步执行。
- 意图识别出口对白名单、参数和 missing 做规范化；白名单只在 `recognize_intent` 内部生效，原搜索正则、生图原文和 pending 持久化层保持不变。
- 新前端天气卡、北京时间今天/明天/星期标签、中文雨雪雷提醒，移除实时/体感/湿度与英文天气翻译。
- 删除旧视觉搜索实现；普通搜索中的“天气”不再触发专用分流；同步现行文档与配置模板。

**R1 已修复的产品场景：** 天气追问后回复“帮我搜一下今天的新闻”，现在拒绝把该句当城市，清除天气 pending 后重新识别并执行搜索；原聊天测试确认假高德未被调用。所有测试均离线，没有真实请求。

## 3. 与规格 5.1–5.10 逐项对应

| 规格 | 实现与验证 | 当前状态 |
|---|---|---|
| 5.1 MCP 客户端 | `amap_mcp.call_tool` 使用模块属性 `urllib.request.urlopen`，固定 URL/POST/Bearer/Accept/唯一整数 id；调用时读开关、Key、1–30 秒预算；限量读取、JSON/SSE、RPC/HTTP/额度/超时处理，SSE 仅按 CRLF/CR/LF 分行并保留字符串内 U+2028；不握手、不引入依赖、不读取 HTTP 错误体 | 完成；对应离线用例通过 |
| 5.2 天气工具 | 共享 `normalize_city`，模块名字调用 `amap_mcp.call_tool`；固定无 subtype 错误卡；最多四个有效日期、按日期算星期、字符串截 20 字、温度/风力校验，空 forecasts 不计费；上游城市去空白后为空或非字符串时回退规范化用户城市 | 完成；`2026-07-20` 为周一的断言迁入新测试 |
| 5.3 移除旧分流 | `web_search` 仅删除规定分流和旧说明；删除 `visual_search.py`，全库业务调用方检索为空；旧护栏反转为原生搜索调用一次 | 完成；grep 仅剩获准 `find_spec` 断言 |
| 5.4 意图与规范化 | weather 清单、正反例、城市来源约束、city 提问/补参、识别出口允许键/missing 去重；generate_image 参数原样保留；不改变 fallback 或槽位载荷 | 完成；按 R1 在重复剥离后增加精确拒绝规则，原新闻参数空串断言通过 |
| 5.5 分派、计费、摘要 | 保留 execute_intent 双参数签名；weather 成功计费/失败退款；新旧天气形状与空 forecast 均安全摘要，不产生 `?°` | 完成；新旧卡、失败计费及聊天结算测试通过，R2 失败卡先 card 后资源且落库一致 |
| 5.6 追问与危机 | 逻辑放在 skip_tools 返回之后；取消清 pending，不计费；规范化为空/possible 信息求助清 pending 后按新消息路由；更早 high/possible 非信息语境行为不变 | 完成；R1 后原新闻例句按新消息路由，取消、危机及其他无效形状均通过 |
| 5.7 每日上限 | `FIONA_DAILY_WEATHER=30`、公共文案、同步检查；direct/pending 完整参数 hit=True、缺参 hit=False 共四处；超限 trace/error/退款/不写 pending，资源一次 | 完成；额度 2、失败计数、逐用户、开发模式、午夜换日、动态额度及默认池占满测试通过；R2 新增同账号三会话追问补齐计数，并以 hit=False 反向验证变红 |
| 5.8 前端 | 新 WeatherForecastDay/WeatherData；非空预报、首日详情、其余最多三天、现有 tokens/classes；新中文 tip 与缺失温度处理；通用卡/来源不改 | 完成；tsc 退出 0，ESLint 0 errors/25 warnings，旧字段 grep 无输出 |
| 5.9 测试 | 新增三个文件首轮共 168 用例，R1 增至 254、R2 增至 265 用例；每个 autouse 阻断 urllib/requests/safe_http，额度文件 reset limiter；原仓库测试仅改获准两函数，R2 仅调整增补点名的失败卡顺序测试 | 265 个新增用例全部通过；全量只剩规格允许的 6 个旧端口用例 |
| 5.10 文档 | 六份现行文档与 env 同步天气源、开通/费用/隐私、意图规范化、五项额度、配置和危机唯一例外；旧模型视觉搜索用途移除；路线描述不改 | 完成；现行旧事实检索无匹配，原 12 个 env 变量值逐字不变 |

全库搜索已覆盖历史任务文档；其中旧规格、实现报告和评审记录作为历史证据保留，第 6.1 节也未授权改写其他任务目录。现行说明的过时事实已逐处更新。

## 4. 首次验收历史记录：第 6 节每条命令的实际输出与退出码（R1 前）

所有命令在规格指定目录执行。后端预先把已有 `.venv/bin` 加入 PATH，使原命令 `python -m pytest -q` 可用；通过仓库外临时 `sitecustomize` 审计钩子在系统调用前拒绝 INET socket 监听、连接与真实 DNS，未修改任何既有测试或夹具。新增测试另有规格要求的 autouse 断网夹具。前端设置 npm 离线环境后使用本地已安装的工具，未安装依赖。

未启动后端，未执行 `npm run build` / `npm run dev`，未调用真实高德或其他外部服务。下面完整保留命令输出，只将仓库根路径改为相对路径、Homebrew 标准库路径替换为 `<Python标准库>/`、临时护栏目录替换为 `<临时离线护栏>/`，避免文档出现本机绝对路径；错误正文、警告、行号、计数与退出码均为实际结果。

### 6.1 修改范围

目录：仓库根目录。

```bash
git status --porcelain
```

实际输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/intent_router.py
 M backend/rate_limit.py
 M backend/services/chat_service.py
 M backend/tests/test_search_real_sources.py
 M backend/tests/test_spec_bugfixes.py
 D backend/tools/visual_search.py
 M backend/tools/web_search.py
 M docs/ARCHITECTURE.md
 M docs/CYBER_AVATAR_PLATFORM.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
?? backend/tests/test_amap_mcp.py
?? backend/tests/test_weather_daily_cap.py
?? backend/tests/test_weather_intent.py
?? backend/tools/amap_mcp.py
?? backend/tools/weather.py
?? backend/utils/city_name.py
?? docs/tasks/2026-10-09-amap-weather/
```

退出码：`0`。

输出均在规格白名单内；报告新增仍归入已列出的本任务目录。

### 6.2 六个受保护实现文件

目录：仓库根目录。

```bash
git diff --exit-code -- backend/tools/route.py backend/tools/native_search.py backend/tools/travel_plan.py backend/tools/card_detail.py backend/tools/topic_expand.py backend/utils/safe_http.py
```

实际输出：

无输出。

退出码：`0`。

### 6.3 现有测试文件 diff 统计

目录：仓库根目录。

```bash
git diff --stat -- backend/tests/
```

实际输出：

```text
 backend/tests/test_search_real_sources.py | 19 ++++++-------------
 backend/tests/test_spec_bugfixes.py       | 30 ------------------------------
 2 files changed, 6 insertions(+), 43 deletions(-)
```

退出码：`0`。

### 6.3 补充：两文件逐函数 diff

目录：仓库根目录。

```bash
git diff -- backend/tests/test_search_real_sources.py backend/tests/test_spec_bugfixes.py
```

实际输出：

```text
diff --git a/backend/tests/test_search_real_sources.py b/backend/tests/test_search_real_sources.py
index 4b9b25a..ca82f57 100644
--- a/backend/tests/test_search_real_sources.py
+++ b/backend/tests/test_search_real_sources.py
@@ -265,24 +265,17 @@ def test_surrounding_prose_is_tolerated_and_raw_is_preserved(monkeypatch):
     assert card["error"] is False
 
 
-def test_weather_dispatch_happens_before_native_search(monkeypatch):
-    from tools import visual_search
+def test_weather_query_uses_native_search_and_legacy_module_is_removed(monkeypatch):
+    import importlib.util
 
-    weather_card = {"type": "card", "subtype": "weather", "source": "宁波", "points": ["晴"]}
-    weather_calls = []
-
-    def weather(query):
-        weather_calls.append(query)
-        return weather_card
-
-    monkeypatch.setattr(visual_search, "_search_weather_direct", weather)
     calls = _stub(monkeypatch, _payload())
 
     card = web_search.web_search("  宁波天气  ")
 
-    assert card is weather_card
-    assert weather_calls == ["宁波天气"]
-    assert calls == []
+    assert card["error"] is False
+    assert len(calls) == 1
+    assert calls[0][0][-1]["content"] == "搜索：宁波天气"
+    assert importlib.util.find_spec("tools.visual_search") is None
 
 
 def test_grounded_search_copies_provider_sources(monkeypatch):
diff --git a/backend/tests/test_spec_bugfixes.py b/backend/tests/test_spec_bugfixes.py
index 8d08983..97a9212 100644
--- a/backend/tests/test_spec_bugfixes.py
+++ b/backend/tests/test_spec_bugfixes.py
@@ -222,36 +222,6 @@ def test_latest_match_decision_wins(tmp_path, monkeypatch):
     assert asyncio.run(scenario()) == []
 
 
-def test_weather_weekday_uses_monday_first(monkeypatch):
-    import requests
-    from tools.visual_search import _search_weather_direct
-
-    payload = {
-        "current_condition": [{
-            "weatherDesc": [{"value": "晴"}],
-            "temp_C": "28",
-            "FeelsLikeC": "29",
-        }],
-        "weather": [{
-            "date": "2026-07-20",
-            "maxtempC": "30",
-            "mintempC": "22",
-            "hourly": [{}, {}, {}, {}, {"weatherDesc": [{"value": "晴"}]}],
-        }],
-    }
-
-    class _Response:
-        def raise_for_status(self):
-            return None
-
-        def json(self):
-            return payload
-
-    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _Response())
-    card = _search_weather_direct("宁波天气")
-    assert card["weather"]["forecast"][0]["day"] == "周一"
-
-
 def test_peer_manager_keeps_each_socket_independent():
     from routers.peer import ConnectionManager
 
```

退出码：`0`。

### 6.4 旧天气/视觉搜索引用

目录：仓库根目录。

```bash
grep -rn "visual_search\|wttr\|Ningbo" backend --include=*.py | grep -v "^backend/.venv"
```

实际输出：

```text
backend/tests/test_search_real_sources.py:278:    assert importlib.util.find_spec("tools.visual_search") is None
```

退出码：`0`。

唯一命中是规格明确允许的旧模块不存在断言，因此本项满足；管道实际退出码为 0，不能记录成无匹配的 1。

### 6.5 execute_intent 签名

目录：仓库根目录。

```bash
grep -n "def execute_intent(intent: str, params: dict)" backend/services/chat_service.py
```

实际输出：

```text
232:def execute_intent(intent: str, params: dict):
```

退出码：`0`。

### 6.6 全量后端测试

目录：`backend/`。

```bash
python -m pytest -q
```

实际输出：

```text
........................................................................ [  3%]
.................................................................F...... [  6%]
........................................................................ [  9%]
........................................................................ [ 12%]
........................................................................ [ 15%]
........................................................................ [ 18%]
........................................................................ [ 21%]
........................................................................ [ 24%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 37%]
........................................................................ [ 40%]
........................................................................ [ 43%]
........................................................................ [ 46%]
........................................................................ [ 49%]
....................EF.................................................. [ 52%]
........................................................................ [ 55%]
........................................................................ [ 58%]
........................................................................ [ 61%]
........................................................................ [ 64%]
........................................................................ [ 67%]
........................................................................ [ 71%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................EEE.E........... [ 80%]
........................................................................ [ 83%]
........................................................................ [ 86%]
........................................................................ [ 89%]
........................................................................ [ 92%]
........................................................................ [ 95%]
......................................................F................. [ 98%]
................F..........                                              [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10b74eb30>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10b1dac10>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10b156200>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1076b6970>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10b1daa50>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
=================================== FAILURES ===================================
_ test_normalize_city_pure_shape_rules[\u5e2e\u6211\u641c\u4e00\u4e0b\u4eca\u5929\u7684\u65b0\u95fb-] _

raw = '帮我搜一下今天的新闻', city = ''

    @pytest.mark.parametrize("raw,city", [
        ("宁波吧", "宁波"), ("在杭州", "杭州"), ("查一下北京的天气", "北京"),
        ("上海市", "上海市"), ("算了", "算了"), ("帮我搜一下今天的新闻", ""),
        ("Hangzhou", ""), ("割腕", "割腕"), (" \t「换成那杭州的天气吧呢！」\n", "杭州"),
        ("是就去查一下北京啊呀的", "北京"), ("查一下，一二三四五六七八九十的天气", "一二三四五六七八九十"),
        ("一二三四五六七八九十一", ""), ("杭", ""), ("杭州123", ""), ("杭 州", ""),
        ("", ""), (None, ""), (123, ""), ("城市😀", ""),
    ])
    def test_normalize_city_pure_shape_rules(raw, city):
>       assert normalize_city(raw) == city
E       AssertionError: assert '帮我搜一下今天的新闻' == ''
E         
E         + 帮我搜一下今天的新闻

tests/test_amap_mcp.py:343: AssertionError
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x10bf3f350>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10b721be0>

    def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
        import services.exchange_service as service
    
        async def start_server():
            entered, disconnected = asyncio.Event(), asyncio.Event()
    
            async def handler(reader, writer):
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                    length = 0
                    for line in headers.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1].strip())
                    if length:
                        await reader.readexactly(length)
                    entered.set()
                    await reader.read(1)
                    disconnected.set()
                finally:
                    writer.close()
                    await writer.wait_closed()
    
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            return server, entered, disconnected
    
        async def wait_event(event):
            await asyncio.wait_for(event.wait(), timeout=5)
    
>       server, entered, disconnected = client.portal.call(start_server)
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_exchange_isolation.py:151: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x10c7d3530>
host = '127.0.0.1', port = 0, family = <AddressFamily.AF_UNSPEC: 0>
flags = <AddressInfo.AI_PASSIVE: 1>
sock = <socket.socket [closed] fd=-1, family=2, type=1, proto=6>, backlog = 100
ssl = None, reuse_address = True, reuse_port = None, keep_alive = None
ssl_handshake_timeout = None, ssl_shutdown_timeout = None, start_serving = True

    async def create_server(
            self, protocol_factory, host=None, port=None,
            *,
            family=socket.AF_UNSPEC,
            flags=socket.AI_PASSIVE,
            sock=None,
            backlog=100,
            ssl=None,
            reuse_address=None,
            reuse_port=None,
            keep_alive=None,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
            start_serving=True):
        """Create a TCP server.
    
        The host parameter can be a string, in that case the TCP server is
        bound to host and port.
    
        The host parameter can also be a sequence of strings and in that
        case the TCP server is bound to all hosts of the sequence.  If
        a host appears multiple times (possibly indirectly e.g. when
        hostnames resolve to the same IP address), the server is only bound
        once to that host.
    
        Return a Server object which can be used to stop the service.
    
        This method is a coroutine.
        """
        if isinstance(ssl, bool):
            raise TypeError('ssl argument must be an SSLContext or None')
    
        if ssl_handshake_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_handshake_timeout is only meaningful with ssl')
    
        if ssl_shutdown_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_shutdown_timeout is only meaningful with ssl')
    
        if sock is not None:
            _check_ssl_socket(sock)
    
        if host is not None or port is not None:
            if sock is not None:
                raise ValueError(
                    'host/port and sock can not be specified at the same time')
    
            if reuse_address is None:
                reuse_address = os.name == "posix" and sys.platform != "cygwin"
            sockets = []
            if host == '':
                hosts = [None]
            elif (isinstance(host, str) or
                  not isinstance(host, collections.abc.Iterable)):
                hosts = [host]
            else:
                hosts = host
    
            fs = [self._create_server_getaddrinfo(host, port, family=family,
                                                  flags=flags)
                  for host in hosts]
            infos = await tasks.gather(*fs)
            infos = set(itertools.chain.from_iterable(infos))
    
            completed = False
            try:
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    try:
                        sock = socket.socket(af, socktype, proto)
                    except socket.error:
                        # Assume it's a bad family/type/protocol combination.
                        if self._debug:
                            logger.warning('create_server() failed to create '
                                           'socket.socket(%r, %r, %r)',
                                           af, socktype, proto, exc_info=True)
                        continue
                    sockets.append(sock)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                    # Since Linux 6.12.9, SO_REUSEPORT is not allowed
                    # on other address families than AF_INET/AF_INET6.
                    if reuse_port and af in (socket.AF_INET, socket.AF_INET6):
                        _set_reuseport(sock)
                    if keep_alive:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
                    # Disable IPv4/IPv6 dual stack support (enabled by
                    # default on Linux) which makes a single socket
                    # listen on both address families.
                    if (_HAS_IPv6 and
                            af == socket.AF_INET6 and
                            hasattr(socket, 'IPPROTO_IPV6')):
                        sock.setsockopt(socket.IPPROTO_IPV6,
                                        socket.IPV6_V6ONLY,
                                        True)
                    try:
                        sock.bind(sa)
                    except OSError as err:
                        msg = ('error while attempting '
                               'to bind on address %r: %s'
                               % (sa, str(err).lower()))
                        if err.errno == errno.EADDRNOTAVAIL:
                            # Assume the family is not enabled (bpo-30945)
                            sockets.pop()
                            sock.close()
                            if self._debug:
                                logger.warning(msg)
                            continue
>                       raise OSError(err.errno, msg) from None
E                       OSError: [Errno None] error while attempting to bind on address ('127.0.0.1', 0): weather task offline guard: real network disabled

<Python标准库>/asyncio/base_events.py:1637: OSError
_ test_city_normalization[\u5e2e\u6211\u641c\u4e00\u4e0b\u4eca\u5929\u7684\u65b0\u95fb-] _

message = '帮我搜一下今天的新闻', expected = ''

    @pytest.mark.parametrize("message,expected", [
        ("宁波吧", "宁波"), ("在杭州", "杭州"), ("查一下北京的天气", "北京"),
        ("上海市", "上海市"), ("算了", "算了"), ("帮我搜一下今天的新闻", ""),
        ("Hangzhou", ""), ("割腕", "割腕"), (" ！那在查一下杭州的天气呢吧。 ", "杭州"),
        (None, ""), (123, ""), ("京", ""), ("杭 州", ""),
    ])
    def test_city_normalization(message, expected):
>       assert normalize_city(message) == expected
E       AssertionError: assert '帮我搜一下今天的新闻' == ''
E         
E         + 帮我搜一下今天的新闻

tests/test_weather_intent.py:42: AssertionError
____________ test_weather_followup_noncity_is_routed_as_new_message ____________

client = <starlette.testclient.TestClient object at 0x10d0916a0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10aef4520>
weather_calls = [('maps_weather', {'city': '帮我搜一下今天的新闻'})]

    def test_weather_followup_noncity_is_routed_as_new_message(client, dev_headers, monkeypatch, weather_calls):
        import services.chat_service as chat
    
        user, key, send = _production_chat(client, dev_headers, monkeypatch)
        intent_router.set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
        recognized = []
        searches = []
    
        def classify(_client, message, _history):
            recognized.append(message)
            return {"intent": "web_search", "params": {"query": "今天的新闻"}, "missing": []}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "web_search", lambda query: searches.append(query) or {"type": "card", "source": "搜索", "points": ["离线新闻"]})
        assert any(event.get("card") for event in send("帮我搜一下今天的新闻"))
>       assert recognized == ["帮我搜一下今天的新闻"]
E       AssertionError: assert [] == ['帮我搜一下今天的新闻']
E         
E         Right contains one more item: '帮我搜一下今天的新闻'
E         Use -v to get more diff

tests/test_weather_intent.py:195: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=10, detected_count=0
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_amap_mcp.py::test_normalize_city_pure_shape_rules[\u5e2e\u6211\u641c\u4e00\u4e0b\u4eca\u5929\u7684\u65b0\u95fb-]
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
FAILED tests/test_weather_intent.py::test_city_normalization[\u5e2e\u6211\u641c\u4e00\u4e0b\u4eca\u5929\u7684\u65b0\u95fb-]
FAILED tests/test_weather_intent.py::test_weather_followup_noncity_is_routed_as_new_message
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
4 failed, 2322 passed, 11 warnings, 5 errors in 59.06s
```

退出码：`1`。

收集结果：新增 `168 tests collected`，全库 `2331 tests collected`，两个收集命令均退出 `0`（此处仅记录计数摘录，完整全量执行输出已在上方列出）。基线 2164 个用例，删掉一个旧天气星期用例，另一个旧天气用例改写后仍保留，所以实际总数为 `2164 - 1 + 168 = 2331`；高于规格最低数量 `2164 - 2 + 168 = 2330`。

首次验收当时 2322 个通过，剩余 9 个结果由 3 个新增新闻句冲突失败和 6 个旧端口失败/错误组成。当时第 6.6 项尚未满足；此段保留原始事实，最新 R1 结果见第 6 节。

### 6.7 前端 TypeScript

目录：`frontend/`。

```bash
npx tsc --noEmit
```

实际输出：

无输出。

退出码：`0`。

### 6.7 前端 ESLint

目录：`frontend/`。

```bash
npx eslint .
```

实际输出：

```text

frontend/app/page.tsx
   143:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   234:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   392:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   445:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   446:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   447:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   457:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   458:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   459:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   460:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   463:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   469:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   470:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   774:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   868:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1292:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1312:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1320:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1341:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1383:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1479:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1815) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1914:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1954:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2224:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
```

退出码：`0`。

### 6.7 前端旧天气字段

目录：`frontend/`。

```bash
grep -n "WEATHER_CN\|weatherCN\|currentTemp\|feelsLike" app/page.tsx components/ChatBubble.tsx
```

实际输出：

无输出。

退出码：`1`。

无匹配时 grep 退出 1，属于本项的预期通过结果。

### 补充范围与兼容性复核

逐文件比较 73 个已有测试文件，只有两个获准天气函数发生变化；其他测试逐字不动。移除两天气函数后两个文件的剩余字节也与 HEAD 一致。六个受保护实现文件逐字相同；pending 持久化函数 AST 相同。临时只读校验实际输出：

```text
PASS: 73 tracked test files are unchanged outside the two permitted weather functions.
PASS: all six protected implementation files are byte-identical to HEAD.
PASS: pending persistence function syntax is unchanged.
```

退出码：`0`。`git diff --check` 实际无输出，退出码 `0`。另作只读校验确认搜索 fallback 函数及 execute_intent 原双参数不变，原 12 个 env 变量值逐字相同；只新增三项指定配置，退出码 `0`。

## 5. 未完成与需要人工确认

1. **原城市校验冲突已按规格修订 R1 处理，不再等待裁决。** 作者已明确产品场景优先，`normalize_city` 在重复剥离后、形状检查前按 R1 精确拒绝 25 个前缀和 9 个子串；剥离剩余不足 2 字时保留，八个真实地名含“那曲”保持原样。原三条失败用例的输入和期望均未修改，现已通过。修订说明及实际验收见第 6 节。
2. **6 个既有端口用例需沙箱外重跑。** 本轮离线护栏在真实监听发生前抛 PermissionError，避免任何真实网络；与规格列出的端口受限六项相同：exchange 的八个慢请求隔离及停止断连两项，safe_http 的滴流响应、快速重定向、滴流头和四个阻塞解析隔离四项。没有改动这些受保护测试，也没有绕过网络禁止要求。
3. **真实集成、构建与视觉验收按规格留给 Claude。** 百炼 Amap Maps 实际开通/Key 权限、真实高德返回、生产退款和额度、前端构建与界面截图尚未执行。提供方免费期/结束后的计费单价以百炼控制台为准；本轮没有联网查询或验证这些外部状态。

没有提交 Git commit，没有新增依赖，没有修改其他受保护文件，也没有更改路线实现。R1 与 R2 的代码及离线验收已完成；R2 具体结果见第 7 节。仍保留上述六个既有端口用例、真实接口、构建和截图的人工验收项，不能把全量退出码 1 表述为全部通过。

## 6. 规格修订 R1

依据：[05-fix-r1.md](./05-fix-r1.md)。原冲突已由规格作者裁决，以产品场景为准；其余 `02-spec.md` 条款不变。继续使用原文件负责人并行处理，没有传 `model` 或 `reasoning_effort`，未回滚此前已完成工作。

### 本次修改的文件

| 文件 | 本次改动 |
|---|---|
| `backend/utils/city_name.py` | 25 项字面前缀和 9 项子串拒绝；每次剥离候选不足 2 字不剥；先重复剥完后缀再处理前缀，保留“那曲啊的天气”等多重后缀场景 |
| `backend/tests/test_amap_mcp.py` | 新增 67 个 R1 参数化用例：8 地名、6 拒绝句、全部 25 前缀、全部 9 子串、19 剥离/最短长度护栏；93 → 160 用例 |
| `backend/tests/test_weather_intent.py` | 仅补新闻句解释注释和 19 个 R1 用例：8 地名、6 拒绝句、5 正常剥离；50 → 69 用例 |
| `docs/tasks/2026-10-09-amap-weather/02-spec.md` | 按 R1 测试修订第 1 条，仅将 5.9.9 新闻句说明从“超过 10 字”改为命中“帮我”前缀与“新闻”“一下”子串，例句和空串期望不变 |
| `docs/tasks/2026-10-09-amap-weather/03-report.md` | 第 5 节改为冲突已处理，更新当前结论和逐项状态；保留首次实际输出，并末尾追加本 R1 节全部验收记录 |

本次未新增或删除文件。`test_weather_daily_cap.py` 没有改动，仍执行其 25 个用例；`05-fix-r1.md` 为作者提供的修订，未改写。

### R1 各条落实情况

| 修订条款 | 落实与证据 |
|---|---|
| 城市规则 1：规定字面前缀 | 原样加入全部 25 项，在重复剥离稳定后、2–10 汉字检查前用字面 startswith 拒绝；新增全名单、多轮剥离用例 |
| 城市规则 2：规定子串 | 原样加入全部 9 项，任何位置包含即拒绝；新增全名单、多轮剥离用例 |
| 不加入误伤地名的单字拒绝 | 未增加“来/什/顺/可/新/闻/会/那”等单字拒绝；原可剥前缀“那”和其他剥离名单不变，8 个真实地名全部原样通过 |
| 测试修订 1：新闻句说明 | `02-spec.md` 5.9.9 仅改解释，测试增加解释注释；原新闻输入及空串期望逐字保留 |
| 测试修订 2：真实地名与最短剥离 | 来宾、什邡、顺义、可克达拉、新乡、闻喜、会理、那曲在两个城市测试文件均新增参数化断言；每次剥离候选不足两字不剥，正常“那上海呢”仍为上海 |
| 测试修订 3：六个拒绝句 | 两个城市测试文件均覆盖六句原输入，全部期望空串并通过；“我在杭州”按保守取舍拒绝 |
| 测试修订 4：原三条用例不可改 | 原两个城市参数组的全部输入与期望 AST 相同，原新闻聊天函数源码相同；三个原失败用例均通过，新闻按新路由处理且不调用假高德 |
| 验收：原第 6 节全部条目及三文件联合 | 各命令重新执行，原六个端口限制例外之外通过；三文件单独与联合均通过，具体输出见下方 |
| 验收：追加报告并更新第 5 节 | 已更新第 5 节与顶部当前结论，原验收作为历史保留，本节追加结论与全部新输出 |

先将允许后缀重复剥离到稳定，再处理前缀，避免“那曲吧”或“那曲啊的天气”在后缀未剥尽时先失去“那”。这是实现剥离保护的处理顺序，原前后缀名单没有扩大；没有查询城市库或引入新依赖。

R1 额外新增 `67 + 19 = 86` 个用例，三个新增测试文件合计 `160 + 69 + 25 = 254`。实际全量总数为 `2411 passed + 1 failed + 5 errors = 2417`，等于 `2164 - 1 + 254`，高于规格最低总量 `2164 - 2 + 254 = 2416`。六个端口受限旧用例以外全部通过；原三项城市冲突失败已消失。

### R1 验收命令实际输出与退出码

继续使用已有后端虚拟环境、仓库外离线 socket 审计护栏和新增文件的 autouse 断网夹具。npm 设置离线模式，所有工具使用已安装版本。没有安装依赖、启动后端、执行 build/dev 或发起真实网络请求。输出仅按第 4 节相同规则去除本机绝对路径，计数、文案、警告、行号和退出码保持实际。

#### 原 6.1：修改范围

目录：仓库根目录。

```bash
git status --porcelain
```

实际输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/intent_router.py
 M backend/rate_limit.py
 M backend/services/chat_service.py
 M backend/tests/test_search_real_sources.py
 M backend/tests/test_spec_bugfixes.py
 D backend/tools/visual_search.py
 M backend/tools/web_search.py
 M docs/ARCHITECTURE.md
 M docs/CYBER_AVATAR_PLATFORM.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
?? backend/tests/test_amap_mcp.py
?? backend/tests/test_weather_daily_cap.py
?? backend/tests/test_weather_intent.py
?? backend/tools/amap_mcp.py
?? backend/tools/weather.py
?? backend/utils/city_name.py
?? docs/tasks/2026-10-09-amap-weather/
```

退出码：`0`。

#### 原 6.2：受保护文件

目录：仓库根目录。

```bash
git diff --exit-code -- backend/tools/route.py backend/tools/native_search.py backend/tools/travel_plan.py backend/tools/card_detail.py backend/tools/topic_expand.py backend/utils/safe_http.py
```

实际输出：

无输出。

退出码：`0`。

#### 原 6.3：现有测试 diff 统计

目录：仓库根目录。

```bash
git diff --stat -- backend/tests/
```

实际输出：

```text
 backend/tests/test_search_real_sources.py | 19 ++++++-------------
 backend/tests/test_spec_bugfixes.py       | 30 ------------------------------
 2 files changed, 6 insertions(+), 43 deletions(-)
```

退出码：`0`。

#### 原 6.3 补充：逐函数 diff

目录：仓库根目录。

```bash
git diff -- backend/tests/test_search_real_sources.py backend/tests/test_spec_bugfixes.py
```

实际输出：

```text
diff --git a/backend/tests/test_search_real_sources.py b/backend/tests/test_search_real_sources.py
index 4b9b25a..ca82f57 100644
--- a/backend/tests/test_search_real_sources.py
+++ b/backend/tests/test_search_real_sources.py
@@ -265,24 +265,17 @@ def test_surrounding_prose_is_tolerated_and_raw_is_preserved(monkeypatch):
     assert card["error"] is False
 
 
-def test_weather_dispatch_happens_before_native_search(monkeypatch):
-    from tools import visual_search
+def test_weather_query_uses_native_search_and_legacy_module_is_removed(monkeypatch):
+    import importlib.util
 
-    weather_card = {"type": "card", "subtype": "weather", "source": "宁波", "points": ["晴"]}
-    weather_calls = []
-
-    def weather(query):
-        weather_calls.append(query)
-        return weather_card
-
-    monkeypatch.setattr(visual_search, "_search_weather_direct", weather)
     calls = _stub(monkeypatch, _payload())
 
     card = web_search.web_search("  宁波天气  ")
 
-    assert card is weather_card
-    assert weather_calls == ["宁波天气"]
-    assert calls == []
+    assert card["error"] is False
+    assert len(calls) == 1
+    assert calls[0][0][-1]["content"] == "搜索：宁波天气"
+    assert importlib.util.find_spec("tools.visual_search") is None
 
 
 def test_grounded_search_copies_provider_sources(monkeypatch):
diff --git a/backend/tests/test_spec_bugfixes.py b/backend/tests/test_spec_bugfixes.py
index 8d08983..97a9212 100644
--- a/backend/tests/test_spec_bugfixes.py
+++ b/backend/tests/test_spec_bugfixes.py
@@ -222,36 +222,6 @@ def test_latest_match_decision_wins(tmp_path, monkeypatch):
     assert asyncio.run(scenario()) == []
 
 
-def test_weather_weekday_uses_monday_first(monkeypatch):
-    import requests
-    from tools.visual_search import _search_weather_direct
-
-    payload = {
-        "current_condition": [{
-            "weatherDesc": [{"value": "晴"}],
-            "temp_C": "28",
-            "FeelsLikeC": "29",
-        }],
-        "weather": [{
-            "date": "2026-07-20",
-            "maxtempC": "30",
-            "mintempC": "22",
-            "hourly": [{}, {}, {}, {}, {"weatherDesc": [{"value": "晴"}]}],
-        }],
-    }
-
-    class _Response:
-        def raise_for_status(self):
-            return None
-
-        def json(self):
-            return payload
-
-    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _Response())
-    card = _search_weather_direct("宁波天气")
-    assert card["weather"]["forecast"][0]["day"] == "周一"
-
-
 def test_peer_manager_keeps_each_socket_independent():
     from routers.peer import ConnectionManager
 
```

退出码：`0`。

#### 原 6.4：旧天气引用

目录：仓库根目录。

```bash
grep -rn "visual_search\|wttr\|Ningbo" backend --include=*.py | grep -v "^backend/.venv"
```

实际输出：

```text
backend/tests/test_search_real_sources.py:278:    assert importlib.util.find_spec("tools.visual_search") is None
```

退出码：`0`。

仅有规格允许的 find_spec 模块不存在断言，本项满足。

#### 原 6.5：execute_intent 签名

目录：仓库根目录。

```bash
grep -n "def execute_intent(intent: str, params: dict)" backend/services/chat_service.py
```

实际输出：

```text
232:def execute_intent(intent: str, params: dict):
```

退出码：`0`。

#### R1：MCP 新测试文件单跑

目录：`backend/`。

```bash
python -m pytest -q tests/test_amap_mcp.py
```

实际输出：

```text
........................................................................ [ 45%]
........................................................................ [ 90%]
................                                                         [100%]
160 passed in 0.23s
```

退出码：`0`。

#### R1：天气意图新测试文件单跑

目录：`backend/`。

```bash
python -m pytest -q tests/test_weather_intent.py
```

实际输出：

```text
.....................................................................    [100%]
=============================== warnings summary ===============================
tests/test_weather_intent.py: 10 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_weather_intent.py::test_weather_followup_city_runs_and_charges_once
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
69 passed, 11 warnings in 0.96s
```

退出码：`0`。

#### R1：天气额度新测试文件单跑

目录：`backend/`。

```bash
python -m pytest -q tests/test_weather_daily_cap.py
```

实际输出：

```text
.........................                                                [100%]
=============================== warnings summary ===============================
tests/test_weather_daily_cap.py: 10 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_weather_daily_cap.py::test_third_weather_query_is_error_without_charge_or_pending
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
25 passed, 11 warnings in 0.96s
```

退出码：`0`。

#### R1：三个新增测试文件联合

目录：`backend/`。

```bash
python -m pytest -q tests/test_amap_mcp.py tests/test_weather_intent.py tests/test_weather_daily_cap.py
```

实际输出：

```text
........................................................................ [ 28%]
........................................................................ [ 56%]
........................................................................ [ 85%]
......................................                                   [100%]
=============================== warnings summary ===============================
tests/test_weather_intent.py: 10 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_weather_intent.py::test_weather_followup_city_runs_and_charges_once
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
254 passed, 11 warnings in 1.58s
```

退出码：`0`。

#### 原 6.6：全量后端

目录：`backend/`。

```bash
python -m pytest -q
```

实际输出：

```text
........................................................................ [  2%]
........................................................................ [  5%]
........................................................................ [  8%]
........................................................................ [ 11%]
........................................................................ [ 14%]
........................................................................ [ 17%]
........................................................................ [ 20%]
........................................................................ [ 23%]
........................................................................ [ 26%]
........................................................................ [ 29%]
........................................................................ [ 32%]
........................................................................ [ 35%]
........................................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 47%]
........................................................................ [ 50%]
...............EF....................................................... [ 53%]
........................................................................ [ 56%]
........................................................................ [ 59%]
........................................................................ [ 62%]
........................................................................ [ 65%]
........................................................................ [ 68%]
........................................................................ [ 71%]
........................................................................ [ 74%]
........................................................................ [ 77%]
...................................................EEE.E................ [ 80%]
........................................................................ [ 83%]
........................................................................ [ 86%]
........................................................................ [ 89%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 98%]
.........................................                                [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e883b60>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10f6cdc50>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10dec6c80>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10d919fd0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10f6cda20>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
=================================== FAILURES ===================================
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x10dc1ee00>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10d5a63c0>

    def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
        import services.exchange_service as service
    
        async def start_server():
            entered, disconnected = asyncio.Event(), asyncio.Event()
    
            async def handler(reader, writer):
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                    length = 0
                    for line in headers.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1].strip())
                    if length:
                        await reader.readexactly(length)
                    entered.set()
                    await reader.read(1)
                    disconnected.set()
                finally:
                    writer.close()
                    await writer.wait_closed()
    
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            return server, entered, disconnected
    
        async def wait_event(event):
            await asyncio.wait_for(event.wait(), timeout=5)
    
>       server, entered, disconnected = client.portal.call(start_server)
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_exchange_isolation.py:151: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x10f685e80>
host = '127.0.0.1', port = 0, family = <AddressFamily.AF_UNSPEC: 0>
flags = <AddressInfo.AI_PASSIVE: 1>
sock = <socket.socket [closed] fd=-1, family=2, type=1, proto=6>, backlog = 100
ssl = None, reuse_address = True, reuse_port = None, keep_alive = None
ssl_handshake_timeout = None, ssl_shutdown_timeout = None, start_serving = True

    async def create_server(
            self, protocol_factory, host=None, port=None,
            *,
            family=socket.AF_UNSPEC,
            flags=socket.AI_PASSIVE,
            sock=None,
            backlog=100,
            ssl=None,
            reuse_address=None,
            reuse_port=None,
            keep_alive=None,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
            start_serving=True):
        """Create a TCP server.
    
        The host parameter can be a string, in that case the TCP server is
        bound to host and port.
    
        The host parameter can also be a sequence of strings and in that
        case the TCP server is bound to all hosts of the sequence.  If
        a host appears multiple times (possibly indirectly e.g. when
        hostnames resolve to the same IP address), the server is only bound
        once to that host.
    
        Return a Server object which can be used to stop the service.
    
        This method is a coroutine.
        """
        if isinstance(ssl, bool):
            raise TypeError('ssl argument must be an SSLContext or None')
    
        if ssl_handshake_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_handshake_timeout is only meaningful with ssl')
    
        if ssl_shutdown_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_shutdown_timeout is only meaningful with ssl')
    
        if sock is not None:
            _check_ssl_socket(sock)
    
        if host is not None or port is not None:
            if sock is not None:
                raise ValueError(
                    'host/port and sock can not be specified at the same time')
    
            if reuse_address is None:
                reuse_address = os.name == "posix" and sys.platform != "cygwin"
            sockets = []
            if host == '':
                hosts = [None]
            elif (isinstance(host, str) or
                  not isinstance(host, collections.abc.Iterable)):
                hosts = [host]
            else:
                hosts = host
    
            fs = [self._create_server_getaddrinfo(host, port, family=family,
                                                  flags=flags)
                  for host in hosts]
            infos = await tasks.gather(*fs)
            infos = set(itertools.chain.from_iterable(infos))
    
            completed = False
            try:
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    try:
                        sock = socket.socket(af, socktype, proto)
                    except socket.error:
                        # Assume it's a bad family/type/protocol combination.
                        if self._debug:
                            logger.warning('create_server() failed to create '
                                           'socket.socket(%r, %r, %r)',
                                           af, socktype, proto, exc_info=True)
                        continue
                    sockets.append(sock)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                    # Since Linux 6.12.9, SO_REUSEPORT is not allowed
                    # on other address families than AF_INET/AF_INET6.
                    if reuse_port and af in (socket.AF_INET, socket.AF_INET6):
                        _set_reuseport(sock)
                    if keep_alive:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
                    # Disable IPv4/IPv6 dual stack support (enabled by
                    # default on Linux) which makes a single socket
                    # listen on both address families.
                    if (_HAS_IPv6 and
                            af == socket.AF_INET6 and
                            hasattr(socket, 'IPPROTO_IPV6')):
                        sock.setsockopt(socket.IPPROTO_IPV6,
                                        socket.IPV6_V6ONLY,
                                        True)
                    try:
                        sock.bind(sa)
                    except OSError as err:
                        msg = ('error while attempting '
                               'to bind on address %r: %s'
                               % (sa, str(err).lower()))
                        if err.errno == errno.EADDRNOTAVAIL:
                            # Assume the family is not enabled (bpo-30945)
                            sockets.pop()
                            sock.close()
                            if self._debug:
                                logger.warning(msg)
                            continue
>                       raise OSError(err.errno, msg) from None
E                       OSError: [Errno None] error while attempting to bind on address ('127.0.0.1', 0): weather task offline guard: real network disabled

<Python标准库>/asyncio/base_events.py:1637: OSError
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2411 passed, 11 warnings, 5 errors in 60.34s (0:01:00)
```

退出码：`1`。

唯一 1 failed 与 5 errors 都发生于六个既有测试的真实端口监听之前，来自离线护栏拒绝；没有其他失败，原三个失败用例已通过。本条实际退出码仍为 1，六个例外需按规格在沙箱外重跑。

#### 原 6.7：TypeScript

目录：`frontend/`。

```bash
npx tsc --noEmit
```

实际输出：

无输出。

退出码：`0`。

#### 原 6.7：ESLint

目录：`frontend/`。

```bash
npx eslint .
```

实际输出：

```text

frontend/app/page.tsx
   143:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   234:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   392:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   445:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   446:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   447:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   457:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   458:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   459:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   460:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   463:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   469:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   470:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   774:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   868:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1292:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1312:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1320:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1341:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1383:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1479:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1815) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1914:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1954:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2224:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
```

退出码：`0`。

#### 原 6.7：旧前端字段

目录：`frontend/`。

```bash
grep -n "WEATHER_CN\|weatherCN\|currentTemp\|feelsLike" app/page.tsx components/ChatBubble.tsx
```

实际输出：

无输出。

退出码：`1`。

无匹配退出 1，是本项预期通过结果。

### 补充只读校验与人工事项

原两个城市参数组（含新闻输入/期望）未改，原新闻聊天测试函数源码未改；25 项拒绝前缀、9 项拒绝子串与作者列表逐字相同，原可剥离前后缀名单相同。已有 73 个测试文件仍仅包含最初获准两函数的改动；六个受保护实现文件与 HEAD 逐字相同，pending 持久化层 AST 不变。只读复核退出码 `0`；`git diff --check` 无输出、退出码 `0`。

R1 没有未完成的代码或未裁决的规格问题。保留人工验收：六项既有端口测试需在沙箱外重跑，以及真实高德调用、生产配置/额度/退款、前端构建和界面截图；这些仍按原规格交由 Claude，在本轮禁止真实网络的约束下未执行。

## 7. 返修 R2

依据：[06-fix-r2.md](./06-fix-r2.md)。冲突处以 R2 为准，其余原规格及 R1 条款继续有效。三个原文件负责人并行返修：MCP/天气负责人独占 MCP、天气工具和 MCP 测试；意图/聊天负责人独占聊天服务和每日额度测试；文档负责人只改部署文档。派发均未传 `model` 或 `reasoning_effort`；根代理独占本报告并复核。没有回滚先前实现，没有改动前端，没有发起真实网络请求。

### 本轮修改的文件（相对 R2 前）

| 文件 | R2 改动 |
|---|---|
| `backend/services/chat_service.py` | 删除两个天气失败卡特判，统一 card → 摘要 → 保存逻辑追加资源；每日超限 error 路径不变 |
| `backend/tools/weather.py` | 上游城市去首尾空白、空串或非字符串回退用户规范化城市，继续截 20 字 |
| `backend/tools/amap_mcp.py` | SSE 只按 CRLF、CR、LF 分行 |
| `backend/tests/test_weather_daily_cap.py` | 点名顺序测试改名并调整顺序断言；新增实际追问补齐额度用例，25 → 26 |
| `backend/tests/test_amap_mcp.py` | 只追加 7 个城市字段用例及 3 个 U+2028/换行用例，160 → 170 |
| `docs/DEPLOYMENT.md` | 仅替换 R2 指定的部署抽查句 |
| `docs/tasks/2026-10-09-amap-weather/03-report.md` | 更新当前结论并追加本节及实际输出，首次/R1 的历史输出保留 |

本轮修改 7 个文件，没有新增或删除文件。白名单中的 `test_weather_intent.py` 不需要改动；仍运行其全部 69 个用例。前端两文件在累计 `git status` 中仍有首轮改动，但 R2 前后全部 199 个前端文件字节一致；`city_name.py`、原三个失败用例、六个受保护实现文件及其他原测试保持既有完成状态。

### R2-1 至 R2-5 逐项落实

| 条款 | 落实情况与证据 |
|---|---|
| R2-1 失败卡与危机资源 | `stream_intent`、`stream_pending` 两处 `weather_error` 均删除。先 yield card、再设置历史摘要、由既有 `_save_text_reply` 追加资源。点名用例改为 `test_weather_failure_sends_card_before_crisis_resource`：direct/pending 首事件均是失败 card，随后资源 text，整轮恰好一次；存储值严格等于失败摘要 + 空行 + 资源，失败不计费。每日超限 SSE error 的原资源顺序未改，前端未改 |
| R2-2 部署措辞 | 原句精确替换为“部署后抽查应覆盖真实高德响应、失败卡退款、缺城市追问与取消。”；除任务目录外全库“沙箱外”检索无匹配；部署文件其他字节不变 |
| R2-3 补齐路径额度 | 新增 `test_pending_city_completions_consume_weather_daily_cap`，限流器开启、DEV_MODE=0、上限 2，同账号三会话均先走缺城市追问写 pending，再依次补齐。前两次获得天气卡，第三次只有指定每日超限 error；高德桩始终只调用 2 次，第三个 pending 清除，余额保持 80。反向验证将仅此补齐分支的 hit=True 模拟为 False，新测试实际变红；移除模拟实际转绿，详见下方完整输出 |
| R2-4 空城市兜底 | 对上游 city 先 strip，再截 20 字；为空或非字符串使用已规范化用户城市。空串 + 有效一天用例断言 location 为杭州、source 为“天气 · 杭州”；另覆盖空白、全角空白、None、整数、带空白的城市与长度限制，共 7 个新增用例 |
| R2-5 SSE 规范分行 | 改用 `re.split(r"\r\n|\r|\n", text)`，补行收尾逻辑不变；三个新增参数化用例分别使用 CRLF、CR、LF，JSON 内确有未转义的 U+2028，均成功解析 |

R2 共追加 `10 + 1 = 11` 个用例，三文件合计 `170 + 69 + 26 = 265`。实际全量总数 `2422 + 1 + 5 = 2428 = 2164 - 1 + 265`，高于规格总数下限 `2164 - 2 + 265 = 2427`；六个既有端口例外外全部通过。R1 原三条输入和期望未改，随联合与全量持续通过。

为了验证第三次确实在 `stream_pending` 拒绝，先在同账号三个会话建立缺城市 pending，再依次完成两次并尝试第三次。若在前两次完成以后才发第三条缺城市请求，它会先被原 `stream_intent` 的不计数检查拦截，无法验证本条指定的补齐分支；本测试没有改变该既有行为。

### 验收命令实际输出与退出码

后端使用现有虚拟环境、仓库外 `sitecustomize` socket/DNS 离线护栏及新增测试的断网夹具。前端仅运行原规格静态检查，npm 设置 offline，没有安装依赖。未启动后端，未执行 build/dev，未请求真实高德。完整输出只将本机根路径改为相对路径、标准库路径改为 `<Python标准库>/`、仓库外临时路径改为 `<临时离线护栏>/` 或 `<临时反向验证>/`；正文、警告、行号、计数和退出码均为实际。

grep/rg 无匹配时退出码为 1，这是要求“无输出”条款的预期结果。以下累计 git 状态与首轮/R1 一致；R2 新改范围由返修前 SHA256 快照逐文件比对补充验证。

#### R2 验收 1 / 原 6.1：累计工作区状态

目录：`./`。

```bash
git status --porcelain
```

实际输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/intent_router.py
 M backend/rate_limit.py
 M backend/services/chat_service.py
 M backend/tests/test_search_real_sources.py
 M backend/tests/test_spec_bugfixes.py
 D backend/tools/visual_search.py
 M backend/tools/web_search.py
 M docs/ARCHITECTURE.md
 M docs/CYBER_AVATAR_PLATFORM.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
?? backend/tests/test_amap_mcp.py
?? backend/tests/test_weather_daily_cap.py
?? backend/tests/test_weather_intent.py
?? backend/tools/amap_mcp.py
?? backend/tools/weather.py
?? backend/utils/city_name.py
?? docs/tasks/2026-10-09-amap-weather/
```

退出码：`0`。

#### 原 6.2：受保护实现文件

目录：`./`。

```bash
git diff --exit-code -- backend/tools/route.py backend/tools/native_search.py backend/tools/travel_plan.py backend/tools/card_detail.py backend/tools/topic_expand.py backend/utils/safe_http.py
```

实际输出：

无输出。

退出码：`0`。

#### 原 6.3：已跟踪现有测试 diff 统计

目录：`./`。

```bash
git diff --stat -- backend/tests/
```

实际输出：

```text
 backend/tests/test_search_real_sources.py | 19 ++++++-------------
 backend/tests/test_spec_bugfixes.py       | 30 ------------------------------
 2 files changed, 6 insertions(+), 43 deletions(-)
```

退出码：`0`。

#### 原 6.3 补充：获准两函数逐项 diff

目录：`./`。

```bash
git diff -- backend/tests/test_search_real_sources.py backend/tests/test_spec_bugfixes.py
```

实际输出：

```text
diff --git a/backend/tests/test_search_real_sources.py b/backend/tests/test_search_real_sources.py
index 4b9b25a..ca82f57 100644
--- a/backend/tests/test_search_real_sources.py
+++ b/backend/tests/test_search_real_sources.py
@@ -265,24 +265,17 @@ def test_surrounding_prose_is_tolerated_and_raw_is_preserved(monkeypatch):
     assert card["error"] is False
 
 
-def test_weather_dispatch_happens_before_native_search(monkeypatch):
-    from tools import visual_search
+def test_weather_query_uses_native_search_and_legacy_module_is_removed(monkeypatch):
+    import importlib.util
 
-    weather_card = {"type": "card", "subtype": "weather", "source": "宁波", "points": ["晴"]}
-    weather_calls = []
-
-    def weather(query):
-        weather_calls.append(query)
-        return weather_card
-
-    monkeypatch.setattr(visual_search, "_search_weather_direct", weather)
     calls = _stub(monkeypatch, _payload())
 
     card = web_search.web_search("  宁波天气  ")
 
-    assert card is weather_card
-    assert weather_calls == ["宁波天气"]
-    assert calls == []
+    assert card["error"] is False
+    assert len(calls) == 1
+    assert calls[0][0][-1]["content"] == "搜索：宁波天气"
+    assert importlib.util.find_spec("tools.visual_search") is None
 
 
 def test_grounded_search_copies_provider_sources(monkeypatch):
diff --git a/backend/tests/test_spec_bugfixes.py b/backend/tests/test_spec_bugfixes.py
index 8d08983..97a9212 100644
--- a/backend/tests/test_spec_bugfixes.py
+++ b/backend/tests/test_spec_bugfixes.py
@@ -222,36 +222,6 @@ def test_latest_match_decision_wins(tmp_path, monkeypatch):
     assert asyncio.run(scenario()) == []
 
 
-def test_weather_weekday_uses_monday_first(monkeypatch):
-    import requests
-    from tools.visual_search import _search_weather_direct
-
-    payload = {
-        "current_condition": [{
-            "weatherDesc": [{"value": "晴"}],
-            "temp_C": "28",
-            "FeelsLikeC": "29",
-        }],
-        "weather": [{
-            "date": "2026-07-20",
-            "maxtempC": "30",
-            "mintempC": "22",
-            "hourly": [{}, {}, {}, {}, {"weatherDesc": [{"value": "晴"}]}],
-        }],
-    }
-
-    class _Response:
-        def raise_for_status(self):
-            return None
-
-        def json(self):
-            return payload
-
-    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _Response())
-    card = _search_weather_direct("宁波天气")
-    assert card["weather"]["forecast"][0]["day"] == "周一"
-
-
 def test_peer_manager_keeps_each_socket_independent():
     from routers.peer import ConnectionManager
 
```

退出码：`0`。

#### 原 6.4：旧天气/视觉搜索引用

目录：`./`。

```bash
grep -rn "visual_search\|wttr\|Ningbo" backend --include=*.py | grep -v "^backend/.venv"
```

实际输出：

```text
backend/tests/test_search_real_sources.py:278:    assert importlib.util.find_spec("tools.visual_search") is None
```

退出码：`0`。

#### 原 6.5：execute_intent 双参数签名

目录：`./`。

```bash
grep -n "def execute_intent(intent: str, params: dict)" backend/services/chat_service.py
```

实际输出：

```text
232:def execute_intent(intent: str, params: dict):
```

退出码：`0`。

#### MCP 新测试文件单跑

目录：`backend/`。

```bash
python -m pytest -q tests/test_amap_mcp.py
```

实际输出：

```text
........................................................................ [ 42%]
........................................................................ [ 84%]
..........................                                               [100%]
170 passed in 0.21s
```

退出码：`0`。

#### 天气意图新测试文件单跑

目录：`backend/`。

```bash
python -m pytest -q tests/test_weather_intent.py
```

实际输出：

```text
.....................................................................    [100%]
=============================== warnings summary ===============================
tests/test_weather_intent.py: 10 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_weather_intent.py::test_weather_followup_city_runs_and_charges_once
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
69 passed, 11 warnings in 0.89s
```

退出码：`0`。

#### 天气每日额度新测试文件单跑

目录：`backend/`。

```bash
python -m pytest -q tests/test_weather_daily_cap.py
```

实际输出：

```text
..........................                                               [100%]
=============================== warnings summary ===============================
tests/test_weather_daily_cap.py: 10 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_weather_daily_cap.py::test_third_weather_query_is_error_without_charge_or_pending
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
26 passed, 11 warnings in 0.89s
```

退出码：`0`。

#### R2 验收 2：三个新增测试文件联合

目录：`backend/`。

```bash
python -m pytest -q tests/test_amap_mcp.py tests/test_weather_intent.py tests/test_weather_daily_cap.py
```

实际输出：

```text
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 81%]
.................................................                        [100%]
=============================== warnings summary ===============================
tests/test_weather_intent.py: 10 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_weather_intent.py::test_weather_followup_city_runs_and_charges_once
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
265 passed, 11 warnings in 1.30s
```

退出码：`0`。

#### R2 验收 2 / 原 6.6：全量后端

目录：`backend/`。

```bash
python -m pytest -q
```

实际输出：

```text
........................................................................ [  2%]
........................................................................ [  5%]
........................................................................ [  8%]
........................................................................ [ 11%]
........................................................................ [ 14%]
........................................................................ [ 17%]
........................................................................ [ 20%]
........................................................................ [ 23%]
........................................................................ [ 26%]
........................................................................ [ 29%]
........................................................................ [ 32%]
........................................................................ [ 35%]
........................................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 47%]
........................................................................ [ 50%]
.........................EF............................................. [ 53%]
........................................................................ [ 56%]
........................................................................ [ 59%]
........................................................................ [ 62%]
........................................................................ [ 65%]
........................................................................ [ 68%]
........................................................................ [ 71%]
........................................................................ [ 74%]
........................................................................ [ 77%]
.............................................................EEE.E...... [ 80%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 94%]
........................................................................ [ 97%]
....................................................                     [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10dbf04b0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10f59df60>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10de50280>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e71e190>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10f59dda0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
<Python标准库>/socketserver.py:478: in server_bind
    self.socket.bind(self.server_address)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

event = 'socket.bind'
args = (<socket.socket [closed] fd=-1, family=2, type=1, proto=0>, ('127.0.0.1', 0))

    def _no_real_network(event, args):
        if event in {"socket.connect", "socket.bind"}:
            sock = args[0]
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
>               raise PermissionError("weather task offline guard: real network disabled")
E               PermissionError: weather task offline guard: real network disabled

<临时离线护栏>/sitecustomize.py:10: PermissionError
=================================== FAILURES ===================================
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x10ec6b350>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10dbf01a0>

    def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
        import services.exchange_service as service
    
        async def start_server():
            entered, disconnected = asyncio.Event(), asyncio.Event()
    
            async def handler(reader, writer):
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                    length = 0
                    for line in headers.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1].strip())
                    if length:
                        await reader.readexactly(length)
                    entered.set()
                    await reader.read(1)
                    disconnected.set()
                finally:
                    writer.close()
                    await writer.wait_closed()
    
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            return server, entered, disconnected
    
        async def wait_event(event):
            await asyncio.wait_for(event.wait(), timeout=5)
    
>       server, entered, disconnected = client.portal.call(start_server)
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_exchange_isolation.py:151: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x10f58f690>
host = '127.0.0.1', port = 0, family = <AddressFamily.AF_UNSPEC: 0>
flags = <AddressInfo.AI_PASSIVE: 1>
sock = <socket.socket [closed] fd=-1, family=2, type=1, proto=6>, backlog = 100
ssl = None, reuse_address = True, reuse_port = None, keep_alive = None
ssl_handshake_timeout = None, ssl_shutdown_timeout = None, start_serving = True

    async def create_server(
            self, protocol_factory, host=None, port=None,
            *,
            family=socket.AF_UNSPEC,
            flags=socket.AI_PASSIVE,
            sock=None,
            backlog=100,
            ssl=None,
            reuse_address=None,
            reuse_port=None,
            keep_alive=None,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
            start_serving=True):
        """Create a TCP server.
    
        The host parameter can be a string, in that case the TCP server is
        bound to host and port.
    
        The host parameter can also be a sequence of strings and in that
        case the TCP server is bound to all hosts of the sequence.  If
        a host appears multiple times (possibly indirectly e.g. when
        hostnames resolve to the same IP address), the server is only bound
        once to that host.
    
        Return a Server object which can be used to stop the service.
    
        This method is a coroutine.
        """
        if isinstance(ssl, bool):
            raise TypeError('ssl argument must be an SSLContext or None')
    
        if ssl_handshake_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_handshake_timeout is only meaningful with ssl')
    
        if ssl_shutdown_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_shutdown_timeout is only meaningful with ssl')
    
        if sock is not None:
            _check_ssl_socket(sock)
    
        if host is not None or port is not None:
            if sock is not None:
                raise ValueError(
                    'host/port and sock can not be specified at the same time')
    
            if reuse_address is None:
                reuse_address = os.name == "posix" and sys.platform != "cygwin"
            sockets = []
            if host == '':
                hosts = [None]
            elif (isinstance(host, str) or
                  not isinstance(host, collections.abc.Iterable)):
                hosts = [host]
            else:
                hosts = host
    
            fs = [self._create_server_getaddrinfo(host, port, family=family,
                                                  flags=flags)
                  for host in hosts]
            infos = await tasks.gather(*fs)
            infos = set(itertools.chain.from_iterable(infos))
    
            completed = False
            try:
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    try:
                        sock = socket.socket(af, socktype, proto)
                    except socket.error:
                        # Assume it's a bad family/type/protocol combination.
                        if self._debug:
                            logger.warning('create_server() failed to create '
                                           'socket.socket(%r, %r, %r)',
                                           af, socktype, proto, exc_info=True)
                        continue
                    sockets.append(sock)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                    # Since Linux 6.12.9, SO_REUSEPORT is not allowed
                    # on other address families than AF_INET/AF_INET6.
                    if reuse_port and af in (socket.AF_INET, socket.AF_INET6):
                        _set_reuseport(sock)
                    if keep_alive:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
                    # Disable IPv4/IPv6 dual stack support (enabled by
                    # default on Linux) which makes a single socket
                    # listen on both address families.
                    if (_HAS_IPv6 and
                            af == socket.AF_INET6 and
                            hasattr(socket, 'IPPROTO_IPV6')):
                        sock.setsockopt(socket.IPPROTO_IPV6,
                                        socket.IPV6_V6ONLY,
                                        True)
                    try:
                        sock.bind(sa)
                    except OSError as err:
                        msg = ('error while attempting '
                               'to bind on address %r: %s'
                               % (sa, str(err).lower()))
                        if err.errno == errno.EADDRNOTAVAIL:
                            # Assume the family is not enabled (bpo-30945)
                            sockets.pop()
                            sock.close()
                            if self._debug:
                                logger.warning(msg)
                            continue
>                       raise OSError(err.errno, msg) from None
E                       OSError: [Errno None] error while attempting to bind on address ('127.0.0.1', 0): weather task offline guard: real network disabled

<Python标准库>/asyncio/base_events.py:1637: OSError
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2422 passed, 11 warnings, 5 errors in 57.62s
```

退出码：`1`。

#### R2 验收 3：天气失败卡特判检索

目录：`./`。

```bash
grep -n "weather_error" backend/services/chat_service.py
```

实际输出：

无输出。

退出码：`1`。

#### R2 验收 4：指定现行文档工作流措辞检索

目录：`./`。

```bash
grep -rn "沙箱外" README.md CLAUDE.md PLAN.md docs/ARCHITECTURE.md docs/DEPLOYMENT.md docs/CYBER_AVATAR_PLATFORM.md
```

实际输出：

无输出。

退出码：`1`。

#### R2-2 补充：除任务文档外全库措辞检索

目录：`./`。

```bash
rg -n '沙箱外' --glob '!docs/tasks/**' --glob '!frontend/node_modules/**' --glob '!backend/.venv/**' .
```

实际输出：

无输出。

退出码：`1`。

#### 原 6.7：TypeScript

目录：`frontend/`。

```bash
npx tsc --noEmit
```

实际输出：

无输出。

退出码：`0`。

#### 原 6.7：ESLint

目录：`frontend/`。

```bash
npx eslint .
```

实际输出：

```text

frontend/app/page.tsx
   143:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   234:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   392:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   445:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   446:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   447:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   457:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   458:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   459:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   460:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   463:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   469:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   470:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   774:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   868:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1292:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1312:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1320:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1341:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1383:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1479:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1815) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1914:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1954:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2224:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
```

退出码：`0`。

#### 原 6.7：旧前端天气字段检索

目录：`frontend/`。

```bash
grep -n "WEATHER_CN\|weatherCN\|currentTemp\|feelsLike" app/page.tsx components/ChatBubble.tsx
```

实际输出：

无输出。

退出码：`1`。

本项仅摘录实际收集汇总行（此前各测试文件单跑与联合输出完整保留）。

#### 新增测试收集数

目录：`backend/`。

```bash
python -m pytest --collect-only -q tests/test_amap_mcp.py tests/test_weather_intent.py tests/test_weather_daily_cap.py
```

实际输出：

```text
265 tests collected in 0.36s
```

退出码：`0`。

#### 原受保护测试与持久化层复核

目录：`./`。

```bash
python3 <临时离线护栏>/check_scope.py
```

实际输出：

```text
PASS: 73 tracked test files are unchanged outside the two permitted weather functions.
PASS: all six protected implementation files are byte-identical to HEAD.
PASS: pending persistence function syntax is unchanged.
```

退出码：`0`。

### R2-3 反向验证的实际过程与输出

临时 pytest 插件只在本新用例运行时包装 `chat_service.check_chat_daily_cap`：天气调用、调用者为 `stream_pending` 且 hit=True 时替换为 hit=False。`stream_intent`、缺参检查及其他工具不受影响。插件在测试结束立即恢复函数，并仅位于仓库外，没有临时改写/回滚实现文件。

#### 反向：补齐 hit=False，新用例必须失败

目录：`backend/`。

```bash
PYTHONPATH=<临时离线护栏>:<临时反向验证>:$PWD PATH="$PWD/.venv/bin:$PATH" python -m pytest -q -p weather_pending_nohit_plugin tests/test_weather_daily_cap.py::test_pending_city_completions_consume_weather_daily_cap
```

实际输出：

```text
F                                                                        [100%]
=================================== FAILURES ===================================
___________ test_pending_city_completions_consume_weather_daily_cap ____________

weather_chat = ('smoke_tester', ('smoke_tester', 'deb9cb8a-3223-4cfc-98eb-de8fd0efee92'), <function weather_chat.<locals>.send at 0x10b512090>, [('maps_weather', {'city': '宁波'}), ('maps_weather', {'city': '宁波'}), ('maps_weather', {'city': '宁波'})])
client = <starlette.testclient.TestClient object at 0x10b48ea50>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10949a9e0>

    def test_pending_city_completions_consume_weather_daily_cap(weather_chat, client, monkeypatch):
        import services.chat_service as chat
        from auth import create_token
    
        user, first_key, _, calls = weather_chat
        version = asyncio.run(database.get_session_version(user))
        headers = {"Authorization": f"Bearer {create_token(user, version)}"}
        conversations = [first_key[1]]
        for _ in range(2):
            response = client.post("/conversations", headers=headers, json={})
            assert response.status_code == 201, response.text
            conversations.append(response.json()["conversation"]["id"])
        monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
            "intent": "weather", "params": {}, "missing": ["city"],
        })
    
        def send(conversation, message):
            response = client.post("/chat", headers=headers, json={
                "message": message, "conversation_id": conversation,
            })
            assert response.status_code == 200, response.text
            return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    
        # Establish all three follow-ups before completions exhaust the account cap;
        # otherwise the third question is rejected by the non-consuming check.
        for conversation in conversations:
            assert {"text": "哪个城市？"} in send(conversation, "明天会下雨吗")
            assert intent_router.get_pending((user, conversation)) == {
                "intent": "weather", "params": {}, "missing": ["city"],
            }
        assert calls == []
        assert _balance(user) == 100
        for conversation in conversations[:2]:
            events = send(conversation, "宁波吧")
            card = next(event["card"] for event in events if event.get("card"))
            assert card["subtype"] == "weather"
            assert card["error"] is False
            assert intent_router.get_pending((user, conversation)) is None
        assert calls == [("maps_weather", {"city": "宁波"})] * 2
        assert _balance(user) == 80
>       assert send(conversations[2], "宁波吧") == [{"error": rate_limit.daily_cap_message("weather")}]
E       AssertionError: assert [{'card': {'t...'done': True}] == [{'error': '今...的次数已用完，明天再试'}]
E         
E         At index 0 diff: {'card': {'type': 'card', 'subtype': 'weather', 'source': '天气 · 杭州市', 'points': [], 'error': False, 'weather': {'location': '杭州市', 'forecast': [{'date': '2026-10-09', 'day': '周五', 'dayWeather': '晴', 'nightWeather': '晴', 'high': '26', 'low': '17', 'dayWind': '', 'nightWind': ''}]}}} != {'error': '今天查天气的次数已用完，明天再试'}
E         Left contains one more item: {'done': True}
E         Use -v to get more diff

tests/test_weather_daily_cap.py:374: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=weather, missing=['city']
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=weather, missing=['city']
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=weather, missing=['city']
[硬词检测] chars=3, detected_count=0
[R2 mutation] stream_pending weather hit=True -> hit=False
[硬词检测] chars=3, detected_count=0
[R2 mutation] stream_pending weather hit=True -> hit=False
[硬词检测] chars=3, detected_count=0
[R2 mutation] stream_pending weather hit=True -> hit=False
=============================== warnings summary ===============================
tests/test_weather_daily_cap.py: 10 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_weather_daily_cap.py::test_pending_city_completions_consume_weather_daily_cap
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_weather_daily_cap.py::test_pending_city_completions_consume_weather_daily_cap
1 failed, 11 warnings in 0.79s
```

退出码：`1`。

#### 正常：不加载模拟插件，新用例通过

目录：`backend/`。

```bash
PYTHONPATH=<临时离线护栏>:<临时反向验证>:$PWD PATH="$PWD/.venv/bin:$PATH" python -m pytest -q tests/test_weather_daily_cap.py::test_pending_city_completions_consume_weather_daily_cap
```

实际输出：

```text
.                                                                        [100%]
=============================== warnings summary ===============================
tests/test_weather_daily_cap.py: 10 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_weather_daily_cap.py::test_pending_city_completions_consume_weather_daily_cap
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 11 warnings in 0.71s
```

退出码：`0`。

反向实际第三轮返回第三张天气卡 + done，桩调用达到 3，因预期应只有 error 而在新用例第 374 行失败（退出 1）；去掉插件恢复真实实现后 `1 passed`（退出 0）。两次运行前后 `chat_service.py` SHA256 均为 `109138053496ffa64010a3b1f54f6d8e1707578f5c1dedabd954611815c2bcaf`，证实实现文件从未发生临时改写。

### R2 白名单与原测试完整性最终复核

```bash
python3 <临时离线护栏>/r2/check_r2_scope.py
```

实际输出：

```text
R2 files changed relative to pre-R2 snapshot:
backend/services/chat_service.py
backend/tests/test_amap_mcp.py
backend/tests/test_weather_daily_cap.py
backend/tools/amap_mcp.py
backend/tools/weather.py
docs/DEPLOYMENT.md
docs/tasks/2026-10-09-amap-weather/03-report.md
PASS: no changed files outside the R2 whitelist.
PASS: all 199 frontend files are byte-identical to pre-R2.
PASS: backend/tests/test_amap_mcp.py: 32 existing functions/classes unchanged; only named R2 test may change.
PASS: backend/tests/test_weather_daily_cap.py: 19 existing functions/classes unchanged; only named R2 test may change.
PASS: backend/tests/test_weather_intent.py: 18 existing functions/classes unchanged; only named R2 test may change.
PASS: DEPLOYMENT changes exactly the required sentence.
PASS: R1 normalize_city implementation is unchanged.
```

退出码：`0`。

```bash
git diff --check
```

实际输出：

无输出。

退出码：`0`。

### 未完成或需要人工确认

R2-1 至 R2-5 没有未完成代码或待裁决规格冲突。全量退出码仍为 1，不能表述为全量全部通过：原 6 个端口用例被离线护栏在监听前拒绝，需按原规格在允许监听的环境重跑；这些受保护测试未被修改，也未跳过。真实高德响应、生产权限/配置、额度与失败退款抽查、前端构建及界面截图继续按原规格留给 Claude，当前禁止真实网络和 build/dev 的约束下未执行。

本轮没有提交 commit、没有新增依赖、没有改变前端或城市规范化的 R1 实现。报告已按 R2 验收第 5 条在末尾新增“返修 R2”，保留先前实际验收历史并更新当前结论。
