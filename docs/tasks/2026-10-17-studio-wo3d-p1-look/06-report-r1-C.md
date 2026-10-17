# WO3d-P1 返修 R1 · 块 C（前端）报告

- 范围：`02-spec.md` §3 中块 C 的五个文件，外加 `frontend/components/studio/SetupCard.tsx`。
- 未改动：`frontend/node_modules`、`globals.css`、依赖与块 A/B 文件。
- 后端契约：按主控口径使用块 A 在途新增的 `CastingJob.item_ids?: string[]`；造型任务的 `item_id` 视为 `null`。

## 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/lib/studio-casting.ts` | `CastingJob.item_ids`；重写 `castingLookInflight`；新增 `castingLookProblem`、`castingLookBatchCount`、`castingLookQuoteLineLabel` |
| `frontend/components/studio/CastingItemCard.tsx` | 编辑时快照 base；只提交与 base 不同的字段；在途时禁用「编辑」并显示「导演补全中」 |
| `frontend/components/studio/CastingItems.tsx` | 失败/不确定的造型任务提示与「释放预留」；在途条目不计入补全；超过 30 条禁用并提示 |
| `frontend/components/studio/CastingQuoteDialog.tsx` | 造型明细显示「第 n 批（k 个条目）」；新版式文案 |
| `frontend/components/studio/SetupCard.tsx` | 新版式文案 |
| `backend/tests/test_studio_casting_frontend.py` | 新增/更新前端探针测试 |

## 逐项对应

### M2 编辑草稿基线

- `CastingItemCard.tsx:24` 新增 `lookBase` 状态。
- `CastingItemCard.tsx:47` `startLookEdit` 在点「编辑」时把当时的 `item.look` 按字段 trim 后快照为 base。
- `CastingItemCard.tsx:54-63` 保存时逐字段比较「草稿 vs base」，只把不同的字段放进 PATCH；`lookChanged` 同样基于 base。
- `CastingItemCard.tsx:85-86` 有在途造型任务（`castingLookInflight`）时「编辑」禁用，并显示「导演补全中」；卡片头部继续显示「导演正在补全造型…」。
- 测试：`test_casting_item_card_look_edit_base_and_inflight_lock`。编辑过程中把 props 换成导演刚写回的结果，只改 hair，断言 PATCH 仅为 `{look:{hair:'银白短发'}}`（旧代码会带 7 个空串）。同时断言在途条目禁用编辑、无关条目不受影响。

### 可 4 失败/不确定任务的出口

- `studio-casting.ts:115` `castingLookProblem` 取最近一次 failed / uncertain / rejected / filtered / cancelled 的 `casting_look` 任务（按 `created_at`）。
- `CastingItems.tsx:80-89` 批量区上方常驻展示该任务的状态与 `error_message`；`uncertain` 时显示「可能已扣费，请先到供应商控制台核对再释放。」与「释放预留」按钮。
- 释放复用 `releaseStudioJob`（与 `StyleCard.tsx:46` 同一接口、同一文案）。
- 测试：`test_casting_items_look_problem_banner_inflight_and_limit`，断言只显示最新一条、包含原因、点「释放预留」发出 `/release` 请求。

### 可 5 在途判定与批量按钮

- `studio-casting.ts:111-114` `castingLookInflight` 改为：brain + 在途状态 + `task === "casting_look"` + `job.item_ids` 包含本条目；删除 `(job.task == null && !!job.item_id)` 死代码分支。
- `CastingItems.tsx:35` `lookTargets` 排除在途条目。
- `CastingItems.tsx:37,109,112` `lookTargets.length > 30` 时按钮禁用并提示「一次最多补全 30 个条目，请减少勾选。」
- 测试：同一测试断言仅选中在途条目时按钮禁用、混选时只提交非在途条目（`['i4']`）、31 条勾选时禁用并提示；`test_casting_looks_request_wrappers_fields_and_labels` 断言 `item_ids` 命中/未命中与生命周期状态。

### 可 10 报价明细与版式文案

- `studio-casting.ts:118-123` `castingLookBatchCount` 兼容后端两种命名：`造型说明 1–4`（按区间算 k）与「第 n 批（k 个条目）」（按 `versions` 兜底）。
- `CastingQuoteDialog.tsx:22` 造型明细显示 `造型说明 第 n 批（k 个条目）`，不再显示「1 项」。
- `CastingQuoteDialog.tsx:26`、`SetupCard.tsx:57` 改为「一图两区：三视图 + 细节栏」。
- 测试：`test_casting_quote_dialog_looks_wording`、`test_setup_card_defaults_confirm_and_reedit`、`test_casting_quote_dialog_ssr_lines_total_and_expiry` 相关断言。

## 测试结果

- 新增测试先在旧代码上跑：4 failed（M2 基线、批量问题出口、报价批次文案、in-flight/限额），随后在新代码上全绿。
- `cd backend && <py> -m pytest -q tests/test_studio_casting_frontend.py`：**30 passed**。
- `cd backend && <py> -m pytest -q tests/ -k studio`：**1610 passed, 5550 deselected**（当前工作树，块 A 的 R1 改动尚未落地时结果）。
- `cd frontend && npx tsc --noEmit`：**0 error**。
- `cd frontend && npm run lint`：**0 error**，25 条既有 warning（均不在本次改动文件内）。

## 未完成项 / 依赖说明

- 块 C 无未完成项。
- 与块 A 的联调依赖：需要块 A 在 `CastingJob` 中返回 `item_ids`，并且造型任务 `item_id` 为 `null`。块 A 落地前，前端不会把旧式 `item_id` 任务误判为在途（这是有意的严格匹配）。
- 报价批次计数对后端命名是兼容的，不阻塞块 A 把批大小改为 4 或调整 quote 行 name。
