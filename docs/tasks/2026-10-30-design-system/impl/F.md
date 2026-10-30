# F：既有测试字面量（T4）记录

- 角色：工作流 agent F（既有测试字面量）。只做 `02-spec.md` §4 T4；未调用 subagent / subagent_fork / workflow。
- 工作目录：`<工作树>`
- 基线：`HEAD` = `647a486`。git 只做读操作（`status` / `diff` / `show`），没有任何 git 写操作。
- 输入：`docs/tasks/2026-10-30-design-system/verify/test_literals.tsv`（29 个数据行、10 个文件）。
- 结果：PASS，无偏差。

## 1. 改动文件与行数

逐行把 `old` 原样换成 `new`；替换前断言该行里 `old` 恰好出现 1 次（29/29 通过）。采用按字节读写，只改目标行的目标片段，其他行与行尾不变。

| # | 文件（相对 `backend/tests/`） | 改动行 | 行数 |
|---|---|---|---:|
| 1 | test_empty_states_agents.py | 24、25、36、37、41、42、92、126、143 | 9 |
| 2 | test_empty_states_match_profile.py | 86 | 1 |
| 3 | test_empty_states_settings_privacy.py | 105 | 1 |
| 4 | test_mobile_chat_fix.py | 222、226 | 2 |
| 5 | test_novel_p21_frontend.py | 95、158 | 2 |
| 6 | test_novel_p2_frontend.py | 32 | 1 |
| 7 | test_song_frontend.py | 39、42 | 2 |
| 8 | test_ui_polish_beijing_time.py | 247 | 1 |
| 9 | test_ui_polish_composer_controls.py | 49、63、64、100、101、243、266、271、276 | 9 |
| 10 | test_ui_polish_markdown.py | 337 | 1 |
| | **合计** | | **29** |

29 行的 old → new 与 TSV 完全一致，未改表、未自行取整、未改其他测试、夹具或辅助模块。

## 2. numstat 核对

命令：

```bash
git diff --numstat HEAD -- backend/tests/
```

输出：

```text
9	9	backend/tests/test_empty_states_agents.py
1	1	backend/tests/test_empty_states_match_profile.py
1	1	backend/tests/test_empty_states_settings_privacy.py
2	2	backend/tests/test_mobile_chat_fix.py
2	2	backend/tests/test_novel_p21_frontend.py
1	1	backend/tests/test_novel_p2_frontend.py
2	2	backend/tests/test_song_frontend.py
1	1	backend/tests/test_ui_polish_beijing_time.py
9	9	backend/tests/test_ui_polish_composer_controls.py
1	1	backend/tests/test_ui_polish_markdown.py
```

- 既有文件恰好这 10 个；每个文件的增、删行数都等于表里该文件的行数；合计 `29 added / 29 deleted`。
- `git status --porcelain --untracked-files=all -- backend/tests/`：只有这 10 个 `M`，无新增/删除文件。
- `git diff --check -- backend/tests/`：退出码 0，无空白错误。

## 3. 逐行内容比对

用内联 Python 以 `git show HEAD:backend/tests/<file>` 为基准逐行核对：

- 每个文件实际变化行号集合 = TSV 该文件行号集合（29/29 文件内一致）；
- 每个变化行都等于「HEAD 原行把 `old` 恰好替换一次为 `new`」；
- 其余所有行与 HEAD 逐字节相同；
- 所有文件行数不变（只做行内替换，不增删行）。

```text
test_empty_states_agents.py: lines=9 changed=[24, 25, 36, 37, 41, 42, 92, 126, 143] untouched_identical=True
test_empty_states_match_profile.py: lines=1 changed=[86] untouched_identical=True
test_empty_states_settings_privacy.py: lines=1 changed=[105] untouched_identical=True
test_mobile_chat_fix.py: lines=2 changed=[222, 226] untouched_identical=True
test_novel_p21_frontend.py: lines=2 changed=[95, 158] untouched_identical=True
test_novel_p2_frontend.py: lines=1 changed=[32] untouched_identical=True
test_song_frontend.py: lines=2 changed=[39, 42] untouched_identical=True
test_ui_polish_beijing_time.py: lines=1 changed=[247] untouched_identical=True
test_ui_polish_composer_controls.py: lines=9 changed=[49, 63, 64, 100, 101, 243, 266, 271, 276] untouched_identical=True
test_ui_polish_markdown.py: lines=1 changed=[337] untouched_identical=True
ALL OK
```

## 4. pytest（只跑这 10 个文件）

在 `backend/` 下按 §3.5 清掉代理变量后执行：

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    .venv/bin/python -m pytest -q -p no:cacheprovider \
    tests/test_empty_states_agents.py \
    tests/test_empty_states_match_profile.py \
    tests/test_empty_states_settings_privacy.py \
    tests/test_mobile_chat_fix.py \
    tests/test_novel_p21_frontend.py \
    tests/test_novel_p2_frontend.py \
    tests/test_song_frontend.py \
    tests/test_ui_polish_beijing_time.py \
    tests/test_ui_polish_composer_controls.py \
    tests/test_ui_polish_markdown.py
```

结果：

```text
........................................................................ [ 46%]
........................................................................ [ 92%]
............                                                             [100%]
156 passed in 3.61s
```

- passed：**156**
- failed：**0**
- skipped：**0**
- 未跑全量 pytest；未跑其他测试文件。
- B 负责的 T2（`frontend/app/globals.css`、`frontend/lib/utils.ts`、`frontend/components/Seal.tsx`）落盘后，又用同一命令复跑了一次：`156 passed in 3.59s`，仍 0 failed、0 skipped。`test_mobile_chat_fix.py` 会读取 `globals.css` 的抽屉 `@media` 块，复跑确认 T2 未破坏它。

## 5. 保护文件

未改 `docs/tasks/2026-10-30-design-system/02-spec.md` 与 `verify/**`。前后 sha256 一致：

```text
1a0274b29affcce671f3e9a07ef83c1929ebc18ed7e1dbd083c0a7b01f73af0b  02-spec.md
e2a191cf795c18307d883dfb2da941ddca10c65ef6c4acfcb3adc369fb4cc3c6  verify/test_literals.tsv
7beed58a195bd0a8afead6621bca94da09f93bc9f4eea2c59a4b74c81bc454e7  verify/t2_edits.json
223580db0326928b4bb495619525647674d43b3b5f93890fc9ab4eb8d394f425  verify/replacements.tsv
```

## 6. 偏差与说明

- 无偏差；29 行全部按表替换，没有跳过或自行修正。
- 替换前在 `/tmp/fiona-F-backup/` 留了 10 个文件的临时备份，核对与测试通过后已删除；没有进入仓库。
- 只改动了本记录与上述 10 个既有测试文件。
