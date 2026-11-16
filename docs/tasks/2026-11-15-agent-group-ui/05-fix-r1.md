# 门禁返修单 第 1 轮：讨论群第二期（界面）

首轮交回的门禁结果：改动范围合规；lint、类型检查、构建全过；新用例 39 条全过；后端全量 `8601 passed`、0 跳过；规格作者的盲测探针 26 项全过；变异 66 条全部被断言发现。功能在真实浏览器里全部走通。

下面是真实浏览器走查里发现的问题（静态检查和单元测试都抓不到），加上作者对你报告里两处绕行的决定。依据：规格 `02-spec.md` 开头新增的「v1.1 修订」，先读那一节。

## 一、规矩

1. 允许改的文件：规格 4.1 两张表里的文件；下面 A、B 两条点名的两份既有测试（只许改写明的那几处）；新报告 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r1.md`。
2. 不许动：其他既有测试、`frontend/app/globals.css`、`frontend/lib/messageMarkdown.ts`、`frontend/components/novel/`、任务目录下的规格与返修单。
3. 界面上的中文文案一个字都不要改。已经通过的行为不要动。
4. 不 commit / stash / checkout / reset；不装依赖；不读 `.env`；不访问外网；不调用真实模型。
5. 本单按文件不重叠拆分，用工作流（workflow 工具）并行：`parallel()` 同时运行多个 agent，每个 agent 的任务说明自包含，并写明不得调用 subagent / subagent_fork / workflow。同一个文件只归一个 agent。也可以由你直接完成。
6. 你实测到的事实优先于本单的说法；不符就停下来在报告里说明。只有影响「实现什么」的矛盾才停；任何情况不回滚已完成的工作。

## 二、要改的

### A. 抽屉类名不再拆开拼接（作者决定）

- `frontend/app/page.tsx`：删掉 `drawerPanelClass` 这个常量，讨论群抽屉的 `className` 里直接写 `drawer-panel`，写法与工作室抽屉相同。
- `backend/tests/test_ui_polish_page_contracts.py`，只许改这四处：
  - `DRAWER_IDS` 末尾加上 `"discuss"`；
  - `assert source.count("drawer-panel") == 6` 改成 `== 7`；
  - 那条用例的函数名里的 `six` 改成 `seven`；
  - 在最后一条顺序断言后面加一行：`assert source.index('id="studio-drawer"') < source.index('id="discuss-drawer"')`。
- 你自己的 `test_discuss_frontend_navigation.py` 里那条 `count("drawer-panel") == 6` 同步改成 7，并断言源码里没有 `"drawer" + "-panel"` 这种拼接。

### B. 两个对话框改用原生 `dialog`（作者决定）

- 追加轮数（含「按意见返工」）与追加预算两个对话框改用原生 `<dialog>`，写法照 `frontend/components/novel/NovelSettingsDialog.tsx`：挂载后 `showModal()`，卸载时 `close()`，`onCancel` 里提交中不许关、其余情况关闭，`className` 里带 `scrim-dialog`。不再用 `role="dialog"` 的手写弹层。
- 打开时焦点落在第一个输入框上（不是「关闭」按钮）。关闭后焦点回到触发它的那个按钮。在对话框里按 Esc 只关对话框，不关抽屉。
- `backend/tests/test_ui_closeout_dialog_scrim.py`，只许改一处：`assert_dialogs_have_scrim` 的默认参数 `expected_count=14`，改成 14 加上你新增的原生 `<dialog` 标签个数。在报告里写明新增了几个、各在哪个文件。

### C. 侧栏书签区不显示滚动条

现象：视口 1280×620 时，书签区右边露出一条 11px 宽的细滚动条，书签整体左移 5.5px。原因见规格 v1.1 第 7 条。

要求：书签区隐藏滚动条的类用带 `!` 的写法。放不下时仍然可以滚动。

### D. 表格换行，表头不加粗

现象：真实成果里一张两列的表格被撑到 1019px 宽（容器 720px），要横向拖动才能读完；表头是粗体（字重 700）。

要求：见规格 v1.1 第 2、3 条。表头 `th` 写上 `font-normal`。

### E. 群聊第一次显示时停在最新一条

现象：打开一个默认停在「成果」的群，再切到「群聊」，消息区停在最早一条；默认就在「群聊」的群，开发模式下也停在最早一条。

要求：见规格 v1.1 第 4 条。

### F. 群聊的高度

现象：群聊面板的高度写死成 `100dvh - 320px`。视口 1280×620 时整页出现纵向滚动，消息区只有 229px；视口 1440×900 时消息区 284px，下面还空着八十多像素。

要求：见规格 v1.1 第 5 条。插话框默认两行高。

### G. 宽布局的标签条位置

要求：见规格 v1.1 第 6 条。

## 三、测试

1. 新用例放进你已有的 `test_discuss_frontend_guards.py` 或 `test_discuss_frontend_navigation.py`（这两份是你自己的，可以改），至少包括：
   - 讨论群部件里每个 `<th` 都带 `font-normal`（先断言扫到的 `<th` 个数大于 0）；
   - 侧栏书签区的类名里有带 `!` 的隐藏滚动条写法；
   - 主页源码里没有 `"drawer" + "-panel"`；
   - 讨论群部件里没有 `role="dialog"` 的手写弹层，新对话框的 `<dialog` 标签带 `scrim-dialog`。
2. E、F、G 是布局与滚动行为，由规格作者在真实浏览器里核验；你不用写用例，但要在报告里说明实现思路，以及为什么在开发模式（effect 执行两遍）下也成立。
3. 自检表：上面每条新用例对应的改坏方式，由哪条用例靠断言失败发现（必须是 `failed`）。

## 四、验收

命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. 在 `frontend/`：`npm run lint -- --max-warnings=25`、`npx tsc --noEmit`、`npm run build` 都是退出码 0。
2. 在 `backend/`：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py tests/test_studio_frontend_*.py` 全部通过、0 跳过。
3. 在 `backend/`：全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`，通过数 = 8601 + 本轮新增的用例数，0 失败、0 跳过。唯一的失败如果是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，单独重跑并贴出两次输出，不要为它改文件。
4. `git diff --stat -- backend/tests/test_ui_polish_page_contracts.py backend/tests/test_ui_closeout_dialog_scrim.py`：两份既有测试的改动只有 A、B 写明的那几处，把 diff 原文贴进报告。
5. `git status --porcelain --untracked-files=all`：相对本单派出时，变动只在第一节第 1 条允许的文件里。

报告写进 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r1.md`，不写本机绝对路径：A–G 逐条做了什么、改了哪些文件、两份既有测试的 diff 原文、新用例与自检表、验收五条的命令与输出摘要、没做完或需要人工确认的地方。
