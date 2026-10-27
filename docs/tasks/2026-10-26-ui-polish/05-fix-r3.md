# 返修 R3（作者验收时要求顺手修的两项，2026-10-27）

本返修单与 `02-spec.md`、`05-fix-r1.md`、`05-fix-r2.md` 同等效力，冲突时以本单为准。两项都来自第二轮复核 `04-review-r2.md` §5 的 O1、O2，作者已决定都修。§2 的约束照旧：不加粗、不新增依赖、不重排无关代码、白名单外不改；**改动前就存在的测试（基线测试）一字不许改**。

只做下面两项，其余已完成的工作保持不动，不回滚。本轮改动很小，不需要拆子代理，由你自己完成；不得调用 subagent / subagent_fork / workflow。

**放宽条款**（同 R2）：本任务自己新增的 8 个测试文件（`backend/tests/test_ui_polish_*.py`）里，如果某条断言与本单要求直接冲突，允许只改那一条，并在报告里逐条列出改了哪里、为什么。其余断言不动。

**何时停下来问**：只有本单自相矛盾、或照做会让某条既有测试变红且放宽条款不覆盖时才停下来说明；只影响「怎么实现 / 怎么测」的问题自己决定并在报告里写明理由。你实测到的事实优先于本单的断言，不符就停下来说明。

## 白名单（本轮）

可修改：`frontend/lib/messageMarkdown.ts`、`frontend/components/VoiceButton.tsx`、`backend/tests/test_ui_polish_fix_r2.py`（只限 O1 第 3 条所说的那一个用例）、`docs/tasks/2026-10-26-ui-polish/03-report.md`。
可新增：`backend/tests/test_ui_polish_fix_r3.py`。

## O1 去掉 `stripMessageMarkdown` 里的数字占位处理

现状：`frontend/lib/messageMarkdown.ts` 的 `stripMessageMarkdown` 先把「数字夹住的 `**`」换成私用区字符 U+E000（常量 `LITERAL_DOUBLE_STAR`），解析后再换回 `**`。副作用：原文里本来就有 U+E000 时会被改成 `**`；而且只照顾数字，strip 的结果与渲染结果不一致（`"2**10**3"` 渲染成「2」+着重「10」+「3」，strip 却返回 `"2**10**3"`）。这个函数目前没有调用方。

改法：

1. 删掉 `LITERAL_DOUBLE_STAR` 常量、那条 `replace`、末尾的 `split(...).join("**")`，以及相关注释。`stripMessageMarkdown` 直接对 `parseMessageMarkdown(text)` 的结果拼纯文本，其余逻辑（各块类型的拼法、列表编号、块之间用两个换行连接）不变。
2. 结果应当等于「渲染结果的纯文字」：成对的 `**` 已被解析成着重，剩下的 `**` 原样保留。
3. `backend/tests/test_ui_polish_fix_r2.py` 里 `"combined"` 用例的输入 `"2**10 和 **重点**"` 与 T1「从左到右配对」冲突（第一个 `**` 会和「重点」前面的 `**` 配对），按放宽条款把这个用例的输入改成 ``"2**10 和 `x`"``，对应断言的期望值改成 `"2**10 和 x"`。这个文件里别的地方不动。

测试（新文件 `test_ui_polish_fix_r3.py`，能跑 node 时运行时断言，node 依赖缺失时按现有做法 skip，并保留下面的源码断言不 skip）：
- `stripMessageMarkdown("2**10**3")` → `"2103"`。
- 含 U+E000 的原文原样返回：在 JS 里用 `String.fromCharCode(0xE000)` 构造 `"x " + 该字符 + " y"`，断言结果与输入完全相同。**不要在任何源文件或测试文件里直接写入这个不可见字符，也不要写它的反斜杠 u 转义**，一律用 `String.fromCharCode(0xE000)`（JS）或 `chr(0xE000)`（Python）构造。
- `stripMessageMarkdown("2**10 和 `x`")` → `"2**10 和 x"`；`"**重点**"` → `"重点"`；`"a ** b"` → `"a ** b"`。
- 源码断言：`messageMarkdown.ts` 不含 `LITERAL_DOUBLE_STAR`，文件字节里不含 `chr(0xE000)` 的 UTF-8 编码。

## O2 长按之后没有 click 时，下一次键盘 / 读屏点击不应被吞

现状（`frontend/components/VoiceButton.tsx`）：`handlePointerUp` 处理完会置 `pointerUpHandledRef`，`handleLostPointerCapture` 会把它转存到 `captureLostAfterPointerUpRef`；`handleClick` 见到任一标记就吞掉这次 click。手机浏览器长按后通常不派发 click，标记就一直留着，用户随后用外接键盘或读屏软件点按钮时，第一次点击没反应（复核实测序列：`pointerdown → 等过长按阈值 → pointerup → lostpointercapture →（没有 click）→ click(detail=0)`，onTap 0 次）。

改法：只吞「紧跟在 pointerup 后面」的那次 click。

1. 新增模块级常量 `const CLICK_AFTER_POINTERUP_MS = 500;`，新增 `pointerUpAtRef`（初值 `Number.NEGATIVE_INFINITY`）。
2. `handlePointerUp` 在置 `pointerUpHandledRef.current = true` 的同时记下 `pointerUpAtRef.current = performance.now()`。
3. `handleClick`：只要见到两个标记中的任何一个，就把两个标记都复位；只有当 `performance.now() - pointerUpAtRef.current <= CLICK_AFTER_POINTERUP_MS` 时才吞掉这次 click，超过时限就照常调用 `handleTap()`。没有标记时照常调用 `handleTap()`。
4. `handleClick` 保持无参数（`const handleClick = () => {`），不要读 `event.detail`；保留 `if (pointerUpHandledRef.current) {` 这个分支写法，现有源码断言依赖它。其余状态机（短按、长按、录音中短按、pointercancel、lostpointercapture、禁用、首次提示）不变。

测试（放进 `test_ui_polish_fix_r3.py`，照 `test_ui_polish_fix_r2_controls.py` 的假事件写法驱动组件）：
- ① 复核序列：长按 → pointerup → lostpointercapture → 等待 `CLICK_AFTER_POINTERUP_MS + 150` 毫秒 → `click({detail: 0})` → `{tap: 1, start: 1, end: 1}`。
- ② 同上，但最后是 `click({detail: 1})`（读屏软件）→ `{tap: 1, start: 1, end: 1}`。
- ③ 短按 → pointerup → 立即 `click({detail: 1})` → `{tap: 1, start: 0, end: 0}`（同一次指针操作带出的 click 仍被吞）。
- ④ 长按 → pointerup → lostpointercapture → 立即 `click({detail: 1})` → `{tap: 0, start: 1, end: 1}`。
- ⑤ 短按 → pointerup → 等待超过时限 → `click({detail: 1})` → `{tap: 2, start: 0, end: 0}`（超时后的 click 是新的一次点击）。
- 源码断言：含 `const CLICK_AFTER_POINTERUP_MS = 500;`，`handleClick` 函数体里出现 `performance.now()` 与 `CLICK_AFTER_POINTERUP_MS`。

## 验收（全部）

- `cd frontend && npx tsc --noEmit` 退出码 0；`npm run lint` 0 errors、25 warnings；`npm run build` 成功。
- 后端全量 `cd backend && <Fiona 主检出>/backend/.venv/bin/python -m pytest -q` 0 失败；`test_ui_polish_fix_r3.py` 全部通过；改动前就存在的测试一字未改。
- `test_ui_polish_fix_r2_controls.py`、`test_ui_polish_composer_controls.py` 不改且全部通过（O2 不得让 R2 的读屏 / Chrome 顺序用例变红）。
- 改动集合只多出 `backend/tests/test_ui_polish_fix_r3.py` 一个新文件；修改只涉及本单白名单。
- 在 `03-report.md` 末尾追加「R3」一节：两项各改了什么、改动了哪些本任务新增测试的断言（逐条列出）、各项测试的原始摘要行。
