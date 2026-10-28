# 02 规格：手机对话页修缮（UI 复核第一批）

- 规格版本：v2.1（2026-10-28；v1 经四视角对抗复核后修订为 v2，独立复核后修订为 v2.1，改动见文末「修订记录」）
- 基线：`main` @ `58be576`；工作分支 `fix/mobile-chat-fix`（本工作树）
- 来源：`docs/tasks/2026-10-28-ui-review/01-audit.md` 的 P1-1、P1-2、P1-4、P2-12、P3-16 五条。
- 级别：L2（修 bug + 版式，不改数据模型、不改接口）。全程不设中途确认。
- 执行者：dsh（DeepSeek Flash，max）；Claude 做门禁与视觉验收；独立复核另派。

---

## 1. 产品目标

手机（390×844）上的对话页有五处看得见的毛病，用户每天都会碰到：

1. 点输入框或打开图片菜单后，整个对话外壳被向上顶 40px，页头（朱印、名字、朗读 / 免提）只剩半截。
2. 「回到最新」浮标浮在屏幕正中，压住正文与生成图。
3. 打开「对话列表」弹层后，弹层下沿附近的页面文字被透镜折成乱码。
4. 输入区空闲时 151px 高（从未配置自带模型的账号），比 10-26 定的 ≤140px 目标高。
5. 六个抽屉与对话列表弹层在手机上贴底栏的那条边，有一道釉口阴影，看起来像没盖严。

修完以后：页头永远钉在顶上；浮标贴着输入釉片上沿、清晰不透明；弹层像一整片瓷；输入区空闲 ≤140px（状态 A，见 §2.4）且所有控件照旧可见；抽屉与弹层底边与底栏连成一片。桌面布局一个像素都不变。

## 2. 现状事实（全部从 HEAD `58be576` 实测与核对；行号以 HEAD 为准）

### 2.1 外壳被滚动（P1-1）

- `frontend/app/page.tsx:2387`：`<div className="chat-shell relative flex flex-col h-dvh overflow-hidden">`。
- 实测 390×844：点输入框后 `document.scrollingElement.scrollTop === 0`，`document.documentElement.scrollHeight === 844`，但 `document.querySelector('.chat-shell').scrollTop === 40`，`.chat-header` 的 `getBoundingClientRect().top === -40`。被滚动的是这个 `overflow:hidden` 的外壳，不是文档。
- 40 这个数来自 `frontend/app/globals.css:533`：手机上 `.chat-composer > .glaze-lens` 的 `bottom: calc(-40px - var(--tabbar-h) - env(safe-area-inset-bottom))` 向下探出外壳，给了外壳 40px 可滚余量；浏览器把焦点元素滚进可视区时就用掉了它。
- `focusChatInput`（`page.tsx:641`）与 `composeSongSection`（`:647`）只调用 `textarea.focus()`。
- `frontend/app/layout.tsx:29,97`：`<html className="h-full">`、`<body className="h-full antialiased">`，文档本身不可滚动。
- 桌面 1440×900：`.chat-header` 是 `absolute … top-3`（`page.tsx:2483`），HEAD 的 `top` 为 12px；`.chat-shell.scrollTop` 为 0。
- Tailwind 4.3.0 已装，`overflow-clip` 工具类可用（生成 `overflow: clip`）。
- 既有测试 `backend/tests/test_novel_p2_frontend.py:132` 断言的 `"h-dvh overflow-hidden"` 针对 `components/novel/NovelWorkbench.tsx`，不是 `page.tsx`，与本单无冲突。

### 2.2 「回到最新」浮标（P1-2）

- `frontend/components/ChatScrollArea.tsx:138–141`：`{showLatest && <button … className="chat-latest absolute bottom-[calc(var(--chat-content-bottom)+96px)] left-1/2 … border-border bg-background/95 … text-muted-foreground shadow-sm … focus-visible:outline-primary"><ArrowDown size={12} />回到最新</button>}`，渲染在 `[data-chat-scroll-area]` 容器内，而该容器位于 `.chat-message-layer`（`page.tsx:2542`）之内。
- `.chat-message-layer` 带 `mask-image`（`globals.css:510–516`，手机 `:523–528`）：靠近输入釉片的一段被渐隐。浮标在这一层里，放得越靠近输入釉片越透明——这是它被推到屏幕中间的原因。
- `--chat-content-bottom`：桌面 `calc(var(--composer-height) + 72px)`；手机 `calc(var(--composer-height) + var(--tabbar-h) + env(safe-area-inset-bottom) + 50px)`。再加 96px，手机上浮标下沿离底约 357px。
- `--composer-height` 是内联变量，只写在 `.chat-message-layer` 上（`page.tsx:2543`），值来自 `page.tsx:702` 对 `composerRef`（`:2587` 的 `<Glaze as="footer">`）的 `getBoundingClientRect().height`（向上取整）。
- 输入釉片位置：桌面 `bottom-[18px]`（`page.tsx:2587`）；手机 `max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]`。
- `page.tsx` 结构（各锚点在文件中恰好出现 1 次）：`:2481` `<div className="relative z-[1] flex-1 min-w-0" data-chat-panel>` → `:2542` `<div className="chat-message-layer absolute inset-0 …">` → `:2544` `<ChatScrollArea ref={chatScrollRef} resetKey={…}>` → `:2585` `</ChatScrollArea>` → `:2586` `</div>`（遮罩层闭合）→ `:2587` `<Glaze as="footer" …>`。
- `ChatScrollArea` 对外接口：`forwardRef<ChatScrollHandle>`，句柄只有 `scrollToLatest()`（`:9–11`、`:62`）；props 只有 `children`、`resetKey`（`:13–16`）；第 20 行签名 `export default forwardRef<ChatScrollHandle, Props>(function ChatScrollArea({ children, resetKey }, ref) {`；显示条件 `showLatest = !following && distance > 2`（`:30–35`）；`:21–113`（从 `  const viewportRef = useRef<HTMLDivElement>(null);` 到 `onScroll` 的闭合 `  };`，共 93 行）是跟随 / 意图判定逻辑；`:114` 空行，`:115` `  return (`。
- `page.tsx` 顶部 `lucide-react` 引入在 `:24` 结束的那个 `import { … } from "lucide-react";` 里，尚未引入 `ArrowDown`；`useState` 已引入。
- HEAD 计数：`回到最新` 与 `chat-latest` 在 `page.tsx` 各 0 次、在 `ChatScrollArea.tsx` 各 1 次；`backend/tests` 全目录没有引用 `ChatScrollArea`、`chat-latest` 或「回到最新」的测试。

### 2.3 对话目录弹层（P1-4）

- `frontend/app/page.tsx:2474`：遮罩 `fixed … z-[61] bg-[var(--scrim)] lg:hidden max-md:left-0 max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]`。
- `page.tsx:2476`：弹层 `chat-conversation-modal fixed … z-[62] w-[min(85vw,320px)] glaze-slide-in outline-none lg:hidden max-md:left-0 max-md:top-0 max-md:bottom-[…] max-md:rounded-none max-md:pt-[env(safe-area-inset-top)]`，内容是 `<ConversationPicker>`（默认 `glazed`，即 `<Glaze variant="panel" className="h-full">`，`components/ConversationPicker.tsx:109`；`Glaze` 渲染的根元素带 `glaze` 类，`.glaze-lens/.glaze-blur/.glaze-tint/.glaze-finish` 是它的直接子元素）。所以 `.chat-conversation-modal > .glaze > .glaze-*` 这个结构成立。
- `globals.css:530`（手机媒体块内）：`.chat-conversation-modal > .glaze { border-radius:0; }`——只去了圆角，边缘遮罩（`.glaze-blur`、`.glaze-tint` 的 `mask-image`）和透镜层（`.glaze-lens`）都还在。
- 10-26 给六个抽屉做的修法在 `globals.css:565–571`（所在媒体块 `:564–572`，块头注释 `:563`）：`:root:not([data-shell=desktop]) .drawer-panel > .glaze-blur / .glaze-tint { -webkit-mask-image:none; mask-image:none; }`、`.drawer-panel > .glaze-lens { display:none; }`、`.drawer-panel > .glaze-tint { background:var(--glass2); }`。弹层没有套这套规则。
- 实测现象：弹层下沿附近（输入釉片页脚文字所在位置）被透镜折成乱字；右侧 15vw 透过遮罩能看到「发送」按钮一角（遮罩是设计内的，不算问题）。
- 既有测试 `backend/tests/test_ui_polish_page_contracts.py:119–134` 的定位方式：`first = css.index(".drawer-panel")`（全文件第一次出现，HEAD 在 `:565`）→ `media_start = css.rindex("@media (width < 48rem)", 0, first)`（HEAD 为 `:564`）→ `balanced_block(...)` 取整块，再断言块内含既有四条规则且不含 `:root[data-shell=desktop] .drawer-panel`。**`:564` 之前若新增任何含 `.drawer-panel` 字样的文本（含注释），或在它前面另起一个 `@media (width < 48rem)` 块，这条测试就会定位到 `:559` 的 composer-mode-exit 块而全红。**

### 2.4 手机输入区高度（P2-12）

- `ChatModelFooter`（`page.tsx:300–448`）在手机上有三种状态，页脚行高不同：
  - **A）`GET /chat-model` 的 `config` 为 null**（该账号从未保存过自带模型配置，`backend/byok/store.py:61–63`；`settings` 尚未返回也落在此分支）→ `page.tsx:437` 渲染一行 16px 的 `<span>每条消息消耗 <span className="readout font-normal">10</span> 颗草莓</span>`，页脚行 8+1+8+16 = 33px。**复核报告的 151px 是在这一状态下量的。**
  - **B）`config` 非 null 且 `enabled === false`** → `:408` 分支：模型标签 + 「改用我的模型」按钮（`:432–434`，`h-7 … max-md:min-h-10`，加 `globals.css:376` 的手机 `button { min-height:40px }`，实际 40px）。页脚行 57px，空闲输入区约 175px。
  - **C）`enabled === true` 且 provider 为 anthropic** → 标签 + 「思考」三枚 40px radio（`:420–428`）+ 「改用平台」按钮。页脚行同样 57px。
  - 请求失败走 `:438–441` 的错误分支，也含 40px「重试」按钮。
  - 保存任一聊天模型配置后 `status` 即为 `ok`（`store.py:173`），不需要真实连接测试。
- 390×844 状态 A 空闲（文本框空、非生图模式）实测 `--composer-height = 151px`。拆解（全部在 `page.tsx:2587–2727`）：
  - `<Glaze as="footer">`（`:2587`）：上距用不带前缀的 `pt-3`（桌面手机共用，12px），下距用 `max-md:pb-2`（8px）→ 手机上下合计 20px。**这一行没有裸 `pb-2`，桌面下距是 `pb-3`；全文件只有这一处 `max-md:pb-2`。**
  - `.composer-inner`（`:2630`）：`max-md:px-3 max-md:py-2` → 上下 16px；
  - 文本行：`textarea rows=1 py-1 leading-relaxed text-base` → 34px；
  - 网格间距 `gap-2` → 8px；
  - 工具 / 动作行：按钮 `max-md:h-10` → 40px；
  - 页脚行（`:2723`）：`mt-2 border-t pt-2 text-xs` → A 态 33px；B/C 态 57px。
- 桌面同一块用的是不带前缀的类：`px-[18px] pb-3 pt-3`、`rounded-[14px]`。
- `globals.css:376` 的手机 `button { min-height:40px; min-width:40px }` 是 09-23 手机规格「可点目标 ≥40×40」的来源，不得动。
- 既有测试 `test_ui_polish_page_contracts.py:165` 保护字面量 `"平台模型 · 每条 10 颗草莓"`；`page.tsx:437` 的 JSX 文本没有既有测试保护（本单 T6 补）。

### 2.5 抽屉与弹层底边（P3-16）

- 实测 390×844 打开任一抽屉：抽屉 `getBoundingClientRect().bottom === 784 === 底栏 top`，没有空隙；那道「缝」是 `.glaze-finish` 的底部积釉渐变（`globals.css:325` `background-image` 的第二层 `linear-gradient(to bottom, transparent 72%, var(--pool) 135%)`）、`box-shadow` 里的 `inset 0 -1px 0 var(--lipdk)` 和 `inset 0 0 24px -8px var(--pool)` 在边到边的抽屉上成了一条横线。第一层 `radial-gradient(ellipse 90% 24% at 24% 0%, var(--sheen), transparent 70%)` 是顶部酥油光，不是缝的成因，要保留。
- 底栏 `.mobile-tabbar`（`components/Sidebar.tsx:141`，对话页 `shared` 为真，`fixed … z-[70]`）自带 `border-t border-[var(--carve)]`，并有 `globals.css:545` `.chat-shell .mobile-tabbar { box-shadow:inset 0 1px 0 var(--etch); }`。这两条 1px 线落在 y=784（底栏第一行），属于底栏自己的上沿，本单不动、不计入「缝」。本单只去掉抽屉与弹层最后几行（y≤783）里 `.glaze-finish` 造成的积釉渐变与 `lipdk` 线。
- 桌面抽屉离屏边 12px 悬浮，这条釉口是对的，不能动。

### 2.6 门禁基线（HEAD 实测）

- `cd frontend && npx tsc --noEmit` → 退出码 0。
- `cd frontend && npm run lint` → 0 errors，25 warnings。
- `cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py -p no:cacheprovider` → 492 passed。
- 全量后端测试（上一单在 Pillow 13 环境）：7744 passed、0 skipped；本单由 Claude 在沙箱外复跑。
- 文案与锚点计数（HEAD）：见 §6 第 5 条括号里的基线值。

## 3. 技术约束

### 3.1 白名单（只许改这些；新增只许新增这些）

- `frontend/app/page.tsx`
- `frontend/components/ChatScrollArea.tsx`
- `frontend/app/globals.css`
- 新增 `backend/tests/test_mobile_chat_fix.py`
- 新增 `docs/tasks/2026-10-28-mobile-chat-fix/03-report.md`

其余一律不动：不改 `package.json` / lockfile、不改 `next.config.ts`、不改既有测试的任何输入、断言与夹具、不改后端、不改其他组件、不删文件、不提交 git commit。完成标准与验收命令的覆盖范围与本白名单一致（本规格文件本身已在工作树里，`git status` 会显示它，属预期）。

### 3.2 必须原样保留

- 10-06 规格 §4.2 的全部保留项：`data-chat-panel`、`data-chat-composer`、`data-chat-scroll-area/-viewport/-content`、`#conversation-picker-dialog` 及其 `role="dialog" aria-modal`、`composerRef` / `textareaRef` 与两个 composition 事件、`primeTtsAudio` 的用户手势链、所有 `aria-label`。
- `ChatScrollArea.tsx:21–113`（从 `  const viewportRef = useRef<HTMLDivElement>(null);` 起，到 `onScroll` 的闭合 `  };` 止，共 93 行）逐字节不改、不插行、不删行。`:13–16` 的 `Props` 只允许追加两个可选字段；`:20` 签名只允许在解构里追加 `renderLatestButton = true, onLatestVisibilityChange`，其余字符不变；新增的上报 effect 只能插在 `:113` 之后、`:115` `  return (` 之前（代码见 T2-1）；按钮分支（`:138`）只允许把 `{showLatest && <button` 改为 `{renderLatestButton && showLatest && <button`。
- `page.tsx` 中 `drawer-panel` 出现次数仍为 6；六个抽屉的 `id`、顺序、`inert` / `aria-hidden` 契约不动。
- `globals.css:565–571` 既有的 `.drawer-panel` 规则逐字保留（含 `:563` 的块头注释，不改字）；新规则只能插在 `:571` 之后、`:572` 的 `}` 之前；`:564` 之前的任何位置不得新增或改出含 `.drawer-panel` 字样的文本（包括注释），不得在它前面另起 `@media (width < 48rem)` 块（原因见 §2.3 末条）。不得出现 `:root[data-shell=desktop] .drawer-panel` 或 `:root[data-shell=desktop] .chat-conversation-modal`。
- `globals.css:376` 的手机 `button { min-height:40px }`、`ChatModelFooter` 两组按钮的 `max-md:min-h-10` 不得改；`ChatModelFooter` 的 DOM 结构与文案不得改。
- 桌面（≥768px，或 `html[data-shell=desktop]`）的任何可见样式不变：本单对输入区、抽屉、弹层的所有间距 / 材质改动只能写在 `max-md:` 变体或 `@media (width < 48rem)` + `:root:not([data-shell=desktop])` 块里。
- 文案一字不改。具体指：`page.tsx:437` 的 `<span>每条消息消耗 <span className="readout font-normal">10</span> 颗草莓</span>`（注意这句在源码里被 span 切开，不是连续字面「每条消息消耗 10 颗草莓」，内层 span 的结构与 className 也不动）；`page.tsx:403`、`:406` 的 `"平台模型 · 每条 10 颗草莓"`；`:2534` 的 title `平台模型每条消息消耗 10 颗；自带模型聊天不扣`；`:2724` 的 `Enter 发送，Shift + Enter 换行`；`ChatScrollArea.tsx:140` 的 `回到最新`（T2 搬到 `page.tsx` 的新浮标用同样四个字）。
- 界面文字不加粗（不新增 `font-semibold` / `font-bold` / `font-weight ≥ 600`；`page.tsx` 基线已有 3 处 `font-semibold`，总数不得增加）。
- 新写的界面文案不得用中点「·」分隔（既有的保留）。

### 3.3 环境

- 沙箱 workspace-write，有网。`npm` 写不了 `~/.npm`：跑 npm 前 `export npm_config_cache=/tmp/fiona-npm-cache`。`frontend/node_modules` 与 `backend/.venv` 已经就位，不要重装。
- 沙箱里没有浏览器，§6 第 8 条的视觉判据由 Claude 在沙箱外用真实浏览器量；你负责把代码按 §4 写对、把 §6 第 1–7 条跑绿、并在报告里写明每条视觉判据对应的代码依据。
- 后端测试用 `backend/.venv/bin/python -m pytest`。

## 4. 任务清单

### T1 外壳不可被滚动（P1-1）

1. `page.tsx:2387` 的 `overflow-hidden` 改为 `overflow-clip`，其他类保持原样、顺序不变：`chat-shell relative flex flex-col h-dvh overflow-clip`。
2. 不要去改 `globals.css:533` 的透镜探出量（那是手机输入釉片与底栏连成一片的材质做法）。
3. 不要加 `scrollIntoView`、不要给 `focus()` 加 `preventScroll`。

### T2 「回到最新」搬到遮罩层之外、贴着输入釉片（P1-2）

1. `ChatScrollArea.tsx` 新增两个可选 props，名称固定：
   - `Props` 追加 `renderLatestButton?: boolean;`（默认 `true`）与 `onLatestVisibilityChange?: (visible: boolean) => void;`；
   - `:20` 解构改为 `{ children, resetKey, renderLatestButton = true, onLatestVisibilityChange }`；
   - 在 `:113` 之后、`  return (` 之前插入，原文固定为：
     ```tsx
     useEffect(() => { onLatestVisibilityChange?.(showLatest); }, [showLatest, onLatestVisibilityChange]);
     ```
     （依赖数组含 `showLatest`，挂载首帧自然上报一次，不另写首帧逻辑；`useEffect` 已引入。）
   - `:138` 改为 `{renderLatestButton && showLatest && <button …`，按钮其余原文不动（旧分支保留）。
   - 句柄 `scrollToLatest()` 不变；显示条件 `!following && distance > 2` 不变；`:21–113` 不动。
2. `page.tsx`：
   - 新增 state，原文固定为 `const [showLatestPill, setShowLatestPill] = useState(false);`，放在 `:638` `composerHeight` 那个 `useState` 附近；
   - 给 `<ChatScrollArea>`（`:2544`）追加两个 prop，写法固定为 `renderLatestButton={false}` 与 `onLatestVisibilityChange={setShowLatestPill}`（直接传 setter，不要包箭头函数）；
   - 把 `--composer-height` 的内联变量从 `.chat-message-layer`（`:2543`）移到父容器 `[data-chat-panel]`（`:2481`）的 `style` 上（`.chat-message-layer` 靠继承仍能读到；`globals.css:510–528` 不用改）；
   - 在 `:2586`（`.chat-message-layer` 的闭合 `</div>`）之后、`:2587` `<Glaze as="footer">` 之前，条件渲染浮标，className 必须是一个字面字符串（不用模板串、不用 `cn()`）：
     ```tsx
     {showLatestPill && <button type="button" onClick={() => chatScrollRef.current?.scrollToLatest()}
       className="chat-latest chip absolute left-1/2 z-[1] h-8 -translate-x-1/2 gap-1.5 px-3 text-xs bg-[var(--mount)] shadow-[0_1px_2px_var(--drop)] bottom-[calc(var(--composer-height)+34px)] max-md:bottom-[calc(var(--composer-height)+var(--tabbar-h)+env(safe-area-inset-bottom)+12px)]">
       <ArrowDown size={12} />回到最新
     </button>}
     ```
     桌面 34px = 输入釉片离底 18px + 16px 间距；手机 12px 间距。层级用 `z-[1]`：高于 `.chat-message-layer`（z auto）、低于页头与输入釉片（`z-[2]`），这样打开「图片」菜单时菜单在浮标之上（v2 写的 `z-[3]` 会压住菜单，复核时发现）。`ArrowDown` 追加到 `page.tsx` 现有的 `lucide-react` 引入里。
   - 浮标 className 里不得出现：`border-border`、`bg-background`、`text-muted-foreground`、`shadow-sm`、`outline-primary`。

### T3 对话目录弹层像一整片瓷（P1-4）

在 `globals.css` 的 `.drawer-panel` 手机块内、`:571` 之后、`:572` 的 `}` 之前追加（要写说明注释也放在这个位置；不要碰 `:563` 的块头注释，不要在 `:564` 之前写任何带 `.drawer-panel` 的文字）：

```css
:root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-blur,
:root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-tint { -webkit-mask-image:none; mask-image:none; }
:root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-lens { display:none; }
:root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-tint { background:var(--glass2); }
```

`:530` 的 `border-radius:0` 保留。弹层宽度、遮罩、滑入动画、焦点陷阱都不动。

### T4 手机输入区空闲（状态 A）≤140px（P2-12）

1. 只改手机分支，桌面类不动：
   - `<Glaze as="footer">`（`:2587`）：把该行既有的 `max-md:pb-2` **原位替换**为 `max-md:pb-1.5`（不是追加），并追加 `max-md:pt-2`。改后该行必须同时含 `max-md:pt-2` 与 `max-md:pb-1.5`，且不得再含 `max-md:pb-2`（同一元素上不得出现两个 `max-md:pb-*` 或两个 `max-md:pt-*`：哪个生效由 Tailwind 排序决定，不受 class 书写顺序控制）。裸 `pb-3 pt-3`、`px-[18px]`、`rounded-[14px]` 一字不动。
   - `.composer-inner`（`:2630`）的 `max-md:py-2` 原位改为 `max-md:py-1.5`。
   - 页脚行（`:2723`）追加 `max-md:mt-1 max-md:pt-1 max-md:text-[11px]`（这一行基线没有任何 `max-md:` 间距类，追加即可）。
   - 以上合计减去 ≥ 12px（20→14、16→12、33→≤27）。状态 A 目标 ≤140；状态 B/C 因页脚行必含一枚 40px 按钮，本单只要求「与 A 相同的间距改动所能达到的最小值」（预期约 160），把 B/C 的实测值与拆解写进报告「已知未达」一节。若 A 实测仍 > 140，允许再把文本行 `py-1` 改成 `max-md:py-0.5`，但不许缩小文本框字号（手机 ≥ 16px 是硬约束）、不许把任何控件改成 `hidden` / `visibility:hidden` / 零行高、不许减小按钮高度、不许改 `ChatModelFooter` 的 DOM 结构或把它的按钮搬到别处。
2. 文本框有两行文字时输入区照常长高（只是空闲态要矮）。
3. 本单不改 `ChatModelFooter`（余额低于 30 变朱色的需求另开单）。

### T5 手机抽屉与弹层底边与底栏连成一片（P3-16）

在 T3 同一位置（`:571` 之后、`:572` 之前）追加：

```css
:root:not([data-shell=desktop]) .drawer-panel > .glaze-finish,
:root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-finish { background-image:radial-gradient(ellipse 90% 24% at 24% 0%, var(--sheen), transparent 70%); box-shadow:inset 0 1px 0 var(--lip); }
```

即只保留顶部酥油光与顶边高光，去掉底部积釉渐变、`lipdk` 底线、`pool` 内光与 `rim` 描边（边到边的面板上 `rim` 的左右边贴在屏幕外，底边正是缝）。不动桌面；不动 `.drawer-panel` 既有的四条规则。

### T6 新测试 `backend/tests/test_mobile_chat_fix.py`

照 `test_ui_polish_page_contracts.py` 的写法（读源码文本、做契约断言），离线、不依赖 git 历史、不读仓库外文件。`backend/tests` 不是包，`balanced_block` 不能 import，把它原样抄一份进新文件。至少覆盖：

1. `page.tsx` 含 `"chat-shell relative flex flex-col h-dvh overflow-clip"`，且不含 `"chat-shell relative flex flex-col h-dvh overflow-hidden"`。
2. `ChatScrollArea.tsx`：含 `renderLatestButton`；含 `onLatestVisibilityChange?.(showLatest)`（调用，不只是声明）与 `[showLatest, onLatestVisibilityChange]`（依赖数组）；`source.count("onLatestVisibilityChange") == 3`（Props 声明、解构、effect 调用各一次——多出一次即说明回调被塞进了别处）；含 `{renderLatestButton && showLatest && <button`；`scrollToLatest` 句柄仍在；`:30–35` 的 `updateButton` 六行原文与 `:96–113` 的 `onScroll` 全文作为多行常量 `in source`；`source.index("const onScroll = ") < source.index("onLatestVisibilityChange?.(showLatest)") < source.index("  return (")`；`source.count("回到最新") == 1`。
3. `page.tsx` 浮标：`<ChatScrollArea`（带尖括号，避开 import 行）、`</ChatScrollArea>`、`className="chat-message-layer`、`<Glaze as="footer"` 四个锚点各恰好出现 1 次（先断言，再比偏移）；`chat-latest` 恰好出现 1 次；令 `scroll_end = source.index('</ChatScrollArea>')`、`layer_end = source.index('</div>', scroll_end)`、`pill = source.index('chat-latest')`、`footer = source.index('<Glaze as="footer"')`，断言 `layer_end < pill < footer`；从 `<ChatScrollArea` 到 `</ChatScrollArea>` 之间不含 `chat-latest`；`m = re.search(r'className="([^"]*\bchat-latest\b[^"]*)"', source)` 非空且 `m.group(1)` 不含五个旧令牌写法；`'renderLatestButton={false}' in source`；`'onLatestVisibilityChange={setShowLatestPill}' in source` 且 `source.count('onLatestVisibilityChange=') == 1`；`'const [showLatestPill, setShowLatestPill] = useState(false);' in source` 且 `source.count('showLatestPill') >= 2`；`source.count('回到最新') == 1`。
4. `globals.css`：用与 `test_ui_polish_page_contracts.py:119–123` 相同的方式取出 `.drawer-panel` 所在的手机媒体块（不要另造更宽松的取法），断言块内含 T3 的三类选择器（`.chat-conversation-modal > .glaze > .glaze-blur`、`> .glaze-lens { display:none; }`、`> .glaze-tint { background:var(--glass2); }`）与 T5 的两条选择器（`.drawer-panel > .glaze-finish`、`.chat-conversation-modal > .glaze > .glaze-finish`），T5 规则含 `box-shadow:inset 0 1px 0 var(--lip)` 且不含 `lipdk`；块内不含 `:root[data-shell=desktop] .chat-conversation-modal`；既有四条 `.drawer-panel` 规则原文仍在。
5. `page.tsx` 输入区：取出 `<Glaze as="footer"` 所在的那一行，断言它仍含 `px-[18px] pb-3 pt-3`、`rounded-[14px]`（桌面不变），含 `max-md:pt-2` 与 `max-md:pb-1.5`，`re.search(r"max-md:pb-2(?![\d.])", line)` 为 `None`，`len(re.findall(r"max-md:pb-", line)) == 1`，`len(re.findall(r"max-md:pt-", line)) == 1`；`.composer-inner` 那一行含 `max-md:py-1.5` 且不含 `max-md:py-2`。
6. 文案契约：`page.tsx` 中 `source.count('每条消息消耗 <span className="readout font-normal">10</span> 颗草莓') == 1`、`source.count('"平台模型 · 每条 10 颗草莓"') == 2`、`source.count('平台模型每条消息消耗 10 颗；自带模型聊天不扣') == 1`、`source.count('Enter 发送，Shift + Enter 换行') == 1`；断言写成 `== N`，不得写成 `>= 0` 或 `in` 以外的弱形式。
7. 不加粗：`page.tsx` `source.count("font-semibold") <= 3`；`ChatScrollArea.tsx` 不含 `font-semibold` / `font-bold`。

### T7 报告 `03-report.md`

见 §7。

## 5. 不允许的做法

- 用隐藏元素、`visibility:hidden`、零行高、裁切、缩字号、缩按钮高度来凑 140px。
- 把浮标留在 `.chat-message-layer` 里（包括塞在 `</ChatScrollArea>` 与遮罩层闭合 `</div>` 之间），靠改 mask 让它「看起来」不透明。
- 在 `updateButton` 或 `onScroll` 里调用 `onLatestVisibilityChange`（只能用 T2-1 给定的 effect）。
- 为了让弹层不露缝而改成全屏（`w-screen`）——这会丢掉点遮罩关闭的交互；本单只改材质。
- 改 `ChatScrollArea` 的跟随逻辑、`ResizeObserver`、`resetKey` 行为。
- 任何桌面可见变化；任何不在白名单的文件改动；任何既有测试改动；为了让新测试绿而放宽取块方式。
- 新写的界面文案用中点「·」分隔；任何加粗。

## 6. 验收标准（全部可执行；Claude 逐条复跑，以 Claude 结果为准）

在仓库根执行（第 1–7 条你必须自己跑绿并把输出摘要写进报告）：

1. `cd frontend && npx tsc --noEmit` → 退出码 0。
2. `cd frontend && npm run lint` → 0 errors，warnings ≤ 25。
3. `cd frontend && npm run build` → 退出码 0。
4. `cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py -p no:cacheprovider` → 全部通过，总数 ≥ 492 + 7（既有 492 条一条不少；新文件 ≥ 7 条，其中 `test_globals_css_smooths_drawer_materials_on_mobile_only` 必须仍绿）。
5. 结构判据（`grep` 在仓库根；括号内为 HEAD 基线）：
   - `grep -c 'chat-shell relative flex flex-col h-dvh overflow-clip' frontend/app/page.tsx` = 1（0）；`grep -c 'h-dvh overflow-hidden' frontend/app/page.tsx` = 0（1）。
   - `grep -c 'drawer-panel' frontend/app/page.tsx` = 6（6）。
   - `grep -c 'chat-latest' frontend/app/page.tsx` = 1（0）；`grep -c 'renderLatestButton={false}' frontend/app/page.tsx` = 1（0）；`grep -c 'onLatestVisibilityChange={setShowLatestPill}' frontend/app/page.tsx` = 1（0）；`grep -c 'onLatestVisibilityChange=' frontend/app/page.tsx` = 1（0）；`grep -cF 'onLatestVisibilityChange?.(showLatest)' frontend/components/ChatScrollArea.tsx` = 1（0）；`grep -c '回到最新' frontend/app/page.tsx` = 1（0）；`grep -c '回到最新' frontend/components/ChatScrollArea.tsx` = 1（1）。
   - 浮标位置：`grep -c '</ChatScrollArea>' frontend/app/page.tsx` = 1（1），且 `awk '/<\/ChatScrollArea>/{a=NR} a&&!d&&/<\/div>/{d=NR} /chat-latest/{b=NR} /<Glaze as="footer"/{c=NR} END{exit !(d && b && c && d<b && b<c)}' frontend/app/page.tsx` 退出码 0。
   - `grep 'chat-latest' frontend/app/page.tsx | grep -cE 'border-border|bg-background|text-muted-foreground|shadow-sm|outline-primary'` = 0。
   - `ChatScrollArea.tsx:21–113` 未动：`diff <(git show HEAD:frontend/components/ChatScrollArea.tsx | sed -n 21,113p) <(awk '/^  const viewportRef = /{p=1} p{print} p&&/^  const onScroll = /{q=1} q&&/^  };$/{exit}' frontend/components/ChatScrollArea.tsx)` 输出为空（HEAD 上已实测为空、恰好 93 行）；`git diff -U0 HEAD -- frontend/components/ChatScrollArea.tsx | grep -E '^@@ -'` 的每个 hunk 头 `@@ -a[,b]`（b 缺省记 1）：b>0 时 [a, a+b) 与 [21,114) 不相交；b=0（纯插入）时 a ∉ [21,112]。
   - `grep -c 'chat-conversation-modal > .glaze > .glaze-lens' frontend/app/globals.css` = 1（0）；`grep -c 'drawer-panel > .glaze-finish' frontend/app/globals.css` = 1（0）；`grep -c 'chat-conversation-modal > .glaze > .glaze-finish' frontend/app/globals.css` = 1（0）；`grep -c 'data-shell=desktop\] .chat-conversation-modal' frontend/app/globals.css` = 0（0）。
   - `grep -n '\.drawer-panel' frontend/app/globals.css | head -1` 的行号 = 565，`grep -n '@media (width < 48rem)' frontend/app/globals.css | tail -1` 的行号 = 564（`.drawer-panel` 第一次出现仍落在 `:564` 开头的块内，前面没有新增块）。
   - 输入区：`grep 'as="footer"' frontend/app/page.tsx | grep -cE 'max-md:pb-2([^.0-9]|$)'` = 0（1）；`grep 'as="footer"' frontend/app/page.tsx | grep -c 'max-md:pb-1.5'` = 1（0）；`grep 'as="footer"' frontend/app/page.tsx | grep -c 'max-md:pt-2'` = 1（0）；`grep 'composer-inner' frontend/app/page.tsx | grep -c 'max-md:py-1.5'` = 1（0）。
   - 文案：`grep -cF '每条消息消耗 <span className="readout font-normal">10</span> 颗草莓' frontend/app/page.tsx` = 1（1）；`grep -cF '平台模型 · 每条 10 颗草莓' frontend/app/page.tsx` = 2（2）；`grep -cF '平台模型每条消息消耗 10 颗；自带模型聊天不扣' frontend/app/page.tsx` = 1（1）；`grep -cF 'Enter 发送，Shift + Enter 换行' frontend/app/page.tsx` = 1（1）。
   - 不加粗：`grep -c 'font-semibold' frontend/app/page.tsx` ≤ 3（3）；`grep -cE 'font-(semibold|bold)' frontend/components/ChatScrollArea.tsx` = 0（0）。
6. 改动集合：`git status --porcelain` 只出现白名单五个路径与本规格所在目录；`git diff --stat` 不含 `package.json`、`package-lock.json`、`next.config.ts`、`backend/`（测试新文件除外）、`components/ui/`。
7. 桌面不变（Claude 核）：`git diff -U0 HEAD -- frontend/app/page.tsx` 中，输入区（`<Glaze as="footer"` 到其 `</Glaze>`）新增的每个 class 都带 `max-md:` 前缀；`globals.css` 新增规则全部位于 `:564` 开头的 `@media (width < 48rem)` 块内。
8. 视觉与行为（Claude 在隔离实例用真实浏览器量，昼夜各一遍；状态 A/B/C 按 §2.4 用隔离实例的测试账号构造，不碰用户库）：
   - 外壳：390×844 真实点击文本框、再真实点击「图片」菜单后，`.chat-shell.scrollTop === 0`，`.chat-header` 的 `top` 为 0（±0.5），`document.scrollingElement.scrollTop === 0`；1440×900 同样操作后 `.chat-shell.scrollTop === 0`，`.chat-header` 的 `top` 为 12（与 HEAD 相同）。
   - 浮标：两种视口下把消息区向上滚 300px 后，`.chat-latest` 存在、`!document.querySelector('.chat-message-layer').contains(pill)`、水平居中（其中心与 `[data-chat-panel]` 中心之差 ≤ 2px）、`.chat-composer` 的 `top` 减去浮标 `bottom` 在 12–24px 之间、`getComputedStyle(pill).opacity === '1'`；滚回底部后浮标消失；点击浮标回到底部；截图里浮标文字清晰、不被渐隐。
   - 弹层：390×844 打开「对话列表」，`.chat-conversation-modal > .glaze > .glaze-lens` 的 `display === 'none'`，`.glaze-tint` 的 `maskImage === 'none'`、`backgroundColor` 等于 `--glass2` 解析值；截图里弹层下沿附近不出现可辨认或扭曲的底层文字。
   - 输入区：390×844 空闲态分别在状态 A、B、C 各量一次 `.chat-composer` 的 `getBoundingClientRect().height`：A ≤ 140；B、C ≤ 同状态 HEAD 实测值 − 12（Claude 先量 HEAD 再量候选）。三态下文本框、「图片」、语音、「发送」四个元素均 `getClientRects().length > 0`、`visibility === 'visible'`、`opacity === '1'`、高度 ≥ 16（文本框）/ ≥ 40（按钮）且整个矩形落在 `.chat-composer` 矩形内；A 态另要求「每条消息消耗」那一行可见且高度 ≥ 14，B/C 态另要求模型标签与「改用…」按钮可见且按钮高度 ≥ 40；文本框 `font-size ≥ 16px`；输入两行文字后高度增加且 ≤ 190（A）/ ≤ 214（B/C）；1440×900 三态空闲高度均与 HEAD 相同。不得用 mock 404 或请求 pending 代替 B/C（404 走错误分支会多出 40px「重试」按钮）。
   - 抽屉与弹层底边：390×844 打开设置抽屉，`getComputedStyle(document.querySelector('.drawer-panel > .glaze-finish'))` 的 `backgroundImage` 含恰好一个 `radial-gradient` 且不含 `linear-gradient`，`boxShadow` 等于 `inset 0 1px 0 <--lip 解析值>`（不含 `-1px`、不含 `24px`）；对话列表弹层的 `.glaze-finish` 同样。像素判据（HEAD 与候选同机、同主题、同一抽屉各截一张，昼夜各一遍）：取抽屉最后一行 y=783 与其上方 y=776 两行，在抽屉整宽上逐列算每通道绝对差，取中位数；候选 ≤ 3/255，而 HEAD 同一测量必须 > 3/255（HEAD 若也 ≤ 3 说明没量到 `lipdk` 线，换行号或主题重测，不得直接判过）。y=784 及以下属于底栏自身的 `--carve` 边线与 `--etch` 内阴影，不参与比对。1440×900 打开同一抽屉，`.glaze-finish` 的 `backgroundImage` 与 `boxShadow` 与 HEAD 逐字相同。
9. 手机不变量（来自 09-23 手机规格，继续成立）：390×844 与 360×740 下 `/` 无横向滚动（比 `document.documentElement.clientWidth`，不比 `innerWidth`），可点目标 ≥ 40×40，输入区下沿不低于底栏上沿。

## 7. 交付：变更总结（写进 `03-report.md`）

1. 修改 / 新增了哪些文件（逐个列）；
2. 实现了哪些功能；
3. 与 §4 T1–T7 的逐项对应；
4. §6 第 1–7 条的实际运行结果（命令与输出摘要；第 4 条写明 passed 数；第 5 条逐条写实际值）；
5. 「已知未达」：状态 B/C 的拆解与预期高度；
6. 未完成或需要人工确认的地方，含你主动偏离本规格的地方与理由，以及 §6 第 8 条每项视觉判据对应的代码依据（让 Claude 能对着量）。

## 8. 何时停下来问

只在影响「实现什么」时停：

- 不改 `ChatScrollArea.tsx:21–113` 的任何一行（含插行）就做不到 T2；
- 在状态 A 下，不隐藏任何控件、不缩字号 / 按钮的前提下做不到 ≤140（此时把能做到的最小值与改法写进报告，不要硬凑）；状态 B/C 到不了 140 是预期内的，不要停、不要为它缩按钮；
- 规格与你实测到的事实不符（你实测到的事实优先于本规格的断言，先停下来说明）。

只影响「怎么实现 / 怎么验证」的自行决定并在报告里说明。任何情况下不回滚已完成的工作。

## 9. 执行方式（派单正文随规格一起发）

用工作流（`workflow` 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好：

- agent A：`frontend/app/page.tsx`（T1、T2 的 page 侧、T4）；
- agent B：`frontend/components/ChatScrollArea.tsx`（T2 的组件侧，接口按 §4-T2-1 的名字与原文写死）；
- agent C：`frontend/app/globals.css`（T3、T5）；
- agent D：`backend/tests/test_mobile_chat_fix.py`（T6）——等 A、B、C 完成后再跑一次确认全绿。

每个 agent 的任务说明自包含（它看不到主代理的对话），并写明不得调用 subagent / subagent_fork / workflow。主代理只做拆分、派发、汇总、白名单检查、门禁（§6 第 1–7 条）、报告；报告开头列拆分表，如实列出全部派出过的 agent。

## 10. 待拍板（不在本单实现）

- 手机状态 B/C（账号配置过自带模型）输入区空闲约 160px，超过 10-26 的 ≤140 目标。要到 140 必须动页脚结构，可选：① 「思考」强度切换移到设置页，页脚只留标签 + 一枚切换按钮；② 把切换按钮并入 `.composer-tools` 行（390 宽下 C 态可能折行）；③ 接受 B/C ≈160 为新目标。
- 余额低于 30 时费用提示变朱色：涉及 `ChatModelFooter` 三态与桌面颜色，另开单。

## 修订记录

### v2.1（独立复核后）

- T2 浮标层级 `z-[3]` → `z-[1]`：`z-[3]` 高于输入釉片（`z-[2]`）的层叠上下文，会盖住困在其中的「图片」菜单（`ComposerImageMenu.tsx:103`）。
- T6-2 两处笔误按实现方的解释执行：`onLatestVisibilityChange` 子串总数是 4（effect 一行含调用与依赖数组各一次），「含该词的行数」为 3；`return (` 锚点用 `"\n  return ("`，避免命中 effect 清理函数里的四空格 `return`。
- §6-8 状态 C 的构造：PUT `/chat-model` 不会把已存在记录的 `enabled` 改回 true（`store.py:173` 沿用旧值），测量脚本须在 PUT 后 PATCH `{"enabled": true}` 并断言页脚出现 `role=radiogroup`。
- 返修单：`05-fix-r1.md`。

### v2（对抗复核后）

- §2.4：补 `ChatModelFooter` 三态事实；151px 明确为状态 A；footer 行的 `max-md:pb-2` 写法纠正。
- §2.3：遮罩行号 2470→2474；补既有测试取块方式的脆弱点。
- §2.5：补底栏自身两条 1px 线不计入缝；T5 改为只去底部积釉与 lipdk，保留顶部酥油光。
- §3.2：ChatScrollArea 保留范围 18–113 → 21–113，并写死签名、effect、按钮分支的允许改法；文案保留按源码真实写法列出。
- T2：state、prop、effect 原文全部固定；浮标 className 必须是字面串。
- T4：`max-md:pb-2` 原位替换；去掉 T4-2 变朱色；B/C 态写明不要求 ≤140。
- T6：锚点唯一性与偏移断言重写；补文案契约、`onLatestVisibilityChange` 调用计数、`balanced_block` 抄入说明。
- §6：补 awk/diff 机械判据与全部 HEAD 基线值；「每条消息消耗」恒真 grep 改为真实串；桌面页头 top 为 12；抽屉缝改为像素中位数判据并要求 HEAD 先失败一次；控件可见判据补 visibility/opacity/包含关系。
