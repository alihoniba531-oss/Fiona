# WO3d-P1 返修 R1 · 块 A（后端）报告

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- Python：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- 范围：只改 `backend/studio/casting.py` 与块 A 测试 `backend/tests/test_studio_casting_api.py`；未改块 B / 块 C 文件。

## 改动文件

| 文件 | 说明 |
|---|---|
| `backend/studio/casting.py` | M1、M3、可 1/2/3/5/6/10 全部实现 |
| `backend/tests/test_studio_casting_api.py` | 更新旧的批大小/币种断言，新增 8 条返修测试 |

## 逐项对应

**M1 报价币种（`casting.py:519`）**
- `_looks_quote_public` 改为取 `items[0]["currency"]`，与 `_style_quote_public` 同口径。
- `test_studio_casting_api.py:1235` `test_looks_quote_currency_follows_provider`：claude 项目报价为 `USD`，切到 qwen 后为 `CNY`。
- 同步修正 `test_looks_quote_gates_author_exclusion_and_batching`（`test_studio_casting_api.py:1045`）里的币种断言。

**M3 批大小改为 4（`casting.py:40`）**
- `LOOK_BATCH_SIZE = 4`；`max_tokens` 维持 `brain_tasks.py` 的 4096。
- 报价明细名称改为「造型说明 第 n 批（k 个条目）」（`casting.py:586`）。
- `test_looks_quote_gates_author_exclusion_and_batching` 断言 12 个条目拆成 `[4, 4, 4]`，名称为第 1–3 批。

**可 1 水位写回（`casting.py:277`）**
- 移除 `look_job_ids`，每个条目在 `spec_json["look_job_created_at"]` 记录已应用任务的 `created_at`。
- 任务按 `created_at` 升序回放，只有 `created_at` 更新的成功任务才能覆盖；等于或更旧直接跳过，已应用任务不再写库。
- 保留 `look_source=="author"` 跳过、孤儿跳过、非本次请求 id 忽略。
- `test_studio_casting_api.py:1256` `test_look_results_use_created_at_watermark`：旧任务创建早、完成晚时新结果仍为最终值；第二次 GET 不再调用写回逻辑；`look_job_ids` 不再产生。

**可 2 执行前回放（`casting.py:748`、`casting.py:809`、`casting.py:845`）**
- `start_sheets`：建任务前在同一事务内调用 `_apply_look_results`。
- `quote_sheets`：改为单一写事务，报价计算前调用 `_apply_look_results`。
- `patch_item` 的 look 分支：读取条目后、合并前调用 `_apply_look_results`，再重新读取条目。
- `test_studio_casting_api.py:1284` `test_look_results_apply_before_quote_and_start`：不经过 GET，报价后库内 look 已更新；报价后新完成的任务在 start 前落库。
- `test_studio_casting_api.py:1308` `test_patch_look_merges_on_top_of_pending_director_result`：PATCH 只改 hair 时保留导演写回的 makeup。

**可 3 look 空值校验（`casting.py:866`、`casting.py:882`）**
- PATCH `look={}` 返回 422「造型说明不能为空」。
- 合并后所有字段都为空时删除 `look` 与 `look_source`，条目可重新交给导演。
- `test_studio_casting_api.py:1324` `test_patch_look_rejects_empty_object_and_clears_blank_result`：`{}` 为 422；`{"hair": ""}` 后 look/source 为 null，且可再次报价。

**可 5 在途条目与 item_ids（`casting.py:190`、`casting.py:201`、`casting.py:528`、`casting.py:658`）**
- casting_look 任务的 `params_json` 记录 `item_ids`（`start_looks` 建任务后同事务更新）。
- `CastingJob` 公共结构仅对 `task=="casting_look"` 输出 `item_ids`。
- 报价前汇总 queued / submitting / submitted / running 造型任务的条目并从本次报价排除；全部被排除时返回 409「这些条目正在补全造型」。
- `test_studio_casting_api.py:1341` `test_looks_quote_skips_inflight_items_and_jobs_expose_item_ids`：任务与库内 params 都有 item_ids；在途条目被 409 排除；混合请求只报剩余条目。

**可 6 start 逐条复核（`casting.py:603`）**
- 执行前复核：条目存在、非孤儿、kind 为 character/prop、`look_source!="author"`、`locked_features` 与报价时一致；任何变化返回 409「请重新报价」。
- `test_studio_casting_api.py:1366` `test_looks_start_revalidates_quote`：锁定特征改动、报价后作者改 look、报价后条目成孤儿三种情况均 409。

**可 10 异常保护（`casting.py:329`）**
- 单个条目结果损坏时记一条 warning 并跳过，其余条目与 `GET /casting` 正常。
- `test_studio_casting_api.py:1393` `test_corrupt_look_result_is_skipped_with_warning`：坏结果不写回、好结果正常写回、出现 warning 日志。

## 测试结果

先写测试并在旧代码上运行，新增/修改用例 9 条失败（符合预期）：

```
9 failed, 1 passed, 21 deselected
```

实现后：

```
tests/test_studio_casting_api.py                 31 passed
tests/test_studio_casting_jobs.py + integration   38 passed
tests/ -k studio                                 1610 passed, 5550 deselected
```

## 未完成项

- 块 A 无未完成项。
- 前端 `npx tsc --noEmit` / `npm run lint` 属于块 C，本次未运行、未改动前端文件。
