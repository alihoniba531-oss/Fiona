# D：T5 盲区 2、3 结构守卫测试

- 执行者：agent D（dsh）
- 日期：2026-11-02
- 工作树：`<工作树>`，分支 `feat/ui-closeout`
- 基线 HEAD：`bccbf9f015b4f41f51b5ed009918b5021ac35b49`

## 1. 做了什么

只新增了 `backend/tests/test_ui_closeout_structure_guards.py`，未改动任何 frontend 源码、既有测试或其他文件；本记录 `docs/tasks/2026-11-02-ui-closeout/impl/D.md` 为允许写入的执行记录。

测试按规格 §4 T5 的「structure guards」实现，全部离线、只读仓库内源码、不依赖 git 历史、不需要 node：

- `ROOT = Path(__file__).resolve().parents[2]`；读文件使用 `encoding="utf-8"`。
- 每个检查是接收源码字符串的纯函数；真实测试传入工作树源码，自检传入改坏副本并要求抛 `AssertionError`。

### 1.1 盲区 2（`ChatModelSection.tsx`）

检查函数 `check_privacy_paragraph_is_unconditional(source)`：

1. 去行首空白后以 `<p className={noteClass}>启用后，` 开头的行恰 1 行；若首段被包进 `{needsKey && <p …>…</p>}`（不再以 `<p` 开头）会直接失败。
2. 源码中第二个含 `<fieldset` 的行必须在该首段行之前。
3. 取第二个 `<fieldset` 行与首段行之间的所有行（不含两端），拼接统计 `{` 与 `}` 个数必须相等。
4. 该区间内没有任何一行去首尾空白后以 `&&`、`&& (` 或 `&& <>` 结尾。

HEAD 实测：第二个 `<fieldset` 在第 324 行，首段在第 345 行，Claude 提示在第 346 行；区间内 `{` 与 `}` 各 24 个，无违规行尾。

### 1.2 盲区 3（`page.tsx`）

检查函数 `check_chat_opener_group_structure(source)`：

1. 去首尾空白后恰有 1 行等于
   `<div data-chat-openers className="flex flex-col items-center gap-4 pt-8 text-center max-md:pt-4">`。
2. 下一行以
   `<p className="text-fs-15 leading-[1.85] text-[color:var(--ink2)]" role="status">` 开头。
3. 再下一行恰等于
   `<div role="group" aria-label="开场" className="flex flex-wrap justify-center gap-2">`。
4. 随后三行分别以 `<button type="button" className="chip min-h-10"` 开头，并依次含
   `onClick={startChatOpener}`、`onClick={startDrawOpener}`、`onClick={startPhotoOpener}`。
5. 再下一行恰等于 `</div>`。

HEAD 实测该结构位于 `page.tsx` 第 2614–2620 行，共 7 行（容器、状态段、group、3 个按钮、group 收尾）。

### 1.3 自检

共 5 份改坏副本，全部断言抛 `AssertionError`，每份都是独立测试：

- 盲区 2：首段前一行插入 `{needsKey && <>`、Claude 提示之后插入 `</>}`。整份源码的花括号仍平衡，但被检查区间里只剩开括号，且开行以 `&& <>` 结尾，两道检查都会拦住。
- 盲区 2：把首段改成 `{needsKey && <p className={noteClass}>启用后，…</p>}` 单行（既有测试也能拦，按要求保留作对照）。
- 盲区 3：给 `role="group"` 那行加 ` onKeyDown={noop}`。
- 盲区 3：把第一个开场按钮包进 `<div onKeyDown={noop}>…</div>`，多出一行。
- 盲区 3：给 `data-chat-openers` 容器那行加 ` onKeyDown={noop}`。

## 2. 实际命令与结果

### 2.1 工作树运行（§3.5 写法）

```bash
cd backend && env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ui_closeout_structure_guards.py
```

输出原文：

```text
.......                                                                  [100%]
7 passed in 0.02s
```

退出码 0。

### 2.2 用例清单

```bash
cd backend && env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy .venv/bin/python -m pytest -q -p no:cacheprovider --collect-only tests/test_ui_closeout_structure_guards.py
```

输出原文：

```text
tests/test_ui_closeout_structure_guards.py::test_first_privacy_paragraph_is_not_wrapped_in_needs_key_conditional
tests/test_ui_closeout_structure_guards.py::test_chat_openers_are_not_wrapped_by_extra_keyboard_handlers
tests/test_ui_closeout_structure_guards.py::test_selfcheck_privacy_guard_rejects_split_needs_key_wrapper
tests/test_ui_closeout_structure_guards.py::test_selfcheck_privacy_guard_rejects_single_line_needs_key_wrapper
tests/test_ui_closeout_structure_guards.py::test_selfcheck_opener_guard_rejects_on_key_down_on_group
tests/test_ui_closeout_structure_guards.py::test_selfcheck_opener_guard_rejects_wrapped_first_button
tests/test_ui_closeout_structure_guards.py::test_selfcheck_opener_guard_rejects_on_key_down_on_container

7 tests collected in 0.02s
```

### 2.3 HEAD 对照（§5 第 5 条）

在 `/tmp` 用 `git archive HEAD` 生成副本，只把本任务的新测试复制进去，用工作树 `backend/.venv/bin/python` 按 §3.5 写法只跑该文件：

```bash
set -euo pipefail
H=$(mktemp -d /tmp/fiona-head.XXXXXX)
echo "H=$H"
git archive HEAD | tar -x -C "$H"
git -C "$H" status >/dev/null 2>&1 || true
cp backend/tests/test_ui_closeout_structure_guards.py "$H/backend/tests/"
cd "$H/backend"
set +e
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy <工作树>/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ui_closeout_structure_guards.py 2>&1 | tee /tmp/fiona-D-head.txt
rc=${PIPESTATUS[0]}
echo "EXIT=$rc"
echo "HEAD_SOURCE_COUNT=$(git -C "$H" rev-parse --short HEAD 2>/dev/null || echo no-git)"
exit 0
```

输出原文：

```text
H=/tmp/fiona-head.jinFc5
.......                                                                  [100%]
7 passed in 0.02s
EXIT=0
HEAD_SOURCE_COUNT=no-git
```

`HEAD_SOURCE_COUNT=no-git` 是因为 `git archive` 导出的目录本身不含 `.git`，不是测试失败；被测源码来自 HEAD 已用校验和确认：

```text
$ git show HEAD:frontend/app/page.tsx | shasum -a 256
e7b9746a8b4d942a4c1ebd31bd5d6c6cde040d871b93040f371574101c0c82d2  -
$ shasum -a 256 /tmp/fiona-head.jinFc5/frontend/app/page.tsx
e7b9746a8b4d942a4c1ebd31bd5d6c6cde040d871b93040f371574101c0c82d2  /tmp/fiona-head.jinFc5/frontend/app/page.tsx
$ git show HEAD:frontend/components/ChatModelSection.tsx | shasum -a 256
dd9b582979bb7c65444f12ea20c1a1d9043fdee64ee6e31e03ed17048c844934  -
$ shasum -a 256 /tmp/fiona-head.jinFc5/frontend/components/ChatModelSection.tsx
dd9b582979bb7c65444f12ea20c1a1d9043fdee64ee6e31e03ed17048c844934  /tmp/fiona-head.jinFc5/frontend/components/ChatModelSection.tsx
```

### 2.4 状态检查

```text
$ git rev-parse HEAD
bccbf9f015b4f41f51b5ed009918b5021ac35b49
$ git status --porcelain -- backend/tests/test_ui_closeout_structure_guards.py
?? backend/tests/test_ui_closeout_structure_guards.py
```

运行期间工作树里另有其他 agent 对 `frontend/app/history/page.tsx`、`globals.css`、8 个 dialog 组件、两个门禁测试及各自新测试的改动；D 未触碰这些文件。本次 HEAD 对照用 `git archive HEAD`，不受并行改动影响。

## 3. 判断

- 规格 §2.5 盲区 2、3 的事实与 HEAD 一致：第二个 `<fieldset`（324 行）、首段（345 行）、Claude 提示（346 行）以及 2614–2620 的 7 行开场结构均如规格所述；没有触发「§2 事实对不上、白名单外既有测试变红、某条做不到」的停止条件。
- 工作树测试与 HEAD 副本测试均 7/7 PASS，满足「HEAD 上必须通过」。
- 自检不是只调一次检查函数：每份坏副本都在原测试已通过的前置条件下构造，再由 `_assert_rejected` 断言检查函数抛 `AssertionError`；若守卫失效，自检测试会以「坏副本没有被拦住」失败。
- 盲区 2 的括号平衡检查特意排除首段行本身：条件开括号落在区间内、闭括号落在首段行尾时，仍会因区间不平衡而失败。
- 测试只读取 `frontend/components/ChatModelSection.tsx` 与 `frontend/app/page.tsx`，不写仓库文件、不联网、不调 git、不需要 node。

## 4. 遗留

- 本任务只跑了自己的新测试文件；§5 第 4 条的全量 pytest 与最终 `git status`/白名单核对由主代理执行。
- 无功能遗留。若后续其他任务改动 `ChatModelSection.tsx` 的隐私段结构或 `page.tsx` 的 `data-chat-openers` 区块，本测试会按设计变红。
