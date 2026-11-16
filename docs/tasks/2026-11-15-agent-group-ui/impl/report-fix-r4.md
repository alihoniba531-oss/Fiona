# 复核返修报告 第 1 轮：讨论群第二期（界面）

依据 `docs/tasks/2026-11-15-agent-group-ui/04-review.md`、规格 `02-spec.md` 的「v1.3 修订」与复核后的浏览器补测。返修 1–3 已合格的行为未回退；`04-review.md` 第 4 节的其余可优化项未做。

## A. 读取游标

**做了什么**

- `frontend/lib/discussLogic.ts` 新增纯函数 `advanceDiscussCursor(cursor, messages)`：只接受服务器读回的消息，返回旧游标与本批最大 `id` 的较大值；空列表或更小的 `id` 不改变游标。
- `frontend/components/discuss/DiscussRoom.tsx`：
  - 新增 `cursorRef`，只由 `publishDetail` 在合并服务器返回的消息时推进；
  - `poll`、操作后的 `refreshDetail`、`reloadPlan` 的 `getDiscussGroup(id, after)` 全部改用 `cursorRef.current`；
  - 第一次读取仍从 `after=0` 开始、按页续读；`sendNote` 把插话并进本地消息，但**不**推进游标。
- 插话在下一轮读取时会随更早的引擎消息一起回来；`mergeDiscussMessages` 按 id 去重，服务器版本覆盖本地版本，界面不会出现两条。

**为什么**：插话的 id 可能大于前端尚未读到的引擎消息。只要游标只跟服务器读取走，插话就不会让 `after` 越过中间的消息。

**用例**：`test_advance_cursor_only_moves_on_server_reads`（游标 1 + 本地插话场景仍为 1；服务器返回 2、3 后为 3；空列表和更小 id 不改变）；`test_discuss_room_reads_use_server_cursor`（Room 中三处带 after 的读取都用 `cursorRef`，且不存在按本地最大 id 取 after）。

## B. 自定义成员的模型

**做了什么**

- `frontend/lib/discussLogic.ts` 新增 `defaultDiscussCustomMemberModel(catalog)`：从 `catalog.roles` 里第一个 `kind === "lens"` 的成员取 `catalog.defaults[role.id]`。
- `frontend/components/discuss/DiscussCreateForm.tsx` 的「添加自定义成员」初始化改用这个函数；目录真实形状下得到 `deepseek:deepseek-flash`，不再回落到 `models[0]` 的千问。
- `buildDiscussCreateBody` 对自定义成员**总是**写入 `models.customN`，不再只在「与默认不同」时才带；界面显示的模型与实际请求一致。
- `frontend/lib/discuss.ts` 中 `DiscussCustomMemberDraft` 的注释同步改正。

**用例**：`test_custom_member_default_model_uses_lens_default`（用后端 `catalog()` 的真实形状断言 DeepSeek Flash）；`test_build_create_body_members_models_and_identities` 更新为断言 `custom1`、`custom2` 始终出现在 `models`。

## C. 自定义调研成员的分工

- `frontend/lib/discussLogic.ts` 新增 `discussMemberShowsFocus(member)`：`kind` 为 `lens` 或 `custom` 且 `focus` 去掉空白后非空时为真。
- `DiscussPlanPanel.tsx` 只读视图改用该函数，自定义调研成员也显示「分工：…」。
- **用例**：`test_member_focus_visibility_covers_lens_and_custom` 覆盖 lens/custom 非空、空字符串、纯空白、core、avatar。

## D. 字重守卫

- `test_discuss_frontend_guards.py` 的正则改为 `<(?:b|strong)\b` 与 `font-weight`，`font-normal` 仍允许。
- 用例先对含 `<strong className="x">`、`<b className="x">`、`[font-weight:600]`、`style={{ fontWeight: 600 }}` 的样例文本断言正则能命中，再扫描真实文件。

## E. 列多的表格

- `frontend/lib/discussLogic.ts` 新增 `discussTableMinWidth(columnCount)`：每列 8em，至少 1 列。
- `DiscussDocument.tsx` 的表格用 `style={{ minWidth: ... }}` 按列数给最小宽度；外层仍是 `overflow-x-auto`。
- 两三列表格在 720px 容器里仍由 `w-full` 撑满、不滚动；十列表格按列数获得更宽的表格，在容器里横向滚动，页面不被撑宽。表格仍是 `table-fixed`，每列等宽。
- **用例**：`test_table_min_width_is_eight_em_per_column` 覆盖 0/1/2/3/10 列；`test_discuss_tables_have_column_min_width` 定位唯一 `<table>`，断言有 `minWidth` 且按列数计算。

## F. 发送插话后的焦点

- `DiscussComposer.tsx` 的 textarea 从 `disabled={sending || busy}` 改为 `readOnly={sending || busy}`，并保留 `read-only:opacity-60`；新增 `textareaRef`，无论成功或失败都在 `finally` 里 `focus()` 回插话框。发送中仍由 `sendingRef` 和按钮禁用防止重复提交。
- **用例**：`test_discuss_composer_keeps_focus_while_sending` 定位 `data-discuss-composer` 的标签，断言 `readOnly={sending || busy}`、没有 `disabled` 属性、带 `ref={textareaRef}`，并断言源码调用了 `textareaRef.current?.focus()`。

## G. 不在群聊标签时到达的新消息

- `DiscussTimeline.tsx` 新增 `pendingWhileHiddenRef`：`active` 为假时收到新消息（且不是第一次显示）只置位，不滚动；回到群聊时用同一个 ref 判断。
- 回来看 `nearBottomRef`：离开前距底不超过 80px 的滚到最新；否则不滚、显示「有新消息」。没有新消息时不动。
- v1.1 第 4 条的第一次显示逻辑保留：第一次看到群聊仍用 rAF 滚到最新；开发模式 effect 双执行仍成立。`DiscussRoom.tsx` 的 `DiscussTimeline` 类名与 `aria-label="群聊"`、`ref={viewportRef}` 等返修 3 钉住的标记未改。
- **用例**：`test_discuss_timeline_tracks_messages_while_hidden` 按 `DiscussTimeline` 函数体断言隐藏分支置位、回来读取，并保留 `setHasNew(true)`。

## M16：外链必须过 `safeExternalUrl`

- 新增 `test_discuss_external_links_use_safe_external_url`：分别扫 `DiscussDocument.tsx` 与 `DiscussSourcesPanel.tsx` 的 `target="_blank"` 标签，要求 `href={href}`、源码存在 `safeExternalUrl(source.url)`，且不允许 `href={source.url}`。
- 把编号链接改成直接用 `source.url`、或来源列表绕过 `safeExternalUrl`，都会失败。

## 文档

- `README.md`：「讨论群界面（第二期）」最后一句话改为实际行为：「访问检查通过才会出现书签；直接打开独立页时，检查不通过会看到「讨论群尚未开放」或「你的账号暂未开通讨论群」。」只改这一句。
- `docs/tasks/2026-11-15-agent-group-ui/impl/report.md`：开头加一行说明，`"drawer" + "-panel"` 和 `role="dialog"` 手写弹层已被返修 1 取代，指向 `impl/report-fix-r1.md`；正文未改。

## 改了哪些文件

- `frontend/lib/discussLogic.ts`
- `frontend/lib/discuss.ts`
- `frontend/components/discuss/DiscussRoom.tsx`
- `frontend/components/discuss/DiscussCreateForm.tsx`
- `frontend/components/discuss/DiscussPlanPanel.tsx`
- `frontend/components/discuss/DiscussDocument.tsx`
- `frontend/components/discuss/DiscussComposer.tsx`
- `frontend/components/discuss/DiscussTimeline.tsx`
- `backend/tests/test_discuss_frontend_logic.py`
- `backend/tests/test_discuss_frontend_guards.py`
- `README.md`（一句）
- `docs/tasks/2026-11-15-agent-group-ui/impl/report.md`（开头一行）
- `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r4.md`

`frontend/components/discuss/DiscussSourcesPanel.tsx` 未改实现，只被 M16 守卫覆盖；`test_discuss_frontend_navigation.py` 本轮未改。未改 `frontend/app/`、Sidebar、globals.css、两份既有测试、后端代码、规格、各张返修单或 `04-review.md`。

## 新用例与自检表

新用例共 9 条净增（46→55）：逻辑 4 条、守卫 5 条。自检 12 次，全部得到 `failed`（不是 `error` 或超时），恢复后复跑 55 条新用例通过。

| 编号 | 改坏的实现 | 发现问题的用例 | 结果 |
|---|---|---|---|
| A1 | `advanceDiscussCursor` 永远不推进游标 | `test_advance_cursor_only_moves_on_server_reads` | failed |
| A2 | `DiscussRoom` 的三处 after 改回 `0` | `test_discuss_room_reads_use_server_cursor` | failed |
| B1 | 自定义成员默认值跳过 lens 默认值 | `test_custom_member_default_model_uses_lens_default` | failed |
| B2 | 自定义成员模型改回「只在变化时才带」 | `test_build_create_body_members_models_and_identities` | failed |
| C | `discussMemberShowsFocus` 排除 custom | `test_member_focus_visibility_covers_lens_and_custom` | failed |
| D1 | 部件里加 `<strong className="…">` | `test_discuss_frontend_has_no_bold_font_weight` | failed |
| D2 | 部件里加 `[font-weight:600]` | 同上 | failed |
| E | 去掉表格的 `minWidth` | `test_discuss_tables_have_column_min_width` | failed |
| F | textarea 改回 `disabled` | `test_discuss_composer_keeps_focus_while_sending` | failed |
| G | 隐藏分支不再置 `pendingWhileHiddenRef` | `test_discuss_timeline_tracks_messages_while_hidden` | failed |
| M16a | `DiscussDocument` 的编号链接直接用 `source.url` | `test_discuss_external_links_use_safe_external_url` | failed |
| M16b | `DiscussSourcesPanel` 的来源链接直接用 `source.url` | 同上 | failed |

## 验收命令与输出摘要

1. 前端 `cd frontend`，均加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=...`：
   - `npm run lint -- --max-warnings=25`：退出码 0，`✖ 25 problems (0 errors, 25 warnings)`。
   - `npx tsc --noEmit`：退出码 0，无输出。
   - `npm run build`：退出码 0，路由表含 `○ /discuss`、`○ /discuss/new`、`ƒ /discuss/[id]`。
2. 后端指定用例：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py tests/test_studio_frontend_*.py`
   输出 `114 passed, 45 warnings in 13.30s`，0 skip、0 failed。
3. 后端全量：
   `cd backend && NO_PROXY=... no_proxy=... .venv/bin/python -m pytest -q -p no:cacheprovider`
   输出 `8617 passed, 47 warnings in 427.83s (0:07:07)`：通过数 = 上一轮 8608 + 本轮净增 9 条，0 failed、0 skip。47 条 warning 都是第三方库的 DeprecationWarning。
4. `git diff --stat -- backend/tests/test_ui_polish_page_contracts.py backend/tests/test_ui_closeout_dialog_scrim.py`：
   ```
    backend/tests/test_ui_closeout_dialog_scrim.py | 2 +-
    backend/tests/test_ui_polish_page_contracts.py | 7 ++++---
    2 files changed, 5 insertions(+), 4 deletions(-)
   ```
   与本单派出时相同。
5. `git status --porcelain --untracked-files=all`：本轮新增变动只有上面「改了哪些文件」列出的允许文件；其余状态项是前几轮已存在的文件。任务目录里的 `04-review.md`、`08-fix-r4-review.md` 是规格作者放置的复核与返修文档，本轮没有改。

## 没做完或需要人工确认的地方

- 判据 1–6 的最终浏览器行为由规格作者按第四节核验；本环境没有浏览器。A 的游标、B 的默认值、C 的分工、D 的字重、E 的列宽、F 的焦点、G 的滚动都已在纯函数/静态守卫层面钉住。
- E 采用每列 8em 的表格最小宽度；表格字号是 `text-fs-13`，8em 约 104px，满足每列不小于 100px。实际表格是否只在列多时横向滚动，仍需浏览器确认。
- F 用 `readOnly` 保留焦点；发送中不能编辑、按钮仍禁用，`sendingRef` 继续防止重复提交。
- 全量里如果唯一失败仍是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，按返修单要求单独重跑并贴出两次输出，未为它改文件。
