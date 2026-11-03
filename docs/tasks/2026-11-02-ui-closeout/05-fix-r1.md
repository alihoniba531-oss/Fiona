# 返修单 R1：T1 落地（2026-11-02）

你在 T1 停下来问的三点，裁决如下；规格已更新为 v1.1（`02-spec.md` 开头有改动说明），以 v1.1 为准。

## 裁决

1. **readout 计数冲突**：采用你列的方案 1。`backend/tests/test_ui_polish_page_contracts.py` 已加入白名单，**只许**把 `test_page_readout_numbers_are_not_bold` 里的 `assert source.count('className="readout font-normal"') == 2` 改成 `== 4`，其余一个字节不动。T1 第 6 条、T5 cost_hint 的字面量按规格原文落地（两个余额数字都用 `readout font-normal`）。
2. **`::backdrop` 计数**：你的理解对，注释里的词不算。§5.6 已改成 `grep -c "::backdrop {"` = 2。T3 不用动。
3. **页脚行判据**：按 T1 第 5 条的代码块为准——容器 `<div className={cn("mt-2 flex … ", !hasContent && "max-md:hidden")}>` 一行，`<span className="shrink-0 max-md:hidden">Enter 发送，Shift + Enter 换行</span>` 在下一行。cost_hint 测试按 v1.1 的写法：容器行恰 1 行且含 `!hasContent && "max-md:hidden"`；下一行去掉首尾空白后恰等于那个 span。

## 本轮要做

1. **T1 全部落地**（`frontend/app/page.tsx`，按字节读写、保留 BOM）：规格 §4 T1 第 1–7 条逐条做，不改 `label` / `labelTitle` 两个常量，不改思考档和「改用」按钮。
2. **新建 `backend/tests/test_ui_closeout_cost_hint.py`**：规格 §4 T5 的 cost_hint 清单（v1.1），每条断言一个用例或合并成少量用例都可以，但清单上每一项都要有断言。
3. **改 `test_ui_polish_page_contracts.py` 的那一个数字**（见裁决 1）。
4. **重跑验收**（规格 §5 全部 7 条）：
   - 全量 pytest 用后台任务跑完，`passed = 7836 + 14 + cost_hint 的用例数`，0 failed、0 skipped；
   - HEAD 对照按 §5 第 5 条重跑一遍（这次要把 `test_ui_polish_page_contracts.py` 也拷进 HEAD 副本？**不要**——它在 HEAD 上会因计数 2≠4 失败，这是预期的，不属于对照项。只拷四个新测试和两个门禁文件），期望：cost_hint 在 HEAD 上 FAIL 且原因是 AssertionError；
   - §5.6 的计数全部重贴；
   - `git diff -U0 HEAD -- backend/tests/test_ui_polish_page_contracts.py` 必须只有一个 hunk、一行 `-`、一行 `+`。
5. **更新 `03-report.md`**：删掉「阻塞」一节，改成 R1 记录（裁决 + 做了什么）；§6 第 1–6 项按新结果重写，原始输出照贴，不留占位符。`impl/A.md` 追加本轮记录。

## 不要做

- 不要动 T2–T5 已完成的文件（`history/page.tsx`、`globals.css`、8 个组件、两个门禁文件、三个新测试）。改完后 `git diff --stat` 里这些文件的行数应与你上一轮报告一致。
- 不要用编辑工具改 `page.tsx`。
- 不要改其他既有测试。

## 执行方式

只剩一个文件的实现和一个新测试，不必再开工作流；主代理直接做，或派一个 agent（任务说明自包含、不得再派生）都可以。

最终回复：修改了哪些文件、T1 逐条对应、§5 七条的实际输出、未完成或需人工确认的地方。
