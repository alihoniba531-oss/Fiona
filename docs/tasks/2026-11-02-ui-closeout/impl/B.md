# B 执行记录：T2 日期 chip 接管键盘焦点 + 测试盲区 1

- 基线：`bccbf9f`（分支 `feat/ui-closeout`，工作树 `<工作树>`）
- 负责文件：`frontend/app/history/page.tsx`（修改）、`backend/tests/test_ui_closeout_history_keyboard.py`（新增）
- 未改其他任何文件；未做 git 写操作；未安装依赖；未调用 subagent / workflow。

## 1. 做了什么

严格按 `docs/tasks/2026-11-02-ui-closeout/02-spec.md` §4 T2 与 §4 T5（`test_ui_closeout_history_keyboard.py`，含盲区 1）实现。

`frontend/app/history/page.tsx`：

1. `:43` `searchRef` 之后新增 `dateFromRef`、`dateToRef` 与 `rawChip` 状态（`"from" | "to" | null`）。
2. `openDatePicker` 的 `try { input.showPicker(); } catch {` 原样保留，`catch` 内新增：按 `input.dataset.chip === "to"` 设 `rawChip`，再 `input.focus()`。
3. 「从」「到」两个 chip 各新增一枚铺满 chip 的透明 `<button type="button">`：`aria-label` 带中文日期，`onClick` 只打开自己 ref 对应的原生框；原生 `<input type="date">` 增加 `ref`、`aria-hidden="true"`、`tabIndex={-1}`、`data-chip`、`onBlur={() => setRawChip(null)}`，`className` 改为 `cn("absolute inset-0 h-full w-full cursor-pointer", rawChip === ... ? "opacity-100" : "opacity-0")`。
4. 原生框上的 `onClick` / `onKeyDown`（鼠标点按与已聚焦后的 Enter/Space）保持原样；`openDatePicker(e.currentTarget)` 仍恰 4 处。

`backend/tests/test_ui_closeout_history_keyboard.py`（4 个用例）：

1. `test_date_chip_keyboard_contract`：`tabIndex={-1}` 恰 2、`data-chip` 各 1、两个 `ref` 各 1、`aria-hidden="true"` ≥ 6、`onBlur` 恰 2；`setRawChip(input.dataset.chip === "to" ? "to" : "from");` 与 `input.focus();` 必须位于 `catch {` 之后、函数结束 `};` 之前。
2. `test_date_inputs_pair_with_their_own_chips`（盲区 1）：用 `<input\b.*?/>`（DOTALL）取全部 `<input>` 标签，其中 `type="date"` 恰 2 个；带 `aria-label="从（开始日期）"` 的标签必须同时带 `value={dateFrom}`、`data-chip="from"`、`ref={dateFromRef}`，「到」同理。两个 label 对调会失败。
3. `test_date_buttons_pair_with_their_own_inputs`（盲区 1 的按钮半边）：两个按钮 `aria-label={`…${dayFace(...)}`}` 各恰 1 行，且每个按钮的下一行（去首尾空白）恰等于对应 ref 的 `onClick` 行。
4. `test_selfcheck_swapped_labels_are_rejected`：互换两个原生框 `aria-label="…"` 字面量后，配对检查必须抛 `AssertionError`；互换两个按钮的 `aria-label={…}` 后，按钮配对检查必须抛 `AssertionError`。

## 2. 实际命令与结果

### 2.1 新测试 + 既有日期字面量锁（§3.5 写法，在 `backend/` 下）

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
  .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_ui_closeout_history_keyboard.py tests/test_empty_states_history_dates.py
```

```
........                                                                 [100%]
8 passed in 0.04s
```

### 2.2 既有 `test_empty_states_history_dates.py` 单独跑（要求全 PASS）

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
  .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_empty_states_history_dates.py
```

```
....                                                                     [100%]
4 passed in 0.02s
```

### 2.3 其余引用 `frontend/app/history/page.tsx` 的既有测试

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
  .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ui_polish_beijing_time.py tests/test_ui_polish_fix_r1.py
```

```
.......................                                                  [100%]
23 passed in 1.07s
```

### 2.4 前端类型检查（可选，门禁由主代理跑）

```bash
cd frontend
export npm_config_cache=/tmp/fiona-npm-cache
npx tsc --noEmit
```

无输出，退出码 0。

### 2.5 改动文件 lint

```bash
cd frontend
export npm_config_cache=/tmp/fiona-npm-cache
npx eslint app/history/page.tsx; echo "EXIT=$?"
```

```
EXIT=0
```

### 2.6 HEAD 对照（§5 第 5 条，必做）

在 `/tmp` 生成 HEAD 副本，只复制本工作树的新测试文件，用工作树 venv 按 §3.5 写法只跑该文件：

```bash
H=$(mktemp -d /tmp/fiona-head.XXXXXX)   # 实际：/tmp/fiona-head.XhWYIo
git archive HEAD | tar -x -C "$H"
cp backend/tests/test_ui_closeout_history_keyboard.py "$H/backend/tests/"
cd "$H/backend"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
  <工作树>/backend/.venv/bin/python \
  -m pytest -q -p no:cacheprovider -rf tests/test_ui_closeout_history_keyboard.py
# 退出码 1
```

原文输出：

```
FFFF                                                                     [100%]
=================================== FAILURES ===================================
_______________________ test_date_chip_keyboard_contract _______________________

    def test_date_chip_keyboard_contract() -> None:
>       check_date_chip_keyboard_contract(read_history())

tests/test_ui_closeout_history_keyboard.py:119: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

source = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'

    def check_date_chip_keyboard_contract(source: str) -> None:
        """The native inputs leave the Tab order; the chip buttons own the focus ring."""
>       assert source.count("tabIndex={-1}") == 2, "both native date inputs must leave the Tab order"
E       AssertionError: both native date inputs must leave the Tab order
E       assert 0 == 2
E        +  where 0 = <built-in method count of str object at 0x79ed47c000>('tabIndex={-1}')
E        +    where <built-in method count of str object at 0x79ed47c000> = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'.count

tests/test_ui_closeout_history_keyboard.py:55: AssertionError
__________________ test_date_inputs_pair_with_their_own_chips __________________

    def test_date_inputs_pair_with_their_own_chips() -> None:
>       check_date_input_pairing(read_history())

tests/test_ui_closeout_history_keyboard.py:123: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

source = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'

    def check_date_input_pairing(source: str) -> None:
        """Blind spot 1: each native date input carries only its own chip's binding."""
        date_tags = [tag for tag in INPUT_TAG.findall(source) if 'type="date"' in tag]
        assert len(date_tags) == 2, f"expected exactly two native date inputs, found {len(date_tags)}"
    
        from_tags = [tag for tag in date_tags if FROM_INPUT_LABEL in tag]
        to_tags = [tag for tag in date_tags if TO_INPUT_LABEL in tag]
        assert len(from_tags) == 1, "the from date label must belong to exactly one native input"
        assert len(to_tags) == 1, "the to date label must belong to exactly one native input"
    
        for expected in ("value={dateFrom}", 'data-chip="from"', "ref={dateFromRef}"):
>           assert expected in from_tags[0], (
                f"the input labeled 「从（开始日期）」 must carry {expected}, not the other chip's binding"
            )
E           AssertionError: the input labeled 「从（开始日期）」 must carry data-chip="from", not the other chip's binding
E           assert 'data-chip="from"' in '<input\n                  type="date"\n                  aria-label="从（开始日期）"\n                  value={dateFrom}\n  ...rget); } }}\n                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"\n                />'

tests/test_ui_closeout_history_keyboard.py:84: AssertionError
_________________ test_date_buttons_pair_with_their_own_inputs _________________

    def test_date_buttons_pair_with_their_own_inputs() -> None:
>       check_date_button_pairing(read_history())

tests/test_ui_closeout_history_keyboard.py:127: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

source = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'

    def check_date_button_pairing(source: str) -> None:
        """Blind spot 1, button half: each visible chip opens its own native input."""
>       assert source.count(FROM_BUTTON_LABEL) == 1, "the from chip button label must appear exactly once"
E       AssertionError: the from chip button label must appear exactly once
E       assert 0 == 1
E        +  where 0 = <built-in method count of str object at 0x79ed47c000>('aria-label={`从（开始日期）：${dayFace(dateFrom)}`}')
E        +    where 0 = <built-in method count of str object at 0x79ed47c000> = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'.count

tests/test_ui_closeout_history_keyboard.py:105: AssertionError
__________________ test_selfcheck_swapped_labels_are_rejected __________________

    def test_selfcheck_swapped_labels_are_rejected() -> None:
        source = read_history()
    
        # Swapping the two literal native-input labels must break the pairing check.
        swapped_inputs = _swap(source, FROM_INPUT_LABEL, TO_INPUT_LABEL)
        with pytest.raises(AssertionError):
            check_date_input_pairing(swapped_inputs)
    
        # Swapping the two visible chip button labels must break the button check.
>       swapped_buttons = _swap(source, FROM_BUTTON_LABEL, TO_BUTTON_LABEL)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_ui_closeout_history_keyboard.py:139: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

source = '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n'
left = 'aria-label={`从（开始日期）：${dayFace(dateFrom)}`}'
right = 'aria-label={`到（结束日期）：${dayFace(dateTo)}`}'

    def _swap(source: str, left: str, right: str) -> str:
>       assert left in source and right in source
E       assert ('aria-label={`从（开始日期）：${dayFace(dateFrom)}`}' in '"use client";\n\nimport { useState, useEffect, useRef, useMemo, Suspense } from "react";\nimport { useRouter, useSear...3 text-[color:var(--ink2)]">\n        加载中…\n      </div>\n    }>\n      <HistoryContent />\n    </Suspense>\n  );\n}\n')

tests/test_ui_closeout_history_keyboard.py:113: AssertionError
=========================== short test summary info ============================
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_chip_keyboard_contract
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_inputs_pair_with_their_own_chips
FAILED tests/test_ui_closeout_history_keyboard.py::test_date_buttons_pair_with_their_own_inputs
FAILED tests/test_ui_closeout_history_keyboard.py::test_selfcheck_swapped_labels_are_rejected
4 failed in 0.03s
```

HEAD 上 4 个用例全部失败，失败类型均为 `AssertionError`，无 `ImportError` / `FileNotFoundError` / `SyntaxError`。

## 3. 判断与遗留

- 既有字面量锁要求 `className="absolute inset-0 h-full w-full cursor-pointer opacity-0"` 恰 2 次。按规格把该字面量放在新增的透明 `<button>` 上（每个 chip 一次，共 2 次），原生框改用 `cn(...)` 按 `rawChip` 切换透明度，因此 `test_empty_states_history_dates.py` 的计数与 `openDatePicker(e.currentTarget)` 4 次、`aria-label="从/到（…）"` 各 1 次等锁全部保持通过。
- 当前文件实测计数：`tabIndex={-1}` 2、`data-chip=` 2、`aria-hidden="true"` 9（≥6）、透明按钮字面量 2、`openDatePicker(e.currentTarget)` 4、`onClick={e => openDatePicker(e.currentTarget)}` 2。
- HEAD 对照中，自检用例在 HEAD 上先因按钮字面量不存在而在 `_swap` 的前置断言处失败（仍是 `AssertionError`）；这是预期现象：HEAD 根本没有新增按钮，无法完成按钮 label 互换。在工作树源码上两条互换自检都实际执行并通过（即改坏后配对检查确实抛 `AssertionError`）。
- 未发现规格 §2.2 与 HEAD 对不上；未发现白名单外既有测试变红。未改 `02-spec.md` 或其他 docs 文件。
- 全量 pytest、`npm run lint`、`npm run build` 留给主代理按 §5 执行；本次只跑了 §2.1–2.6 列出的命令。
