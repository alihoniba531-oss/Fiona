# 复核返修单 第 2 轮（只补用例）：讨论群第二期（界面）

依据第 2 轮独立复核 `04-review-r2.md`。这是复核返修的第 2 轮（最多 3 轮）。**本轮不改实现，只改用例。**

## 一、现状

- 第 2 轮复核对 A–G 七项的实现全部认可：没有带出新的错误，不用改实现。
- 上一张只补用例的单子（`09-fix-r5-tests.md`）已过门禁：前端逐字节未变；V1–V20 二十处改坏全部被断言发现。
- 复核方在那 6 处之外又找到几处「一行就能改坏、用例照样通过」的地方，都在守卫里。下面是要补的。

## 二、要拦住的改坏

把实现改成下面的样子时，现在的用例全部通过；补强后每一处都必须让至少一条用例**断言失败**（`failed`，不是 `error`）。

| 编号 | 文件 | 把这段 | 改成这段 | 后果 |
|---|---|---|---|---|
| W1 | `DiscussDocument.tsx` | `` `${discussTableMinWidth(block.header.length)}em` `` | `` `${discussTableMinWidth(block.header.length)}px` `` | 十列的表最小宽度只有 80px，各列又被挤回去 |
| W2 | `DiscussDocument.tsx` | `discussTableMinWidth(block.header.length)` | `discussTableMinWidth(block.rows.length)` | 最小宽度按行数算，与列数无关 |
| W3 | `DiscussComposer.tsx` | `finally` 里的 `textareaRef.current?.focus();` | 挪到 `try` 里 `setText("");` 的后面，`finally` 里不再有 | 发送失败后焦点又丢了 |
| W4 | `DiscussTimeline.tsx` | 「回到群聊标签」那个 effect 里的 `pendingWhileHiddenRef.current = false;` | 删掉 | 之后每次切回群聊都重做一次跟随或提示：没有新消息也会冒出「有新消息」 |
| W5 | `DiscussDocument.tsx` | `const href = source ? safeExternalUrl(source.url) : null;` | `const href = source ? (safeExternalUrl(source.url) ?? source.url) : null;` | 不安全的地址又能点了 |
| W6 | `DiscussSourcesPanel.tsx` | `const href = safeExternalUrl(source.url);` | `const href = safeExternalUrl(source.url) \|\| source.url;` | 同上 |
| W7 | `DiscussTimeline.tsx` | `if (arrived && !firstViewRef.current) pendingWhileHiddenRef.current = true;` | `if (arrived) pendingWhileHiddenRef.current = true;` | 还没看过群聊时就留下一个过期标记 |

W1–W4 是复核的必须修复 1–3（复核报告里的 R13、R14、R15、R19）；W5、W6 是可优化第 1 条（R02、R03），涉及安全路径，这次一并钉住；W7 是 R18，与 W4 同源。

## 三、要求

1. 只改 `backend/tests/test_discuss_frontend_guards.py`；第 4 条里那处清理改 `backend/tests/test_discuss_frontend_logic.py`。再写报告 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r6.md`。其余文件一律不动，包括 `frontend/` 下的任何文件。如果你认为必须改实现才能测，停下来说明，不要改。
2. 断言落在具体的标签、函数或代码块上，先断言找到了目标，再断言内容。可以参考的钉法（你也可以用别的）：
   - W1、W2：`DiscussDocument.tsx` 唯一的 `<table>` 标签上，`minWidth` 的值恰好是 `` `${discussTableMinWidth(block.header.length)}em` ``。
   - W3：取出 `DiscussComposer.tsx` 里 `submit` 的函数体，`textareaRef.current?.focus()` 在它的 `finally { … }` 块里，不在 `try { … }` 块里。
   - W4、W7：`DiscussTimeline.tsx` 里读取 `pendingWhileHiddenRef` 的那个 effect 中有 `pendingWhileHiddenRef.current = false`；不可见分支里置位的条件带着 `!firstViewRef.current`。与 V17、V18 用同一个定位即可。
   - W5、W6：两个文件里给 `href` 赋值的那一句，右边除了 `safeExternalUrl(source.url)` 之外不再出现 `source.url`（注意来源面板里把地址当文字显示的地方是允许的，不要误伤）。
3. 上一轮之前已经能发现的改坏继续能发现。
4. 顺手清理（复核可优化第 5 条）：`test_discuss_frontend_logic.py` 的 `test_advance_cursor_only_moves_on_server_reads` 里，`localNoteOnly` 与 `afterLocalThree` 都是 `advanceDiscussCursor(1, [])`，和 `emptyReadKeeps` 测的是同一件事，名字却让人以为测到了「插话不推动游标」。删掉这两个重复的情形，或改成名副其实的名字；断言同步调整。
5. 自检：把上表 7 处逐一改坏、跑用例、还原，每处写明是哪条用例失败、输出摘要。还原用你读到的原文写回，不用 `git stash`、`git checkout`。自检用的临时脚本放在仓库外的临时目录，用完删掉。
6. 不提交 git。你实测到的事实优先于本单的断言，不符就停下来说明。任何情况下不回滚已完成的工作。复核报告里其余的可优化项本轮不要做。

## 四、验收

命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. 在 `backend/`：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py` 全部通过、0 跳过。
2. 在 `backend/`：全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`，0 失败、0 跳过，通过数 = 8618 + 本轮净增的用例数（写明净增几条；只是在已有用例里加断言的话净增为 0）。唯一的失败如果是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，单独重跑并贴出两次输出，不要为它改文件。
3. `git status --porcelain --untracked-files=all`：相对本单派出时，变动只有这两份测试文件与新报告。
4. `git diff --stat -- frontend/`：与本单派出时相同（本轮没有改前端）。

报告不写本机绝对路径：补了哪些断言、各自钉住什么；7 处自检表；第 4 条的清理；验收四条的命令与输出摘要。
