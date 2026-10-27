# 04 独立复核：前端 UI 打磨（L2）

复核方与实现方无共享上下文。复核副本：基线 `5985f43` + 待审改动。开工时 `git diff 5985f43 | shasum -a 256` = `3307b79b10afe90641606655253612b30839aa20d06eb29fafebe3611118d1bc`，变异实验结束后复测仍为同一值；4 个被临时改坏的新文件逐个 `cmp` 与备份一致，备份已删除。实现方报告只当线索，以下结论均来自本次实测。

## 1. 结论：不通过

只有 **1 项必须修复**（严重度低、改动小）：打字状态下「去掉末尾未配对的 `**` / 反引号」被按每个块、每个列表项各做一次，违反 T1-9「整段文本最后一个」，流式输出时前面已写完的段落会被改字（`2**10` 显示成 `210`，输出结束后又变回来）。

其余验收标准全部通过：tsc、lint、build、全量 pytest、白名单、粗体检查、innerHTML 检查、浅克隆、R1 三项。另有 12 条可优化项，其中 O1（标题正则在极端输入下会卡死页面）和 O4（`page.tsx` 的 BOM 被顺手删掉）建议在返修时一并处理。

## 2. 验收标准逐条核验

### 02-spec §5

| # | 命令 | 关键输出 | 结论 |
|---|---|---|---|
| 1 | `cd frontend && npx tsc --noEmit; echo $?` | 无输出，`TSC_EXIT=0` | 通过 |
| 2 | `cd frontend && npm run lint` | `✖ 25 problems (0 errors, 25 warnings)`，`LINT_EXIT=0`；24 条在 `app/page.tsx`，1 条在 `app/plaza/page.tsx`，都是原有的未使用变量和 `<img>`，5 个新文件 0 条 | 通过（与基线 25 条持平） |
| 3 | `cd frontend && npm run build` | `BUILD_EXIT=0`，`✓ Generating static pages … (18/18)`；为排除旧构建，查了产物 `.next/static/chunks/*.css`（21:06 新生成），里面有本次新增的 `-webkit-text-emphasis:filled dot var(--ink2)`、`.\[\&_header_h1\]\:sr-only header h1{…}` | 通过 |
| 4 | `cd backend && …/.venv/bin/python -m pytest -q -p no:cacheprovider` | `7715 passed, 35 warnings in 283.46s`，`EXIT=0`，0 skipped，0 failed；只跑 6 个新测试文件：`69 passed`；基线 7646 + 新增 69 = 7715，且 `backend/` 下已跟踪文件零改动 | 通过（本机不用改代理环境变量也能跑全量） |
| 5 | `git status --short`、`git diff 5985f43 --name-only`、`git diff 5985f43 -- backend \| wc -l`、`git diff --diff-filter=D --name-only 5985f43` | 修改了 14 个文件，全在 §3 白名单；新增 5 个前端文件和 6 个测试文件（含 R1 的 `test_ui_polish_fix_r1.py`），以及 docs 下的 01/02/03/05；`backend` 已跟踪文件 diff 为 0 行；没有删除文件；`package.json` / `package-lock.json` 未出现在改动里 | 通过 |
| 6 | `git diff 5985f43 -U0 -- frontend \| grep -E '^\+' \| grep -E 'font-(semibold\|bold\|extrabold\|black)\|font-weight:\s*(6\|7\|8\|9)00\|<strong\|<b[ >]'`；新文件不在 git diff 里，另用同一正则（加上 `fontWeight`）直接 grep 5 个新前端文件 | 两者都无输出（exit=1）；正控：拿 `+<b className="x">` 喂给同一 grep 能命中 | 通过 |
| 7 | `grep -rn 'dangerouslySetInnerHTML' frontend/components/MessageText.tsx frontend/lib/messageMarkdown.ts`；另 grep `<a[ >]\|href\|innerHTML\|createElement(` | 均无输出 | 通过 |
| 8 | 在 `.review/shallow` 里 `git clone --depth 1 file://<副本>`（`is-shallow-repository=true`，没有 `node_modules`），拷入全部改动文件和新文件后跑 6 个新测试 | `43 passed, 26 skipped`，0 failed；跳过原因都是「typescript / react 不可用」，源码断言照常执行（克隆已删除） | 通过 |
| 9 | 只看代码能否达成，并对照 Claude 的实测数字 | 见下 | 通过 |

§5-9 代码层核对：
- **Markdown 与光标**：在 dev 模式下用 `react-dom/server` 渲染 9 种组合（混合块、高亮、正则元字符、空文本带光标、最后一块是分隔线 / 代码块 / 列表 / 标题）。输出里没有原样的 `- `、`**`、`#`；光标在段落、标题、列表最后一项里都贴在文字末尾；没有块时只渲染光标。正控（故意不带 key 的数组）会报 1 条警告，MessageText 渲染时 0 条，所以没有 React key 警告。
- **手机输入区**：`globals.css:548-549` 的网格从「text / tools / actions」三行改为「text text / tools actions」两行，图片模式和改图模式多一行「models exit」。网格里每个元素都有区域：`composer-text`、`composer-tools`、`composer-actions` 任何状态都在；`image-model-segments` 和 `composer-mode-exit` 只在 `imageMode \|\| hasReferenceImages` 时渲染，`composer-with-model` 类名也恰好在同一条件下加上；两个隐藏的文件输入分别在 tools 和 actions 里面。模型说明不再换行（`flex-wrap` 已去掉）。这与 Claude 实测「243→175px」一致。
- **麦克风与图片菜单**：`page.tsx` 里已经没有 `<Mic`、`ImagePlus`、「语音转文字」「按住说话」「上传参考图」按钮，只剩一个 `<VoiceButton>`；`<ComposerImageMenu>` 正好三项。与 Claude 实测「麦克风 1 个、菜单三项」一致。
- **设置页 key**：两个 key 分别是 `chat-model:${username}` 和 `local-watch:${username}`，同级元素里没有别的 `key={username}`。与「duplicate key 报错消失」一致。
- **抽屉**：6 个抽屉 id 对应的 `className` 都加了 `drawer-panel`（共 6 处）。CSS 只写在 `@media (width < 48rem)` 加 `:root:not([data-shell=desktop])` 下面，而且不在任何 `@layer` 里，能盖过 `@layer components` 的 `.glaze-tint/.glaze-blur`；桌面不受影响。五处嵌入页的大标题见 §2.4。
- **北京时间**：用 T4 的 grep 正则扫了 T4 表格列出的 8 个文件，只剩 `AgentExchangeWorkspace.tsx` 222/387/461 行三处数字千分位的 `toLocaleString`，按规则保留。又用 Python 扫了 `app/ components/ lib/` 全部 ts/tsx（排除 T4 明确不改的 novels/studio），没有其他按设备时区显示的日期时间。明确不改的文件确实没动。与「New_York 设备上显示北京时间」一致。
- **历史页高亮**：AI 消息走 `<MessageText text={msg.content} highlight={query} />`，在 em、行内代码、代码块里都能渲染出 `<mark>`。与 Claude 实测一致。

### 05-fix-r1 验收

| 项 | 证据 | 结论 |
|---|---|---|
| tsc 0 / lint 0 errors 25 warnings | 同 §5-1、§5-2 | 通过 |
| 全量 pytest 0 失败，`test_ui_polish_fix_r1.py` 全过 | 全量 7715 passed；`test_ui_polish_fix_r1.py` 2 passed（浅克隆里 1 passed 1 skipped） | 通过 |
| 改动集合只多出 `test_ui_polish_fix_r1.py` | 当前改动集合 ⊆ 白名单 + 这个文件。没有首轮快照，**无法把 R1 和首轮的改动分开**；首轮 5 个测试文件在 R1 里是否只改了 ink3→ink2 那一处，也只能采信报告 | 通过（附说明） |
| F1 | `history/page.tsx`：AI 消息用 `highlight={query}`，用户消息仍是 `highlight(msg.content)`；`MessageText.tsx:8-19` 的 mark 类名和转义正则与历史页 `highlight` 逐字相同；`highlight` 为 `""` 或纯空白时输出与不传完全一样（测试和我的渲染都验证过）；`highlight="("`、`".*("` 不抛异常 | 通过 |
| F2 | `MessageText.tsx:26` 的 `-webkit-` 和标准写法两处都是 `--ink2`，构建出的 CSS 也是 ink2 | 通过 |
| F3 | `page.tsx` ChatModelFooter 的写法与返修单逐字一致；未启用时仍是「平台模型 · 每条 10 颗草莓」，`title` 不变 | 通过 |
| 03-report 末尾有 R1 一节 | 有 | 通过 |

### 2.3 新测试的证明力（变异实验，备份放在 `.review/`，做完已还原）

| # | 临时改坏的地方 | 跑的测试 | 结果 | 还原后 |
|---|---|---|---|---|
| M1 | `beijingTime.ts` 的 `formatBeijingTime` 把 `getUTCHours()` 换成 `getHours()`（偷用设备时区） | `test_ui_polish_beijing_time.py` | **2 failed**：运行时用例报 `formatBeijingTime depends on the device time zone`（纽约与上海结果不同），源码断言也失败 | sha256 一致 |
| M2 | `messageMarkdown.ts` 有序列表正则 `[.)]\s+` 改成 `[.)]\s*` | `test_ui_polish_markdown.py` | **1 failed**：`test_decimal_is_not_a_list`，`assert 'list' == 'para'`（「1.5 倍」被当成列表）。这是运行时断言，不是字面匹配 | sha256 一致 |
| M3 | `VoiceButton.tsx` 的 `const wasLongPress = longPressRef.current;` 改成 `… && false`（长按松开被当成短按） | `test_ui_polish_composer_controls.py` | **2 failed**：运行时状态机报 `{'tap': 1} != {'tap': 0}`、`{'end': 0} != {'end': 1}`，源码断言也失败 | sha256 一致 |
| M4 | `MessageText.tsx` 的 em 里不再做高亮 | `test_ui_polish_fix_r1.py` | **1 failed**：`expected exactly one mark` | sha256 一致 |

还原后 6 个新测试文件 `69 passed`，`git diff 5985f43 | shasum` 与开工时相同。注意：新测试**没有覆盖多块文本的打字状态**，所以必须修复项 R2-1 一直没被发现。

### 2.4 重点审查结论（没有问题的部分）

- **messageMarkdown.ts**：50 多个边界输入（空串、只有标记、未闭合围栏、深层缩进、1.5 倍、snake_case、`* 不是列表`、`*不是列表`、全角 `－＊＃＞１.`、全角空格缩进、tab、`\r`、`***x***`、`` `a``b` ``，以及 null / undefined / 数字 / 对象）都不抛异常，结果与 T1 规则一致。`* 不是列表` 按 T1 的无序列表正则确实算列表；不带空格的 `*不是列表` 是普通文字。一个 177KB 的混合 Markdown 解析只要 12ms。
- **MessageText.tsx**：只输出 React 文本节点，没有 innerHTML，不生成链接，没有粗体；光标位置符合 T2；高亮会转义元字符，空串时行为不变；没有 key 警告。
- **VoiceButton.tsx**：短按调一次 onTap；长按 onHoldStart / onHoldEnd 各一次；录音中短按只调 onTap；pointercancel / lostpointercapture 在短按时什么都不做、长按时只调一次 onHoldEnd；键盘触发时 `detail===0`，调一次 onTap；指针产生的 click（detail≥1）被忽略。和 `page.tsx:871-884` 原有的全局 mouseup / touchend 监听合起来看：长按松开时按钮的 pointerup 先结束录音，随后的全局 touchend 最多再做一次 `asrSessionRef+=1; setRecording(false)`，`recording` 已经是 false，状态只从 true 变 false 一次，`mr.onstop` 也不看 asrSessionRef，所以只结束一次、只发送一次；全局监听只在 `recording` 为真时挂着，不会误触发「轻点录音」。鼠标按下时 pointerdown 调了 preventDefault，兼容 mouseup 本来就不会发出来。这条双重路径和改动前一样，不算新问题。
- **ComposerImageMenu.tsx**：三项的禁用条件与 git diff 里删掉的旧按钮逐项对照一致：see 和旧的 ImagePlus 完全相同；generate 是旧条件加上 `imageMode \|\| hasReferenceImages`；edit 和旧的「上传参考图」完全相同；三处 title 文案也一致。`handleSelect` 在 click 事件里同步先 `setOpen(false)` 再 `onSelect()`，没有 setTimeout / rAF，文件选择框拿得到用户手势。方向键循环、Escape 关闭并把焦点还给触发按钮、Tab 关闭、点外部（pointerdown）关闭都已实现。
- **beijingTime.ts 与 T4 各处替换**：跨日边界、非法日期、`beijingDayStart` 遇到不可能的日期返回 Invalid Date，都由测试在两个时区下验证过。历史页「近7天」用 `(beijingDayNumber(now)-6)*86_400_000` 推算，「本月」用 `beijingParts` 拼出 `YYYY-MM-01`，自定义区间用北京日期键做字符串比较，分组标题、导出时间戳 `YYYY/MM/DD HH:mm:ss`、导出文件名都已改成北京时间，逐一核对无误。
- **settings / 五处 sr-only / novels**：novels 的任意变体在构建产物里生成了 `.\[\&_header_h1\]\:sr-only header h1{…}`。`components/novel/` 下 `/novels` 路由只有 `NovelShelf.tsx:59` 一个 `header h1`；`h1+*` 正好是「新建一本」，加了 `ml-auto` 后右对齐。

## 3. 必须修复项

### R2-1 打字状态的「去掉末尾未配对标记」按每个块各做一次，违反 T1-9

- **位置**：`frontend/lib/messageMarkdown.ts:175-181`（`parseInline` 里 `typing` 为真就调用 `findLastUnmatchedDelimiter`）；调用处在 234 行（每个列表项）、269 行（标题）、289 行（引用）、308 行（段落），都把 `typing` 传了进去。
- **问题**：T1-9 写的是「`typing === true` 时，**整段文本最后一个**未配对的 `**`（或单个反引号）不显示」。现在的实现每个段落、每个列表项都各去掉一个，前面已经输出完、本来就该原样显示的 `**` 或反引号会在流式输出期间消失，输出结束后又冒出来，内容显示错，而且会跳动。
- **复现**（node 加载 `lib/messageMarkdown.ts`，调用 `parseMessageMarkdown(x, { typing: true })`）：
  - `"2**3 是幂\n\n正在**强"` → 第一段显示成 `"23 是幂"`（应保留 `2**3`），第二段 `"正在强"`
  - `"- 2**10\n- 正在**强"` → 第一项显示成 `"210"`（应保留 `2**10`）
  - typing 为 false 时两例都正确保留。ChatBubble 在 `message.isTyping || stillTyping` 时传 `typing`，回复越长，打字机动画越久，错字显示的时间就越长。
- **为什么必须修**：明确违反规格条文，用户能看到错误内容（数字被改），现有测试覆盖不到（只测了单块）。修起来只需几行。

## 4. 可优化项

- **O1（建议本轮一并处理，但要 Claude 批准偏离规格里写死的正则）**：T1 给的标题正则 `HEADING_RE = /^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/`（`messageMarkdown.ts:17`）有立方级回溯。实测一行 `"# a" + N 个空格 + "x"`：N=1000 要 275ms，2000 要 1.8s，4000 要 11.8s。`isBlockStart` 也会对每行跑它；打字状态下每次刷新都会重新解析，遇到这种行页面会卡死。触发需要以 `#` 开头的行里有上千个连续空白，概率低，但不报错不等于一定能及时返回。建议改成线性写法：先用 `^\s{0,3}(#{1,6})\s+(.*)$` 匹配，再用 `trimEnd()`、去掉结尾的 `#`、再 `trimEnd()` 来处理结尾，不要用带两个相邻 `\s*` 的正则。
- **O2**：`ComposerImageMenu.tsx:23` 只是在「全部禁用」时把菜单藏起来，`open` 状态没有复位。如果菜单开着时三项一起变禁用（比如语音识别完自动发送，`isLoading` 变真），等回复结束重新可用时，菜单会自己弹出来，26-29 行的 effect 还会把焦点抢到第一项（用户可能正在输入）。建议 `triggerDisabled` 为真时 `setOpen(false)`。
- **O3**：`ComposerImageMenu.tsx:106` 只在禁用时给菜单项加 `title`。原来三个按钮在可用时也有提示，比如「选择 PNG、JPEG 或 WebP；每张不超过5MB，发送修改要求时才上传」，现在桌面鼠标悬停看不到格式和大小限制了。建议可用时也带 title，或把限制写进 description。
- **O4**：`page.tsx` 第 1 行的 UTF-8 BOM（`ef bb bf`）被删了，和本任务无关，也违反「只改任务涉及的行」。不影响功能和测试，建议恢复，让 diff 保持最小。报告里也没提这一处。
- **O5（未实测，需要 Claude 用浏览器看）**：手机图片 / 改图模式下，模型分组从原来独占一整行变成只占「models exit」那行的第一列，而且不换行。按 12px 字号粗算：模型分组约 237px；390 宽时第一列约 230px，只是略溢出到列间距里；320 宽时第一列约 160px，可能压到「返回聊天 / 全部取消」。建议在 320 和 360 宽各截一张图确认；如果真重叠，可以让模型分组 `min-w-0 overflow-x-auto`，或让它恢复独占一行。另外 exit 也从原来的「tools exit」位置挪到了 models 那一行。
- **O6（规格层面）**：VoiceButton 只认 `event.detail === 0` 的 click（规格要求）。有些读屏软件模拟的点击 detail≥1、却没有先发指针事件，这时按钮就完全没反应。可以改成用 ref 记「刚处理过 pointerup」，只吞掉紧接着的那一次 click。
- **O7**：菜单处理 Escape 时没有 `stopPropagation()`。宽度小于 1024 且历史面板开着时，按一次 Escape 会把菜单和历史面板一起关掉（`page.tsx:573` 的 document 监听）。
- **O8**：`stripMessageMarkdown` 会把文字里**所有** `**` 都删掉，包括没配对的（`"2**10"` 变成 `"210"`，`"a ** b"` 变成 `"a  b"`）。本轮还没接朗读，以后接入前建议只删成对的。
- **O9（规格正则自带的问题，供以后参考）**：`"# 学习 C#"` 解析成标题「学习 C」；`"1、2、3 是三个数"` 被当成从 1 开始的有序列表，内容是「2、3 是三个数」；`"****"` 被当成分隔线；中间夹着行内代码的 `` **a `b` c** `` 不会成为着重（两边的 `**` 原样显示）。
- **O10**：03-report 说原有的 `.readout b { font-weight:400 }` 本来就让那两个数字不粗，这个说法不对。那两处是 `<b className="readout">`，b 自己带 .readout 类，不是 .readout 的后代，原来确实是粗体。真正修好它的是改成 `<span className="readout font-normal">`，这个做法没问题。
- **O11**：在菜单里选了某项后，菜单卸载，焦点掉到 body 上。键盘用户关掉文件选择框后找不到原来的位置，建议把焦点还给「图片」按钮。
- **O12**：打字过程中，行首的 `-`、`#`、`1.` 在下一个字符到达前会以原样显示一帧（比如 `"-"` 先被当成段落）。这是逐字解析的固有现象，影响很小。

## 5. 给实现方的修改指令（只针对 R2-1）

只允许改 `frontend/lib/messageMarkdown.ts`，再新增 `backend/tests/test_ui_polish_fix_r2.py`（需要 Claude 把它加进白名单）。§2 的全部约束照旧：不改既有测试，也不改已有的 6 个 `test_ui_polish_*.py`；不改正则（O1 等 Claude 另行裁决）；不改导出签名；不加依赖。

1. `parseBlocks` 解析行内内容时一律按 `typing=false` 调 `parseInline`，同时记下**最后一个块**的原始行内文本：段落是 `paragraph.join("\n")`，标题是 `heading[2]`，引用是 `quoted.join("\n")`，列表只记最后一项的 `item.text`。`parseList` 要把最后一项的原文返回出来。
2. 循环结束后，如果 `typing === true` 且最后一个块是 `para` / `heading` / `quote`，就用 `parseInline(原文, true)` 重算它的 `inlines`；如果是 `list`，只重算最后一项的 `inlines`。如果最后一个块是 `code` 或 `rule`，什么都不做（未闭合的代码块正在输出时，前面已完成的段落里那个原样的 `**` 要保留）。这样整段文本最多去掉一个标记，而且只发生在正在输出的末尾，符合 T1-9 的本意。
3. `typing` 为 false 时，输出必须与现在逐字节相同。`findLastUnmatchedDelimiter`、`scanCode` 等函数本身不动。
4. 在新文件 `backend/tests/test_ui_polish_fix_r2.py` 里照抄 `test_ui_polish_markdown.py` 的 node 运行和跳过写法，断言以下 6 条：
   - `parseMessageMarkdown("2**3 是幂\n\n正在**强", {typing:true})`：第一段 inlines 为 `[{"kind":"text","text":"2**3 是幂"}]`，第二段为 `[{"kind":"text","text":"正在强"}]`；
   - `"- 2**10\n- 正在**强"`（typing）：第一项为 `"2**10"`，第二项为 `"正在强"`；
   - `` "正在**强\n\n```\ncode" ``（typing）：第一段保留 `"正在**强"`，代码块文本为 `"code"`；
   - `` "看 `代码\n\n下一段" ``（typing）：第一段保留原样的反引号；
   - 原有的单块用例 `"正在**强调"`、`` "看 `代码" ``、`"完成**重点**"` 在 typing 下结果不变；
   - `test_ui_polish_markdown.py` 里 `PARSE_CASES` 的全部输入在 `typing:false` 下的输出，与改动前一致（直接比对固定的期望 JSON，不依赖 git 历史）。
   - node 不可用时 skip，另写一条源码断言作为兜底（比如断言 `parseBlocks` 里只有一处用 `true` 调 `parseInline`）。
5. 复跑：`npx tsc --noEmit`（退出码 0）、`npm run lint`（0 errors / 25 warnings）、`npm run build`、全量 pytest（0 失败）、浅克隆跑全部新测试（0 失败），在 `03-report.md` 末尾追加「R2」一节，贴原始摘要行。
6. （可选，需 Claude 同意后再做）顺手处理 O4（恢复 `page.tsx` 首行 BOM）和 O2（`triggerDisabled` 时复位 `open`）。
