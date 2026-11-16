# 门禁返修单 第 3 轮（只补用例）：讨论群第二期（界面）

这是门禁返修，不计入复核返修轮次。**本轮不改实现，只补用例。**

## 一、返修 2 的核验结果

实现全部合格，不要再动：

- 范围合规；lint 0 错误 25 警告、类型检查、构建通过；全量 8607 条通过、0 失败、0 跳过。
- 真实浏览器按返修单 `06-fix-r2.md` 第三节逐条量过，九条全部合格：

| 判据 | 实测 |
|---|---|
| 1 抽屉列表页 1280×620 滚到底 | 底部留白 20px |
| 2 抽屉成果标签 1280×900 滚到底 | 底部留白 20px |
| 3 手机宽度 `/discuss` 滚到底 | 最后一张卡片在导航栏之上 20px |
| 4 手机宽度 `/discuss/new` 滚到底 | 「建群并立项」整个在导航栏之上，内容盒子留白 20px |
| 5 不回退 | 抽屉群聊 1280×900 页面不滚动、消息区 356px、插话框留白 20px；宽布局 1920×1000 两栏 787px 齐平；手机群聊页面不滚动；首次显示停在最新、来回切换保持位置 |
| 6 抽屉群聊 1280×620 | 消息区 120px，页面可滚 44px，滚到底留白 20px |
| 7 抽屉群聊 1280×440 | 消息区 120px，滚到底留白 20px |
| 8 宽布局 1920×520 | 两栏 320px，页面可滚 13px，滚到底留白 20px |
| 9 对话框 | 点内边距、点两个输入框之间的空隙都不关，填的数还在；点遮罩关闭；Esc 只关对话框；焦点回到触发按钮 |

## 二、问题：三条新守卫用例钉得不够

我把返修 2 的机制逐处改坏，跑 `test_discuss_frontend_*.py`、`test_discuss_ui_api.py` 和两份既有测试。16 处里 7 处被发现，下面 9 处全部通过（没有任何用例失败）：

| 编号 | 文件 | 把这段 | 改成这段 | 我在浏览器里量到的后果 |
|---|---|---|---|---|
| U2 | `DiscussShell.tsx` | `relative z-[1] flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto` | `relative z-[1] min-h-0 min-w-0 flex-1 overflow-y-auto` | 1920×1000 宽布局两栏只有 320px（应为 787px），下面空着 |
| U4 | `DiscussRoom.tsx` | `"flex flex-[1_0_auto] min-w-0 flex-col" data-discuss-room` | `"flex min-w-0 flex-col" data-discuss-room` | 同上，两栏 320px |
| U8 | `DiscussRoom.tsx` | `grid flex-[1_1_0px] min-h-[320px]` | `grid flex-1 min-h-[320px]` | 两栏被撑到 8241px，整页要滚 8454px |
| U11 | `DiscussRoom.tsx` | `className="mt-4 flex min-w-0 flex-[1_0_auto] flex-col"` | `className="mt-4 flex min-w-0 flex-col"` | 两栏 320px |
| U12 | `DiscussTimeline.tsx` | `<section className="flex flex-[1_0_auto] flex-col" aria-label="群聊">` | `<section className="flex flex-col" aria-label="群聊">` | 同类：群聊面板不再撑满 |
| U13 | `DiscussRoom.tsx` | `: "flex flex-[1_0_auto] flex-col"}` | `: "flex flex-col"}` | 同类：窄布局的布局层不再撑满 |
| U14 | `DiscussTimeline.tsx` | `<div className="relative flex min-h-0 flex-[1_0_auto] flex-col">` | `<div className="relative flex min-h-0 flex-col">` | 同类：消息区外层不再撑满 |
| U15 | `DiscussRoom.tsx` | `: "mt-4 flex min-w-0 flex-[1_0_auto] flex-col"}` | `: "mt-4 flex min-w-0 flex-col"}` | 同类：窄布局的群聊分区不再撑满 |
| U16 | `DiscussRoom.tsx` | `<div className="flex min-w-0 flex-[1_0_auto] flex-col">` | `<div className="flex min-w-0 flex-col">` | 同类：群聊分区的内层不再撑满 |

原因：现在的三条用例是按整份文件查子串的。`flex-[1_0_auto]` 在 `DiscussShell.tsx` 里只查「出现过」，`DiscussRoom.tsx` 里只查「没有 `h-full`」，所以从外壳到消息区这条「逐层撑满」的链，断掉哪一环用例都看不出来；`flex-[1_1_0px]` 只在 `DiscussTimeline.tsx` 里查，宽布局两栏的基准没人管；`main` 是不是纵向 flex 也没人管。

## 三、要求

1. 只改 `backend/tests/test_discuss_frontend_guards.py`（你自己的文件），再写报告 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r3.md`。其余文件一律不动，包括 `frontend/` 下的任何文件。如果你认为必须改实现才能测，停下来说明，不要改。
2. 补强后，上表 9 处改坏的每一处，都必须让至少一条用例**断言失败**（`failed`，不是 `error`）；返修 2 已经能发现的 7 处（内容容器写回 `h-full`、房间根节点写回 `h-full`、消息区去掉最小高度、消息区基准写回 `flex-1`、两栏去掉最小高度、`<dialog>` 加内边距、内容层去掉内边距）继续能发现。
3. 断言要落在具体的那个标签或那段类名上，不要按整份文件查子串。文件里已有 `iter_jsx_tags`，可以按标签上的标记找到目标，例如 `data-discuss-room`、`ref={contentRef}`、`ref={viewportRef}`、`aria-label="群聊"`、`<main`、带 `@container` 的内容容器；宽布局两栏那段类名可以用 `grid-rows-[auto_minmax(0,1fr)]` 定位。每条用例先断言找到了目标（个数符合预期），再断言它的类名。
4. 自检：把上表 9 处逐一改坏、跑用例、还原，每处写明是哪条用例失败、输出摘要。还原用你读到的原文写回，不用 `git stash`、`git checkout`。自检用的临时脚本放在仓库外的临时目录，用完删掉（上一轮留在系统临时目录里的 `r2_mutation.py` 也请删掉）。
5. 不提交 git。你实测到的事实优先于本单的断言，不符就停下来说明。任何情况下不回滚已完成的工作。

## 四、验收

命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. 在 `backend/`：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py` 全部通过、0 跳过。
2. 在 `backend/`：全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`，通过数 = 8607 + 本轮新增的用例数，0 失败、0 跳过。唯一的失败如果是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，单独重跑并贴出两次输出，不要为它改文件。
3. `git status --porcelain --untracked-files=all`：相对本单派出时，变动只有 `backend/tests/test_discuss_frontend_guards.py` 与新报告。
4. `git diff --stat -- frontend/`：与本单派出时相同（本轮没有改前端）。

报告不写本机绝对路径：补了哪些用例、各自钉住哪个标签的哪些类名；9 处自检表；验收四条的命令与输出摘要。
