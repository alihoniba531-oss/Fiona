# WO3d 返修 R2 公共说明（三块并发：R2-A 后端编排、R2-B 适配器与提示词、R2-C 前端）

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- Python 解释器：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- 依据文件：
  - 复核报告 `docs/tasks/2026-10-16-studio-wo3d-casting/04-review.md`，下文按其中的编号引用：「必须修复 1–5」「可优化 a–m」「存疑 1」。
  - 规格 `02-spec.md`。
- 复核者的复现脚本（只读参考）：`/private/tmp/claude-501/-Users-yangjing-Desktop-----/4cdfbac6-6c36-436b-b93e-8ad8fab63402/scratchpad/wo3d_review/test_studio_review_repro.py`。
- 三块在同一工作区并行：
  - 只许改本块列出的文件。
  - 别的块的文件只读。
  - 不要隐藏、移动 `frontend/node_modules`。
- 每一处修改都要配一条测试。测试先在旧代码上失败、在新代码上通过。不要只改断言去迁就实现。
- 不联网、不读 `.env`、不提交。
- 报告写到 `docs/tasks/2026-10-16-studio-wo3d-casting/08-report-r2-<块>.md`，每项写清：文件:行、改法、对应测试。

## 产品口径（主控已定，三块共同遵守）

- **条目级补充提示词和参考图（必须修复 5）**：
  - 条目卡上保存的 `extra_prompt` / `reference_asset_ids` 是该条目的**常驻默认**，之后每次出图都会带上。
  - 批量栏里临时填的 `extra_prompt` 追加在常驻默认之后，参考图与常驻默认合并去重，只对本批生效。
  - 合并后参考图总数（含派生的已选定版本）不超过 4 张，超出时报价返回 422。
  - 前端条目卡的文案改为「补充提示词（之后每次出图都会带上）」。
- **派生（必须修复 1）**：
  - 报价里只存显式参考图，加上 `derive_from_approved` 标志。
  - 执行时统一合并：已选定版本排在第一位，用 derived 说明，并去重。
  - 报价阶段的张数校验按合并后的实际张数计算。
  - 条目没有已选定版本却勾了派生 → 409。
- **归档（必须修复 2）**：
  - 只允许归档 `role IN ('sheet','audition')` 且 `item_id` 非空的资产。
  - 已选定的定妆版本、已定档的试听都不能归档，返回 409，提示「先换选定」。
- **孤儿（必须修复 4、可优化 d）**：
  - `orphaned` 的判定除了总表条目已归档或已合并，再加上 `bible.breakdown_id` 不等于项目当前的 breakdown_id。
  - 孤儿条目不计入 G1，也不能报价、出图、试听，返回 409。
- **skip / reopen（可优化 e）**：
  - 两者都清空 `approved_asset_id`。
  - 已定档的声线保留，不清。

## 不做（已知、留后续）

- 可优化 l（试听条数上限）。
- 缩略图生成：到 WO5 关键帧镜头墙时统一做。本期前端只加懒加载。
