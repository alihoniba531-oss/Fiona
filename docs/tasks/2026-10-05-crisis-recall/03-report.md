# 危机识别补词与 possible 路由报告（2026-10-05）

实现和报告已完成。规格 91 句语料与新增路由护栏通过；新增 **137** 个用例，收集总数为 **1546 + 137 = 1683**。A1 原始全量未通过：1 个临时目录断言失败、6 个本地 HTTP 端口用例受限。调整验证目录并明确排除这 6 个用例后，**1677 passed, 6 deselected**；A2 **137 passed**。A1 完整通过与 A6 盲测仍需主会话验收，不能视为已完成。

## 1. 文件、行号与规则覆盖

| 文件／行号 | 改动与覆盖的现象 |
|---|---|
| `backend/safety.py:33` | 新增片段剥离：一棵树上吊死成语、吊床／吊灯／吊兰；烧炭取暖／生火／做饭／烧烤；跳河江海游泳／潜水／救援／训练；备绳露营／帐篷／攀岩／晾衣。剩余明确危机仍继续判级。 |
| `backend/safety.py:44` | 第 2／3 条他人语境覆盖自尽、割脉、寻死、水域跳跃、烧炭、吊死、一死了之、了断自己／自己了断，避免第三方危机描述被新增自身规则升为 high。第 4 条信息／求助正则未改。 |
| `backend/safety.py:52` | 统一计划词模式认计划／计画／计畫，以设／统前字边界排除设计画面、统计画面。逐字归一行为保留。 |
| `backend/safety.py:59` | 在已有方法询问之外，新增方法与多久／多长／多深／多高／几层／数量及死亡结局的组合，覆盖上吊、割腕、割脉、跳楼、跳河江海、吊死、吞药、烧炭的量化询问；单独植物／宠物“多久会死”无方法词时不触发。 |
| `backend/safety.py:68` | “只／需／重／主”对要的排除只保留于一切分支；生命分支覆盖需要结束生命、只要结束生命、现在就结束生命。 |
| `backend/safety.py:70` | 了断自己／自己了断、把自己杀掉；吊死自己／吊死算了／想吊死；明确自身意图且句尾的裸了断；想好怎么死、怎么死最快／不痛／不疼。 |
| `backend/safety.py:73` | 第一人称现在／已发生跳河江海、自尽、割脉、寻死；想／要／准备／打算／计划／考虑的新增方法意图（含烧炭、一死了之）。 |
| `backend/safety.py:76` | 危险位置后接句尾想跳，覆盖站在桥上想跳，保持跳槽／伞／绳等既有边界。 |
| `backend/safety.py:79` | 明确整瓶／全部／所有泛药服用，支持药名与药在前的倒装；动作带完成词。药备齐且当天即时结束的准备表达，结束须为句尾而非结束疗程。 |
| `backend/safety.py:84` | 安眠药不醒／醒不过来／睡不醒／一睡不醒；多少、几片／粒／颗与死亡结局组合。普通遵医嘱几片问题不因此升为 high。 |
| `backend/safety.py:86` | 英语 end it all、hang myself、gonna、bridge／roof、thinking about killing/hanging/hurting/cutting myself、took all my pills 等同类表达。 |
| `backend/safety.py:93` | 意义的啥／甚么变体；完成式天台位置且句尾、活够了、不配活着、备好绳子、不愿醒／撑、痛苦求解脱、自身消失／一了百了句尾、结束这一切并撑不住、done with living/life、disappear/vanish forever/permanently 等 possible 兜底。 |
| `backend/safety.py:105` | 复用原归一操作；`assess_crisis`、`detect_crisis` 的签名和返回类型未改，危机指引与热线文字未改。 |
| `backend/safety.py:123` | 跟随逝者：仅他人语境中有完成式自杀／轻生／自尽／吊死，并出现自身也想／也要跟／随其走／去才判 high；否认、信息语境不触发。 |
| `backend/safety.py:151` | 暴露 `is_informational_crisis_context(text)`：整句 possible 且归一全文命中现有第 4 条规则才返回 True。 |
| `backend/utils/traditional_chinese.py:138` | 仅追加 26 组映射，原映射与逐字算法不改，详见字符清单。 |
| `backend/services/chat_service.py:35` | 导入 safety 暴露的语境判断，无复制正则。 |
| `backend/services/chat_service.py:1023` | 只对 possible 且非信息／求助语境启用跳过工具的路由条件。 |
| `backend/services/chat_service.py:1079` | 不调用生图候选判断或候选意图确认。 |
| `backend/services/chat_service.py:1113` | 不读取或处理生图追问 pending。 |
| `backend/services/chat_service.py:1153` | 保留镜子回复；为受保护轮传保留 pending 参数。 |
| `backend/services/chat_service.py:1164` | 模式与看图之后、普通 pending／意图之前直接走普通回复。工具、补参、搜索兜底均不进入。 |
| `backend/services/chat_service.py:657` | 镜子 helper 增加默认 False 的 `preserve_pending` 参数；受保护轮不执行手动镜子原有 pending 清理。配套判断见未决问题。 |
| `backend/tests/test_traditional_crisis.py:36`、`:49`、`:156` | 只追加两张字符清单，并按授权把計畫下週跳樓期望改为 high。 |
| `backend/tests/test_crisis_resource_paths.py:325`、`:331`、`:335` | 只修改授权的 possible tool／pending 断言和余额，high／mirror 分支保持原样。 |
| `backend/tests/test_crisis_recall_2026_10.py:13`、`:32`、`:39`、`:48` | 54 high、16 至少 possible、18 None、3 不得 high，逐句与规格 AST 核验相等。 |
| 新测试 `:74`、`:93`、`:117` | 单独参数组追加计划及词边界 10 例、方法／语境／日常护栏 15 例、信息语境接口 8 例。 |
| 新测试 `:264`、`:308`、`:349`、`:374` | R1–R4／生图候选 6 例；自动与手动镜子／看图 5 例；R6 1 例；固定修图引导 1 例。所有模型、工具打桩，检查调用、pending、10 颗计费、资源一次与 trace。 |
| `CLAUDE.md:76`、`README.md:136`、`docs/ARCHITECTURE.md:84` | 仅更新相关行为句：possible 的例外语境、跳过工具与保留 pending、其余模式与计费／热线。 |
| `PLAN.md:118` | 指定位置追加一行 2026-10-05 记录，未改历史段落。 |
| `docs/tasks/2026-10-05-crisis-recall/03-report.md:1` | 新建本报告。 |

新增用例分解：91 + 10 + 15 + 8 + 6 + 5 + 1 + 1 = **137**。R3 使用原示例“查一下安眠药吃多少会有危险”，确认 possible 且非信息／求助语境，无需换句。R5 复用 `test_possible_crisis_keeps_tool_routing_billing_resources_and_trace`；显式 image／image_edit 复用 `test_high_image_modes_use_support_reply_while_possible_uses_generation`。

## 2. 与规格逐节对应

| 规格 | 对应结果 |
|---|---|
| 0 | 仅白名单持久改动；既有测试只在第 4 节授权位置修改；无新增依赖、前端、提示词文案、计费规则改动。自主判断和冲突逐条记录于未决问题。 |
| 1 | 按 D1 先补词再加 possible 路由保护，并有危机／日常两道护栏；未引入模型判级。 |
| 2 | 覆盖即时水域行动、吊死／吞药倒装／新增求死词、生命分支、英语遗漏、致死询问、計畫和上吊日常误伤。 |
| 3.1 | 91 句语料达标；字符覆盖旧测试通过；公共签名和资源文案保留。实现的泛化边界另列未决问题。 |
| 3.2 | 非信息 possible 跳过候选、补参、意图和工具；模式／镜子／看图／普通回复、计费／热线／trace 继续；信息语境、显式图片模式和固定修图引导保持原路由。删除会话 cleanup 冲突见未决问题。 |
| 3.3 | 不处理列出的既有误报为高危问题，不改前端或 chat router。 |
| 4 | 三处授权修改的原样 diff 如下；原 high／mirror 断言 AST 相等，其他测试定义与参数未变，旧字符清单只追加。 |
| 5 | 四组逐字原句各自参数化；R1–R4、R6新增，R5复用现有测试；额外用例独立分组。 |
| 6 | 本报告提供文件行号、规则现象、diff、逐字字符、原始验收输出、退出码、status 和未决问题。 |
| 7 | A2 通过，A3／A4／A5差异核查完成；A1原始未全过，补跑1677过／6排除；A6由主会话执行。 |

## 3. 第 4 节三处授权测试修改：原样 diff

以下为 `git diff -- backend/tests/test_traditional_crisis.py backend/tests/test_crisis_resource_paths.py` 的完整原样输出（顺序为 git 实际输出）。退出码 `0`。资源路径测试的 high／mirror 内容只有上下文展示，无修改。

```diff
diff --git a/backend/tests/test_crisis_resource_paths.py b/backend/tests/test_crisis_resource_paths.py
index f2db342..827ec2d 100644
--- a/backend/tests/test_crisis_resource_paths.py
+++ b/backend/tests/test_crisis_resource_paths.py
@@ -322,22 +322,21 @@ def test_crisis_tool_pending_and_mirror_paths(client, dev_headers, monkeypatch,
     }))
     _assert_resource_once(events, level)
     assert events[-1] == {"done": True}
-    assert _balance(user) == before - (0 if path == "pending" and level == "possible" else 10)
+    assert _balance(user) == before - 10
     if level == "high":
         assert mode_calls == intent_calls == tool_calls == fill_calls == []
         assert model_calls == [700]
         if path == "pending":
             assert get_pending((user, conversation))["intent"] == "route"
     elif path == "tool":
-        assert mode_calls == intent_calls == [1]
-        assert len(tool_calls) == 1
-        assert fill_calls == model_calls == []
-        assert any("现在是下午三点" in event.get("text", "") for event in events)
+        assert mode_calls == [1]
+        assert intent_calls == tool_calls == fill_calls == []
+        assert model_calls == [700]
     elif path == "pending":
         assert mode_calls == [1]
-        assert fill_calls == [message]
-        assert intent_calls == tool_calls == model_calls == []
-        assert get_pending((user, conversation))["intent"] == "route"
+        assert intent_calls == tool_calls == fill_calls == []
+        assert model_calls == [700]
+        assert get_pending((user, conversation)) == {"intent": "route", "params": {}, "missing": ["origin"]}
     else:
         assert mode_calls == [1]
         assert model_calls == [80]
diff --git a/backend/tests/test_traditional_crisis.py b/backend/tests/test_traditional_crisis.py
index 283336c..4cbf8a6 100644
--- a/backend/tests/test_traditional_crisis.py
+++ b/backend/tests/test_traditional_crisis.py
@@ -33,6 +33,12 @@ RULE_CHARACTER_VARIANTS = {
     "简": "簡", "系": "係繫", "紧": "緊", "级": "級", "线": "線", "联": "聯",
     "认": "認", "评": "評", "询": "詢", "语": "語", "诺": "諾", "轮": "輪",
     "边": "邊", "达": "達", "镜": "鏡", "险": "險",
+    "兰": "蘭", "几": "幾", "台": "臺檯颱", "够": "夠", "尽": "盡儘",
+    "层": "層", "岩": "巖巗", "帐": "帳", "床": "牀", "来": "來", "树": "樹",
+    "潜": "潛", "灯": "燈", "烧": "燒", "练": "練", "统": "統", "脉": "脈",
+    "脱": "脫", "训": "訓", "设": "設", "过": "過", "随": "隨", "颗": "顆",
+    "饭": "飯", "马": "馬",
+    "长": "長",
 }
 
 # Rule characters without a traditional/alternate form used by this classifier.
@@ -40,6 +46,7 @@ RULE_CHARACTER_VARIANTS = {
 # RULE_CHARACTER_VARIANTS, so any newly added Chinese rule character fails review.
 NO_VARIANT_RULE_CHARACTERS = frozenset(
     "一上下不中主也事人什他以任伴何作保信停像先光全再切判到割助半危即去友反受可同吞否吧命和哈哥哪回在地多大天她好如妹姐子孩安完室害家密小少就工巧己式弟很得循心必忙快怎思急想意感我或所打扛承技把持挑接援支救教整文新方明是普暖最有朋服本束果某查根槽止正死永求江河法活海爸理瓶生甩由疼痛的目直看眠短研硬磕究窗立笑算累考者聊背能腕自致舞表要解象趣跳身逗通道那部都醒重防陪需高鼓"
+    "久之今住做取啥失掉攀晚晾棵水泳消深游火炭烤片甚百睡知篷粒苦衣走跟配露"
 )
 
 
@@ -146,7 +153,7 @@ def test_traditional_variants_match_simplified_crisis_level(traditional, simplif
 
 
 @pytest.mark.parametrize("message,expected", [
-    ("計畫下週跳樓", "possible"),
+    ("計畫下週跳樓", "high"),
     ("我想死妳", None),
 ])
 def test_word_level_plan_and_second_person_variant(message, expected):
```

## 4. 新增规则字

字面量新增共 **60** 字：26 字追加到变体清单与生产映射，34 字追加到无变体清单。既有条目未删改，无已有字因改写丢失，也未添加纯保留用的无行为字面量。另有画／畫两个 Unicode escape 保留码点，取舍见未决问题。

| 新增字 | 繁体／异体或说明 |
|---|---|
| 兰 | 蘭 |
| 几 | 幾 |
| 台 | 臺、檯、颱 |
| 够 | 夠 |
| 尽 | 盡、儘 |
| 层 | 層 |
| 岩 | 巖、巗 |
| 帐 | 帳 |
| 床 | 牀 |
| 来 | 來 |
| 树 | 樹 |
| 潜 | 潛 |
| 灯 | 燈 |
| 烧 | 燒 |
| 练 | 練 |
| 统 | 統 |
| 脉 | 脈 |
| 脱 | 脫 |
| 训 | 訓 |
| 设 | 設 |
| 过 | 過 |
| 随 | 隨 |
| 颗 | 顆 |
| 饭 | 飯 |
| 马 | 馬 |
| 长 | 長 |
| 久 | 常用繁体与简体同字，追加到无变体清单 |
| 之 | 常用繁体与简体同字，追加到无变体清单 |
| 今 | 常用繁体与简体同字，追加到无变体清单 |
| 住 | 常用繁体与简体同字，追加到无变体清单 |
| 做 | 常用繁体与简体同字，追加到无变体清单 |
| 取 | 常用繁体与简体同字，追加到无变体清单 |
| 啥 | 常用繁体与简体同字，追加到无变体清单 |
| 失 | 常用繁体与简体同字，追加到无变体清单 |
| 掉 | 常用繁体与简体同字，追加到无变体清单 |
| 攀 | 常用繁体与简体同字，追加到无变体清单 |
| 晚 | 常用繁体与简体同字，追加到无变体清单 |
| 晾 | 常用繁体与简体同字，追加到无变体清单 |
| 棵 | 常用繁体与简体同字，追加到无变体清单 |
| 水 | 常用繁体与简体同字，追加到无变体清单 |
| 泳 | 常用繁体与简体同字，追加到无变体清单 |
| 消 | 常用繁体与简体同字，追加到无变体清单 |
| 深 | 常用繁体与简体同字，追加到无变体清单 |
| 游 | 常用繁体与简体同字，追加到无变体清单 |
| 火 | 常用繁体与简体同字，追加到无变体清单 |
| 炭 | 常用繁体与简体同字，追加到无变体清单 |
| 烤 | 常用繁体与简体同字，追加到无变体清单 |
| 片 | 常用繁体与简体同字，追加到无变体清单 |
| 甚 | 常用繁体与简体同字，追加到无变体清单 |
| 百 | 常用繁体与简体同字，追加到无变体清单 |
| 睡 | 常用繁体与简体同字，追加到无变体清单 |
| 知 | 常用繁体与简体同字，追加到无变体清单 |
| 篷 | 常用繁体与简体同字，追加到无变体清单 |
| 粒 | 常用繁体与简体同字，追加到无变体清单 |
| 苦 | 常用繁体与简体同字，追加到无变体清单 |
| 衣 | 常用繁体与简体同字，追加到无变体清单 |
| 走 | 常用繁体与简体同字，追加到无变体清单 |
| 跟 | 常用繁体与简体同字，追加到无变体清单 |
| 配 | 常用繁体与简体同字，追加到无变体清单 |
| 露 | 常用繁体与简体同字，追加到无变体清单 |
| 画 | 繁体为畫；以 `\u753b` 保留原码点，未追加映射 |
| 畫 | 画的繁体；以 `\u756b` 保留原码点，未追加映射 |

## 5. 验收记录

以下命令用验收表的 `python` 记法列示，终端输出原样保留；退出码逐条注明。

### A1：原始全量

`python -m pytest -q -p no:cacheprovider`，在 `backend/` 下。

```text
........................................................................ [  4%]
........................................................................ [  8%]
........................................................................ [ 12%]
........................................................................ [ 17%]
........................................................................ [ 21%]
............................F........................................... [ 25%]
........................................................................ [ 29%]
........................................................................ [ 34%]
........................................................................ [ 38%]
........................................................................ [ 42%]
........................................................................ [ 47%]
........................................................................ [ 51%]
........................................................................ [ 55%]
....................EF.................................................. [ 59%]
........................................................................ [ 64%]
........................................................................ [ 68%]
........................................................................ [ 72%]
........................................................................ [ 77%]
........................................................................ [ 81%]
........................................................................ [ 85%]
............................EEE.E....................................... [ 89%]
........................................................................ [ 94%]
........................................................................ [ 98%]
...........................                                              [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10eca9940>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:457: in __init__
    self.server_bind()
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x110673e00>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:478: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10f7160b0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:457: in __init__
    self.server_bind()
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1106c2350>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:478: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10f715cc0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:457: in __init__
    self.server_bind()
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1103eccd0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:478: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x111148440>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:457: in __init__
    self.server_bind()
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x110750b00>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:478: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1111dfe70>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:457: in __init__
    self.server_bind()
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x110751ba0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/socketserver.py:478: PermissionError
=================================== FAILURES ===================================
____________ test_import_time_paths_use_session_temporary_directory ____________

    def test_import_time_paths_use_session_temporary_directory():
        import database
        from utils import media
    
        backend_dir = Path(__file__).resolve().parents[1]
        assert database.DB_PATH == os.environ["FIONA_DB_PATH"]
        assert media.UPLOADS_DIR == os.environ["FIONA_UPLOADS_DIR"]
>       assert not Path(database.DB_PATH).is_relative_to(backend_dir)
E       AssertionError: assert not True
E        +  where True = is_relative_to(PosixPath('<worktree>/backend'))
E        +    where is_relative_to = PosixPath('<worktree>/backend/.pytest-runtime/fiona-pytest-8091y9zo/test.db').is_relative_to
E        +      where PosixPath('<worktree>/backend/.pytest-runtime/fiona-pytest-8091y9zo/test.db') = Path('<worktree>/backend/.pytest-runtime/fiona-pytest-8091y9zo/test.db')
E        +        where '<worktree>/backend/.pytest-runtime/fiona-pytest-8091y9zo/test.db' = <module 'database' from '<worktree>/backend/database.py'>.DB_PATH

tests/test_beta_test_isolation.py:16: AssertionError
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x1105f9d00>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10eca9550>

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
../../../Fiona/backend/.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
../../../Fiona/backend/.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x110f56cf0>
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
E                       PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] operation not permitted

/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/base_events.py:1637: PermissionError
=============================== warnings summary ===============================
../../../Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  <repo>/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  <repo>/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_beta_test_isolation.py::test_import_time_paths_use_session_temporary_directory
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
2 failed, 1676 passed, 11 warnings, 5 errors in 44.86s
```

退出码：`1`。

这次运行共 1683 例：1676 通过、2 失败、5 setup 错误。临时目录位于 backend 内触发 `test_import_time_paths_use_session_temporary_directory` 的原断言；其余 1 failed + 5 errors 均为本地端口绑定 PermissionError，未发现判级或路由回归失败。没有修改这些旧测试。

### A1 补充：移到仓库根目录内的临时目录，排除 6 个本地端口用例

```sh
python -m pytest -q -p no:cacheprovider \
  --deselect=tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot \
  --deselect=tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive \
  --deselect=tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline \
  --deselect=tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work \
  --deselect=tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline \
  --deselect=tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
```

```text
........................................................................ [  4%]
........................................................................ [  8%]
........................................................................ [ 12%]
........................................................................ [ 17%]
........................................................................ [ 21%]
........................................................................ [ 25%]
........................................................................ [ 30%]
........................................................................ [ 34%]
........................................................................ [ 38%]
........................................................................ [ 42%]
........................................................................ [ 47%]
........................................................................ [ 51%]
........................................................................ [ 55%]
........................................................................ [ 60%]
........................................................................ [ 64%]
........................................................................ [ 68%]
........................................................................ [ 72%]
........................................................................ [ 77%]
........................................................................ [ 81%]
........................................................................ [ 85%]
........................................................................ [ 90%]
........................................................................ [ 94%]
........................................................................ [ 98%]
.....................                                                    [100%]
=============================== warnings summary ===============================
../../../Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  <repo>/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  <repo>/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1677 passed, 6 deselected, 11 warnings in 42.92s
```

退出码：`0`。

### A2：最终新增文件

`python -m pytest -q -p no:cacheprovider tests/test_crisis_recall_2026_10.py -v`，在 `backend/` 下。

```text
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
rootdir: <worktree>/backend
plugins: anyio-4.14.2
collected 137 items

tests/test_crisis_recall_2026_10.py .................................... [ 26%]
........................................................................ [ 78%]
.............................                                            [100%]

=============================== warnings summary ===============================
tests/test_crisis_recall_2026_10.py: 10 warnings
  <repo>/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_crisis_recall_2026_10.py::test_possible_turn_bypasses_candidates_pending_and_tools[R1-route-pending]
  <repo>/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 137 passed, 11 warnings in 0.92s =======================
```

退出码：`0`。

### A3：测试文件范围

在 `backend/` 下原样执行 `git diff --stat -- backend/tests`：输出为空，退出码 `0`。此相对路径在 backend 工作目录内不能检查仓库根路径，因此补在仓库根目录执行同命令：

```text
 backend/tests/test_crisis_resource_paths.py | 15 +++++++--------
 backend/tests/test_traditional_crisis.py    |  9 ++++++++-
 2 files changed, 15 insertions(+), 9 deletions(-)
```

退出码：`0`。

新文件未被跟踪，另用 `git diff --no-index --stat -- /dev/null backend/tests/test_crisis_recall_2026_10.py` 只读补查：

```text
 .../tests/test_crisis_recall_2026_10.py            | 393 +++++++++++++++++++++
 1 file changed, 393 insertions(+)
```

退出码：`1`。

这里退出码 `1` 是 no-index diff 发现新文件内容的正常含义。合并 status，可确认测试变动为授权的两个已有文件和一个新增文件。

### A4：不可改测试

在 `backend/` 和仓库根目录分别原样执行：

`git diff -- backend/tests/test_beta_safety.py backend/tests/test_o1_resource_cleanup.py`

两次输出都为空，两次退出码均 `0`。

### A5：授权 possible 分支

原样 diff 见第 3 节。附加 AST 核验 high／mirror 断言分支，及服药日常边界诊断：

```text
A5: high and mirror assertion branches are unchanged
服了一瓶中药: None
吃了一瓶补药: None
服了半瓶药: possible
药都准备好了，今晚就结束疗程: None
跳河多久会死: high
```

退出码：`0`。

另外，两个既有测试文件中非授权测试函数的 AST（含参数化装饰器）均与 diff 重建的原文件一致；变体清单既有键值未变、无变体原字符串保持前缀；四组规范数组与规格各个 Python 块 AST literal 相等。上述核验退出码均 `0`。

`git diff --check`：输出为空，退出码 `0`。

### A6：盲测

未执行。规格明确由主会话持有盲测语料并独立验收，本轮未猜测或替代该语料。

## 6. 未决问题

1. **A1 完整验收未完成。** 原始全量的 6 个旧 HTTP 用例需要本地端口，受到绑定限制；已明确排除补跑，其余 1677 全过。需要主会话在可运行这些既有用例的验证环境重跑 A1，确认 1683 全过。原始命令还暴露临时目录断言：验证目录改在仓库根内、backend 外后该旧测试通过。临时目录安排与补跑筛选属于本轮自行选择的验证方式，没有修改旧测试或实现以掩盖失败。
2. **删除会话的 pending 清理与 3.2 字面冲突。** 未授权改的 `test_o1_resource_cleanup.py::test_deleted_conversation_cleanup_failure_keeps_crisis_resource_and_error`（possible 参数，约 :70）及 `::test_deleted_conversation_error_disconnect_still_cleans_pending_and_mode`（约 :128）要求 ResourceNotFound 后清 pending／mode。按第 0 节优先保留旧测试和既有 finally cleanup；正常受保护轮保留 pending，但删除／不可用会话错误仍会清理。是否另开单调整该异常语义需人工决定。
3. **手动镜子模式取舍。** 3.2 要求保留 pending，同时说镜子模式保持现状；原手动镜子会清 pending。新增默认关闭的 `stream_mirror(..., preserve_pending=False)` 配套路由参数，受保护轮传 True 跳过这次清理，镜子回复／计费／资源不变。这是为 pending 保留作出的自行判断，超出仅编辑 run_chat 函数体的最窄解释，已明示。high、None 与信息语境继续默认行为。
4. **明确例外的原清理保留。** 按 3.2.5，显式 image／image_edit 与 image_edit_requires_reference 固定引导仍在 guard 前，原来的 clear_pending 保留。因此本轮不将“possible 不清 pending”扩大到这些明确保留现状的路径。
5. **画／畫的字符清单张力。** 3.1 明确要保留逐字归一，既有测试要求計畫→计畫、計画→计画；4.3 又要求新增有变体规则字追加映射。未添加会改变上述行为的畫→画映射；用 raw regex 的 `\u753b`／`\u756b` 表示原码点，因此两个字不进入“字面量”AST oracle，也未错误列为无异体。已另增计划六种拼法与设计／统计词边界用例验证。此实现选择须人工验收。
6. **新增方法的他人语境。** 自行把第 2／3 条 contextual 词表扩到新增求死方法，可能使过去 None 的第三人称危机表达成为 possible，以保持已有“谈论他人危机”机制且避免误升 high；这些轮次仍非第 4 条定义的信息／求助豁免，故受 possible 路由保护。第 4 条未扩展到新方法，按规格原定义处理。
7. **新增规则边界的自行判断。** 沿用短跨度正则窗口，不引入语义模型；量化方法询问另外覆盖多长与几字数量；自身吊死／自尽／寻死的算了／吧结尾、了断双词序、怎么死最快／不痛／不疼属于现象泛化。裸了断要求明确自身意图与句尾／标点／了或吧，普通了断关系不升级。跟随他人要求第 2／3 条中的完成式自杀／轻生／自尽／吊死，避免信息或否认语境误升。泛药新增 high 限整瓶／全部／所有加完成动作，普通一瓶及泛药半瓶／一把维持原判级；备药后的结束须为句尾以排除结束疗程。单纯位置 possible 仅天台完成式句尾，其他普通位置或接日常活动不由位置升档。消失与一了百了要求自身表达及边界。上述各项是自行确定的规则语义，范围见第 1 节，不承诺覆盖未提供的盲测。
8. **新增日常剥离及英语泛化的自行判断。** 在规格成语／吊床／取暖／游泳基础上扩到吊灯／吊兰、做饭／生火／烧烤、潜水／救援／训练、露营／帐篷／攀岩／晾衣；仅删除匹配片段，不删除整句，以保留独立危险信号。英语除规格原句外覆盖 wanna／gonna、hanging／hurting／cutting、vanish、life、permanently 等同类写法。这些是主动泛化选择。
9. **额外测试与验收路径选择。** 规格 91 句之外增加 46 例独立护栏／接口／路由测试；R5和显式图片复用规格允许的既有用例，R3无改句。A3／A4从 backend 执行相对路径输出空，补在根目录验证；未跟踪新增文件另外以 no-index diff 和展开 status 核查，未把空输出误作完整检查结果。
10. **A6 待主会话。** 盲测未提供，需由主会话完成日常不升级与危机召回验收。除此处及上述明确冲突／验证限制外，没有已知未实现功能。

## 7. 最终 git 状态

原样执行 `git status --porcelain`：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/safety.py
 M backend/services/chat_service.py
 M backend/tests/test_crisis_resource_paths.py
 M backend/tests/test_traditional_crisis.py
 M backend/utils/traditional_chinese.py
 M docs/ARCHITECTURE.md
?? backend/tests/test_crisis_recall_2026_10.py
?? docs/tasks/2026-10-05-crisis-recall/
```

退出码：`0`。

补充展开未跟踪文件：`git status --porcelain --untracked-files=all`：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/safety.py
 M backend/services/chat_service.py
 M backend/tests/test_crisis_resource_paths.py
 M backend/tests/test_traditional_crisis.py
 M backend/utils/traditional_chinese.py
 M docs/ARCHITECTURE.md
?? backend/tests/test_crisis_recall_2026_10.py
?? docs/tasks/2026-10-05-crisis-recall/02-spec.md
?? docs/tasks/2026-10-05-crisis-recall/03-report.md
```

退出码：`0`。`02-spec.md` 在任务开始时已存在且为未跟踪文件，本轮未修改；本轮持久改动仅为白名单中的 11 个文件。测试临时产物已清除。新增测试与本报告仍未跟踪，因此普通 `git diff --stat` 不显示它们。

## 第 1 轮返修

本节按 `05-fix-round1.md` 记录当前结果；上文第 0 轮的规则、测试数与验收结论保留为历史记录。本轮按返修单原文完成收窄，尚未通过验收：F1/F2/F3 的要求存在可复现冲突，产生 5 个非 HTTP 测试失败，R4 也多出 2 句判级变化。未自行放宽 F1/F2/F3 或修改旧测试期望。

### F1–F7 与文件对应

| 项目 | 文件与结果 |
|---|---|
| F1 | `backend/safety.py` 从 `9061a52` 重建，仅两处计划词替换、原归一辅助函数及其调用、原信息语境接口；四条日常剥离、他人扩词、方法/生命/high/possible/英文扩充与 contextual_death 全部撤回。 |
| F2 | `backend/utils/traditional_chinese.py` 完全恢复基线，字节相等，diff 为空。 |
| F3 | `backend/tests/test_traditional_crisis.py` 恢复基线，仅保留「計畫下週跳樓」的 high 期望；无变体清单末尾追加画/畫及指定两行注释，其余逐字相同。 |
| F4 | `backend/tests/test_crisis_resource_paths.py` 第 0 轮授权改动保持原样，本轮未编辑；`backend/services/chat_service.py` 已通过复核的路由实现也未编辑。 |
| F5 | `backend/tests/test_crisis_recall_2026_10.py` 删除四组 SPEC 语料 91 例及依赖旧扩充规则的护栏 15 例；保留路由、镜子/看图、固定引导、接口、计划词边界，加入指定計畫 11 例。新增测试现共 42 例（137−91−15+11）；11 个新增計畫参数全部通过。 |
| F6 | `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md` 保留路由保护并补計畫/計劃一致性；`PLAN.md` 删除旧补词完成描述，在 2026-09-29 之后新建 2026-10-05 小节，两条完成记录及下一单待办。 |
| F7 | 本报告末尾追加本节，提供原样 diff、测试数及 R1–R4 的验收输出、退出码和未决问题。 |

字面规则清单本轮只按 F3 追加「画」「畫」，未加畫→画映射，保留既有逐字归一行为。`test_beta_safety.py`、`test_o1_resource_cleanup.py` 与基线字节相等。独立子代理对 F1–F6 的只读复核确认，当前文件符合返修单字面要求，并独立复现下述冲突。

### R1：完整后端验收

在 `backend/` 下执行验收命令 `python -m pytest -q -p no:cacheprovider`，收集总数 **1546 + 42 = 1588**。以下为原样输出尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_crisis_recall_2026_10.py::test_plan_spellings_and_design_word_boundaries[\u6211\u5728\u505a\u8a2d\u8a08\u756b\u9762\uff0c\u4e3b\u89d2\u6700\u5f8c\u8df3\u6cb3-None]
FAILED tests/test_crisis_recall_2026_10.py::test_plan_spellings_and_design_word_boundaries[\u7d71\u8a08\u756b\u9762\u986f\u793a\u4e0a\u540a\u4eba\u6578-possible]
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
FAILED tests/test_traditional_crisis.py::test_crisis_rule_character_variants_normalize_back_to_rule_characters
FAILED tests/test_traditional_crisis.py::test_design_frame_mentions_keep_baseline_crisis_level[\u904a\u6232\u8a2d\u8a08\u756b\u9762\u88e1\u52a0\u4e00\u6bb5\u8df3\u6d77\u7684\u52d5\u756b-None]
FAILED tests/test_traditional_crisis.py::test_design_frame_mentions_keep_baseline_crisis_level[\u96fb\u5f71\u8a2d\u8a08\u756b\u9762\u6709\u81ea\u6bba\u93e1\u982d-possible]
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
6 failed, 1577 passed, 11 warnings, 5 errors in 43.68s
```

退出码：`1`。其中 6 个旧 HTTP 用例（1 failed、5 errors）在本地端口绑定处报 `PermissionError: [Errno 1] Operation not permitted`；其余 5 个失败是返修单冲突引起的字符覆盖与繁体词边界问题，不能归为环境限制。

补跑仅排除题给的这 6 个旧 HTTP 用例，仍在 `backend/` 下：

```sh
python -m pytest -q -p no:cacheprovider \
  --deselect=tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot \
  --deselect=tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive \
  --deselect=tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline \
  --deselect=tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work \
  --deselect=tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline \
  --deselect=tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
```

原样输出尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_crisis_recall_2026_10.py::test_plan_spellings_and_design_word_boundaries[\u6211\u5728\u505a\u8a2d\u8a08\u756b\u9762\uff0c\u4e3b\u89d2\u6700\u5f8c\u8df3\u6cb3-None]
FAILED tests/test_crisis_recall_2026_10.py::test_plan_spellings_and_design_word_boundaries[\u7d71\u8a08\u756b\u9762\u986f\u793a\u4e0a\u540a\u4eba\u6578-possible]
FAILED tests/test_traditional_crisis.py::test_crisis_rule_character_variants_normalize_back_to_rule_characters
FAILED tests/test_traditional_crisis.py::test_design_frame_mentions_keep_baseline_crisis_level[\u904a\u6232\u8a2d\u8a08\u756b\u9762\u88e1\u52a0\u4e00\u6bb5\u8df3\u6d77\u7684\u52d5\u756b-None]
FAILED tests/test_traditional_crisis.py::test_design_frame_mentions_keep_baseline_crisis_level[\u96fb\u5f71\u8a2d\u8a08\u756b\u9762\u6709\u81ea\u6bba\u93e1\u982d-possible]
5 failed, 1577 passed, 6 deselected, 11 warnings in 44.46s
```

退出码：`1`。未改动这些既有 HTTP 测试；完整 R1 仍需主会话在沙箱外重跑。

新增文件单独验证：`python -m pytest -q -p no:cacheprovider tests/test_crisis_recall_2026_10.py`。原样输出尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_crisis_recall_2026_10.py::test_plan_spellings_and_design_word_boundaries[\u6211\u5728\u505a\u8a2d\u8a08\u756b\u9762\uff0c\u4e3b\u89d2\u6700\u5f8c\u8df3\u6cb3-None]
FAILED tests/test_crisis_recall_2026_10.py::test_plan_spellings_and_design_word_boundaries[\u7d71\u8a08\u756b\u9762\u986f\u793a\u4e0a\u540a\u4eba\u6578-possible]
2 failed, 40 passed, 11 warnings in 0.87s
```

退出码：`1`。通过的 40 例包含本轮新增的 11 句計畫语料、接口测试及保留的全部路由/镜子/看图/固定引导测试。失败的 2 例为繁体设计/统计词边界，不是新增計畫语料。

### R2：繁简映射恢复

`git diff 9061a52 --stat -- backend/utils/traditional_chinese.py` 与 `git diff 9061a52 -- backend/utils/traditional_chinese.py` 均无输出：

```text
```

两条命令退出码均为 `0`。本轮没有保留第 0 轮的任何新映射。

### R3：safety.py 原样 diff

`git diff 9061a52 -- backend/safety.py` 的完整原样输出：

```diff
diff --git a/backend/safety.py b/backend/safety.py
index 2c8e35d..07b3f42 100644
--- a/backend/safety.py
+++ b/backend/safety.py
@@ -53,11 +53,11 @@ _METHOD_QUERY = re.compile(
 _HIGH_PATTERNS = tuple(re.compile(pattern) for pattern in (
     r"(?:我|自己|本人).{0,10}(?:想死(?![你他她它])|要死(?!了|[你他她它])|去死|不想(?:再)?活(?!得)|活不下去|自杀|轻生)",
     r"(?:好想死|不如死了算了|生无可恋.{0,8}想死|活着没意思.{0,8}(?:想死|自杀)|活着好累.{0,8}不想再活)",
-    r"(?:不想(?:再)?活(?!得)|活不下去|活着没(?:有)?(?:意思|劲).{0,8}(?:不如死|想死|自杀)|(?<![你他她它])不如死了|(?<![你他她它])(?:想|要|打算|准备|计划|考虑).{0,4}(?:自杀|轻生|去死|死了算了)|(?:想|打算|准备|考虑|(?<![现正实])在|(?<![只需重主])要)结束(?:自己|我|这)?(?:的)?(?:生命|一切))",
+    r"(?:不想(?:再)?活(?!得)|活不下去|活着没(?:有)?(?:意思|劲).{0,8}(?:不如死|想死|自杀)|(?<![你他她它])不如死了|(?<![你他她它])(?:想|要|打算|准备|(?<![设统])计(?:划|画|畫)|考虑).{0,4}(?:自杀|轻生|去死|死了算了)|(?:想|打算|准备|考虑|(?<![现正实])在|(?<![只需重主])要)结束(?:自己|我|这)?(?:的)?(?:生命|一切))",
     r"(?:我|自己|本人).{0,8}没有活下去的理由",
     r"(?:我|自己|本人).{0,10}(?:想结束这一切|结束(?:自己|我)(?:的)?生命|伤害(?:我)?自己|割(?:了)?(?:我)?自己|了结(?:我)?自己|自我了断|杀了(?:我)?自己|把(?:我)?自己杀了|自残|自伤)|想结束(?:自己|我)(?:的)?生命",
     r"(?:我|自己|本人).{0,6}(?:割腕|上吊|吞药|跳楼(?![价机]))",
-    r"(?:想|要|准备|打算|计划|考虑).{0,8}(?:割腕|跳楼(?![价机])|跳下去|上吊|吞药|跳河|跳江|跳海|自残|自伤|伤害自己)",
+    r"(?:想|要|准备|打算|(?<![设统])计(?:划|画|畫)|考虑).{0,8}(?:割腕|跳楼(?![价机])|跳下去|上吊|吞药|跳河|跳江|跳海|自残|自伤|伤害自己)",
     r"(?:楼上|楼顶|窗户|桥上).{0,8}跳下去",
     r"(?:我|本人|自己).{0,10}(?:写好遗书|遗书写好|(?:攒|准备|买|吞|吃|服).{0,5}安眠药)",
     r"(?:吞|吃|服)(?:了|下|光)?.{0,4}(?:一整?瓶|半瓶|一把|整瓶|全部|所有|很多|好多)安眠药",
@@ -75,9 +75,13 @@ _POSSIBLE_PATTERNS = tuple(re.compile(pattern) for pattern in (
 ))
 
 
+def _normalize_crisis_text(text: str) -> str:
+    return normalize_traditional(re.sub(r"\s+", "", text or "").lower().replace("’", "'"))
+
+
 def assess_crisis(text: str) -> Literal["high", "possible"] | None:
     """Return high for direct danger, possible for related talk, else None."""
-    normalized = normalize_traditional(re.sub(r"\s+", "", text or "").lower().replace("’", "'"))
+    normalized = _normalize_crisis_text(text)
     if not normalized:
         return None
     # Remove common idioms before checking risk words, so a separate explicit
@@ -109,6 +113,13 @@ def assess_crisis(text: str) -> Literal["high", "possible"] | None:
     return "possible" if joking_phrase or contextual_mention else None
 
 
+def is_informational_crisis_context(text: str) -> bool:
+    """Allow existing informational/help routing only for a possible-level turn."""
+    return assess_crisis(text) == "possible" and bool(
+        _CONTEXTUAL_MENTIONS[3].search(_normalize_crisis_text(text))
+    )
+
+
 def detect_crisis(text: str) -> bool:
     """Compatibility gate for callers that only need the high level."""
     return assess_crisis(text) == "high"
```

退出码：`0`。独立复核按基线与指定替换重建全文比对相等，没有其他判级规则改动。

### R4：基线测试字符串的新旧判级比较

在 `backend/` 下执行以下比较。三个测试文件的源代码全部取自 `9061a52`；基线 safety 和基线归一表在内存中执行，工作树 safety 单独导入，不创建基线副本或验证脚本文件。

```sh
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
import ast
from pathlib import Path
import subprocess

revision = "9061a52"
def baseline(path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], text=True)

traditional = {"__name__": "baseline_traditional"}
exec(compile(baseline("backend/utils/traditional_chinese.py"), "9061a52:backend/utils/traditional_chinese.py", "exec"), traditional)
old = {"__name__": "baseline_safety", "normalize_traditional": traditional["normalize_traditional"]}
old_source = baseline("backend/safety.py").replace("from utils.traditional_chinese import normalize_traditional", "")
exec(compile(old_source, "9061a52:backend/safety.py", "exec"), old)
import safety
assert Path(safety.__file__).resolve() == Path("safety.py").resolve()

literals = []
for name in ("test_beta_safety.py", "test_traditional_crisis.py", "test_crisis_resource_paths.py"):
    tree = ast.parse(baseline(f"backend/tests/{name}"))
    values = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    literals.extend(values)
    print(f"{name}: {len(values)} string literals")
changes = sorted({(text, old["assess_crisis"](text), safety.assess_crisis(text)) for text in literals if old["assess_crisis"](text) != safety.assess_crisis(text)})
print(f"total literals: {len(literals)}; unique literals: {len(set(literals))}; changed unique literals: {len(changes)}")
for text, before, after in changes:
    print(f"{text!r}: {before!r} -> {after!r}")
assert changes == [("計畫下週跳樓", "possible", "high")], changes
print("R4 PASS: only 計畫下週跳樓 changes crisis level")
PY
```

完整原样输出：

```text
test_beta_safety.py: 561 string literals
test_traditional_crisis.py: 454 string literals
test_crisis_resource_paths.py: 251 string literals
total literals: 1266; unique literals: 690; changed unique literals: 3
'計畫下週跳樓': 'possible' -> 'high'
'遊戲設計畫面裡加一段跳海的動畫': None -> 'high'
'電影設計畫面有自殺鏡頭': 'possible' -> 'high'
Traceback (most recent call last):
  File "<stdin>", line 27, in <module>
AssertionError: [('計畫下週跳樓', 'possible', 'high'), ('遊戲設計畫面裡加一段跳海的動畫', None, 'high'), ('電影設計畫面有自殺鏡頭', 'possible', 'high')]
```

退出码：`1`。共比较 1266 个字符串字面量、690 个唯一字符串。预期只有「計畫下週跳樓」变化，实际有 3 句；两句额外变化与完整测试中的旧繁体设计画面失败一致。

### 未决问题

1. **F1/F2/F3 无法同时满足完整验收。** F1 指定直接写 `(?<![设统])计(?:划|画|畫)`，新增规则字实际为画/畫/设/统；F3 仅允许追加画/畫，基线两清单均没有设/统，覆盖测试报 `unlisted rule chars: 统设; oracle chars absent from rules: none`。按 F2 完全恢复的基线映射也没有設→设、統→统，所以「設計畫面」「統計畫面」不能被只含简体的前字边界挡住，4 个繁体词边界参数升为 high（2 个旧测试、2 个保留的新测试）。R4 中的两句额外变化是「遊戲設計畫面裡加一段跳海的動畫」None→high，以及「電影設計畫面有自殺鏡頭」possible→high。根因由独立代理确认，F1 已严格恢复，不是遗漏撤回第 0 轮规则。
2. **待人工决定的最小例外。** 可在 F2 恢复基线后仅追加「设: 設」「统: 統」，F3 的 `RULE_CHARACTER_VARIANTS` 同时仅追加两项，F1 原文不变；这会偏离 F2 的空 diff 与 F3 的仅画/畫要求，因此本轮未擅自实施，已向用户请求决定。仅改 F3 不能修复，因为归一断言和繁体词边界仍会失败。没有新增判级词或额外判级规则，没有改旧测试输入/断言来掩盖失败。
3. **6 个旧 HTTP 用例待外部重跑。** 本轮按用户指示明确记录本地端口绑定限制，并逐个 deselect 补跑；这只是验证方法，不是实现变更或完整 R1 通过。测试临时产物由原有隔离夹具清理，仓库根与 backend 下均无 `.pytest-runtime/`；未新增临时脚本、测试日志、缓存或字节码。
4. **下一单。** 第 0 轮判级扩充及其验收语料按 F5 撤出本单，危机判级改为规则加模型复核仍是下一单待办，本轮未实现。上文第 0 轮新增判级规则的自行判断与验收结论不再代表当前实现。

补充检查：`git diff --check` 无输出，退出码 `0`；任务输入 `02-spec.md`、`04-review.md`、`05-fix-round1.md` 未修改。本轮实际修改或恢复 9 个文件；路由实现及 F4 测试两个文件保留第 0 轮修改，本轮未再次编辑。

## 第 1 轮返修·勘误

按 `05-fix-round1.md` 末尾「勘误（2026-10-05，主会话）」实施最小例外。本节更新前节 F2/F3、R2/R4 及验收结论；前节保留为历史记录。原有 5 个非 HTTP 失败和 R4 多出的 2 句变化已消除。

- F2：`backend/utils/traditional_chinese.py` 在 `9061a52` 字典末尾仅追加 `"设": "設"`、`"统": "統"` 两行；其余与基线逐字节相同。
- F3：`backend/tests/test_traditional_crisis.py` 的 `RULE_CHARACTER_VARIANTS` 在基线末尾仅追加这两项；`NO_VARIANT_RULE_CHARACTERS` 维持仅追加「画畫」及指定注释，保留「計畫下週跳樓」的 `high` 期望，其余与基线逐字节相同。独立只读审查按上述授权变更重建基线并完成全文比对。
- 本次持久修改仅这两个文件和本报告。未增加判级规则；新增规则字映射为设/設、统/統，画/畫继续保持既有逐字归一行为。

### F2/F3 与 R2：原样 diff

`git diff 9061a52 -- backend/utils/traditional_chinese.py backend/tests/test_traditional_crisis.py` 的完整原样输出：

```diff
diff --git a/backend/tests/test_traditional_crisis.py b/backend/tests/test_traditional_crisis.py
index 283336c..359ed7f 100644
--- a/backend/tests/test_traditional_crisis.py
+++ b/backend/tests/test_traditional_crisis.py
@@ -33,13 +33,16 @@ RULE_CHARACTER_VARIANTS = {
     "简": "簡", "系": "係繫", "紧": "緊", "级": "級", "线": "線", "联": "聯",
     "认": "認", "评": "評", "询": "詢", "语": "語", "诺": "諾", "轮": "輪",
     "边": "邊", "达": "達", "镜": "鏡", "险": "險",
+    "设": "設", "统": "統",
 }
 
 # Rule characters without a traditional/alternate form used by this classifier.
 # This is intentionally a literal whitelist, independent of safety.py and of
 # RULE_CHARACTER_VARIANTS, so any newly added Chinese rule character fails review.
 NO_VARIANT_RULE_CHARACTERS = frozenset(
-    "一上下不中主也事人什他以任伴何作保信停像先光全再切判到割助半危即去友反受可同吞否吧命和哈哥哪回在地多大天她好如妹姐子孩安完室害家密小少就工巧己式弟很得循心必忙快怎思急想意感我或所打扛承技把持挑接援支救教整文新方明是普暖最有朋服本束果某查根槽止正死永求江河法活海爸理瓶生甩由疼痛的目直看眠短研硬磕究窗立笑算累考者聊背能腕自致舞表要解象趣跳身逗通道那部都醒重防陪需高鼓"
+    # 画/畫 appear literally in the plan-word pattern; 畫 is deliberately not mapped
+    # (see test_plan_word_does_not_cross_word_boundaries).
+    "一上下不中主也事人什他以任伴何作保信停像先光全再切判到割助半危即去友反受可同吞否吧命和哈哥哪回在地多大天她好如妹姐子孩安完室害家密小少就工巧己式弟很得循心必忙快怎思急想意感我或所打扛承技把持挑接援支救教整文新方明是普暖最有朋服本束果某查根槽止正死永求江河法活海爸理瓶生甩由疼痛的目直看眠短研硬磕究窗立笑算累考者聊背能腕自致舞表要解象趣跳身逗通道那部都醒重防陪需高鼓画畫"
 )
 
 
@@ -146,7 +149,7 @@ def test_traditional_variants_match_simplified_crisis_level(traditional, simplif
 
 
 @pytest.mark.parametrize("message,expected", [
-    ("計畫下週跳樓", "possible"),
+    ("計畫下週跳樓", "high"),
     ("我想死妳", None),
 ])
 def test_word_level_plan_and_second_person_variant(message, expected):
diff --git a/backend/utils/traditional_chinese.py b/backend/utils/traditional_chinese.py
index 15076ac..77273eb 100644
--- a/backend/utils/traditional_chinese.py
+++ b/backend/utils/traditional_chinese.py
@@ -135,6 +135,8 @@ SIMPLIFIED_TO_TRADITIONAL_VARIANTS: dict[str, str] = {
     "还": "還",
     "国": "國",
     "拨": "撥",
+    "设": "設",
+    "统": "統",
 }
 
 _TRANSLATION = str.maketrans({
```

退出码：`0`。R2 的生产文件 diff 只有两行映射，符合勘误。

### R4：基线测试字面量比对

独立子代理在 `backend/` 下执行如下命令；三个测试文件、旧版 safety 与归一表均来自 `9061a52`，当前 safety 导入路径断言为本 worktree。源码仅在内存执行，不创建副本或脚本文件。

```sh
PYTHONDONTWRITEBYTECODE=1 <repo>/backend/.venv/bin/python - <<'PY'
import ast
from pathlib import Path
import subprocess

revision = "9061a52"
def baseline(path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], text=True)

traditional = {"__name__": "baseline_traditional"}
exec(compile(baseline("backend/utils/traditional_chinese.py"), "9061a52:backend/utils/traditional_chinese.py", "exec"), traditional)
old = {"__name__": "baseline_safety", "normalize_traditional": traditional["normalize_traditional"]}
old_source = baseline("backend/safety.py").replace("from utils.traditional_chinese import normalize_traditional", "")
exec(compile(old_source, "9061a52:backend/safety.py", "exec"), old)
import safety
assert Path(safety.__file__).resolve() == Path("safety.py").resolve()

literals = []
for name in ("test_beta_safety.py", "test_traditional_crisis.py", "test_crisis_resource_paths.py"):
    tree = ast.parse(baseline(f"backend/tests/{name}"))
    values = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    literals.extend(values)
    print(f"{name}: {len(values)} string literals")
changes = sorted({(text, old["assess_crisis"](text), safety.assess_crisis(text)) for text in literals if old["assess_crisis"](text) != safety.assess_crisis(text)})
print(f"total literals: {len(literals)}; unique literals: {len(set(literals))}; changed unique literals: {len(changes)}")
for text, before, after in changes:
    print(f"{text!r}: {before!r} -> {after!r}")
assert changes == [("計畫下週跳樓", "possible", "high")], changes
print("R4 PASS: only 計畫下週跳樓 changes crisis level")
PY
```

完整原样输出：

```text
test_beta_safety.py: 561 string literals
test_traditional_crisis.py: 454 string literals
test_crisis_resource_paths.py: 251 string literals
total literals: 1266; unique literals: 690; changed unique literals: 1
'計畫下週跳樓': 'possible' -> 'high'
R4 PASS: only 計畫下週跳樓 changes crisis level
```

退出码：`0`。共 1266 个字符串字面量、690 个唯一字符串，仅「計畫下週跳樓」从 `possible` 变成 `high`；两句繁体「設計畫面」不再升级。

### 测试结果

所有测试在 `backend/` 下使用用户指定的解释器和 `PYTHONDONTWRITEBYTECODE=1`，禁用 pytest 缓存。为满足不读写 worktree 外文件、不留下临时文件，内存包装器调用指定解释器的 `-m pytest`，并用 `TMPDIR` 和 `--basetemp` 将临时库、上传目录及 pytest 临时目录约束在 worktree 内，运行结束自动清理。最终两次全量测试的临时根位于 worktree 根目录，满足既有测试要求的「backend 外」。全量的实际包装命令为：

```sh
PYTHONDONTWRITEBYTECODE=1 <repo>/backend/.venv/bin/python - <<'PY'
import os
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory(prefix=".pytest-runtime-", dir=Path.cwd().parent) as runtime:
    result = subprocess.run([
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "--basetemp", str(Path(runtime) / "cases"),
    ], env=dict(os.environ, TMPDIR=runtime))
    exit_code = result.returncode
sys.exit(exit_code)
PY
```

#### 定向回归

包装器中 pytest 参数为 `-q -p no:cacheprovider --basetemp <临时根>/cases tests/test_traditional_crisis.py tests/test_crisis_recall_2026_10.py tests/test_crisis_resource_paths.py`。原样输出尾部：

```text
=============================== warnings summary ===============================
tests/test_traditional_crisis.py: 10 warnings
  <repo>/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_traditional_crisis.py::test_traditional_crisis_chat_persists_and_sends_original
  <repo>/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
205 passed, 11 warnings in 2.64s
```

退出码：`0`。205 例全部通过，包括字符覆盖、繁体设计/统计词边界、11 句計畫语料及保留的路由用例。

#### R1：完整后端测试

总数仍为 **1546 + 42 = 1588**，本次只追加字典项，未增加测试用例。原样输出尾部：

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 1582 passed, 11 warnings, 5 errors in 48.98s
```

退出码：`1`。唯一失败及 5 个 setup errors 均在绑定本地端口时报 `PermissionError: [Errno 1] Operation not permitted`，对应用户预告的 6 个环境受限用例；无其他失败。

#### 仅排除 6 个端口用例的补跑

实际包装命令如下，临时路径约束与完整测试一致：

```sh
PYTHONDONTWRITEBYTECODE=1 <repo>/backend/.venv/bin/python - <<'PY'
import os
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory(prefix=".pytest-runtime-", dir=Path.cwd().parent) as runtime:
    result = subprocess.run([
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "--basetemp", str(Path(runtime) / "cases"),
        "--deselect=tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot",
        "--deselect=tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive",
        "--deselect=tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline",
        "--deselect=tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work",
        "--deselect=tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline",
        "--deselect=tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch",
    ], env=dict(os.environ, TMPDIR=runtime))
    exit_code = result.returncode
sys.exit(exit_code)
PY
```

原样输出尾部：

```text
=============================== warnings summary ===============================
../../../Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  <repo>/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  <repo>/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1582 passed, 6 deselected, 11 warnings in 48.56s
```

退出码：`0`。1582 例全部通过，6 例仅 deselect；完整 R1 仍需主会话在沙箱外重跑。

### 检查与未决问题

1. **仍待外部验证：6 个本地端口用例。** 本次未修改或绕过这 6 个既有测试的实现和断言，主会话需在沙箱外完成完整 R1。F2/F3、R2、R4 无已知实现未决问题；前节未决问题 1、2 已由勘误授权并修复。
2. **验证设置修正，已解决。** 首次完整测试把临时根放在 `backend/` 内，引起额外的 `test_import_time_paths_use_session_temporary_directory` 失败；这是本次自行选择的验证设置与既有隔离断言冲突，不是实现缺陷，也未修改旧测试。改用 worktree 根下临时目录后重跑，该用例通过。首次运行的原样尾部仍记录如下，以保留验证过程：

```text
=========================== short test summary info ============================
FAILED tests/test_beta_test_isolation.py::test_import_time_paths_use_session_temporary_directory
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
2 failed, 1581 passed, 11 warnings, 5 errors in 46.54s
```

该次退出码：`1`。上述重跑结果取代该次验收结论。

补充检查：`git diff --check` 无输出，退出码 `0`；运行结束检查 worktree 根与 `backend/`，无 `.pytest-runtime*`、`.pytest_cache` 或 `__pycache__` 遗留。本次没有执行 git 写命令，没有修改任务输入文件，没有遗留临时脚本、日志、库、上传文件或字节码。
