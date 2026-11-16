# 门禁返修报告 第 2 轮：讨论群第二期（界面）

依据 `docs/tasks/2026-11-15-agent-group-ui/02-spec.md` 的「v1.2 修订」与 `06-fix-r2.md`。本轮只做 H、I、J；返修 1 的 A–G 表现未改。没有修改 `frontend/app/discuss/` 下的页面文件。

## H. 页面滚到底的底部留白

### 做了什么

- `frontend/components/discuss/DiscussShell.tsx`
  - `main` 改成纵向 flex 容器，仍保留 `overflow-y-auto`。
  - 内容容器去掉 `h-full`，改为 `flex-[1_0_auto]`：`flex-grow: 1`、`flex-shrink: 0`、`flex-basis: auto`。内容少时可以拉高填满主区，内容多时不压缩，主区滚动；`py-5` 的下内边距因此始终在真实内容之后。
- `frontend/components/discuss/DiscussRoom.tsx`
  - 房间根节点、内容层、标签以下的布局层、群聊 section、群聊内层都改为 `flex-[1_0_auto]`，不再写死 `h-full` 或 `min-h-full`。
  - 宽布局的两栏 grid 是「被限高的盒子」：`flex-[1_1_0px] min-h-[320px]`，沿用 `grid-rows-[auto_minmax(0,1fr)]`。
  - 窄布局群聊标签的消息区是「被限高的盒子」：`flex-[1_1_0px] min-h-[120px]`；群聊面板和房间根节点可以按内容被拉高、不能被压矮，页面不够高时由 `main` 滚动。
  - 窄布局的方案、成果、来源以及列表、新建、加载、错误等页面同样使用自然高度 + 可增长的内容层，下内边距在内容之后。
- 手机宽度：`main` 原有的 `mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]` 保留；内容容器 `py-5` 在内容之后，滚到底时最后内容与底部导航栏之间是 20px 的内容下内边距，不会被导航栏挡住。

### 为什么成立

- **下内边距在内容之后**：内容容器不再是固定 `h-full`。`flex-basis:auto` 让容器高度从内容出发，`flex-grow:1` 只在有剩余空间时拉高；内容超出时 `flex-shrink:0` 阻止它被压回视口，溢出由 `main` 的 `overflow-y-auto` 接管。因此 `py-5` 的底边始终跟在最后一段内容后面。
- **消息区不会被全部内容撑高**：真正滚动的消息区用 `flex-[1_1_0px]`，基准是 `0px` 而不是 `0%`，再配 `min-h-[120px]`。父链都是 `flex:1 0 auto`，只在可用高度里分配；开发模式 effect 跑两遍也不改变这个纯 CSS 高度链。
- **宽布局两栏等高**：grid 是唯一的限高盒子，左栏跨两行，右栏第一行标签、第二行面板；grid 高度由 `flex:1 1 0px` 和 `min-h-[320px]` 决定，左右两栏都填满同一个 grid 高度，各自内部滚动。

## I. 对话框只在点遮罩时关闭

- `frontend/components/discuss/DiscussDialogs.tsx`：`<dialog>` 自身去掉所有内边距，只保留边框、背景、`scrim-dialog`、尺寸和滚动；内容包进一层 `p-6 mobile:p-4` 的 `div`。
- 点内边距、控件之间空隙时，`event.target` 是内层 `div` 或其子元素，不等于 `currentTarget`，不会触发关闭；只有点对话框方框外的遮罩时 `target === currentTarget` 才关闭。
- 提交中 `requestClose` 不关闭；Esc、关闭按钮、取消按钮行为保持；打开时 `showModal()` 后聚焦第一个输入框，关闭时把焦点还给触发按钮（返修 1 已有逻辑未动）。
- 新增原生 `<dialog` 仍是 1 个，`test_ui_closeout_dialog_scrim.py` 的 15 不变。

## J. 群聊消息区最小高度

- `frontend/components/discuss/DiscussTimeline.tsx`：消息区从 `flex-1` 改为 `flex-[1_1_0px] min-h-[120px]`；Timeline 本身及中间容器改为 `flex-[1_0_auto]`，不再被内容压扁。
- `frontend/components/discuss/DiscussRoom.tsx`：窄布局群聊的消息区最小 120px；宽布局的 grid 最小 320px。视口不够时页面改为纵向滚动，群聊面板保持最小高度并完整显示插话框；视口够用时仍占满剩余高度、页面不滚动。
- 因为消息区基准是 0px，短视口下不会把全部消息高度算进页面；最小高度只在需要时把页面撑开。

## 改了哪些文件

- `frontend/components/discuss/DiscussShell.tsx`
- `frontend/components/discuss/DiscussRoom.tsx`
- `frontend/components/discuss/DiscussTimeline.tsx`
- `frontend/components/discuss/DiscussDialogs.tsx`
- `backend/tests/test_discuss_frontend_guards.py`
- `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r2.md`

`frontend/app/discuss/`、`frontend/app/page.tsx`、`frontend/components/Sidebar.tsx`、`globals.css`、两份既有测试、后端代码均未改。

## 新用例与自检表

在 `test_discuss_frontend_guards.py` 新增 3 条（讨论群新用例总数 42→45）：

- `test_discuss_shell_content_grows_without_fixed_full_height`：`DiscussShell` 有 `flex-[1_0_auto]` 与 `py-5`，并且没有 `h-full`。
- `test_discuss_chat_has_min_height_contracts`：`DiscussTimeline` 有 `min-h-[120px]` 与 `flex-[1_1_0px]`，`DiscussRoom` 有 `min-h-[320px]`。
- `test_discuss_dialog_padding_is_inside_not_on_dialog_element`：原生 `<dialog` 标签含 `scrim-dialog` 且不带内边距类，源码里内层仍有 `p-6`。

每条用例都先断言扫描到了目标（内容容器/消息区/原生 `<dialog>`），再断言实现。

| # | 改坏的实现 | 发现问题的用例 | 结果 |
|---:|---|---|---|
| 1 | `DiscussShell.tsx` 的内容容器 `flex-[1_0_auto]` 改回 `h-full` | `test_discuss_shell_content_grows_without_fixed_full_height` | failed（1 failed, 11 passed） |
| 2 | `DiscussTimeline.tsx` 的消息区 `min-h-[120px]` 改回 `min-h-0` | `test_discuss_chat_has_min_height_contracts` | failed（1 failed, 11 passed） |
| 3 | 在原生 `<dialog>` 的类名里加 `p-6` | `test_discuss_dialog_padding_is_inside_not_on_dialog_element` | failed（1 failed, 11 passed） |

每条都是断言失败（`failed`），不是 `error` 或超时；运行后都用原文恢复，并复跑 36 条守卫/导航/既有页面用例通过。


## 验收命令与输出摘要

1. 前端 `cd frontend`，均加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=...`：
   - `npm run lint -- --max-warnings=25`：退出码 0，`✖ 25 problems (0 errors, 25 warnings)`。
   - `npx tsc --noEmit`：退出码 0，无输出。
   - `npm run build`：退出码 0，路由表含 `○ /discuss`、`○ /discuss/new`、`ƒ /discuss/[id]`。
2. 后端指定用例：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py tests/test_studio_frontend_*.py`
   输出 `104 passed, 45 warnings in 13.94s`，0 skip、0 failed。
3. 后端全量：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider`
   输出 `1 failed, 8606 passed, 47 warnings in 589.34s (0:09:49)`。唯一失败是已知的旧用例：
   ```
   FAILED tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]
   ```
   本轮没有为它改文件。按返修单要求单独重跑两次：
   ```
   === RUN 1 ===
   ..                                                                       [100%]
   2 passed in 0.08s
   === RUN 2 ===
   ..                                                                       [100%]
   2 passed in 0.07s
   ```
   8606 + 失败 1 = 8607，等于上一轮 8604 + 本轮 3 条新用例；除此之外 0 skip。
4. 两份既有测试的 diff 统计（与返修 1 交回时相同，本轮未改）：
   `git diff --stat -- backend/tests/test_ui_polish_page_contracts.py backend/tests/test_ui_closeout_dialog_scrim.py`
   ```
    backend/tests/test_ui_closeout_dialog_scrim.py | 2 +-
    backend/tests/test_ui_polish_page_contracts.py | 7 ++++---
    2 files changed, 5 insertions(+), 4 deletions(-)
   ```
5. `git status --porcelain --untracked-files=all`：相对本单派出时，本轮新增改动只有 `frontend/components/discuss/DiscussShell.tsx`、`DiscussRoom.tsx`、`DiscussTimeline.tsx`、`DiscussDialogs.tsx`、`backend/tests/test_discuss_frontend_guards.py` 与本报告；其余状态项是上一轮已存在、本单未改动的文件。没有改 `frontend/app/discuss/`、`frontend/app/page.tsx`、`frontend/components/Sidebar.tsx`、`globals.css`、两份既有测试、后端代码、规格或依赖。


## 没做完或需要人工确认的地方

- H、J 的最终像素值由规格作者在真实浏览器按第三节判据核验；本环境没有浏览器。实现按 v1.2 给出的 `flex:1 0 auto` + `flex:1 1 0px` + 最小高度方案落地，并在构建产物里确认生成了 `flex:1 0 auto`、`min-height:120px`、`min-height:320px`。
- I 的点击遮罩、内边距、控件间隙行为同样需要在真实浏览器确认；静态用例只锁定「dialog 自身无内边距、内容层有内边距」。
- 极矮视口的具体滚动距离由浏览器布局决定，本单不写死像素值。
