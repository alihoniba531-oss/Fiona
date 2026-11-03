# 04 复核（第二轮）：UI 复核收尾 R2 返修核验

- 复核方：独立复核（第二轮），和实现方、规格作者没有对话上下文。
- 依据：`docs/tasks/2026-11-02-ui-closeout/02-spec.md` v1.2；第一轮复核 `04-review.md` §4/§6；返修单 `05-fix-r2.md`。
- 范围：只核验第一轮 §4 两项必须修复项和返修单 A/B/C 是否按字面落地。实现文件（T1–T4）本轮不复审，只证明它们一个字节没变。新发现的问题一律放在 §5「可优化项」。
- `03-report.md` 的「R2 记录」和 `impl/A.md` 只当线索用，下面每个结论都是本轮亲自重跑得到的。

## 1. 结论：**通过**

- **4.1 已修好**：两个原生日期框的 `aria-hidden="true"`、`tabIndex={-1}`、`onBlur={() => setRawChip(null)}`，以及各自的 `rawChip === "from"` / `"to"`，现在都按 `<input …/>` 标签逐框检查；按钮里不能出现 `tabIndex` / `aria-hidden` 的检查也绑定在 `<button` … `/>` 这一段上。在真实源码上做 M17、M18、rawChip 对调三项变异，每项都有非自检的真实用例变红。
- **4.2 已修好**：`SCAN_BASES` 改成三个不存在的目录后，`test_no_backdrop_tailwind_variants_remain` 变红；`assert_scan_is_not_empty({})` 会抛 `AssertionError`。
- **C 项已落地**：在 `page.tsx` 上真实做 M19、M20、M21 三项变异，`test_cost_hint_contract` 都变红。
- 改动范围：`git diff` 与 `.review/diff.patch` 逐字节相同；`structure_guards` 与第一轮的副本逐字节相同；三个改动过的测试相对第一轮只有新增，没有删掉或放宽原有断言。
- 回归：`tests/test_ui_closeout_*.py` 共 27 passed（实数 8/4/8/7）。HEAD 对照结果符合规格 §5 第 5 条。全量 pytest **7863 passed，0 failed，0 skipped**，7863 = 7855 + 8，其中 8 是本轮新增用例数。
- 收尾时工作区与 `.review/snapshot.sha256` 一致。

## 2. 两项必须修复项逐条核验

### 2.0 改动范围与快照

```text
$ diff <(git diff) .review/diff.patch && echo DIFF_SAME
DIFF_SAME
$ (git diff; for f in $(cat .review/untracked.txt); do echo "== $f"; cat "$f"; done) | shasum -a 256
1d612c1f082388ce0bc6b96a3d17aafadfba863e01acc21dc44a2728edac0efc  -
$ cat .review/snapshot.sha256
1d612c1f082388ce0bc6b96a3d17aafadfba863e01acc21dc44a2728edac0efc
$ cmp backend/tests/test_ui_closeout_structure_guards.py .review/r1/test_ui_closeout_structure_guards.py && echo SAME
SAME
```

- 开工时和收尾时各算了一次快照哈希，两次都与 `.review/snapshot.sha256` 相同。
- `git status --porcelain` 的未跟踪集合仍是 4 个新测试文件加 `docs/tasks/2026-11-02-ui-closeout/`。
- 三个改动过的测试文件，相对 `.review/r1/` 的 `diff` 里删除行只有 `history_keyboard` 的两行。这两行是 `check_date_input_pairing` 原来的三元组 `for expected in (...)`，被扩写成七元组，原有的 value / data-chip / ref 三项都保留了。`cost_hint` 和 `dialog_scrim` 没有删除行。
- 局限：仓库里没有第一轮时 `03-report.md`、`impl/A.md` 等文档的副本，所以只能证明「已跟踪文件 diff 不变、未跟踪集合不变」，没法逐字节证明其余文档没动过。

### 2.1 必须修复项 4.1（`test_ui_closeout_history_keyboard.py`）

先实数确认源码事实（`frontend/app/history/page.tsx`，用 Python 计数）：

```text
2 'aria-hidden="true"\n                  tabIndex={-1}'
2 '                  tabIndex={-1}\n'
2 '                  type="button"\n'
1 'rawChip === "from"'
1 'rawChip === "to"'
9 'aria-hidden="true"'      # 全文件 9 处，旧的 >= 6 对原生框恒真
2 'tabIndex={-1}'
```

逐条对照返修单 A 的代码：

| 返修单 | 落地位置 | 核验 |
|---|---|---|
| A.1 `check_date_input_pairing` 追加 4 项 | `:83–106` 的两个七元组。`from` 侧以 `'rawChip === "from"'` 结尾，`to` 侧以 `'rawChip === "to"'` 结尾。检查对象是 `INPUT_TAG`（`<input\b.*?/>`）中含 `type="date"` 的标签，并断言恰好 2 个 | ✅ 按标签检查，不按全文件计数 |
| A.2 `check_date_buttons_stay_in_tab_order` + 真实用例 | `:128–143`。按 label 找到恰好 1 行，向上找最近一行去空白后等于 `<button` 的行，向下找最近一行去空白后等于 `/>` 的行，并断言 `start < label < end`，然后在这一段里断言不含 `tabIndex`、不含 `aria-hidden`。真实用例 `test_date_buttons_stay_in_tab_order` 在 `:164` | ✅ 见下方绑定性证明 |
| A.3 对调自检先跑正样本 | `:168–171` 先对原文调用 `check_date_input_pairing` 和 `check_date_button_pairing` | ✅ |
| A.4 三条新自检 | `:184` 先跑原文 → 断言出现 `count == 2` → 坏副本抛错。`:195` 先跑原文，两项检查都过 → 两个计数 `== 2` → 替换后断言 `tabIndex={-1}` 仍恰好 2 处 → 两项检查都抛错。`:212` 先跑原文 → `_swap` 对调 → 抛错 | ✅（第 3 条只断言两个键存在，没断言恰好 1 次，见 §5.1） |

按钮段的检查确实绑定在按钮标签上（看代码，并用变异验证）：

- 原文里每个 `<button` 行的上一行，都是带 `aria-hidden="true"` 的可见 span（第 225–226 行、250–251 行）。原文能通过检查，说明这一段从 `<button` 开始，没有把上面的 span 吞进来。
- M18b（只给「从」按钮加一行 `aria-hidden="true"`，原生框不动）：`test_date_buttons_stay_in_tab_order` 变红，报 `:143 the 从（开始日期） chip button must not be hidden from AT`。其余真实用例都是绿的，所以变红只来自按钮段。
- M18c（`tabIndex={-1}` 写在 `<button tabIndex={-1}` 同一行，这时 `<button` 行不再是光秃的一行）：仍然变红。定位器在格式变化时是失败关闭的（误红），不会失败放行。

### 2.2 必须修复项 4.2（`test_ui_closeout_dialog_scrim.py`）

| 返修单 | 落地位置 | 核验 |
|---|---|---|
| B.1 `assert_scan_is_not_empty(sources, *, require_css=True)` | `:46–57`：三个 `SCAN_BASES` 都要 `is_dir()`；`sources` 非空；必须含 `frontend/components/SongProjectCard.tsx`；`require_css` 为真时还必须含 `frontend/app/globals.css` | ✅ |
| B.2 两个真实用例先调用它 | `:165` 的 `test_all_dialogs_use_scrim_dialog` 用 `require_css=False`；`:208` 的 `test_no_backdrop_tailwind_variants_remain` 用默认值，且都在主断言之前调用 | ✅ |
| B.3 空集自检 | `:222–226`：`assert_scan_is_not_empty({})` 和 `({"frontend/app/globals.css": ""})` 都在 `pytest.raises(AssertionError)` 里 | ✅ |

`assert_scan_is_not_empty({})` 抛错是因为 `sources` 为空（第 50 行），不是别的断言先触发：三个扫描目录在本机都存在，所以 `is_dir()` 那一步不会先失败。

## 3. 变异实验记录

- 做法：用一个仓库外的临时脚本按字节读出原文件，先断言被替换串的出现次数，再写入坏副本跑对应测试，结束后在 `finally` 里按字节写回，并比对 sha256。
- `page.tsx` 的坏副本先断言仍以 `EF BB BF` 开头。
- 所有变异都在全量 pytest 跑完之后才开始，避免干扰全量结果。
- history 相关变异同时跑了 `tests/test_ui_closeout_history_keyboard.py` 和 `tests/test_empty_states_history_dates.py`。

| 编号 | 改动（真实文件） | 变红的真实用例（非自检） | 结果末行 | 还原 |
|---|---|---|---|---|
| M17 | `history/page.tsx`：两个原生框删掉 `aria-hidden="true"`，即两处 `'aria-hidden="true"\n                  tabIndex={-1}'` 换成 `'tabIndex={-1}'` | `test_date_inputs_pair_with_their_own_chips`（`:92 … must carry aria-hidden="true"`） | 5 failed, 7 passed | ✅ sha 一致 |
| M18 | `history/page.tsx`：按 A.4 写法删掉两行 `                  tabIndex={-1}\n`，在两处 `type="button"` 后插入 | `test_date_inputs_pair_with_their_own_chips`（`:92 … tabIndex={-1}`）和 `test_date_buttons_stay_in_tab_order`（`:142 … must stay in the Tab order`） | 6 failed, 6 passed | ✅ |
| M23 | `history/page.tsx`：`rawChip === "from"` 与 `rawChip === "to"` 对调（各 1 处） | `test_date_inputs_pair_with_their_own_chips`（`:92 … rawChip === "from"`） | 5 failed, 7 passed | ✅ |
| M18b | `history/page.tsx`：只给「从」按钮加 `aria-hidden="true"` | `test_date_buttons_stay_in_tab_order`（`:143`） | 2 failed, 10 passed | ✅ |
| M18c | `history/page.tsx`：同 M18，但写成 `<button tabIndex={-1}` | `test_date_inputs_pair_with_their_own_chips`、`test_date_buttons_stay_in_tab_order` | 6 failed, 6 passed | ✅ |
| E1 | `test_ui_closeout_dialog_scrim.py`：`SCAN_BASES` 改成 `frontend/app-missing`、`components-missing`、`lib-missing` | **`test_no_backdrop_tailwind_variants_remain`**（`:49 scan base is missing`）和 `test_all_dialogs_use_scrim_dialog` | 2 failed, 2 passed | ✅ |
| E2 | 同文件：`ALL_SOURCE_EXTS` 去掉 `.css` | `test_no_backdrop_tailwind_variants_remain`（`:55 source scan must include globals.css`） | 1 failed, 3 passed | ✅ |
| E3 | 同文件：`ALL_SOURCE_EXTS = ()` | `test_no_backdrop_tailwind_variants_remain`（`:50 source scan returned no files`） | 1 failed, 3 passed | ✅ |
| M19 | `page.tsx`（保留 BOM）：`setFirstVisit(firstVisitDecided.current);` → `setFirstVisit(false);` | `test_cost_hint_contract`（`:66`） | 8 failed | ✅ |
| M20 | `page.tsx`：删掉 `if (firstVisitDecided.current === null) ` 守卫 | `test_cost_hint_contract`（`:63`） | 8 failed | ✅ |
| M21 | `page.tsx`：只把第一处 `{lowBalance && <>，还剩` 换成 `{<>，还剩` | `test_cost_hint_contract`（`:69`） | 8 failed | ✅ |

补充说明：

- M17、M18 下，第一轮就有的 `test_date_chip_keyboard_contract` 和既有的 `test_empty_states_history_dates.py` 四条仍然是绿的。它们本来就是全文件计数，这在预期之内；拦截现在由新的逐标签检查负责。
- cost_hint 的 7 条自检都先对原文跑 `check_cost_hint_contract`，所以原文被改坏时自检也会一起变红。这是设计如此，不是空跑。

### 3.1 回归

```text
$ cd backend && <§3.5 写法> -m pytest -q -p no:cacheprovider tests/test_ui_closeout_*.py
27 passed in 0.25s
$ … --collect-only tests/test_ui_closeout_*.py
27 tests collected        # 逐文件：cost_hint 8、dialog_scrim 4、history_keyboard 8、structure_guards 7
```

第一轮副本 `.review/r1/` 的用例数是 5/3/4/7，合计 19，所以本轮新增 8 条。

HEAD 对照按规格 §5 第 5 条做：`git archive HEAD` 解到 mktemp 目录，拷入 4 个新测试和两个门禁文件，`cp -cR` 拷入 `node_modules`，不拷 `test_ui_polish_page_contracts.py`，然后用本工作树的 venv、`--tb=line -rA` 运行：

```text
FAILED test_ui_closeout_cost_hint.py ×8           （:51 AssertionError: the footer must accept a nullable balance prop）
FAILED test_ui_closeout_dialog_scrim.py ×3 真实用例
       （:123 ConfirmDialog 缺 scrim-dialog；:134 found 4 ::backdrop；:157 SongProjectCard.tsx:340 backdrop: utility）
PASSED test_ui_closeout_dialog_scrim.py::test_selfcheck_empty_scan_is_rejected   （纯自检，不读源码）
FAILED test_ui_closeout_history_keyboard.py ×8    （:55 / :92 / :121 / :133 AssertionError）
PASSED test_ui_closeout_structure_guards.py ×7
FAILED test_design_system_gate.py::test_token_layer；其余 gate 5 条 PASS；test_design_system_css.py PASS
20 failed, 14 passed in 1.93s
失败类型统计：20 E AssertionError（无 ImportError / FileNotFoundError）
```

- 在 HEAD 上，`test_no_backdrop_tailwind_variants_remain` 是被真实存在的 `backdrop:` 工具类拦下的，不是空集。
- 空集自检在 HEAD 上 PASS，和门禁的两条自检一样，属于不读仓库源码的纯自检，与本轮「真实用例在 HEAD 上 FAIL」的判据不冲突。

全量 pytest（后台跑完，`-rfEs`）：

```text
7863 passed, 35 warnings in 321.18s (0:05:21)
exit=0
日志中 SKIPPED 0 条，FAILED/ERROR 0 条
```

7863 = 7855 + 8。

## 4. 必须修复项

无。第一轮 4.1、4.2 都没有残留。

## 5. 可优化项（不阻断，留给用户裁决）

1. **rawChip 对调自检没有断言出现次数**：`test_selfcheck_swapped_raw_chip_keys_are_rejected`（`:215`）直接用 `_swap`，`_swap` 只断言两个键都存在，没有断言各恰好 1 次。返修单 A.4 第 3 条没给次数预期，所以字面上合规；当前实数是各 1 次。建议补 `assert source.count('rawChip === "from"') == 1`，`"to"` 同样补一条。
2. **空集自检没有正样本对照**：`test_selfcheck_empty_scan_is_rejected` 没有先断言真实扫描能通过 `assert_scan_is_not_empty`。返修单 B.3 没要求这一步，而且两个真实用例都先调用了它，合起来不会出错。但单看这条自检，证明不了「拒绝是因为空」。
3. **旧的全文件计数仍留在 `check_date_chip_keyboard_contract`**：`:55`、`:60`、`:61` 三条全局计数没删也没收紧，其中 `aria-hidden="true"` 的 `>= 6` 实际是 9，对原生框恒真，提示文案也不准确。逐框绑定已经由 `check_date_input_pairing` 负责，这几条现在只是冗余，不是漏洞。可以改成 `== 9`，或者删掉以免误导。
4. **按钮段定位依赖排版**：定位器要求 `<button` 和 `/>` 各自独占一行。prettier 改排或改成带子元素的 `<button>…</button>` 时会误红（M18c 已证明是失败关闭），不会误绿。以后若改排版，需要同步改这个检查。
5. **第二轮输入缺文档基线**：`.review/r1/` 只有四个测试的副本，没有第一轮时的 `03-report.md` / `impl/*.md`，复核方没法逐字节确认本轮只改了 `03-report.md` 和 `impl/A.md` 两个文档。建议以后派单把文档的第一轮副本也放进 `.review/r1/`。
6. 第一轮 §5 列的其余可优化项（换号余额串号、T2 退回路径的无障碍、F7 边角等）本轮不在范围内，状态不变。

## 6. 给执行者的三次修改指令

无必须修复项，不需要第三次修改。§5 第 1–3 条如果用户决定要做，可以作为下一批测试补强的一部分，只改 `backend/tests/test_ui_closeout_history_keyboard.py` 和 `backend/tests/test_ui_closeout_dialog_scrim.py`。
