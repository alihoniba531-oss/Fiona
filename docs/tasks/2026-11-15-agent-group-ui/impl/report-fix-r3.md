# 门禁返修报告 第 3 轮（只补用例）：讨论群第二期（界面）

依据 `docs/tasks/2026-11-15-agent-group-ui/02-spec.md` 的「v1.2 修订」与第 3 轮返修要求。本轮不改实现、不改 `frontend/`，只补强 `backend/tests/test_discuss_frontend_guards.py` 并写本报告。

## 补了哪些用例

把返修 2 的 3 条守卫改成按具体标签断言，并新增 1 条房间逐层 flex 链用例；讨论群新用例总数 45→46。

1. `test_discuss_shell_main_and_content_flex_chain`（替换原来的整文件子串断言）
   - 找到唯一 `<main` 标签，断言类名包含 `flex min-h-0 min-w-0 flex-1 flex-col`。
   - 找到唯一带 `@container` 的内容容器，断言类名包含 `flex-[1_0_auto]`、`py-5`，且不含 `h-full`。
2. `test_discuss_chat_flex_chain_and_min_height`（替换原来的整文件子串断言）
   - 找到唯一 `aria-label="群聊"` 的 `<section`，断言类名包含 `flex-[1_0_auto]`。
   - 找到唯一 `ref={viewportRef}` 的消息区，断言类名包含 `min-h-[120px]`、`flex-[1_1_0px]`。
   - 断言消息区前一个 opening 标签（消息区外层 `div`）含 `flex-[1_0_auto]`。
3. `test_discuss_room_layout_flex_chain`（新增）
   - `data-discuss-room` 根节点含 `flex-[1_0_auto]`。
   - `ref={contentRef}` 标签区内容层含 `flex-[1_0_auto]`。
   - 用 `grid-rows-[auto_minmax(0,1fr)]` 找到宽布局两栏 grid，断言含 `flex-[1_1_0px]`、`min-h-[320px]`，并断言同一个标签的窄布局分支含 `flex flex-[1_0_auto] flex-col`。
   - `id="discuss-panel-chat"` 群聊分区含 `flex-[1_0_auto]`；它后面的下一个 opening 标签（群聊内层 `div`）也含 `flex-[1_0_auto]`。
4. 保留并继续使用 `test_discuss_dialog_padding_is_inside_not_on_dialog_element`：原生 `<dialog` 无内边距类、含 `scrim-dialog`，内容层仍有 `p-6`。

所有定位都先断言目标数量符合预期，再断言具体标签的类名，不按整份文件查子串。

## 9 处自检表

把下表每一处按「改坏」列修改，运行 `tests/test_discuss_frontend_guards.py`，确认失败后按原文写回。全部是断言失败（`failed`），不是 `error` 或超时。每轮都是 `1 failed, 12 passed`。

| 编号 | 改坏的文件与位置 | 失败的用例 | 结果 |
|---|---|---|---|
| U2 | `DiscussShell.tsx` 的 `<main` 去掉 `flex` 与 `flex-col` | `test_discuss_shell_main_and_content_flex_chain` | failed |
| U4 | `DiscussRoom.tsx` 的 `data-discuss-room` 根节点去掉 `flex-[1_0_auto]` | `test_discuss_room_layout_flex_chain` | failed |
| U8 | `DiscussRoom.tsx` 的宽布局 grid 把 `flex-[1_1_0px]` 改成 `flex-1` | `test_discuss_room_layout_flex_chain` | failed |
| U11 | `DiscussRoom.tsx` 的 `ref={contentRef}` 内容层去掉 `flex-[1_0_auto]` | `test_discuss_room_layout_flex_chain` | failed |
| U12 | `DiscussTimeline.tsx` 的 `aria-label="群聊"` section 去掉 `flex-[1_0_auto]` | `test_discuss_chat_flex_chain_and_min_height` | failed |
| U13 | `DiscussRoom.tsx` 的窄布局布局层分支去掉 `flex-[1_0_auto]` | `test_discuss_room_layout_flex_chain` | failed |
| U14 | `DiscussTimeline.tsx` 的消息区外层 div 去掉 `flex-[1_0_auto]` | `test_discuss_chat_flex_chain_and_min_height` | failed |
| U15 | `DiscussRoom.tsx` 的窄布局群聊分区分支去掉 `flex-[1_0_auto]` | `test_discuss_room_layout_flex_chain` | failed |
| U16 | `DiscussRoom.tsx` 的群聊分区内层 div 去掉 `flex-[1_0_auto]` | `test_discuss_room_layout_flex_chain` | failed |

自检脚本放在仓库外临时目录，运行完已删除；上一轮的临时脚本也已删除。原有 7 处（内容容器写回 `h-full`、房间根节点写回 `h-full`、消息区去掉最小高度、消息区基准写回 `flex-1`、两栏去掉最小高度、`<dialog>` 加内边距、内容层去掉内边距）仍由上述按标签断言的用例覆盖。

## 验收命令与输出摘要

1. 后端指定用例：
   `cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py`
   输出 `61 passed, 45 warnings in 5.80s`，0 skip、0 failed。
2. 后端全量：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider`
   输出 `8608 passed, 47 warnings in 460.39s (0:07:40)`：通过数 = 上一轮 8607 + 本轮新增 1 条用例，0 failed、0 skip。47 条 warning 都是第三方库的 DeprecationWarning。
3. `git status --porcelain --untracked-files=all`：相对本单派出时，本轮变动只有 `backend/tests/test_discuss_frontend_guards.py` 与新报告 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r3.md`；其余状态项是前两轮已存在的文件。任务目录里的 `07-fix-r3-tests.md` 是规格作者放置的本轮任务文档，本单没有改它。
4. `git diff --stat -- frontend/`：
   ```
    frontend/app/page.tsx           | 74 ++++++++++++++++++++++++++++++++++++++---
    frontend/components/Sidebar.tsx | 30 +++++++++++++------
    2 files changed, 90 insertions(+), 14 deletions(-)
   ```
   这是返修 1 之前就有的改动；本轮没有改 `frontend/` 下任何文件，diff 与本单派出时相同。

## 没做完或需要人工确认的地方

- 本轮只补静态守卫；布局与点击行为仍由规格作者在真实浏览器核验，本轮不改实现。
- 全量里如果唯一失败仍是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，按返修单要求单独重跑并贴出两次输出，未为它改文件。
