# 讨论群第二期（界面）独立复核 · 第 2 轮

本轮只核验上一轮 4 条必须修复项（A–D）和规格作者在浏览器里补测确认的 3 条（E–G），依据是返修单 `docs/tasks/2026-11-15-agent-group-ui/08-fix-r4-review.md` 与规格 `02-spec.md` 的「v1.3 修订」第 1–7 条。真实浏览器的数值采信 `.cache/review/gate-evidence-round2.md`。实现方报告 `impl/report-fix-r4.md` 只当线索。门禁证据列出的 6 处已知用例缺口（V2、V4、V7、V9、V17、V18）正由 `09-fix-r5-tests.md` 处理，本报告不重复。

## 1. 结论

**不通过。原因只在用例，实现没有问题。**

- A–G 七项的实现都已修好，没有带出新的错误：游标在所有读取路径上一致；自定义成员的模型显示的就是实际用的；分工、字重守卫、多列表格、发送后的焦点、别的标签期间到达的新消息都符合 v1.3。
- 有 3 条必须修复，全是守卫钉得不够：在已知的 6 处之外，又有 3 种一行就能做出的改坏，会让 E、F、G 原来的缺陷或验收判据回退，而全部用例照样通过。3 条都只改 `backend/tests/test_discuss_frontend_guards.py`，可以并进正在做的 `09-fix-r5-tests.md`，不用改实现。

## 2. 七项逐条核验

机械检查（本轮在副本里跑）：派单给的 pytest 命令 `114 passed`（上一轮 105，净增 9 条），0 跳过；`npm run lint -- --max-warnings=25` 结果为 `0 errors, 25 warnings`，退出码 0；只对讨论群文件跑 `npx eslint` 无输出；`npx tsc --noEmit` 无输出。`git diff --stat` 与上一轮完全相同，两份既有测试、`frontend/app/`、侧栏、后端代码都没动。

### A 读取游标（v1.3 第 1 条）：修好

- 纯函数 `advanceDiscussCursor`（`frontend/lib/discussLogic.ts:193-204`）返回旧游标与本批最大 `id` 中较大的一个，非整数一律忽略。
- 游标只在一个地方推进：`publishDetail`（`frontend/components/discuss/DiscussRoom.tsx:166-177`，第 169 行），参数是服务器读回的 `next.messages`。逐条核对调用 `publishDetail` 的路径：
  - 首次读取：`:179-220`，`after` 仍从 0 开始分页，合并后的消息从 0 起连续；
  - 补读、轮询、重新读方案：`:226-239`、`:241-257`、`reloadPlan`（`:441`），三处的 `after` 都是 `cursorRef.current`；
  - 方案保存与方案面板里的重新加载：`frontend/components/discuss/DiscussPlanPanel.tsx:279,298-300`。它们拿到的是 `after=0` 的前 200 条，同样从 0 起连续；游标只取较大值，不会越过任何没有读到的 ID。
- 不推进游标的地方：
  - 各操作接口返回的详情没有传给 `publishDetail`，`mutate` 只取结果并调 `refreshDetail`（`DiscussRoom.tsx:392-395`）；
  - `sendNote`（`:559-590`）只把插话并进本地列表，不碰游标。
  - 全文件里没有其他把非服务器读回的消息喂给游标的地方。
- 换群、换账号：`Room` 的 `key` 是 `${owner}:${id}`，会整体重新挂载，`cursorRef` 归零。整页重新加载时游标从 0 开始。首次读取失败后重试时详情仍是 `null`，游标也是 0。开发模式下首次读取跑两遍，第一遍被作废、不会发布结果。所以不会带着旧值漏读或重复读；插话在下一次读取时会再回来一次，由 `mergeDiscussMessages` 去重并以服务器版本为准。
- 浏览器实测（门禁）：`?after=307`，308 出现在插话之前，插话只有一条。

### B 自定义成员的模型（v1.3 第 2 条）：修好

- 初始值：`defaultDiscussCustomMemberModel`（`discussLogic.ts:346-355`）取 `catalog.roles` 里第一个 `kind === "lens"` 的成员在 `defaults` 里的值。`DiscussCreateForm.tsx:189` 用它，取不到时才回落到 `catalog.models[0]`。即使回落了，因为模型总是发送，界面显示的仍是实际使用的。`frontend/lib/discuss.ts:276-280` 的注释已改正。
- 请求体：`buildDiscussCreateBody` 对每个自定义成员总是写入 `models.custom{序号}`（`discussLogic.ts:440-444`），序号只按自定义成员计数，与后端 `_parse_members` 的分配一致（`backend/discuss/service.py:146-167`）。
- 后端接受：我在副本里用临时用例实测过（跑完已删除）。带一个角色池成员和一个自定义成员建群：
  - `{"custom1": "deepseek:deepseek-flash"}` 和 `{"custom1": "dashscope:qwen3.8-max"}` 都返回 201，详情里 `custom1` 的 `model` 分别是 DeepSeek Flash 和千问 3.8 Max，说明按请求存储；
  - `{"custom1": ""}` 返回 422「模型选择不合法」，这个边界见可优化 3；
  - 不存在的 `custom2` 返回 422。
- 浏览器实测（门禁）：下拉初始为 DeepSeek Flash，不改直接提交时请求体带 `custom1`。

### C 方案只读视图里的分工（v1.3 第 3 条）：修好

`discussMemberShowsFocus`（`discussLogic.ts:207-213`）对 `lens` 与 `custom` 且 `focus` 去空白后非空为真；`DiscussPlanPanel.tsx:372` 用它。浏览器实测（门禁）显示了「分工：…」。

### D 字重守卫（v1.3 第 4 条）：修好

- 正则改成 `<(?:b|strong)\b` 并加入 `font-weight`，不区分大小写（`backend/tests/test_discuss_frontend_guards.py:26-39`）。
- 用例先拿四段样例证明能命中，并断言 `font-normal` 不命中，再扫描真实文件（`:214-232`）。`\b` 不会误伤 `<br`、`<button`、`<boolean>`。
- 重做上一轮的 M18、M19，再加一处 `<b className=…>`，都被断言失败抓到。把正则改弱成 `<(?:b|strong)>`，也会被样例自检抓到（R21）。
- 仍有一种 Tailwind v4 写法抓不到，见可优化 4。

### E 列多的表格（v1.3 第 5 条）：实现修好；守卫钉得不够（必须修复 1）

- `discussTableMinWidth(n)` 返回 `n × 8`（`discussLogic.ts:254-259`）。表格写的是 `style={{ minWidth: \`${discussTableMinWidth(block.header.length)}em\` }}`（`frontend/components/discuss/DiscussDocument.tsx:176-178`），外层 `max-w-full overflow-x-auto`。`em` 相对表格的字号，所以每列 104px，不小于 8em。列少时由 `w-full` 跟着容器走。
- 浏览器实测（门禁）：10 列每列 104px，表格在自己的容器里横向滚动，页面不滚；两三列的表仍与容器等宽。

### F 发送插话之后的焦点（v1.3 第 6 条）：实现修好；守卫钉得不够（必须修复 2）

- 输入框改用 `readOnly={sending || busy}`（`frontend/components/discuss/DiscussComposer.tsx:99`），`finally` 里调 `textareaRef.current?.focus()`（`:40-45`）。
- 重复提交仍拦得住，有三层：
  - `submit` 开头检查 `sendingRef.current`（`:31`），在同一事件里同步生效；
  - 父组件 `setBusy("note")` 之后重新渲染，下一次按键拿到的 `busy` 是真；
  - 父组件 `sendNote` 用 `mutating` 引用拒绝并发（`DiscussRoom.tsx:560-566`）。
- 无条件 `focus()` 会不会抢焦点：
  - 对话框开着时，原生模态对话框之外的元素不可聚焦，`focus()` 什么都不做；
  - 窄布局下作者切到了别的标签时，群聊面板是 `hidden`（`display: none`），`focus()` 也什么都不做；
  - 抽屉被关时整个 iframe 是 `inert`，同样什么都不做；
  - 唯一的副作用：发送很慢时，作者把焦点移到另一个看得见的控件（宽布局里成果的版本下拉、标签按钮等），回包后焦点会被拉回插话框。见可优化 2。
- 浏览器实测（门禁）：成功、失败之后焦点都在插话框，能接着打字。

### G 不在群聊标签时到达的新消息（v1.3 第 7 条）：实现修好；守卫钉得不够（必须修复 3）

- 机制（`frontend/components/discuss/DiscussTimeline.tsx:70,91-140`）：
  - 不可见时，有新消息到达、且已经看过群聊，就置位 `pendingWhileHiddenRef`（`:102-106`）；
  - 新加的第三个 effect 在 `active` 变真时检查这个标记：同步取离开时的 `nearBottomRef`，在 rAF 里决定滚到最新还是显示「有新消息」，然后清掉标记（`:124-140`）。
- 与原有两个 effect 的关系：
  - 第一个 effect（首次显示停在最新）只在 `firstViewRef` 为真时动作，第三个 effect 要求它为假，两者互斥；
  - 第二个 effect 在 `active` 变真时，因为隐藏期间已经更新过最后一条的 ID，判定为「没有新消息到达」并直接返回，不会重复滚动；
  - 第三个 effect 在 effect 阶段同步取 `nearBottomRef`，早于浏览器恢复滚动位置时可能触发的 `scroll` 事件，不会被它改写。
- 开发模式：挂载时第三个 effect 因 `firstViewRef` 为真直接返回，没有需要清理的东西；第一个 effect 的 rAF 在 cleanup 里取消，第二遍重新排上。
- 宽布局：`active` 恒为真，隐藏分支不会进入，标记不会置位，第三个 effect 不动作，没有副作用。从窄布局的其他标签变成宽布局时，`active` 变真，按标记正确处理。
- 浏览器实测（门禁）：
  - 离开时在底部、期间到达新消息，回来离最新一条 0px；
  - 离开前往上滚过，回来位置不变，并出现「有新消息」按钮；
  - 期间没有新消息时，位置不变，也没有按钮。

## 3. 必须修复项（3 条，都只改用例）

### 必须修复 1：E 的守卫没有钉住单位，改成 `px` 照样通过

- 现象：把 `DiscussDocument.tsx:178` 的 `…}em` 改成 `…}px`（变异 R13），76 条相关用例全部通过。这时 10 列的表最小宽度只有 80px，各列又被挤回容器宽度，正是 E 原来的缺陷。把列数从 `block.header.length` 换成 `block.rows.length`（R14）同样通过。
- 位置：`backend/tests/test_discuss_frontend_guards.py:450-462` 只断言 `<table>` 标签里出现 `minWidth` 和 `discussTableMinWidth` 两个子串。
- 为什么是问题：返修单第三节第 5 条要求守卫「钉住你选的机制」；v1.3 第 5 条的机制是每列 8em，单位和列数这两处一改，要求就失效了。
- 建议：断言该 `<table>` 标签里恰好是 `minWidth: \`${discussTableMinWidth(block.header.length)}em\``（或用正则钉住 `header.length` 与 `}em`）。

### 必须修复 2：F 的守卫没有钉住「失败后也回焦点」

- 现象：把 `textareaRef.current?.focus()` 从 `finally` 挪进 `try`、放在 `setText("")` 后面（变异 R15，只有成功时回焦点），全部用例通过。
- 位置：`test_discuss_frontend_guards.py:482` 用的是整份文件里查子串 `"textareaRef.current?.focus()" in composer`。
- 为什么是问题：v1.3 第 6 条要求「成功或失败之后」焦点都留在插话框；返修单第三节第 5 条要求断言落在具体的函数上，不按整份文件查子串。
- 建议：取出 `submit` 函数体里 `finally { … }` 那一段，断言 focus 调用就在其中（且 `try` 段里没有）。

### 必须修复 3：G 的守卫没有钉住「处理完之后清掉标记」

- 现象：删掉 `DiscussTimeline.tsx:137` 的 `pendingWhileHiddenRef.current = false;`（变异 R19），全部用例通过。
- 后果：只要有过一次「隐藏期间到达新消息」，之后每次切回群聊都会重做一次跟随或提示。往上翻着看时，即使期间没有新消息，回来也会冒出「有新消息」按钮；停在底部附近（离底 80px 以内）时会被拉到最底。这违反返修单第四节第 6 条「期间没有新消息时来回切换，位置不变」，也违反门禁记录的「没有按钮」。
- 位置：`test_discuss_frontend_guards.py:487-500` 只查几个子串出现过。
- 建议：在读取 `pendingWhileHiddenRef` 的那个 effect 里断言有 `pendingWhileHiddenRef.current = false`。可以和 `09-fix-r5-tests.md` 里 V17、V18 的钉法写在同一条用例里，那条也要定位到同一个 effect。

## 4. 可优化项（5 项）

1. **外链守卫只拦住了 M16 的原样写法。** 改成带回落的 `safeExternalUrl(source.url) ?? source.url`（`DiscussDocument.tsx`，R02）或 `|| source.url`（`DiscussSourcesPanel.tsx`，R03）都能通过 `test_discuss_external_links_use_safe_external_url`（`guards.py:503-522`）。现在代码是对的，返修单要求的 M16 也已经能变红。但这是安全相关路径，建议守卫进一步断言 `source.url` 只作为 `safeExternalUrl(…)` 的参数出现。
2. **`finally` 里无条件 `focus()`。** 发送慢时，作者如果把焦点移到另一个看得见的控件，回包后会被拉回插话框（`DiscussComposer.tsx:44`）。可以在 `submit` 开始时记下焦点是否在插话框，或回包时 `document.activeElement` 是否仍是插话框或 `body`，只在这种情况下回焦点。
3. **`models.customN` 可能是空串。** `buildDiscussCreateBody` 不判空就发（`discussLogic.ts:443`）。实测空串会得到 422「模型选择不合法」。只有目录既没有角色池默认值、又没有任何模型时才会出现，现实中到不了；可以不发空值，或在 `validateDiscussCreate` 里给出明确提示。
4. **字重守卫还漏一种写法。** Tailwind v4 的 `font-(--变量)` 是字重写法，`font-[var(--变量)]` 也设字重，这两种都抓不到（R07 存活；正则只认 `font-[` 后面跟数字）。v1.3 第 4 条说的是「任何写法」。项目里目前没有字重变量，实际风险很低。
5. **游标用例里有两个重复的情形。** `test_advance_cursor_only_moves_on_server_reads` 里的 `localNoteOnly` 与 `afterLocalThree` 都是 `advanceDiscussCursor(1, [])`，和 `emptyReadKeeps` 测的是同一件事（`backend/tests/test_discuss_frontend_logic.py:943-945`）。「插话不推动游标」这件事纯函数表达不了，真正的保护要靠 `09` 里 V2 的部件守卫。建议删掉或改名，免得读者以为已经测到了。另外，`test_custom_member_default_model_uses_lens_default` 用的是精简过的目录（2 个角色池成员，没有 `models`、`limits`），不是报告里说的「真实形状」，不影响结论。

## 5. 需要在浏览器里补测的项（3 项）

1. **F 的抢焦点**：宽布局 1920×1000。在开发者工具里把 `POST …/notes` 拦住 3 秒，按 Enter 发一条插话，随即点一下成果标签的版本下拉（或右栏的标签按钮），放开请求。看回包后 `document.activeElement` 是被拉回插话框还是留在刚点的控件上，再由作者判断是否需要可优化 2。
2. **B 的「我的模型」**：账号配有自带模型（目录 `byok` 不为空）。`/discuss/new` 给自定义成员选「我的模型」建群，应返回 201，方案标签显示「模型：我的模型」。
3. **E 在窄宽度下**：手机宽度 390×780 的独立页，以及宽布局左栏的群聊里，各放一张 4 列和一张 10 列的表。表格在自己的容器里横向滚动，页面不出现横向滚动，消息区不被撑宽。

## 6. 给执行者的修改指令

只改 `backend/tests/test_discuss_frontend_guards.py`，可以并进 `09-fix-r5-tests.md` 这一轮一起交。不改实现，不改既有测试，不提交 git。

1. E：在 `DiscussDocument.tsx` 唯一的 `<table>` 标签上，断言 `minWidth` 的值恰好是 `` `${discussTableMinWidth(block.header.length)}em` ``。
2. F：取出 `DiscussComposer.tsx` 里 `submit` 的函数体，断言 `textareaRef.current?.focus()` 在它的 `finally { … }` 块里、不在 `try { … }` 块里。
3. G：在 `DiscussTimeline.tsx` 里读取 `pendingWhileHiddenRef` 的那个 effect 中，断言有 `pendingWhileHiddenRef.current = false`（与 V17、V18 用同一个定位）。
4. 自检：把 R13、R14、R15、R19 四种改坏逐一做一遍，确认都是 `failed`（不是 `error`），用原文写回，输出摘要写进 `impl/report-fix-r5.md`。可优化项不要求本轮处理。

## 7. 变异与结果

做法同上一轮：临时脚本放在仓库外，逐处做唯一匹配的字符串替换，跑 `test_discuss_frontend_logic.py`、`test_discuss_frontend_guards.py`、`test_discuss_frontend_navigation.py`、`test_ui_polish_page_contracts.py`、`test_ui_closeout_dialog_scrim.py`、`test_studio_frontend_navigation.py`（共 76 条），再用原始字节写回。结束后对 14 个可能被改过的文件做 SHA-256 比对，全部与改前一致，临时脚本已删除。另做过一个临时后端用例（B 的后端接受性），跑完已删除。

| 编号 | 文件 | 改坏方式 | 结果 | 抓到它的用例 |
|---|---|---|---|---|
| R01（重做 M16） | `DiscussDocument.tsx` | 编号链接直接用 `source.url` | 抓到（failed） | `test_discuss_external_links_use_safe_external_url` |
| R02 | `DiscussDocument.tsx` | `safeExternalUrl(source.url) ?? source.url` | 存活 | 无（可优化 1） |
| R03 | `DiscussSourcesPanel.tsx` | `safeExternalUrl(source.url) \|\| source.url` | 存活 | 无（可优化 1） |
| R04（重做 M18） | `DiscussOutputPanel.tsx` | `<strong className=…>` | 抓到（failed） | `test_discuss_frontend_has_no_bold_font_weight` |
| R05（重做 M19） | `DiscussOutputPanel.tsx` | `[font-weight:600]` | 抓到（failed） | 同上 |
| R06 | `DiscussOutputPanel.tsx` | `<b className=…>` | 抓到（failed） | 同上 |
| R07 | `DiscussOutputPanel.tsx` | `font-(--discuss-weight)` | 存活 | 无（可优化 4） |
| R08 | `discussLogic.ts` | 游标不取旧值（从 0 起算） | 抓到（failed） | `test_advance_cursor_only_moves_on_server_reads` |
| R09 | `discussLogic.ts` | 自定义成员模型改回「与默认不同才发」 | 抓到（failed） | `test_build_create_body_members_models_and_identities` |
| R10 | `discussLogic.ts` | 初始模型不限 `kind === "lens"`（取到主持人的千问） | 抓到（failed） | `test_custom_member_default_model_uses_lens_default` |
| R11 | `discussLogic.ts` | 分工只认 `lens` | 抓到（failed） | `test_member_focus_visibility_covers_lens_and_custom` |
| R12 | `discussLogic.ts` | 每列 6em | 抓到（failed） | `test_table_min_width_is_eight_em_per_column` |
| R13 | `DiscussDocument.tsx` | `em` 改 `px` | **存活** | 无（必须修复 1） |
| R14 | `DiscussDocument.tsx` | 列数改用 `block.rows.length` | **存活** | 无（必须修复 1 一并解决） |
| R15 | `DiscussComposer.tsx` | 只在成功时回焦点 | **存活** | 无（必须修复 2） |
| R16 | `DiscussComposer.tsx` | 再加回 `disabled={sending}` | 抓到（failed） | `test_discuss_composer_keeps_focus_while_sending` |
| R17 | `DiscussComposer.tsx` | 去掉 `sendingRef` 判断 | 存活 | 无。影响小：父组件的 `busy` 与 `mutating` 仍拦住第二次请求，最多出现一句「正在处理」的提示 |
| R18 | `DiscussTimeline.tsx` | 隐藏期间置位时不再要求「已看过群聊」 | 存活 | 无。只在「开工后一直没看群聊」的情形下留下一个过期标记，与必须修复 3 同源，补那条用例时可一并钉住 |
| R19 | `DiscussTimeline.tsx` | 处理完不清掉标记 | **存活** | 无（必须修复 3） |
| R20 | `DiscussRoom.tsx` | 操作后的补读 `after` 改回 0 | 抓到（failed） | `test_discuss_room_reads_use_server_cursor` |
| R21 | `test_discuss_frontend_guards.py` | 字重正则改弱成 `<(?:b\|strong)>` | 抓到（failed） | `test_discuss_frontend_has_no_bold_font_weight`（样例自检） |

小结：21 处变异，12 处被抓，全部是断言失败，没有 `error`；9 处存活。存活的里面：R13、R14、R15、R19 对应必须修复 1–3；R02、R03、R07 列为可优化；R17、R18 影响小，已在表里说明。本轮新加的纯函数（游标、初始模型、分工、表格宽度）各自的改坏都被抓到。已知的 V2、V4、V7、V9、V17、V18 没有重复做。
