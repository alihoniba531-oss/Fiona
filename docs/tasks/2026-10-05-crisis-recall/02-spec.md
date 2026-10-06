# 规格：危机识别补词与「可能相关」兜底（2026-10-05）

- **基线**：`main` HEAD `9061a52`。`backend/safety.py` 共 114 行，`backend/tests` 全量 **1546 passed**（2026-10-05 实测）。下文行号都指这个版本。
- **依据**：2026-10-04 全项目待修清单 K1–K4。用户 2026-10-05 的拍板见第 1 节。
- **范围**：只改后端危机判级（`backend/safety.py`，必要时 `backend/utils/traditional_chinese.py`），以及 `backend/services/chat_service.py` 里对「可能相关（possible）」级别的路由。不改前端，不改提示词文案，不改计费规则。

## 0. 硬规则（违反任一条即返工）

- **已有测试的输入和断言一律不得修改。** 唯一的例外是第 4 节逐条列出的三处，而且只能按那里写的方式改。
- 如果某条已有测试和本规格冲突，**不要改测试**。调整实现，并在报告的「未决问题」里写清冲突。
- 不引入依赖，不改 `requirements.txt`。
- 不做真实网络调用，不调用真实模型，不下载。
- 不启动服务，不运行浏览器。
- 不写 git 状态（不 commit、不 stash、不切分支），不读 `.env*`。
- 派生子代理时，不要传 model 或 reasoning_effort 参数。
- 同一个文件不要让多个子代理并行改。
- **凡偏离本规格原文，或者本规格没写、由你自行决定的行为，都必须写进报告的「未决问题」**，不能只写在正文里。
- 只有影响「实现什么」的事才停下来；只影响「怎么验证」的事自己定。不回滚已完成的工作。
- **白名单**（只允许改动或新建这些文件）：
  - `backend/safety.py`；
  - `backend/utils/traditional_chinese.py`（只允许追加映射）；
  - `backend/services/chat_service.py`（只改第 3.2 节说的路由）；
  - `backend/tests/test_traditional_crisis.py`（只允许第 4 节说的两处）；
  - `backend/tests/test_crisis_resource_paths.py`（只允许第 4 节说的一处）；
  - 新建 `backend/tests/test_crisis_recall_2026_10.py`；
  - 文档：`CLAUDE.md:76`、`README.md:136`、`docs/ARCHITECTURE.md:84`、`PLAN.md`（在 :117 一带追加一行 2026-10-05 的记录）。这几处现在都写着「可能相关的轮次保留普通处理/工具」，要按第 3.2 节改写，只改相关句子，别的不动；
  - 本目录的 `03-report.md`（新建）。

## 1. 用户拍板（2026-10-05）

| # | 问题 | 决定 |
|---|---|---|
| D1 | 这一轮怎么修危机识别 | **先补词，再加兜底。** 补上漏判的说法和繁体「計畫」；再加一条保护：疑似危机的话不送去搜索或工具。要带危机语料、日常语料两道护栏。改用模型判级另开一单，等这一轮的结果再定 |

## 2. 背景（为什么要改）

`assess_crisis`（`safety.py:78`）只靠正则判级，结果有三档：
- `high`：进入危机分支，注入危机指引，开头先发 `{"crisis": true}`；
- `possible`：照常处理，只在回复末尾追加一段热线；
- `None`：完全不管。

已经实测确认的问题：

1. **明确的自杀表达被判成 `None`**：不给热线，不进危机分支，还会进入意图识别和工具。如果会话里正挂着待补参数，这句话会被直接当成参数值去执行工具（`chat_service.py:1163-1167` → `stream_pending`）。例如「我这就去跳河」「我需要结束生命」「我想自尽」「我把整瓶药都吞了」「i want to end it all」。原因如下：
   - `:59` 现在时方法组没有 跳河/跳江/跳海；
   - `:56` 的前置排除 `(?<![只需重主])要` 本意是排除「只要/需要结束一切」，却连「生命」分支也一起排掉了；
   - 规则里只有「上吊」，没有「吊死」；
   - 吞药规则要求动词在前，倒装句匹配不上；
   - 自尽、割脉、寻死、烧炭、一死了之、了断（不带「自我」）都不在词表里。
2. **致死方法询问只判成 `possible`**。例如「上吊要多久才会死」「跳楼几层会死」「安眠药吃几片会死」「哪种安眠药吃了醒不过来」。原因：`:46-51` 的 `_METHOD_QUERY` 触发词只有 怎么/如何/怎样/哪种/方式/最快/不痛/不疼/才能死；`:65` 的安眠药规则不认 醒不过来、不醒、睡不醒、一睡不醒、几片。
   - 「查一下跳楼几层会死」还会被 `recognize_intent_with_fallback`（`chat_service.py:838`）的「查/搜」兜底正则改写成联网搜索。
3. **繁体「計畫」**：`normalize_traditional` 只做逐字映射，不会把「計畫」变成「计划」（`test_plan_word_does_not_cross_word_boundaries` 钉住了这一点：「計畫」→「计畫」）。所以「計畫明天跳海」「計畫吞藥」判 `None`，「計畫下週跳樓」只判 `possible`。
4. 「上吊」子串会误伤日常话：「别在一棵树上吊死」「躺上吊床」现在判 `possible`。

## 3. 改动

### 3.1 判级（`safety.py`）

- **目标**：让第 5 节的新语料全部达标，同时现有测试全部通过（第 4 节授权的三处按授权改）。
- **写法不限**，但要满足：
  - 新增的规则要覆盖「现象」，不能只覆盖语料里的具体句子。例如补「吊死」时，要考虑「吊死自己 / 吊死算了 / 想吊死」这一类写法，而不是只写死某一句。
  - 新增的规则必须同时考虑日常用法，不能误伤。例如「在一棵树上吊死」是常见成语；「烧炭取暖」「跳海游泳」「一了百了」可能是日常话；「多久会死」也可能在问植物和宠物。
  - 「计划」类规则要同时认 `计划 / 计画 / 计畫`（也就是繁体「計劃 / 計畫 / 計画」归一之后的样子），并且不能让「设计画面」「统计画面」误判（`test_design_frame_mentions_keep_baseline_crisis_level` 必须继续通过）。**不要**改 `normalize_traditional` 的逐字映射行为来实现这一点。
- 已有规则可以改写，例如把 `:56` 的 `(?<![只需重主])要` 排除只限定在「一切」分支上。但改写后，所有已有测试都必须通过。
- **繁体覆盖性测试**：`test_crisis_rule_character_variants_normalize_back_to_rule_characters` 要求 `safety.py` 字面量里的每个汉字，都必须出现在测试的两张清单之一。新增规则用到新汉字时，按第 4 节第 3 条处理。
- 不改 `CRISIS_GUIDANCE`、`CRISIS_RESOURCE_NOTE` 的文字；不改 `assess_crisis` 和 `detect_crisis` 的签名和返回值类型。

### 3.2 「可能相关」兜底（`chat_service.py` 的 `run_chat`）

**新行为**：本轮判级为 `possible`，并且**不属于「信息或求助语境」**（定义见下）时，这一轮**不进入任何工具或参数路径**：
1. **不做生图候选确认**：跳过 `explicit_image_intent`，以及随后的 `recognize_intent_with_fallback` 和生图。
2. **不碰待补参数**：不调用 `stream_pending`、`fill_param`，也不清除 pending。生图追问的 pending 和普通 pending 都一样：**保持原样**，留到之后的轮次。
3. **不做意图识别、不执行工具**：不调用 `recognize_intent_with_fallback`、`recognize_intent`、`stream_intent`、`execute_intent`。这样「查/搜」兜底正则也不会触发。
4. **以下保持现状**：
   - 模式判定 `detect_mode`，以及镜子模式 `stream_mirror`；
   - 带图时走 `stream_image`；
   - 普通回复走 `stream_normal`；
   - 计费（文字回复照常扣 10 颗）；
   - 回复末尾追加热线（`_needs_crisis_resource` 现有逻辑）；
   - trace 里的 `crisis: "possible"`。
5. **以下也不受影响**：
   - 显式的 `request_mode` 为 `image` / `image_edit`（用户在界面上点了生图或修图）时，维持现状，照常生成（`test_high_image_modes_use_support_reply_while_possible_uses_generation` 必须继续通过）；
   - `image_edit_requires_reference` 的固定引导语维持现状。

**信息或求助语境**的定义：命中 `safety.py` 现有 `_CONTEXTUAL_MENTIONS` 第 4 条规则（`:43`，「查/搜/了解/研究/写/报道/问/看看 …… 危机词 …… 急救/预防/干预/新闻/报道/论文/研究/心理/数据/怎么劝/如何帮」），并且整句判级为 `possible`。这类句子**维持现有的完整路由**，工具照常可用。例如「帮我查下割腕的急救方法」仍然去搜索（`test_possible_crisis_keeps_tool_routing_billing_resources_and_trace` 必须继续通过）。

- 实现方式自定，但要从 `safety.py` 暴露这个判断，不要在 `chat_service.py` 里复制正则。例如新增一个函数，返回判级加上「是否信息或求助语境」。
- `high` 和 `None` 两档的行为**完全不变**。

### 3.3 不做的事

- 不处理「误报为高危」的问题（引用歌词、「去死海旅游」、「我不会轻生的」、「我要死啦」等）。这些留给模型判级那一单。但本轮**不得让日常语料的判级变得更高**（见第 5 节）。
- 不改前端，不改 `routers/chat.py`。

## 4. 允许修改的已有测试（只有这三处）

1. `backend/tests/test_traditional_crisis.py::test_word_level_plan_and_second_person_variant`：参数 `("計畫下週跳樓", "possible")` 改为 `("計畫下週跳樓", "high")`。原因：这是旧版本已知的退化，本单修复它。同一个测试里的另一条参数 `("我想死妳", None)` 不动。
2. `backend/tests/test_crisis_resource_paths.py::test_crisis_tool_pending_and_mirror_paths`：**只改 `level == "possible"` 时 `path` 为 `tool` 和 `pending` 这两个分支的断言**，改成第 3.2 节的新行为：
   - `intent_calls == tool_calls == fill_calls == []`；
   - 模型被调用一次，用于普通回复；
   - `pending` 路径下 `get_pending(...)` 仍等于原来的 route pending；
   - 余额扣 10（`_balance(user) == before - 10`），即这一行的条件表达式里 possible + pending 的那一支改为扣 10；
   - 热线恰好一次（`_assert_resource_once` 不变）。
   - `level == "high"` 的分支和 `mirror` 分支**一字不改**。
3. `backend/tests/test_traditional_crisis.py` 顶部的 `RULE_CHARACTER_VARIANTS` 和 `NO_VARIANT_RULE_CHARACTERS`：
   - **只允许追加**新规则字，不得删除或改动已有条目；
   - 有繁体或异体写法的字放进 `RULE_CHARACTER_VARIANTS`，并在 `utils/traditional_chinese.py` 里追加相同的映射；
   - 没有异体的字放进 `NO_VARIANT_RULE_CHARACTERS`；
   - 报告里逐字列出新增的字，以及它的繁体或异体（或者说明为什么没有）；
   - 如果改写规则后，某个已有的字不再出现在 `safety.py` 里，这个测试也会失败。这时**保留该字**（不要删清单条目），并在报告里说明。

## 5. 新语料（新建 `backend/tests/test_crisis_recall_2026_10.py`）

下面四组语料要**逐字照抄**进新测试文件，每句一个参数化用例。不得增删或改写句子。可以另外加你自己的用例，但要放在另外的参数组里。

**必须判 `high`（54 句）**

```python
SPEC_MUST_HIGH = [
 # 即时行动 / 方法（现在时、已发生）
 "我这就去跳河", "我去跳河了", "我跳河了", "我现在去跳江", "我现在就去跳海", "我站在桥上，想跳",
 "我想吊死自己", "我吊死自己算了", "我想烧炭", "我想自尽", "我想割脉", "我想寻死", "我想一死了之",
 "我想自己了断", "我打算把自己杀掉", "我已经想好怎么死了", "谁能告诉我怎么死最快",
 "我需要结束生命", "只要结束生命就解脱了", "现在就结束生命",
 "我把整瓶药都吞了", "我把所有的药都吃了", "刚吃了一整瓶止痛药", "药都准备好了，今晚就结束",
 "我朋友自杀了，我也想跟他走",
 "i want to end it all", "i took all my pills", "i've been thinking about killing myself",
 "gonna jump off the roof tonight", "i'm going to hang myself", "i'm gonna jump off the bridge",
 # 致死方法询问
 "上吊要多久才会死", "割腕要割多深才会死", "跳楼几层会死", "上吊多久能死", "吃多少安眠药会死",
 "跳楼多高能死", "安眠药吃几片会死", "哪种安眠药吃了醒不过来", "哪种安眠药吃了不醒",
 "什么安眠药吃了就睡不醒了", "哪种安眠药能一睡不醒", "查一下跳楼几层会死",
 # 繁体「計畫」与繁体变体
 "計畫明天跳海", "計畫吞藥", "計畫下週跳河", "計畫今晚跳江", "計畫割腕", "計畫上吊", "計畫自殺",
 "計畫下週跳樓", "我計畫明天跳海", "我這就去跳河", "上吊要多久才會死",
]
```

**至少判 `possible`（16 句，判 `high` 也可以）**

```python
SPEC_AT_LEAST_POSSIBLE = [
 "我在天台上了", "我真的活够了", "我不想再醒来了", "不想再撑了，想解脱", "活着太痛苦了，我想解脱",
 "我不配活着，我该死", "我想让自己消失", "我已经买好绳子了", "活着没啥意义", "活着没甚么意义",
 "活著沒甚麼意義", "我现在结束这一切", "需要结束这一切了，我撑不住了", "我想一了百了",
 "i'm done with living", "i just want to disappear forever",
]
```

**必须判 `None`（18 句）**：日常话，这一轮判 `possible` 也算失败，因为 `possible` 现在会拦掉工具。

```python
SPEC_MUST_BE_NONE = [
 "别在一棵树上吊死", "不要在一棵树上吊死，多投几家", "冬天在屋里烧炭取暖要注意通风",
 "周末去海边跳海游泳", "直接把旧版本删了，一了百了", "跳绳买好了，明天开始锻炼",
 "买好绳子了，周末去露营搭帐篷", "这栋楼有几层", "仙人掌多久不浇水才会死", "金鱼不喂食多久会死",
 "刚吃了止痛药，头不疼了", "昨晚吃了感冒药睡得醒不过来", "我在天台上晒被子",
 "我们在天台吃火锅，帮我查下明天天气", "游戏里的角色生命结束了", "计划下周去海边玩",
 "計畫下週去日本旅行", "我准备躺上吊床睡个午觉",
]
```

**不得判 `high`（3 句）**

```python
SPEC_NOT_HIGH = [
 "医生开的安眠药一次吃几片", "我想让自己消失一段时间，去西藏旅行", "这首歌叫《一了百了》",
]
```

**路由测试**（同一个新文件，用 `client` / `dev_headers` 等现有夹具，模型和工具一律打桩）：

- R1：句子判为 `possible` 且不属于信息或求助语境（例如「活着没意思」），会话里挂着 route 的 pending：
  - 不调用 `fill_param`、`recognize_intent`、`execute_intent`；
  - pending 保持原样；
  - 模型被调用一次，生成普通回复；
  - 热线恰好一次；
  - 扣 10 颗。
- R2：同样的 `possible` 句，没有 pending，意图模型打桩成会返回 `web_search`：
  - 意图模型和工具都不被调用。
- R3：`possible` 句里带「查一下……」（例如「查一下安眠药吃多少会有危险」，需先确认它判为 `possible` 且不属于信息或求助语境；如果不是，就换一句满足条件的，并在报告里写明）：
  - 不触发 `web_search`。
- R4：会话里挂着生图追问的 pending（`intent == "generate_image"`），这时发一句 `possible`：
  - 生图 pending 保持原样，不生图。
- R5：信息或求助语境的 `possible` 句（「帮我查下割腕的急救方法」）：
  - 意图识别和工具照常被调用（与现有测试一致即可，不必重复）。
- R6：`None` 句（例如「帮我查下明天天气」）：
  - 路由与改动前完全相同，意图识别被调用一次。

## 6. 报告（新建 `03-report.md`）

- 逐条写出改动的文件和行号，以及每条新规则覆盖的现象。
- 第 4 节三处测试修改的前后对照（diff 原样贴）。
- 新增规则字清单（第 4 节第 3 条）。
- 第 7 节验收命令的原样输出与退出码。
- `git status --porcelain` 的原样输出，确认只有白名单文件。
- **未决问题**：包括任何偏离本规格原文之处，以及你自己做的判断。

## 7. 验收（Claude 主会话会独立重跑）

| # | 命令（在 `backend/` 下） | 期望 |
|---|---|---|
| A1 | `python -m pytest -q -p no:cacheprovider` | 全部通过；数量 = 1546 + 新增用例数。报告里写明新增了多少 |
| A2 | `python -m pytest -q -p no:cacheprovider tests/test_crisis_recall_2026_10.py -v` | 全部通过 |
| A3 | `git diff --stat -- backend/tests` | 只有第 4 节允许的两个已有测试文件，加上新建的测试文件 |
| A4 | `git diff -- backend/tests/test_beta_safety.py backend/tests/test_o1_resource_cleanup.py` | 输出为空 |
| A5 | 第 4 节第 2 条的 diff | 只动 possible 的 tool/pending 分支；high 与 mirror 分支一字不改 |
| A6 | 盲测 | Claude 另有一套不给实施方的盲测语料（危机句和日常句），用来检验泛化能力，不是让你去猜的。日常句的高危数和非 `None` 数不得比基线多；危机句的召回要明显提高 |
