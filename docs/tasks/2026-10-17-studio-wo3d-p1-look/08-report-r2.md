# WO3d-P1 返修 R2 报告

工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
依据：`04-review-r2.md`

## 修改内容

### 1. 可 6：锁定特征复核不再依赖 `look_inputs`

- `backend/studio/casting.py`
  - 报价时把每批条目的原始 `locked_features` 以英文键单独写入报价 payload：`locked_features: {item_id: value}`。
  - `start_looks` 复核时直接读取该字段，与条目当前 `spec_json.locked_features` 比较；不再从 `look_inputs` 的 `inputs.items` 中猜字段。
- 回归测试：`test_looks_start_revalidates_locked_features_from_quote_payload`
  - 有锁定特征且未改动：报价后 `start` 返回 200。
  - 报价后改动锁定特征：`start` 返回 409「锁定特征已修改」，报价保持 `open`。

### 2. 新发现：同一批条目的第二份报价不能重复 start

- `backend/studio/casting.py`
  - `start_looks` 在自身 `BEGIN IMMEDIATE` 事务内，确认报价状态后、检查预算和消耗报价前，再次查询本条报价涉及条目的在途 `casting_look` 任务。
  - 在途状态限定为 `queued / submitting / submitted / running`。
  - 任意条目在途时返回 409「这些条目正在补全造型，请等完成后再报价」，不更新报价状态，报价保持 `open`。
- 回归测试：`test_looks_start_rejects_second_open_quote_and_keeps_it_open`
  - 两份报价均先保持 `open`；第一份 start 成功，第二份 start 返回上述 409。
  - 仅生成 1 个造型任务、仅 1 笔预留。
  - 第一份报价为 `confirmed`，第二份仍为 `open`。

### 3. 报价框批次条目数

- `backend/studio/casting.py`
  - 造型报价的公开明细新增 `item_count`，值为该批实际条目数。
  - 报价内部 payload 同步保存 `item_count`。
- `frontend/lib/studio-casting.ts`
  - `CastingQuoteLine` 增加可选 `item_count`。
  - `castingLookBatchCount` 优先读取 `item_count`；缺失时兼容解析后端名称中的「（k 个条目）」，再回退到旧区间/`versions` 逻辑。
- 回归测试：`test_casting_quote_dialog_looks_wording`
  - 用 6 个条目拆成 4+2 的真实载荷形态，断言报价框显示「造型说明 第 1 批（4 个条目）」和「造型说明 第 2 批（2 个条目）」。

## 旧代码失败确认

先在未修改业务代码的旧实现上运行新增/调整的测试：

```text
backend $ ... -m pytest -q tests/test_studio_casting_api.py \
  -k 'revalidates_locked_features or rejects_second_open_quote'
2 failed:
- test_looks_start_revalidates_locked_features_from_quote_payload
  期望 200，旧代码返回 409「阿宁 的锁定特征已修改，请重新报价」
- test_looks_start_rejects_second_open_quote_and_keeps_it_open
  期望第二份 start 返回 409，旧代码返回 200，并生成第二个任务

backend $ ... -m pytest -q tests/test_studio_casting_frontend.py \
  -k 'quote_dialog_looks_wording'
1 failed:
- 断言页面包含「造型说明 第 1 批（4 个条目）」失败，旧实现显示 1 个条目
```

三条回归均先在旧代码上确认失败，再修改实现。

## 修改后验证

```text
cd backend && /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python \
  -m pytest -q tests/ -k studio

1612 passed, 5550 deselected, 32 warnings in 76.63s
```

```text
cd frontend && npx tsc --noEmit && npm run lint

tsc: 通过，无输出
eslint: 0 errors, 25 warnings（均为原有未使用变量/图片提示）
```

## 变更文件

- `backend/studio/casting.py`
- `frontend/lib/studio-casting.ts`
- `backend/tests/test_studio_casting_api.py`
- `backend/tests/test_studio_casting_frontend.py`

未联网、未提交、未移动 `node_modules`。
