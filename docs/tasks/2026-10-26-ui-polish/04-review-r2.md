# 04 第二轮独立复核：R2 返修（前端 UI 打磨）

复核方与实现方、第一轮复核方都没有共享上下文。按工作流规则，本轮只核验 R2 是否落实、有没有引入回归，不新增主观问题；新发现的问题都放在 §6 可优化项。

- 复核副本：会话临时目录下的 `review-ui-polish`（基线 `5985f43` + 待审改动）。
- 开工时 `git diff 5985f43 | shasum -a 256` = `0fcbb02ed0a082931dcc49caaf38a77c47cd9146e05f229baf19c08d1b5e1aab`，结束时复测为同一值；开工时的 19 个未跟踪文件，sha256 开工 / 结束逐个一致（另外只多了本报告这一个新文件）。
- 变异实验的备份、对照脚本都放在 `.review/r2check/`，做完已删除。我的 tsc / build 生成的 `frontend/.next`、`next-env.d.ts`、`tsconfig.tsbuildinfo`（开工时都没有）也已删除。`.review/` 下只剩 Claude 给的三个输入文件。
- 实现方报告 03-report 只当线索，以下结论都来自本次实测。
- 对照用的「R2 前版本」：R2 之前新增文件的内容没有保存。`messageMarkdown.ts` 的 R2 前版本是我按返修单从当前文件推回去的：标题正则换回旧写法、去掉 `headingContent`、行内按块传 `typing`、去掉末尾重算、strip 恢复 `replace(/\*\*/g,"")`。推回版的行号与第一轮报告引用的位置一致（第 17 行正则、177 行 `if (typing)`、234 行列表项；标题 / 引用 / 段落的调用处只差 R2 新增的几行），可以当正控用。`VoiceButton` 的 R1 写法同样按 02-spec T6 还原（`event.detail === 0`）。

## 1. 结论：通过

R2-1 到 R2-7 全部按单落实，没有发现 R2 引入、并破坏前几轮已通过行为的回归。本任务测试被改动的 5 处断言都是与本单直接冲突、必须改的，没有发现借机放松或删除别的断言（核验手段和局限见 §3）。

有两处实现偏离了返修单的字面写法，请 Claude 知悉：
- **R2-5**：多了一个「接力」标记 `captureLostAfterPointerUpRef`。这处偏离是**必要的**：照单子字面写（lostpointercapture 直接复位、不接力），在浏览器真实的 `pointerup → lostpointercapture → click` 顺序下，短按会触发两次 onTap。我用假事件验证过（§2 R2-5）。
- **R2-6**：为了凑出单子要求的 `"2**10 和 重点"`，额外加了「数字夹住的 `**` 先换成 U+E000 占位、最后还原」的处理，超出了单子写的改法。它带来一个新的小缺陷：原文里本来就有 U+E000 时，会被改成 `**`。目前这个函数没有任何调用方，用户看不到影响，所以不判为必须修复，列为 O1，请 Claude 裁决。

## 2. R2-1 到 R2-7 逐条核验

### R2-1 打字时只去掉整段最后一个未配对标记：落实

- 代码：`messageMarkdown.ts` 的 `parseBlocks`（250–339 行）里，行内解析一律按 `false` 调用（列表项 242、标题 281、引用 304、段落 326 行），并用 `lastInlineSource` 记下最后一块的原文；列表通过 `parseList` 返回的 `lastText` 只记最后一项；代码块和分隔线把它置为 `null`（271、290 行）。329–337 行在 `typing` 为真时只重算最后一块或最后一项。
- 用第一轮报告的复现输入亲测（node 加载当前文件，旧版为推回版）：

| 输入（typing:true） | 当前结果 | R2 前（正控） |
|---|---|---|
| `"2**3 是幂\n\n正在**强"` | `["2**3 是幂"]`、`["正在强"]` | `["23 是幂"]`、`["正在强"]` |
| `"- 2**10\n- 正在**强"` | 项 `"2**10"`、`"正在强"` | `"210"`、`"正在强"` |
| 多个列表 `` "- 2**10\n- a`b\n\n1. 3**4\n2. 正在**强" `` | `"2**10"`、`` "a`b" ``、`"3**4"` 原样，只有末项 `"正在强"` | `"210"`、`"ab"`、`"34"`、`"正在强"` |
| 种类切换 `"- 2**10\n1. 正在**强"`、嵌套末项 `"- 2**10\n  - 子**项"` | 前项保留，只改末项 | 前项被改 |
| 末尾是未闭合代码块 `` "2**3 是幂\n\n```\nconst a = `x" `` | 段落 `"2**3 是幂"`，代码块 `` "const a = `x" `` | 段落 `"23 是幂"` |
| 末尾是未闭合代码块 `` "- a**b\n```\n未闭合**" `` | 列表项 `"a**b"` 保留 | `"ab"` |
| 末尾是引用 `"2**3 是幂\n\n> 正在**强"` | 段落保留，引用 `"正在强"` | 段落 `"23 是幂"` |
| 末尾是分隔线 `"a**b\n\n***"` | 段落 `"a**b"` 保留 | `"ab"` |

- typing=false 不变：`test_ui_polish_markdown.py` 里 `PARSE_CASES` 的 32 条输入，当前输出、推回版输出与 `test_ui_polish_fix_r2.py` 里的固定快照三者逐条 JSON 相同，**0 差异**。两个文件里的 `PARSE_CASES` 字典完全相同（用 `ast.literal_eval` 比对）。PARSE_CASES 里按原选项（含 typing:true 的单块用例）跑，当前与推回版也 0 差异。另外随机生成 60000 条不含 `#` 的 Markdown 片段（列表、引用、围栏、`**`、反引号、全角空格、tab 混排），typing=false 下新旧 **0 差异**。
- typing=true 的性质检验（同样 60000 条）：除最后一块外都与 typing=false 完全相同；最后一块（列表是最后一项）与旧的逐块算法对这一块的结果相同；以代码块或分隔线结尾时整段与 typing=false 相同。**0 违例**。
- 03-report 说的 6 组用例都在新测试里（`test_ui_polish_fix_r2.py` 190–270 行），另外补了标题、引用、分隔线结尾三组，还有一条源码兜底断言（`parseBlocks` 里恰好一处 `parseInline(…, true)`，没有 `parseInline(…, typing)`）。

### R2-2 标题正则改成线性写法：落实

- `HEADING_RE = /^\s{0,3}(#{1,6})[ \t]+(.*)$/`（第 17 行），`isBlockStart` 用的是同一个常量（第 44 行）。`headingContent`（58–65 行）用字符串处理去尾：先 `trimEnd`，结尾那串 `#` 前面紧挨着空白、或整行内容只有 `#`，才去掉。
- 亲测计时（node `process.hrtime`，单位 ms）：

| 输入形状 | N=1000 | N=5000 | N=20000 |
|---|---|---|---|
| `"# a" + N 个空格 + "b"` | 0.3 | 0.1 | 0.3 |
| 段落后接该行（走 `isBlockStart`） | 0.3 | 0.2 | 0.3 |
| 列表续行里的该行（走 `isBlockStart`） | 0.1 | 0.0 | 0.1 |
| 同上加 `**`、typing:true | 0.1 | 0.0 | 0.2 |
| 正控：旧正则 `"# a"+N空格+"b"` | 266.0 | —（N=2000 时 1752.7） | — |
| 正控：旧正则走 `isBlockStart`（N=1000） | 528.6 | — | — |

- 用例（当前结果）：`"# 学习 C#"` → 标题「学习 C#」；`"## 标题 ##"` → 「标题」；`"# 标题#"` → 「标题#」；`"#标题"` → 段落；`"# "`、`"# ###"`、`"# #"` → 标题，inlines 为 `[]`；`"### C++ 与 C# ###"` → 「C++ 与 C#」；`"    # x"`、`"####### x"`、`"#"` → 段落。都符合本单。
- 独立判据：按 R2-2 的文字另写一个判定（同一匹配正则 + `replace(/(^|\s)#+$/, "$1").trimEnd()`），随机 10 万条标题样式的单行里有 23278 条能匹配，当前实现与判定 **0 差异**。
- 残留：行内含 `.` 匹配不到的字符（单独的 `\r`、U+2028）时仍有平方级回溯，见 O3；全角空格不再算标题分隔，见 O4。两者都是本单指定的正则本身带来的。

### R2-3 手机图片 / 改图模式的模型分组：落实（只核对 CSS 与 markup）

- `globals.css:546` `.image-model-segments` 改成 `flex-wrap:wrap`；`:547` `.chip` 由 `min-width:0` 改为 `flex-shrink:0`；`:549` `.composer-inner.composer-with-model` 为 `grid-template-areas:"text text" "tools tools" "models models" "exit actions"`；`:548` 普通状态仍是 `"text text" "tools actions"`（与 R1 一样）。
- `:553` `.composer-mode-exit` 改为 `justify-self:start`，`:559–561` 新增一条不在任何 `@layer` 里的 `@media (width < 48rem) { .composer-inner.composer-with-model .composer-mode-exit { margin-left:0; } }`。这条是必要的：两个退出按钮在 `page.tsx:2701/2703` 上带 `ml-auto`，在网格里 `margin-left:auto` 会压过 `justify-self`，把按钮推到右边；utilities 层又比 components 层优先，所以只能用不分层的规则盖掉。作用范围与原来分层的网格规则相同（都是 `width < 48rem`，没有 data-shell 限定），不影响桌面。
- markup：`composer-toolbar` / `composer-mode-tools` 是 `display:contents`，网格的直接子元素只有 `composer-text`、`composer-tools`、`image-model-segments`（仅 `imageMode || hasReferenceImages` 时渲染，`page.tsx:2699`）、`composer-mode-exit`（同条件）、`composer-actions`，每个都有对应的区域名；`composer-with-model` 类名也只在同一条件下加（`page.tsx:2630`）。所以 Claude 实测的 gridTemplateAreas、模型分组独占一行、chip 不缩到比文字窄，CSS 都能达成。
- 构建产物（删掉 `.next` 后重新 build）里有 `grid-template-areas:"text text""tools tools""models models""exit actions"`、`.image-model-segments .chip{flex-shrink:0;…}`、`.composer-mode-exit{grid-area:exit;justify-self:start}`，以及 `@media not all and (min-width:48rem){.composer-inner.composer-with-model .composer-mode-exit{margin-left:0}…}`。

### R2-4 图片菜单四处细节：落实

| 条目 | 代码 | 行为验证（自写的小型 hooks 运行时：useState / useEffect 按依赖跨次渲染，refs 接假 DOM 节点） | 正控（只撤掉这一处） |
|---|---|---|---|
| ① 禁用时复位 | `ComposerImageMenu.tsx:26–31`，依赖 `[triggerDisabled]` 的 effect 里 `setOpen(false)` | 打开 → 全部禁用 → 再可用：菜单不再弹出，焦点仍在原处（`textarea`） | 菜单自己弹出，焦点被抢到第一项「see」 |
| ② Escape 不外传 | `:61–66`，含 `event.stopPropagation()` | `stopPropagation` 调用 1 次，菜单关闭，焦点回到触发按钮。页面上的历史面板监听（`page.tsx:572–577`）挂在 document 冒泡阶段，React 根节点上的 stopPropagation 能挡住它 | 调用 0 次 |
| ③ 选中后焦点回到按钮 | `:78–82`：`setOpen(false)` → `item.onSelect()` → `triggerRef.current?.focus()`，同步执行，没有定时器 | `onSelect` 执行后，处理函数一返回，焦点就在触发按钮上，菜单已关 | 焦点留在菜单项上 |
| ④ 可用时也有 title | `:115` `title={item.title}` | 三项（含两个可用项）都带各自的 title | — |

`page.tsx` 里三个菜单项的 `disabled` / `title` 条件，R2 前后逐字相同（page.tsx 的 diff 在 R2 前后只差 BOM 那一段）。

### R2-5 语音按钮兼容读屏软件的点击：落实（实现比单子多一个必要的接力标记）

- 代码：`VoiceButton.tsx:24` 的 `pointerUpHandledRef`；`:82` pointerup 处理完置真；`:108–118` `handleClick` 遇到标记就复位并忽略，否则调 `handleTap()`；`:89`、`:101` pointercancel / lostpointercapture 里复位。另有 `:25` `captureLostAfterPointerUpRef`：lostpointercapture 把「刚处理过 pointerup」接力过来（`:100`），紧接着的 click 照样吞掉（`:113–116`）；pointerdown / pointerup / pointercancel 都会清它。源码里已经没有 `event.detail`。
- 假事件驱动结果（tap / start / end 计数）：

| 序列 | 当前 | 照单字面写法（lost 时直接复位） | R1 写法（detail===0） |
|---|---|---|---|
| 短按：down → up → lost → click(1)（Chrome 实际顺序） | 1/0/0 | **2/0/0（双触发）** | 1/0/0 |
| 短按：down → up → click(1) → lost | 1/0/0 | 1/0/0 | 1/0/0 |
| 无指针事件直接 click(detail=1)（读屏软件） | 1/0/0 | 1/0/0 | **0/0/0（无反应）** |
| 键盘 click(detail=0) | 1/0/0 | 1/0/0 | 1/0/0 |
| 长按：down → 等待 → up → lost → click(1) | 0/1/1 | **1/1/1** | 0/1/1 |
| 录音中短按（Chrome 顺序） | 1/0/0 | 2/0/0 | 1/0/0 |
| 连续两次指针短按 | 2/0/0 | 4/0/0 | 2/0/0 |
| down → cancel → lost → 键盘 click | 1/0/0 | 1/0/0 | 1/0/0 |

单子要求的 ①–④ 都满足（新测试 `test_ui_polish_fix_r2_controls.py:308–380` 覆盖了这 4 种，外加 Chrome 顺序 2 种、指针后键盘 1 种）。字面写法在 Chrome 顺序下会双触发，所以多出来的接力标记是必须的。还剩一个边角情况，见 O2。

### R2-6 `stripMessageMarkdown` 不删未配对的 `**`：落实（附带一处超出单子的处理，见 O1）

- `inlinesToPlainText`（354–360 行）现在对所有片段原样拼接 `inline.text`，不再 `replace`。
- 实测：`"2**10"` → `"2**10"`；`"a ** b"` → `"a ** b"`；`"**重点**"` → `"重点"`；`"2**10 和 **重点**"` → `"2**10 和 重点"`。04-review / test_ui_polish_markdown 原有的 4 条 strip 用例新旧结果相同。
- 偏离：362–367、397 行先把 `(\d)\*\*(?=\d)` 换成 U+E000，解析后再换回 `**`。源码里写的是 `"\uE000"` 转义，文件里没有真正的不可见字符。原因是按 T1 从左到右配对，`2**10 和 **重点**` 里第一个 `**` 会和「重点」前面的 `**` 配成一对，单靠「原样输出」得不到单子写的期望值。也就是说，本单的期望值与 T1 的配对规则本身冲突。实现方在报告里说明了这一点，但没有停下来问。影响见 O1。

### R2-7 恢复 `page.tsx` 首行 BOM：落实

- `head -c 3 frontend/app/page.tsx | xxd -p` → `efbbbf`，基线 `git show 5985f43:frontend/app/page.tsx | head -c 3` 也是 `efbbbf`。
- `git diff 5985f43 -- frontend/app/page.tsx | head -8` 的第一个 hunk 是 `@@ -14,10 +14,13 @@`，不再有第 1 行。
- 把 `.review/diff-before-r2.patch` 与当前 diff 逐行比较：page.tsx 部分只少了 `@@ -1,4 +1,4 @@` 那一段（还有 index 行），其余 hunk 完全相同。

## 3. 被改动的本任务测试断言

| # | 文件:行 | R2 前 → 现在 | 判断 |
|---|---|---|---|
| 1 | `test_ui_polish_composer_controls.py:66` | `"title={item.disabled ? item.title : undefined}" in source` → `"title={item.title}" in source` | 与 R2-4④ 直接冲突，必要。强度没降：新文件里还另断言了不含 `item.disabled ? item.title`，并在渲染里核对可用项的 title |
| 2 | 同文件 `:112–113` | 两条 `event.detail === 0` 源码断言 → `"if (pointerUpHandledRef.current) {"`、`"pointerUpHandledRef.current = false;"` | R2-5 明文允许修改；旧写法本身就是 R2-5 要求删掉的。必要 |
| 3 | 同文件 `:489` | `keyboard` 期望 tap 1 → tap 2（该用例依次发 detail=0、detail=1 两次无指针 click） | R2-5② 要求无指针的 detail=1 click 也调 onTap，直接冲突，必要。hint 断言没动 |
| 4 | `test_ui_polish_page_contracts.py:185` | `"text text" "tools actions" "models exit"` → `"text text" "tools tools" "models models" "exit actions"` | R2-3 指定的新网格，直接冲突，必要。`:184` 普通状态 `"text text" "tools actions"` 的断言保留 |
| 5 | 同文件 `:187` | `.composer-mode-exit { grid-area:exit; justify-self:end; }` → `justify-self:start` | R2-3 要求退出按钮在最后一行左边，`end` 与之冲突，必要。`:81` 对 `composer-mode-exit ml-auto` 的断言保留 |

有没有借机放松或删除别的断言？R2 前的测试文件没有快照，没法逐字比对，下面是间接证据：
- 测试数量：6 个文件当前分别是 21 / 8 / 2 / 21 / 11 / 6 条，共 69 条，与第一轮报告记的「6 个新测试文件 69 passed」相同。没有删掉的用例。
- 证明力：第一轮的 M2（有序列表正则）、M3（`wasLongPress && false`）、M4（em 里不高亮）三个变异原样重做，失败的测试和失败原因与第一轮报告逐条相同（§4.2）。composer_controls 仍然能抓到长按状态机被改坏（2 failed，运行时 `{'tap': 1} != {'tap': 0}`、`{'end': 0} != {'end': 1}`）。
- 02-spec T9 对 composer_controls / page_contracts 要求的覆盖项逐项都在（`event.detail === 0` 那项已由 R2-5 修订为新断言）。
- `test_ui_polish_markdown.py` 与 `test_ui_polish_fix_r2.py` 的 `PARSE_CASES` 相同；markdown 测试里没有钉死标题正则字面的断言（第一轮 M2 也证明这些测试是运行时断言），R2-2 不需要改它。
- 03-report 的 R2 一节自报的改动正好是这 5 处，还说明 R2 代理一度扩写过 handleSelect / timeout / try-count 断言、后来已还原。当前 `:84–86` 的 `"setOpen(false);\n    item.onSelect();"`、`setTimeout` / `requestAnimationFrame` 不在源码中，以及 `:94` 的 `try {` 计数断言都在。

结论：5 处都是与本单直接冲突的必要修改，没有发现放松或删除。

## 4. 回归检查、证明力与机械门禁

### 4.1 回归检查

| 项 | 证据 | 结论 |
|---|---|---|
| Markdown 渲染 | typing=false 下 PARSE_CASES 32 条 + 随机 60000 条（不含 `#`）新旧 0 差异；只有标题行的变化，而且都在 R2-2 规定范围内（独立判据 0 差异）；`MessageText.tsx` 的 8–19、26 行与第一轮报告引用的内容一致；`test_ui_polish_markdown.py` 21 条、`test_ui_polish_fix_r1.py` 2 条全过 | 无回归 |
| VoiceButton 其他分支 | composer_controls 的运行时状态机（短按、长按、录音中短按、短按 / 长按被 cancel 或 lost、禁用、首次提示）全过；我自己的序列：录音中短按、cancel 后键盘点击、连续两次短按都正确 | 无回归（边角情况见 O2） |
| 菜单禁用逻辑 | `page.tsx` 三项的条件 R2 前后逐字相同；`triggerDisabled` / `allDisabled` / `isOpen` 没变；SSR 断言「全部禁用 → 触发按钮 disabled」照过；运行时全部禁用时菜单隐藏 | 无回归 |
| 北京时间、设置页 key、嵌入时 sr-only | R2 前后两份 tracked diff 逐行比较，只有 `globals.css` 的手机网格 / 新增 margin 规则和 `page.tsx` 的 BOM 两处不同；history / settings / profile / novels / plaza / LocalWatch / AgentExchange / MyAgent / ChatBubble / ConversationPicker / chatModel / chineseDate 的 diff 完全相同；beijing_time 21 条、settings_drawers 6 条全过 | 无回归 |
| 既有测试一字未改、backend 其他文件零改动 | `git diff 5985f43 -- backend \| wc -l` = 0；`git status --short -- backend` 只有 8 个 `?? backend/tests/test_ui_polish_*.py`；`git diff --diff-filter=D` 为空；`package.json` / `package-lock.json` 无改动 | 通过 |
| 改动集合 ⊆ 各轮白名单 | 已跟踪的 14 个修改都在 02-spec §3；新增 5 个前端文件在 §3；测试 = §3 的 5 个 + R1 的 `fix_r1` + R2 的 `fix_r2` / `fix_r2_controls`；docs 下只有 03-report 是实现方写的。R2 这一轮自己动的：tracked 只有 `globals.css`、`page.tsx`；新文件只有 `messageMarkdown.ts`、`ComposerImageMenu.tsx`、`VoiceButton.tsx`、两个新测试和 §3 列的冲突断言，全在 R2 白名单内。`ComposerImageMenu.tsx` 的行号偏移与第一轮引用对得上（23 行不变；焦点 effect 26→33；title 106→115，正好是新 effect 7 行 + Escape 1 行 + handleSelect 1 行） | 通过 |
| 不加粗 / 不注入 HTML | 新文件与 `git diff -U0` 的 `+` 行用 `font-(semibold\|bold\|extrabold\|black)\|font-weight:\s*[6-9]00\|fontWeight\|<strong\|<b[ >]` 扫描都无命中（正控 `+<b className="x">` 能命中）；`dangerouslySetInnerHTML` 无命中；`git diff --check` 通过；R2 文件里没有 0xa0 / U+2060 / U+200B | 通过 |
| 没有 node_modules 时 | 把 8 个测试和前端源码拷到不含 node_modules 的目录里跑：`51 passed, 43 skipped`，0 failed；两个 R2 新文件 `8 passed, 17 skipped`，跳过原因是「Frontend dependencies unavailable」，源码断言照常执行 | 通过 |

### 4.2 证明力（变异实验：每次只改一处，跑对应测试，再用备份还原，`cmp` 一致）

| # | 临时改坏的地方 | 结果 | 还原 |
|---|---|---|---|
| MA | R2-1：段落改回按块传 `typing`（回到第一轮缺陷） | `test_ui_polish_fix_r2.py` **7 failed**（多段落、未闭合代码前、反引号后接段落、标题结尾、引用结尾、分隔线结尾，以及源码兜底） | cmp 一致 |
| MA2 | R2-1：关掉末尾重算 | fix_r2 5 条 + markdown 1 条，共 **6 failed** | cmp 一致 |
| MB | R2-2：去掉「结尾 # 前必须是空白」的判断 | **2 failed**（`学习 C#`、`标题#`） | cmp 一致 |
| MB2 | R2-2：换回第一轮的正则 | **5 failed**，其中计时用例报 `long heading line took 20811ms` | cmp 一致 |
| MC1 | R2-5：pointerup 不再置标记（click 不被吞） | **2 failed**：运行时 `{'tap': 2} != {'tap': 1}`，源码断言也失败 | cmp 一致 |
| MC2 | R2-5：去掉 lostpointercapture 的接力 | **1 failed**：运行时 Chrome 顺序 `{'tap': 2} != {'tap': 1}`（只有运行时用例抓到） | cmp 一致 |
| MC3 | R2-5：改回只认 `detail===0` | **3 failed**：新文件运行时 `{'tap': 0} != {'tap': 1}`、源码断言，以及 composer_controls 运行时 `{'tap': 1} != {'tap': 2}` | cmp 一致 |
| MD1 | R2-4①：effect 里去掉 `setOpen(false)` | **1 failed**（只有源码断言抓到） | cmp 一致 |
| MD2 | R2-4④：title 改回只在禁用时带 | **3 failed**（新文件源码 + 渲染 `assert 0 == 1`，composer_controls 源码） | cmp 一致 |
| ME | R2-6：strip 恢复删除全部 `**` | **2 failed**（`'a  b' == 'a ** b'`、源码断言） | cmp 一致 |
| M2/M3/M4 | 第一轮的三个变异原样重做 | 结果与第一轮相同：M2 1 failed（`'list' == 'para'`）；M3 2 failed；M4 1 failed（`expected exactly one mark`） | cmp 一致 |

全部还原后，8 个本任务测试文件 `94 passed in 3.63s`。

### 4.3 机械门禁（原始摘要行）

```text
$ cd frontend && npx tsc --noEmit; echo $?
TSC_EXIT=0

$ cd frontend && npm run lint
✖ 25 problems (0 errors, 25 warnings)        LINT_EXIT=0
（24 条在 app/page.tsx，1 条在 app/plaza/page.tsx；新文件 0 条，与基线持平）

$ cd frontend && rm -rf .next && npm run build
✓ Compiled successfully in 1608ms
✓ Generating static pages using 17 workers (18/18) in 168ms
BUILD_EXIT=0

$ cd backend && <Fiona 主检出>/backend/.venv/bin/python -m pytest -q -p no:cacheprovider
7740 passed, 35 warnings in 278.66s (0:04:38)
EXIT=0（0 failed，0 skipped；= 第一轮 7715 + R2 新增 18 + 7）
```

## 5. 必须修复项

无。

## 6. 可优化项（新发现的问题，不算必须修复）

- **O1（需要 Claude 裁决）R2-6 的数字保护会改坏原文里的 U+E000，并让 strip 与渲染不一致**。`messageMarkdown.ts:362–367、397`。实测：`stripMessageMarkdown("x \uE000 y")` 返回 `"x ** y"`，改动前原样返回。`"2**10**3"` 渲染成「2」+着重「10」+「3」，strip 却给出 `"2**10**3"`。非数字的同类输入 `"a**b 和 **重点**"` 仍返回 `"ab 和 重点**"`，保护只照顾到数字。目前 `stripMessageMarkdown` 在 `app/`、`components/`、`lib/` 里都没有调用方，所以用户看不到影响。建议二选一：① 去掉这段保护，把 `test_ui_polish_fix_r2.py:320` 的 `combined` 用例换成不和 T1 配对规则冲突的输入（比如 `` "2**10 和 `x`" ``），让 strip 等于「渲染结果的纯文本」；② 保留，但换一个不会和原文冲突的办法（比如先扫描原文里是否已有占位符），并在规格里写明 strip 与渲染可以不一致。
- **O2 VoiceButton：指针操作后没有 click 时，下一次键盘 / 读屏点击会被吞一次**。`VoiceButton.tsx:100、113–116`。序列 `down → 长按 → up → lostpointercapture →（没有 click）→ 键盘 click(detail=0)`：当前 onTap 0 次，R1 写法 1 次。手机浏览器长按后通常不会再派发 click，所以触屏用户长按说话后改用外接键盘或读屏软件点按钮时，第一次点击没反应；下一次 pointerdown 会清掉标记。发生面很窄。可选改法：`detail === 0` 的 click 一律放行（键盘点击前不会有 pointerup），只吞 `detail ≥ 1` 的；或者只吞同一个任务内、或很短时间窗内到达的 click。
- **O3 标题正则在特定字符下仍有平方级回溯**。`[ \t]+(.*)$` 遇到 `.` 匹配不到的字符（单独的 `\r`、U+2028、U+2029）时，`$` 失败会引起回溯。实测 `"#" + N 个空格 + "b\r"`：N=1000 / 5000 / 20000 分别 0.7 / 15.6 / 152.5 ms；U+2028、N=20000 为 130 ms。`\r\n` 被拆在两个流式分片里时，末尾可能暂时出现单独的 `\r`，但还需要 `#` 后面紧跟上万个空格，实际几乎遇不到。这是本单指定的正则。若要彻底线性，可以改用 `([\s\S]*)$`，或在匹配前把单独的 `\r` 规范掉。
- **O4 `#` 后接全角空格不再是标题**。`"#　标题"` 旧正则（`\s+`）判为标题，现在判为段落，因为本单指定 `[ \t]+`。这是规格的选择，记下供以后参考；模型回复里一般是半角空格。
- **O5 R2-4 ①②③ 的测试只有源码断言**。MD1 只被源码正则抓到；禁用复位、Escape 不外传、焦点回到按钮都没有运行时用例（本单允许只写源码断言）。§2 R2-4 用的小型 hooks 运行时可以照搬成测试，提高证明力。
- **O6（R2 之前就有，与 R2 无关）去掉反引号可能让 `**` 重新配对**。`` "**`**强a" `` 在 typing 时显示成 `"****强a"`，输出结束后变成着重「`」+「强a」。`parseInline` / `findLastUnmatchedDelimiter` 在 R2 里没动，R1 版本结果相同，影响极小。
