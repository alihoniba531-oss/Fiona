# 返修 R1（用户验收后要求「顺手改掉」的 4 项）

背景：本单独立复核（`04-review.md`）0 项必须修复；用户看完结论，要求把下列 4 项改进一并做掉再合并。以下要求是 `02-spec.md` 的增补，与其冲突处以本文为准；`02-spec.md` 第 4 节技术约束、5.7 的「不得修改的测试」名单、第 6 节验收标准继续有效。

## 改动范围白名单

只允许改动 `02-spec.md` 第 6.1 节已列出的文件（不新增文件）。本轮预计涉及：`backend/tools/native_search.py`、`backend/tools/web_search.py`、`backend/tools/travel_plan.py`、`backend/tests/test_search_real_sources.py`、`frontend/components/ChatBubble.tsx`、`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、`CLAUDE.md`。

## R1-1 卡片正文里的模型网址也要去掉（对应复核 BE-1 / SEC-1）

现状：模型若违抗提示词在要点正文里写网址（如「详见 https://invented.example.org/page 了解更多」），会以纯文本进入卡片 `points`、旅行 `headline`、朗读文本和聊天历史摘要；非字符串的 point（dict/list）被 `str()` 成 Python repr，可能夹带 URL。

要求：
1. 在 `native_search.py` 新增 `strip_urls(text: str) -> str`：
   - Markdown 链接 `[文字](任意 URL)` → 只保留「文字」；
   - 删除 `http://`、`https://` 开头直到空白或中文标点（`，。！？；：、）】》」』`）之前的整段；删除 `www.` 开头的同类片段；
   - 删除后按 `strip_citations` 相同的规则收拢「空格+中文标点」和重复空格，首尾 `strip()`；
   - 不改动不含 URL 的文本（例如「3.5%」「v2.0」「A股」原样保留）。
2. `web_search` 与 `travel_plan` 中，凡是进入卡片的模型文本（`points` 每条、旅行 `headline`、`data is None` 时按行回退的每一行）都先 `strip_citations` 再 `strip_urls`，再去空；去空后若为空则丢弃该条。
3. `points` 里**不是字符串**的元素（dict、list、数字以外的对象）直接丢弃，不再 `str()`；数字（int/float，非 bool）可以 `str()` 保留。
4. 新增测试（加在 `backend/tests/test_search_real_sources.py`）至少覆盖：正文含 http(s) 网址、`www.` 网址、Markdown 链接三种情况被清理且其余文字保留；只含网址的要点被整条丢弃；dict/list 类要点被丢弃；旅行 headline 含网址被清理；`build_playback` 与 `_summarize_card_for_history` 结果中不含 `http`；`strip_urls` 对「3.5%」「v2.0」不改动。

## R1-2 来源箭头悬停时跟随文字变色（对应复核 FE-3）

`frontend/components/ChatBubble.tsx` 来源按钮里的 `ArrowUpRight` 去掉内联 `style={{ color: "var(--ink2)" }}`，改为继承按钮文字颜色（按钮本身已是 `text-[color:var(--ink2)] hover:text-[color:var(--ink)]`），使悬停时箭头与文字同步变深。其余样式不变。

## R1-3 来源标题防御（对应复核 FE-1）

同文件计算 `safeSources` 时，`title`、`site_name` 先判断 `typeof === "string"` 再 `trim()`，非字符串当作空串，保证后端将来返回异常数据也不会让聊天页渲染崩溃。

## R1-4 文档三处说法纠正（对应复核 DOC-1 / DOC-2 / DOC-3）

1. **删掉流程说明**：`PLAN.md` 2026-10-09 小节里「构建、真实接口抽查与界面截图由 Claude 在沙箱外验收」这句删除（PLAN 只记录产品与代码现状，不记录谁来验收）。
2. **30 秒原生调用的例外范围写全**：走 `tools.topic_expand._request_search` 的不只搜索与旅行规划，还有**热点展开**（`routers/hot.py` → `topic_expand`）和**卡片详情**（`card_detail`）。凡是文档里写「搜索与旅行规划……固定 30 秒 socket 超时、不重试、不受 `DASHSCOPE_TIMEOUT_SECONDS` / `DASHSCOPE_MAX_RETRIES` 控制」的地方，改为准确覆盖这四项（或改成「走 DashScope 原生联网搜索接口的调用（搜索、旅行规划、热点展开、卡片详情）」）。**请全库搜索**「30 秒」「socket 超时」「DASHSCOPE_TIMEOUT_SECONDS」「重试」相关陈述逐处核对，不要只改一处。卡片详情外层另有 45 秒总超时（`routers/cards.py`），如涉及可一并写准。
3. **热点分类的模型写错了**：热点分类用的是 `qwen3.8-flash`（`backend/routers/hot.py` 使用 `llm.QWEN_MODEL`，`backend/llm.py` 中 `QWEN_MODEL = "qwen3.8-flash"`，8 秒超时、不重试），只有热点**展开**才用 `qwen-plus`。纠正 `docs/ARCHITECTURE.md` 模型清单里「`qwen-plus`：联网搜索、热点分类/展开和旅行规划」及 `CLAUDE.md`「搜索/热点/旅行 `qwen-plus`」等含混或错误表述；同样全库搜索「热点分类」「qwen-plus」的其他陈述。

## 验收（在 02-spec 第 6 节全部条目继续成立的基础上）

1. `git status --porcelain` 不出现白名单以外的路径。
2. 在 `backend/` 下 `python -m pytest -q tests/test_search_real_sources.py` 全部通过，且用例数比 72 多（新增了 R1-1 的测试）。
3. `grep -n 'style={{ color: "var(--ink2)" }}' frontend/components/ChatBubble.tsx` 中不再出现来源按钮里的 `ArrowUpRight` 那一处。
4. `grep -n "沙箱外" PLAN.md` 无输出。
5. `grep -rn "热点分类/展开" README.md docs/ PLAN.md CLAUDE.md` 无输出。
6. 前端 `npx tsc --noEmit` 退出码 0；`npx eslint .` 0 errors、warnings ≤ 25。
7. 沙箱内全量 pytest 因端口权限失败的那 6 项可忽略，由 Claude 在沙箱外重跑全量。
