# 04 独立复核：手机对话页修缮（UI 复核第一批）

- 复核日期：2026-10-28
- 复核方：独立复核（全新上下文，无前置对话），模型 Opus 5.5
- 复核对象：工作树副本 `scratchpad/b1/review-b1`，基线 `58be576`，候选改动为 3 个已跟踪文件的未暂存修改 + 新测试 `backend/tests/test_mobile_chat_fix.py`
- 依据：`02-spec.md` v2、`03-report.md`、`verify/gate-record.md`、`verify/gate.sh`、`verify/measure.py`、调用方留在 scratchpad 的原始量测 `b1/{head,head2,cand}/measure.json`
- 限制：按调用方硬规矩，不用任何浏览器、不起服务器、不派子代理。视觉判据只审逻辑与数据一致性；变异实验全部在副本**之外**的隔离目录 `scratchpad/r1mut/` 进行（见 §3 说明）。

## 0. 任务书缺失说明

调用方指定的任务书 `docs/tasks/2026-10-28-mobile-chat-fix/04-review-brief.md` **在副本中不存在**。我在开工时发现缺失后挂了一个 10 分钟的等待（10:59–11:09），它一直没有出现；在 scratchpad 内也没有找到同名文件。按规矩我不进入 `Fiona/` 和 `.worktrees/` 去找。

因此本复核依据调用方消息里的补充硬规矩加上 `02-spec.md` v2 执行，输出按调用方要求的「结论 / 必须修复项 / 可优化项」三节组织。若任务书里另有点名要查的项目，需要补一轮复核。

## 1. 一致性声明

| 项 | 开始时 | 结束时 |
|---|---|---|
| `git diff HEAD \| shasum -a 256` | `e3c55cb43ab3186f8ca75da38802b2381d1bff81012f2bd7ae2ee88e2498b7fc` | `e3c55cb43ab3186f8ca75da38802b2381d1bff81012f2bd7ae2ee88e2498b7fc`（相同） |
| 与调用方快照 `b1/review-snapshot.patch` | 逐字节相同（`cmp` 通过，sha256 同上） | — |
| `git status --porcelain` | 3 个 ` M` + `?? backend/tests/test_mobile_chat_fix.py` + `?? docs/tasks/2026-10-28-mobile-chat-fix/` | 只多出本文件 `04-review.md`（目录级显示不变） |

本复核只新增了 `04-review.md` 一个文件，没有提交 git。`npm run build` 产出的 `frontend/.next/` 已被 `frontend/.gitignore` 忽略，`git status` 不受影响。

## 2. 机械复跑（§6 第 1–7 条）

| 判据 | 结果 |
|---|---|
| §6.1 `npx tsc --noEmit` | 退出码 0 |
| §6.2 `npm run lint` | 0 errors / 25 warnings；与 HEAD 基线（`b1/lint-head.txt`）逐条比对，除 `handleSend` 那条的行号 2193→2194 外完全相同 |
| §6.3 `npm run build` | 退出码 0（注意：`node_modules` 里装的是 Next **16.3.3**，见可优化项 2） |
| §6.4 定向 pytest | `499 passed`（492 条既有测试 + 7 条新测试）；新测试单跑 7 passed |
| §6.5 结构 grep，共 30 余项 | 全部等于规格期望值。awk 浮标位置检查的 d/b/c = 2587/2589/2592，退出码 0。`ChatScrollArea.tsx` 21–113 行的 diff 为空（两边都是 93 行）。hunk 头为 `-15,0` `-20` `-114,0` `-138`，都在规格允许的范围内 |
| §6.6 改动集合 | 只有白名单路径加规格目录；`git diff --stat` 不含 package/lock/next.config/`components/ui` |
| §6.7 桌面不变 | footer 区新增的 6 个 class 全部带 `max-md:` 前缀；`globals.css` 新增的 6 行都在 `:564` 开头的 `@media (width < 48rem)` 块内，且都带 `:root:not([data-shell=desktop])`。编译产物里 T3/T5 规则未分层（unlayered），包在 `@media not all and (min-width:48rem)` 内；`.max-md:pt-2` 排在 `.pt-3` 之后，所以手机上生效 |
| 不可见字符 / BOM | `page.tsx` 的 BOM（EF BB BF）与 HEAD 一致；4 个文件都没有 CRLF、NBSP、U+2060 或 U+200B |

执行方报告里两处「只改测试写法」的偏离，我核对后都属实，是规格 v2 的笔误：
- 固定的 effect 行本身就含两次 `onLatestVisibilityChange`，所以整个文件的计数必然是 4，不可能是 3。
- `ChatScrollArea.tsx:81` 的 `    return () => {` 含子串 `  return (`，用 `index("  return (")` 会先命中它，而不是组件顶层的 return。

## 3. 变异实验

`git checkout -- <file>` 会把那 3 个文件恢复到 HEAD，候选改动会一起丢掉，结束时的 diff 哈希就对不上了。为了同时满足调用方的两条规矩，我把 3 个源文件和新测试复制到 `scratchpad/r1mut/` 的同构目录里做变异；新测试以 `parents[2]` 定位仓库根，所以测的是这份副本。整个实验没有碰复核副本。

| 变异 | 结果 |
|---|---|
| 未变异 | 7 passed |
| 三个文件全换成 HEAD 版本（正控） | 5 failed / 2 passed（文案、不加粗两条在 HEAD 上本来就成立，属正常） |
| `overflow-clip` → `overflow-hidden` | 被测出 |
| 上报回调额外塞进 `updateButton` | 被测出 |
| 依赖数组只剩 `[showLatest]` | 被测出 |
| 旧按钮分支去掉 `renderLatestButton &&` | 被测出 |
| `renderLatestButton={true}` | 被测出 |
| 浮标搬进 `<ChatScrollArea>` 内 / 搬到 `</ChatScrollArea>` 与遮罩层 `</div>` 之间 / 搬到 footer 之后 | 三种都被测出 |
| 弹层 T5 选择器删掉 / tint 改成 `--glass` / 去掉 blur 选择器 / lens 规则挪出手机块 | 四种都被测出 |
| **`--composer-height` 不移到 `[data-chat-panel]`** | **存活**（这时浮标的 `bottom` 在计算值阶段失效，浮标会跳到面板顶上） |
| **浮标 `bottom` 偏移改成 +96px** | **存活** |
| **去掉浮标 `onClick`** | **存活** |
| **页脚行的 `max-md:mt-1 max-md:pt-1 max-md:text-[11px]` 不加** | **存活** |
| **footer 写成 `max-md:pt-2.5`** | **存活**（`"max-md:pt-2" in footer` 是子串判断） |
| **浮标加 `opacity-60` / 去掉 `absolute`** | **存活** |
| **T5 之后再追加一条带 `lipdk` 的同选择器规则** | **存活**（测试第 164–165 行断言的是常量 `T5_RULE`，恒真） |

这些存活项都不在规格 T6 要求的覆盖范围内，不算执行方违约，归入可优化项 1。

## 4. 逐项核对（T1–T7）

- **T1**：`chat-shell relative flex flex-col h-dvh overflow-clip`，其余 class 与顺序不变。编译产物生成了 `.overflow-clip{overflow:clip}`。`overflow:clip` 不形成滚动容器，程序和焦点都滚不动它；被裁掉的溢出也不计入祖先的可滚动区域。`.chat-shell` 本身是 flex 容器，不涉及 BFC 差异；外壳内没有 `position:sticky`。Tailwind v4 本身要求 Safari 16.4+，`clip` 的兼容性不成问题。没有新增 `scrollIntoView` 或 `preventScroll`。✅
- **T2**：`ChatScrollArea` 的接口、effect 原文、按钮分支都与规格逐字一致，21–113 行未动。`page.tsx` 侧的 state、两个 prop、变量迁移、浮标位置与 className 字面串也都与规格一致，`ArrowDown` 加进了现有的 lucide 引入。`.chat-message-layer` 上的 `--chat-content-bottom` / `--chat-message-mask` 是在该层上声明的，继承来的 `--composer-height` 在这里求值，迁移后仍然成立；仓库里没有其他读 `--composer-height` 的地方。✅（层级问题见必须修复项 1）
- **T3 / T5**：与规格逐字一致；`:530` 的 `border-radius:0` 保留；`:563–571` 原文未动。调用方量测（`cand/measure.json`）显示，候选的弹层与抽屉 `.glaze-finish` 只剩一个 radial 加 `inset 0 1px 0 lip`，弹层的 lens 为 `none`、tint 的 mask 为 `none`、背景等于 `--glass2`，昼夜都是如此。✅
- **T4**：footer 原位改成 `max-md:pb-1.5` 并追加 `max-md:pt-2`，`.composer-inner` 改成 `max-md:py-1.5`，页脚行追加三类。桌面的 `px-[18px] pb-3 pt-3`、`rounded-[14px]` 未动。量测：A 态 151→133（390 与 360 都是），B 态 175→157，桌面 135/147 不变；两行文字时 A 159、B 183。✅（C 态见必须修复项 2）
- **T6**：7 条测试覆盖了规格列出的各项，`balanced_block` 原样抄入，取块方式与既有测试相同，不依赖 git 历史，也不读仓库外文件。✅（强度不足见可优化项 1）
- **T7**：报告结构齐全，各项数值与我的复跑一致。✅

## 结论

**有条件通过：先修 2 项再合入。** 代码对 02-spec v2 的执行是逐字准确的，§6 第 1–7 条我全部复跑通过，桌面不变的静态证据也充分。但有两处问题挡在合入前：

1. 规格写死的浮标层级 `z-[3]` 带来一个新的交互回归：手机上浮标可见时，打开「图片」菜单，浮标会压在菜单上，并抢走一部分点击。这是规格层面的缺陷，执行方照做了。
2. 门禁记录里「状态 C」这一行与原始量测数据不符：候选从来没有在真正的 C 态下量过。这是验收证据的问题，不是代码缺陷。

其余全部是可优化项，不挡合入。

## 必须修复项

### 1. 浮标 `z-[3]` 压在「图片」菜单之上，抢走菜单项的点击（手机必现，窄桌面也会出现）

- **成因（静态推导，确定）**：输入釉片是 `absolute … z-[2]`（`page.tsx:2592`），形成了层叠上下文。`ComposerImageMenu` 的菜单是 `absolute bottom-full left-0 z-[60]`（`components/ComposerImageMenu.tsx:103`），被困在釉片的 z=2 层里。新浮标是 `[data-chat-panel]` 里与釉片同级的 `z-[3]`（`page.tsx:2588–2591`），所以会画在整个釉片及其弹出菜单之上。HEAD 的旧浮标在 `.chat-message-layer`（带 mask，z 为 auto）里面，始终低于釉片，从来不会盖住菜单。
- **几何（用调用方自己的实测坐标，390×844，A 态）**：
  - 浮标：y 599–639，高 40（手机上全局 `min-height:40px` 生效），x 约 149–241。
  - 「图片」按钮：top 707、x 从 22 起。
  - 菜单：底边 = 707 − 8 = 699；三项各约 52px，加 padding 与边框约 170px，所以菜单约占 y 529–699、x 22–302。
  - 结论：浮标落在第二项「生成图片」（约 y 588–640）的右侧三分之一。B 态时釉片更高，整体上移，但同样重叠。
- **用户可见的后果**：用户上滑看历史（浮标出现）后，点「图片」想生成图片。点到「生成图片」右半边时，`pointerdown` 落在浮标上，触发菜单的外部点击关闭（`ComposerImageMenu.tsx:40–46`），同时 click 触发回到最新。结果是菜单关掉、页面跳到底部，图片没生成。即使不点，视觉上也是一枚浮标叠在打开的菜单上。
- **窄桌面**：桌面浮标与菜单的竖向范围同样重叠。按 `--rail-w`=84、目录宽 288 推算，约 1024–1100px（目录常驻时）和约 768–820px 宽度下，横向也会重叠。1440 下不重叠。
- **建议修法**：把浮标 className 里的 `z-[3]` 改成 `z-[1]`。这样它仍高于遮罩层（z auto），低于釉片和页头（z-2）；浮标本身离釉片上沿 12–16px，不会被釉片的盒子或阴影盖住。需要同步做三件事：
  - 改规格 v2.1 里写死的 className 字面串；
  - 在 `test_mobile_chat_fix.py` 里加断言：浮标 class 含 `z-[1]`、不含 `z-[2]`/`z-[3]`；
  - 补一次实测：上滑 300px → 打开「图片」菜单 → `document.elementFromPoint(195, 619)` 应落在 `[role=menuitem]` 内，而不是 `.chat-latest`。另外要复核浮标在关闭菜单时仍然可见、可点。

### 2. 「状态 C」未实测，门禁记录的 C 行与原始数据矛盾（验收证据，须补测并更正）

- **原始数据**：
  - `b1/cand/measure.json` 里，候选的 `C-day-m390` / `C-day-d1440` 页脚按钮只有「改用我的模型」，没有「思考 低/中/高」和「改用平台」，与 B 态完全相同。
  - 同文件的 `byokSetup` 里，PUT `/api/chat-model` 返回的是 `"enabled":false`。
  - 原因：`measure.py` 构造 C 态只发了一次 PUT。`backend/byok/store.py:173` 会沿用旧记录的 `enabled`，而同一测试账号在先跑的 HEAD 流程里已经被 PATCH 成 `enabled:false`。
  - 只有第一次 HEAD 跑（`b1/head/measure.json` 的 `C-day-m390`，175px）是真正的 C 态；所有 1440 的「C」都是 B。
- **影响**：`gate-record.md` 表里「状态 C：390 175/157、1440 147/147」中，候选的两格和 HEAD 1440 那格实际都是 B 态数据。§6.8 要求的 C 态四项（「思考」三枚 radio 可见、高度 ≥40、整体落在釉片内、空闲高度 ≤ HEAD−12）都没有被验证过。按代码推断，C 态同样减 18px，结论大概率成立，但不能写成「已实测」。
- **建议**：在 `measure.py` 构造 C 态时，PUT 之后显式 PATCH `{"enabled": true}`，并断言页脚出现 `role=radiogroup` 和「改用平台」，再量 HEAD 与候选的 390 和 1440。量完后更正 `gate-record.md`；`verify/results/*-measure.json` 若入库，也要换成新数据。

## 可优化项

1. **新测试的强度**（§3 中的存活项）。建议补以下断言：
   - `[data-chat-panel]` 那一行含 `"--composer-height"`，且 `className="chat-message-layer …"` 那一行不含它。这一条最重要：一旦回退，浮标会跳到面板顶上，现有测试全绿。
   - 浮标 class 含 `absolute`、两个 `bottom-[calc(var(--composer-height)…)]` 的偏移量，以及 `onClick={() => chatScrollRef.current?.scrollToLatest()}`，且不含 `opacity-`。
   - 页脚行（`border-t border-[var(--carve)] pt-2` 那一行）含 `max-md:mt-1 max-md:pt-1 max-md:text-[11px]`。
   - footer 的 pt/pb 改用 `(?![\d.])` 一类的边界正则，避免 `max-md:pt-2.5` 混过去。
   - 第 164–165 行改为对 block 本身断言，例如所有 `.glaze-finish` 选择器所在的规则体都不含 `lipdk`，而不是断言常量。
2. **依赖与锁文件不一致**：副本（以及执行方报告里的构建输出）的 `frontend/node_modules` 是 9 月 21 日的旧安装，`next` 和 `eslint-config-next` 都是 16.3.3，而 HEAD 的 `package.json`/lockfile 已锁定 16.4.3（上一单 c87958f 升级）。tsc、lint、build 以及调用方的无头量测都跑在 16.3.3 上。本单只改 CSS/JSX，风险低，但建议合入前在与 lockfile 一致的环境（`npm ci` 之后）重跑一次 `npm run build`。
3. **抽屉像素判据的替代**：门禁用计算样式代替了规格写的抽屉像素判据，理由是设置抽屉 y≈780 有内容 chip 的边框（候选 19.3 对 HEAD 19.1，确实被内容污染）。计算样式本身更强，我接受这一替代；但它没有满足「HEAD 先失败一次」这条正控要求。可以换一个底部留空的抽屉，或把设置抽屉滚到空白处再量一次。另外，1440 下抽屉 `.glaze-finish` 与 HEAD 逐字相同这一条，门禁只给了静态证据；静态上确实成立（规则只在手机块内），补一次实测更稳。
4. **P1-1 只有探针证据**：无头环境复现不出 HEAD 的「页头被顶上 40px」，门禁改用「外壳能否被程序滚动」做探针（HEAD 40，候选 0）。按 CSS 规范，`overflow:clip` 禁止一切滚动，这个探针是可靠的代理指标；但按「先在用户操作路径上复现」的惯例，建议在真机或浏览器面板上照原路径（点文本框，再点「图片」）各走一遍 HEAD 和候选。
5. **浮标底色半透明**：`--mount` 是 rgba 0.70（昼）/ 0.72（夜），门禁的「不透明」只量了元素的 `opacity`。现有截图里看不出透字；如果实机上看到背后正文透出，可改用不透明的 token。
6. **旧浮标分支成了死代码**：`ChatScrollArea` 唯一的使用方已传 `renderLatestButton={false}`，旧按钮分支在应用里不会再渲染。规格要求保留，属有意为之；以后可以另开单清理，或在注释里说明保留原因。
7. **键盘焦点丢失**（既有行为，非回归）：用键盘激活浮标后浮标被卸载，焦点会掉到 `body`。可以考虑在 `scrollToLatest()` 之后把焦点交给消息视口或文本框。
8. **规格模板的两处笔误**：`count == 3` 和 `index("  return (")`（见 §2）。建议在 02-spec 修订记录里注明已按 4 / `"\n  return ("` 执行，避免下一单照抄。

## 第二轮复核（R1）

- 日期：2026-10-28 11:27 起；同一副本 `scratchpad/b1/review-b1`，已套上 R1 返修
- 范围：只核首轮两项必须修复项。新发现只写进本节末尾的「可优化项（新发现）」，不改变结论。
- 依据：`05-fix-r1.md`、`03-report.md` §8、`02-spec.md` v2.1 修订记录、`verify/measure.py`、`verify/results/{head,cand}-measure.json`、`verify/gate-record.md`，以及原始量测 `b1/head4/measure.json`、`b1/cand2/measure.json`

### 结论

**通过。** 两项必须修复项都已落实，证据与数据一致：
- 浮标层级已改为 `z-[1]`，新测试能拦住改回 `z-[3]`/`z-[2]`；
- 状态 C 在 HEAD 和候选两端都是真 C 态，门禁表的 C 行与 JSON 一致。

### 两项逐条核验

#### 必须修复项 1：浮标层级 `z-[3]` → `z-[1]`

| 核验点 | 实际值 | 期望 | 证据 |
|---|---|---|---|
| 浮标 className 的层级 | `z-[1]` | `z-[1]` | `page.tsx:2589` |
| 其余字符不变 | 与首轮 diff 相比只有这一行 `z-[3]`→`z-[1]` 不同（外加 index 行的 blob 哈希） | 只改 z | `diff <(首轮 diff-now.patch) <(git diff HEAD)` 只输出这两处 |
| `grep -c 'z-\[1\]' page.tsx` / 浮标行含 `z-[3]` 的计数 | 3 / 0 | ≥1 / 0 | 本轮复跑 |
| 新测试：含 `z-[1]`，不含 `z-[2]`/`z-[3]` | 已断言 | 已断言 | `test_mobile_chat_fix.py:137–139` |
| R1-2 第 1 条其余断言：含 `absolute`、桌面与手机两档 `bottom-[calc(…)]`，不含 `opacity-` | 已断言 | 已断言 | `:140–143` |
| R1-2 第 2 条：`{showLatestPill && <button` 到第一个 `</button>}` 的片段同时含 `chat-latest` 与 `onClick={() => chatScrollRef.current?.scrollToLatest()}` | 已断言 | 已断言 | `:152–157` |
| R1-2 第 3 条：`data-chat-panel` 行（恰好 1 行）含 `"--composer-height"`；`chat-message-layer` 行（恰好 1 行）不含 | 已断言 | 已断言 | `:159–164` |
| R1-2 第 4 条：页脚行恰好 1 行，且含 `max-md:mt-1`/`max-md:pt-1`/`max-md:text-[11px]` | 已断言 | 已断言 | `:220–227` |
| R1-2 第 5 条：footer 的 `max-md:pt-2(?![\d.])` 与 `max-md:pb-1\.5(?![\d.])` 边界正则 | 已断言，原有 `in` 断言也保留 | 已断言 | `:214–215` |
| R1-2 第 6 条：对手机媒体块里每条 `.glaze-finish` 规则的规则体断言不含 `lipdk`、不含 `linear-gradient`、含 `inset 0 1px 0 var(--lip)`，且有 `assert finish_rules` 防止空集通过 | 已断言（对规则体，不对常量） | 已断言 | `:189–194` |
| 只增不减 | 与首轮测试文件相比只有新增行，7 个测试函数不变 | 只增不减 | `diff r1mut/…/test_mobile_chat_fix.py backend/tests/test_mobile_chat_fix.py` 全是 `>` 行 |
| 测试结果 | 新测试 7 passed；定向集合 499 passed | 全绿，≥499 | 本轮复跑 |
| 实测探针 | 候选 `A-day-m390` / `A-night-m390` 的 `pillUnderMenu` 为 `inMenu=true`、`isPill=false`，命中元素是菜单项描述 `block text-xs text-[color:var(--ink2)]`，`menuOpen=true`；探针点是浮标中心（`PILL_JS` 的 `left` 取的是 `r.left + r.width/2`） | inMenu=true、isPill=false | `verify/results/cand-measure.json`；与原始 `b1/cand2/measure.json` 逐项一致 |

1440 下候选 `pillUnderMenu` 为 `isPill=true`。这是预期结果：1440 下浮标居中，菜单靠左，探针点不在菜单范围内（首轮已推算 1440 不重叠）。门禁表标的是「不要求」，与数据一致。

#### 必须修复项 2：状态 C 证据

| 核验点 | 实际值 | 期望 | 证据 |
|---|---|---|---|
| `measure.py` 在 PUT 之后显式 PATCH `{"enabled": true}` | 是 | 是 | `verify/measure.py:241` |
| 检查页脚出现 `role=radiogroup` 与「改用平台」 | 在 C 态测量前做 DOM 检查，结果写入 `byokSetup[].c_state_check`（**只记录不中断**，见可优化项 a） | 断言为真 | `measure.py:244–245` |
| 原始数据里 PUT / PATCH 的返回 | 两端 PUT 都返回 `"enabled":false`；随后的 `patch_enable` 返回 `"enabled":true` | 进入真 C 态 | `b1/head4/measure.json`、`b1/cand2/measure.json` 的 `byokSetup` |
| `c_state_check` | HEAD 与候选的 m390、d1440 四处全部 `{"radiogroup": true, "toPlatform": true}` | 两端为 true | `verify/results/head-measure.json`、`cand-measure.json` |
| `C-day-m390` 的 footerButtons | HEAD 与候选都是 `低 40 / 中 40 / 高 40 / 改用平台 40` | 四枚 40px | 同上 |
| `C-day-d1440` 的 footerButtons | 两端都是 `低/中/高/改用平台` 各 28px | 桌面档 | 同上 |
| C 态空闲高度 | HEAD 175 / 147；候选 157 / 147 | 候选 ≤ HEAD−12（163）；桌面不变 | 同上 |
| `gate-record.md` 的 C 行 | 「HEAD 175 / 147，候选 157 / 147」，页脚写明「思考 低/中/高 + 改用平台」 | 与 JSON 一致 | `verify/gate-record.md` 实测对照表 |
| 汇总 JSON 与原始 JSON | `head4`→`head-measure.json`、`cand2`→`cand-measure.json`：所有 run 的 composer、footerButtons、pillUnderMenu、twoLines、shellScrollable 逐项比对，0 处不符 | 一致 | 本轮脚本比对 |
| B 态 | 两端页脚都是「改用我的模型」40px；候选 157 / HEAD 175 | — | 同上 |
| 重测依赖版本 | 结果文件的 `base` 字段标注「next 16.4.3」；`b1/main-npmci.txt` 记录 `npm ci` 后为 `next 16.4.3` | 16.4.3 | 只有标注与日志作证，本副本无法独立核实（见可优化项 d） |

### 变异记录

本轮按协调方要求在副本里**原位**临时改已跟踪源码。改之前把 `page.tsx`、`globals.css` 按字节备份到 `scratchpad/r1out/r2bak/`；每个变异跑完都按字节拷回，并校验 sha256 与备份一致。没有用 `git checkout`，因为它会连同候选改动一起恢复到 HEAD。新测试文件（未跟踪）全程没动。

| # | 改了什么 | 结果 | 变红的测试 |
|---|---|---|---|
| — | 未变异 | 7 passed | — |
| M1 | 浮标 `z-[1]` 改回 `z-[3]` | **变红** | `test_page_latest_pill_lives_outside_the_masked_layer`（`assert 'z-[1]' in classes`） |
| M2 | `--composer-height` 内联样式从 `data-chat-panel` 行挪回 `chat-message-layer` 那一行 | **变红** | 同上（`'"--composer-height"' in panel_lines[0]`） |
| M3 | 去掉页脚行的 `max-md:mt-1` | **变红** | `test_mobile_composer_uses_shorter_spacing`（`AssertionError: max-md:mt-1`） |
| M4 | 浮标 `z-[1]` 改成 `z-[2]` | **变红** | `test_page_latest_pill_lives_outside_the_masked_layer` |
| M5 | 去掉浮标的 `onClick={() => chatScrollRef.current?.scrollToLatest()}` | **变红** | 同上（pill_block 断言） |
| M6 | footer 的 `max-md:pt-2` 改成 `max-md:pt-2.5` | **变红** | `test_mobile_composer_uses_shorter_spacing`（边界正则返回 None） |
| M7 | T5 之后追加一条 `.drawer-panel > .glaze-finish { box-shadow:inset 0 -1px 0 var(--lipdk); }` | **变红** | `test_globals_css_mobile_modal_and_drawer_edges`（规则体含 `lipdk`） |

恢复后两份文件的 sha256 与备份一致，`page.tsx` 开头的 BOM（EF BB BF）仍在。首轮存活的 7 个变异里，本轮重做的 M2、M3、M5、M6、M7 已全部被拦住；M1、M4 是本轮新增的层级变异。

### 哈希核对

| 项 | 开始（11:27） | 结束 |
|---|---|---|
| `(git diff HEAD; cat backend/tests/test_mobile_chat_fix.py) \| shasum -a 256` 前 16 位 | `4ef00981f53ff71d`（与协调方给的一致） | `4ef00981f53ff71d` |
| `git diff HEAD \| shasum -a 256` | `39658b44cfb497d717cfe65c032c0a437c87e3dcac2273ad6e7d66ef3469baf3` | 同左 |
| 与 R1 快照 `b1/review-snapshot-r1.patch` | `cmp` 逐字节相同（快照 sha256 同上） | — |
| `git status --porcelain` | 3 个 ` M` + `?? backend/tests/test_mobile_chat_fix.py` + `?? docs/tasks/2026-10-28-mobile-chat-fix/` | 相同；本轮只在已有的 `04-review.md` 末尾追加了本节 |

### 可优化项（新发现，不影响结论）

a. **`c_state_check` 只记录不中断**：`measure.py:244–245` 把检查结果写进 JSON，但为 false 时脚本照样往下量，并且仍把这一轮标成 `C-day-*`。这次两端都为 true，结论不受影响；建议为 false 时直接 `raise`，或以非零码退出，避免再次把 B 态当成 C 态。
b. **层级探针缺正控**：`pillUnderMenu` 只在 `z-[1]` 的候选上跑过，没有在 `z-[3]` 的构建上证明它会返回 `isPill=true`。HEAD 的 `isPill=true` 是因为旧浮标根本不在菜单范围内，不能算正控。源码层面已有测试变异 M1 兜底，所以只是证据强度问题；下次可以临时用 `z-[3]` 构建跑一次探针，确认它会失败。
c. **窄桌面未探测**：1440 下探针点不在菜单内，量不到重叠；首轮推算可能重叠的 768–820px、1024–1100px 宽度没有实测。`z-[1]` 按层叠规则对这些宽度同样有效，补一个 1024 宽的探针更完整。
d. **16.4.3 只有标注作证**：本副本的 `frontend/node_modules` 仍是 9 月 21 日安装的 next 16.3.3，所以我无法在副本里独立复跑 16.4.3 的构建。原始 `measure.json` 里也没有记录 next 版本，只有汇总文件 `base` 字段的文字标注和 `b1/main-npmci.txt`。建议 `measure.py` 把 `next --version`（或页面响应头 / `package.json` 读到的实际版本）写进输出。
