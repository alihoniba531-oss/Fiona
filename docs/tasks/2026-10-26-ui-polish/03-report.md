# 03 报告：前端 UI 打磨（2026-10-26）

基线提交 `5985f43`，分支 `feat/ui-polish`。任务按规格用 workflow 的 `parallel()` 拆成 6 个文件互不重叠的 agent 并行实现，主代理负责集成、白名单检查、全量验证与报告。

## 拆分与执行

| Agent | 负责内容 | 改动 / 新增文件 |
|---|---|---|
| A Markdown | T1、T2、T9 Markdown 测试 | 新增 `frontend/lib/messageMarkdown.ts`、`frontend/components/MessageText.tsx`、`backend/tests/test_ui_polish_markdown.py` |
| B Bubble/History | T3，以及 `ChatBubble.tsx`、`history/page.tsx` 内的 T4 | `frontend/components/ChatBubble.tsx`、`frontend/app/history/page.tsx` |
| C Beijing time | T4 工具与其余时间改造、T8 的 `AgentExchangeWorkspace` 标题、北京时间测试 | 新增 `frontend/lib/beijingTime.ts`、`backend/tests/test_ui_polish_beijing_time.py`；修改 `frontend/lib/chineseDate.ts`、`frontend/components/ConversationPicker.tsx`、`frontend/components/LocalWatchSection.tsx`、`frontend/app/plaza/page.tsx`、`frontend/components/AgentExchangeWorkspace.tsx` |
| D Composer controls | T5、T6 与输入控件测试 | 新增 `frontend/components/ComposerImageMenu.tsx`、`frontend/components/VoiceButton.tsx`、`backend/tests/test_ui_polish_composer_controls.py` |
| E Page composer | T7、`page.tsx` 内的 T4、页面契约测试 | 修改 `frontend/app/page.tsx`、`frontend/app/globals.css`、`frontend/lib/chatModel.ts`；新增 `backend/tests/test_ui_polish_page_contracts.py` |
| F Settings/Drawers | T8、设置/抽屉测试 | 修改 `frontend/app/settings/page.tsx`、`frontend/app/profile/page.tsx`、`frontend/app/novels/page.tsx`、`frontend/components/MyAgentWorkspace.tsx`；新增 `backend/tests/test_ui_polish_settings_drawers.py` |

主代理集成修补（均在各 agent 的负责文件内）：

- `frontend/app/page.tsx`：把两处 `readout` 数字由 `<b className="readout font-normal">` 改为 `<span className="readout font-normal">`。原因见第 5 节：T7.7 要求保留 `<b>`，但 §5.6 的验收 grep 明确禁止新增 `<b[ >]`；两者不可能同时满足。改为 `span` 后仍是 400 字重，且验收 grep 干净。同步调整了新测试 `test_page_readout_numbers_are_not_bold`，未改任何既有测试。
- `frontend/components/MessageText.tsx`：depth 1 空心圆不再同时保留实心 `bg` 类；按 depth 二选一，避免两个 Tailwind `bg-*` 工具类竞争导致空心圆失效。

## 1. 修改了哪些文件

修改（14 个，均在白名单内）：

- `frontend/components/ChatBubble.tsx`
- `frontend/app/history/page.tsx`
- `frontend/app/page.tsx`
- `frontend/app/globals.css`
- `frontend/lib/chatModel.ts`
- `frontend/lib/chineseDate.ts`
- `frontend/components/ConversationPicker.tsx`
- `frontend/components/LocalWatchSection.tsx`
- `frontend/app/plaza/page.tsx`
- `frontend/components/AgentExchangeWorkspace.tsx`
- `frontend/app/settings/page.tsx`
- `frontend/app/profile/page.tsx`
- `frontend/app/novels/page.tsx`
- `frontend/components/MyAgentWorkspace.tsx`

新增（11 个，均在白名单内）：

- `frontend/lib/messageMarkdown.ts`
- `frontend/components/MessageText.tsx`
- `frontend/lib/beijingTime.ts`
- `frontend/components/ComposerImageMenu.tsx`
- `frontend/components/VoiceButton.tsx`
- `backend/tests/test_ui_polish_markdown.py`
- `backend/tests/test_ui_polish_beijing_time.py`
- `backend/tests/test_ui_polish_composer_controls.py`
- `backend/tests/test_ui_polish_page_contracts.py`
- `backend/tests/test_ui_polish_settings_drawers.py`
- `docs/tasks/2026-10-26-ui-polish/03-report.md`

未改 `package.json` / `package-lock.json`，未改任何既有测试，未改 `backend/` 下除 5 个新测试外的文件。

## 2. 实现了哪些功能

- **Markdown 安全子集**：自写纯函数解析器，支持围栏代码、标题三档、分隔线、有序/无序及一层缩进列表、列表续行、引用、段落、行内代码、`**强调**`；打字时隐藏末尾未配对标记；`stripMessageMarkdown` 输出纯文本。渲染只用 React 文本节点，无 HTML、无链接、无粗体。
- **聊天气泡与历史页**：AI 消息接入 `MessageText`，用户消息继续纯文本；AI 打字光标由 `MessageText` 渲染；历史页 AI 正文接入 Markdown，用户搜索高亮保留。
- **北京时间**：新增 UTC+8 算术工具；聊天时间、会话列表、历史筛选/分组/导出、热点更新时间、本机监控、分身交流时间全部改为北京时间；聊天页头历史区域补「北京时间」小字。
- **统一图片入口**：输入区新增「图片」菜单（发图给 Chloe 看 / 生成图片 / 改一张图），删除原三个分散入口；保留两个隐藏文件输入及所有图片/改图模式逻辑。
- **合并语音按钮**：一个麦克风，短按开始/再按发送，长按说话/松开发送，键盘可触发，首次短按提示可长按；删除原两个麦克风。
- **输入区压缩**：手机非图片/无参考图时只有输入框一行 + 图片/语音/发送一行；模型说明与思考强度/切换按钮压成一行，标签省略号截断；图片/改图模式保留额外模式行。
- **抽屉**：六个抽屉追加 `drawer-panel`，手机下去除边缘 mask、隐藏透镜、改用 `--glass2` 底色；嵌入页面隐藏重复大标题（novels 通过页面作用域样式隐藏其下层组件里的 h1）。
- **模型展示名**：`claude-haiku-5-5` → `Claude Haiku 5.5`，DeepSeek 两个固定名称，其余原样；输入框下方显示展示名，完整系统 ID 放 `title`。
- **设置页与标题**：两个同级区块改为不同前缀 key；嵌入时隐藏设置、画像、分身、广场、书斋的页面大标题，非嵌入不变；书斋「新建一本」保持右对齐。

## 3. 与 T1–T9 的逐项对应

- **T1**：`messageMarkdown.ts` 导出签名、块解析、列表 depth/start/续行、引用、行内、typing、`stripMessageMarkdown` 均按规格实现；新增测试覆盖规格列出的全部情形。
- **T2**：`MessageText.tsx` 所有块与行内样式、三档标题、列表标记、光标位置、空输入光标、无 HTML/链接/粗体均按规格；depth 1 空心圆已修正类冲突。
- **T3**：`ChatBubble` AI 分支使用 `MessageText`，用户分支保留纯文本与 `typing-cursor`；历史页 AI 正文使用 `MessageText`，用户正文保留；两处时间改用北京时间；历史页补「北京时间」。
- **T4**：`beijingTime.ts` 8 个导出与非法日期行为完整；T4 表格所列文件和时间点全部替换；未改时间解析方式。`lib/novels.ts`、`lib/studio.ts`、`lib/studio-casting.ts`、`components/studio/**`、`app/studio/**` 未动。
- **T5**：`ComposerImageMenu` 触发器、菜单上方定位、宽度、材质、菜单项、禁用、焦点、方向键、Escape、Tab、外点关闭、同步 `onSelect` 均实现。
- **T6**：`VoiceButton` 单按钮、状态文案、指针状态机、键盘 click、上下文菜单、4 秒提示、localStorage 容错、卸载清理均实现。
- **T7**：图片菜单三项与隐藏输入、单一语音按钮、`ChatModelFooter` 展示名/单行布局、手机两行输入区、六抽屉 `drawer-panel`、北京时间、`readout` 数字去粗体均完成。T7.7 的具体标签处理见第 5 节。
- **T8**：设置页两个 key 带前缀且唯一；五个页面/组件嵌入时隐藏 h1，独立打开不变；书斋按钮位置处理；`LocalWatchSection` 字符串保留。
- **T9**：5 个新测试文件全部落地；Node/TypeScript 用例在缺依赖时 `pytest.skip`，另有源码断言，无 git/网络/仓库外依赖。

## 4. 测试结果

原始摘要：

```text
$ cd frontend && npx tsc --noEmit
（无输出，exit 0）

$ cd frontend && npm run lint
✖ 25 problems (0 errors, 25 warnings)

$ cd frontend && npm run build
✓ Compiled successfully in 296ms
✓ Generating static pages using 17 workers (18/18) in 176ms
（exit 0）

$ cd backend && <Fiona 主检出>/backend/.venv/bin/python -m pytest -q
7713 passed, 35 warnings in 288.85s (0:04:48)

$ 仅 5 个新测试
67 passed in 3.49s

$ 无 Node 环境模拟浅克隆
42 passed, 25 skipped in 0.34s
```

其他检查：

- `git diff -U0 -- frontend | grep ...` 粗体/`<b`/`<strong` 验收 grep：无输出。
- `grep -rn 'dangerouslySetInnerHTML' frontend/components/MessageText.tsx frontend/lib/messageMarkdown.ts`：无输出。
- 白名单：tracked 修改 14 个 + 新文件 11 个（含本报告）；`package.json` / `package-lock.json` 零改动；`backend/` 只有 5 个新测试。`docs/tasks/.../01-audit.md`、`02-spec.md` 是任务开始时已在工作树中的 untracked 输入文件，不是本次改动。

## 5. 未完成或需要人工确认的地方

1. **T7.7 与 §5.6 冲突，已按可验证验收选择**：T7.7 要求给两处 `<b className="readout">` 追加 `font-normal`，但 §5.6 的 grep 明确禁止新增行出现 `<b[ >]`；两者无法同时满足。实测既有 `.readout b { font-weight:400 }` 本来就让这两个数字不粗。最终改成 `<span className="readout font-normal">`，保留 400 字重并让 §5.6 为零输出。若必须保留字面 `<b>`，则该验收 grep 必然有输出。
2. **书斋 h1 的隐藏方式**：`书斋` 的 h1 实际在 `frontend/components/novel/NovelShelf.tsx`，不在白名单。为避免改白名单外文件，`app/novels/page.tsx` 在 `embed=1` 时用页面作用域的 `[&_header_h1]:sr-only` 隐藏下层 `header h1`，并给同行的「新建一本」加 `ml-auto`。视觉与读屏语义满足 T8，但不是把 `sr-only` 字面写进那个 h1 的 className。新增测试按此实现断言。
3. **未做浏览器截图**：本会话的 headless Chrome 被文件沙箱拦截，无法在 390×844 下实际测量输入区高度或抽屉边缘。已完成 CSS/构建/结构检查；手机两行网格、40px 点击区、抽屉 mask 规则均由源码和构建产物确认，最终视觉验收需在沙箱外补截图。
4. **全量 pytest 的运行环境**：本机 harness 导出了含 `[::1]` 的 `NO_PROXY`，httpx 在收集 `test_byok_client.py` 等文件时抛 `InvalidURL: Invalid port: ':1]'`。这不是代码失败；已用 `env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u NO_PROXY -u http_proxy -u https_proxy -u all_proxy -u no_proxy -u NODE_USE_ENV_PROXY` 清空代理变量后重跑全量。交付环境若同样带该变量，需同样处理。
5. **任务输入文件**：`docs/tasks/2026-10-26-ui-polish/01-audit.md` 和 `02-spec.md` 在开始时已存在且未跟踪，本报告未修改它们。

## R1 返修

本轮按 R1 要求直接完成，未拆子代理。

- **F1 历史页搜索高亮**：`MessageText` 新增可选 `highlight?: string`，对 text、em、行内 code 和围栏代码块按不区分大小写子串高亮，查询词用历史页同样的正则转义，mark 类名与历史页完全一致；空串/纯空白走原文本输出。`history/page.tsx` 的 AI 消息改为 `<MessageText text={msg.content} highlight={query} />`，用户消息保留原 `highlight(msg.content)`。新增 `backend/tests/test_ui_polish_fix_r1.py`，覆盖 em 内高亮、`(` 不抛异常、空 highlight 与不传逐字节一致、行内/围栏代码高亮，以及 history 源码断言。
- **F2 着重号提亮**：`MessageText.tsx` 中 em 的 `-webkit-text-emphasis` 与 `text-emphasis` 两处均由 `var(--ink3)` 改为 `var(--ink2)`，其他不动。
- **F3 手机模型说明**：`ChatModelFooter` 启用自带模型时改为两段，桌面显示「Claude Haiku 5.5 · 不扣草莓」，手机通过 `max-md:hidden` 只留模型名；`title={labelTitle}` 不变。未启用时仍显示「平台模型 · 每条 10 颗草莓」。保留 `label` 变量供未启用分支和既有页面契约测试使用，未修改 `test_ui_polish_page_contracts.py`。

测试原始摘要：

```text
$ cd frontend && npx tsc --noEmit
（无输出，exit 0）

$ cd frontend && npm run lint
✖ 25 problems (0 errors, 25 warnings)

$ cd frontend && npm run build
✓ Compiled successfully in 523ms
✓ Generating static pages using 17 workers (18/18) in 182ms
（exit 0）

$ cd backend && python -m pytest -q tests/test_ui_polish_fix_r1.py
2 passed in 0.45s

$ 无 Node 环境
1 passed, 1 skipped in 0.22s

$ cd backend && python -m pytest -q
1 failed, 7714 passed, 35 warnings in 285.35s (0:04:45)
```

**待 Claude 裁决**：全量唯一失败是上一轮的 `test_ui_polish_markdown.py::test_message_text_source_is_safe_and_uses_parser`，它断言源码仍含 `text-emphasis:filled_dot_var(--ink3)`。这与本轮 F2「两处都改为 ink2」直接冲突；按 R1「不改已有的 5 个新测试文件」未修改该测试。`test_ui_polish_fix_r1.py` 2 项全部通过，页面契约测试也未因 F3 变红。建议允许把该断言中的 `ink3` 改为 `ink2`，或另行指定处理方式。

裁决后已仅修改该断言中的 `ink3` 为 `ink2`，并复跑：

```text
$ cd backend && python -m pytest -q tests/test_ui_polish_markdown.py
21 passed in 0.41s

$ cd backend && python -m pytest -q tests/test_ui_polish_fix_r1.py
2 passed in 0.43s

$ cd backend && python -m pytest -q
7715 passed, 35 warnings in 287.01s (0:04:47)
```

## R2 返修

### 拆分

| Agent | 负责内容 | 改动 / 新增文件 |
|---|---|---|
| A | R2-1、R2-2、R2-6 | `frontend/lib/messageMarkdown.ts`、新增 `backend/tests/test_ui_polish_fix_r2.py` |
| B | R2-4、R2-5 | `frontend/components/ComposerImageMenu.tsx`、`frontend/components/VoiceButton.tsx`、新增 `backend/tests/test_ui_polish_fix_r2_controls.py`；仅改 `test_ui_polish_composer_controls.py` 的冲突断言 |
| C | R2-3、R2-7 | `frontend/app/globals.css`、`frontend/app/page.tsx`（只补 BOM）；仅改 `test_ui_polish_page_contracts.py` 的冲突断言 |

### 各项改动

- **R2-1**：`parseBlocks` 的所有行内解析先按 `typing=false` 执行，并记录最后一个块的原始行内文本（列表取最后一项）；循环结束后只对最后一块 / 最后一项用 `parseInline(..., true)` 重算。前面的段落不再被去掉 `**` / 反引号，`typing=false` 的解析结果不变。测试覆盖 04-review 要求的 6 组场景，并保留固定 `typing:false` 快照。
- **R2-2**：标题正则改为 `/^\s{0,3}(#{1,6})[ \t]+(.*)$/`，新增 `headingContent` 用 `trimEnd` 和末尾 `#` 扫描处理，`C#` / `标题#` 保留，`## 标题 ##` / `# ###` 正确去除；`#标题` 仍是段落。5000 空格标题行测试在 200ms 内，源码断言检查正则线性写法。
- **R2-3**：手机图片 / 改图模式网格改为 `"text text" "tools tools" "models models" "exit actions"`；模型分组独占整行并允许 `flex-wrap`，chip 设 `flex-shrink:0`；最后一行 exit 靠左、actions 靠右，并补 `margin-left:0` 抵消页面上的 `ml-auto`。普通两行布局不变。
- **R2-4**：`ComposerImageMenu` 在 `triggerDisabled` 变真时通过依赖该值的 effect 复位 `open`；Escape 增加 `stopPropagation`；选中后按 `setOpen(false)` → `onSelect()` → `triggerRef.focus()` 同步执行；菜单项始终带 `title={item.title}`。
- **R2-5**：`VoiceButton` 用 `pointerUpHandledRef` 记录刚由 pointerup 处理的指针操作，随后那次 click 被吞掉；无指针事件的 click（detail≥1、键盘、读屏软件）调用 `handleTap`。额外处理 Chrome 的 `pointerup → lostpointercapture → click` 顺序，避免复位后同一次指针操作再次触发；pointercancel / lostpointercapture 仍复位标记。
- **R2-6**：`inlinesToPlainText` 的 text 片段改为原样输出，未配对的 `**` 不再被删除。为了同时满足 R2-6 明确要求的 `stripMessageMarkdown("2**10 和 **重点**") === "2**10 和 重点"`，`stripMessageMarkdown` 仅在 strip 路径把「数字夹住的 `**`」临时保护起来、解析后还原；`parseMessageMarkdown` 的公开解析结果不变。这是 R2-6 指定结果与现有 `splitEmphasis` 左到右配对之间的必要衔接，未改动解析器的公开行为。
- **R2-7**：用 Python 字节操作恢复 `frontend/app/page.tsx` 的 `EF BB BF` BOM；`head -c 3` 为 `efbbbf`，`git diff 5985f43 -- frontend/app/page.tsx | head -8` 从第 14 行开始，不再有首行改动。

### 本任务新增测试的断言改动

- `backend/tests/test_ui_polish_composer_controls.py`：
  - `title={item.disabled ? item.title : undefined}` → `title={item.title}`（R2-4-4）。
  - 两条 `event.detail === 0` 源码断言 → pointerup ref 相关断言（R2-5 修订）。
  - 直接 click 测试的 `keyboard` 期望由 tap 1 改为 tap 2（detail=0 与 detail=1 两次无指针 click 都应触发 onTap）。
  - 其余断言、夹具和 pointer harness 保持原样；R2 代理曾扩写 `handleSelect` / timeout / try-count 断言，主代理已还原为非冲突原断言。
- `backend/tests/test_ui_polish_page_contracts.py`：
  - `"text text" "tools actions" "models exit"` → `"text text" "tools tools" "models models" "exit actions"`（R2-3 新网格）。
  - `.composer-mode-exit` 的 `justify-self:end` → `justify-self:start`（R2-3 最后一行靠左）。
- `backend/tests/test_ui_polish_fix_r2.py`（本轮新增）：R2-6 的 `combined` 期望按本单修正为 `"2**10 和 重点"`；其余为新增 R2 覆盖。
- `test_ui_polish_markdown.py`、`test_ui_polish_beijing_time.py`、`test_ui_polish_settings_drawers.py`、`test_ui_polish_fix_r1.py` 未改动。基线测试一字未改。

### 验收结果

```text
$ cd frontend && npx tsc --noEmit
TSC_EXIT:0

$ cd frontend && npm run lint
✖ 25 problems (0 errors, 25 warnings)

$ cd frontend && npm run build
✓ Compiled successfully in 328ms
✓ Generating static pages using 17 workers (18/18) in 167ms
（exit 0）

$ cd backend && python -m pytest -q tests/test_ui_polish_fix_r2.py
18 passed in 0.39s

$ cd backend && python -m pytest -q tests/test_ui_polish_fix_r2_controls.py
7 passed in 0.70s

$ cd backend && python -m pytest -q
7740 passed, 35 warnings in 281.00s (0:04:41)

$ 无 Node 环境，仅两个 R2 新测试
8 passed, 17 skipped in 0.27s
```

其他：`git diff --check` 通过；新增前端代码粗体验收 grep 无输出；`dangerouslySetInnerHTML` grep 无输出；`page.tsx` BOM 为 `efbbbf`；改动集合落在 R2 / 前几轮白名单内；`package.json` / `package-lock.json` 零改动；`backend/` 已跟踪文件 diff 为 0。任务输入 `01-audit.md`、`02-spec.md`、`04-review.md`、`05-fix-r1.md`、`05-fix-r2.md` 均未修改。

## R3 返修

R3 由主代理直接完成，未拆子代理。

### O1 去掉 strip 的数字占位处理

- 删除 `LITERAL_DOUBLE_STAR` 常量、数字夹 `**` 的 `replace`、末尾还原以及相关注释。
- `stripMessageMarkdown` 现在直接对 `parseMessageMarkdown(text)` 的 blocks 拼纯文本；各块拼法、列表编号、块间两个空行不变。未配对的 `**` 原样保留，成对 `**` 已是着重。
- 结果与渲染纯文字一致：`2**10**3` → `2103`；含私用区字符的原文原样返回。
- 新测试 `backend/tests/test_ui_polish_fix_r3.py` 通过 `String.fromCharCode(0xE000)` / `chr(0xE000)` 构造该字符，源码中没有直接字符，也没有反斜杠 u 转义。源码断言确认 `messageMarkdown.ts` 不含 `LITERAL_DOUBLE_STAR`，且文件字节不含该字符的 UTF-8 编码。

### O2 长按后无 click 时下一次点击不被吞

- `VoiceButton` 新增 `CLICK_AFTER_POINTERUP_MS = 500` 与 `pointerUpAtRef`（初值 `Number.NEGATIVE_INFINITY`）。
- `handlePointerUp` 置 `pointerUpHandledRef` 时同时记录 `performance.now()`。
- `handleClick` 保持无参数；遇到 `pointerUpHandledRef` 或 `captureLostAfterPointerUpRef` 任一标记时把两者都复位，只有距 pointerup 不超过 500ms 才吞掉该次 click，超时或没有标记时照常 `handleTap()`。
- 新测试覆盖：长按 → pointerup → lost → 等 650ms → detail 0/1 click 各 tap 1；短按后立即 click 被吞；长按后立即 click 仍被吞；短按后超时 click 产生第二次 tap。

### 本任务测试断言改动

- `backend/tests/test_ui_polish_fix_r2.py` 的 `STRIP_CASES["combined"]`：
  - 输入 `"2**10 和 **重点**"` → `"2**10 和 \`x\`"`。
  - 期望 `"2**10 和 重点"` → `"2**10 和 x"`。
  - 原因：O1 删除数字占位后，按 T1 从左到右配对，旧输入无法得到旧期望；改用不与配对规则冲突的用例。
- 未改其他任何本任务新增测试的断言；`test_ui_polish_fix_r2_controls.py`、`test_ui_polish_composer_controls.py` 一字未动并全部通过。基线测试未改。

### 验收结果

```text
$ cd frontend && npx tsc --noEmit
TSC_EXIT:0

$ cd frontend && npm run lint
✖ 25 problems (0 errors, 25 warnings)

$ cd frontend && npm run build
✓ Compiled successfully in 525ms
✓ Generating static pages using 17 workers (18/18) in 181ms
（exit 0）

$ cd backend && python -m pytest -q tests/test_ui_polish_fix_r3.py
4 passed in 2.73s

$ cd backend && python -m pytest -q tests/test_ui_polish_fix_r2_controls.py tests/test_ui_polish_composer_controls.py
15 passed in 2.59s

$ cd backend && python -m pytest -q
7744 passed, 35 warnings in 302.93s (0:05:02)

$ 无 Node 环境，仅 R3 新测试
2 passed, 2 skipped in 0.25s
```

其他：`git diff --check` 通过；前端新增代码粗体验收 grep 无输出；`page.tsx` BOM 仍为 `efbbbf`；本轮只新增 `test_ui_polish_fix_r3.py` 一个新文件；`package.json` / `package-lock.json` 零改动；`backend/` 已跟踪文件 diff 为 0。任务输入文档未修改。
