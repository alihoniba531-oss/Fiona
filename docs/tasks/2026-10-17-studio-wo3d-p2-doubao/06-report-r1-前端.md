# WO3d-P2 小返修 R1 · 前端加文档报告

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- 范围：`05-fix-r1.md` 的【前端加文档】块
- 未联网、未读取 `.env`、未提交、未移动或隐藏 `frontend/node_modules`

## 改动文件

- `frontend/lib/studio-casting.ts`
- `frontend/components/studio/VoicePanel.tsx`
- `docs/ARCHITECTURE.md`
- `backend/tests/test_studio_casting_frontend.py`

## 逐项对应

1. **费用提示按实际方案计算**
   - `castingAuditionCost` / `castingAuditionCostLabel` 改为接收每个方案的引擎列表。
   - 豆包按 `doubao_cny_per_10k_chars`、CosyVoice 按 `cosyvoice_cny_per_10k_chars` 乘字数，各自最低 ¥0.01；edge-tts 为 0。
   - 多个方案的金额相加；英文项目手选豆包后不再显示「免费」。
   - 测试：`test_casting_voice_cost_uses_each_variant_engine`、`test_voice_panel_cost_tracks_selected_engines_and_variants`。

2. **试听任务的失败和 uncertain 可见**
   - `studio-casting.ts` 新增 `castingVoiceProblem`：按条目取最近一次 `tts` 的 `failed` / `rejected` / `uncertain` 任务。
   - `VoicePanel` 在每条声线卡片显示该任务的错误原因；`uncertain` 复用「可能已扣费，请勿直接重试，去控制台核对」文案和「释放」按钮，释放走现有 `releaseStudioJob` 接口。
   - 由于本块只允许改 `VoicePanel.tsx`，没有改 `CastingStage.tsx`；`VoicePanel` 通过现有 `getStudioCasting` 读取任务列表，并在有 tts 任务进行中时每 5 秒刷新。
   - 测试：`test_voice_panel_shows_latest_tts_problem_and_releases_uncertain`。

3. **定档失败时保留已填内容**
   - approve 失败时不再关闭「角色基调」编辑器，输入值和错误提示都保留；成功时才清空弹层。
   - 测试：`test_voice_panel_approve_failure_keeps_baseline`。

4. **允许修改已定档声线的角色基调**
   - 已定档试听增加「改基调」入口，提交按钮显示「保存基调」。
   - 重新提交仍使用原 `asset_id`，只替换 `baseline`。
   - 已确认后端 `studio.casting.approve_voice` 对同一条试听重复 approve 没有拦截：会再次校验资产并覆盖 `voice_asset_id` / `spec_json`，因此无需改后端。
   - 测试：`test_voice_panel_approved_voice_baseline_can_be_edited`。

5. **修正 TTS 额度文档**
   - `docs/ARCHITECTURE.md` 改为：豆包、CosyVoice、edge-tts 各用独立的默认 2 并发信号量，每个引擎各自上限为 2。
   - 测试：`test_architecture_documents_per_engine_tts_limits`。

## 测试结果

先跑旧代码，新增用例确认失败：

- `test_casting_voice_cost_uses_each_variant_engine`：失败，edge-tts 仍按豆包价返回 `约 ¥0.01`。
- `test_voice_panel_cost_tracks_selected_engines_and_variants`：失败，英文项目手选豆包后仍显示「免费」。
- `test_voice_panel_shows_latest_tts_problem_and_releases_uncertain`：失败，旧面板不显示 tts 失败/uncertain。
- `test_voice_panel_approve_failure_keeps_baseline`：失败，旧实现失败后丢失基调输入。
- `test_voice_panel_approved_voice_baseline_can_be_edited`：失败，旧面板没有「改基调」。
- `test_architecture_documents_per_engine_tts_limits`：失败，文档仍是旧的共用配额描述。

修改后：

- `cd backend && <py> -m pytest -q tests/test_studio_casting_frontend.py`：36 passed。
- `cd backend && <py> -m pytest -q tests/ -k studio`：1676 passed, 5550 deselected。
- `cd frontend && npx tsc --noEmit`：0 error。
- `cd frontend && npm run lint`：0 error（25 个既有 warning，均不在本次改动文件）。

## 未完成项

- 无。本块 5 项均已完成并覆盖测试。
- 说明：`CastingStage.tsx` 不在本块允许修改的文件列表内，因此任务列表由 `VoicePanel` 自行读取；这不影响功能，但会增加一次项目 casting 状态读取。
