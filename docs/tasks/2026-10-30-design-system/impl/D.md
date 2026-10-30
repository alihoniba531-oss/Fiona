# D（对比度，T3-2）实施记录

## 改动的文件

- 新增 `backend/tests/test_design_tokens_contrast.py`
- 新增本记录 `docs/tasks/2026-10-30-design-system/impl/D.md`

未改动工作树的 `frontend/app/globals.css`，未改动 A 的 76 个文件、`02-spec.md`、`verify/**` 或其它既有测试。测试文件本身只读仓库内的 `frontend/app/globals.css`，不 import/执行/读取 `docs/` 下任何文件。

## 实现要点

- 解析 `frontend/app/globals.css` 的四套主题，按浏览器层叠：
  - 昼 = `:root`
  - 夜 = `:root` + `.dark`
  - 昼素瓷 = `:root` + `:root[data-solid]`
  - 夜素瓷 = `:root` + `.dark` + `:root[data-solid]` + `.dark[data-solid]`
- 断言四个主题块键集合相同；别名 `:root` 与其后的顶层 `.dark` 不定义被检查的 16 个颜色。
- 参与计算的令牌只接受 `#RRGGBB` 或 `rgba(r,g,b,a)`，其它写法抛 `AssertionError`。
- `--seal-soft` 从别名 `:root` 的 `color-mix(in srgb, var(--X) N%, transparent)` 解析；HEAD 上按旧名 `--rec-soft` 回退；解析不到直接失败。
- 半透明底先按 alpha 叠到 `--paper` / `--hi` 上（逐通道 `round()`），再按 WCAG 2.x 算相对亮度与对比度。
- 底色集合 S：`--paper`、`--hi`、`--slip`；`--glass`、`--glass2`、`--chip`、`--tile`、`--mount` 不透明时直接用，半透明时分别叠在 `--paper`、`--hi` 上各算一次。
- 断言表：`--ink`/`--ink2` 对 S ≥ 4.5；`--seal` 对 S 及 `--seal-soft` 叠在 paper/hi/glass/glass2/tile 基色上的悬停/录音底 ≥ 4.5；`--ink3` 对 S 除 chip 系外 ≥ 3；`--btnink`/`--btn` ≥ 4.5；`--glyph`/`--stamp` ≥ 4.5；HEAD 无 `--stamp` 时按 `--seal` 代算。
- 两个测试函数：
  - `test_token_contrast`：断言当前 CSS 全部达标；
  - `test_selfcheck_head_tokens_fail`：用当前 CSS 解析结果，昼两块 `--ink3` 换回 `#84918B`、夜两块 `--seal` 换回 `#BF4537`，去掉 `--stamp`（悬停底基色回落到 `--seal`），断言不达标集合恰为四组、共 43 条，且夜 `--seal` 失败项包含 `seal-soft@` 底。

## HEAD 正控（按 §T3 跑法）

命令（实际执行，副本每次新建）：

```bash
H=$(mktemp -d /tmp/fiona-d-head.XXXXXX)
git archive HEAD | tar -x -C "$H"
cp backend/tests/test_design_tokens_contrast.py "$H/backend/tests/"
cd "$H/backend"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    <工作树>/backend/.venv/bin/python \
    -m pytest -v -p no:cacheprovider -rf tests/test_design_tokens_contrast.py
```

结果：退出码 1；`1 failed, 1 passed`，**0 skipped**（输出中没有 `SKIPPED`，summary 无 skipped）。逐函数：

- `test_token_contrast`：**FAILED**，`tests/test_design_tokens_contrast.py:320: AssertionError`，失败消息为「不达标 43 条（WCAG 2.x）」，逐条列出 43 个 `实际 ... < ...` 行。
- `test_selfcheck_head_tokens_fail`：**PASSED**。

43 条分布（与规格一致）：

| 主题 | 前景 | 条数 |
|---|---|---|
| day（昼） | `--ink3` | 6 |
| day-solid（昼素瓷） | `--ink3` | 3 |
| night（夜） | `--seal` | 21 |
| night-solid（夜素瓷） | `--seal` | 13 |
| **合计** | | **43** |

夜 `--seal` 的失败项中包含 `seal-soft@paper`、`seal-soft@hi`、`seal-soft@glass@paper` 等悬停/录音底；测试内正控断言了该条件。

## 改后（B 完成后）验证

1. 当前工作树（B 的 T2 值已落盘：四块均有 `--stamp`，`--seal-soft: color-mix(in srgb, var(--stamp) 12%, transparent)`，昼 `--ink3: #6F7C76`，夜 `--seal: #E56F5D`）：

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    .venv/bin/python -m pytest -q -p no:cacheprovider \
    tests/test_design_tokens_contrast.py -rf
```

结果：`2 passed in 0.02s`（`test_token_contrast`、`test_selfcheck_head_tokens_fail` 均通过）。

2. 另用 HEAD 副本按 T1 的 2 处 `globals.css` 改动 + T2 全部 `globals.css` 改动模拟 B 完成后的 CSS（临时副本，不碰工作树）：`2 passed in 0.02s`；参考实现 `contrast_check.py` 在该副本上退出 0。

## 额外核对

- `python3 -I docs/tasks/2026-10-30-design-system/verify/ref/contrast_check.py frontend/app/globals.css`：
  - HEAD 副本：退出码 43，输出与测试的 43 条分布一致；
  - 当前工作树（post-T2）：退出码 0，`不达标 0 条`。
- 变异自检（均在临时副本上，未改工作树）：
  - 夜 `.dark --chip` 从 `rgba(74,63,52,0.42)` 改为 `rgba(74,63,52,0.60)`：`test_token_contrast` 变红，`AssertionError`，2 条 night `--seal` 对 chip 底不达标；`test_selfcheck_head_tokens_fail` 仍通过。
  - 夜两块 `--seal` 换回 `#BF4537`：`test_token_contrast` 变红，`AssertionError`，34 条（night 21 + night-solid 13）；`test_selfcheck_head_tokens_fail` 仍通过。
- `backend/.venv/bin/python -m py_compile backend/tests/test_design_tokens_contrast.py`：通过。

## 偏差

- 无。
- HEAD 副本不需要 `frontend/node_modules`，因此没有复制、也没有 `pytest.skip`。
- B 的 `impl/B.md` 已生成、`globals.css` 的 T2 值已落盘；B 完成后最终复跑仍为 `2 passed`，参考实现退出 0。
