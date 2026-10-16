# WO3b 返修 R1 复核（R2）

> 范围：只核验 `04-review.md` 列出的 M1 与可优化 2–8 是否按指令落实，以及返修是否引入回归；新发现一律标「可优化」。
> 输入：`05-fix-r1.md`、`03-report.md §7`、当前工作树（`backend/studio/sources.py`、`backend/studio/novel_chat.py`、`frontend/components/studio/{StudioWorkbench,SourceChoices}.tsx`、`frontend/components/novel/NovelFilmDialog.tsx`、`docs/CYBER_AVATAR_PLATFORM.md`、新增 `backend/tests/test_studio_novel_chat_threads.py`、修改的 `test_studio_sources.py / test_studio_sources_frontend.py / test_studio_frontend_shell.py`）全部逐行读过。
> 取证：`cd backend && .venv/bin/python -m pytest -q tests/test_studio_sources.py tests/test_studio_novel_chat_threads.py tests/test_novel_chat.py tests/test_studio_sources_frontend.py tests/test_studio_frontend_shell.py tests/test_studio_sources_readonly_integration.py tests/test_novel_chat_frontend.py tests/test_studio_brain_frontend.py` → **249 passed、0 failed**（本机 node_modules 在位，node 用例实跑）。lint / tsc / 全量以实现方自报与主控沙箱外复跑为准。

## 结论：通过

M1 已按指令落实并超出点名范围（额外线程化了 manifest/章文件读取校验、漂移比较、整书组装、成稿判定与失败清理），可优化 2–8 全部落实且各有测试；未发现回归。返修新增的 `_finish_task` 取消排水逻辑正确，旧有「提交已持久化则不删目录」的保证保留。新发现 3 条，均为低严重度，标可优化。

## 逐项核验

| 项 | 结论 | 证据（file:line） |
|---|---|---|
| **M1-a** `_write_snapshot` 不再在事件循环上执行 | 落实 | `sources.py:463` `asyncio.create_task(asyncio.to_thread(_write_snapshot, …))`，经 `:449-457` `_finish_task` 排水；`test_studio_sources.py::test_heavy_sources_operations_use_to_thread` 记录 `_write_snapshot` 经 `to_thread`；`::test_sources_workers_leave_event_loop_responsive[_write_snapshot]` 在 worker 阻塞期间断言事件循环仍能连续执行 3 个回调 |
| **M1-b** `normalize_text` / `split_text` 线程化 | 落实 | `sources.py:519`（上传/粘贴）、`:356`（交流列表）、`:367`（交流导入）、`:291`（切分）；同上两条测试覆盖 `normalize_text`、`split_text`、`_assemble_text_snapshot` |
| **M1-c** 补充要求：其他整书/大文本同步调用 | 落实 | `_assemble_novel_snapshot`（哈希+清单组装）`:148`；`_validate_text_source` `:290`；`_assemble_text_snapshot` `:292`；`_exchange_artifact` `:330`；`_discard_directory` `:493`；`_read_manifest` `:556,:610`；`_compare_drift` `:574`；`_read_snapshot_chunks` `:611`；`novel_chat._render_read_novel` `novel_chat.py:70`。留在循环上的只剩元数据与既有 async 调用。`test_studio_novel_chat_threads.py:50-72` 用真实线程 id 证明两条入口（`sources.read_novel` / `novel_chat.read_novel`）的渲染在 worker 中执行且返回值逐键相等；`:131-163` 阻塞期间心跳 |
| **M1-d** 取消语义不退化 | 落实 | `_finish_task` `:449-457` 反复 `shield` 直到任务真正结束；写入中被取消→等文件写完→`:465-468` 抛 `CancelledError`→`:491-494` 线程中 `_discard_directory` 并同样排水→不留正式孤儿目录；提交中被取消→`:487-490` `committed=True` 后才抛，不删已提交目录；空项目回滚 `:507` 同样排水。`test_studio_sources.py::test_repeated_cancellation_drains_write_and_cleanup_workers[before_write/after_rename/cleanup]` 三个时点 + 既有 `readonly_integration::test_repeated_cancellation_cannot_remove_a_committed_snapshot` 均通过 |
| **M1-e** 既有回滚/注入测试仍有效 | 成立 | `to_thread(_write_snapshot, …)` 在调用时查模块全局名，`monkeypatch.setattr(sources, '_write_file'/'_write_snapshot'/'_discard_directory', …)` 继续生效；`::test_snapshot_failure_rolls_back_project_and_directory[write/database]`、`::test_snapshot_path_rejects_escape` 原样通过 |
| **O1** 选中整卡高亮 | 落实 | `SourceChoices.tsx:16` `article` 追加 `${selected ? "ring-1 ring-[color:var(--ink)]" : ""}`，与成稿卡片一致；`aria-pressed` 仍在 chip（`:17`）；`test_studio_sources_frontend.py::test_candidate_ssr_flags_eligibility_and_embedded_existing_links` 断言未选中无 `ring-1`、选中时 `<article class="…ring-1 ring-[color:var(--ink)]` 且 `aria-pressed="true"` |
| **O2** 来源项目默认①拆解、空白保持④、手动切换后不被改回 | 落实 | `StudioWorkbench.tsx:34-38` `stageTouched`/`stageInitialized` refs + `selectStage`；`:74-81` 仅首次成功读取项目时初始化，`source_kind` 非空且未 touched 才 `setStage(0)`；鼠标 `onClick`、键盘 `useRovingTabs(…, selectStage)`、`ShotWall.onRefill` 均走 `selectStage` 标记 touched。`test_studio_frontend_shell.py::test_source_project_lands_on_source_stage_once[novel/upload/paste/exchange]`、`::test_project_refresh_preserves_manually_selected_stage[mouse/keyboard]`（含完整刷新 + 5 s 轮询 + 来源元数据变化）、`::test_blank_project_does_not_reinitialize_stage_if_source_appears_on_later_refresh`；原空白项目断言 `tabs[3]` 选中（`:73`）未动 |
| **O3** rename 竞争返回 409 | 落实 | `sources.py:401-406` 捕获 `OSError`，errno ∈ {EEXIST, ENOTEMPTY, EISDIR} → `HTTPException(409, '快照已更新，请重新检查')`，其余原样抛；`finally :414-416` 清理 part 目录；`::test_rename_competitor_returns_409_and_keeps_winner[EEXIST/ENOTEMPTY/EISDIR]` 断言胜者目录内容保留、无残留 part；`::test_existing_snapshot_target_returns_409_without_part` |
| **O4** 目录 fsync | 落实 | `:407-408` rename 后 `_fsync_directory(target.parent)`；`:419-432` 打开目录 fd、fsync、finally close；POSIX 任何 `OSError` 继续抛，仅 `os.name == 'nt'` 且 errno 在不支持列表内忽略；fsync 失败时 `:410-413` 删除本次刚 rename 的目录（`renamed` 守卫保证只删自己的）。`::test_directory_fsync_runs_after_rename`（断言 fsync 时 `snapshot.json` 已在正式目录）、`::test_posix_directory_fsync_failure_removes_owned_target_and_project`、`::test_directory_fsync_ignores_only_windows_unsupported_errors` 5 组 |
| **O5** 文档残留 | 落实 | `docs/CYBER_AVATAR_PLATFORM.md:43` 「共八项」+「成功读小说 `60`（`FIONA_DAILY_NOVEL_READS` / `novel_read`，仅成功读取计数，不扣草莓）」 |
| **O6** `summary` 回退仅限旧工作流 | 落实 | `sources.py:333-339` `_exchange_artifact`：`artifact` 空白且 `not exchange.get('workflow_version')` 才回退 `summary`；归属/对象/状态判定与 404 文案不变。`::test_exchange_import_and_list_summary_only` legacy 分支显式 `workflow_version: None`；`::test_summary_fallback_only_for_legacy_workflows` 覆盖 None/0 回退、2/'draft_review_v1' 不回退、新工作流有正式成稿照常 |
| **O7 / 指令 8** 做成片对话框按钮主次 | 落实 | `SourceChoices.tsx:11-13` `ExistingSourceProjects` 新增 `primary` prop（默认 false，`CreateProjectDialog` 调用点样式不变）；`NovelFilmDialog.tsx:48` 传 `primary`，`:52` 有已有项目时「再建一个」为 `btn min-h-10`，否则「创建项目」保持 `btn btn-primary`。`test_studio_sources_frontend.py::test_film_dialog_existing_eligibility_and_embedded_creation` 精确断言两种 className 与 embed 链接 |
| **指令 9** 报告 | 落实 | `03-report.md §7` 列出改动文件、逐条实现、线程化清单、测试清单与结果；声明非工作室测试固定值零变更 |
| **回归：非工作室测试** | 无改动 | `git diff 532d11d --stat -- backend/tests/` 仍只有 `conftest.py`、`test_studio_brain_frontend.py`、`test_studio_frontend_shell.py`（后者仅新增 3 个用例 + 上轮已核的一处精确断言替换） |
| **回归：未声明文件** | 无改动 | `CreateProjectDialog.tsx`（77 行）、`SourcePanel.tsx`（69 行）与上轮一致；`novel_chat.py` 仅 `import asyncio` 与把渲染体抽成 `_render_read_novel`，早返回路径（整数校验、消歧、来源错误）仍在循环上且不派发线程（`test_studio_novel_chat_threads.py:106-128`） |
| **回归：行为等价** | 成立 | 小说快照：缺章→`_bounded`→组装的顺序与错误文案不变（`:152-173`）；文本快照：kind→50 万字→空文本的校验顺序不变（`:295-301`）；`read_snapshot` 范围校验移入线程但仍 422（`:614-616`）；`source_status` 的 404→`unavailable` 分支不变（`:563-572`）。全部既有用例（含真实库只读集成）通过 |
| **回归：node 测试 skip 守卫** | 成立 | 新增页签用例沿用 `test_studio_frontend_shell.py:19-23` 的 `probe()` 守卫；`test_studio_novel_chat_threads.py` 为纯 Python；实现方自报隐藏 node_modules 后 5 passed / 31 skipped |

## 新发现（均为可优化，不阻塞）

- **N1 默认执行器承载重活**：所有线程化都用 `asyncio.to_thread`（事件循环默认执行器）。仓库另有 `utils.slow_pool.run_slow`，其文档注明默认执行器应留给「chat state and stream reads」。快照写入/大文本解析可达秒级，理论上会与聊天路径的 `to_thread(clear_pending…)` 等短任务争抢默认线程池。与工作室既有 `store.py:318` 的 `to_thread(storage.save_image…)` 惯例一致，作者只读、低频，严重度低。若后续 3c 期拆解引入更多重活，可把 `_write_snapshot`、`normalize_text`、`_assemble_*` 改走 `run_slow`。
- **N2 旧工作流判定口径**：`sources.py:335` 以 `workflow_version` 的真值判断旧工作流，而 `exchange_store.py:288-289` `_uses_workflow` 以 `== DRAFT_REVIEW_WORKFLOW_VERSION` 判断新工作流。当前旧行为 NULL、新行为该常量，两种口径结果一致；若将来出现第二个版本号，建议统一引用 `exchange_store.DRAFT_REVIEW_WORKFLOW_VERSION`。
- **N3 `_finish_task` 的异常覆盖取消**：被排水的任务若本身抛错（如 `_discard_directory` 的 `OSError`），`task.result()` 会以该异常替代外层的 `CancelledError` 传播（`sources.py:457`）。客户端已断开，无业务影响；与返修前 `except` 块直接调用同步清理的行为一致。可在 `_finish_task` 中保留原始取消标志并优先传播，属锦上添花。
