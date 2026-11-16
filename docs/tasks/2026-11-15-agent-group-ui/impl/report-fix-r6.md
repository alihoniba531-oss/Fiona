# 复核返修报告（只补用例）第 2 轮

依据第 2 轮独立复核 `04-review-r2.md` 与门禁返修单。本轮不改实现、不改 `frontend/`，只补强 `backend/tests/test_discuss_frontend_guards.py`，并按第 4 条清理 `backend/tests/test_discuss_frontend_logic.py` 的重复游标情形。

## 补了哪些断言

1. **W1、W2：表格最小宽度**
   `test_discuss_tables_have_column_min_width` 定位唯一的 `<table>`，要求 `minWidth` 的值恰好是：
   `` `${discussTableMinWidth(block.header.length)}em` ``
   因此改成 `px`、或把 `header.length` 改成 `rows.length` 都会失败。

2. **W3：焦点恢复在 `finally`**
   `test_discuss_composer_keeps_focus_while_sending` 用 `brace_block` 取出 `submit`、`try`、`finally` 三个块，断言 `textareaRef.current?.focus()` 在 `finally` 里、不在 `try` 里；同时保留 `readOnly`、无 `disabled`、`ref={textareaRef}` 等旧断言。

3. **W4、W7：隐藏期间标记的生命周期**
   `test_discuss_timeline_tracks_messages_while_hidden` 定位「回到群聊」的 effect，断言：
   - 隐藏分支置位必须是 `if (arrived && !firstViewRef.current) pendingWhileHiddenRef.current = true;`；
   - 跟随或提示后必须 `pendingWhileHiddenRef.current = false;`；
   - `shouldFollow` 仍必须来自 `nearBottomRef.current`。
   删掉清理、或把置位条件改成 `if (arrived)` 都会失败。

4. **W5、W6：外链赋值行**
   `test_discuss_external_links_use_safe_external_url` 在每个文件里定位唯一的 `const href` 行，断言该行除 `safeExternalUrl(source.url)` 的参数外不再出现 `source.url`。`?? source.url` 或 `|| source.url` 都会让计数变成 2 而失败；来源面板里把地址当文字显示的其他行不受影响。

## 第 4 条清理

`test_advance_cursor_only_moves_on_server_reads` 删掉了 `localNoteOnly` 与 `afterLocalThree` 两个都是 `advanceDiscussCursor(1, [])` 的重复情形，只保留：服务器返回 2、3 后游标为 3；空读保持 5；更小 id 保持 5；0 游标为 0。断言同步调整。没有新增或删除测试函数。

## 7 处自检表

W3 的改坏需要两处编辑（`finally` 里移除、`try` 里加入），因此分 W3a/W3b 两次运行；其余各一次。每次修改后运行 `tests/test_discuss_frontend_guards.py`，再按原文写回。全部是断言失败（`failed`），不是 `error` 或超时；每轮都是 `1 failed, 18 passed`。

| 编号 | 改坏方式 | 失败的用例 | 结果 |
|---|---|---|---|
| W1 | 表格 `minWidth` 单位从 `em` 改成 `px` | `test_discuss_tables_have_column_min_width` | failed |
| W2 | 表格最小宽度按 `block.rows.length` 计算 | `test_discuss_tables_have_column_min_width` | failed |
| W3a | 从 `finally` 删除 `textareaRef.current?.focus()` | `test_discuss_composer_keeps_focus_while_sending` | failed |
| W3b | 在 `try` 的 `setText("")` 后加入焦点恢复 | 同上 | failed |
| W4 | 删除隐藏标记的 `pendingWhileHiddenRef.current = false;` | `test_discuss_timeline_tracks_messages_while_hidden` | failed |
| W5 | `DiscussDocument` 的 href 加 `?? source.url` | `test_discuss_external_links_use_safe_external_url` | failed |
| W6 | `DiscussSourcesPanel` 的 href 加 `\|\| source.url` | 同上 | failed |
| W7 | 隐藏分支置位条件去掉 `!firstViewRef.current` | `test_discuss_timeline_tracks_messages_while_hidden` | failed |

自检临时脚本放在仓库外，运行完已删除。之前已能发现的改坏没有回退。

## 验收命令与输出摘要

1. 后端指定用例：
   `cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py`
   输出 `71 passed, 45 warnings in 6.33s`，0 skip、0 failed。
2. 后端全量：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider`
   输出 `8618 passed, 47 warnings in 425.47s (0:07:05)`：本轮只在已有用例里加断言、没有新增测试函数，净增 0 条；0 failed、0 skip。47 条 warning 都是第三方库的 DeprecationWarning。
3. `git status --porcelain --untracked-files=all`：相对本单派出时，本轮变动只有 `backend/tests/test_discuss_frontend_guards.py`、`backend/tests/test_discuss_frontend_logic.py` 与新报告 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r6.md`；其余状态项是之前各轮已存在的文件。任务目录里的 `04-review-r2.md`、`10-fix-r6-tests.md` 是规格作者/复核方放置的文档，本轮没有改。
4. `git diff --stat -- frontend/`：
   ```
    frontend/app/page.tsx           | 74 ++++++++++++++++++++++++++++++++++++++---
    frontend/components/Sidebar.tsx | 30 +++++++++++++------
    2 files changed, 90 insertions(+), 14 deletions(-)
   ```
   与本单派出时相同；本轮没有改 `frontend/` 下任何文件。

## 没做完或需要人工确认的地方

- 本轮只补静态断言和清理重复游标情形，不改实现；W1–W7 的真实浏览器行为已由复核方/规格作者核验，本轮不新增浏览器验证。
- 全量里如果唯一失败仍是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，按返修单要求单独重跑并贴出两次输出，不为它改文件。
