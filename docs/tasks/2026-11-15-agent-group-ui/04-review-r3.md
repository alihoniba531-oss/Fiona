# 讨论群第二期（界面）独立复核 · 第 3 轮

本轮只核验第 2 轮的 3 条必须修复项（都在守卫用例里），以及门禁记录的 6 处已知缺口（V2、V4、V7、V9、V17、V18）是否补上。依据是 `docs/tasks/2026-11-15-agent-group-ui/09-fix-r5-tests.md`、`10-fix-r6-tests.md`，以及用例增量 `.cache/review/tests-delta-round3.diff`（对照 `.cache/review/prev/` 里第 2 轮的两份测试）。实现没有变化；实现方报告只当线索。

## 1. 结论

**通过。**

- 第 2 轮的 3 条必须修复项都已补上。我把第 2 轮存活的 7 处改坏（R02、R03、R13、R14、R15、R18、R19）照原样重做，全部以断言失败变红，没有 `error`。
- 已知的 6 处缺口也都补上，同样全部以断言失败变红。
- 增量里的新断言都绑在具体的函数体、effect、标签或赋值语句上，并且先断言找到了目标；没有恒真的断言，也没有扫描到空集也通过的断言。
- 剩下的问题是：有三种写法不同的改坏仍能通过，另有几处断言对排版钉得偏死。都列在可优化，不影响结论。

机械检查：派单给的 pytest 命令 `115 passed`（第 2 轮 114，多出的 1 条是 `test_discuss_custom_helpers_are_used_in_components`），0 跳过。游标用例删掉了两个重复情形，其余断言不变。

## 2. 三条必须修复项逐条核验

| 第 2 轮必须修复 | 本轮的钉法（`backend/tests/test_discuss_frontend_guards.py`） | 核验 |
|---|---|---|
| 1. E：表格最小宽度的单位与列数 | 在 `DiscussDocument.tsx` 唯一的 `<table>` 标签上，断言恰好含 `` style={{ minWidth: `${discussTableMinWidth(block.header.length)}em` }} ``（`test_discuss_tables_have_column_min_width`） | R13（`em` 改 `px`）、R14（`header.length` 改 `rows.length`）都以断言失败变红 |
| 2. F：失败后也回焦点 | 用 `brace_block` 取出 `submit` 的函数体，再取出其中的 `try { … }` 与 `finally { … }`；断言回焦点在 `finally` 里、不在 `try` 里（`test_discuss_composer_keeps_focus_while_sending`） | R15（挪到 `setText("")` 之后）变红；我另做的 Q5（挪到 `try` 块末尾）也变红 |
| 3. G：处理完清掉标记 | 截出以 `if (!active \|\| firstViewRef.current \|\| !pendingWhileHiddenRef.current) return;` 开头、到下一个 `}, [active]);` 为止的那个 effect，断言其中有 `pendingWhileHiddenRef.current = false;`，且跟随与否取 `nearBottomRef.current`；不可见分支的置位语句带 `!firstViewRef.current`（`test_discuss_timeline_tracks_messages_while_hidden`） | R19（删掉清标记）、R18（去掉 `!firstViewRef.current`）都变红 |

一并钉住的：

- 外链（R02、R03）：两个文件里各恰好一条 `const href` 赋值，且这一行里 `source.url` 只出现一次（只作为 `safeExternalUrl` 的参数）。两种带回落的写法都变红。
- 已知 6 处：
  - V2、V4：取出 `publishDetail` 与 `sendNote` 的函数体，断言游标只在前者里用 `next.messages` 推进，后者里不出现 `cursorRef`；
  - V7：在 `handleTeamChange` 里断言用了 `defaultDiscussCustomMemberModel(catalog)`；
  - V9：在 `renderMember` 里断言用了 `discussMemberShowsFocus(member)`，并且没有手写的 `member.kind === "lens" &&`；
  - V17、V18：在上面那个 effect 里钉住 `const shouldFollow = nearBottomRef.current;`。
  - 六处全部变红。

## 3. 必须修复项

无。

## 4. 可优化项（5 项）

1. **「整个 Room 只能有一处推进游标」只查了一种写法。** `room.count("cursorRef.current = advanceDiscussCursor") == 1` 只数这一种文字，所以：
   - Q1：在 `refreshDetail` 里加一行 `cursorRef.current = Math.max(cursorRef.current, ...(detailRef.current?.messages ?? []).map(item => item.id));`，又按本地最大 ID 续读。这是 A 原来的缺陷换了一种写法，用例照样通过。
   - Q2：给 `publishDetail` 里那一行加上条件 `if (mode === "replace")`，轮询从此不推进游标，后果与 V4 相同。用例同样通过。

   建议：断言整个文件里匹配 `cursorRef\.current\s*=(?!=)` 的地方恰好一处；并且在 `publishDetail` 的函数体里，这条语句独占一行、前面没有条件（例如按行匹配 `^\s*cursorRef\.current = advanceDiscussCursor\(cursorRef\.current, next\.messages\);$`）。
2. **V7 的钉法只要求「调用过」辅助函数。** 把回落顺序倒过来写成 `catalog.models[0]?.id || defaultDiscussCustomMemberModel(catalog) || ""`（Q4），初始模型又变回千问，用例照样通过。建议断言 `customDefault` 那一句以 `defaultDiscussCustomMemberModel(catalog)` 开头。
3. **有几处断言对排版钉得偏死。** 下面四种行为完全等价的改写都会让用例变红。它们不会放过缺陷，只会误报；如果以后引入自动格式化，或有人顺手重排，会白白卡住：
   - E1：`style={{minWidth: …}}` 去掉花括号内的空格；
   - E2：把 `if (arrived && !firstViewRef.current) pendingWhileHiddenRef.current = true;` 改成带花括号的两行；
   - E3：调换 effect 开头 `return` 条件的顺序（这一行同时被用作截取 effect 的定位串）；
   - E4：把 `const href = source ? … : null;` 断成三行。

   建议对表格宽度、置位语句与 `href` 赋值改用容忍空白的正则；effect 改用 `pendingWhileHiddenRef.current = false` 等语句所在的 `useEffect(() => { … }, [active])` 块来定位，不依赖整行字面。
4. **两处截取在找不到终点时会得到 `error`，不是 `failed`。** `renderMember` 的截取用 `panel.index("\n  return (", start)`，effect 的截取用 `timeline.index("}, [active]);", effect_start)`；终点串一变，`str.index` 会抛 `ValueError`。返修单要求改坏时是断言失败；建议先 `assert 终点串 in 源码[起点:]`，再取下标。
5. **用例增量文件里有本机绝对路径（与本轮用例无关，涉及隐私）。** `.cache/review/tests-delta-round3.diff` 的两处文件头写着复核副本所在的本机临时目录，路径里含有本机账号名。如果 `.cache/review/` 会随任务材料提交进公开仓库，这个文件应先去掉文件头里的路径（例如用 `diff -u --label` 改成仓库相对路径），或不提交。

## 5. 变异与结果

做法同前两轮：临时脚本放在仓库外，逐处做唯一匹配的字符串替换，跑 `test_discuss_frontend_logic.py`、`test_discuss_frontend_guards.py`、`test_discuss_frontend_navigation.py`、`test_ui_polish_page_contracts.py`、`test_ui_closeout_dialog_scrim.py`、`test_studio_frontend_navigation.py`（共 77 条），再用原始字节写回。结束后对 `frontend/components/discuss/` 下全部部件做 SHA-256 比对，与改前一致；临时脚本已删除。「改坏」应当变红；「等价改写」行为不变，变红说明钉得过死。

| 编号 | 类型 | 文件 | 改法 | 结果 | 变红的用例 |
|---|---|---|---|---|---|
| R02 | 改坏 | `DiscussDocument.tsx` | `safeExternalUrl(source.url) ?? source.url` | 变红（failed） | `test_discuss_external_links_use_safe_external_url` |
| R03 | 改坏 | `DiscussSourcesPanel.tsx` | `safeExternalUrl(source.url) \|\| source.url` | 变红（failed） | 同上 |
| R13 | 改坏 | `DiscussDocument.tsx` | `em` 改 `px` | 变红（failed） | `test_discuss_tables_have_column_min_width` |
| R14 | 改坏 | `DiscussDocument.tsx` | 列数改用 `block.rows.length` | 变红（failed） | 同上 |
| R15 | 改坏 | `DiscussComposer.tsx` | 回焦点挪到 `setText("")` 之后 | 变红（failed） | `test_discuss_composer_keeps_focus_while_sending` |
| R18 | 改坏 | `DiscussTimeline.tsx` | 置位时去掉 `!firstViewRef.current` | 变红（failed） | `test_discuss_timeline_tracks_messages_while_hidden` |
| R19 | 改坏 | `DiscussTimeline.tsx` | 删掉清标记 | 变红（failed） | 同上 |
| V2 | 改坏 | `DiscussRoom.tsx` | 插话后推进游标 | 变红（failed） | `test_discuss_room_reads_use_server_cursor` |
| V4 | 改坏 | `DiscussRoom.tsx` | 删掉 `publishDetail` 里推进游标那一行 | 变红（failed） | 同上 |
| V7 | 改坏 | `DiscussCreateForm.tsx` | 初始模型改回 `catalog.models[0]` | 变红（failed） | `test_discuss_custom_helpers_are_used_in_components` |
| V9 | 改坏 | `DiscussPlanPanel.tsx` | 分工条件改回只认 `lens` | 变红（failed） | 同上 |
| V17 | 改坏 | `DiscussTimeline.tsx` | 回来时总是跟随 | 变红（failed） | `test_discuss_timeline_tracks_messages_while_hidden` |
| V18 | 改坏 | `DiscussTimeline.tsx` | 回来时从不跟随 | 变红（failed） | 同上 |
| Q1 | 改坏 | `DiscussRoom.tsx` | `refreshDetail` 里另行按本地最大 ID 赋值游标 | **存活** | 无（可优化 1） |
| Q2 | 改坏 | `DiscussRoom.tsx` | 推进游标加条件 `if (mode === "replace")` | **存活** | 无（可优化 1） |
| Q3 | 改坏 | `DiscussRoom.tsx` | 推进游标时把本地消息也算进去 | 存活 | 无。实际影响极小：下一次读回的列表本来就包含插话，只有单次读回被 200 条截断时才可能越过消息，不另列 |
| Q4 | 改坏 | `DiscussCreateForm.tsx` | 回落顺序倒过来（目录第一个模型优先） | **存活** | 无（可优化 2） |
| Q5 | 改坏 | `DiscussComposer.tsx` | 回焦点挪到 `try` 块末尾 | 变红（failed） | `test_discuss_composer_keeps_focus_while_sending` |
| E1 | 等价改写 | `DiscussDocument.tsx` | `style={{minWidth: …}}` 去掉空格 | 变红（failed） | `test_discuss_tables_have_column_min_width`（可优化 3） |
| E2 | 等价改写 | `DiscussTimeline.tsx` | 置位语句改成带花括号的两行 | 变红（failed） | `test_discuss_timeline_tracks_messages_while_hidden`（可优化 3） |
| E3 | 等价改写 | `DiscussTimeline.tsx` | 调换 `return` 条件的顺序 | 变红（failed） | 同上（可优化 3） |
| E4 | 等价改写 | `DiscussDocument.tsx` | `const href` 的三元表达式断成三行 | 变红（failed） | `test_discuss_external_links_use_safe_external_url`（可优化 3） |

小结：
- 应当补上的 13 处（第 2 轮存活的 7 处，加上已知 6 处）全部以断言失败变红。
- 自选的 5 处改坏里，Q5 变红；Q1、Q2、Q4 存活，列为可优化 1、2；Q3 实际无害。
- 4 处等价改写全部误报，列为可优化 3。
- 第 2 轮列为可优化的 R07、R17 本轮不要求，没有重做。
