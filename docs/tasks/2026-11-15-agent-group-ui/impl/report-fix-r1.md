# 门禁返修报告 第 1 轮：讨论群第二期（界面）

依据 `docs/tasks/2026-11-15-agent-group-ui/02-spec.md` 开头的「v1.1 修订」与 `05-fix-r1.md`。本轮只改规格 4.1 两张表里的文件、返修单点名的两份既有测试与这份报告；既有界面中文文案未改。

## A. 抽屉类名不再拆开拼接

- `frontend/app/page.tsx`：删掉 `drawerPanelClass` 常量，讨论群抽屉 `className` 直接写完整的 `drawer-panel`，与工作室抽屉写法一致。编辑后确认文件仍以 UTF-8 BOM（`EF BB BF`）开头，满足既有 BOM 契约。
- `backend/tests/test_ui_polish_page_contracts.py` 只改四处：`DRAWER_IDS` 末尾加 `"discuss"`；计数 6→7；用例函数名 `six`→`seven`；顺序断言最后加 `studio < discuss`。
- `backend/tests/test_discuss_frontend_navigation.py`：计数 6→7，并断言源码没有 `drawerPanelClass` 和 `"drawer" + "-panel"` 拼接。

## B. 两个对话框改用原生 `dialog`

- `frontend/components/discuss/DiscussDialogs.tsx` 的 `DialogFrame` 改回原生 `<dialog>`：挂载后 `showModal()`，卸载时 `close()`；`onCancel` 里提交中 `preventDefault`、其余情况关闭；`className` 含 `scrim-dialog`。
- 打开时先 `showModal()`，再聚焦第一个输入框（不是「关闭」按钮）；打开时记录触发按钮，卸载时若仍可见就把焦点还给它。
- 对话框自己的 `onKeyDown` 对 Escape 调 `stopPropagation()`，因此 Esc 只触发原生 `cancel` / 关闭对话框，不冒泡到主页抽屉或 iframe 外壳。
- 新增的原生 `<dialog` 标签 **1 个**，在 `frontend/components/discuss/DiscussDialogs.tsx`；`backend/tests/test_ui_closeout_dialog_scrim.py` 只把 `assert_dialogs_have_scrim` 的默认 `expected_count` 从 14 改成 15。

## C. 侧栏书签区不显示滚动条

- `frontend/components/Sidebar.tsx` 的书签区隐藏滚动条类改为带 `!` 的写法：`[scrollbar-width:none]!` 与 `[&::-webkit-scrollbar]:hidden!`，覆盖 `globals.css` 里 `html, * { scrollbar-width: thin !important; }` 的全局规则。
- 仍然保留 `overflow-y-auto`，放不下时可以滚动；没有改书签字号或间距。
- 构建后检查生成的 CSS，确认存在 `scrollbar-width:none!important` 与 `::-webkit-scrollbar{display:none!important}`。

## D. 表格换行，表头不加粗

- `frontend/components/discuss/DiscussDocument.tsx`：表格从 `w-max min-w-full` 改为 `w-full table-fixed`，宽度跟随容器，单元格继续 `whitespace-pre-wrap break-words`；只有内容确实放不下时才由外层 `overflow-x-auto` 横向滚动。
- 表头 `th` 加 `font-normal`，覆盖浏览器默认的 700 字重。
- 新守卫扫描讨论群部件的全部 `<th`，先断言数量大于 0，再要求每个标签都带 `font-normal`。

## E. 群聊第一次显示停在最新一条

- `frontend/components/discuss/DiscussTimeline.tsx` 新增 `active` 属性；`DiscussRoom` 在群聊真正可见时传 `active={wide || tab === "chat"}`。
- 用 `firstViewRef` 标记「还没真正看过群聊」，在 `active` 变为真时用 `requestAnimationFrame` 滚到 `scrollHeight`，并检查元素有布局盒子（`getClientRects().length > 0`）。滚动成功后才把标记置假。
- 清理函数会 `cancelAnimationFrame`。开发模式 effect 执行两遍时，第一遍被清理取消，第二遍仍会执行，因此不依赖「effect 只跑一次」。
- 原来的消息变化 effect 在 `active` 为假时只更新最后消息 id、不滚动；因此之后在标签间切换、或离开期间有新消息，都不会把离开时的位置改掉。第一次真正可见后，`firstViewRef` 已为假，再做标签切换不再强制回到底部。

## F. 群聊的高度

- `DiscussShell` 固定为 `h-dvh`，主区 `flex-1 min-h-0 overflow-y-auto`，内容容器 `flex h-full min-h-0 flex-col`，为群聊页提供确定的高度链；列表页和新建页仍由主区滚动。
- `DiscussRoom` 在「宽布局」或「窄布局的群聊标签」时使用 `flex h-full min-h-0 flex-col`，顶栏与提示条 `shrink-0`，标签条以下区域 `flex-1 min-h-0`；消息区在 `DiscussTimeline` 内部滚动，插话框 `shrink-0` 始终完整可见。
- 去掉原来的 `h-[calc(100dvh-320px)] min-h-[420px] max-h-[900px]` 固定高度。
- 窄布局的方案、成果、来源标签不使用 `h-full`，页面由 `main` 正常滚动；宽布局左右两栏等高，各自内部滚动。
- `DiscussComposer` 的 textarea 从 `rows={3}` 改为 `rows={2}`，最小高度从 72px 改为 52px，默认两行。

## G. 宽布局的标签条位置

- `DiscussRoom` 的宽布局改为 `grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)]`：群聊左栏跨两行，右栏第一行只放方案/成果/来源三个标签，第二行放对应面板并在内部滚动。标签条不再横跨左栏。
- 窄布局仍是一条四标签的标签条，群聊/面板在标签下方切换。

## 两份既有测试的 diff 原文

```diff
diff --git a/backend/tests/test_ui_closeout_dialog_scrim.py b/backend/tests/test_ui_closeout_dialog_scrim.py
index 3788971..9118b14 100644
--- a/backend/tests/test_ui_closeout_dialog_scrim.py
+++ b/backend/tests/test_ui_closeout_dialog_scrim.py
@@ -114,7 +114,7 @@ def _dialog_classes(sources):
     return dialogs
 
 
-def assert_dialogs_have_scrim(sources, *, expected_count=14):
+def assert_dialogs_have_scrim(sources, *, expected_count=15):
     dialogs = _dialog_classes(sources)
     assert len(dialogs) == expected_count, (
         f"expected {expected_count} dialog tags, found {len(dialogs)}"
diff --git a/backend/tests/test_ui_polish_page_contracts.py b/backend/tests/test_ui_polish_page_contracts.py
index 08d7625..88f78fe 100644
--- a/backend/tests/test_ui_polish_page_contracts.py
+++ b/backend/tests/test_ui_polish_page_contracts.py
@@ -18,7 +18,7 @@ PAGE = ROOT / "frontend/app/page.tsx"
 GLOBALS = ROOT / "frontend/app/globals.css"
 CHAT_MODEL = ROOT / "frontend/lib/chatModel.ts"
 
-DRAWER_IDS = ("agent", "exchange", "plaza", "settings", "novel", "studio")
+DRAWER_IDS = ("agent", "exchange", "plaza", "settings", "novel", "studio", "discuss")
 
 
 def balanced_block(source, marker, start=0):
@@ -100,9 +100,9 @@ def test_voice_button_props_preserve_recording_logic():
         assert fragment in source
 
 
-def test_page_drawers_append_drawer_panel_exactly_six_times():
+def test_page_drawers_append_drawer_panel_exactly_seven_times():
     source = PAGE.read_text()
-    assert source.count("drawer-panel") == 6
+    assert source.count("drawer-panel") == 7
     for drawer in DRAWER_IDS:
         match = re.search(
             rf'id="{drawer}-drawer"([\s\S]{{0,800}}?)className="([^"]*)"', source
@@ -114,6 +114,7 @@ def test_page_drawers_append_drawer_panel_exactly_six_times():
     assert source.index('id="plaza-drawer"') < source.index('id="settings-drawer"')
     assert source.index('id="settings-drawer"') < source.index('id="novel-drawer"')
     assert source.index('id="novel-drawer"') < source.index('id="studio-drawer"')
+    assert source.index('id="studio-drawer"') < source.index('id="discuss-drawer"')
 
 
 def test_globals_css_smooths_drawer_materials_on_mobile_only():
```

## 新用例与自检表

新用例加入自己的两份测试，共新增 3 条：`test_discuss_table_headers_carry_font_normal`、`test_discuss_dialogs_are_native_and_use_scrim`（`test_discuss_frontend_guards.py`），`test_sidebar_scrollbar_hide_uses_important`（`test_discuss_frontend_navigation.py`）；同时把抽屉计数与拼接断言的修改放在既有导航用例中。讨论群新用例总数从 39 增到 42。

| # | 改坏的实现 | 发现问题的用例 | 结果 |
|---:|---|---|---|
| 1 | `DiscussDocument.tsx` 的表头去掉 `font-normal` | `test_discuss_table_headers_carry_font_normal` | failed（1 failed, 8 passed） |
| 2 | 讨论群部件里加一个手写 `role="dialog"` 弹层（`DiscussShelf` 标题） | `test_discuss_dialogs_are_native_and_use_scrim` | failed（1 failed, 8 passed） |
| 3 | 原生对话框的 `className` 去掉 `scrim-dialog` | `test_discuss_dialogs_are_native_and_use_scrim` | failed（1 failed, 8 passed） |
| 4 | `Sidebar.tsx` 去掉滚动条隐藏类的 `!` | `test_sidebar_scrollbar_hide_uses_important` | failed（1 failed, 8 passed） |
| 5 | `page.tsx` 重新加入 `"drawer" + "-panel"` 拼接 | `test_page_discuss_drawer_gates_iframe_and_matches_studio_shell` | failed（1 failed, 8 passed） |

每条都是断言失败（`failed`），不是 `error` 或超时；运行后都用原文恢复，并复跑 33 条受影响的守卫/导航/既有页面用例通过。


## 验收命令与输出摘要

1. 前端 `cd frontend`，均加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=...`：
   - `npm run lint -- --max-warnings=25`：退出码 0，`✖ 25 problems (0 errors, 25 warnings)`。
   - `npx tsc --noEmit`：退出码 0，无输出。
   - `npm run build`：退出码 0，路由表含 `○ /discuss`、`○ /discuss/new`、`ƒ /discuss/[id]`。
2. 后端指定用例：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py tests/test_studio_frontend_*.py`
   输出 `101 passed, 45 warnings in 14.02s`，0 skip、0 failed。
3. 后端全量：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider`
   输出 `8604 passed, 47 warnings in 448.40s (0:07:28)`：通过数 = 上一轮 8601 + 本轮 3 条新用例，0 failed、0 skip。47 条 warning 都是第三方库的 DeprecationWarning。
4. 两份既有测试的 diff 统计：
   `git diff --stat -- backend/tests/test_ui_polish_page_contracts.py backend/tests/test_ui_closeout_dialog_scrim.py`
   输出：
   ```
    backend/tests/test_ui_closeout_dialog_scrim.py | 2 +-
    backend/tests/test_ui_polish_page_contracts.py | 7 ++++---
    2 files changed, 5 insertions(+), 4 deletions(-)
   ```
   diff 原文见上文「两份既有测试的 diff 原文」。
5. `git status --porcelain --untracked-files=all`：相对本单派出时，新增的本轮变动是 `backend/tests/test_ui_closeout_dialog_scrim.py`、`backend/tests/test_ui_polish_page_contracts.py`、`frontend/app/page.tsx`、`frontend/components/Sidebar.tsx`、`frontend/components/discuss/DiscussDialogs.tsx`、`DiscussDocument.tsx`、`DiscussRoom.tsx`、`DiscussShell.tsx`、`DiscussTimeline.tsx`、`DiscussComposer.tsx`、`test_discuss_frontend_guards.py`、`test_discuss_frontend_navigation.py` 与本报告；其余状态项是上一轮已存在、本单未改动的文件。没有 `.env`、数据库、上传文件、备份、`fiona.config.json`、`package.json` 或 `globals.css` 的变动。

## 没做完或需要人工确认的地方

- E、F、G 是布局与滚动行为，按要求由规格作者在真实浏览器核验；本环境没有真实浏览器。实现思路已写在上面，开发模式 effect 双执行的成立理由见 E。
- B 的焦点返回依赖打开对话框时浏览器把焦点放在触发按钮上（点击按钮的常规行为）；若某些浏览器点击按钮不聚焦，焦点会回到 `body`。打开时聚焦第一个输入框、Esc 只关对话框、提交中不许关，均按规格实现。
- 新增原生 `<dialog>` 只有 `DiscussDialogs.tsx` 一处（追加预算与追加轮数共用 `DialogFrame`），`test_ui_closeout_dialog_scrim.py` 的期望值是 15。
- 其余 A、C、D 已由源码/静态用例和构建覆盖；F 的极矮视口回退整页滚动没有专门写自动化用例，按规格允许回退，当前实现优先保证正常视口下群聊只滚动消息区。
