# 搜索与旅行卡片改用真实来源链接（L2）

基线：`main` @ `5279935`，工作区干净；后端 `python -m pytest -q` 为 **2052 passed**；前端 `npx eslint .` 为 **0 errors / 25 warnings**。

## 1. 产品目标

Chloe 的「搜索」卡（意图 `web_search`）和「旅行规划」卡（意图 `travel_plan`）现在的来源链接是**模型自己在 JSON 里写的**：
- 只检查了 `http(s)://` 前缀和 example.com，模型编过死链（`backend/tools/topic_expand.py` 文件头注释记录过 `caixin.com/404`）；
- 前端从没把 `sources` 渲染出来，只把第一个 url 当灰字显示，用户无法点开核验。

这和产品「诚实交付、不编造」的气质冲突（`backend/persona.py` 人设写明具体数字事实不能编）。

**目标**：
1. 两张卡的来源**只取自 DashScope 原生接口返回的真实搜索结果** `output.search_info.search_results`，模型输出里的任何 URL 一律丢弃。
2. 前端在卡片要点下方列出可点击的来源（标题 + 站点），点开走现有的安全外链函数。
3. 要点里的引用角标（如 `[3][4]`）不得出现在卡片、朗读和聊天记录里。

**用户场景**：「帮我查下今天 A 股收盘怎么样」→ 卡片 3–5 条要点 + 下方「来源」列出东方财富网、雪球等真实文章，点开即原文。

## 2. 本单范围与明确不做的事

- **天气不在本单**：`backend/tools/web_search.py` 中「query 含『天气』→ `_search_weather_direct`」的分流（约 73–77 行）**原样保留、一行不改**；`backend/tools/visual_search.py` 不改。天气意图会在下一单随高德一起做。
- **不做持久化**：卡片（含来源）目前不落库，刷新或切换会话后只剩文字摘要，这是所有卡片的既有行为。本单不改数据库、不改 `agent_store.py`、`useConversations.ts`。这是已知限制。
- **不改 `backend/tools/card_detail.py`、`backend/tools/topic_expand.py`**（只从它们导入函数）。
- 不引入任何新依赖；不改 `globals.css`；不改意图识别与计费规则。

## 3. 已实测的真实接口事实（2026-10-09，`qwen-plus` + `_request_search`）

一次真实调用的返回（节选）：

```
finish_reason: stop
content: {"success": true, "headline": "...", "points": ["沪指收3813.79点（+0.05%）...北证50领涨+2.49%[3][4]；", "...收盘72只，跌停由17只收敛至10只[3]；", "...CPO/PCB/风电持续走弱[1][3]"]}
search_results（10 条），每条形如：
{"icon": "https://...", "site_name": "东方财富网", "index": "1", "title": "A股每日复盘 2026-10-09(周五) ", "url": "https://caifuhao.eastmoney.com/news/..."}
```

要点：
- **`index` 是字符串**（`"1"`），不是整数。`card_detail._search_sources` 只认 `type(index) is int`，直接套用会让所有编号变成 `None`、引用对不上。本单必须先把纯数字字符串规范成 `int` 再交给它。
- 即使提示词里没要求，模型也会在要点里写 `[n]` 角标（`enable_citation` 开着）。
- 结果里有 `icon` 字段，本单**不使用、不下发**。
- 原生接口经 `tools.topic_expand._request_search`（urllib，30 秒 socket 超时，不重试，不受 `DASHSCOPE_TIMEOUT_SECONDS` / `DASHSCOPE_MAX_RETRIES` 控制）。

## 4. 技术约束

- 沿用现有栈与写法，修改范围集中，不做无关重构。
- 复用现有函数：`tools.topic_expand._request_search(messages, api_key, *, max_tokens)`、`tools.card_detail._search_sources(output, cited)`、`utils.safe_http.validate_public_http_link`（由 `_search_sources` 内部调用）。**不得修改这三个函数，也不得给它们加参数。**
- 前端外链必须用 `frontend/lib/open.ts` 的 `openExternal(url)`（Tauri WebView 里 `<a target="_blank">` 会被吞，见该文件头注释）；颜色只用现有设计 token（`--ink`、`--ink2`、`--carve`、`text-muted-foreground` 等），日夜间自动生效。
- 改前端前先读 `frontend/AGENTS.md`。
- 请用多个 subagent 并行：按文件不重叠分工（建议：①后端 `tools/` + 新测试；②前端三个文件；③文档）。同一文件的多处改动交给同一个 subagent。

## 5. 任务清单

### 5.1 后端：新模块 `backend/tools/native_search.py`

提供两个函数，供 `web_search` 与 `travel_plan` 共用：

```python
def grounded_search(messages: list[dict], *, max_tokens: int, max_sources: int = 5) -> dict:
    """返回 {"data": dict | None, "raw": str, "sources": list[dict], "error": str | None}"""

def strip_citations(text: str) -> str:
    ...
```

`grounded_search` 行为：
1. Key 用 `os.environ.get("DASHSCOPE_API_KEY")` 读取（与 `card_detail.py` 相同）；为空则**不发请求**，返回 `error="missing_key"`。
2. 通过**本模块的模块级名字** `_request_search` 调用（即 `from tools.topic_expand import _request_search` 后在函数里直接调用），使测试可以 `monkeypatch.setattr(native_search, "_request_search", fake)`。
3. 任何异常 → `error=<异常类名>`，不把上游响应正文透出。
4. 响应不是预期形状（`output`/`choices[0]/message/content` 缺失或类型不对）→ `error="bad_response"`。
5. `finish_reason == "length"` → `error="truncated"`。
6. `raw` = content 原文。`data` = 从 content 中用与现有 `web_search.py` 相同的容错方式（`re.search(r"\{[\s\S]*\}", content)` 后 `json.loads`）解析出的 dict；解析失败或不是 dict 时 `data=None`、`error=None`（由调用方按原有「不是 JSON」分支处理）。
7. 来源：
   - 先从 `raw` 里解析被引用的编号集合 `cited`（正则与 `card_detail._citation_indices` 相同：`\[(\d+(?:\s*[,，、]\s*\d+)*)\]`，取其中全部数字）。
   - 复制 `output["search_info"]["search_results"]` 中的每个 dict，把 `index` 规范化：`int` 原样；**纯数字字符串**转成 `int`；其余（含 bool、空串、非数字串）删掉 `index` 键。原响应对象不得被原地修改。
   - 调用 `_search_sources({"search_info": {"search_results": normalized}}, cited)`。
   - 结果截到 `max_sources` 条；每条只保留 `title`（截到 80 字）、`url`、`site_name`（可为空串）、`index`（若有）。**不得包含 `icon` 或其他字段。**
8. 模型 JSON 里如果出现 `sources`、`url` 等字段，一律忽略，绝不进入返回的 `sources`。

`strip_citations(text)`：删除所有 `[n]`、`[n, m]`、`[n，m]`、`[n、m]`、`[ref_n]` 形式的角标；删除后把因此留下的「空格+中文标点」「重复空格」收拢，首尾 `strip()`。不改动其他方括号内容（如 `[图]`、`[注]`）。

### 5.2 后端：`backend/tools/web_search.py`

1. 天气分流（含「天气」→ `_search_weather_direct`）**原样保留**，仍在任何网络请求之前。
2. 去掉 OpenAI 兼容客户端：删除 `_get_client` 及其使用，改为 `native_search.grounded_search(messages, max_tokens=700)`。
3. 系统提示词：保留 `_today_directive()` 函数及其文案不变（`tests/test_beijing_time.py` 断言它）；去掉要求模型输出 `sources` / `url` 的内容，改为写明「不要输出任何 URL、链接或来源列表，来源由系统根据真实搜索结果附加」。输出 JSON 结构保留 `success` 与 `points`（`headline` 等现有字段按原样保留或删除均可，以不破坏现有卡片字段为准）。
4. 卡片组装（`type`、`source` 标签沿用现状）：
   - `error` 为 `missing_key` / 异常 / `bad_response` / `truncated` → 错误卡：`points` 为一条中文说明（与现有「搜索失败:…」风格一致，只含异常类名，不含上游正文），`error: True`。
   - `data is None`（不是 JSON）→ 沿用现有分支的行为（按行截取前 5 行做 points，`error: True`）；按行截取前先对每行做 `strip_citations`。
   - 解析出的 `points` 为空 → 沿用现有「没搜到」错误卡。
   - `points` 每条先 `strip_citations` 再去空；最多 5 条。
   - **`sources` 为空**（真实搜索没有任何可用来源）→ 错误卡：`points=["没搜到可核实的来源，换个说法再试试"]`，`error: True`（不计费）。
   - 成功：`{"type": "card", "source": ..., "url": sources[0]["url"], "points": points, "sources": sources, "error": data.get("success") is not True}`。
5. 卡片 dict 里不得出现模型写的任何 URL。

### 5.3 后端：`backend/tools/travel_plan.py`

1. 同样删除 `_get_client`，改为 `native_search.grounded_search(messages, max_tokens=1200)`。
2. 提示词：保留 `_today_directive()` 及文案；去掉要求模型输出 `sources` 的内容，同 5.2 写明不要输出 URL。
3. `headline` 与每条 `points` 先 `strip_citations`；`headline` 不是字符串时当作没有（修掉现在 `.strip()` 可能抛 AttributeError 的问题）。
4. `sources` 来自 `grounded_search`，最多 5 条；**为空时行程仍正常交付**（`sources: []`、`url: ""`，`error` 规则保持现状），因为行程建议本身不要求逐条引证。
5. 其余错误分支（空 query、异常、不是 JSON、points 为空）保持现有语义与文案风格；异常类分支只显示类名。
6. `build_playback`（朗读文本）不需要改，但其输入的 headline/points 必须已经去掉角标。

### 5.4 前端：`frontend/lib/open.ts`

新增并导出：

```ts
export function toSafeExternalUrl(url: unknown): string | null
```

- 只接受**绝对** URL（`new URL(url)` 不带 base 解析）；协议只能是 `http:`/`https:`；hostname 非空；不得带 username/password；`href.length <= 2048`；否则返回 `null`。
- 不改变 `openExternal`、`openInBrowser` 及现有私有函数的行为。

### 5.5 前端：`frontend/components/ChatBubble.tsx`

1. `CardData.sources` 类型扩展为 `{ title: string; url: string; site_name?: string; index?: number }[]`。
2. 在通用卡分支（`subtype !== "weather"` 的那张卡）里，要点列表 `</ul>` 之后、卡片收口之前，加「来源」区块：
   - 先 `const safeSources = (cardData.sources ?? [])` 映射为 `toSafeExternalUrl(url)` 非空的条目，最多 5 条；为空则整个区块不渲染。
   - 区块顶部一条分隔线：`border-t` + `style={{ borderColor: "var(--carve)" }}`，与卡片现有分隔线一致。
   - 小标题「来源」：`text-[11px] text-muted-foreground`。
   - 每条是 `<button type="button" onClick={() => void openExternal(url)}>`，`aria-label={`打开来源：${label}`}`；第一行显示 label（`title` 去空后为空则回落 `site_name`，再回落 hostname），单行截断；第二行 `text-[10px] text-muted-foreground` 显示 `site_name || hostname`（与第一行相同时可省略第二行）；前置 `ArrowUpRight`（lucide-react，项目已用）小图标，颜色 `var(--ink2)`；`hover:text-[color:var(--ink)] hover:underline`；手机端 `max-md:min-h-10` 保证触控区。
   - 字号、间距与卡片现有 11–13px 体系协调，不新增颜色值。
3. 卡片表头那行灰色 url：**有 safeSources 时不再显示**（避免重复）；没有 sources 的卡（如 `fetch_card` 网页卡）保持现状。
4. 天气卡分支不改。

### 5.6 前端：`frontend/app/page.tsx`

只改收到 `data.card` 后生成气泡提示文字（tip）的那段（约 1740–1773 行）中**通用卡**的分支：当 `card.error` 为真时，tip 不得是「搜到了，详情在下面的卡片里」，改为 `card.points[0]`（若有）否则「这次没查到可靠的结果」。天气与旅行分支的 tip 逻辑不改。

### 5.7 测试

**允许修改的现有测试（只限这两处，只改打桩方式，保留原测试意图）**：
- `backend/tests/test_spec_bugfixes.py` 的 `test_malformed_search_json_is_sanitized`：改为给 `tools.native_search._request_search` 打桩，喂原生形状的载荷（content 为畸形 JSON 的同一份字符串，`search_info.search_results` 给 1 条合法来源），断言：web_search 的 points 为 `["没搜到"]`；旅行卡 points 为 `["主线"]`；**旅行卡 sources 来自 search_results，模型 JSON 里的 `https://example.net` 不出现**。
- `backend/tests/test_beta_billing.py` 的 `test_unstructured_tool_model_reply_is_explicitly_non_billable`：同样改为给 `_request_search` 打桩，content 为纯文本「服务暂时没有结果」，断言 `card["error"] is True` 且不计费。

**不得修改的测试**（逐字不动）：`test_card_detail.py`、`test_beijing_time.py`、`test_spec_bugfixes.py` 中除上面那个函数外的全部内容（含 `test_search_fallback_does_not_match_observation`、`test_weather_weekday_uses_monday_first`）、所有 `test_crisis_*.py`、`test_chat_*.py`、`test_context_slot_state.py`、`test_daily_caps.py`、`test_public_surface.py`、`test_safe_http.py`。

**新增 `backend/tests/test_search_real_sources.py`**：
- autouse 夹具：把 `urllib.request.urlopen`、`requests.get`、`utils.safe_http._open_pinned` 替换为抛 `AssertionError("network")` 的函数；设 `DASHSCOPE_API_KEY` 为假值。任何没打桩的真实请求都必须让测试失败。
- 载荷构造函数按第 3 节的真实形状（`index` 为字符串、带 `icon`、content 带 `[n]` 角标）。
- 至少覆盖：
  1. web_search 成功：sources 只来自 search_results；模型 JSON 里夹带的 `sources`/`url` 不出现；不含 `icon` 键；最多 5 条；title ≤ 80 字；`url` 等于 sources[0].url。
  2. 字符串 index 被规范化：被正文引用的来源排在前面（例如正文引用 `[3]`，则 index 3 排第一）。
  3. 非公网/非法 URL（`http://127.0.0.1/x`、`javascript:alert(1)`、`ftp://...`、带用户名密码）被过滤。
  4. 同 `(index, url)` 去重。
  5. points 与旅行卡 headline、朗读文本（`build_playback`）、`_summarize_card_for_history` 结果中均不含 `[数字]` 角标；`[图]` 这类非数字方括号保留。
  6. search_results 为空或全部被过滤 → web_search 返回错误卡、`error is True`、`chat_service._tool_billable("web_search", card) is False`；travel_plan 仍成功、`sources == []`。
  7. `finish_reason == "length"` → 错误卡；响应形状不对 → 错误卡；`_request_search` 抛 `urllib.error.HTTPError` → 错误卡，points 只含类名、不含上游正文。
  8. 缺 Key → 错误卡，且 `_request_search` 一次都没被调用。
  9. content 是「说明文字 + JSON + 说明文字」时仍能解析。
  10. 含「天气」的 query 仍走 `_search_weather_direct`（打桩它），`_request_search` 不被调用。
  11. `grounded_search` 不原地修改传入的响应对象。
  12. `strip_citations` 的单元测试（各种角标形式、标点收拢、保留非数字方括号）。

### 5.8 文档

代码改变了「搜索/旅行的接口与超时」「来源的来源」「前端展示」，按 `CLAUDE.md` 工作约定同步文档。**请全库搜索**下列事实的所有陈述点逐处更新，不要只改下面举例的位置：
- 搜索与旅行规划改走 DashScope 原生接口（`qwen-plus`，联网搜索强制开启），来源只取自真实搜索结果并经公网 HTTP(S) 格式校验，模型生成的 URL 不再进入卡片；
- 这两项调用固定 30 秒 socket 超时、不重试，不受 `DASHSCOPE_TIMEOUT_SECONDS` / `DASHSCOPE_MAX_RETRIES` 控制（README 与 DEPLOYMENT 现有「模型客户端默认 60 秒超时、重试 1 次」的说法要补充例外，ARCHITECTURE 里「模型客户端已有明确超时和有限重试」同理）；
- 前端搜索/旅行卡展示可点击来源；卡片不落库、刷新后来源不保留（已知限制）。

可从这些位置找起：`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、`CLAUDE.md`。文档里不得写入任何本机绝对路径。

## 6. 验收标准

在仓库根目录执行，全部满足才算完成：

1. `git status --porcelain` 只出现以下路径（`??` 为新增）：
   - `backend/tools/native_search.py`（新）、`backend/tools/web_search.py`、`backend/tools/travel_plan.py`
   - `backend/tests/test_search_real_sources.py`（新）、`backend/tests/test_spec_bugfixes.py`、`backend/tests/test_beta_billing.py`
   - `frontend/lib/open.ts`、`frontend/components/ChatBubble.tsx`、`frontend/app/page.tsx`
   - 第 5.8 节涉及的文档（`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、`CLAUDE.md` 中的任意几个）
   - 本任务目录 `docs/tasks/2026-10-09-search-real-sources/`
2. `git diff --exit-code -- backend/tests/test_card_detail.py backend/tests/test_beijing_time.py backend/tools/card_detail.py backend/tools/topic_expand.py backend/tools/visual_search.py backend/utils/safe_http.py` 退出码 0。
3. `git diff -U0 -- backend/tools/web_search.py | grep -n '_search_weather_direct'` 无输出（天气分流那几行未被改动）。
4. `grep -n "_get_client" backend/tools/web_search.py backend/tools/travel_plan.py` 无输出。
5. 在 `backend/` 下：`python -m pytest -q` 全部通过，`passed` 数 ≥ 2052 + 新增测试数，0 failed、0 error。
6. 在 `backend/` 下：`python -m pytest -q tests/test_search_real_sources.py` 全部通过。
7. 在 `frontend/` 下：`npx tsc --noEmit` 退出码 0；`npx eslint .` 为 0 errors 且 warnings ≤ 25。
8. 在 `frontend/` 下：`grep -n "toSafeExternalUrl" components/ChatBubble.tsx lib/open.ts` 至少各 1 行；`grep -n "openExternal" components/ChatBubble.tsx` 至少 1 行。

不要运行 `npm run build` / `npm run dev`、不要启动后端服务（沙箱内会 EPERM 或占端口）；构建、真实接口抽查与界面截图由 Claude 在沙箱外完成。沙箱内也不要尝试任何真实网络请求。

## 7. 什么时候停下来问

- 只有当发现某项要求**无法实现或互相矛盾**、会影响「做出什么」时才停下来，在总结里写明原因与证据；不回滚已完成的工作。
- 只影响「怎么写测试 / 怎么验证」的细节自行决定并在总结里说明。
