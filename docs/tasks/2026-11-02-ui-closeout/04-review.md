# 04 独立复核：UI 复核收尾（第五批）

- 依据：`docs/tasks/2026-11-02-ui-closeout/02-spec.md` v1.1（唯一依据）；`03-report.md`、`impl/*.md`、`05-fix-r1.md` 只当线索，下列结论均为本次亲自复跑。
- 对象：基线 `bccbf9f` + 工作区改动。开工前核对：`git diff` 与 `.review/diff.patch` 逐字节相同；按「`git diff` + 未跟踪清单各文件内容」计算的 sha256 = `f0e4514c…a7dea`，与 `.review/snapshot.sha256` 一致。
- 收尾核对：全部变异已按字节还原（每次还原后比对 sha256），最终 sha256 仍为 `f0e4514cf48fdf08a5f2dc4e684e305ba5260dca88c44466a2b9c73423ea7dea`，`page.tsx` 开头仍是 `ef bb bf`。本文件（`04-review.md`）是复核新增，不在快照清单内。

## 1. 结论：**不通过**

实现代码（T1–T4 的前端与门禁改动）与规格逐条一致，白名单、字面量锁、§5 第 1–7 条全部成立，未发现功能性错误。不通过的原因只在 T5 新测试：

1. `test_ui_closeout_history_keyboard.py` 的 `tabIndex={-1}` / `aria-hidden="true"` 是全文件计数，不绑定到原生日期框：把 `tabIndex={-1}` 从两个原生框挪到两个按钮上（T2 行为整个反过来——原生框回到 Tab 序列、按钮退出），或去掉两个原生框的 `aria-hidden`，新旧测试**全部仍绿**。其中 `aria-hidden="true"` ≥ 6 在 HEAD 上就已经是 7，本身恒真。
2. `test_ui_closeout_dialog_scrim.py::test_no_backdrop_tailwind_variants_remain` 有空集问题：扫描目录全部不存在时这条用例照样通过。

两项都只需改新测试文件（在白名单内），不需要动实现。

## 2. 验收标准逐条核验（规格 §5）

| # | 命令 | 实际结果 | 判定 |
|---|---|---|---|
| 1 | `cd frontend && export npm_config_cache=/tmp/fiona-npm-cache && npx tsc --noEmit` | 无输出，`EXIT=0` | ✅ |
| 2 | `cd frontend && npm run lint` | `✖ 25 problems (0 errors, 25 warnings)`，`EXIT=0` | ✅（≤25） |
| 3 | `cd frontend && npm run build` | 路由表正常输出，`EXIT=0` | ✅ |
| 4 | `cd backend && env -u …(9 个代理变量) .venv/bin/python -m pytest -q -p no:cacheprovider -rs`（后台跑完） | `7855 passed, 35 warnings in 328.12s (0:05:28)`，`EXIT=0`，日志中 `SKIPPED` 0 条 | ✅ 7855 = 7836 + 19 |
| 5 | HEAD 对照（见下） | 13 failed, 13 passed；失败全部为 AssertionError | ✅ |
| 6 | 计数（见下） | 全部符合 | ✅（§5.6 最后一项见注） |
| 7 | 既有测试原样 | 门禁文件只改 T4 点名处；其余既有测试只有 v1.1 授权的一行 | ✅ |

**第 4 条新增用例数**（`--collect-only` 实数）：`test_ui_closeout_cost_hint.py` 5、`test_ui_closeout_dialog_scrim.py` 3、`test_ui_closeout_history_keyboard.py` 4、`test_ui_closeout_structure_guards.py` 7，合计 19。

**第 5 条 HEAD 对照**：按规格 `git archive HEAD` 解到 `mktemp -d /tmp/fiona-head.XXXXXX`，拷入 4 个新测试与 `test_design_system_gate.py`、`test_design_system_css.py`（未拷 `test_ui_polish_page_contracts.py`，按 R1 裁决），`cp -cR frontend/node_modules`，用本工作树 `backend/.venv/bin/python` 清代理后跑 `-rf`（复核后已删除临时目录）。`-rf` 摘要原文：

```
FAILED tests/test_ui_closeout_cost_hint.py::test_cost_hint_contract - Asserti...
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_missing_show_cost_guard_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_balance_digits_are_rejected_when_not_readout
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_moved_enter_hint_is_rejected
FAILED tests/test_ui_closeout_cost_hint.py::test_selfcheck_missing_bom_is_rejected
FAILED tests/test_ui_closeout_dialog_scrim.py::test_all_dialogs_use_scrim_dialog
FAILED tests/test_ui_closeout_dialog_scrim.py::test_scrim_backdrop_rules_are_the_only_two
FAILED tests/test_ui_closeout_dialog_scrim.py::test_no_backdrop_tailwind_variants_remain
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_chip_keyboard_contract
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_inputs_pair_with_their_own_chips
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_buttons_pair_with_their_own_inputs
FAILED tests/test_ui_closeout_history_keyboard.py::test_selfcheck_swapped_labels_are_rejected
FAILED tests/test_design_system_gate.py::test_token_layer - AssertionError: ...
13 failed, 13 passed in 1.85s
```

`--tb=line -rA` 复跑确认：13 个失败的末行全部是 `AssertionError`（12 条带消息，history 自检那条是 `_swap` 里的裸 `assert`），没有 ImportError / FileNotFoundError；`test_token_layer` 只有 `FAIL T8 所有对话框共用 .scrim-dialog::backdrop…`，T1–T7 均 PASS。PASSED：structure_guards 7 条全部、`test_font_size_rules`、`test_color_rules`、`test_role_rules`、`test_selfcheck_source_rules`、`test_selfcheck_token_layer`、`test_design_system_css.py::test_generated_css_font_sizes`。与规格期望完全一致。

**第 6 条计数**：

```
grep -rn "backdrop:" frontend/app frontend/components frontend/lib | wc -l      → 0
grep -rln "scrim-dialog" frontend/components | wc -l                            → 8
grep -c "::backdrop {" frontend/app/globals.css                                  → 2
grep -c 'className="absolute inset-0 h-full w-full cursor-pointer opacity-0"' frontend/app/history/page.tsx → 2
grep -c 'tabIndex={-1}' frontend/app/history/page.tsx                            → 2
grep -c '"平台模型 · 每条 10 颗草莓"' frontend/app/page.tsx                        → 2
head -c 3 frontend/app/page.tsx | xxd | head -1                                  → 00000000: efbb bf
git status --porcelain → 14 个 M（§3.1 的 14 个已跟踪文件）+ 4 个新测试 + docs/tasks/2026-11-02-ui-closeout/
git diff --stat -- backend/tests → test_design_system_css.py 2 +-、test_design_system_gate.py 95 ++--、test_ui_polish_page_contracts.py 2 +-（3 files）
```

注：§5.6 注释写「只有两个既有文件」、§5.7 期望「为空」，是 v1 的写法，v1.1 把 `test_ui_polish_page_contracts.py` 加进白名单后没有同步这两处；实际是 3 个文件、§5.7 输出只有 `test_ui_polish_page_contracts.py | 2 +-`，与 v1.1 §3.1 的授权一致，不算违规。构建产物核对：`.next/static/chunks/*.css` 中为 `.scrim-dialog::backdrop{background:var(--scrim,#1f29262e)}` 与 `.dark .scrim-dialog::backdrop{background:var(--scrim,#00000073)}`，兜底色保留；产物里已无 `backdrop\:bg` 工具类。

**第 7 条与白名单（`git diff -U0` 逐 hunk）**：

- `test_ui_polish_page_contracts.py`：1 个 hunk，`-…== 2` / `+…== 4`，只此一行。✅
- `test_design_system_css.py`：1 个 hunk，只改 `REQUIRED_PACKAGES`。✅
- `test_design_system_gate.py`：10 个 hunk，依次为 `TYPE_WORDS→TYPE_WORD_RX`（T4.1）、F7 说明文字（T4.2）、F7 正则新增分支（T4.2）、`startswith→TYPE_WORD_RX.match`（T4.1）、T8 段注释一行（在规格点名的 `:519–535` 块内）、`want_backdrop`（T4.4）、断言名（T4.4）、`good_f7` 两条 + `bad_f7`/误伤样本（T4.3）、样本 CSS 四行换两行（T4.5）、T8 自检五坏一好（T4.5）。没有越界改动。✅
- 8 个组件文件：每个文件 1 处，只改 className 字符串（6 处 `backdrop:bg-[color:var(--scrim)]` 原位换 `scrim-dialog`，ConfirmDialog/GeneratedImage 追加 `scrim-dialog`）。✅
- `globals.css`：删 5 行（注释 + 4 条 `::backdrop`），在 `.confirm-dialog {…}` 后加注释 + 2 条规则；`.image-preview-dialog {…}`、`.confirm-dialog {…}` 未动。✅
- 未跟踪文件：4 个新测试 + `docs/tasks/2026-11-02-ui-closeout/`；其中 `03-report.md`、`impl/A–D.md` 在白名单；`02-spec.md`、`dispatch.md`、`05-fix-r1.md` 是派单方文档（规格/派单/返修单），不属于执行者产出。该目录整体在基线中不存在，无法逐字节证明执行者未改动 `02-spec.md`，但其内容与 `05-fix-r1.md` 的裁决一致。

**§2.1 / §2.2 字面量锁（逐条实数）**：

- page.tsx：含 `border-t border-[color:var(--carve)] pt-2` 的行 1 行，且含 `max-md:mt-1`、`max-md:pt-1`、`max-md:text-fs-11`；`每条消息消耗 <span className="readout font-normal">10</span> 颗草莓` 1；`"平台模型 · 每条 10 颗草莓"` 2；`平台模型每条消息消耗 10 颗；自带模型聊天不扣` 1；`Enter 发送，Shift + Enter 换行` 1；两条模板字面量各 1；`改用我的模型` 1；`className="readout font-normal"` 4。
- history/page.tsx：`showPicker(` 1 且匹配 `try { input.showPicker(); } catch {`；`openDatePicker(e.currentTarget)` 4；`onClick={e => openDatePicker(e.currentTarget)}` 2；`e.key === "Enter"`、`e.key === " "` 各 2；四个 `has-[:focus-visible]:…` 片段各 2；两个原生框 `aria-label` 各 1；`className="absolute inset-0 h-full w-full cursor-pointer opacity-0"` 2（现在由两个按钮提供，原生框改成 `cn(…)`，这是规格 T2 的写法）；`<label className={cn("chip relative` 2；`type="date"` 2；`aria-label=` 7（≥5）；`dateFrom && "chip-on"` / `dateTo && "chip-on"` 各 1；`dayFace` 定义行逐字相同；`toLocale*` / `getHours(` 0。
- 对应既有测试（`test_mobile_chat_fix.py`、`test_ui_polish_page_contracts.py`、`test_empty_states_history_dates.py`、`test_component_language.py`）在全量中全部通过。

**T1–T5 逐项对应（diff 中均找到）**：T1 第 1–7 条代码与规格逐字一致（模块级 `costHintSeenKey`/`markCostHintSeen`、签名加 `balance`、`firstVisit` + ref 判定 effect、三个派生常量、容器整行搬入组件且在一行、两处 `showCost &&` 与朱色余额、调用点单行传 `balance={strawberryBalance}`，`label`/`labelTitle`/思考档/改用按钮/错误行未动）；T2 第 1–4 条逐字一致；T3 第 1–4 条一致（13 个 `<dialog>` 全部带类：6 个直接字符串、`dialogClass` 2 个引用点 `BrainTrial.tsx:168/182`、`sourceDialogClass` 5 个引用点 `BreakdownDialog:24`、`CreateProjectDialog:63`、`SourcePanel:65`、`EpisodePlan:25`、`NovelFilmDialog:44`；`grep "<dialog"` 共 14 行，多出的 1 行是 `globals.css` 注释）；T4 第 1–6 条一致；T5 四个文件的清单项均有对应断言（缺陷见 §4）。

## 3. 变异实验记录

全部用脚本按字节读写（`page.tsx` 的 BOM 保留），每次只改一处，跑完立即写回原字节并比对 sha256，结果都是「还原 OK」。

| # | 改了什么 | 跑的测试 | 结果 | 还原 |
|---|---|---|---|---|
| M1 | page.tsx 平台分支去掉 `showCost && ` | cost_hint + mobile_chat_fix + ui_polish | 红：cost_hint 5 条全红（`the platform-model cost text must be guarded by showCost`）；既有 18 条绿 | ✅ |
| M2 | page.tsx 图片模式分支去掉 `showCost && ` | cost_hint | 红：5 条（`the image-mode cost text must be guarded by showCost`） | ✅ |
| M3 | history 第一个 `tabIndex={-1}` → `tabIndex={0}` | history_keyboard + empty_states_history_dates | 红：`test_date_chip_keyboard_contract`（`both native date inputs must leave the Tab order`）；既有 4 条仍绿 | ✅ |
| M4 | history 删掉 catch 里的 `input.focus();` | history_keyboard | 红：`test_date_chip_keyboard_contract` | ✅ |
| S1 | history 两个原生框 `aria-label` 真实对调（盲区 1） | history_keyboard + empty_states_history_dates | 红：`test_date_inputs_pair_with_their_own_chips`、`test_selfcheck_swapped_labels_are_rejected`；**既有 4 条全绿**（证明旧盲区存在、新测试补上） | ✅ |
| S2 | 两个按钮的 `onClick` ref 对调 | 同上 | 红：`test_date_buttons_pair_with_their_own_inputs` + 自检；既有全绿 | ✅ |
| M6 | SongProjectCard 的 `scrim-dialog` 换回 `backdrop:bg-[color:var(--scrim)]` | dialog_scrim + gate | 红：`test_all_dialogs_use_scrim_dialog`、`test_no_backdrop_tailwind_variants_remain` | ✅ |
| M7 | BrainTrial `dialogClass` 去掉 `scrim-dialog`（标识符解析路径） | dialog_scrim | 红：`test_all_dialogs_use_scrim_dialog`（BrainTrial.tsx） | ✅ |
| M8 | ConfirmDialog 退回 `className="confirm-dialog"` | dialog_scrim + component_language | 红：`test_all_dialogs_use_scrim_dialog` | ✅ |
| M9 | globals.css `.dark` 那条去掉兜底色 | dialog_scrim + gate | 红：`test_token_layer`（T8） | ✅ |
| M10 | globals.css 多加 `.image-preview-dialog::backdrop` | dialog_scrim + gate | 红：`test_scrim_backdrop_rules_are_the_only_two`（found 3）、`test_token_layer` | ✅ |
| M11 | gate F7 退回前缀匹配 `val.startswith((…10 个词…))` | gate | 红：`test_selfcheck_source_rules`（`F7 坏样本没有命中：'const style = { fontSize: anySize };'`） | ✅ |
| M12 | gate F7 去掉 `.style.fontSize =` / `setProperty` 分支 | gate | 红：`test_selfcheck_source_rules`（`el.style.fontSize = "14px"`） | ✅ |
| M13 | gate T8 `want_backdrop` 多收一条 image-preview | gate | 红：`test_token_layer`、`test_selfcheck_token_layer` | ✅ |
| M14 | ChatModelSection.tsx 真实插入 `{needsKey && <>` / `</>}`（盲区 2） | structure_guards + empty_states_settings_privacy | 红：structure_guards 3 条（花括号 25≠24）；**既有测试全绿** | ✅ |
| M15 | page.tsx `role="group"` 行加 `onKeyDown`（盲区 3） | structure_guards + empty_states_chat_openers | 红：structure_guards 4 条；既有全绿 | ✅ |
| M16 | page.tsx `data-chat-openers` 行加 `onKeyDown` | 同上 | 红：structure_guards 4 条；既有全绿 | ✅ |
| W1 | structure_guards 把花括号与 `&&` 结尾两条断言都改成 `assert True or …` | structure_guards | 红：`test_selfcheck_privacy_guard_rejects_split_needs_key_wrapper`（自检确实依赖这两条） | ✅ |
| W2 | history_keyboard 的 `check_date_input_pairing` 改成直接 return | history_keyboard | 红：`test_selfcheck_swapped_labels_are_rejected`（DID NOT RAISE） | ✅ |
| W3 | dialog_scrim 的 `scrim-dialog in class_name` 断言改恒真 | dialog_scrim | 红：`test_all_dialogs_use_scrim_dialog` 里的坏样本自检 | ✅ |
| W4 | cost_hint 的 `PLATFORM_SPAN` 断言改恒真 | cost_hint | 红：`test_selfcheck_missing_show_cost_guard_is_rejected` | ✅ |
| W5 | gate 的 `TYPE_WORD_RX.match` 改 `if False:` | gate | 红：既有好样本 `const style: { fontSize: number } = {};` 被误伤 | ✅ |
| M22 | `REQUIRED_PACKAGES` 的 `tailwindcss` 改成不存在的包名 | design_system_css | SKIPPED（`Frontend dependencies unavailable: tailwindcss-missing-probe`），说明探测真的在查包；原样时 1 passed、不 skip | ✅ |
| **M17** | history 两个原生框删掉 `aria-hidden="true"` | history_keyboard + empty_states_history_dates | **8 passed，无一红** | ✅ |
| **M18** | history 两个 `tabIndex={-1}` 从原生框挪到两个按钮上 | 同上 | **8 passed，无一红** | ✅ |
| **E1** | dialog_scrim 的 `SCAN_BASES` 三个目录改成不存在 | dialog_scrim 两条 | `test_no_backdrop_tailwind_variants_remain` **通过**；`test_all_dialogs_use_scrim_dialog` 红（found 0） | ✅ |
| M19 | page.tsx `setFirstVisit(firstVisitDecided.current)` → `setFirstVisit(false)` | cost_hint | 5 passed，无一红 | ✅ |
| M20 | page.tsx 去掉 `firstVisitDecided.current === null` 的 ref 守卫 | cost_hint | 5 passed，无一红 | ✅ |
| M21 | page.tsx 第一处 `{lowBalance && <>，还剩` → `{<>，还剩` | cost_hint | 5 passed，无一红 | ✅ |

规格要求的四类变异（`showCost &&`、`tabIndex={-1}`、`scrim-dialog`、F7 前缀）全部能变红。M17/M18/E1 是必须修复项的证据；M19–M21 列为可优化项。

## 4. 必须修复项

### 4.1 日期 chip 测试的 `tabIndex` / `aria-hidden` 不绑定原生框，T2 核心行为可整体反转而全绿

- 文件：`backend/tests/test_ui_closeout_history_keyboard.py:55`、`:60`、`:73–90`（`check_date_input_pairing`）、`:130` 起的自检。
- 现象：
  - `:55` `source.count("tabIndex={-1}") == 2`、`:60` `source.count('aria-hidden="true"') >= 6` 都是全文件计数。M18 把 `tabIndex={-1}` 从两个原生框挪到两个按钮上——原生框回到 Tab 序列、按钮退出，正是 T2 要消除的「键盘停在看不见的分段上盲改」——新旧 8 条用例全绿。
  - `history/page.tsx` 除两个原生框外还有 7 处 `aria-hidden="true"`（4 个 chip 内 span + `:157`、`:354`、`:356`），HEAD 上就是 7 ≥ 6；M17 去掉两个原生框的 `aria-hidden` 也全绿。这条断言的提示写的是「four visible labels plus two native inputs」，实际对原生框恒真。
  - `onBlur={() => setRawChip(null)}` 恰 2 次同样不检查位置（挪到按钮上也能过）。
- 期望：每个 `type="date"` 的 `<input>` 标签内必须同时含 `aria-hidden="true"`、`tabIndex={-1}`、`onBlur={() => setRawChip(null)}`，以及与自己对应的 `rawChip === "from"` / `rawChip === "to"`；两个按钮的标签内不得出现 `tabIndex`、`aria-hidden`。自检补两种坏副本（M17、M18 的写法）并断言抛 `AssertionError`。

### 4.2 遮罩工具类扫描有空集问题

- 文件：`backend/tests/test_ui_closeout_dialog_scrim.py:30–44`（`_source_map` 对不存在的目录静默 `continue`）、`:139–146`（`assert_no_backdrop_utility`）、`:191–192`（`test_no_backdrop_tailwind_variants_remain`）。
- 现象：E1 把三个扫描目录改成不存在后，`_source_map` 返回空字典，`assert_no_backdrop_utility({})` 什么也不检查，`test_no_backdrop_tailwind_variants_remain` 通过。同文件的 `test_all_dialogs_use_scrim_dialog` 会因 found 0 变红，所以整个文件不会全绿；但这一条用例单独跑（如 `-k backdrop`）时恒真，正是「目标不存在也照样通过」的问题。当前真实扫描到 138 个文件、含 `globals.css`，所以现状结果正确。
- 期望：扫描前断言三个目录都存在；扫描结果非空，且包含 `frontend/app/globals.css` 和本批改过的至少一个组件（如 `frontend/components/SongProjectCard.tsx`）；用一条自检证明「空字典」会被拒。

## 5. 可优化项（不阻断）

1. **T1 首次判定逻辑没有测试锁**（M19–M21 全绿）：`setFirstVisit(false)`（首次提示永远不出现）、去掉 ref 守卫（严格模式下首次被判成 false）、余额后缀去掉 `lowBalance &&`，cost_hint 都拦不住。规格 T5 清单没要求，但建议在 cost_hint 加三条字面量：`if (firstVisitDecided.current === null) firstVisitDecided.current = markCostHintSeen(username);`、`setFirstVisit(firstVisitDecided.current);` 各恰 1 次，`{lowBalance && <>，还剩 <span className="readout font-normal">{balance}</span> 颗</>}` 恰 2 次。
2. **T1 逻辑核对（无问题，记录在案）**：`chatMode=false` 时不论 config，只走「每条消息消耗」分支，受 `showCost` 守卫；`config=null` 且 chatMode 时同样落到该分支，`hasContent` 只看 `showCost || error`；`config.enabled` 时模型名常显、`hasContent` 恒真、不显示余额（与「自带模型那一行不变」一致）；`balance=null` 时 `lowBalance=false`，从 null 变成数字只会让提示出现，不会抖动布局以外的问题。严格模式 effect 跑两遍时 ref 跨模拟卸载保留，第二遍沿用第一次的 `true`；`key={username}` 换号即重挂载，ref 清空、存储键按 `encodeURIComponent(username)` 区分。
3. **换号时余额短暂串号**（既有问题，白名单外）：`Sidebar.tsx` 在 `fiona-user-changed` 后先发请求，期间不把余额回报为 `null`，新账号的页脚可能短暂显示旧账号的低余额朱色提示；手机工具栏在 HEAD 上就有同样现象。建议下批在 Sidebar 换号时先 `onBalanceChange(null)`。
4. **首次提示的消耗时机**：首次进聊天时若处于自带模型状态，首次标记照样写入，之后切回平台模型就看不到首次提示（低余额提示不受影响）。符合规格字面，产品上可再斟酌。
5. **T2 退回路径的无障碍**：退回路径里获得焦点的原生框仍是 `aria-hidden="true"`，读屏用户听不到它；另外窗口失焦会触发 `blur` 把 `rawChip` 清空，切回窗口时焦点回到原生框但它已透明——在不支持 `showPicker()` 的旧浏览器上又会出现「盲改」。建议下批改成 `aria-hidden={rawChip !== "from"}` 并加 `onFocus` 恢复显示（要同步 §2.2 的计数锁）。按钮在前、原生框在后且都 `absolute inset-0` 无 z-index，原生框在上层，指针仍落在原生框；`<label>` 现在的「被标注控件」是第一个可标注后代（按钮），但原生框整块覆盖 label，点击目标总是原生框（交互内容），不会触发 label 激活，没有重复调用；`has-[:focus-visible]` 对按钮生效。
6. **F7 规则边角**：`\.style\.fontSize\s*=` 也会命中比较 `el.style.fontSize === "14px"`（误报）；反引号 `` setProperty(`font-size`, …) `` 与 `style["fontSize"] = …` 漏报。仓库当前都是 0 处。另外新加的两条好样本 `fontSize?: string | number;`、`React.CSSProperties["fontSize"] = …` 根本不命中 F7 主正则，不会走到 `TYPE_WORD_RX`，对整词放行没有正向覆盖（W5 证明既有好样本 `const style: { fontSize: number } = {};` 在覆盖）；可补 `fontSize: string | number` 这类好样本。
7. **history 自检缺正样本对照**：`test_selfcheck_swapped_labels_are_rejected` 没有先断言原文能通过两条检查（cost_hint、structure_guards 都有）；与真实用例合起来不会出错，但单看自检不能证明拒绝是因为对调。
8. **cost_hint 的 `<ChatModelFooter ` 按行计数**而不是按出现次数，同一行出现两次不会被发现；影响极小。
9. **规格文本**：§5.6 的「只有两个既有文件」、§5.7 的「为空」没有随 v1.1 更新，建议规格作者顺手改成 3 个文件 / 只含 `test_ui_polish_page_contracts.py` 一行。

## 6. 给执行者的二次修改指令

> 只改下面两个测试文件（都在 §3.1 白名单的「新增」里），实现文件、既有测试、门禁文件一个字节都不许动。不得调用 subagent / subagent_fork / workflow。pytest 写法沿用规格 §3.5（`backend/` 下，`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider …`）。git 只读。
>
> **A. `backend/tests/test_ui_closeout_history_keyboard.py`**
>
> 1. 在 `check_date_input_pairing` 里，对 `from_tags[0]` 追加要求同时含：`aria-hidden="true"`、`tabIndex={-1}`、`onBlur={() => setRawChip(null)}`、`rawChip === "from"`；对 `to_tags[0]` 同样追加，最后一项换成 `rawChip === "to"`。保留原有 `value` / `data-chip` / `ref` 三项。
> 2. 新增 `check_date_buttons_stay_in_tab_order(source)`：按行找到含 `` aria-label={`从（开始日期）：${dayFace(dateFrom)}`} `` 的行，向上找到最近一行去空白后等于 `<button` 的行、向下找到最近一行去空白后等于 `/>` 的行，取这一段；断言段内不含 `tabIndex`、不含 `aria-hidden`；「到」按钮同理。新增真实用例调用它。
> 3. `test_selfcheck_swapped_labels_are_rejected` 开头先对原文调用 `check_date_input_pairing` 和 `check_date_button_pairing`（必须通过）。
> 4. 新增自检用例（每个都先断言原文通过，再断言坏副本抛 `AssertionError`，替换前断言被替换串在原文中的出现次数符合预期）：
>    - 坏副本 1：把原文中两处 `aria-hidden="true"\n                  tabIndex={-1}` 改成 `tabIndex={-1}`（即删掉两个原生框的 `aria-hidden`），`check_date_input_pairing` 必须抛；
>    - 坏副本 2：删掉两行 `                  tabIndex={-1}\n`，并在两处 `                  type="button"\n` 之后插入 `                  tabIndex={-1}\n`，`check_date_input_pairing` 和 `check_date_buttons_stay_in_tab_order` 都必须抛；
>    - 坏副本 3：两个原生框里的 `rawChip === "from"` 与 `rawChip === "to"` 对调，`check_date_input_pairing` 必须抛。
>
> **B. `backend/tests/test_ui_closeout_dialog_scrim.py`**
>
> 1. 新增 `assert_scan_is_not_empty(sources)`：断言 `SCAN_BASES` 里每个目录都 `is_dir()`；`sources` 非空；`"frontend/app/globals.css"` 与 `"frontend/components/SongProjectCard.tsx"` 都在 `sources` 的键里。
> 2. `test_no_backdrop_tailwind_variants_remain` 在调用 `assert_no_backdrop_utility(sources)` 之前先调用 `assert_scan_is_not_empty(sources)`；`test_all_dialogs_use_scrim_dialog` 同样先调用一次（传它自己的 `.tsx` 源码字典时，只检查目录存在、非空、含 `SongProjectCard.tsx`，可以给函数加一个参数控制是否要求 `globals.css`）。
> 3. 自检：`assert_scan_is_not_empty({})` 必须抛 `AssertionError`。
>
> **C. 可选（建议一起做，同在 `backend/tests/test_ui_closeout_cost_hint.py`，白名单内）**：在 `check_cost_hint_contract` 加三条——`if (firstVisitDecided.current === null) firstVisitDecided.current = markCostHintSeen(username);` 恰 1 次；`setFirstVisit(firstVisitDecided.current);` 恰 1 次；`{lowBalance && <>，还剩 <span className="readout font-normal">{balance}</span> 颗</>}` 恰 2 次；并各配一条自检坏副本（`setFirstVisit(false);`、去掉 `if (firstVisitDecided.current === null) `、去掉第一处 `lowBalance && `）。
>
> **验收**：
> - `tests/test_ui_closeout_*.py` 全绿；
> - 手工变异复现：按 A.4 坏副本 1、2 的写法真实改 `frontend/app/history/page.tsx`（改完按字节还原），`test_ui_closeout_history_keyboard.py` 必须有真实用例变红；把 `SCAN_BASES` 改成不存在的目录，`test_no_backdrop_tailwind_variants_remain` 必须变红；
> - HEAD 对照按规格 §5 第 5 条重跑：cost_hint / history_keyboard / dialog_scrim 仍全部 FAIL 且都是 `AssertionError`，structure_guards 全 PASS；
> - 全量 pytest 后台跑完：0 failed、0 skipped，passed = 7855 + 本轮新增用例数；
> - `git diff --stat` 中实现文件与门禁文件行数与本轮复核时相同（`git diff` 与 `.review/diff.patch` 相比只能多出新测试文件的变化——新测试是未跟踪文件，所以 `git diff` 应完全不变）。
> - 在 `03-report.md` 追加 R2 记录：改了什么、新增用例数、上述变异的实际输出。
