# 02 规格：UI 复核收尾（第五批）

- 规格版本：v1.2（2026-11-02；v1.2 只改措辞：§5.6 末项与 §5.7 随 v1.1 的白名单同步为「三个既有测试文件」，由独立复核指出。）
- v1.1（2026-11-02；v1 派单后执行者在 T1 停下：`test_ui_polish_page_contracts.py:176` 锁住 `className="readout font-normal"` 恰 2 处，v1 漏查。v1.1 改三处：§3.1 白名单加该测试文件并只许改那一个数字；§5.6 `::backdrop` 按规则行计数；T5 cost_hint 的页脚行判据改成两行。其余不变。）
- 基线：`main` @ `bccbf9f`；工作分支 `feat/ui-closeout`（本工作树）
- 来源：`docs/tasks/2026-10-28-ui-review/01-audit.md` 待拍板第 4 条；第三批（`2026-10-28-empty-states`）复核留下的日期框键盘问题与三处测试盲区；第四批（`2026-10-30-design-system`）两轮复核的可优化项。
- 用户 2026-11-02 拍板：
  1. 费用提示只在**首次**与**余额低于 30** 时显示，低于 30 改朱色并带余额数字；
  2. 历史页日期 chip **接管键盘焦点**，原生日期框退出 Tab 序列；
  3. 书斋抽屉 0 本书时的 40px 空带**保留现状**，本批不动；
  4. 第三批的三处测试盲区补反例测试；
  5. 原生 `confirm()` 已在第二批全部换成 `useConfirm`，本批**不做**（11-02 复查：`window.confirm` / `confirm("…")` 为 0 处）。
- 级别：L2（组件行为、样式与测试，不改接口、数据模型、依赖）。全程不设中途确认。
- 执行者：dsh（DeepSeek Flash，max）；Claude 做门禁与真实浏览器实测；独立复核另派。

---

## 1. 产品目标

五件事：

1. **费用提示少打扰**（T1）：输入区底部那行「每条消息消耗 10 颗草莓」现在常显。改成只在该账号在本浏览器首次进聊天时显示一次、以及余额低于 30 时常显（朱色，带余额数）。平时这一行不渲染，手机空闲态少一行。自带模型那一行（模型名、思考档、改用平台）不变。
2. **日期 chip 可用键盘**（T2）：历史页「从 / 到」两枚 chip 下面是透明的原生日期框，键盘 Tab 会停在看不见的年 / 月 / 日分段上，直接键入会盲改。改成 chip 本身可聚焦、Enter / Space 打开系统日期选择器；原生框只接鼠标 / 触屏，退出 Tab 序列。不支持 `showPicker()` 的旧浏览器退回原生框：显出来并把焦点交给它，失焦后藏回去。
3. **遮罩只有一种写法**（T3）：13 个 `<dialog>` 里，2 个用 CSS 类带了旧版 Safari 兜底色，11 个用 Tailwind 变体 `backdrop:bg-[color:var(--scrim)]` 没有兜底。统一成一个公共类 `scrim-dialog`，昼夜各一条规则、都带兜底色。
4. **门禁补强**（T4）：F7 的类型词放行改整词匹配，并补抓 `.style.fontSize =` 与 `setProperty("font-size")`；T8 改成校验公共类并补三种坏样本；生成 CSS 测试的依赖探测补 `tailwindcss`。
5. **三处反例测试**（T5）：第三批的三条断言各有一种写坏的方式拦不住——日期框两个 aria-label 对调、隐私首段被包进 `{needsKey && <>…</>}`、开场按钮外层 `div` 加 `onKeyDown`。补三条能拦住的断言，每条带自检。

## 2. 现状事实（HEAD `bccbf9f` 实测；行号以 HEAD 为准）

### 2.1 费用提示（`frontend/app/page.tsx`）

- `:303` `function ChatModelFooter({ username, settingsOpen, chatMode, loading }: {…})`，props 没有余额。
- `:404–409`：
  ```tsx
  const label = config?.enabled
        ? `${modelDisplayName(config.model)} · 不扣草莓`
        : "平台模型 · 每条 10 颗草莓";
  const labelTitle = config?.enabled
        ? `聊天：${provider?.name ?? config.provider} · ${config.model}（自带 Key，不扣草莓）`
        : "平台模型 · 每条 10 颗草莓";
  ```
- `:410` `return <div className="flex min-w-0 flex-col items-end gap-1 max-md:w-full max-md:items-start xl:flex-1">`
- `:411` `{chatMode && config ? <div className="flex min-w-0 max-w-full items-center justify-end gap-x-2 gap-y-1 max-md:w-full max-md:justify-start xl:w-full xl:flex-nowrap">`
- `:412–414`：
  ```tsx
      {config.enabled
        ? <span className="min-w-0 truncate" title={labelTitle}>{modelDisplayName(config.model)}<span className="max-md:hidden"> · 不扣草莓</span></span>
        : <span className="min-w-0 truncate" title={labelTitle}>{label}</span>}
  ```
- `:415–435` 思考档 radiogroup（只在 Claude 时）；`:436–439` 「改用平台 / 改用我的模型」按钮（有 config 时总是渲染）。
- `:440` `    </div> : <span>每条消息消耗 <span className="readout font-normal">10</span> 颗草莓</span>}`
- `:441–446` 错误行 `{chatMode && error && <div …>…</div>}`；`:447` `  </div>;`。
- `:463` `const [strawberryBalance, setStrawberryBalance] = useState<number | null>(null);`，由 `:2448` 侧栏的 `onBalanceChange={setStrawberryBalance}` 更新；手机工具栏 `:2576` 与侧栏 `components/Sidebar.tsx:136` 已经在余额 < 30 时用 `var(--seal)` 显示数字。
- `:2778–2781`：
  ```tsx
                <div className="mt-2 flex min-w-0 items-center justify-between gap-3 border-t border-[color:var(--carve)] pt-2 text-fs-12 text-[color:var(--ink2)] shadow-[inset_0_1px_0_var(--etch)] xl:flex-nowrap max-md:mt-1 max-md:pt-1 max-md:text-fs-11">
                  <span className="shrink-0 max-md:hidden">Enter 发送，Shift + Enter 换行</span>
                  <ChatModelFooter key={username} username={username} settingsOpen={settingsOpen} chatMode={!imageMode && !hasReferenceImages} loading={isLoading} />
                </div>
  ```
- 文件开头有 UTF-8 BOM。
- 本地存储的键名惯例：`lib/localWatch.ts:145` `` `fiona_local_watch_notifications:${encodeURIComponent(username)}` ``。
- 既有测试锁住的字面量（一律不得改）：
  - `test_mobile_chat_fix.py:220–226`：恰好一行含 `border-t border-[color:var(--carve)] pt-2`，且该行含 `max-md:mt-1`、`max-md:pt-1`、`max-md:text-fs-11`；
  - `test_mobile_chat_fix.py:237–240`：`每条消息消耗 <span className="readout font-normal">10</span> 颗草莓` 恰 1 次；`"平台模型 · 每条 10 颗草莓"` 恰 2 次；`平台模型每条消息消耗 10 颗；自带模型聊天不扣` 恰 1 次；`Enter 发送，Shift + Enter 换行` 恰 1 次；
  - `test_ui_polish_page_contracts.py:160–170`：两条模板字面量、`"平台模型 · 每条 10 颗草莓"`、`改用我的模型` 都在。
- 第一批实测（`2026-10-28-mobile-chat-fix/03-report.md`）：390×844 空闲输入区高度，状态 A（平台模型）133px、B / C（自带模型）157px。

### 2.2 日期 chip（`frontend/app/history/page.tsx`）

- `:3` 已引入 `useState, useEffect, useRef, useMemo, Suspense`；`:6` `import { cn } from "@/lib/utils";`。
- `:85–87`：
  ```tsx
  const openDatePicker = (input: HTMLInputElement) => {
    try { input.showPicker(); } catch { /* 浏览器不支持或拒绝时，沿用原生点按 */ }
  };
  ```
- `:88` `const dayFace = (key: string) => (key ? formatBeijingDateLong(beijingDayStart(key)) || key : "不限");`
- `:217–230` 「从」chip、`:231–244` 「到」chip，结构相同（以「从」为例）：
  ```tsx
              <label className={cn("chip relative h-auto min-h-10 w-full justify-between gap-2 px-3 py-1.5 has-[:focus-visible]:outline has-[:focus-visible]:outline-1 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[color:var(--ink)]", dateFrom && "chip-on")}>
                <span aria-hidden="true">从</span>
                <span aria-hidden="true" className="readout text-fs-13 text-[color:var(--ink)]">{dayFace(dateFrom)}</span>
                <input
                  type="date"
                  aria-label="从（开始日期）"
                  value={dateFrom}
                  max={dateTo || "9999-12-31"}
                  onChange={e => { setDateFrom(e.target.value); setQuick("all"); }}
                  onClick={e => openDatePicker(e.currentTarget)}
                  onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDatePicker(e.currentTarget); } }}
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                />
              </label>
  ```
  「到」的差异：`aria-label="到（结束日期）"`、`value={dateTo}`、`min={dateFrom || undefined} max="9999-12-31"`、`setDateTo`、`dateTo && "chip-on"`。
- 既有测试 `test_empty_states_history_dates.py` 锁住的（一律不得改）：`showPicker(` 恰 1 次且形如 `try { input.showPicker(); } catch {`；`openDatePicker(e.currentTarget)` 恰 4 次、`onClick={e => openDatePicker(e.currentTarget)}` 恰 2 次；`e.key === "Enter"` 与 `e.key === " "` 都在；四个 `has-[:focus-visible]:…` 片段都在；`aria-label="从（开始日期）"` / `aria-label="到（结束日期）"` 各恰 1 次；`className="absolute inset-0 h-full w-full cursor-pointer opacity-0"` **恰 2 次**；`<label className={cn("chip relative` **恰 2 次**；`type="date"` 恰 2 次；`aria-label=` ≥ 5 次；`dateFrom && "chip-on"` / `dateTo && "chip-on"` 各 1 次；`dayFace` 定义行逐字相同；不得出现 `toLocale*`、`getHours(` 等设备时区 API。
- `showPicker()` 支持：Chrome / Edge 99+、Firefox 101+、Safari 16+（含 iOS）。不支持时调用抛 TypeError；跨域 iframe 抛 SecurityError；没有用户手势抛 NotAllowedError。都走 catch。

### 2.3 对话框遮罩

- `frontend/app/globals.css:511–517`：
  ```css
  .image-preview-dialog { background:var(--hi); box-shadow:… }
  /* Safari 17.4 之前，::backdrop 取不到 :root 上的变量：var() 带上原来的遮罩色作兜底 */
  .image-preview-dialog::backdrop { background:var(--scrim, rgba(31,41,38,.18)); }
  .dark .image-preview-dialog::backdrop { background:var(--scrim, rgba(0,0,0,.45)); }
  .confirm-dialog { width:min(420px,calc(100vw - 32px)); … }
  .confirm-dialog::backdrop { background:var(--scrim, rgba(31,41,38,.18)); }
  .dark .confirm-dialog::backdrop { background:var(--scrim, rgba(0,0,0,.45)); }
  ```
  `--scrim` 定义在 `:303`（昼 `rgba(31,41,38,.18)`）与 `:305`（`.dark` 夜 `rgba(0,0,0,.45)`）。
- `backdrop:bg-[color:var(--scrim)]` 在 6 个字符串里，覆盖 11 个 `<dialog>`：
  | 文件 | 行 | 说明 |
  |---|---|---|
  | `components/SongProjectCard.tsx` | 340 | `<dialog>` 的 className |
  | `components/novel/NovelSettingsDialog.tsx` | 42 | 同上 |
  | `components/studio/QuoteDialog.tsx` | 45 | 同上 |
  | `components/studio/ShotCard.tsx` | 65 | 同上 |
  | `components/studio/BrainTrial.tsx` | 11 | `const dialogClass = "…"`，`:168`、`:182` 两个 `<dialog>` 用 |
  | `components/studio/SourceChoices.tsx` | 34 | `export const sourceDialogClass = "…"`，`BreakdownDialog:24`、`CreateProjectDialog:63`、`SourcePanel:65`、`EpisodePlan:25`、`novel/NovelFilmDialog:44` 五个 `<dialog>` 用 |
- 另外 2 个：`components/ConfirmDialog.tsx:142` `className="confirm-dialog"`；`components/GeneratedImage.tsx:170` `className="image-preview-dialog m-auto max-h-[94vh] max-w-[94vw] overflow-auto rounded-[8px] border p-0 text-[color:var(--ink)]"`。
- 全仓 `<dialog` 恰 13 处（上面 11 + 2）。
- `test_component_language.py:113` 要求 `ConfirmDialog.tsx` 含 `confirm-dialog` 字样（保留该类名即可）。
- 构建产物里 `backdrop:bg-[color:var(--scrim)]` 变成 `background-color:var(--scrim)`，Safari 17.4 / Chrome 122 / Firefox 120 之前的 `::backdrop` 取不到 `:root` 变量，遮罩透明。`var(--scrim, <兜底>)` 这种写法能退回兜底色；分两条声明的回退写法不行（第四批 R1 实测）。

### 2.4 门禁（`backend/tests/test_design_system_gate.py`、`test_design_system_css.py`）

- `:51–62` `TYPE_WORDS = ("number", "string", "undefined", "null", "boolean", "any", "unknown", "React.", "CSSProperties", "Property.")`。
- `:101–109` F7 规则：
  ```python
  re.compile(
      r"""(?<![\w$.-])(?:["']?(?:fontSize|font)["']?\s*:\s*(?P<val>[^,}\n]+)|fontSize\s*=\s*(?P<attr>"[^"]*"|'[^']*'|\{[^}]*\}))"""
  ),
  ```
- `:259–266` F7 命中后的放行：
  ```python
                  if rid == "F7":
                      val = (match.group("val") or match.group("attr") or "").strip()
                      val = val.rstrip(";").strip()
                      if re.fullmatch(r"""\{?\s*["'`]""" + FSVAR + r"""["'`]\s*\}?""", val):
                          continue
                      if val.startswith(TYPE_WORDS):
                          continue
                      if rel == "frontend/components/Seal.tsx" and val == '"30"':
                          continue
  ```
  `startswith` 是前缀匹配：`fontSize: anySize`、`fontSize: numberPx`、`fontSize: nullableSize ?? 14` 都会被放过。仓库当前 0 处这种写法；`el.style.fontSize = "14px"`、`style.setProperty("font-size", …)` 也是 0 处、也不在规则覆盖内。
- `:519–535` T8：收集 `globals.css` 里所有 prelude 以 `::backdrop` 结尾的块的 `background`，要求恰等于 2.3 列出的四条。断言名 `"T8 两个对话框的 ::backdrop 用 var(--scrim) 并带兜底色，昼夜各一条"`。
- `:592` 自检 F7 坏样本 `const style = { fontSize: 14 };`；`:617–624` F7 好样本三条（类型声明、JSX 属性、Seal.tsx 的 `"30"`）。
- `:658–721` `_selfcheck_token_css()` 的样本 CSS，`:708–711` 是上述四条遮罩规则。
- `:766–770` T8 自检：只有一种坏样本（四条兜底一起去掉）。
- `test_design_system_css.py:18` `REQUIRED_PACKAGES = ["@tailwindcss/node", "@tailwindcss/oxide"]`。`tailwindcss` 与 `tw-animate-css` 由 `globals.css` `@import` 引入；`tw-animate-css` 装着也会 `ERR_PACKAGE_PATH_NOT_EXPORTED`（第四批 R1 复核实测），**不能**加进探测，加了测试永远 skip；`tailwindcss` 可以。

### 2.5 第三批三处测试盲区

- `test_empty_states_history_dates.py:117–118` 只数两个 `aria-label` 各 1 次：两个值对调（「从」的标签挂到 `value={dateTo}` 的框上）拦不住。
- `test_empty_states_settings_privacy.py` `test_first_privacy_paragraph_is_outside_fold_before_switch_and_save`：只要求首段那一行以 `<p className={noteClass}>启用后，` 开头、下一行是 Claude 提示。把首段连同 Claude 提示一起包进上一行的 `{needsKey && <>` 和下一行的 `</>}` 拦不住。`ChatModelSection.tsx:324` 是第二个 `<fieldset`，`:345` 是首段，`:346` 是 Claude 提示；`:325–344` 之间的花括号成对（`{custom && <div …>` … `</div>}`、`{config && <div …>` … `</div>}`、单行的 `{needsKey && <p …>…</p>}`）。
- `test_empty_states_chat_openers.py` `OPENER_BUTTONS` 比对整个 `<button …>` 标签：给外层 `<div role="group" …>` 或 `<div data-chat-openers …>` 加 `onKeyDown` 拦不住。`page.tsx` 里这段（去掉行首空白后）是连续 6 行：
  ```
  <div data-chat-openers className="flex flex-col items-center gap-4 pt-8 text-center max-md:pt-4">
  <p className="text-fs-15 leading-[1.85] text-[color:var(--ink2)]" role="status">{`和 ${agent?.display_name || "你的分身"} 开始新的交流。`}</p>
  <div role="group" aria-label="开场" className="flex flex-wrap justify-center gap-2">
  <button type="button" className="chip min-h-10" … onClick={startChatOpener}>聊聊今天</button>
  <button type="button" className="chip min-h-10" … onClick={startDrawOpener}>帮我画一张…</button>
  <button type="button" className="chip min-h-10" … onClick={startPhotoOpener}>看看我拍的这张图</button>
  ```
  再下一行是 `</div>`。

### 2.6 基线数字

- 全量 pytest（沙箱外，清掉代理变量）：**7836 passed，0 skipped，0 failed**（第四批门禁在同一提交 `bccbf9f` 上实测）。
- `npx tsc --noEmit` 0 错误；`npm run lint` 0 错误、25 条警告；`npm run build` 通过。
- `grep -rn "backdrop:bg-" frontend/app frontend/components` 6 行；`grep -rn "scrim-dialog" frontend backend/tests` 0 行；`<dialog` 13 处。

## 3. 约束

### 3.1 白名单（只许改这些；其余文件一个字节都不许动）

改：
- `frontend/app/page.tsx`（T1，按字节读写、保留 BOM）
- `frontend/app/history/page.tsx`（T2）
- `frontend/app/globals.css`（T3）
- `frontend/components/ConfirmDialog.tsx`、`frontend/components/GeneratedImage.tsx`、`frontend/components/SongProjectCard.tsx`、`frontend/components/novel/NovelSettingsDialog.tsx`、`frontend/components/studio/BrainTrial.tsx`、`frontend/components/studio/QuoteDialog.tsx`、`frontend/components/studio/ShotCard.tsx`、`frontend/components/studio/SourceChoices.tsx`（T3，各只改 className 字符串）
- `backend/tests/test_design_system_gate.py`（T4，只许改 §4 T4 列出的几处）
- `backend/tests/test_design_system_css.py`（T4，只改 `REQUIRED_PACKAGES`）
- `backend/tests/test_ui_polish_page_contracts.py`（v1.1 加入：只许把 `test_page_readout_numbers_are_not_bold` 里的 `== 2` 改成 `== 4`。T1 第 6 条新增的两个余额数字和原来的「10」一样用 `readout font-normal`，这个计数因此从 2 变 4；该测试的本意是「readout 数字不加粗」，改计数不改本意。此外一个字节都不许动。）

新增：
- `backend/tests/test_ui_closeout_cost_hint.py`（T1 的测试）
- `backend/tests/test_ui_closeout_history_keyboard.py`（T2 的测试，含盲区 1）
- `backend/tests/test_ui_closeout_dialog_scrim.py`（T3 的测试）
- `backend/tests/test_ui_closeout_structure_guards.py`（盲区 2、3）
- `docs/tasks/2026-11-02-ui-closeout/impl/<A|B|C|D>.md`、`docs/tasks/2026-11-02-ui-closeout/03-report.md`

只读：本规格、`docs/tasks/**` 其余文件（含第四批的 `verify/**`，那是历史记录，T8 改了之后 `verify/ref/gate_rules.py` 跑不过是预期的，不要去改它）。

### 3.2 既有测试一字不许改

`backend/tests/` 下除 3.1 列出的两个文件外，任何既有测试的输入、断言、夹具都不得改。两个允许改的文件也只许改 T4 点名的位置。门禁逐函数比对。

### 3.3 字面量锁（§2.1、§2.2 列出的）

改完后这些计数必须原样成立。它们是既有测试的断言，不是本批的目标——本批的目标写在 §4。

### 3.4 UI 约束

- 沿用令牌：字号只用 `text-fs-*`；颜色写 `[color:var(--x)]`；新写的类不得触发 `test_design_system_gate.py` 任何规则。
- 界面文字不加粗；新文案不用「·」做分隔（既有字面量除外）。
- 朱色一律 `var(--seal)`。
- 不新增依赖，不改 `package.json`。

### 3.5 执行环境

- 沙箱是 workspace-write：可写的是本工作树和系统临时目录。
- `frontend/node_modules`、`backend/.venv` 已就位，不要重装，不要 `npm ci`。跑 npm / npx 前先 `export npm_config_cache=/tmp/fiona-npm-cache`。
- pytest 一律在 `backend/` 下这样跑：
  ```bash
  env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider …
  ```
  沙箱的 `NO_PROXY` 里有 `[::1]`，不清掉的话 httpx 在收集阶段就报 InvalidURL。
- 全量 pytest 约 5 分钟：用后台任务跑，等它结束再写结果。跑不完就照实写明，由 Claude 在沙箱外补跑。报告里不许留占位符。
- `app/page.tsx` 开头有 UTF-8 BOM，必须原样保留：不要用编辑工具改这个文件；T1 一律用脚本按字节读写（`open(path, "rb")` / `"wb"`，不要用 `utf-8-sig`）。改完用 `head -c 3 frontend/app/page.tsx | xxd` 确认仍是 `ef bb bf`。
- git 只许做读操作：status、diff、show、archive、log。

## 4. 任务

四个任务按文件互不重叠，可并行；T5 的三个盲区分别并进 T2（盲区 1）和独立任务 D（盲区 2、3）。

### T1 费用提示只在首次与低余额时显示（`frontend/app/page.tsx`）

1. 在 `ChatModelFooter` 之前的模块级作用域（`:303` 之前，和其他模块级常量放一起）加：
   ```tsx
   const costHintSeenKey = (username: string) => `fiona_cost_hint_seen:${encodeURIComponent(username)}`;
   /** 该账号在本浏览器首次进聊天时返回 true 并记下；浏览器存储不可用时按首次处理。 */
   function markCostHintSeen(username: string): boolean {
     try {
       const key = costHintSeenKey(username);
       if (localStorage.getItem(key) === "1") return false;
       localStorage.setItem(key, "1");
       return true;
     } catch { return true; }
   }
   ```
2. 签名改为：
   ```tsx
   function ChatModelFooter({ username, settingsOpen, chatMode, loading, balance }: {
     username: string; settingsOpen: boolean; chatMode: boolean; loading: boolean; balance: number | null;
   }) {
   ```
3. 在现有的 `useState` / `useRef` 声明之后加：
   ```tsx
     const [firstVisit, setFirstVisit] = useState(false);
     const firstVisitDecided = useRef<boolean | null>(null);
     useEffect(() => {
       if (!username) return;
       if (firstVisitDecided.current === null) firstVisitDecided.current = markCostHintSeen(username);
       setFirstVisit(firstVisitDecided.current);
     }, [username]);
   ```
   用 ref 记住判定结果，是为了 React 严格模式在开发环境把 effect 跑两遍时，第二遍不会因为第一遍已经写了存储而把首次判成 false。
4. 在 `const label = …` 之前加：
   ```tsx
     const lowBalance = balance !== null && balance < 30;
     const showCost = firstVisit || lowBalance;
     const hasContent = (chatMode && !!config) || showCost || (chatMode && !!error);
   ```
   `config` 是函数里已有的 `settings?.config`（按现有代码的写法取，不要另起名字）。
5. 把 `:2778–2781` 那一整行容器搬进组件：组件的 `return` 改为
   ```tsx
     return <div className={cn("mt-2 flex min-w-0 items-center justify-between gap-3 border-t border-[color:var(--carve)] pt-2 text-fs-12 text-[color:var(--ink2)] shadow-[inset_0_1px_0_var(--etch)] xl:flex-nowrap max-md:mt-1 max-md:pt-1 max-md:text-fs-11", !hasContent && "max-md:hidden")}>
       <span className="shrink-0 max-md:hidden">Enter 发送，Shift + Enter 换行</span>
       <div className="flex min-w-0 flex-col items-end gap-1 max-md:w-full max-md:items-start xl:flex-1">
         …原 :411–446 的内容，按第 6 条改…
       </div>
     </div>;
   ```
   `cn` 已在 `:26` 引入。容器那一行必须写在**一行**里（既有测试按行找它）。
6. 两处费用文字加 `showCost &&` 守卫，低余额时朱色并带余额：
   - `:412–414` 改为
     ```tsx
         {config.enabled
           ? <span className="min-w-0 truncate" title={labelTitle}>{modelDisplayName(config.model)}<span className="max-md:hidden"> · 不扣草莓</span></span>
           : showCost && <span className={cn("min-w-0 truncate", lowBalance && "text-[color:var(--seal)]")} title={labelTitle}>{label}{lowBalance && <>，还剩 <span className="readout font-normal">{balance}</span> 颗</>}</span>}
     ```
   - `:440` 改为
     ```tsx
         </div> : showCost && <span className={cn(lowBalance && "text-[color:var(--seal)]")}>每条消息消耗 <span className="readout font-normal">10</span> 颗草莓{lowBalance && <>，还剩 <span className="readout font-normal">{balance}</span> 颗</>}</span>}
     ```
   「改用平台 / 改用我的模型」按钮、思考档、错误行、`label` / `labelTitle` 两个常量都不动。
7. `:2778–2781` 四行替换为一行：
   ```tsx
                   <ChatModelFooter key={username} username={username} settingsOpen={settingsOpen} chatMode={!imageMode && !hasReferenceImages} loading={isLoading} balance={strawberryBalance} />
   ```
   缩进与原来 `<div …>` 那行相同。

行为判据（Claude 在真实浏览器里量）：
- 390×844、平台模型、非首次、余额 ≥ 30：底部那一行不渲染，空闲输入区高度 ≤ 115px 且 ≥ 100px（HEAD 133）；1440×900 桌面仍显示「Enter 发送，Shift + Enter 换行」，右侧没有费用文字。
- 同上但清掉 `fiona_cost_hint_seen:<用户>` 后刷新：显示「平台模型 · 每条 10 颗草莓」（墨色）；再刷新一次就不显示。
- 余额 < 30：显示「平台模型 · 每条 10 颗草莓，还剩 N 颗」，颜色 `--seal`；清掉存储键也一样。
- 自带模型（B / C）：行高与 HEAD 相同（157 ± 1）。
- 图片模式（`chatMode=false`）：非首次、余额 ≥ 30 时整行在手机上隐藏；首次或低余额时显示「每条消息消耗 10 颗草莓[，还剩 N 颗]」。

### T2 日期 chip 接管键盘焦点（`frontend/app/history/page.tsx`）

1. 在 `:43` `searchRef` 之后加：
   ```tsx
     const dateFromRef = useRef<HTMLInputElement>(null);
     const dateToRef = useRef<HTMLInputElement>(null);
     const [rawChip, setRawChip] = useState<"from" | "to" | null>(null);
   ```
2. `:85–87` 改为：
   ```tsx
     const openDatePicker = (input: HTMLInputElement) => {
       try { input.showPicker(); } catch {
         // 浏览器不支持或拒绝时退回原生日期框：显出来并把焦点交给它，失焦后藏回去
         setRawChip(input.dataset.chip === "to" ? "to" : "from");
         input.focus();
       }
     };
   ```
   `try { input.showPicker(); } catch {` 这一段的写法不能变（既有测试用正则锁住）。
3. 「从」chip `:217–230` 改为（`<label>` 开标签那一行**不变**）：
   ```tsx
               <label className={cn("chip relative h-auto min-h-10 w-full justify-between gap-2 px-3 py-1.5 has-[:focus-visible]:outline has-[:focus-visible]:outline-1 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[color:var(--ink)]", dateFrom && "chip-on")}>
                 <span aria-hidden="true">从</span>
                 <span aria-hidden="true" className="readout text-fs-13 text-[color:var(--ink)]">{dayFace(dateFrom)}</span>
                 <button
                   type="button"
                   aria-label={`从（开始日期）：${dayFace(dateFrom)}`}
                   onClick={() => { if (dateFromRef.current) openDatePicker(dateFromRef.current); }}
                   className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                 />
                 <input
                   ref={dateFromRef}
                   type="date"
                   aria-label="从（开始日期）"
                   aria-hidden="true"
                   tabIndex={-1}
                   data-chip="from"
                   value={dateFrom}
                   max={dateTo || "9999-12-31"}
                   onChange={e => { setDateFrom(e.target.value); setQuick("all"); }}
                   onClick={e => openDatePicker(e.currentTarget)}
                   onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDatePicker(e.currentTarget); } }}
                   onBlur={() => setRawChip(null)}
                   className={cn("absolute inset-0 h-full w-full cursor-pointer", rawChip === "from" ? "opacity-100" : "opacity-0")}
                 />
               </label>
   ```
4. 「到」chip `:231–244` 同样改：`dateToRef`、`` aria-label={`到（结束日期）：${dayFace(dateTo)}`} ``、`aria-label="到（结束日期）"`、`data-chip="to"`、`value={dateTo}`、`min={dateFrom || undefined} max="9999-12-31"`、`setDateTo`、`rawChip === "to"`。

为什么这样摆：按钮在前、原生框在后，原生框叠在上层，鼠标和触屏仍点到原生框（手机路径与 HEAD 完全一致）；按钮在 Tab 序列里，原生框 `tabIndex={-1}` 退出；按钮是 `<button>`，Enter / Space 原生触发 click，不需要再写 onKeyDown。原生框 `aria-hidden` 加 `tabIndex=-1` 是 axe `aria-hidden-focus` 认可的组合。原生框上的 `onKeyDown` 保留：鼠标点过之后它有焦点，Enter 可以再开一次选择器。

行为判据（Claude 实测）：
- 键盘：从搜索框 Tab 过来，焦点落在「从」按钮（`document.activeElement.tagName === "BUTTON"`，`aria-label` 含「从（开始日期）：」），chip 有墨线焦点框；再 Tab 落在「到」按钮；两个原生框都不在 Tab 序列里（整页 Tab 一圈，`activeElement` 从不是 `input[type=date]`）。
- Enter / Space 在按钮上：`showPicker` 被调用一次（打桩计数）。
- 鼠标点 chip：仍然是原生框收到 click 并调 `showPicker`（与 HEAD 相同）。
- 把 `HTMLInputElement.prototype.showPicker` 改成抛错后按 Enter：对应原生框 `opacity` 为 1 且有焦点；失焦后回到 0。
- 选定日期后按钮的 `aria-label` 变成「从（开始日期）：2026年11月2日」这类中文日期。

### T3 遮罩统一成 `scrim-dialog`

1. `globals.css:512–514` 与 `:516–517` 的五行（含注释）删掉，在 `.confirm-dialog { … }` 那一行（原 `:515`）之后加：
   ```css
     /* 所有 <dialog> 共用：Safari 17.4 之前 ::backdrop 取不到 :root 上的变量，var() 带上原来的遮罩色作兜底 */
     .scrim-dialog::backdrop { background:var(--scrim, rgba(31,41,38,.18)); }
     .dark .scrim-dialog::backdrop { background:var(--scrim, rgba(0,0,0,.45)); }
   ```
   `.image-preview-dialog { … }`、`.confirm-dialog { … }` 两条非遮罩规则不动。改完 `globals.css` 里 `::backdrop` 恰 2 处。
2. 六个字符串里的 `backdrop:bg-[color:var(--scrim)]` 原位替换成 `scrim-dialog`（位置不变，其余类不动）。
3. `ConfirmDialog.tsx:142` 改为 `className="confirm-dialog scrim-dialog"`；`GeneratedImage.tsx:170` 改为 `className="image-preview-dialog scrim-dialog m-auto …（其余不变）"`。
4. 改完：`grep -rn "backdrop:" frontend/app frontend/components frontend/lib` 0 行；`grep -rln "scrim-dialog" frontend/components` 8 个文件；13 个 `<dialog>` 的 className 都含 `scrim-dialog`（直接写在字符串里，或通过 `dialogClass` / `sourceDialogClass`）。

### T4 门禁补强（`test_design_system_gate.py`、`test_design_system_css.py`）

只改下面点名的位置；其他行、其他规则、其他自检样本不动。

1. **F7 整词匹配**：`:51–62` 的 `TYPE_WORDS` 换成
   ```python
   TYPE_WORD_RX = re.compile(
       r"(?:number|string|undefined|null|boolean|any|unknown|CSSProperties)(?![\w$])|React\.|Property\."
   )
   ```
   `:264` `if val.startswith(TYPE_WORDS):` 改为 `if TYPE_WORD_RX.match(val):`。`TYPE_WORDS` 不再保留。
2. **F7 补抓 DOM 写法**：`:101–109` 的正则改为
   ```python
   re.compile(
       r"""(?<![\w$.-])(?:["']?(?:fontSize|font)["']?\s*:\s*(?P<val>[^,}\n]+)|fontSize\s*=\s*(?P<attr>"[^"]*"|'[^']*'|\{[^}]*\}))"""
       r"""|\.style\.fontSize\s*=|\.setProperty\(\s*["']font(?:-size)?["']"""
   ),
   ```
   新增的两个分支没有命名组，`val` 取到空串，三个放行条件都不成立，自然计为命中。规则说明文字改为 `'行内 fontSize / font 的值必须恰为 "var(--fs-*)" 之一；禁止 .style.fontSize = 与 setProperty("font-size")'`。
3. **F7 自检**：`:617–624` 的 `good_f7` 加两条好样本：
   ```python
           ("frontend/components/SelfCheck.tsx", "fontSize?: string | number;"),
           ("frontend/components/SelfCheck.tsx", 'const size: React.CSSProperties["fontSize"] = "var(--fs-13)";'),
   ```
   并在它后面加坏样本断言（每条必须命中 F7）：
   ```python
       bad_f7 = [
           ("frontend/components/SelfCheck.tsx", "const style = { fontSize: anySize };"),
           ("frontend/components/SelfCheck.tsx", "const style = { fontSize: numberPx };"),
           ("frontend/components/SelfCheck.tsx", "const style = { fontSize: nullableSize ?? 14 };"),
           ("frontend/components/SelfCheck.tsx", 'el.style.fontSize = "14px";'),
           ("frontend/components/SelfCheck.tsx", 'el.style.setProperty("font-size", "14px");'),
           ("frontend/components/SelfCheck.tsx", "el.style.setProperty('font', '14px serif');"),
       ]
       for rel, text in bad_f7:
           assert _count_hits([(rel, text)])["F7"], f"自检失败：F7 坏样本没有命中：{text!r}"
       for rel, text in [
           ("frontend/components/SelfCheck.tsx", 'el.style.fontWeight = "500";'),
           ("frontend/components/SelfCheck.tsx", 'el.style.setProperty("--fs-x", "1");'),
       ]:
           assert not _count_hits([(rel, text)])["F7"], f"自检失败：F7 好样本被误伤：{text!r}"
   ```
4. **T8 改校验公共类**：`:519–535` 改为要求 `globals.css` 里 prelude 以 `::backdrop` 结尾的块恰好是这两个、各恰一条 `background`：
   ```python
       want_backdrop = {
           ".scrim-dialog::backdrop": "var(--scrim, rgba(31,41,38,.18))",
           ".dark .scrim-dialog::backdrop": "var(--scrim, rgba(0,0,0,.45))",
       }
   ```
   断言名改为 `"T8 所有对话框共用 .scrim-dialog::backdrop，用 var(--scrim) 并带兜底色，昼夜各一条"`。收集逻辑不变。
5. **T8 样本与自检**：`:708–711` 四行换成 T3 第 1 条的两行规则；`:766–770` 的自检改成五个坏样本，每个都要让 T8 为 False：
   - 两条兜底一起去掉（原样本）；
   - 只把 `.dark` 那条的兜底去掉；
   - 昼夜颜色对调；
   - 删掉 `.dark .scrim-dialog::backdrop` 那条；
   - 多一条 `.image-preview-dialog::backdrop { background:var(--scrim, rgba(31,41,38,.18)); }`（HEAD 的写法）。
   另加一条好样本控制：样本 CSS 原样时 T8 为 True。
6. `test_design_system_css.py:18` 改为 `REQUIRED_PACKAGES = ["@tailwindcss/node", "@tailwindcss/oxide", "tailwindcss"]`。

### T5 新测试

全部离线、只读仓库内源码、不依赖 git 历史、不读仓库外文件、不需要 node。写法沿用 `test_empty_states_*.py`：`ROOT = Path(__file__).resolve().parents[2]`，读文件用 `encoding="utf-8"`（`page.tsx` 带 BOM，读出来开头是 `﻿`，断言不受影响）。每个检查写成接收源码字符串的函数，真实测试调它，自检用改坏的副本调它并断言 `AssertionError`。

**`test_ui_closeout_cost_hint.py`**（HEAD 上必须失败）：
- `balance: number | null;` 恰 1 次；`balance={strawberryBalance}` 恰 1 次；`function markCostHintSeen(username: string): boolean {` 恰 1 次；`` `fiona_cost_hint_seen:${encodeURIComponent(username)}` `` 恰 1 次；
- `const lowBalance = balance !== null && balance < 30;`、`const showCost = firstVisit || lowBalance;`、`const hasContent = (chatMode && !!config) || showCost || (chatMode && !!error);` 各恰 1 次；
- `: showCost && <span className={cn("min-w-0 truncate", lowBalance && "text-[color:var(--seal)]")} title={labelTitle}>{label}` 恰 1 次；`</div> : showCost && <span className={cn(lowBalance && "text-[color:var(--seal)]")}>每条消息消耗 ` 恰 1 次；`，还剩 <span className="readout font-normal">{balance}</span> 颗` 恰 2 次；
- 含 `border-t border-[color:var(--carve)] pt-2` 的那一行恰 1 行，且含 `!hasContent && "max-md:hidden"`；它的下一行去掉首尾空白后恰等于 `<span className="shrink-0 max-md:hidden">Enter 发送，Shift + Enter 换行</span>`（v1.1：与 T1 第 5 条代码块一致，提示 span 在容器行的下一行）；
- `className="readout font-normal"` 恰 4 次（原 2 处 + 两个余额数字）；
- `<ChatModelFooter ` 恰 1 次且该行含 `balance={strawberryBalance}`；
- 源码开头仍是 `﻿`（BOM 没丢）。

**`test_ui_closeout_history_keyboard.py`**（HEAD 上必须失败）：
- `tabIndex={-1}` 恰 2 次；`data-chip="from"` / `data-chip="to"` 各 1 次；`ref={dateFromRef}` / `ref={dateToRef}` 各 1 次；`aria-hidden="true"` ≥ 6 次（四个 span 加两个框）；`` aria-label={`从（开始日期）：${dayFace(dateFrom)}`} `` / `` aria-label={`到（结束日期）：${dayFace(dateTo)}`} `` 各 1 次；`setRawChip(input.dataset.chip === "to" ? "to" : "from");` 与 `input.focus();` 都在 `catch {` 之后、`};` 之前；`onBlur={() => setRawChip(null)}` 恰 2 次。
- **盲区 1（配对）**：用正则 `<input\b.*?/>`（DOTALL）取出所有 `<input` 标签，其中含 `type="date"` 的恰 2 个；含 `aria-label="从（开始日期）"` 的那个必须同时含 `value={dateFrom}`、`data-chip="from"`、`ref={dateFromRef}`；含 `aria-label="到（结束日期）"` 的必须含 `value={dateTo}`、`data-chip="to"`、`ref={dateToRef}`。按钮不要用正则取标签（`onClick` 里有 `=>`）：按行检查——含 `` aria-label={`从（开始日期）：${dayFace(dateFrom)}`} `` 的那一行恰 1 行，它的下一行去掉首尾空白后恰等于 `onClick={() => { if (dateFromRef.current) openDatePicker(dateFromRef.current); }}`；「到」同理对应 `dateToRef`。
- 自检：把源码里两个 `aria-label="…"` 字面量互换后的副本必须让配对检查抛 `AssertionError`；把两个按钮的 `aria-label={…}` 互换也必须抛。

**`test_ui_closeout_dialog_scrim.py`**（HEAD 上必须失败）：
- 扫 `frontend/app`、`frontend/components` 下的 `.tsx`（跳过 `node_modules`、`.next`、`components/ui/`）。对每个 `<dialog` 标签，从 `<dialog` 起逐字符走，记录花括号深度与是否在 `"` / `'` / `` ` `` 字符串内，深度为 0 且不在字符串内时遇到的第一个 `>` 是标签结尾（标签里有 `=>`，不能用 `[^>]*`）。标签总数恰 13。
- 每个标签取 `className=` 的值：`"…"` 字符串按空白切分后必须含 `scrim-dialog`；`{标识符}` 则在全部扫描到的 `.tsx` 里找唯一的 `const 标识符 = "…"` 定义，其字符串按空白切分后必须含 `scrim-dialog`；没有 `className` 或找不到定义都算失败。
- `globals.css` 里 `::backdrop` 恰 2 处，且这两处的 prelude 恰为 `.scrim-dialog::backdrop` 与 `.dark .scrim-dialog::backdrop`。
- 全部 `.ts .tsx .css` 里正则 `(?<![\w-])backdrop:` 0 命中（`backdrop-filter:` 与 CSS 的 `::backdrop {` 都不会命中）。
- 自检：标签解析对 `` <dialog ref={r} onCancel={e => { if (b) e.preventDefault(); }} className="x scrim-dialog"> `` 要正确取到 className；坏样本 `className="m-auto backdrop:bg-[color:var(--scrim)]"` 要被判失败；`className={dialogClass}` 配 `const dialogClass = "m-auto scrim-dialog"` 要通过、配 `const dialogClass = "m-auto"` 要失败；正则对 `backdrop:bg-x` 命中、对 `backdrop-filter:blur(1px)` 与 `.a::backdrop {` 不命中。

**`test_ui_closeout_structure_guards.py`**（HEAD 上通过；自检必须能拦）：
- **盲区 2**：`ChatModelSection.tsx` 里以 `<p className={noteClass}>启用后，` 开头（去行首空白）的行恰 1 行；第二个含 `<fieldset` 的行在它之前；两者之间的所有行拼起来 `{` 与 `}` 个数相等，且没有任何一行去掉首尾空白后以 `&&`、`&& (`、`&& <>` 结尾。自检：在首段前一行插入 `{needsKey && <>`、在首段后第二行（Claude 提示之后）插入 `</>}` 的副本必须抛 `AssertionError`；把首段改成 `{needsKey && <p className={noteClass}>启用后，…</p>}` 单行的副本也必须抛（这一种既有测试已经能拦，仍写进自检作对照）。
- **盲区 3**：`page.tsx` 去行首尾空白后，存在恰 1 行等于 `<div data-chat-openers className="flex flex-col items-center gap-4 pt-8 text-center max-md:pt-4">`；它的下一行以 `<p className="text-fs-15 leading-[1.85] text-[color:var(--ink2)]" role="status">` 开头；再下一行恰等于 `<div role="group" aria-label="开场" className="flex flex-wrap justify-center gap-2">`；随后三行各以 `<button type="button" className="chip min-h-10"` 开头、分别含 `onClick={startChatOpener}`、`onClick={startDrawOpener}`、`onClick={startPhotoOpener}`；再下一行恰等于 `</div>`。自检：给 group 那行加 ` onKeyDown={noop}` 的副本必须抛；把第一个按钮包进 `<div onKeyDown={noop}>…</div>`（多出一行）的副本必须抛；给 `data-chat-openers` 那行加 `onKeyDown` 的副本必须抛。

## 5. 验收标准（执行者自跑；Claude 在沙箱外复跑并以自己的为准）

在工作树根目录：

1. `cd frontend && export npm_config_cache=/tmp/fiona-npm-cache && npx tsc --noEmit` → 退出码 0。
2. `cd frontend && npm run lint` → 0 错误；警告数 ≤ 25。
3. `cd frontend && npm run build` → 退出码 0。
4. `cd backend && <§3.5 的 pytest 命令>` 全量 → 0 failed，**0 skipped**，passed = 7836 + 本批新增用例数（报告里写明新增数与每个新文件的用例数）。
5. HEAD 对照（**必做**）：
   ```bash
   H=$(mktemp -d /tmp/fiona-head.XXXXXX)
   git archive HEAD | tar -x -C "$H"
   cp backend/tests/test_ui_closeout_*.py "$H/backend/tests/"
   cp backend/tests/test_design_system_gate.py backend/tests/test_design_system_css.py "$H/backend/tests/"
   cp -cR frontend/node_modules "$H/frontend/node_modules"
   cd "$H/backend" && <用本工作树的 backend/.venv/bin/python，按 §3.5 写法> -m pytest -q -p no:cacheprovider -rf tests/test_ui_closeout_*.py tests/test_design_system_gate.py tests/test_design_system_css.py
   ```
   期望：`test_ui_closeout_cost_hint.py`、`test_ui_closeout_history_keyboard.py`、`test_ui_closeout_dialog_scrim.py` 全部 FAIL；`test_ui_closeout_structure_guards.py` 全部 PASS；`test_design_system_gate.py::test_token_layer` FAIL（T8 对不上 HEAD 的四条），`test_selfcheck_source_rules`、`test_selfcheck_token_layer` PASS（自检不读仓库源码）；`test_design_system_css.py` PASS。失败原因都是 `AssertionError`，不许是 ImportError、FileNotFoundError 等。把 `-rf` 输出原文贴进报告。
6. 计数：
   ```bash
   grep -rn "backdrop:" frontend/app frontend/components frontend/lib | wc -l        # 0
   grep -rln "scrim-dialog" frontend/components | wc -l                              # 8
   grep -c "::backdrop {" frontend/app/globals.css                                    # 2（v1.1：按规则行数，T3 的注释里也含这个词，不算）
   grep -c 'className="absolute inset-0 h-full w-full cursor-pointer opacity-0"' frontend/app/history/page.tsx   # 2
   grep -c 'tabIndex={-1}' frontend/app/history/page.tsx                              # 2
   grep -c '"平台模型 · 每条 10 颗草莓"' frontend/app/page.tsx                          # 2
   head -c 3 frontend/app/page.tsx | xxd | head -1                                     # ef bb bf
   git status --porcelain                                                             # 只有 §3.1 的文件
   git diff --stat -- backend/tests                                                   # 只有三个既有文件：两个门禁文件 + test_ui_polish_page_contracts.py（2 +-）（v1.2 措辞同步）
   ```
7. 既有测试原样：`git diff HEAD -- backend/tests/test_design_system_gate.py` 的改动只落在 T4 点名的位置；`git diff HEAD --stat -- backend/tests/ ':!backend/tests/test_design_system_gate.py' ':!backend/tests/test_design_system_css.py' ':!backend/tests/test_ui_closeout_*'` 只含 `test_ui_polish_page_contracts.py | 2 +-` 一行（v1.2 措辞同步；v1.1 §3.1 授权的那一个数字）。

Claude 另做（不要求执行者）：真实浏览器里量 T1、T2 的行为判据；变异测试（T1 去掉 `showCost &&`、T2 去掉 `tabIndex={-1}`、T3 把一处 `scrim-dialog` 换回 `backdrop:bg-[color:var(--scrim)]`、T4 把 F7 整词匹配改回前缀，对应测试必须变红）。

## 6. 报告（`docs/tasks/2026-11-02-ui-closeout/03-report.md`）

1. 拆分表：派出过的全部 agent、各自负责的文件、是否成功。
2. 修改了哪些文件（与 `git status --porcelain` 一致）。
3. 实现了哪些功能，与 T1–T5 逐项对应。
4. §5 第 1–7 条的实际输出（原文，不改写、不省略计数）。
5. 未完成或需人工确认的地方。
6. 新增用例数与每个新文件的用例数。

每个 agent 结束前把自己做了什么、跑了什么、遇到什么写到 `docs/tasks/2026-11-02-ui-closeout/impl/<字母>.md`。

## 7. 何时停下来问

只有影响「实现什么」的问题才停下来，例如：
- 规格自相矛盾；
- §2 的某条事实在 HEAD 上对不上（行号偏移不算，内容对不上才算）；
- 按规格做会让 §3.1 之外的既有测试变红；
- 某条做不到。

只影响「怎么实现、怎么验证」的问题，自己决定，并在报告里写明理由。任何情况下都不回滚已完成的工作。**你实测到的事实优先于规格里的断言**，两者不符就停下来说明。

## 8. 执行方式

用工作流（`workflow` 工具）并行：在脚本里用 `parallel()` 同时运行四个 agent，按文件不重叠拆分；主代理只做拆分、派发、汇总、白名单检查、跑门禁和写报告。每个 agent 的任务说明自包含（agent 看不到你的对话），写明它负责的文件、要读的规格章节、以及「不得调用 subagent / subagent_fork / workflow」。不要把规格原文或正则转抄进工作流脚本，让 agent 自己读规格。

| agent | 任务 | 文件 |
|---|---|---|
| A | T1 + `test_ui_closeout_cost_hint.py` | `frontend/app/page.tsx`、新测试 |
| B | T2 + `test_ui_closeout_history_keyboard.py` | `frontend/app/history/page.tsx`、新测试 |
| C | T3 + T4 + `test_ui_closeout_dialog_scrim.py` | `globals.css`、8 个组件文件、两个门禁测试文件、新测试 |
| D | T5 盲区 2、3：`test_ui_closeout_structure_guards.py` | 新测试 |

A、B、C、D 之间没有文件重叠。四个都完成后，主代理跑 §5，写报告。agent 失败先读它的结果和已落盘改动再决定，不盲目重派。
