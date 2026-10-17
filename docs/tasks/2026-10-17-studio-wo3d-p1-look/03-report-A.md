# 块 A 报告：后端编排

工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
基线：`6de7873`

## 改动文件

- `backend/studio/casting.py:21`：新增 `LOOK_TASK = "casting_look"`、`MAX_LOOK_ITEMS`、`LOOK_BATCH_SIZE`。
- `backend/studio/casting.py:152`：`CastingItem` 增加 `look` / `look_source`。
- `backend/studio/casting.py:187`：任务列表条目增加 `task` 字段。
- `backend/studio/casting.py:197`：`_JOBS_FILTER` 纳入 `casting_look`，`CastingState.jobs` 可见该导演任务。
- `backend/studio/casting.py:242`：按条目 kind 读取 `LOOK_FIELDS` 的字段名；`_clean_look` 过滤未知字段并按 `LOOK_MAX_CHARS` 截断。
- `backend/studio/casting.py:260`：`_apply_look_results` 幂等回放已成功的 `casting_look` 任务，逐条写回 look。
- `backend/studio/casting.py:312`：`state()` 在同步条目后执行 look 写回。
- `backend/studio/casting.py:499`：`quote_looks`，按 10 条一批报价，排除作者改过的条目。
- `backend/studio/casting.py:557`：`start_looks`，确认报价、预留额度、建导演任务并返回 `CastingState`。
- `backend/studio/casting.py:771`：`patch_item` 支持 `look` 校验、合并与 `look_source="author"`。
- `backend/studio/casting_jobs.py:441`：出图时把 `spec_json["look"]` 传给 `build_sheet_prompt(look=...)`。
- `backend/studio/brain_tasks.py:32`：造型说明软检查（单字段超过 60 字给警告）。
- `backend/studio/brain_tasks.py:166`：登记 `casting_look` 导演任务，使用块 B 的 `CASTING_LOOK_SCHEMA`。
- `backend/routers/studio.py:238`：`CastingItemPatchBody` 增加 `look`。
- `backend/routers/studio.py:261`：新增 `LooksQuoteBody`（1–30 个 item_ids）。
- `backend/routers/studio.py:622`：新增 `POST /studio/projects/{pid}/casting/looks/quote`。
- `backend/routers/studio.py:627`：新增 `POST /studio/projects/{pid}/casting/looks/start`。

## 逐项对应

- **造型字段与来源**：使用块 B 的 `LOOK_FIELDS` / `LOOK_MAX_CHARS`，数据只写入 `studio_items.spec_json["look"]` 与 `spec_json["look_source"]`，未新增数据库列。内部另存 `spec_json["look_job_ids"]`（最多 20 个）用于幂等回放，不对外暴露。
- **`casting_look` 任务登记**：`brain_tasks.TASKS` 使用 `BrainTask("造型说明", "casting_look.md", CASTING_LOOK_SCHEMA, _look_warnings, 4096)`。
- **looks quote 前置条件**：G0、开工确认、风格选定均通过既有 `_require_g0` / `_require_setup` / `_require_style` 校验；孤儿条目、场景条目返回 409；未知条目 404。
- **作者条目排除**：`look_source == "author"` 的条目不进入报价；全部被排除时 409「这些条目的造型说明已由作者修改」。
- **分批报价**：每 10 个条目一次 `look_inputs` / `_quote_item`，对应一条报价明细；`kind="casting_looks"`。
- **start 机制**：只确认一次、15 分钟过期、`check_brain_budget`（单次上限 / 日上限 / Claude 月度额度）、`_insert_job` 预留，均与风格提案一致。
- **写回规则**：只处理请求内的 item_id；忽略结果中的额外 id；跳过 `look_source=="author"`、已成孤儿、条目不存在、kind 不匹配的结果。成功后写 `look_source="director"`。
- **PATCH look**：按条目 kind 校验字段；未知字段、超 200 字、非文本、场景条目均 422；传入字段覆盖、未传字段保留；保存后 `look_source="author"`。
- **出图提示词**：`casting_jobs._run_image` 将 `spec.get("look")` 传给块 B 的 `build_sheet_prompt`，由块 B 负责版式与裁剪。
- **任务列表**：`CastingState.jobs` 现在带 `task`，可识别在途 `casting_look`。

## 测试

测试前已用 `grep -n "def look_inputs" backend/studio/casting_prompts.py` 确认块 B 已落盘。

- `backend/tests/test_studio_casting_api.py:1045`：报价门禁、场景/孤儿 409、作者排除、10 条分批、单次 30 条上限。
- `backend/tests/test_studio_casting_api.py:1093`：报价 → 确认 → 假 brain 结果 → state 写回；作者期间修改、孤儿、额外 id 均按契约处理；任务列表可见 `casting_look`。
- `backend/tests/test_studio_casting_api.py:1153`：PATCH look 的 422 校验、合并规则与人物/道具字段差异。
- `backend/tests/test_studio_casting_jobs.py:266`：出图任务把 look 传给 `_build_sheet_prompt`。
- `backend/tests/test_studio_casting_integration.py:665`：真实块 B 提示词；Seedream 请求 prompt 同时包含「细节栏」和全部 look 字段值。
- `backend/tests/test_studio_casting_integration.py:65` / `:72`：`CastingItem` / `CastingJob` 形状断言同步增加 `look`、`look_source`、`task`。

命令与结果：

```text
cd backend && <venv-python> -m pytest -q tests/test_studio_casting_api.py
23 passed

cd backend && <venv-python> -m pytest -q tests/test_studio_casting_jobs.py
25 passed

cd backend && <venv-python> -m pytest -q tests/test_studio_casting_integration.py
13 passed

cd backend && <venv-python> -m pytest -q tests/ -k studio
1597 passed, 5550 deselected, 32 warnings
```

## 未完成项

- 无。
- 说明：写回采用「任务成功后、下一次读取 `CastingState` 时幂等回放」的实现，既覆盖正常轮询，也覆盖进程重启后的遗留任务；未改动块 A 范围外的 `brain_jobs.py` / `breakdown.py` 完成回调。
