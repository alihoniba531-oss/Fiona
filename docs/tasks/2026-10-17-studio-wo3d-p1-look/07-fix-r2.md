# WO3d-P1 返修 R2（单个任务，三处小修）

工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
Python 解释器：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
依据：同目录下的 `04-review-r2.md`

## 要修的三处

1. **可 6 修错了**（`backend/studio/casting.py:645` 附近）
   - 问题：start 复核时读的是 `locked_features`，但 `look_inputs` 输出的键是中文「锁定特征」。结果报价时取到的值永远是空，凡是有锁定特征的条目，start 都会返回 409。
   - 改法：报价时把每个条目的 `locked_features` 原值单独存进报价的 payload（键名用英文 `locked_features`），复核时拿它和条目当前的 `spec_json.locked_features` 比较。不要依赖 `look_inputs` 的输出格式。
   - 测试：有锁定特征、且锁定特征未改动的条目，报价后 start 必须成功；锁定特征改动后 start 返回 409。

2. **新发现：两份报价都能 start，会重复扣费**（`casting.py` 里造型的 start 路径）
   - 问题：同一批条目开了两份报价，两份都能确认，于是生成两个造型任务。
   - 改法：start 时，在建任务的同一个事务里再检查一遍。只要本次报价里任一条目已有在途的 casting_look 任务（状态为 queued、submitting、submitted、running），就返回 409「这些条目正在补全造型，请等完成后再报价」。此时报价不能被消耗，保持 open。
   - 测试：两份报价各自都已 open，第一份 start 成功后，第二份 start 返回 409，并且只生成 1 个任务、只有 1 笔预留。

3. **报价框批次文案里的条目数恒为 1**（`frontend/lib/studio-casting.ts:118-123`）
   - 问题：后端 6 个条目拆成 4+2 两批，前端却显示两批各「1 个条目」。
   - 改法：k 按实际条目数显示。先看后端报价明细里有没有条目数，或者 `inputs.items` 的长度。如果后端没有提供，就在 `casting.py` 的报价明细里补一个 `item_count` 字段，前端读这个字段。
   - 测试：在 `backend/tests/test_studio_casting_frontend.py` 里断言 6 个条目显示为「第 1 批（4 个条目）」和「第 2 批（2 个条目）」。

## 允许修改的文件
- `backend/studio/casting.py`
- `frontend/lib/studio-casting.ts`
- `frontend/components/studio/CastingQuoteDialog.tsx`
- `backend/tests/test_studio_casting_api.py`
- `backend/tests/test_studio_casting_frontend.py`

## 规则
- 每条测试都要先在旧代码上跑一次，确认会失败。
- 改完后要跑通：
  - `cd backend && <py> -m pytest -q tests/ -k studio`
  - `cd frontend && npx tsc --noEmit && npm run lint`，要求 0 error
- 写报告 `08-report-r2.md`。
- 不联网，不提交，不要移动 `node_modules`。
