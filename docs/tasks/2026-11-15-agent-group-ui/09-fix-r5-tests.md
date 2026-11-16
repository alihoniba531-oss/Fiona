# 门禁返修单（只补用例）：复核返修第 1 轮之后

这是门禁返修，不计入复核返修轮次。**本轮不改实现，只补用例。**

## 一、复核返修第 1 轮的核验结果

实现全部合格，不要再动：

- 范围合规；lint 0 错误 25 警告、类型检查、构建通过；全量 8617 条通过、0 失败、0 跳过。
- 真实浏览器按 `08-fix-r4-review.md` 第四节逐条量过，七条全部合格：

| 判据 | 实测 |
|---|---|
| A 读取游标 | 拦住轮询 → 库里写入引擎消息（308）→ 界面发插话（309）→ 放开：下一次是 `?after=307`，308 出现在插话之前，插话只有一条，随后变成 `?after=309` |
| B 自定义成员的模型 | 下拉初始「DeepSeek Flash」；不改直接提交，请求体 `models.custom1` 是 `deepseek:deepseek-flash`；改选千问再提交是 `dashscope:qwen3.8-max` |
| C 分工 | 方案只读视图里自定义成员显示「分工：…」 |
| E 多列表格 | 10 列：每列 104px，表格 1040px 在 737px 的容器里横向滚动，页面不滚；两三列的表仍与容器等宽、不滚动 |
| F 焦点 | 发送成功、发送失败之后，`document.activeElement` 都是插话框，紧接着打字能输入；失败时文字保留并显示报错 |
| G 新消息 | 离开时在底部，回来离最新一条 0px；离开前往上滚了 300px，回来位置一像素没变并出现「有新消息」，点它滚到最新；期间没有新消息时位置不变、没有按钮 |
| 不回退 | 抽屉群聊 1280×900 页面不滚动、插话框留白 20px；宽布局 1920×1000 两栏 787px 齐平 |

## 二、问题：有 6 处改坏没有用例拦得住

我把本轮的实现逐处改坏，跑 `test_discuss_frontend_*.py`、`test_discuss_ui_api.py` 和两份既有测试。20 处里 14 处被发现，下面 6 处全部通过：

| 编号 | 文件 | 把这段 | 改成这段 | 后果 |
|---|---|---|---|---|
| V2 | `DiscussRoom.tsx` | `const message = await addDiscussNote(id, { text }, request.signal);` | 在这一行后面加一行 `cursorRef.current = advanceDiscussCursor(cursorRef.current, [message]);` | 插话又推动了游标，丢消息的缺陷原样回来 |
| V4 | `DiscussRoom.tsx` | `publishDetail` 里的 `cursorRef.current = advanceDiscussCursor(cursorRef.current, next.messages);` 这一行 | 删掉 | 游标永远是 0，每次轮询都从头读，超过 200 条之后的新消息读不到 |
| V7 | `DiscussCreateForm.tsx` | `defaultDiscussCustomMemberModel(catalog) \|\| catalog.models[0]?.id \|\| ""` | `catalog.models[0]?.id \|\| ""` | 自定义成员的初始模型又变回目录里的第一个（千问） |
| V9 | `DiscussPlanPanel.tsx` | `{discussMemberShowsFocus(member) && (` | `{member.kind === "lens" && !!member.focus && (` | 自定义成员的分工又不显示 |
| V17 | `DiscussTimeline.tsx` | 「回到群聊标签」那个 effect 里的 `const shouldFollow = nearBottomRef.current;` | `const shouldFollow = true;` | 往上翻着看时也被拉到最新 |
| V18 | `DiscussTimeline.tsx` | 同一行 | `const shouldFollow = false;` | 停在底部离开的，回来也不跟随 |

原因：纯函数本身都测了，但「部件有没有真的用上它、有没有在不该用的地方用」没有钉住；G 的守卫只查了几个子串出现过，没有钉住「跟随还是提示」取决于离开前是否在底部。

## 三、要求

1. 只改 `backend/tests/test_discuss_frontend_guards.py`，再写报告 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r5.md`。其余文件一律不动，包括 `frontend/` 下的任何文件。如果你认为必须改实现才能测，停下来说明，不要改。
2. 补强后，上表 6 处改坏的每一处都必须让至少一条用例**断言失败**（`failed`，不是 `error`）；本轮之前已经能发现的改坏继续能发现。
3. 断言落在具体的函数或标签上，先断言找到了目标，再断言内容。可以参考的钉法（你也可以用别的）：
   - V2、V4：`DiscussRoom.tsx` 里给 `cursorRef.current` 赋值的地方恰好一处，就在 `publishDetail` 里，参数是服务器读回的 `next.messages`；`sendNote` 所在的那段代码里没有对游标的赋值。
   - V7：`DiscussCreateForm.tsx` 里自定义成员的初始模型来自 `defaultDiscussCustomMemberModel(catalog)`。
   - V9：`DiscussPlanPanel.tsx` 里「分工：」那一段的条件是 `discussMemberShowsFocus(member)`，文件里不再出现 `member.kind === "lens" &&` 这种手写条件。
   - V17、V18：`DiscussTimeline.tsx` 里读取 `pendingWhileHiddenRef` 的那个 effect 中，跟随与否取自 `nearBottomRef.current`。
4. 自检：把上表 6 处逐一改坏、跑用例、还原，每处写明是哪条用例失败、输出摘要。还原用你读到的原文写回，不用 `git stash`、`git checkout`。自检用的临时脚本放在仓库外的临时目录，用完删掉。
5. 不提交 git。你实测到的事实优先于本单的断言，不符就停下来说明。任何情况下不回滚已完成的工作。

## 四、验收

命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. 在 `backend/`：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py` 全部通过、0 跳过。
2. 在 `backend/`：全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`，0 失败、0 跳过，通过数 = 8617 + 本轮净增的用例数。唯一的失败如果是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，单独重跑并贴出两次输出，不要为它改文件。
3. `git status --porcelain --untracked-files=all`：相对本单派出时，变动只有 `backend/tests/test_discuss_frontend_guards.py` 与新报告。
4. `git diff --stat -- frontend/`：与本单派出时相同（本轮没有改前端）。

报告不写本机绝对路径：补了哪些用例、各自钉住什么；6 处自检表；验收四条的命令与输出摘要。
