# 04 复核（2026-10-16，全新上下文 subagent，只看规格 + diff + worktree）

## 结论：通过（第 1 轮，无必须修复项）

## 验收标准逐条核验

| 项 | 结论 | 证据 |
|---|---|---|
| T1 `llm.py` 常量 | ✅ | `backend/llm.py:81-87`，在 `QWEN_EXTRA_BODY` 之后；常量名、值、注释与规格一致 |
| T2 解析函数 | ✅ | 导入 `chat_service.py:40`；`_CHAT_VISION_ENV_WARNED` 在 `:79`；函数 `:249-262` |
| T3 `stream_image()` | ✅ | docstring、`vision_model` 在 `try` 前、`model=vision_model`、`extra_body=dict(CHAT_VISION_EXTRA_BODY)`、异常日志；其余参数未动 |
| T4 `model_router.py` | ✅ | `:134` 注释与规格一致 |
| T5 测试 | ✅ | 原分支测试新增 4 条断言；新文件覆盖 a–g，环境变量逐测清理 |
| T6 文档 | ✅ | CLAUDE.md、ARCHITECTURE.md、PLAN.md、README.md、DEPLOYMENT.md、`.env.example` 六处与规格一致 |
| AC1 qwen-vl-max | ✅ | 只剩 3 处历史说明；其余命中在禁改的 studio probe 文件和 `docs/tasks` 历史文档 |
| AC2 FIONA_CHAT_VISION_MODEL | ✅ | 7 个文件命中 2/1/1/1/1/1/1 |
| AC3 目标测试 | ✅ | 23 passed；在 `FIONA_CHAT_VISION_MODEL` 设为非法值和其他合法值下相关测试共 202 passed |
| AC4 全量 | ✅（主会话执行） | `6172 passed, 0 failed`（基线 6125 passed + 33 skipped；skipped 来自 worktree 原先缺 `frontend/node_modules`） |
| AC5/AC6 范围 | ✅ | 只动允许的文件；禁改路径 diff 为空 |

`stream_image()` 前后逐行比对，只有 docstring、`vision_model`、`model=`/`extra_body=`、异常日志四处变化；提示词、历史条数、计费、摘要落库、危机资源、错误文案未变。

## 变异实验（18 组，在 scratchpad 副本里做）

拦住 13 组：默认值改回 qwen-vl-max、去掉 extra_body、enable_thinking 改 True、告警带原值、fullmatch→match、不去空白、告警标志不置真、空串也告警、加载时缓存、长度上限放到 65、允许斜杠、日志去掉模型名、max_tokens 改 800。

漏网 5 组：上限收紧到 63、temperature 改动、原值经 `extra=` 附到日志记录、告警写死字面量、extra_body 不复制。后三项行为等价或影响极小。

## 必须修复项

无。

## 可优化项与处理

1. 补 `"a" * 64` 合法边界测试 —— **已由主会话补上**（`test_chat_vision_model_accepts_64_char_boundary`）。
2. `test_chat_image_branch` 断言 `temperature == 0.9` —— **已补上**。
3. c 组「不告警」可改成断言该 logger 无任何 WARNING —— 未改，留作者裁决。
4. 告警用 f-string 而同文件其他告警是字面量 —— 规格允许常量拼接，未改。
