# 04 独立复核 R2：空态与文案（返修 R1 之后）

- 复核对象：基线 `f6adca6` + 返修 R1 后的候选改动（快照哈希 `7c4aa5ca5c3c3510`，与任务书、`verify/gate-record.md` 一致），规格 v1.2（重点 §10），返修单 `05-fix-r1.md` / `05-fix-r1-b.md`。
- 复核方式：§6 第 1–6 条全部在本副本亲自复跑（pytest 前照例清代理变量，规避沙箱 `NO_PROXY=[::1]` 的 httpx 环境问题）；第 7 条无浏览器，只审 `probe_r1.py` / `compare.py` v3 逻辑与 `results/*` 数据一致性；变异实验独立重做 19 个；报告与记录只当线索，逐条自证。
- R1 复核（`04-review.md`）的唯一必须修复项（03-report.md 两处占位符）已在本轮核验为**已修复**。

---

## 1. 结论

**通过**——返修单第一节 1–9 号与规格 §10 第 8 条 1–10 小项全部落实并有实证，§6 第 1–6 条全绿（155 项门禁 0 失败、7826 passed / 0 failed / 0 skipped、52 条新测试在 HEAD 上全部失败的正控成立），19 个变异全数被捕获，实测证据链自洽；无必须修复项，仅一处非回归的差异（page.tsx 的 UTF-8 BOM 在返修中被移除）列为可优化项。

## 2. 本轮必须修复项逐项核验

### 2.1 返修单第一节 1–9 号

| # | 要求 | 判定 | 证据 |
|---|---|---|---|
| 1 | `page.tsx`：`if (e.repeat) return;` 从第一行移到 `e.preventDefault();` 与 `handleSend();` 之间，函数体恰为 T3-3 的 8 行；其余一字不动 | **通过** | awk 提取 `handleKeyDown` 全函数，8 行与规格 T3-3 逐行一致（顺序：key 判断 → 注释 → isComposing → `e.preventDefault();` → `if (e.repeat) return;` → `handleSend();` → `};`）；规范化比对 `T3-3 verbatim: True`；gate v2 `PASS keydown block is exactly the v1.2 8 lines`；diff hunk `@@ -2223,6 +2237,7 @@` 仅 +1 行。实测佐证：`probe-r1.json` `holdEnterAfterTyping={chatPosts:1, valueAfter:''}`（v1.1 留 4 个换行），`cand-measure-r1.json` 开场 holdEnter `value` 恰为「聊聊今天」。page.tsx 其余 hunk 仍只有 T3 授权的 3 处（:959 注释、:1789 开场函数、:2608 空态）；`handleSend`/图片菜单 items 未触及（见 2.4 附带核验）。**例外发现**：文件头的 UTF-8 BOM 被移除（非行为回归，见第 6 节可优化项 1） |
| 2 | `NovelShelf.tsx` 页眉行加 `min-h-10` | **通过** | `NovelShelf.tsx:60` = `<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">`，恰 1 处（gate `PASS novel header row min-h-10 (v1.2) 1`）；旧串不存在（`test_novel_shelf_header_row_reserves_min_height` 断言并通过）。实测佐证：`probe-r1.json` 嵌入书斋说明文字 top 五个采样点恒为 80（v1.1 是 80→40→80→40） |
| 3 | `StudioShelf.tsx` 页眉行加 `min-h-10` | **通过** | `StudioShelf.tsx:70` 同款串恰 1 处（gate `PASS studio header row min-h-10 (v1.2) 1`；`test_shelf_header_reserves_height_...` 通过）。实测佐证：`probe-r1.json` 「在新页面打开」top 恒为 129（v1.1 是 89→129；HEAD 恒 131） |
| 4 | `history/page.tsx` 三处：dayFace 回退原值；「从」aria-label + max；「到」aria-label + min/max | **通过** | `:88` `const dayFace = (key: string) => (key ? formatBeijingDateLong(beijingDayStart(key)) || key : "不限");` 与 T7-2 v1.2 全等（测试 `DAY_FACE` 逐字断言）；`:222` `aria-label="从（开始日期）"`、`:224` `max={dateTo || "9999-12-31"}`、`:236` `aria-label="到（结束日期）"`、`:238` `min={dateFrom || undefined} max="9999-12-31"`；gate 8 条 history v1.2 判据全 PASS（含旧裸 aria-label = 0）。实测佐证：`probe-r1.json` 键入「20261027」后候选 `value='1027-02-02'`、日期面 `['从','1027年2月2日']`（不写「不限」），`labelFrom=labelTo=1`；HEAD 无 max 钳制得 `61027-02-02`，反证 `max="9999-12-31"` 真实生效 |
| 5 | `match/page.tsx` section className 换成 T4-3 v1.2 整串（`mt-10`→`pt-10`、`mobile:mt-2`→`mobile:pt-2`） | **通过** | `:349` 开标签与 T4-3 代码块逐字一致（规范化比对 `T4-3 section verbatim: True`）；gate `PASS match section padding not margin (v1.2)`；测试断言 classes 含 `pt-10`/`mobile:pt-2`、不含 `mt-10`/`mobile:mt-2`。实测佐证：`probe-r1.json` 820×360 候选 `ctaBottom=263 ≤ parentBottom=287`（v1.1 是 303 > 287），HEAD 无该 section 记「无」 |
| 6 | Claude 提示句改「你在聊天里发的图片」 | **通过** | `ChatModelSection.tsx:346` 与 T6-2 v1.2 逐字一致；gate `PASS claude-only disclosure line (v1.2 copy)`、`PASS old 本轮图片 copy gone (v1.2) 0`；测试 `CLAUDE_NOTE` 全等断言 + `"已选 Claude：本轮图片" not in source` |
| 7 | `useAccountIdentity.ts` 只换新代码开头注释为 T1-1 的两行，代码一字不动 | **通过** | `:60-62` 三行注释与 v1.2 T1-1 一致；整段追加块与 T1-1 代码块逐字比对 `verbatim match: True`；diff 删除行 = 0（gate `PASS lib diff has no removed lines 0`）；gate 3 条注释判据 PASS；`lib/auth.ts` 未动（gate PASS） |
| 8 | 9 个测试文件按 §10 第 8 条加固 | **通过** | 见 2.2 逐小项 |
| 9 | `03-report.md` 补「返修 R1」一节及两处精度修正 | **通过** | §8.1–§8.7 齐全（逐项对应表、拆分表 9 agent、门禁结果、16 变异表、精度修正、已知局限补 3 条、未完成项）；全文件 `grep '__[A-Z_]*__'` 为空——R1 复核的唯一必须修复项（`__PYTEST_RESULT__`/`__SKIP_NOTE__`）已由 Claude 补入实测数（§4 第 4 条：7813/0/0 并注明补入来源）；§8.5 两处精度修正经独立复核为准确：build 输出确为 19 行 Route；「社交画像（旧版）」在 §6-5 路径组内确为 **8 处、分布在 7 行**（match `:352` 1 处 + profile 3 行 4 处（`:136` 一行 2 处）+ 三份文档各 1——我 R1 复核报「7 处/6 行」系漏数 match 页 1 处，报告的修正是对的） |

### 2.2 规格 §10 第 8 条 1–10 小项（测试加固）

| 小项 | 判定 | 证据（测试文件:行为断言 → 变异验证） |
|---|---|---|
| 8.1 identity「找回失败」场景 | **通过** | `test_empty_states_identity.py:187-199` 新增 `settled_empty` 模式：用户名保持空串、恢复以空串落定；`:109-113` 订阅回调内同步 `getSnapshot()` 记入 `notifySnapshots`（模拟 React store 变化时重读快照）；`:286-295` 断言 initial=true、notified≥1、通知时快照全为 false、落定后快照 false。规格要求拦住的两种错误实现均被我的变异证实：MA（置位/通知对调）、MB（快照只看 `!getUsername()`）都使 `test_failed_recovery_with_empty_username_never_reports_pending` 变红 |
| 8.2 novel 四组断言 | **通过** | `test_novel_shelf_new_book_entry_sits_in_header_unless_the_shelf_is_empty`：0 本书时唯一 `/novels/new` 入口是 `EmptyState` 后代（祖先链检查 `:113-120`）、`<header>` 子树 0 个；有书默认数据、`env.failures.set('GET /api/novels',{status:500})` 出错态各一次 probe，`<header>` 内恰 1 个。`test_novel_shelf_pending_identity_settles_to_embedded_login_link`：mount 后 flush 前读 `identityPending=true`，flush（空串落定）后重挂为 false、内层出现「请登录后查看你的书架」、`login[0].props.target=='_top'`。`test_novel_shelf_header_row_reserves_min_height`：HEADER_ROW 恰 1 且旧串不存在。变异 MC/MD/MT 分别打红对应测试 |
| 8.3 接线整段子串（10 文件） | **通过** | novel `WIRING_BRANCHES`（3 文件）、studio `SHELF/WORKBENCH/KB_WORKBENCH_LOGIN_BRANCH`、agents `MY_AGENT/EXCHANGE/MEMORY/AGENT_CARD_WIRING`——我从三个测试文件提取全部 10 个子串常量逐一回查源码，**10/10 恰出现 1 次**；变异 ME（StudioWorkbench 换文案）打红 studio 接线测试 |
| 8.4 studio 三条 | **通过** | `SHELF_HEADER_ROW` 恰 1；非嵌入 probe 断言「新建项目」className **不含** `ml-auto`；直接挂 `AccountStudioWorkbench({id:'project',owner:'',embedded:false,identityPending:true})` 与 `AccountKbWorkbench({owner:'',embedded:false,identityPending:true})`，输出含「正在加载身份…」、不含「请登录后」。变异 MF/MG 打红 `test_shelf_header_reserves_height_and_non_embedded_button_is_not_right_aligned` |
| 8.5 chat_openers 精确化 | **通过** | `HANDLE_KEY_DOWN_LINES` 8 行逐行全等（`:153-160`）；三个开场函数压缩空白后与 T3-1 全等（`OPENER_BODIES`）；三个 button 压缩空白后与 T3-2 全等（`OPENER_BUTTONS`，排除额外 `onKeyDown` 等处理器）；`composeSongSection` 四行以字面量硬编码（`:79-83`，不读 git）用 `textwrap.dedent` 比对。变异 MH/MI/MJ 分别打红对应三条测试 |
| 8.6 match_profile 六条 | **通过** | 左栏 `<p …>双方都接受匹配后，对方会出现在这里</p>` 恰 1；`{rooms.length > 0 && <p className="mt-3">从「最近聊天」选一位` 在；正则 `\{pendingMatches\.length === 0 \? \(\s*<section data-match-empty` 紧接断言；开标签 classes 含 `pt-10`/`mobile:pt-2` 且不含 `mt-10`/`mobile:mt-2`；「暂无社交画像（旧版）」全等；三份文档各 ≥1 处新名（v1.2 放宽）。变异 MK 打红 padding 测试 |
| 8.7 settings_privacy 三条 | **通过** | 第一段所在行 strip 后以 `<p className={noteClass}>启用后，` 开头、以 `</p>` 结尾（`:74-82`）；下一行 strip 后精确等于 v1.2 `CLAUDE_NOTE` 且其位置早于「启用我的聊天模型」（`:84-86`）；`FOLD_ORDER` 七段位置升序断言（`:65-68`）。变异 ML/MM 分别打红两条测试 |
| 8.8 history_dates | **通过** | `showPicker(` 全文件恰 1 且在 `try {…} catch {` 内（正则）；`openDatePicker(e.currentTarget)` 恰 4、`onClick={e => openDatePicker(e.currentTarget)}` 恰 2；`max={dateTo || "9999-12-31"}`、`min={dateFrom || undefined} max="9999-12-31"}` 精确在且旧 `max={dateTo || undefined}` 不在；两个新 aria-label 各恰 1、旧裸标签 0；`dayFace` 行与 T7-2 v1.2 全等；设备时区 API 全文 0。变异 MN/MO/MP 分别打红三条测试 |
| 8.9 voice_hint | **通过** | 两处 `subprocess.run` 均 `timeout=60`（`:46`、`:61`），依赖探测遇 `CalledProcessError`/`TimeoutExpired` → `pytest.skip`（`:50-51`）；新增 `hintWhileDictating: renderWithHint(true, false, true)` 且断言取不到气泡（`:184`、`:196`）；测试自检 `timeout=60` 计数与 run 调用数相等（`:209-214`）。变异 MQ 打红 `test_voice_status_bubble_respects_first_use_hint` |
| 8.10 测试名名副其实 | **通过** | agents：改名 `test_agent_exchange_workspace_pending_identity_uses_local_loading_state`，并补真检查——`function LoadingState(` 恰 1 处 + 所有 import 语句不含 `LoadingState`（`:101-106`）；变异 MR（加一行 LoadingState 导入）打红该测试。settings：改名 `test_first_privacy_paragraph_is_outside_fold_before_switch_and_save`，不再声称「可见」，断言全部是源码位置关系；变异 ML 打红 |

### 2.3 R1 复核遗留项

- R1 唯一必须修复项（报告占位符）：**已修复**（见 2.1 第 9 行；`grep '__[A-Z_]*__'` 为空）。
- R1 可优化项 1（「18 个路由」「7 行」表述）：**已按实测修正**（§8.5，且修正后的数字经我独立复核为准确）。
- R1 可优化项 2（按住 Enter 插空行）：v1.2 已从根上修掉（返修单 1 号），实测输入框恰为「聊聊今天」/发送后为空。
- R1 可优化项 3（跨标签登出短暂登录提示）：已按规格 §10 写入报告已知局限（§8.6 第 5 条），并同步写进 hook 注释第二行。

### 2.4 附带核验（修复未越界）

- 未列入返修单的 14 个已改文件，diff hunk 头与 R1 复核时逐一相同（VoiceButton `@@ -147,6 +147,11`、ConversationPicker `@@ -88,7`、profile 三 hunk 等），未被波及。
- 既有测试仍只有 `test_ui_polish_settings_drawers.py` 1 增 1 删（`git diff --numstat HEAD -- backend/tests/`）；改动文件仍为同 22 个；`git status` 白名单外 0 条（gate `PASS changes outside whitelist none`）。
- `handleSend` 与图片菜单 items：page.tsx 的 hunk 不触及其所在区域，全量 7826 条（含两段 sha256 锁 `test_claude_agent_frontend.py:117-123`、`test_claude_agent_r1_frontend.py:137-145`）通过。
- 规格 v1.2 本身的审查（任务书第 3 条例外条款）：T3-3 新位置正确——repeat 事件在 `preventDefault()` 之后被拦，既不发送也不插空行，Shift+Enter 换行与 IME 组字路径都在守卫之前早退、不受影响（probe 数据 {1, ""} 佐证）；`dayFace` 对非法值走 `beijingDayStart` 的正则守卫返回 Invalid Date → `formatBeijingDateLong` 返回空串 → `|| key` 显示原值，无异常路径，且 `dateFrom/dateTo` 只能来自原生 date 输入或清空按钮；`max="9999-12-31"` 实测把 5 位年钳回 4 位；`pt-10` 改内边距是矮屏裁剪的正确修法（263≤287）；`min-h-10` 不影响独立页（h1 本身高于 40px）。未发现「照 v1.2 做会出问题」的条款。

## 3. §6 第 1–6 条复跑结果

| # | 判据 | 期望 | 实际（本副本） | 判定 |
|---|---|---|---|---|
| 1 | `npx tsc --noEmit` | 0 | 退出码 0 | 通过 |
| 2 | `npm run lint` | 0 errors、warnings ≤ 25 | `✖ 25 problems (0 errors, 25 warnings)` | 通过 |
| 3 | `npm run build` | 0 | `build exit=0`（next 16.4.3，19 行 Route） | 通过 |
| 4 | 全量 pytest | 0 failed、0 skipped、passed ≥ 7774+52 | **7826 passed, 0 failed, 0 skipped**（我方直跑 285.33s；gate 内复跑 287.36s；7826 = 7774 + 52，新测试收集 52 条） | 通过 |
| 5 | `verify/gate.sh` v2 | 155 项 0 失败 | **`== 汇总: 155 项，FAIL=0`**，退出码 0，`grep -c '^PASS'` = 155；脚本 sha `dc50f4fce0535a05` 与记录一致 | 通过 |
| 6 | 改动集合 | 白名单外 0 | `git status -uall` 63 条（22 修改 + 41 未跟踪），gate ALLOW 正则过滤后为空 | 通过 |

第 7 条（无浏览器，证据审计）：
- `compare.py` v3（sha `2d192f46c34483fe`）只比 v2 多判 holdEnter 的 `value == "聊聊今天"`；用 `results/head-measure-r1.json` + `cand-measure-r1.json` 本地重放 → **66 项、FAIL 0**，且 66 行表格与 `gate-record.md` §3 逐行逐字一致（mismatch=0）。HEAD 正控成立：HEAD 无开场 chip，`holdEnter` 键不存在 → 判「败」；计数器正控两边 `counterControl=1`。
- `probe_r1.py`（sha `1a891a191bb24251`）10 项判据逻辑审毕（页眉五采样点 top 值集合大小为 1、按住 Enter 只发 1 次且输入框为空、键入后日期面不含「不限」、`get_by_label("从"/"到")` 各 1、820×360 CTA 底边 ≤ 容器底边）；`results/probe-r1.json` 的 judged 20 行与 gate-record 表逐行一致（head 5 过 5 无、cand 10 过），关键原始值（80/129/{1,''}/1027-02-02/263≤287）与记录引用相符；HEAD 侧「无」的 5 项确因界面对象不存在（`face=None`、`section=False`），判法合理。「v1.1 副本上 10 项全部判失败」的正控无法在本副本直接复跑，但与 v1.1 已知行为（我方 R1 实测「聊聊今天\n\n\n\n」、80→40 跳动、303>287、不限）逐项吻合，采信。
- `measure.py` sha 仍为 v2 `03bdf7cc273932cf`，R1 全量重跑，故隐私 `rendered/boxed` 直接在主 JSON 里（cand closed `[T,F×7]`/`[T×8]`、head `details=None`），compare 无需 v2 覆盖参数；`extra_probe.py` sha `0703793fb414d9b2` 与 R1 相同，`extra-probe-r1.json`：小说关闭时三个路径两种宽度「小说工坊尚未开放」`{all:1,visible:1}`、无残留 pending/login 文案（两侧相同），工作室 h1 候选 1×1、HEAD 174×42、roleCount 均 1。
- HEAD 正控（新测试）：`results/head-newtests-r1.txt` **52 failed / 0 passed**、无收集/导入错误，按文件分布 4+6+4+6+6+14+4+5+3 = 52，与本副本 `--collect-only` 的每文件条数完全一致——每个新测试函数都含 HEAD 上失败的断言。
- gate v2「比 v1 新增 15 项判据、v1.1 副本上恰好这 15 项失败」：155 = 143 + 净增 12；带 `(v1.2)` 标记的 18 行里，`showPicker( 恰 1`、`openDatePicker ×4`、`to min kept` 3 项在 v1.1 上本就成立，其余 15 项对应的都是 v1.1 不存在的模式——与「恰好 15 项失败」自洽。

## 4. 变异实验记录

方法同 R1：改前按字节备份到 `/tmp/b3r2-mut/backups/`（仓库外）并记 sha256，改后前台跑对应测试文件（`-x`），拷回备份并校验 sha256 一致；全程未用 `git checkout`。共 **19 个变异，覆盖 §10 第 8 条全部 10 个小项，含任务书点名的 7 个；19/19 被捕获，存活 0**。完整日志 `/tmp/b3r2-mut/log.txt`。

| 变异 | 小项 | 目标文件 | 变红的测试 | 结果 |
|---|---|---|---|---|
| MA 「置位」与「通知」两行对调 | 8.1 | `useAccountIdentity.ts` | `test_failed_recovery_with_empty_username_never_reports_pending` | 捕获 |
| MB `clientIdentityPending` 改成只看 `!getUsername()` | 8.1 | `useAccountIdentity.ts` | 同上 | 捕获 |
| MC 去掉 NovelShelf 页眉行 `min-h-10` | 8.2 | `NovelShelf.tsx` | `test_novel_shelf_header_row_reserves_min_height` | 捕获 |
| MD 书斋页眉「新建一本」改为无条件渲染 | 8.2 | `NovelShelf.tsx` | `test_shelf_empty_state_has_exactly_one_new_book_link`（probe 断言 2≠1） | 捕获 |
| MT 外层不再下传 `identityPending`（打落定过渡场景） | 8.2 | `NovelShelf.tsx` | `test_shelf_pending_identity_replaces_login_and_idles_refresh`（props.identityPending undefined≠true） | 捕获 |
| ME StudioWorkbench「正在加载身份…」改「正在打开项目…」 | 8.3 | `StudioWorkbench.tsx` | `test_studio_identity_pending_wiring_and_embedded_login_target`（整段子串失配） | 捕获 |
| MF 去掉 StudioShelf 页眉行 `min-h-10` | 8.4 | `StudioShelf.tsx` | `test_shelf_header_reserves_height_and_non_embedded_button_is_not_right_aligned` | 捕获 |
| MG 「新建项目」按钮无条件 `ml-auto` | 8.4 | `StudioShelf.tsx` | 同上（非嵌入 probe 断言不含 ml-auto） | 捕获 |
| MH `if (e.repeat) return;` 挪回 `handleKeyDown` 第一行 | 8.5 | `page.tsx` | `test_enter_key_ignores_auto_repeat`（8 行全等失败） | 捕获 |
| MI 「帮我画一张…」按钮加 `onKeyDown={handleKeyDown}` | 8.5 | `page.tsx` | `test_chat_opener_buttons_match_the_spec_exactly` | 捕获 |
| MJ `composeSongSection` 的 `setInput(text)` 改 `setInput(text.trim())` | 8.5 | `page.tsx` | `test_chat_opener_bodies_match_the_spec_exactly`（四行字面量失配） | 捕获 |
| MK section `pt-10` 改回 `mt-10` | 8.6 | `match/page.tsx` | `test_match_empty_section_moves_top_spacing_from_margin_to_padding` | 捕获 |
| ML 隐私第一段包进 `{needsKey && …}` | 8.7/8.10 | `ChatModelSection.tsx` | `test_first_privacy_paragraph_is_outside_fold_before_switch_and_save` | 捕获 |
| MM 交换折叠里「Key 加密保存」与「自带模型文字聊天」 | 8.7 | `ChatModelSection.tsx` | `test_privacy_fold_follows_second_fieldset_and_holds_locked_paragraphs`（FOLD_ORDER 升序失败） | 捕获 |
| MN `dayFace` 改回 v1.1 写法 | 8.8 | `history/page.tsx` | `test_date_chips_render_chinese_day_faces_and_drop_native_placeholder` | 捕获 |
| MO 去掉「到」的 `max="9999-12-31"` | 8.8 | `history/page.tsx` | `test_date_chips_open_native_picker_and_bound_each_other` | 捕获 |
| MP `aria-label="从（开始日期）"` 改回 `"开始日期"` | 8.8 | `history/page.tsx` | `test_date_labels_stay_accessible_and_existing_history_contracts_survive` | 捕获 |
| MQ 气泡条件去掉 `!showHint &&` | 8.9 | `VoiceButton.tsx` | `test_voice_status_bubble_respects_first_use_hint`（afterHint 与 hintWhileDictating 都能取到 span） | 捕获 |
| MR AgentExchangeWorkspace 加一行 `import { LoadingState } …` | 8.10 | `AgentExchangeWorkspace.tsx` | `test_agent_exchange_workspace_pending_identity_uses_local_loading_state` | 捕获 |

每个变异还原后 sha256 与备份前一致（脚本内 assert 逐个校验，日志逐条打印 `restored sha256 verified`）。全部变异结束后：总哈希前 16 位仍为 `7c4aa5ca5c3c3510`；`git status` 仍 63 条；前台复跑 52 条新测试 **52 passed in 3.39s**。

执行者自报的 16 个变异（报告 §8.4）与其产物在仓库外，本复核无法直接重放，但 gate-record §2 记载 Claude 已抽查其 results.json 与 16 份备份；我方 19/19 独立捕获与之相互印证。

## 5. 必须修复项

无。

## 6. 可优化项（不阻塞合并）

1. **page.tsx 的 UTF-8 BOM 被移除**（新发现，非回归）：HEAD 的 `frontend/app/page.tsx` 首 3 字节为 `EF BB BF`（`﻿"use client"`），候选没有；这是 R1 返修（返修单 1 号改 `handleKeyDown`）时被编辑工具顺带去掉的，v1.1 快照上不存在该 hunk（R1 复核记录的 hunk 列表无 `@@ -1,4`）。字节级核查：仅此一个文件首字节有差异，两边均无 CRLF；tsc/lint/build/7826 条测试全绿，无任何行为影响，也不触碰任何 sha 锁（锁的是文件内部片段）。但它超出返修单「page.tsx 其余一字不动」的字面授权，且会让最终 diff 多一条与任务无关的首行改动。建议：合并前由维护者决定是否把 BOM 补回（补回会改变快照哈希，需 Claude 在 gate-record 重新登记）；若接受去 BOM（更符合无 BOM 的仓库主流），建议在 03-report.md 里如实记一句。
2. gate-record §1「v2 比 v1 新增 15 项判据」的口径可再写明：v2 带 `(v1.2)` 标记的行共 18 条，其中 3 条（showPicker 恰 1、openDatePicker ×4、to min kept）在 v1.1 上本就成立，「恰好 15 项失败」的正控口径与 155 = 143 + 净增 12（含 3 条 v1 判据被替换删除）都对，但两种计数并存容易误读。纯记录表述问题。
3. 报告 §8.3 如实注明「本轮补交未重跑 build / 全量 pytest，tsc/lint/build 为 R1 实现完成后的实测值」——本复核已代跑补齐（第 3 节），与该注明一致，无需动作；仅建议后续轮次的报告在交付前跑齐，避免依赖门禁方回填。

## 7. 二次修改指令

不适用（结论为通过）。若维护者采纳可优化项 1 的「补回 BOM」，做法为：在 `frontend/app/page.tsx` 文件头重新写入 `EF BB BF` 三字节（其余字节不动），随后复跑 `npx tsc --noEmit`、`npm run lint`、`npm run build` 与 `tests/test_empty_states_chat_openers.py`，并请 Claude 重算快照哈希、更新 gate-record；该操作不影响任何测试断言（已核：无测试读取该文件首字节）。

## 8. 哈希核对

- 开始：`(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256` = `7c4aa5ca5c3c35108554019106b13af455158f2fe9759a708e3228677bb3e607`（前 16 位 `7c4aa5ca5c3c3510`，与任务书预期一致）。
- 变异全部还原后、写本文件前复算：同值。
- 结束（本文件写入后复算）：同值 `7c4aa5ca5c3c3510…e607`（本文件为未跟踪文件，不进入 `git diff HEAD`，也不属于 `test_empty_states_*.py`，不影响该哈希）。
- 结束 `git status --porcelain --untracked-files=all`：64 条 = 开始 63 条 + 仅本文件（`docs/tasks/2026-10-28-empty-states/04-review-r2.md`）。变异备份与日志均在 `/tmp/b3r2-mut/`（仓库外），仓库内无残留。
