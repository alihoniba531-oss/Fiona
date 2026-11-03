# 返修单 R2：T5 新测试补强（2026-11-02）

独立复核（`docs/tasks/2026-11-02-ui-closeout/04-review.md`）结论：实现代码 T1–T4 与规格逐条一致、白名单与字面量锁全部成立、§5 七条全过，**不通过的原因只在两个新测试文件**。本轮只改测试，实现一个字节不动。规格以 v1.2 为准（只同步了 §5.6 / §5.7 措辞，判据没变）。

## 复核发现（已由派单方亲自复现）

1. `backend/tests/test_ui_closeout_history_keyboard.py` 的 `tabIndex={-1}`（`:55`）、`aria-hidden="true"`（`:60`，HEAD 上就有 7 处，≥ 6 恒真）、`onBlur={() => setRawChip(null)}`（`:61`）都是全文件计数，不绑定到两个原生日期框。把两处 `tabIndex={-1}` 从原生框挪到两个按钮上（T2 行为整个反转：原生框回到 Tab 序列、按钮退出），或删掉两个原生框的 `aria-hidden="true"`，该文件 4 条 + `test_empty_states_history_dates.py` 4 条**全绿**。
2. `backend/tests/test_ui_closeout_dialog_scrim.py::test_no_backdrop_tailwind_variants_remain` 有空集问题：`_source_map` 对不存在的目录静默 `continue`，`SCAN_BASES` 三个目录都不存在时返回空字典，`assert_no_backdrop_utility({})` 什么也不查，用例照样通过。
3. （可优化，一并做）`backend/tests/test_ui_closeout_cost_hint.py` 没锁 T1 的首次判定逻辑：`setFirstVisit(firstVisitDecided.current)` 改成 `setFirstVisit(false)`、去掉 `firstVisitDecided.current === null` 的 ref 守卫、第一处余额后缀去掉 `lowBalance && `，5 条用例全绿。

## 白名单（本轮）

只许改这三个文件（都在规格 §3.1「新增」里）：

- `backend/tests/test_ui_closeout_history_keyboard.py`
- `backend/tests/test_ui_closeout_dialog_scrim.py`
- `backend/tests/test_ui_closeout_cost_hint.py`

以及 `docs/tasks/2026-11-02-ui-closeout/03-report.md`（追加 R2 记录）和 `impl/A.md`（追加本轮记录）。实现文件、门禁文件、`test_ui_closeout_structure_guards.py`、其他既有测试一个字节不许动；`git diff`（已跟踪文件）改完后必须与改前完全相同。git 只做读操作。不得调用 subagent / subagent_fork / workflow，主代理直接做。

pytest 写法沿用规格 §3.5：在 `backend/` 下 `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider …`。

## A. `test_ui_closeout_history_keyboard.py`

源码里的事实（`frontend/app/history/page.tsx`，派单方实数）：`'aria-hidden="true"\n                  tabIndex={-1}'`（18 个空格缩进）恰 2 处；`'                  tabIndex={-1}\n'` 恰 2 处；`'                  type="button"\n'` 恰 2 处；两个原生框的 `<input` 标签内各含 `aria-hidden="true"`、`tabIndex={-1}`、`onBlur={() => setRawChip(null)}`，以及各自的 `rawChip === "from"` / `rawChip === "to"`；两个 chip 按钮是 `<button` 起、`/>` 止的多行标签，标签内没有 `tabIndex`、没有 `aria-hidden`。

1. `check_date_input_pairing`：对 `from_tags[0]` 的 `expected` 元组追加 `'aria-hidden="true"'`、`"tabIndex={-1}"`、`"onBlur={() => setRawChip(null)}"`、`'rawChip === "from"'`；对 `to_tags[0]` 同样追加，最后一项换成 `'rawChip === "to"'`。原有 `value` / `data-chip` / `ref` 三项保留。
2. 新增 `check_date_buttons_stay_in_tab_order(source)`：按行找到含 `FROM_BUTTON_LABEL` 的那一行（恰 1 行），向上找最近一行去空白后等于 `<button`，向下找最近一行去空白后等于 `/>`，取这一段为按钮标签；断言段内不含 `tabIndex`、不含 `aria-hidden`；`TO_BUTTON_LABEL` 同理。新增真实用例 `test_date_buttons_stay_in_tab_order` 调用它。
3. `test_selfcheck_swapped_labels_are_rejected` 开头先对原文调用 `check_date_input_pairing` 和 `check_date_button_pairing`（必须通过），再做现有的两个对调断言。
4. 新增三条自检用例。每条先断言原文通过相关检查，再断言被替换串在原文中的出现次数符合下列预期，最后断言坏副本抛 `AssertionError`：
   - `test_selfcheck_inputs_without_aria_hidden_are_rejected`：把 `'aria-hidden="true"\n                  tabIndex={-1}'`（恰 2 处）替换成 `'tabIndex={-1}'`，`check_date_input_pairing` 必须抛；
   - `test_selfcheck_tabindex_moved_to_buttons_is_rejected`：删掉 `'                  tabIndex={-1}\n'`（恰 2 处），再把 `'                  type="button"\n'`（恰 2 处）替换成 `'                  type="button"\n                  tabIndex={-1}\n'`；替换后 `tabIndex={-1}` 仍恰 2 处；`check_date_input_pairing` 与 `check_date_buttons_stay_in_tab_order` 都必须抛；
   - `test_selfcheck_swapped_raw_chip_keys_are_rejected`：用现有 `_swap` 把 `'rawChip === "from"'` 与 `'rawChip === "to"'` 对调，`check_date_input_pairing` 必须抛。

## B. `test_ui_closeout_dialog_scrim.py`

1. 新增 `assert_scan_is_not_empty(sources, *, require_css=True)`：断言 `SCAN_BASES` 每个目录 `is_dir()`；`sources` 非空；`"frontend/components/SongProjectCard.tsx"` 在 `sources` 的键里；`require_css` 为真时还要求 `"frontend/app/globals.css"` 在键里。
2. `test_no_backdrop_tailwind_variants_remain` 在 `assert_no_backdrop_utility(sources)` 之前先调用 `assert_scan_is_not_empty(sources)`；`test_all_dialogs_use_scrim_dialog` 在 `assert_dialogs_have_scrim(sources)` 之前先调用 `assert_scan_is_not_empty(sources, require_css=False)`（它扫的是 `.tsx`）。
3. 自检：新增 `test_selfcheck_empty_scan_is_rejected`，断言 `assert_scan_is_not_empty({})` 抛 `AssertionError`，且 `assert_scan_is_not_empty({"frontend/app/globals.css": ""})`（缺组件文件）也抛。

## C. `test_ui_closeout_cost_hint.py`

源码里的事实（`frontend/app/page.tsx`，按字节读、开头有 BOM；派单方实数见规格 T1 第 3、6 条）：`if (firstVisitDecided.current === null) firstVisitDecided.current = markCostHintSeen(username);` 恰 1 处；`setFirstVisit(firstVisitDecided.current);` 恰 1 处；`{lowBalance && <>，还剩 <span className="readout font-normal">{balance}</span> 颗</>}` 恰 2 处。**先用 `grep -c` / Python 实数确认，不符就停下来说明，不要改 `page.tsx`。**

1. `check_cost_hint_contract` 加三条断言：上述三个字面量分别恰 1、1、2 次。
2. 三条自检用例（每条先断言原文通过，再断言替换前出现次数符合预期，再断言坏副本抛 `AssertionError`）：
   - `setFirstVisit(firstVisitDecided.current);` → `setFirstVisit(false);`；
   - 去掉 `if (firstVisitDecided.current === null) ` 前缀（保留后面的赋值）；
   - 第一处 `{lowBalance && <>，还剩` → `{<>，还剩`（只替换第一次出现，用 `replace(..., 1)`）。

## 验收（全部跑完，原始输出贴进 03-report.md）

1. `tests/test_ui_closeout_*.py` 全绿，并用 `--collect-only -q` 实数四个文件的用例数（预期 cost_hint 8、dialog_scrim 4、history_keyboard 8、structure_guards 7，合计 27；以实数为准，写明）。
2. **真实变异复现（改完按字节还原并核对 sha256）**：
   - 按 A.4 第 1 条的写法真实改 `frontend/app/history/page.tsx` → `test_ui_closeout_history_keyboard.py` 必须有真实用例（非自检）变红；
   - 按 A.4 第 2 条的写法真实改 → 同上，且 `test_date_buttons_stay_in_tab_order` 变红；
   - 把 `SCAN_BASES` 临时改成三个不存在的目录 → `test_no_backdrop_tailwind_variants_remain` 必须变红（改完还原）；
   - 按 C.2 第 1 条真实改 `page.tsx`（保留 BOM）→ cost_hint 有真实用例变红。
3. HEAD 对照按规格 §5 第 5 条重跑（`git archive HEAD` 到 mktemp 目录，拷 4 个新测试 + 两个门禁文件，不拷 `test_ui_polish_page_contracts.py`）：cost_hint / history_keyboard / dialog_scrim 的真实用例在 HEAD 上 FAIL 且都是 `AssertionError`；structure_guards 全 PASS；用 `--tb=line -rA` 贴末行。
4. 全量 pytest 用后台任务跑完：0 failed、0 skipped，`passed = 7855 + 本轮新增用例数`。
5. `git diff`（已跟踪文件）与改前逐字节相同：开工前先 `git diff | shasum -a 256` 记下，收尾再算一次比对；`git status --porcelain` 的未跟踪集合不变（只多不出新文件）。
6. `03-report.md` 追加「R2 记录」一节（复核发现、改了什么、新增用例数、上述变异与 HEAD 对照的原始输出、全量 pytest 末行）；`impl/A.md` 追加本轮记录。报告里不写本机绝对路径（用 `<工作树>` / `<HEAD 副本>`）。

## 何时停下来问

只有「规格 / 本单与源码事实矛盾」（如 C 的三个字面量实数不符、A 的缩进不是 18 个空格）才停下来说明；只影响「怎么写断言」的自行决定并在报告里写明理由。任何情况不回滚已完成的工作，不动实现文件。

最终回复：改了哪三个文件、A/B/C 逐条对应、验收 1–6 的实际输出、未完成或需人工确认的地方。
