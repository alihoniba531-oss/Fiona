# 02 规格：前端 UI 打磨（2026-10-26）

任务级别：L2（UI 打磨，不改数据模型、不改后端、不改产品方向）。执行者：dsh / DeepSeek Flash。
仓库根：本工作树（分支 `feat/ui-polish`，基线提交 `5985f43`）。前端在 `frontend/`，后端测试在 `backend/tests/`。

## 1. 产品目标与场景

Fiona（产品名 Chloe）是个人 AI 分身聊天应用，视觉方向「宋式清雅 + 影青釉」已定稿，本次**不改视觉方向**，只修审视中发现的问题：

1. AI 回复里的 Markdown 原样显示（`- `、`1. `、`**`、`#`）。主人现在常用 Claude，回复里大量带这些符号。
2. 设置页两个区块用了同一个 React key，导致「聊天模型」重复出现、「本机监控」有时消失。
3. 手机上输入区太高（输入框、图片按钮行、语音与发送行、两行模型说明叠在一起），消息区只剩一半。
4. 两个一模一样的麦克风按钮（「语音转文字」与「按住说话」）。主人已拍板：**合成一个**，轻点开始录音、再点一下发送；按住说话、松开发送。
5. 三个图片入口意思混在一起。主人已拍板：**合成一个「图片」菜单**，三项：发图给 Chloe 看 / 生成图片 / 改一张图。
6. 抽屉里标题重复：抽屉页眉写着「设置」，页面里又是一个大号「设置」。
7. 手机上抽屉两侧边缘半透明，能看到下面被透镜扭曲的页面。
8. 输入框下方直接显示 `claude-haiku-5-5` 这类系统 ID，应显示 `Claude Haiku 5.5`。
9. 聊天相关的时间按设备时区显示，而 Chloe 按北京时间说话，两者在海外时区设备上对不上。主人已拍板：**聊天相关界面统一按北京时间显示**。

## 2. 技术约束（硬性）

- 沿用现有技术栈（Next.js 16 + React 19 + Tailwind 4）与组件风格（`btn` / `chip` / `ceramic-card` / `Glaze` / CSS 变量 `--ink` `--ink2` `--ink3` `--rule` `--rule2` `--chip` `--seal` `--rec` `--rec-soft` `--bd` 等）。改前端代码前先读 `frontend/AGENTS.md`。
- **不新增任何依赖**，不改 `package.json` / `package-lock.json`。Markdown 必须自己写解析器。
- **界面文字一律不加粗**：新写的代码不得出现 `font-semibold`、`font-bold`、`font-extrabold`、`font-black`、内联或 CSS 里的 `font-weight` ≥ 600，`<strong>`、`<b>` 也不得用于新内容（`<em>` 可用，但要 `not-italic`）。层次只靠字号与灰度。
- 不改后端任何文件（`backend/` 下只允许新增测试文件，见白名单）。
- **不得重排、重新格式化既有代码**。只改任务涉及的行；不要动无关的缩进、引号、换行。很多既有测试按字面片段提取代码（见 §2.1），改格式就会让它们变红。
- **既有测试一字不许改**（输入、断言、夹具都不改，也不删、不跳过）。新测试一律放进新文件。
- Markdown 渲染只用 React 文本节点，**禁止** `dangerouslySetInnerHTML`、禁止生成 `<a>` 链接、禁止解释任何 HTML。
- 不读 `.env`、数据库、`backend/uploads/`。

### 2.1 既有测试钉住的字面片段（改动时必须原样保留）

- `frontend/components/ChatBubble.tsx`：注释 `{/* 文字气泡` 必须保留；它后面紧跟的条件表达式 `{(message.content || (message.isTyping && !message.generationStatus)) && message.content !== "[发了一张图片]" && (` 必须一字不改，且条件后仍是 `&& (` 接 `<div`（测试用正则 `\{(.*?)\s*&&\s*\(\s*<div` 提取它）。以下字符串也必须保留：`cardData.subtype === "web_sources" ? "联网搜索"`、`{cardData.subtype !== "web_sources" && <ul`、`cardData.subtype !== "web_sources" && safeSources.length === 0 && cardData.url`、`cardData.subtype !== "web_sources" && <div className="mb-1.5`、`safeSources.map`、`openExternal(url)`、`import SongProjectCard from "@/components/SongProjectCard";`、`card.subtype === "song_project"`、`<SongProjectCard projectId={projectId} onCompose={onCompose} />`、`songCardCompact?: (projectId: string) => boolean`。
- `frontend/app/page.tsx`：`interface ChatStreamEvent {` 块、`if (data.text) {\n            reply += data.text;` 块、`if (data.card && data.append === true)` 块、`const requestImageModel = imageModel;`、`image_model: requestImageModel,`、`createLocalWatchPoller`、`10_000`、`document.visibilityState === "visible"`、`studioAllowed ? <iframe`、`key={username}`（工作室 iframe 那处）、`src="/studio?embed=1"` 都不得改动。
- 后端文案「今天用自带模型聊天的次数已用完，明天再试，或在输入框下方改用平台」由后端测试钉住，所以**输入框下方必须仍有一个文字为「改用平台」的按钮**（自带模型启用时），行为不变。
- `frontend/app/settings/page.tsx` 必须仍包含字符串 `LocalWatchSection`。
- 不确定某处是否被测试钉住时，先 `grep -rn '<片段>' backend/tests/` 查。

### 2.2 何时停下来问

只有影响「实现什么」的情况才停下来说明（规格自相矛盾、按规格无法实现、为了实现必须改白名单外文件或改既有测试）。只影响「怎么实现 / 怎么验证」的，自己决定并在报告里写明理由。**你实测到的事实优先于本规格的断言**，不一致就在报告里写明。任何情况下不回滚已完成的工作。

## 3. 文件白名单

只允许修改或新增下列文件，其余一律不动：

修改：
- `frontend/components/ChatBubble.tsx`
- `frontend/app/history/page.tsx`
- `frontend/app/page.tsx`
- `frontend/app/globals.css`
- `frontend/lib/chatModel.ts`
- `frontend/lib/chineseDate.ts`
- `frontend/components/ConversationPicker.tsx`
- `frontend/components/LocalWatchSection.tsx`（只改时间格式那一处）
- `frontend/app/plaza/page.tsx`（只改时间格式那两处）
- `frontend/components/AgentExchangeWorkspace.tsx`（时间格式函数 + 嵌入时隐藏大标题）
- `frontend/app/settings/page.tsx`
- `frontend/app/profile/page.tsx`
- `frontend/app/novels/page.tsx`
- `frontend/components/MyAgentWorkspace.tsx`

新增：
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
- `docs/tasks/2026-10-26-ui-polish/03-report.md`（你的变更报告）

明确**不改**：`lib/novels.ts`、`lib/studio.ts`、`lib/studio-casting.ts`、`components/studio/**`、`app/studio/**`（它们的时间格式被既有测试钉成设备时区，本轮不动）、`components/ChatModelSection.tsx`（设置页里的型号按钮保留原始 ID，那是配置表单）。

## 4. 任务清单

### T1 Markdown 安全子集解析器 `frontend/lib/messageMarkdown.ts`（新文件）

导出以下类型与函数，签名必须一致（其他任务按它调用）：

```ts
export type MdInline =
  | { kind: "text"; text: string }
  | { kind: "em"; text: string }
  | { kind: "code"; text: string };
export type MdListItem = { depth: 0 | 1; inlines: MdInline[] };
export type MdBlock =
  | { kind: "para"; inlines: MdInline[] }
  | { kind: "heading"; level: 1 | 2 | 3; inlines: MdInline[] }
  | { kind: "list"; ordered: boolean; start: number; items: MdListItem[] }
  | { kind: "quote"; inlines: MdInline[] }
  | { kind: "code"; text: string }
  | { kind: "rule" };
export function parseMessageMarkdown(text: string, options?: { typing?: boolean }): MdBlock[];
export function stripMessageMarkdown(text: string): string;
```

纯函数，不依赖 React、DOM、浏览器 API。规则（按行处理，先把 `\r\n` 规范成 `\n`）：

1. **围栏代码块**：行匹配 `/^\s{0,3}```/` 开始，到下一个同样匹配的行结束；中间原样收进 `code.text`（去掉首尾两条围栏行，开头那行 ``` 后的语言名丢弃）。没有闭合就收到文本末尾。代码块内部不做任何其他解析。
2. **空行**结束当前段落 / 列表 / 引用。
3. **标题**：`/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/`。`#` 与 `##` → level 1，`###` → level 2，`####`–`######` → level 3。
4. **分隔线**：`/^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/` → `rule`（在列表判断之前判断）。
5. **无序列表项**：`/^(\s*)([-*+•])\s+(.*)$/`。**有序列表项**：`/^(\s*)(\d{1,3})(?:[.)]\s+|、\s*)(.*)$/`（`1.`、`1)` 后必须有空白；`1、` 后空白可有可无，所以「1.5 倍」不会被当成列表）。前导空格 ≥ 2 且当前已在列表中 → `depth: 1`，否则 `depth: 0`。同一列表里有序/无序种类在 depth 0 上切换时，开始一个新的 list 块。`start` 取该列表第一项的数字（无序为 1）。
6. **列表续行**：紧跟列表项、前导空格 ≥ 2、且不是新的块起始的非空行，接到上一项，中间用 `\n` 连接。前导空格 < 2 的普通行**结束列表**并开始新段落（这里刻意不同于 CommonMark 的懒续行）。
7. **引用**：连续的 `/^\s{0,3}>\s?(.*)$/` 行合成一个 `quote`，行间 `\n`。
8. **段落**：其余连续非空行合成一个 `para`，行间保留 `\n`（渲染时 `whitespace-pre-wrap`，与现在的换行效果一致）。
9. **行内**（作用于 para / heading / list item / quote 的文本）：
   - 先切出行内代码：成对的单个反引号 `` `x` ``（内容非空、不跨 `\n`）→ `code`。
   - 再在非代码文本里找成对的 `**x**`（内容非空、不跨块，可以跨 `\n`）→ `em`。
   - 只认 `**`。单个 `*`、`_`、`__` 一律当普通文字（避免把 `snake_case`、乘号弄坏）。链接 `[t](u)`、HTML 标签、表格行都原样当文字。
   - 不成对的 `**` 或反引号原样保留为文字；**但** `options.typing === true` 时，整段文本最后一个未配对的 `**`（或未配对的单个反引号）不显示（去掉这两个字符/这一个字符），避免打字机逐字输出时闪出星号。
   - 相邻的 text 片段合并。
10. 输入为空串返回 `[]`。不得抛异常（任何输入都返回结果）。
11. `stripMessageMarkdown(text)`：返回去掉上述标记后的纯文本（列表项前加「· 」或「n. 」，标题、引用去掉标记，`**`、成对反引号去掉，代码块保留内容），块之间用一个空行分隔。供测试与日后朗读使用；本轮不接入朗读。

### T2 Markdown 渲染组件 `frontend/components/MessageText.tsx`（新文件）

```tsx
export default function MessageText({ text, typing = false, caret = false }: { text: string; typing?: boolean; caret?: boolean }): JSX.Element
```

- 调用 `parseMessageMarkdown(text, { typing })`，逐块渲染。每个块元素带类名 `md-block`。块与块之间 `mt-[0.75em]`（第一个块无上边距，可用 `[&>*:first-child]:mt-0` 或在组件里判断）。
- `para`：`<p className="md-block whitespace-pre-wrap">`。
- `heading`：用 `<h3>`（level 1）、`<h4>`（level 2）、`<h5>`（level 3），全部 `font-normal`。字号：level 1 `text-[18.5px] leading-[1.7] tracking-[.04em] text-[color:var(--ink)]`，level 2 `text-[17.5px] leading-[1.75] tracking-[.04em] text-[color:var(--ink)]`，level 3 用正文字号 `text-[1em] tracking-[.08em] text-[color:var(--ink2)]`；标题上边距 `mt-[1.1em]`（作为第一个块时为 0）。
- `list`：无序 `<ul>`、有序 `<ol start={start}>`，`list-none p-0`。每项 `<li className="relative whitespace-pre-wrap pl-[1.4em]">`，项间 `mt-[.3em]`；depth 1 再加 `ml-[1.4em]`。
  - 无序标记：项内开头一个 `aria-hidden` 的绝对定位小圆点：`absolute left-[.45em] top-[.85em] h-[4px] w-[4px] rounded-full bg-[color:var(--ink3)]`；depth 1 改为空心圆（`border border-[color:var(--ink3)] bg-transparent`）。
  - 有序标记：`aria-hidden` 的 `<span className="absolute left-0 tabular-nums text-[color:var(--ink2)]">{n}.</span>`，n 从 start 起按项递增（只计 depth 0 的项；depth 1 的项用无序小圆点）。
- `quote`：`<blockquote className="md-block whitespace-pre-wrap border-l border-[color:var(--rule2)] pl-[1em] text-[color:var(--ink2)]">`。
- `code`（块）：`<pre className="md-block overflow-x-auto whitespace-pre rounded-[8px] bg-[color:var(--chip)] px-[1em] py-[.75em] font-mono text-[14px] leading-[1.7]">`。
- `rule`：`<hr className="md-block my-[1.2em] border-0 border-t border-[color:var(--rule)]" />`。
- 行内 `em`：用中文着重号，不加粗、不斜体：`<em className="not-italic [-webkit-text-emphasis:filled_dot_var(--ink3)] [text-emphasis:filled_dot_var(--ink3)] [-webkit-text-emphasis-position:under_right] [text-emphasis-position:under_right]">`。
- 行内 `code`：`<code className="rounded-[4px] bg-[color:var(--chip)] px-[.3em] text-[.92em]">`（字体继承正文）。
- `caret === true` 时，在**最后一个块的最后一行文字末尾**（列表就放在最后一项里、代码块放在 pre 里末尾）追加 `<span aria-hidden="true" className="ml-px text-[color:var(--amber-ink)] animate-[blink_1.4s_infinite]">▌</span>`（`blink` 关键帧已在 globals.css 中定义）。没有块时只渲染这个光标。
- 不渲染任何 HTML，不生成链接。

### T3 聊天气泡与历史页接入 Markdown、北京时间 `ChatBubble.tsx`、`history/page.tsx`

- `ChatBubble.tsx`：
  - AI 消息（`!isUser`）的文字气泡内容改为 `<MessageText text={shownContent || (message.isTyping ? "" : "…")} typing={!!(message.isTyping || stillTyping)} caret={!!(message.isTyping || stillTyping)} />`。
  - AI 分支的容器类名去掉 `whitespace-pre-wrap` 与 `typing-cursor`（光标改由 MessageText 渲染）；**用户消息分支保持原样**（纯文本、`whitespace-pre-wrap`、`bubble-user`，有 typing 时仍用 `typing-cursor`）。实现方式：把 `cn(...)` 里的 `"break-words whitespace-pre-wrap"` 和 `(message.isTyping || stillTyping) && "typing-cursor"` 改成按 `isUser` 区分，条件表达式（§2.1）不动。
  - `timeStr` 改用 `formatBeijingTime(message.timestamp)`（T4）。
- `history/page.tsx`：
  - AI 消息正文改用 `<MessageText text={...} />`（不传 typing / caret）；用户消息保持纯文本。
  - 本文件里所有日期 / 时间的计算和显示都改用 T4 的北京时间函数：按日分组的键（第 29–31 行附近的函数）、「今天 / 近7天 / 本月」筛选的起止边界、自定义区间两个日期输入框（`YYYY-MM-DD` 按北京自然日的 00:00–23:59:59 解释）、按日期跳转列表、导出文本里每行的时间戳（格式 `YYYY/MM/DD HH:mm:ss`）、每条消息的时间（`HH:mm`）、分组标题（`formatChineseDate`，T4 会改成按北京时间取年月日）。
  - 页头副标题区域（`tester | 414 条` 那一行之后）加一段 `text-[11px] text-[color:var(--ink2)]` 的小字「北京时间」。

### T4 北京时间工具 `frontend/lib/beijingTime.ts`（新文件）与时间显示改造

北京时间固定为 UTC+8、无夏令时。**用算术实现，不用 `Intl` 时区**（结果与设备时区无关，便于测试）：先 `new Date(date.getTime() + 8 * 3600_000)`，再取 `getUTC*()`。

```ts
export const BEIJING_OFFSET_MS = 8 * 3600_000;
export function beijingParts(date: Date): { year: number; month: number; day: number; hour: number; minute: number; second: number; weekday: number }; // month 1–12，weekday 0=周日
export function beijingDayNumber(date: Date): number;            // Math.floor((date.getTime() + BEIJING_OFFSET_MS) / 86_400_000)
export function beijingDateKey(date: Date): string;              // "YYYY-MM-DD"
export function beijingDayStart(dateKey: string): Date;          // 该北京自然日 00:00 对应的时刻；dateKey 非法时返回 Invalid Date
export function formatBeijingTime(date: Date): string;           // "HH:mm"，24 小时制，补零
export function formatBeijingDateTime(date: Date, withSeconds = false): string; // "YYYY/MM/DD HH:mm" 或 "YYYY/MM/DD HH:mm:ss"
export function formatBeijingDateLong(date: Date): string;       // "2026年10月21日"（月、日不补零）
```

非法日期（`Number.isNaN(date.getTime())`）时，格式化函数返回空串，`beijingParts` 返回全部为 `NaN` 的对象，不抛异常。

按下表替换（**只替换列出的位置**，并用 `grep -nE 'toLocale(Date|Time)?String|getHours\(|getMinutes\(|getDate\(|getDay\(|getMonth\(|getFullYear\(|toDateString\(' <文件>` 确认这些文件里不再有按设备时区显示**日期时间**的调用；数字的 `toLocaleString`（字数千分位）不算，保留）：

| 文件 | 位置 | 改成 |
|---|---|---|
| `components/ChatBubble.tsx` | `timeStr` | `formatBeijingTime`（T3） |
| `app/page.tsx` | `groupByDate` 的分组键 | `formatBeijingDateLong`；组间排序逻辑不变 |
| `app/page.tsx` | 约 2445 行 `msg.timestamp.toLocaleString("zh-CN", {...})` | `formatBeijingDateTime(msg.timestamp)`（按原来是否带秒决定 `withSeconds`） |
| `app/page.tsx` | 约 2571 行相邻消息 `toDateString()` 比较 | 比较 `beijingDateKey` |
| `lib/chineseDate.ts` | `formatChineseDate` | 年月日取自 `beijingParts(date)` |
| `components/ConversationPicker.tsx` | `formatRelative` | `daysAgo = beijingDayNumber(now) - beijingDayNumber(date)`；当天 `formatBeijingTime`；周几用 `beijingParts(date).weekday`；`MM/DD` 用 parts |
| `app/history/page.tsx` | 见 T3 | 见 T3 |
| `components/LocalWatchSection.tsx` | 约 24 行 `date.toLocaleString("zh-CN")` | `formatBeijingDateTime(date, true)`；无效日期仍返回「时间未知」 |
| `app/plaza/page.tsx` | 约 153 行 `toLocaleTimeString`、约 210 行 `title={updateDate?.toLocaleString("zh-CN")}` | `formatBeijingTime` / `formatBeijingDateTime(updateDate, true)` |
| `components/AgentExchangeWorkspace.tsx` | 约 490–494 行的日期函数（当天显示时间、否则 `MM/DD`） | 「当天」按 `beijingDayNumber` 判断，时间 `formatBeijingTime`，`MM/DD` 用 parts |

行号以实际文件为准，先 `grep` 定位。不改任何时间的解析方式（各处现有的「无时区后缀按 UTC 解析」逻辑保持不变）。

### T5 输入区「图片」菜单组件 `frontend/components/ComposerImageMenu.tsx`（新文件）

```tsx
export type ImageMenuItem = {
  key: "see" | "generate" | "edit";
  label: string;
  description: string;
  disabled: boolean;
  title?: string;
  onSelect: () => void;
};
export default function ComposerImageMenu({ items, disabled = false, active = false }: { items: ImageMenuItem[]; disabled?: boolean; active?: boolean }): JSX.Element
```

- 触发按钮：`type="button"`，类名 `btn btn-quiet h-8 px-2 text-xs max-md:h-10`，内容 `<ImagePlus size={14} aria-hidden="true" />` + 文字「图片」（手机上也显示文字）。`aria-haspopup="menu"`、`aria-expanded`、`aria-label="图片：发图给 Chloe 看、生成图片或改一张图"`。`active` 时文字色 `text-[color:var(--ink)]`。`disabled` 或所有项都禁用时按钮禁用。
- 菜单：`role="menu"`，在触发按钮**上方**弹出（容器 `relative`，菜单 `absolute bottom-full left-0 mb-2 z-[60]`），宽 `w-[min(280px,calc(100vw-32px))]`，类名含 `ceramic-card p-1.5`，并设内联样式 `{ backdropFilter: "var(--bd)", WebkitBackdropFilter: "var(--bd)" }`（与站内其他浮层同法：原瓷片材质 + 背景模糊）。
- 每项：`<button type="button" role="menuitem">`，整行可点，`min-h-11 w-full rounded-[8px] px-3 py-2 text-left hover:bg-[color:var(--fill)] disabled:opacity-45 disabled:cursor-not-allowed`；第一行 `label`（`text-sm text-[color:var(--ink)]`），第二行 `description`（`text-xs text-[color:var(--ink2)]`）。禁用项用 `disabled` 并带 `title`。
- 交互：点触发按钮开关菜单；打开后焦点移到第一个可用项；`ArrowDown` / `ArrowUp` 在可用项之间循环；`Escape` 关闭并把焦点还给触发按钮；`Tab` 关闭；在菜单和按钮之外 `pointerdown` 关闭；选中某项先关闭菜单再调用 `onSelect()`（文件选择框必须在这次点击里同步触发，所以 `onSelect` 要在同一个事件处理函数里同步调用，不要放进 `setTimeout` / `requestAnimationFrame`）。
- 只用 React 与 `lucide-react`，不引入其他库。

### T6 合并后的语音按钮 `frontend/components/VoiceButton.tsx`（新文件）

```tsx
export default function VoiceButton({ disabled, dictating, holding, onTap, onHoldStart, onHoldEnd, holdDelayMs = 350 }: {
  disabled: boolean;      // 不可用
  dictating: boolean;     // 「轻点录音」进行中（对应页面里的 inlineRecording）
  holding: boolean;       // 「按住说话」进行中（对应页面里的 recording）
  onTap: () => void;      // 轻点：开始录音；录音中再轻点：结束并发送
  onHoldStart: () => void;
  onHoldEnd: () => void;
  holdDelayMs?: number;
}): JSX.Element
```

- 一个按钮，图标 `<Mic size={14} aria-hidden="true" />`，桌面另显示短字（`max-md:hidden`）：空闲「语音」、`dictating` 时「点此发送」、`holding` 时「松开发送」。类名 `btn btn-quiet h-8 px-2.5 text-xs max-md:h-10 max-md:w-10 max-md:px-0 select-none`，`dictating || holding` 时加 `text-[color:var(--rec)] bg-[color:var(--rec-soft)]`。
- `aria-label` 与 `title`：空闲「语音：轻点开始录音，再点一下发送；按住说话，松开发送」；`dictating`「正在录音，轻点发送」；`holding`「正在录音，松开发送」。
- 指针逻辑（用 ref 记状态，不靠 React state 计时）：
  - `onPointerDown`：禁用或非主键（`event.button !== 0`）直接返回；`event.preventDefault()`；`setPointerCapture`。若 `dictating` 为真，只记「这次按下用于结束录音」，不启动长按计时。否则启动 `holdDelayMs` 计时，到点时置「长按中」并调用 `onHoldStart()`。
  - `onPointerUp`：清计时、释放捕获。若处于「长按中」→ 复位并调用 `onHoldEnd()`；否则（短按）调用 `onTap()`。
  - `onPointerCancel` 与 `onLostPointerCapture`：清计时；若处于「长按中」→ 复位并调用 `onHoldEnd()`；短按被取消则什么也不调用。
  - `onClick`：仅当 `event.detail === 0`（键盘 Enter / 空格触发）时调用 `onTap()`；指针产生的 click 忽略，避免重复触发。
  - `onContextMenu` 里 `preventDefault()`（手机长按不弹系统菜单）。
  - 组件卸载时清计时。
- 首次提示：第一次因短按而**开始**录音时（调用 `onTap()` 那一刻 `dictating` 为假），若 `localStorage` 里没有 `chloe-voice-hint-v1`，就写入它，并在按钮上方显示一条 4 秒后自动消失的提示「也可以按住说话，松开就发送」（`role="status"`，`ceramic-card` 小气泡，`text-xs`，绝对定位在按钮上方）。`localStorage` 读写都包在 `try/catch` 里，失败就不显示，不报错。

### T7 输入区与抽屉整合 `frontend/app/page.tsx`、`frontend/app/globals.css`、`frontend/lib/chatModel.ts`

1. **图片入口**：在输入区工具行（`composer-tools`）里，删除原来非图片模式分支里的「上传参考图」按钮、它后面的竖线分隔（`<span aria-hidden="true" className="h-3 border-l ...`）、「生成图片」安静按钮，以及右侧动作区里单独的 `ImagePlus` 图标按钮；在工具行最前面放 `<ComposerImageMenu>`，三项：
   - `see`：「发图给 Chloe 看」，说明「Chloe 看图后回答」，`disabled` 与 `title` 沿用原 `ImagePlus` 按钮的条件与文案，`onSelect` = `fileInputRef.current?.click()`。
   - `generate`：「生成图片」，说明「用文字描述画一张新图」，`disabled` 沿用原「生成图片」按钮的条件，再加 `imageMode || hasReferenceImages`，`title` 沿用原文案，`onSelect` = `setImageMode(true)`。
   - `edit`：「改一张图」，说明「上传 1–3 张参考图，再说明怎么改」，`disabled` 与 `title` 沿用原「上传参考图」按钮，`onSelect` = `referenceFileInputRef.current?.click()`。
   - `active={imageMode || hasReferenceImages}`。
   - 两个隐藏的 `<input type="file">` 保留原样。图片模式（比例 chips、模型分组、「返回聊天」）与改图模式（「修改图片」chip、参考图 n/3、「全部取消」）原有的界面和行为**保持不变**，只是不再有那两个被删掉的按钮。「先移除待发送图片，即可切换生成模式」「正在读取图片…」这类提示保留。
2. **语音**：删除原来的「语音转文字」按钮和「按住说话」按钮，换成一个 `<VoiceButton>`：`disabled={conversationLoading || !currentConversation || isLoading}`、`dictating={inlineRecording}`、`holding={recording}`、`onTap={toggleInlineVoice}`、`onHoldStart={() => setRecording(true)}`、`onHoldEnd={() => { asrSessionRef.current += 1; setRecording(false); }}`。`toggleInlineVoice`、`recording` 相关的 effect、全局 mouseup 监听等逻辑不改。
3. **模型说明压缩**（`ChatModelFooter`）：
   - 在 `lib/chatModel.ts` 新增并导出 `modelDisplayName(id: string): string`：`claude-(opus|sonnet|haiku)-<主>-<次>` → `Claude Opus 5.5` 这样（首字母大写，版本用点连接）；`deepseek-v4-pro` → `DeepSeek V4 Pro`；`deepseek-flash` → `DeepSeek Flash`；其余原样返回。
   - 标签文字：自带模型启用时 `${modelDisplayName(config.model)} · 不扣草莓`，`title` 为完整信息 `聊天：${provider?.name ?? config.provider} · ${config.model}（自带 Key，不扣草莓）`；未启用时「平台模型 · 每条 10 颗草莓」（`title` 同文）。非聊天模式分支「每条消息消耗 10 颗草莓」不变。
   - 布局：标签、「思考 低/中/高」单选组、「改用平台 / 改用我的模型」按钮排成一行；空间不够时标签省略号截断（`min-w-0 truncate`，完整文字在 `title`），手机上也不要让标签自己占一整行。思考强度组和切换按钮的行为、键盘逻辑一字不改。
   - 「Enter 发送，Shift + Enter 换行」桌面保留、手机隐藏（现状）。
4. **手机输入区布局**（`globals.css` 里 `@media (width < 48rem)` 的 `.composer-inner` 网格及相关类）：非图片模式、无参考图时，输入釉片内只有两行：第一行输入框，第二行左边「图片」菜单按钮、右边语音按钮与「发送」。图片模式 / 改图模式下可以多一行放模式 chips 与模型分组，现有的 `composer-mode-exit` 位置保留。所有可点元素在手机上不小于 40×40px（现有 `max-md:h-10` 等约束保留）。
5. **抽屉嵌入防露缝**：给六个抽屉面板（`id` 为 `agent-drawer`、`exchange-drawer`、`plaza-drawer`、`settings-drawer`、`novel-drawer`、`studio-drawer` 的 `Glaze`）的 `className` 各加一个类名 `drawer-panel`（只追加，不改其他类）。在 `globals.css` 加：手机断点下（与现有写法一致，用 `:root:not([data-shell=desktop])` 限定）`.drawer-panel > .glaze-blur` 与 `.drawer-panel > .glaze-tint` 去掉 `mask-image`（含 `-webkit-`），`.drawer-panel > .glaze-lens` 不显示，`.drawer-panel > .glaze-tint` 背景用 `var(--glass2)`。桌面不变。
6. `page.tsx` 里的时间改造见 T4 表格。
7. **去掉两处默认粗体**：`page.tsx` 里有 2 处 `<b className="readout"`（手机页头的草莓余额、输入框下方「每条消息消耗 10 颗草莓」里的数字），`<b>` 自身带浏览器默认粗体；给这两处的 className 追加 `font-normal`（改成 `className="readout font-normal"`），其余不动。

### T8 设置页重复 key 与嵌入时的重复大标题

1. `app/settings/page.tsx`：`<ChatModelSection key={username} ...>` 改为 ``key={`chat-model:${username}`}``，`<LocalWatchSection key={username} ...>` 改为 ``key={`local-watch:${username}`}``。同文件里其他同级元素若也用 `key={username}` 一并改成带前缀的唯一 key。
2. **嵌入（抽屉）时隐藏页面自己的大标题**：以下页面 / 组件在嵌入状态下，把页面主标题 `h1`（「设置」「旧社交画像」「书斋」「分身」「广场」）加上 `sr-only`（保留给读屏，视觉隐藏），副标题与其他内容不变；非嵌入（独立页面）时完全不变：
   - `app/settings/page.tsx`（已有 `embedded`）
   - `app/profile/page.tsx`（已有 `embedded`）
   - `app/novels/page.tsx`（用 `useSearchParams().get("embed") === "1"` 判断，若该页已有判断就复用；注意本页若被 Suspense 包裹的约束，照现有写法）
   - `components/MyAgentWorkspace.tsx`（`embedded` 属性）
   - `components/AgentExchangeWorkspace.tsx`（`embedded` 属性）
   - 隐藏后，原本和 h1 同一行的按钮（如书斋的「新建一本」）仍要可见、位置合理（右对齐或放到副标题行右侧）。

### T9 新测试（每个文件放在 `backend/tests/` 下，文件名见白名单）

写法照抄 `backend/tests/test_claude_agent_frontend.py`：需要 Node 与 `typescript` 的用例，先用 `node -e "require.resolve(...)"` 检测，缺就 `pytest.skip` 并写明原因；另写不依赖 node 的源码断言，保证 CI（没有 `node_modules`）里也有覆盖。测试不得依赖 git 历史、不得读仓库外文件、不得联网。TS 模块用 `typescript` 的 `transpileModule` 转成 CommonJS 后在 node 里执行。

- `test_ui_polish_markdown.py`：至少覆盖——无序 / 有序列表（含 `1、` 无空格、`1.5 倍` 不是列表、`start` 取首项数字）、depth 1、列表后不缩进的行开始新段落、缩进续行并入上一项、标题三档映射、引用、围栏代码块（含未闭合）、分隔线、`**x**` 成 em、单个 `*` 与 `snake_case` 不变、行内代码、`typing: true` 时末尾未配对 `**` 被去掉而 `typing: false` 时保留、空串返回 `[]`、`stripMessageMarkdown`；源码断言：`MessageText.tsx` 不含 `dangerouslySetInnerHTML`、不含 `<a`、不含 `font-semibold|font-bold`；`ChatBubble.tsx` 的 AI 分支使用 `MessageText`。
- `test_ui_polish_beijing_time.py`：在**不同设备时区**下结果一致——用 `TZ=America/New_York` 与 `TZ=Asia/Shanghai` 两个环境变量各跑一次 node，断言 `formatBeijingTime(new Date("2026-10-22T01:56:24Z")) === "09:56"`、`beijingDateKey` 为 `2026-10-22`、`formatBeijingDateLong` 为 `2026年10月22日`、`beijingDayStart("2026-10-22").toISOString() === "2026-10-21T16:00:00.000Z"`、北京跨日边界（`2026-10-21T15:59:59Z` 与 `2026-10-21T16:00:00Z` 的 `beijingDayNumber` 相差 1）、非法日期返回空串不抛异常；`formatChineseDate` 按北京时间取日；源码断言：T4 表格里列出的文件不再含按设备时区显示日期时间的调用（用规格 T4 的 grep 正则，数字千分位的 `toLocaleString` 用排除规则放行）。
- `test_ui_polish_composer_controls.py`：`ComposerImageMenu` 与 `VoiceButton` 的源码断言（`role="menu"`、`role="menuitem"`、`aria-haspopup`、`Escape`、`ArrowDown`、`chloe-voice-hint-v1`、`event.detail === 0`、`onContextMenu`、无粗体类）；能跑 node 时，用 `react-dom/server` 渲染两种组件的空闲 / 录音状态，断言 `aria-label` 文案与「图片」文字；`VoiceButton` 的指针状态机若能在 node 里用假事件驱动就测：短按调 `onTap` 一次、长按超过 `holdDelayMs` 调 `onHoldStart` 后松开调 `onHoldEnd`、长按期间不调 `onTap`、`dictating` 时按下松开只调 `onTap`。
- `test_ui_polish_page_contracts.py`：`page.tsx` 不再含 `title="语音转文字"`、不再含 `aria-label="按住说话"`、不再含单独的 `>上传参考图<` 按钮文字；含 `<ComposerImageMenu`、`<VoiceButton`、`drawer-panel`（恰好 6 处）、`modelDisplayName(`、仍含 `改用平台`；`globals.css` 含 `.drawer-panel`；`lib/chatModel.ts` 的 `modelDisplayName` 映射（能跑 node 就执行断言 `claude-haiku-5-5 → Claude Haiku 5.5`、`claude-opus-5-5 → Claude Opus 5.5`、`deepseek-v4-pro → DeepSeek V4 Pro`、`deepseek-flash → DeepSeek Flash`、`qwen3.8-max → qwen3.8-max`）。
- `test_ui_polish_settings_drawers.py`：设置页不再有两个同级 `key={username}`（`ChatModelSection` 与 `LocalWatchSection` 的 key 各不相同且带前缀）；五个页面 / 组件在嵌入状态下给 h1 加 `sr-only` 的源码断言；`settings/page.tsx` 仍含 `LocalWatchSection`。

## 5. 验收标准（Claude 会在沙箱外逐条复跑）

运行环境：工作树里没有 Python 虚拟环境，后端测试用主仓库的解释器 `<Fiona 主检出>/backend/.venv/bin/python -m pytest`（在本工作树的 `backend/` 目录下运行）；`frontend/node_modules` 已就位，不要运行 `npm install` / `npm ci`。

1. `cd frontend && npx tsc --noEmit` 退出码 0。
2. `cd frontend && npm run lint` 0 个 error，warning 不多于基线的 25 个（基线 2026-10-26 在 `5985f43` 实测：0 errors, 25 warnings；`npx tsc --noEmit` 退出码 0）。
3. `cd frontend && npm run build` 成功。
4. `cd backend && python -m pytest -q` 全量：既有测试结果与基线逐条一致（基线由 Claude 另行记录），新测试全部通过，0 失败。
5. `git status --porcelain` 与 `git diff --name-only` 的改动集合 ⊆ §3 白名单；`package.json`、`package-lock.json` 零改动；`backend/` 下除新增的 5 个测试文件外零改动。
6. 全部新增 / 修改的前端代码里没有粗体：`git diff -U0 -- frontend | grep -E '^\+' | grep -E 'font-(semibold|bold|extrabold|black)|font-weight:\s*(6|7|8|9)00|<strong|<b[ >]'` 无输出。
7. `grep -rn 'dangerouslySetInnerHTML' frontend/components/MessageText.tsx frontend/lib/messageMarkdown.ts` 无输出。
8. 浅克隆验证：在 `git clone --depth 1` 的副本里（没有 `node_modules`）放入新测试与新源码，新测试全部通过或跳过，不得失败。
9. 界面实测（Claude 用浏览器截图验证，你只需保证实现符合 T1–T8）：
   - 带列表、编号、标题、`**强调**`、行内代码的 AI 回复按 T2 的样式显示，不出现原样的 `- `、`**`、`#`；打字过程中光标贴在最后一行末尾，不另起一行；
   - 手机 390×844 下，非图片模式的空闲输入釉片内只有两行控件，输入区（含模型说明、不含底部导航）高度明显低于改动前（改动前约 242px，目标 ≤ 180px；不得靠把可点元素缩到 40px 以下、或隐藏「改用平台」「思考强度」来凑）；
   - 只有一个麦克风按钮；「图片」菜单三项可用、键盘可操作；
   - 设置页「聊天模型」只出现一次，「本机监控」正常显示，控制台没有 duplicate key 报错；
   - 抽屉里不再出现与抽屉页眉重复的大标题；手机抽屉两侧不露底；
   - 聊天时间、会话列表、历史页按北京时间显示。

## 6. 执行方式（必须遵守）

- **用工作流（workflow 工具）并行**：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好。建议拆分（每行一个 agent，文件互不重叠）：
  1. A：T1 + T2 + `test_ui_polish_markdown.py`（新文件 `lib/messageMarkdown.ts`、`components/MessageText.tsx`）
  2. B：T3（`components/ChatBubble.tsx`、`app/history/page.tsx`）——按 T1/T2/T4 里写死的接口调用，不等 A、C 完成
  3. C：T4 的 `lib/beijingTime.ts`、`lib/chineseDate.ts`、`components/ConversationPicker.tsx`、`components/LocalWatchSection.tsx`、`app/plaza/page.tsx`、`components/AgentExchangeWorkspace.tsx`（含 T8-2 里它的那一项）+ `test_ui_polish_beijing_time.py`
  4. D：T5 + T6 + `test_ui_polish_composer_controls.py`（新文件 `components/ComposerImageMenu.tsx`、`components/VoiceButton.tsx`）
  5. E：T7（`app/page.tsx`、`app/globals.css`、`lib/chatModel.ts`，含 T4 表格里 `page.tsx` 的三处）+ `test_ui_polish_page_contracts.py`
  6. F：T8（`app/settings/page.tsx`、`app/profile/page.tsx`、`app/novels/page.tsx`、`components/MyAgentWorkspace.tsx`）+ `test_ui_polish_settings_drawers.py`
- 每个 agent 的任务说明必须**自包含**：把本规格里与它相关的章节（含 §2 全部约束、§2.1 字面片段、它负责的任务全文和接口签名）原文抄进去，并写明「不得调用 subagent / subagent_fork / workflow」「只许改动下列文件」。同一文件及其测试只归一个 agent。
- agent 失败时先读它的结果再决定，不许盲目重派。
- 主代理只做拆分、派发、汇总、白名单检查、跑 §5 第 1–7 条、写报告；全部 agent 完成后，主代理负责把 tsc / lint / build / pytest 跑绿（必要时在对应 agent 负责的文件内做最小修补，并在报告里写明）。
- 报告写到 `docs/tasks/2026-10-26-ui-polish/03-report.md`，开头列拆分表（如实列出全部派出过的 agent 与各自改动的文件），然后五项：1. 修改了哪些文件 2. 实现了哪些功能 3. 与 T1–T9 的逐项对应 4. 测试结果（tsc / lint / build / pytest 的原始摘要行） 5. 未完成或需要人工确认的地方。
