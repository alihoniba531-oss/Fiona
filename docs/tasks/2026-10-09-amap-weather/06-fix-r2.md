# 返修 R2（独立复核后）

独立复核（Fable，五维 + 逐条反驳）提出 18 条，必须修复 1 条（F1）；另顺手修 4 条低成本改进。本文是 `02-spec.md` / `05-fix-r1.md` 的增补，冲突处以本文为准，其余条款与验收标准不变。

## 改动范围白名单

只允许改动：`backend/services/chat_service.py`、`backend/tools/weather.py`、`backend/tools/amap_mcp.py`、`backend/tests/test_weather_daily_cap.py`、`backend/tests/test_weather_intent.py`、`backend/tests/test_amap_mcp.py`、`docs/DEPLOYMENT.md`、本任务目录。

## R2-1（必须修复）天气失败卡与危机资源的顺序

**问题**：`stream_intent` 与 `stream_pending` 里对天气失败卡有 `weather_error` 特判：先 `yield _crisis_resource_event(state)`、再 `yield _sse({"card": result})`。前端（`frontend/app/page.tsx`）收到 `text` 事件是 `reply += data.text`，收到 `card` 事件是 `reply = tip; content: tip`——**整体替换**气泡内容。于是在 possible + 信息/求助语境下，求助资源在本轮界面被失败文案覆盖，用户看不到（只有落库摘要里有）。其他工具的失败卡都是「先 card、再由 `_save_text_reply` 追加资源 text」，资源可见。

**要求**：
1. 删除两处 `weather_error` 特判，让天气失败卡与其他工具失败卡走**完全相同**的路径：先 `yield _sse({"card": result})`，再 `state.full_response = _summarize_card_for_history(result)`，由紧随其后的既有保存逻辑追加并送达一次危机资源（落库内容与现在一致：摘要 + 空行 + 资源）。
2. 规格第 3 节「先补发危机资源再报错」只针对 SSE `error` 事件（每日上限超限、生图忙碌那类），**不适用于 card 事件**；超限路径保持现状不动。
3. 测试 `test_weather_daily_cap.py::test_weather_failure_sends_crisis_resource_before_error_card`（本单新增的测试，允许修改）改名为表达新顺序的名字，断言改为：`direct` 与 `pending` 两个分支中，第一个事件是失败 card，之后恰好一次含求助资源的 text 事件，整轮资源总计恰好一次；落库内容含失败摘要与资源。
4. 不得改动前端。

## R2-2 部署文档去掉工作流措辞（复核 D2）

`docs/DEPLOYMENT.md` 天气隐私数据流段末句「上线后由作者在沙箱外验证真实高德响应、失败退款、缺城市追问和取消。」改为与同文件搜索段一致的写法：「部署后抽查应覆盖真实高德响应、失败卡退款、缺城市追问与取消。」全库不得出现「沙箱外」这类工作流措辞（`docs/tasks/` 目录除外）。

## R2-3 补一条每日上限测试（复核 T-1）

在 `test_weather_daily_cap.py` 增加：限流器开启、`DEV_MODE=0`、上限 2；两次都走「`stream_intent` 缺城市写 pending → `stream_pending` 收到城市名补齐」并拿到天气卡；第三次同样补齐时收到 `[{"error": daily_cap_message("weather")}]`、高德桩调用次数仍为 2、pending 已清除。证明追问补齐路径确实计数（若把补齐分支的 `hit=True` 改成 `hit=False`，该测试必须变红——请在报告里说明你做过这个反向验证）。

## R2-4 上游城市名为空时的兜底（复核 B3）

`backend/tools/weather.py`：`location` 取 `data["city"]` 去空白后的值；为空或非字符串时回退到规范化后的用户城市名。补一条测试：`{"city": "", "forecasts": [有效一天]}` → `location` 与 `source` 使用用户城市名。

## R2-5 SSE 只按规范换行切分（复核 B2）

`backend/tools/amap_mcp.py` 的 SSE 解析把 `text.splitlines()` 换成只按 `\r\n`、`\r`、`\n` 切分（例如 `re.split(r"\r\n|\r|\n", text)`）。补一条测试：`data:` 行的 JSON 字符串里含 U+2028 时，`text/event-stream` 响应仍能解析成功。

## 验收

1. `git status --porcelain` 相对返修前只新增白名单内文件的改动。
2. 在 `backend/` 下 `python -m pytest -q tests/test_amap_mcp.py tests/test_weather_intent.py tests/test_weather_daily_cap.py` 全部通过；全量 `python -m pytest -q` 除沙箱内既有 6 项端口用例外全部通过。
3. `grep -n "weather_error" backend/services/chat_service.py` 无输出。
4. `grep -rn "沙箱外" README.md CLAUDE.md PLAN.md docs/ARCHITECTURE.md docs/DEPLOYMENT.md docs/CYBER_AVATAR_PLATFORM.md` 无输出。
5. 把逐项落实情况与验收输出追加到 `03-report.md` 末尾（新增一节「返修 R2」）。
