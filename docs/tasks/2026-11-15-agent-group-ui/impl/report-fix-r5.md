# 门禁返修报告（只补用例）：复核返修 1 之后

依据 `docs/tasks/2026-11-15-agent-group-ui/08-fix-r4-review.md` 之后的门禁反馈。本轮不改实现、不改 `frontend/`，只补强 `backend/tests/test_discuss_frontend_guards.py`。

## 补了哪些用例

- `test_discuss_room_reads_use_server_cursor`（补强）
  - 定位 `publishDetail` 与 `sendNote` 两个函数块；
  - 断言 `publishDetail` 中用服务器读回的 `next.messages` 推进游标；
  - 断言 `sendNote` 里没有 `cursorRef`；
  - 断言全文件给 `cursorRef.current` 赋 `advanceDiscussCursor` 的地方恰好一处。
- `test_discuss_custom_helpers_are_used_in_components`（新增）
  - 定位 `handleTeamChange` 函数块，断言自定义成员初始模型来自 `defaultDiscussCustomMemberModel(catalog)`；
  - 定位 `renderMember` 函数块，断言「分工」条件是 `discussMemberShowsFocus(member)`，且不再出现 `member.kind === "lens" &&` 手写条件。
- `test_discuss_timeline_tracks_messages_while_hidden`（补强）
  - 仍断言隐藏分支置位 `pendingWhileHiddenRef`、回来读取、提示按钮；
  - 额外定位「回群聊」的 effect，断言 `const shouldFollow = nearBottomRef.current;`，且不允许写成 `true` / `false`。

讨论群新用例总数 55→56（净增 1 条）。

## 6 处自检表

把下表每一处按「改坏」列修改，运行 `tests/test_discuss_frontend_guards.py`，确认失败后按原文写回。全部是断言失败（`failed`），不是 `error` 或超时；每轮都是 `1 failed, 18 passed`。

| 编号 | 改坏方式 | 失败的用例 | 结果 |
|---|---|---|---|
| V2 | `sendNote` 成功拿到插话后追加 `cursorRef.current = advanceDiscussCursor(cursorRef.current, [message])` | `test_discuss_room_reads_use_server_cursor` | failed |
| V4 | 删掉 `publishDetail` 里的 `cursorRef.current = advanceDiscussCursor(cursorRef.current, next.messages)` | `test_discuss_room_reads_use_server_cursor` | failed |
| V7 | `handleTeamChange` 的 `customDefault` 改回 `catalog.models[0]?.id \|\| ""` | `test_discuss_custom_helpers_are_used_in_components` | failed |
| V9 | 只读视图条件改回 `member.kind === "lens" && !!member.focus` | `test_discuss_custom_helpers_are_used_in_components` | failed |
| V17 | 「回群聊」effect 的 `shouldFollow` 改成 `true` | `test_discuss_timeline_tracks_messages_while_hidden` | failed |
| V18 | 同一行改成 `false` | `test_discuss_timeline_tracks_messages_while_hidden` | failed |

自检临时脚本放在仓库外，运行完已删除。本轮之前已能发现的 14 处改坏未回退：原有 A/B/C/D/E/F/G/M16 守卫仍保留。

## 验收命令与输出摘要

1. 后端指定用例：
   `cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py`
   输出 `71 passed, 45 warnings in 6.54s`，0 skip、0 failed。
2. 后端全量：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider`
   输出 `1 failed, 8617 passed, 47 warnings in 413.73s (0:06:53)`。唯一失败是已知的旧用例：
   ```
   FAILED tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]
   ```
   本轮没有为它改文件。按返修单要求单独重跑两次：
   ```
   === RUN 1 ===
   ..                                                                       [100%]
   2 passed in 0.05s
   === RUN 2 ===
   ..                                                                       [100%]
   2 passed in 0.05s
   ```
   8617 + 失败 1 = 8618，等于上一轮 8617 + 本轮净增 1 条；除此之外 0 skip。
3. `git status --porcelain --untracked-files=all`：相对本单派出时，本轮变动只有 `backend/tests/test_discuss_frontend_guards.py` 与新报告 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r5.md`；其余状态项是之前各轮已存在的文件。任务目录里的 `09-fix-r5-tests.md` 是规格作者放置的本轮任务文档，未改。
4. `git diff --stat -- frontend/`：
   ```
    frontend/app/page.tsx           | 74 ++++++++++++++++++++++++++++++++++++++---
    frontend/components/Sidebar.tsx | 30 +++++++++++++------
    2 files changed, 90 insertions(+), 14 deletions(-)
   ```
   与本单派出时相同；本轮没有改 `frontend/` 下任何文件。

## 没做完或需要人工确认的地方

- 本轮只补静态守卫；A–G 的行为已由规格作者在真实浏览器核验，本轮不改实现，也没有新增浏览器验证。
- 全量里如果唯一失败是已知的 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，按返修单要求单独重跑并贴出两次输出，不为它改文件。
