# E：T3-3（cn / tailwind-merge）与 T3-4（生成 CSS）

日期：2026-10-30。工作目录：`<工作树>`。

## 1. 改动文件

新增，仅这两个文件：

- `backend/tests/test_design_system_cn.py`
- `backend/tests/test_design_system_css.py`

未改工作树的 `frontend/lib/utils.ts`、`frontend/app/globals.css`、`verify/**`、`docs/tasks/2026-10-30-design-system/02-spec.md` 或其他文件。

两个测试都把规则写在文件内，没有 import / 执行 / 读取 `docs/` 下的任何文件。依赖探测与运行都只用 `frontend/node_modules`。

## 2. 实现摘要

### `test_design_system_cn.py`

- 探测 `node`，再用 `createRequire(frontend/package.json)` 探测 `typescript`、`clsx`、`tailwind-merge`；缺失时 `pytest.skip`。
- 用 TypeScript `transpileModule` 把 `frontend/lib/utils.ts` 转成 CJS，在 `new Function` 里用仓库的 `require` 加载，调用导出的 `cn()`。
- 单个 `test_cn_keeps_size_and_color` 覆盖规格 T3-3 表全部 19 项：
  - 表内第 1–8 条（第 7 条拆成两个调用，共 9 个输入）；
  - 10 个令牌 `text-fs-11/12/13/15/16.5/18/22/30/46/76` 逐个与 `text-[color:var(--ink)]` 合并。
- 逐项比对完整输出字符串，失败时逐条列出 `case 编号 + 入参 + 实际 + 期望`。

### `test_design_system_css.py`

- 探测 `node`，再探测 `typescript`、`@tailwindcss/node`、`@tailwindcss/oxide`；缺失时 `pytest.skip`。
- 用 `@tailwindcss/node` 的 `compile` 按真实 `frontend/app/globals.css` 编译；`@tailwindcss/oxide` 的 `Scanner` sources 为 `app/`、`components/`、`lib/`，并 `negated` 排除 `components/ui/`。脚本经 `node -e` 传入，不写仓库、不跑 `next build`。
- 单个 `test_generated_css_font_sizes`：
  - 断言扫描文件数 ≥ 130；
  - 反向：对生成 CSS 全文匹配 `(font-size|font):`，值只允许 10 个 `var(--fs-*)`（可带 `!important`）、`inherit`、`1em`、`75%`、`80%`、`max(var(--fs-16-5), 1em)`；另查 `color: var(--fs-`；
  - 正向：`compiler.build([...12 个类...])`，逐条比对空白归一后的规则体与规格 T3-4 表完全一致（含 `.text-fs-16\.5`、`.text-fs-30\!`、`.max-md\:text-fs-11` 的转义选择器）；
  - 失败信息给出反向违规数、`color: var(--fs-` 数、正向不符数，以及反向前 5 条和正向全部不符项。

## 3. 命令与结果

### 3.1 HEAD 正控（只读副本，不碰工作树）

```bash
set -e
H=$(mktemp -d /tmp/fiona-e-head.XXXXXX)          # 实际：/tmp/fiona-e-head.ut8LXZ
git archive HEAD | tar -x -C "$H"
cp backend/tests/test_design_system_cn.py \
   backend/tests/test_design_system_css.py "$H/backend/tests/"
cp -cR frontend/node_modules "$H/frontend/node_modules"

cd "$H/backend"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    <工作树>/backend/.venv/bin/python \
    -m pytest -q -p no:cacheprovider -rf \
    tests/test_design_system_cn.py tests/test_design_system_css.py
```

结果：`2 failed in 0.65s`，退出码 1，**0 skipped**，两个失败都是 `AssertionError`。

- `test_cn_keeps_size_and_color`：失败。
  - 规格要求失败的第 1、2、5、6 条全部失败：
    - 1 `cn('text-fs-13','text-[color:var(--ink2)]')` → `'text-[color:var(--ink2)]'`
    - 2 `cn('text-[color:var(--ink)]','text-fs-16.5')` → `'text-fs-16.5'`
    - 5 `cn('text-[13px]','text-fs-13')` → 两个都保留
    - 6 `cn('leading-6','text-fs-13')` → 两个都保留
  - 另外第 8 条也失败：`text-fs-12` 被当作颜色组，与第二段的 `text-[color:var(--seal)]` 冲突，`text-fs-12` 被删。
  - 另外 10 个令牌逐个与颜色合并也全部失败：默认 `twMerge` 把未知的 `text-fs-*` 当颜色，后一个颜色类删掉前一个字号类（每个只剩 `text-[color:var(--ink)]`）。
  - 合计 15 条断言失败；第 3、4、7a、7b 条通过。
- `test_generated_css_font_sizes`：失败。
  - `scannedFiles=131`（≥ 130）。
  - 反向：`font-size/font` 违规 **49** 条，`color: var(--fs-` **0** 条；错误信息前 5 条是 `var(--text-base)`、`var(--text-lg)`、`var(--text-sm)`、`var(--text-xl)`、`var(--text-xs)`，其余为源码里的任意 px 字号。
  - 正向：12 个类 **12/12 不符**，全部 `实际 None`（HEAD 的 `globals.css` 没有 `--text-fs-*`，类不生成）。
  - 合规断言失败信息同时报告 `反向 49 + 正向 12`。
- 自检函数：本任务没有单独的 `test_selfcheck_*`；T3-3 / T3-4 按规格各只写一个结构测试。
- 交叉核对：同一 HEAD 副本上跑参考实现
  ```bash
  node docs/tasks/2026-10-30-design-system/verify/ref/gate_twcss.mjs "$H/frontend"
  ```
  得到 `scannedFiles=131 font-size/font 违规=49 令牌编译不符=12`，退出码 61；与新测试的 49 + 12 一致。

### 3.2 B 套用 T2 后的工作树

`frontend/lib/utils.ts` 已出现 `extendTailwindMerge` 与 10 个 `fs-*` 注册；`frontend/app/globals.css` 已有 10 个 `--text-fs-*`。命令：

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    .venv/bin/python -m pytest -v -p no:cacheprovider -rf \
    tests/test_design_system_cn.py tests/test_design_system_css.py
```

结果：

```
tests/test_design_system_cn.py::test_cn_keeps_size_and_color PASSED
tests/test_design_system_css.py::test_generated_css_font_sizes PASSED
2 passed in 0.31s
```

0 failed、0 skipped。B 的记录 `impl/B.md` 出现后（确认 B 已完成）又用同一命令复跑一次，结果相同。

另外直接调用 CSS 测试里的 node runner 核对了一次改后数据：`scannedFiles=131`、`violationCount=0`、`colorViolationCount=0`、`mismatchCount=0`。

## 4. 每函数结果

| 函数 | HEAD 副本 | B 完成后 |
|---|---|---|
| `test_cn_keeps_size_and_color` | FAILED，AssertionError，15 条断言失败（第 1/2/5/6/8 条 + 10 个令牌） | PASSED |
| `test_generated_css_font_sizes` | FAILED，AssertionError，反向 49 条 + 正向 12/12 不符 | PASSED（反向 0、正向 0、扫描 131） |

## 5. 偏差与说明

1. **HEAD 上 cn 的失败条目多于规格字面列举的 4 条。** 规格与派单写「第 1、2、5、6 条会失败」；实测第 8 条和 10 个令牌合并也必然失败。原因相同：HEAD 的 `twMerge` 不认识 `text-fs-*`，把它们归入文字颜色组。第 8 条第二段的 `text-[color:var(--seal)]` 会删掉 `text-fs-12`；令牌用例中后一个 `text-[color:var(--ink)]` 会删掉前一个 `text-fs-*`。测试仍按 T3-3 表逐项断言（不能为了让 HEAD 只报 4 条而放宽第 8 条或令牌断言），失败信息逐条列出。B 套用 `extendTailwindMerge` 后这些项全部通过。
2. CSS 测试的依赖探测按派单列出的五个包执行；其中 `typescript` 在 T3-4 runner 里不使用，只作为依赖探测项，缺它也会 skip。`clsx` 只在 cn 测试里探测/使用。
3. 两个测试都通过 `node -e` 运行，没有在仓库或 `tmp_path` 落任何文件；HEAD 副本目录 `/tmp/fiona-e-head.ut8LXZ` 仅用于正控，验证后删除。
4. HEAD 正控的副本只含 HEAD 源码 + 这两个新测试 + `frontend/node_modules` clone；没有复制任何工作树中被 A/B 改过的前端文件。
