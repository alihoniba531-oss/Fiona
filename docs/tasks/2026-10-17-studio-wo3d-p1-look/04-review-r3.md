# WO3d P1 复核 R3（独立）
结论：**通过**（三项均已修复，无未修复项）。核验对象为未提交工作区，仓库未改动。
复现脚本：`$TMPDIR/r3/test_studio_r3_repro.py`（5 条全绿）。附带：casting api 与 frontend 两个测试文件 63 passed，`tsc --noEmit` 无输出。

## 1. 锁定特征复核：已修复
- 证据：`casting.py:589` 报价时按 `{item_id: 值}` 写入英文键 `locked_features`；`:653-657` 逐条读取；`:623` 与条目当前 `spec.locked_features` 比较，不再依赖 `look_inputs`。
- 实测：
  - 人物「左耳有痣」、道具「底部刻字 N.7」、无特征条目同批报价，payload 为三者对应值，未改动时 start 返回 200。
  - 报价后改成别的值、清空、从空改为非空，start 都返回 409「锁定特征已修改」，报价保持 open，无新任务。重新报价后 start 返回 200。

## 2. 两份报价防重复扣费：已修复
- 证据：`casting.py:646-650` 在 `BEGIN IMMEDIATE` 事务内（`store.py:300`），先于预算检查与报价消耗，用 `_look_inflight_ids`（`:529-536`，queued/submitting/submitted/running）做交集检查，命中返回 409「这些条目正在补全造型，请等完成后再报价」。
- 实测（顺序）：报价 A、B 同条目，C 与 A 部分重叠。A 的 start 返回 200，B、C 返回 409；A confirmed，B、C 保持 open；全程 1 个任务、1 笔预留。不相交条目的报价仍可 start，没有误杀。
- 实测（并发）：3 份报价同时 start，结果恰为 [200, 409, 409]，1 个任务、1 笔预留。
- 实测（状态）：任务处于 queued、submitting、submitted、running 时，第二份 start 均返回 409。

## 3. 前端批次文案：已修复
- 证据：`casting.py:523,588` 后端返回 `item_count`；`studio-casting.ts:118-127` 优先读 `item_count`，缺失时解析名称「（k 个条目）」；`CastingQuoteDialog.tsx:22` 调用该标签函数。
- 实测：用真实接口返回的 6 条目报价 JSON（`item_count` 为 4 和 2）渲染 `CastingQuoteDialog`，显示「造型说明 第 1 批（4 个条目）」「造型说明 第 2 批（2 个条目）」。去掉 `item_count` 只留后端名称时结果相同。

## 新问题
0 条（未发现会多扣费或丢数据的新问题）。
