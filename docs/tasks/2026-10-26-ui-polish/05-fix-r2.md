# 返修 R2（独立复核后，2026-10-26）

本返修单与 `02-spec.md`、`05-fix-r1.md` 同等效力，冲突时以本单为准。复核原文在 `04-review.md`。§2 的约束照旧：不加粗、不新增依赖、不重排无关代码、白名单外不改；**改动前就存在的测试（基线测试）一字不许改**。

**本单放宽一条**：本任务自己新增的 6 个测试文件（`backend/tests/test_ui_polish_*.py`）中，如果某条断言与本单要求直接冲突，允许只改那条断言，并在报告里逐条列出改了哪里、为什么。其余断言不动。

## 白名单（本轮）

可修改：`frontend/lib/messageMarkdown.ts`、`frontend/components/ComposerImageMenu.tsx`、`frontend/components/VoiceButton.tsx`、`frontend/app/globals.css`、`frontend/app/page.tsx`、本任务的 6 个 `backend/tests/test_ui_polish_*.py`（仅限上一段所说的冲突断言）、`docs/tasks/2026-10-26-ui-polish/03-report.md`。
可新增：`backend/tests/test_ui_polish_fix_r2.py`、`backend/tests/test_ui_polish_fix_r2_controls.py`。

## 执行方式

用工作流（workflow 工具）并行，按文件不重叠拆成 3 个 agent，每个 agent 的说明自包含（抄入本单相关条目和 §2 约束），写明不得调用 subagent / subagent_fork / workflow：
- A：R2-1、R2-2、R2-6（`messageMarkdown.ts` + 新文件 `test_ui_polish_fix_r2.py` + 必要时 `test_ui_polish_markdown.py` 的冲突断言）
- B：R2-4、R2-5（`ComposerImageMenu.tsx`、`VoiceButton.tsx` + 新文件 `test_ui_polish_fix_r2_controls.py` + 必要时 `test_ui_polish_composer_controls.py` 的冲突断言）
- C：R2-3、R2-7（`globals.css`、`page.tsx` + 必要时 `test_ui_polish_page_contracts.py` 的冲突断言）

主代理汇总后跑验收，把结果写进 `03-report.md` 末尾新的「R2」一节。

## R2-1 打字时只去掉整段最后一个未配对标记（必须修）

现状与复现见 `04-review.md` §3 R2-1：`parseInline` 在每个段落 / 列表项 / 标题 / 引用里各去掉一个未配对的 `**` 或反引号，`"2**3 是幂\n\n正在**强"`（typing）第一段显示成「23 是幂」。

改法（照 `04-review.md` §5 第 1–3 步）：`parseBlocks` 解析行内一律按 `typing=false`，记下最后一个块的原始行内文本（列表只记最后一项）；结束后若 `typing === true` 且最后一块是 `para` / `heading` / `quote`，用 `parseInline(原文, true)` 重算它；是 `list` 只重算最后一项；是 `code` / `rule` 什么都不做。`typing` 为假时输出与现在逐字节相同。

测试（新文件 `test_ui_polish_fix_r2.py`）：`04-review.md` §5 第 4 步列的 6 条全部写上。

## R2-2 标题正则改成线性写法（必须修）

现状：`HEADING_RE = /^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/` 有多项式回溯，`"# a" + 2000 个空格 + "b"` 解析要 1.7 秒，打字时每次刷新都会重新解析，会卡住页面。另外 `"# 学习 C#"` 被解析成「学习 C」。

改法：标题行用 `/^\s{0,3}(#{1,6})[ \t]+(.*)$/` 匹配（`isBlockStart` 里同样用它），内容再用普通字符串处理去尾：先 `trimEnd()`；如果结尾是一串 `#` 且这串 `#` 前面紧挨着空白（或整行内容就只有 `#`），去掉这串 `#` 再 `trimEnd()`；否则保留（所以 `C#` 不动）。去尾后内容为空的行仍按标题处理，inlines 为空数组。不得再用带相邻 `\s*` / `.+?` 组合的正则。

测试：`"# a" + " ".repeat(5000) + "b"` 的解析在 200ms 内完成（node 里用 `Date.now()` 计时，给足余量）；`"# 学习 C#"` → 标题文字「学习 C#」；`"## 标题 ##"` → 「标题」；`"# 标题#"` → 「标题#」；`"#标题"`（无空格）→ 段落。

## R2-3 手机图片 / 改图模式下模型分组文字溢出（必须修）

现状：Claude 实测 360×740 与 320×640 手机宽度、进入「生成图片」模式后，「模型」那组按钮被压在 `"models exit"` 一行的第一列里，`.image-model-segments` 又是 `flex-wrap:nowrap`、`.image-model-segments .chip { min-width:0 }`，结果「Seedream 5.0 Flash」的文字超出按钮边框，「Qwen 3.0」顶到边框。改动前模型分组独占一整行，没有这个问题。

改法（`globals.css` 手机断点内）：`.composer-inner.composer-with-model` 改为 `grid-template-areas:"text text" "tools tools" "models models" "exit actions"`（模型分组独占一行；「返回聊天 / 全部取消」放在最后一行左边，语音与「生成 / 修改」在右边）。`.image-model-segments` 允许换行（`flex-wrap:wrap`），其中的 `.chip` 不得窄于自身文字（去掉 `min-width:0`，或改成 `flex-shrink:0`）。非图片模式的两行布局（`"text text" "tools actions"`）不变。

验收由 Claude 在浏览器里测：320、360、390 三种宽度下，普通 / 生成图片 / 改图三种状态，输入区里每个按钮与 chip 都满足 `scrollWidth <= clientWidth`（文字不溢出），彼此不重叠，页面不横向滚动；普通状态输入区高度仍 ≤ 180px。

## R2-4 图片菜单的四处细节（必须修）

1. **禁用时复位**：`triggerDisabled` 变为真时 `setOpen(false)`。现在只是隐藏，`open` 仍为真，等重新可用时菜单会自己弹出并抢走焦点（例如语音识别完自动发送期间）。
2. **Escape 不外传**：处理 Escape 时 `event.stopPropagation()`，避免同时关掉页面上监听 Escape 的历史面板。
3. **选中后焦点回到触发按钮**：`handleSelect` 里先 `setOpen(false)`、同步调用 `item.onSelect()`，再把焦点还给「图片」按钮（可用 `triggerRef.current?.focus()`，放在 `onSelect()` 之后，仍然在同一个事件处理函数里，不要用定时器）。
4. **可用时也显示提示**：菜单项无论是否禁用都带 `title={item.title}`（原来三个按钮在可用时就有「选择 PNG、JPEG 或 WebP；每张不超过5MB…」这类提示）。

测试（新文件 `test_ui_polish_fix_r2_controls.py`）：源码断言 `setOpen(false)` 出现在依赖 `triggerDisabled` 的 effect 里、Escape 分支含 `stopPropagation`、`handleSelect` 里 `onSelect()` 在 `focus()` 之前、菜单项 `title={item.title}`；能跑 node 时用 react-dom/server 渲染打开状态（可用模拟），断言可用项也带 title。

## R2-5 语音按钮兼容读屏软件的点击（必须修，修订 02-spec T6 的 onClick 条目）

现状：只认 `event.detail === 0` 的 click。有些读屏软件模拟点击时 `detail >= 1` 且不先发指针事件，按钮就完全没反应。

改法：用 ref 记「刚由 pointerup 处理过」：`handlePointerUp` 处理完时置真；`onClick` 里若该标记为真，则复位并忽略这次 click（它是同一次指针操作带出来的）；否则（键盘、读屏软件、程序触发）调用 `handleTap()`。`pointercancel` / `lostpointercapture` 也复位该标记。其余状态机不变。

测试：在 `test_ui_polish_fix_r2_controls.py` 里用假事件驱动（照 `test_ui_polish_composer_controls.py` 的写法）：① 指针短按一次 → onTap 恰好 1 次（随后的 click 被吞）；② 没有指针事件、直接 click（detail=1）→ onTap 1 次；③ 键盘 click（detail=0）→ onTap 1 次；④ 长按 → onHoldStart / onHoldEnd 各 1 次、onTap 0 次。`test_ui_polish_composer_controls.py` 里若有断言写死 `event.detail === 0` 的源码片段，按本单开头的放宽条款只改那一条。

## R2-6 `stripMessageMarkdown` 不要删掉未配对的 `**`（应修，改动很小）

现状：`inlinesToPlainText` 对 text 片段做 `replace(/\*\*/g, "")`，把未配对的也删了（`"2**10"` → `"210"`）。改法：text 片段原样输出（解析器已经把成对的 `**` 变成 em，剩下的都是该保留的字面字符）。测试：`stripMessageMarkdown("2**10 和 **重点**")` → `"2**10 和 重点"`。

## R2-7 恢复 `page.tsx` 首行的 UTF-8 BOM（应修，保持 diff 最小）

基线 `frontend/app/page.tsx` 以三个字节 `EF BB BF` 开头，第一轮被删了。用 Python 按字节恢复（不要在编辑器或工具参数里手打不可见字符）：

```python
p = "frontend/app/page.tsx"
data = open(p, "rb").read()
if not data.startswith(b"\xef\xbb\xbf"):
    open(p, "wb").write(b"\xef\xbb\xbf" + data)
```

验收：`head -c 3 frontend/app/page.tsx | xxd -p` 输出 `efbbbf`；`git diff 5985f43 -- frontend/app/page.tsx | head -8` 不再出现第 1 行的改动。

## 验收（全部）

- `npx tsc --noEmit` 退出码 0；`npm run lint` 0 errors、25 warnings；`npm run build` 成功。
- 后端全量 pytest 0 失败；两个新测试文件全部通过；基线测试一字未改。
- 改动集合 ⊆ 本单白名单 + 前几轮的白名单。
- 在 `03-report.md` 末尾追加「R2」一节：每条改了什么、改动了哪些本任务新增测试的断言（逐条列出）、各项测试的原始摘要行、拆分表。
