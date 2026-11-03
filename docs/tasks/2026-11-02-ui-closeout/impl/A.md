# Agent A 执行记录（T1 + T5 `test_ui_closeout_cost_hint.py`）

## 结论：按停止条件中止，未改代码

按规格 §4 T1 实现会让白名单外既有测试
`backend/tests/test_ui_polish_page_contracts.py::test_page_readout_numbers_are_not_bold`
必红（`assert 4 == 2`），且 §4 T1 第 6 条与 §4 T5 里写死的字面量计数互相锁定，
不存在同时满足 T1、T5 和该既有测试的写法。

依据规格 §7「按规格做会让 §3.1 之外的既有测试变红」以及派发说明「立即停止进一步改动」，
本 agent：

- **没有修改** `frontend/app/page.tsx`；
- **没有新建** `backend/tests/test_ui_closeout_cost_hint.py`；
- 只新增本记录 `docs/tasks/2026-11-02-ui-closeout/impl/A.md`。

`frontend/app/page.tsx` 未被触碰，BOM 仍为 `ef bb bf`：

```text
$ git diff --stat -- frontend/app/page.tsx
（空）
$ head -c 3 frontend/app/page.tsx | xxd
00000000: efbb bf                                  ...
```

## 冲突事实与推导

HEAD `bccbf9f` 的 `frontend/app/page.tsx` 里 `className="readout font-normal"` 恰 2 处：

```text
$ grep -n 'className="readout font-normal"' frontend/app/page.tsx
440:    </div> : <span>每条消息消耗 <span className="readout font-normal">10</span> 颗草莓</span>}
2576:                  <span className="readout font-normal" style={{ color: strawberryBalance !== null && strawberryBalance < 30 ? "var(--seal)" : "var(--ink)" }}>
```

`test_page_readout_numbers_are_not_bold`（`test_ui_polish_page_contracts.py:176-179`）断言：

```python
assert source.count('className="readout font-normal"') == 2
```

T1 第 6 条要求新增两个余额数字 span，T5 还写死其中字符串各出现 2 次：

- `: showCost && ...` 分支里的 `…，还剩 <span className="readout font-normal">{balance}</span> 颗`（新增 1 处）；
- 图片模式分支里的 `每条消息消耗 <span className="readout font-normal">10</span> 颗草莓{lowBalance && <>，还剩 <span className="readout font-normal">{balance}</span> 颗</>}`（原有的 10 保留 + 新增余额 1 处）。

T5 明写 ``，还剩 <span className="readout font-normal">{balance}</span> 颗`` 恰 2 次，
因此实现后 `className="readout font-normal"` 的最少次数是
`1（T1 图片模式保留的 10，且 test_mobile_chat_fix.py:237 锁死）+ 2（T5 要求的两个余额 span）= 3`；
按 T1 原文实际落地是 `1（10）+ 1（2576 手机工具栏）+ 2（两个余额 span）= 4`。
既有测试要求恰为 2，差 2 处。第 2576 行无论删不删都只能降到 3，仍不等于 2。

`每条消息消耗 <span className="readout font-normal">10</span> 颗草莓` 还被
`test_mobile_chat_fix.py:237` 锁为恰 1 次，不能靠改掉这个 10 的类名来腾出计数空间。

## 复现实验（在 /tmp 副本，不动工作树）

把 HEAD 的 `page.tsx` 复制到 `/tmp/fiona-t1-probe/`，用脚本
`/tmp/fiona-t1-probe/apply_t1.py` 严格按 §4 T1 第 1–7 条做文本替换
（BOM 按 `rb`/`wb` 保留；仅用于验证，不写工作树）。结果：

```text
$ python3 /tmp/fiona-t1-probe/apply_t1.py
written /tmp/fiona-t1-probe/page.tsx BOM: efbbbf
readout class count: 4
OK  'balance: number | null;' 1 want 1
OK  'balance={strawberryBalance}' 1 want 1
OK  'function markCostHintSeen(username: string): boolean {' 1 want 1
OK  '`fiona_cost_hint_seen:${encodeURIComponent(username)}`' 1 want 1
OK  'const lowBalance = balance !== null && balance < 30;' 1 want 1
OK  'const showCost = firstVisit || lowBalance;' 1 want 1
OK  'const hasContent = (chatMode && !!config) || showCost || (chatMode && !!error);' 1 want 1
OK  ': showCost && <span className={cn("min-w-0 truncate", lowBal' 1 want 1
OK  '</div> : showCost && <span className={cn(lowBalance && "text' 1 want 1
OK  '，还剩 <span className="readout font-normal">{balance}</span> 颗' 2 want 2
OK  '<ChatModelFooter ' 1 want 1
```

用工作树同一个测试文件在 /tmp 假仓库里跑那条既有测试：

```text
$ mkdir -p /tmp/fiona-t1-probe/backend/tests /tmp/fiona-t1-probe/frontend/app
$ cp backend/tests/test_ui_polish_page_contracts.py /tmp/fiona-t1-probe/backend/tests/
$ cp /tmp/fiona-t1-probe/page.tsx /tmp/fiona-t1-probe/frontend/app/page.tsx
$ cd /tmp/fiona-t1-probe/backend && env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    <工作树>/backend/.venv/bin/python \
    -m pytest -q -p no:cacheprovider \
    tests/test_ui_polish_page_contracts.py::test_page_readout_numbers_are_not_bold
F                                                                        [100%]
=================================== FAILURES ===================================
____________________ test_page_readout_numbers_are_not_bold ____________________

    def test_page_readout_numbers_are_not_bold():
        source = PAGE.read_text()
>       assert source.count('className="readout font-normal"') == 2
E       assert 4 == 2
E        +  where 4 = <built-in method count of str object at 0x7bd56b8000>('className="readout font-normal"')

tests/test_ui_polish_page_contracts.py:178: AssertionError
=========================== short test summary info ============================
FAILED tests/test_ui_polish_page_contracts.py::test_page_readout_numbers_are_not_bold
1 failed in 0.02s
```

工作树 HEAD 基线（未改 page.tsx）同一测试通过：

```text
$ cd backend && env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    .venv/bin/python -m pytest -q -p no:cacheprovider \
    tests/test_ui_polish_page_contracts.py::test_page_readout_numbers_are_not_bold
1 passed in 0.02s
```

完整两个文件基线（工作树当前，其他 agent 的改动未触及这两个断言）：

```text
$ cd backend && env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    .venv/bin/python -m pytest -q -p no:cacheprovider \
    tests/test_ui_polish_page_contracts.py tests/test_mobile_chat_fix.py
..................                                                       [100%]
18 passed in 0.21s
```

## 另一个（非阻塞的）规格张力

§4 T5 要求：含 `border-t border-[color:var(--carve)] pt-2` 的那一行「且含
`!hasContent && "max-md:hidden"` 与 `Enter 发送，Shift + Enter 换行`」。
§4 T1 第 5 条的代码块把「Enter 发送，Shift + Enter 换行」放在容器 `<div>` 的下一行。
按 T5 字面写测试会失败。可以在实现时把 `<span>Enter 发送…</span>` 并到容器 `<div>`
那一行来同时满足两者（行为不变，只偏离 T1 的换行排版）；这一点不是本次中止的原因，
仅记录给主代理，实现时需作决定。

## 供主代理决策的出路（都需规格/白名单层面拍板）

1. 放行修改既有测试 `test_ui_polish_page_contracts.py`，把
   `source.count('className="readout font-normal"') == 2` 改为 `== 4`
   （该文件不在 §3.1 白名单，当前禁止）。
2. 修改 T1/T5 的余额 span 写法，例如改成
   `className={cn("readout font-normal")}` 或 `className="readout"`，
   让 `className="readout font-normal"` 计数保持 2；T5 的对应字面量需同步改。
   视觉上仍可保留 `font-normal`，但这是对 §4 T1 第 6 条 / T5 第 3 条的偏离，
   当前规格不允许自行改。
3. 其他任何方案都必须删掉 T5 要求的两个余额 span 之一，或改掉被
   `test_mobile_chat_fix.py` 锁死的 10 的 span，均不可行。

## 未做与遗留

- 未改 `frontend/app/page.tsx`，因此 T1 的所有功能点均未落地。
- 未新建 `backend/tests/test_ui_closeout_cost_hint.py`，因此没有该文件的
  HEAD 对照结果；HEAD 对照的失败原因分析已由上面的计数实验覆盖。
- 未跑 `npx tsc --noEmit`（无页面改动）。
- 没有执行任何 git 写操作。

---

## R1 追加（2026-11-02，裁决后由主代理执行）

作者裁决（v1.1）：采用方案 1。`backend/tests/test_ui_polish_page_contracts.py` 加入白名单，只把 `test_page_readout_numbers_are_not_bold` 的 `== 2` 改成 `== 4`；T1/T5 的两个余额数字按规格原文使用 `className="readout font-normal"`。`::backdrop {` 计数改为按规则行数；页脚容器与 `Enter 发送` 提示按 T1 第 5 条分成两行。

主代理实际完成：

- `frontend/app/page.tsx` 用 Python `rb`/`wb` 按字节改写，保留 BOM；按 T1 第 1–7 条加入 `costHintSeenKey` / `markCostHintSeen`、`balance` prop、`firstVisit` 状态与 effect、`lowBalance` / `showCost` / `hasContent`、新容器与两处 `showCost &&` 守卫、`balance={strawberryBalance}`。`label` / `labelTitle`、思考档、「改用」按钮、错误行未改。
- 新建 `backend/tests/test_ui_closeout_cost_hint.py`（5 个用例：1 个真实契约检查 + 4 个改坏副本自检）；每个自检先要求真实源码通过，因此在 HEAD 上 5 个用例都因同一前置断言失败。
- `backend/tests/test_ui_polish_page_contracts.py` 只改指定数字，`git diff -U0` 为单 hunk、一行 `-`、一行 `+`。
- 定向测试：`test_ui_closeout_cost_hint.py` + `test_mobile_chat_fix.py` + `test_ui_polish_page_contracts.py` 共 `23 passed`；`npx tsc --noEmit` 退出码 0。
- 全量 pytest：`7855 passed, 35 warnings in 313.74s (0:05:13)`，0 failed、0 skipped。
- HEAD 对照：`test_ui_closeout_cost_hint.py` 5 个用例全部 FAIL，原因均为 `AssertionError`（HEAD 缺 `balance: number | null;` 等 T1 契约）。
- BOM 复核：`head -c 3 frontend/app/page.tsx | xxd` 仍为 `ef bb bf`。

原「阻塞」结论保留在上文，作为 v1 首轮记录；R1 已按作者裁决解除阻塞。

---

## R2 追加（2026-11-02，独立复核后的 T5 测试补强）

独立复核 `04-review.md` 指出实现 T1–T4 与规格一致、白名单与 §5 七条全过；不通过只在两个新测试文件，另有 cost_hint 可优化项。本轮只改三个新测试文件，实现文件、门禁文件和 `structure_guards` 一个字节未动。

- `test_ui_closeout_history_keyboard.py`：input 配对逐框追加 `aria-hidden`、`tabIndex`、`onBlur`、各自的 `rawChip` 键；新增 `check_date_buttons_stay_in_tab_order` 与真实用例 `test_date_buttons_stay_in_tab_order`；`test_selfcheck_swapped_labels_are_rejected` 先要求原文通过两项配对；新增三条自检（删 input `aria-hidden`、把 `tabIndex` 挪到按钮、对调 `rawChip` 键）。
- `test_ui_closeout_dialog_scrim.py`：新增 `assert_scan_is_not_empty`，两个真实扫描用例先校验目录存在、非空、含 `SongProjectCard.tsx`（需要时还含 `globals.css`）；新增 `test_selfcheck_empty_scan_is_rejected`。
- `test_ui_closeout_cost_hint.py`：契约追加 ref 守卫行、`setFirstVisit(firstVisitDecided.current);`、两处 `lowBalance &&` 余额后缀三条断言；新增三条对应自检。

用例数：cost_hint 5→8、history 4→8、dialog 3→4、structure 7 不变；合计 27（+8）。`--collect-only -q` 为 `27 tests collected`；四个新测试文件 `27 passed`，带两个门禁为 `34 passed`。

真实变异复现（均改真实文件、跑完立即按字节恢复并核对 sha256）：

- 删 input `aria-hidden="true"` → `test_date_inputs_pair_with_their_own_chips` FAIL（1 failed, 3 passed, 4 deselected）。
- 把 `tabIndex={-1}` 从 input 挪到按钮 → input 配对与 `test_date_buttons_stay_in_tab_order` 均 FAIL（2 failed, 2 passed, 4 deselected）。
- `SCAN_BASES` 改成三个不存在目录 → `test_no_backdrop_tailwind_variants_remain` FAIL（`AssertionError: scan base is missing`）。
- `setFirstVisit(firstVisitDecided.current);` → `setFirstVisit(false);` → `test_cost_hint_contract` FAIL（`AssertionError: the effect must set firstVisit from the decided ref`）。

HEAD 对照（四个新测试 + 两个门禁，不拷 `test_ui_polish_page_contracts.py`）：`20 failed, 14 passed`；cost_hint 8/history 8 全 FAIL，dialog 3 个真实用例 FAIL、空集自检 PASS，structure_guards 7 PASS，gate `test_token_layer` FAIL、其余 5 PASS，CSS PASS；失败均为 `AssertionError`。

全量 pytest：`7863 passed, 35 warnings in 311.42s (0:05:11)`，0 failed、0 skipped（7855 + 本轮 8 = 7836 + 27）。

不可变性：开工前后 `git diff | shasum -a 256` 均为 `419727acfd3b3c6dabbf6ed6a3ed2f9c67bfa848b9970b47632f3faffea03fdd`；未跟踪集合不变；`page.tsx` 与 `history/page.tsx` 的 sha256 恢复至变异前。
