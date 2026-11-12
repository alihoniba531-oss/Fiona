# R3 返修报告：修改意见卡（规格 v1.6 §4.8）

本轮只按 §4.8 修改 `PLAN.md` 一处，并新增本报告。产品代码、其他文档、测试、规格、返修单、复核文件、`impl/report.md`、`impl/report-r1.md`、`impl/report-r2.md` 均未动。

## 1. 改了什么

文件：`PLAN.md`，`## 2026-11-12：修改意见卡` 的「已知局限：」段末。

替换前：

```text
已经发起的重新定稿照常有效；只在 Claude 智能体模式开放。
```

替换后：

```text
已经发起的重新定稿照常有效；点「带着这些要求重新定稿」时卡片先重新读取，发现这一项已经不能用就只更新卡片，被点的按钮随之消失、键盘焦点丢失，读屏软件也不会播报新的说明；确认框打开期间如果在书斋里又改了主编模型，框里写的费用会过时（实际按改后的模型计费，后端不核对作者确认时看到的费用类型）；只在 Claude 智能体模式开放。
```

`git diff --check` 退出码 `0`。与 R2 工作副本比较，除派单方后来放入的 `02-spec.md`、`07-review-r2.md`、`08-fix-r3.md`、`impl/report-r2.md` 外，只有 `PLAN.md` 不同；没有改任何产品代码或测试。

## 2. 新句与旧句出现次数

检查命令（Python 精确子串计数）：

```text
OLD_BEFORE= 1
NEW_BEFORE= 0
OLD_AFTER= 0
NEW_AFTER= 1
```

即：

- 新句在 `PLAN.md` 中恰出现 **1** 次；
- 旧句在 `PLAN.md` 中出现 **0** 次。

## 3. 五个测试文件结果

```bash
cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local \
  .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_claude_agent_docs.py \
  tests/test_chat_image_tool_docs.py \
  tests/test_local_watch_docs.py \
  tests/test_local_watch_capture_docs_r3.py \
  tests/test_empty_states_match_profile.py
```

原始尾行：

```text
60 passed in 0.10s
```

退出码 `0`；五个文件全绿。
