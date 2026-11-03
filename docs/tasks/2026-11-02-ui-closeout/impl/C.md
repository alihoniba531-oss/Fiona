# Agent C 执行记录（T3 + T4 + T5 遮罩测试）

## 1. 做了什么

### T3：遮罩统一为 `scrim-dialog`

- `frontend/app/globals.css`：删除 `.image-preview-dialog` / `.confirm-dialog` 两者合计四条 `::backdrop` 规则及旧注释，保留两条非遮罩规则原样；在 `.confirm-dialog` 规则之后新增规格指定的注释与两条公共规则：
  - `.scrim-dialog::backdrop { background:var(--scrim, rgba(31,41,38,.18)); }`
  - `.dark .scrim-dialog::backdrop { background:var(--scrim, rgba(0,0,0,.45)); }`
- 六个 className 字符串中的 `backdrop:bg-[color:var(--scrim)]` 原位替换为 `scrim-dialog`：
  - `frontend/components/SongProjectCard.tsx`
  - `frontend/components/novel/NovelSettingsDialog.tsx`
  - `frontend/components/studio/BrainTrial.tsx`（`dialogClass`）
  - `frontend/components/studio/QuoteDialog.tsx`
  - `frontend/components/studio/ShotCard.tsx`
  - `frontend/components/studio/SourceChoices.tsx`（`sourceDialogClass`）
- `frontend/components/ConfirmDialog.tsx`：`className="confirm-dialog scrim-dialog"`。
- `frontend/components/GeneratedImage.tsx`：在原有 className 的 `image-preview-dialog` 与 `m-auto` 之间插入 `scrim-dialog`，其余类逐字未动。
- 共覆盖 13 个 `<dialog>`；`frontend/components` 中含 `scrim-dialog` 的文件为 8 个。

### T4：门禁补强

只改了规格点名的位置。

- `backend/tests/test_design_system_gate.py`
  - `TYPE_WORDS` 换为 `TYPE_WORD_RX = re.compile(r"(?:number|string|undefined|null|boolean|any|unknown|CSSProperties)(?![\w$])|React\.|Property\.")`。
  - F7 放行改为 `TYPE_WORD_RX.match(val)`。
  - F7 正则补 `.style.fontSize\s*=` 与 `.setProperty\(\s*["']font(?:-size)?["']` 分支，规则说明同步更新。
  - F7 好样本增加类型声明与 `React.CSSProperties["fontSize"]` 两条。
  - 新增 6 条 F7 坏样本断言，并保留 `fontWeight` / `setProperty("--fs-x")` 两条误伤反例。
  - T8 改为只接受 `.scrim-dialog::backdrop` 与 `.dark .scrim-dialog::backdrop`，断言名同步更新。
  - T8 自检样本换成两条公共规则；新增好样本控制与 5 个坏样本：两条兜底全去、仅 `.dark` 去兜底、昼夜颜色对调、删掉 `.dark` 规则、多一条 HEAD 的 `.image-preview-dialog::backdrop`。
- `backend/tests/test_design_system_css.py`：`REQUIRED_PACKAGES` 增加 `"tailwindcss"`，未加 `tw-animate-css`。

### T5：新增 `backend/tests/test_ui_closeout_dialog_scrim.py`

文件含 3 个真实测试：

1. 扫描 `frontend/app`、`frontend/components`（跳过 `node_modules`、`.next`、`components/ui/`）的 `.tsx`，用花括号深度 + 字符串状态的逐字符解析找 `<dialog>` 结尾；共 13 个，全部 className 必须含 `scrim-dialog`；支持字符串 className 和唯一的 `const dialogClass = "m-auto scrim-dialog"` 这类定义。
2. `globals.css` 去掉注释后恰有两条 `::backdrop` 规则，prelude 恰为 `.scrim-dialog::backdrop` 与 `.dark .scrim-dialog::backdrop`。
3. 扫描 `.ts/.tsx/.css`，`(?<![\w-])backdrop:` 必须 0 命中；自检确认命中 `backdrop:bg-x`，不误伤 `backdrop-filter:` 与 `.a::backdrop {`。

自检：`=>` + 嵌套语句块的标签能正确取到 className；静态坏 className 抛 `AssertionError`；`className={dialogClass}` 在定义含/不含 `scrim-dialog` 时分别通过/抛 `AssertionError`；两种正则反例。自检都放在真实断言之后，因此 HEAD 对照时 3 个测试都先因真实源码断言失败，满足“全部 FAIL 且只由 AssertionError 失败”。

## 2. 实际命令与结果

工作目录：`<工作树>`。

### 2.1 工作树必需测试（全 PASS）

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_ui_closeout_dialog_scrim.py \
  tests/test_design_system_gate.py \
  tests/test_design_system_css.py \
  tests/test_component_language.py
```

原文输出：

```text
.................................                                        [100%]
33 passed in 1.83s
```

另单独跑 CSS 测试确认没有 skip：

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_system_css.py -rs
```

原文输出：

```text
.                                                                        [100%]
1 passed in 0.34s
```

`test_design_system_gate.py::test_token_layer`、两个自检及 `test_component_language.py` 也均在上述 33 passed 内。

### 2.2 HEAD 对照（§5 第 5 条）

```bash
set -u
H=$(mktemp -d /tmp/fiona-head.XXXXXX)
git archive HEAD | tar -x -C "$H"
cp backend/tests/test_ui_closeout_dialog_scrim.py "$H/backend/tests/"
cp backend/tests/test_design_system_gate.py backend/tests/test_design_system_css.py "$H/backend/tests/"
ln -s "$PWD/frontend/node_modules" "$H/frontend/node_modules"
cd "$H/backend"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
  "$OLDPWD/backend/.venv/bin/python" -m pytest -q -p no:cacheprovider -rf \
  tests/test_ui_closeout_dialog_scrim.py \
  tests/test_design_system_gate.py \
  tests/test_design_system_css.py
```

临时副本：`/tmp/fiona-head.7mIeQh`。

原文输出（只保留 pytest 进度行与失败列表）：

```text
FFF...F...                                                               [100%]
FAILED tests/test_ui_closeout_dialog_scrim.py::test_all_dialogs_use_scrim_dialog
FAILED tests/test_ui_closeout_dialog_scrim.py::test_scrim_backdrop_rules_are_the_only_two
FAILED tests/test_ui_closeout_dialog_scrim.py::test_no_backdrop_tailwind_variants_remain
FAILED tests/test_design_system_gate.py::test_token_layer - AssertionError: ...
4 failed, 6 passed in 1.42s
```

失败原因均为 `AssertionError`，没有 `ImportError` / `FileNotFoundError`。`test_token_layer` 摘要里的 `AssertionError: ...` 是 pytest `-q` 自身对异常文字的截断，完整 traceback 显示 T1–T7 PASS、T8 FAIL：

- `test_all_dialogs_use_scrim_dialog`：HEAD 的 `ConfirmDialog.tsx` className 为 `confirm-dialog`，不含 `scrim-dialog`。
- `test_scrim_backdrop_rules_are_the_only_two`：HEAD 去掉注释后有 4 处 `::backdrop`。
- `test_no_backdrop_tailwind_variants_remain`：HEAD 第一个命中为 `frontend/components/SongProjectCard.tsx:340` 的 `backdrop:bg-[color:var(--scrim)]`。
- `test_token_layer`：T8 FAIL（HEAD 仍是 `.image-preview-dialog` / `.confirm-dialog` 四条规则），其余 T1–T7 PASS。

同一 HEAD 副本用 `-v --tb=no` 复核逐项结果；其中 `AssertionError: ...` 同样是 pytest 摘要截断：

```text
tests/test_ui_closeout_dialog_scrim.py FFF                               [ 30%]
tests/test_design_system_gate.py ...F..                                  [ 90%]
tests/test_design_system_css.py .                                        [100%]
=========================== short test summary info ============================
FAILED tests/test_ui_closeout_dialog_scrim.py::test_all_dialogs_use_scrim_dialog
FAILED tests/test_ui_closeout_dialog_scrim.py::test_scrim_backdrop_rules_are_the_only_two
FAILED tests/test_ui_closeout_dialog_scrim.py::test_no_backdrop_tailwind_variants_remain
FAILED tests/test_design_system_gate.py::test_token_layer - AssertionError: ...
========================= 4 failed, 6 passed in 1.39s ==========================
```

即：`test_selfcheck_source_rules`、`test_selfcheck_token_layer`、`test_design_system_css.py` 都 PASS；只有 `test_token_layer` FAIL，与期望一致。

### 2.3 计数与工作树范围

```text
rg --pcre2 -n "(?<![\w-])backdrop:" frontend/app frontend/components frontend/lib --glob '*.{ts,tsx,css}'
→ 0 行

rg -l "scrim-dialog" frontend/components | wc -l
→ 8

grep -c "::backdrop" frontend/app/globals.css
→ 3
```

`git diff --check` 对本次改动文件无输出。

## 3. 判断、偏差与遗留

- **规格 §5 第 6 条的 `grep -c "::backdrop"` 期望值 2 与 T3 指定注释冲突。** T3 要求加入的注释本身含 `::backdrop`，因此实际 `grep -c` 为 3（1 行注释 + 2 行规则），不是 2。两条真实规则和 T8/新测试都按 T3 通过；这是验收命令预期值的问题，不是实现多写了规则。未改规格、未改注释、未改测试来掩盖这一差异，交由主代理决定如何记录或修正该计数命令。
- 新测试在统计 `::backdrop` 前先剥离 CSS 注释，因此校验的是“恰好两条规则”，既符合 T3 的注释要求，也符合 T5 的语义。
- 3 个新测试都包含真实源码断言和自检；HEAD 上三者全部 FAIL（`AssertionError`），工作树上全部 PASS。
- 未安装依赖、未运行 `npm ci`、未改 `package.json`；未做任何 git 写操作；未改其他 agent 的文件、其他既有测试或 `02-spec.md`。
- 未提交 commit；工作树中其他 agent 的 `frontend/app/history/page.tsx`、`test_ui_closeout_history_keyboard.py`、`test_ui_closeout_structure_guards.py` 等改动不是本 agent 产生的。
