# agent C（源码门禁 T3-1）实施记录

## 1. 文件变更

| 类型 | 文件 | 说明 |
|---|---|---|
| 新建 | `backend/tests/test_design_system_gate.py` | T3-1 源码门禁：F1–F10、K1–K6、R2–R4、令牌层 T1–T7，以及自检 |
| 新建 | `docs/tasks/2026-10-30-design-system/impl/C.md` | 本记录 |

没有修改任何其他文件；没有动 `docs/tasks/2026-10-30-design-system/02-spec.md`、`verify/**`、`frontend/app/globals.css`、A 已套用的 76 个文件或任何既有测试。

## 2. 实现摘要

- 扫描面：`frontend/app`、`frontend/components`、`frontend/lib`，扩展名 `.ts/.tsx/.js/.jsx/.mjs/.css`；跳过 `node_modules`、`.next`，豁免 `frontend/components/ui/`；HEAD 上扫描到 131 个文件。
- `.css` 先按参考实现把 `/* … */` 替换成等长空白（保留换行和行号）再扫描。
- 规则正则、左右边界、F7/F8/F9/F10/R3 白名单与令牌层 `parse_blocks` / `decls_of` 逻辑全部写进测试文件本身，未 import、执行或读取 `docs/`。
- 四个分组函数名与规格一致：`test_font_size_rules`、`test_color_rules`、`test_role_rules`、`test_token_layer`。每组先断言扫描文件数 ≥ 130；组内所有规则命中汇总后只做一次断言，失败信息逐条列出每条规则的命中数与前 3 处。
- 自检集中在 `test_selfcheck_source_rules` 与 `test_selfcheck_token_layer`，HEAD 与改后都通过；总则列出的合法写法由 `required_good` 统一断言 19 条源码规则对它 0 命中。
- 测试不依赖 node / `frontend/node_modules`，HEAD 副本未执行 `cp -cR` 克隆 `node_modules`，结果仍是 0 skipped。

## 3. 命令与结果

### 3.1 HEAD 正控（mktemp -d + git archive HEAD）

```bash
H=$(mktemp -d /tmp/fiona-c-head-final2.XXXXXX)  # 本次实际为 /tmp/fiona-c-head-final2.DWSxvO
git archive HEAD | tar -x -C "$H"
cp backend/tests/test_design_system_gate.py "$H/backend/tests/test_design_system_gate.py"
cd "$H/backend"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    <工作树>/backend/.venv/bin/python \
    -m pytest -q -p no:cacheprovider tests/test_design_system_gate.py -rf
```

结果：退出码 1，`4 failed, 2 passed in 1.14s`，**0 skipped**。4 个失败全部是 `AssertionError`。

另外用参考实现交叉核对同一份 HEAD 副本：

```bash
cd <工作树>
python3 -I docs/tasks/2026-10-30-design-system/verify/ref/gate_rules.py "$H"
```

结果：`== FAIL 20`，即 6 条 F + 5 条 K + 2 条 R + 7 项 T 失败，与规格「HEAD 上因哪些规则失败」一致。

### 3.2 改后（B 已完成的工作树）

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_system_gate.py -rf
```

结果：`6 passed in 1.11s`，0 skipped。运行前 `git diff HEAD -- frontend/app/globals.css frontend/lib/utils.ts frontend/components/Seal.tsx` 已显示 B 的 T2 改动在当前工作树里；参考实现 `gate_rules.py .` 也是 `== FAIL 0`。

### 3.3 与参考实现的逻辑等价性交叉核对（一次性脚本，未写进测试）

在同一次会话里用临时脚本加载本测试文件与参考 `gate_rules.py`（仅用于核验，测试本身不依赖它）：

- 19 条规则的 `regex.pattern` 与 `regex.flags` 逐条完全相同；
- HEAD 副本与当前工作树都是 131 个文件，测试的每条规则命中数与参考 `scan()` 逐条相同；
- `_token_layer()` 与参考 `token_layer()` 在 HEAD（T1–T7 全 False）和当前树（全 True）上返回逐项相同。

## 4. 每函数结果（HEAD 副本）

| 函数 | 结果 | 失败类型 | 备注 |
|---|---|---|---|
| `test_font_size_rules` | FAIL | `AssertionError` | F1、F3、F6、F7、F8、F9 有命中 |
| `test_color_rules` | FAIL | `AssertionError` | K1、K2、K3、K4、K5 有命中 |
| `test_role_rules` | FAIL | `AssertionError` | R2、R4 有命中 |
| `test_token_layer` | FAIL | `AssertionError` | T1–T7 全部 FAIL |
| `test_selfcheck_source_rules` | PASS | — | 合成样本自检 |
| `test_selfcheck_token_layer` | PASS | — | 合成样本自检 |

合计：4 failed、2 passed、0 skipped、0 error。

## 5. 每条规则 HEAD 命中数对照

### 5.1 F1–F10

| 规则 | 规格 HEAD | 实测 HEAD | 一致 |
|---|---:|---:|:---:|
| F1 | 300 | 300 | ✅ |
| F2 | 0 | 0 | ✅ |
| F3 | 563 | 563 | ✅ |
| F4 | 0 | 0 | ✅ |
| F5 | 0 | 0 | ✅ |
| F6 | 1 | 1 | ✅ |
| F7 | 2 | 2 | ✅ |
| F8 | 7 | 7 | ✅ |
| F9 | 9 | 9 | ✅ |
| F10 | 0 | 0 | ✅ |

### 5.2 K1–K6

| 规则 | 规格 HEAD | 实测 HEAD | 一致 |
|---|---:|---:|:---:|
| K1 | 144 | 144 | ✅ |
| K2 | 223 | 223 | ✅ |
| K3 | 50 | 50 | ✅ |
| K4 | 8 | 8 | ✅ |
| K5 | 69 | 69 | ✅ |
| K6 | 0 | 0 | ✅ |

### 5.3 R2–R4

| 规则 | 规格 HEAD | 实测 HEAD | 一致 |
|---|---:|---:|:---:|
| R2 | 1 | 1 | ✅ |
| R3 | 0 | 0 | ✅ |
| R4 | 18 | 18 | ✅ |

### 5.4 T1–T7

| 项 | 规格 HEAD | 实测 HEAD | 一致 |
|---|---|---|---|
| T1 | 失败 | FAIL | ✅ |
| T2 | 失败 | FAIL | ✅ |
| T3 | 失败 | FAIL | ✅ |
| T4 | 失败 | FAIL | ✅ |
| T5 | 失败 | FAIL | ✅ |
| T6 | 失败 | FAIL | ✅ |
| T7 | 失败 | FAIL | ✅ |

逐条命中数与 `02-spec.md` 的 T3-1 表完全相同。

## 6. 自检覆盖

`test_selfcheck_source_rules` 为 F1–F10、K1–K6、R2–R4 每条规则各配：

| 规则 | 坏样本（会命中） | 好样本（不误伤） |
|---|---|---|
| F1 | `text-[14px]` | `text-[color:var(--ink2)]` |
| F2 | `text-(--ink2)` | `text-[color:var(--ink2)]` |
| F3 | `max-md:text-sm` | `max-md:text-fs-15` |
| F4 | `[font-size:14px]` | `font-medium` |
| F5 | `` text-[${x}] `` | `` text-fs-15 ${x} `` |
| F6 | `` text-fs-13${x} `` | `` text-fs-13 ${x} `` |
| F7 | `fontSize: 14` | `fontSize: "var(--fs-13)"`；类型声明 `fontSize: number`；`Seal.tsx` 的 `fontSize="30"` |
| F8 | `<small>` 无 `text-fs-` | `<small className="text-fs-11">` |
| F9 | CSS `font-size: 14px`、`font: 14px/1.5` | `var(--fs-13)`、`inherit`、`max(var(--fs-16-5), 1em)`、注释里的 14px |
| F10 | `text-fs-14` | `text-fs-30!`、`mobile:text-fs-22`、`@[640px]:text-fs-15`、`text-fs-16.5`、`text-fs-22 leading-[inherit]`、`text-fs-15 text-pretty`、注释里的 `text-fs-12.` |
| K1 | `text-muted-foreground` | `text-[color:var(--ink2)]` |
| K2 | `hover:bg-secondary/50` | `hover:bg-[color:var(--slip)]/50` |
| K3 | `var(--rec)`、`--amber-ink:` | `var(--seal)` |
| K4 | `var(--ring)` | `var(--ink)` |
| K5 | `text-[var(--ink2)]` | `text-[color:var(--ink2)]` |
| K6 | `bg-(--slip)` | `bg-[color:var(--slip)]` |
| R2 | `text-[color:var(--ink3)]` | `text-[color:var(--ink2)]` |
| R3 | 非 Seal 组件里的 `var(--stamp)` | globals.css 的 `--seal-soft` 定义行、`Seal.tsx` 的 `fill="var(--stamp)"` |
| R4 | `text-[color:var(--ink)]/60` | `text-[color:var(--ink)]` |

坏样本全部使用 `<div>`、`<small>`、`<rect>`、`<text>` 或纯 JS 字符串，没有使用 `<button`、`<br`。

规格 T3 总则列出的 `text-fs-30!`、`mobile:text-fs-22`、`@[640px]:text-fs-15`、`text-fs-16.5`、`text-fs-22 leading-[inherit]`、`text-fs-15 text-pretty`、注释里的 `text-fs-12.` 合并在 `required_good` 里；除 F10 的好样本外，还额外断言 19 条源码规则对它全部 0 命中。

`test_selfcheck_token_layer` 构造一份满足 T1–T7 的合成 CSS（四套主题、别名 `:root`、`@theme inline`、第一个 `@layer base`、顶层 `@media` 护栏），断言 T1–T7 全通过；再分别注入 7 种坏写法：

- T1：`--fs-13` 值写成 14px；
- T2：13 档行高写成 1.4；
- T3：昼主题 `--seal` 写错；
- T4：`--seal-soft` 的 12% 写成 20%；
- T5：护栏选择器少一项；
- T6：`::placeholder` 颜色写成 `--ink3`；
- T7：`body` 去掉 `font-size`。

每个坏样本都只断言对应的 T 项失败，基线断言全部通过。

## 7. 偏差

- 无功能偏差。严格按规格 T3-1 与参考实现实现，未调低阈值、白名单或 HEAD 命中数。
- HEAD 正控按要求跳过了 `cp -cR frontend/node_modules`（该测试不需要 node 依赖），结果仍为 0 skipped。
- 自检比最低要求多覆盖了令牌层 T1–T7 的坏样本，以及 F7 的类型声明、JSX 属性、Seal 白名单和 F9 的注释剥离。
- 验证“改后全部通过”时，当前工作树里 B 的 T2 改动已经存在（`globals.css`、`utils.ts`、`Seal.tsx` 的 diff 可见）；本 agent 没有修改这些文件，只新建了测试文件。
