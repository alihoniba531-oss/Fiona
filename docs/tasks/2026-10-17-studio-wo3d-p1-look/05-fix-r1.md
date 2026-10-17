# WO3d-P1 返修 R1（三块并发：A 后端、B 提示词、C 前端）

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`。
- Python：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。
- 复核报告：同目录下的 `04-review.md`。下文用 M1–M3 指必须修复项，用「可 1–10」指可优化项。
- 文件范围与 `02-spec.md` §3 相同：
  - 块 B 额外可以改 `backend/studio/prompts/style_proposals.md`。
  - 块 C 额外可以改 `frontend/components/studio/SetupCard.tsx`。
- 每处修改都要配一条测试。测试先在旧代码上确认会失败，再在新代码上通过。
- 不联网、不读 `.env`、不提交、不移动 `node_modules`。
- 报告写到 `06-report-r1-<块>.md`。

## 主控已定口径
- **M3**：每次导演调用最多 **4** 个条目（`casting.py` 的批大小常量从 10 改为 4），`max_tokens` 维持 4096。报价按 4 个一批拆分明细，报价框显示「造型说明 第 n 批（k 个条目）」。
- **写回顺序（可 1）**：放弃「按完成时间回放」的做法，改为**水位**。
  - 每个条目在 `spec_json` 里记 `look_job_created_at`，只应用比它更新（按任务 `created_at`）的成功任务。
  - 不再保留 `look_job_ids` 列表。
  - 已经应用过的任务不得反复写库。
- **造型行位置（可 7）**：改为「标题 → 版式 → 造型 → 外形」。

## 块 A（后端）
- **M1**：造型报价的 `currency` 取报价明细里的币种，写法与 `_style_quote_public` 一致。同步修正 `test_studio_casting_api.py:1087` 的断言，再补一条 claude 计美元、qwen 计人民币的用例。
- **M3**：批大小改为 4。
- **可 1**：按水位写回，见上面的口径。
- **可 2**：以下三处在执行前，都先在同一事务里调一次 `_apply_look_results`：
  - `start_sheets`（建任务之前）
  - `quote_sheets`
  - `patch_item` 的 look 分支
- **可 3**：
  - PATCH 传 `look={}` 时返回 422。
  - 合并后如果所有字段都为空，清除 `look` 和 `look_source`，让该条目能重新交给导演补全。
- **可 5（后端部分）**：
  - casting_look 任务的 `params` 里记下 `item_ids`。
  - `CastingJob` 新增可选字段 `item_ids: string[]`，只有造型任务有。
  - 报价时，如果条目已有在途的造型任务（queued、submitting、submitted、running），从本次报价中排除。全部被排除时返回 409，提示「这些条目正在补全造型」。
- **可 6**：`start` 时逐条复核，复核内容包括：
  - 是否已成孤儿；
  - 是否已被作者修改；
  - 锁定特征是否与报价时一致。

  任何一项变化就返回 409，提示重新报价。写法参照 `_revalidate_sheet_item`。
- **可 10**：`_apply_look_results` 加异常保护。单个任务的结果损坏时，只记一条 warning 并跳过，不能让 `GET /casting` 返回 500。

## 块 B（提示词）
- **可 7**：造型行改放在版式之后、外形之前。裁剪规则不变，补测试。
- **可 8**，修改 `casting_look.md`：
  1. 某项确实没有内容时写「无」，不能留空。
  2. 写明 synopsis 只用来判断时代、身份和处境。
  3. 声明本任务是「造型设计」，允许在原文没写到的地方合理设计，这是对全局「不得编造外形」的例外，但不能与原文外形和锁定特征矛盾。
  4. 禁止写真实品牌、真人姓名，禁止服装或道具上出现文字字样。
- 渲染出图提示词时，值为「无」的字段视为空，直接跳过。
- **可 10（提示词部分）**：`style_proposals.md` 里涉及定妆版式的旧说法，改成「一图两区：三视图加细节栏」。

## 块 C（前端）
- **M2**：
  - 点「编辑」时，快照一份当时的 look 作为 base。保存时只提交与 base 不同的字段。
  - 条目有在途的造型任务时，禁用「编辑」，提示「导演补全中」。
  - 补测试：编辑过程中 props 被更新，保存时不能提交空串。
- **可 4**：
  - 批量栏显示最近一次失败或结果不确定的 casting_look 任务及其原因。
  - 结果不确定的任务提供「释放预留」按钮，复用风格卡的释放接口和文案「可能已扣费」。
- **可 5（前端部分）**：
  - 在途判定改用 `job.item_ids` 是否包含本条目，只在相关的卡片上显示「导演正在补全造型…」。
  - 已勾选的条目里有在途的，不计入补全；勾选超过 30 个时，按钮禁用并提示。
  - 删掉死代码分支。
- **可 10（前端部分）**：
  - `CastingQuoteDialog` 的明细显示「第 n 批（k 个条目）」。
  - `CastingQuoteDialog.tsx:26`、`SetupCard.tsx:57` 里的旧版式文案，改成「一图两区：三视图 + 细节栏」。

## 验证
- `cd backend && <py> -m pytest -q tests/ -k studio` 全部通过。
- 前端：`npx tsc --noEmit` 与 `npm run lint` 都是 0 error。
