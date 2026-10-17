# WO3d-P2 小返修 R1（两块并发：后端 / 前端加文档）

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- Python 解释器：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- 依据：同目录下的 `04-review.md`（结论为通过，下面几条是从「可优化」里挑出来要修的）
- 每处修改都要配一条测试：先在旧代码上跑，确认失败；改完再跑，确认通过。
- 不联网，不读 `.env`，不提交，不移动 `node_modules`。
- 完成后写报告 `06-report-r1-<后端|前端>.md`。

## 后端块

**只许改这些文件**：`backend/studio/providers/tts_doubao.py`、`backend/studio/casting_jobs.py`，测试 `backend/tests/test_studio_media_tts_doubao.py`、`test_studio_casting_jobs.py`。

1. **error_code 不能原样存上游内容**
   - 上游返回的 `code` 只接受 1–10 位纯数字，生成 `doubao_<数字>`；其他任何值一律记为 `doubao_unknown`。
   - `message` 截断到 200 字，并且继续执行 Key 脱敏。
2. **发送前的错误要记成 rejected**
   - 适用情况：参数校验失败（例如 direction 超长、pitch 越界）、请求构造失败等，即 POST 发出前就抛出的错误。
   - 这类错误必须记成 `rejected` 并释放预留，不能记成 uncertain。
   - uncertain 只留给「请求可能已到达上游」的情况。
   - 测试：POST 次数为 0 时，任务状态是 rejected，并且预留已释放。
3. **uncertain 的提示语统一**：统一使用 `providers/media_errors.py` 或 `tts_cosy.py` 里既有的提示语常量，并删除死代码分支。

## 前端加文档块

**只许改这些文件**：`frontend/components/studio/VoicePanel.tsx`、`frontend/lib/studio-casting.ts`、`docs/ARCHITECTURE.md`，测试 `backend/tests/test_studio_casting_frontend.py`。

1. **费用提示按实际方案计算**
   - 逐个方案按它选的引擎估价：豆包、CosyVoice 按字数乘单价，最低 ¥0.01；edge-tts 免费。然后把所有方案加总。
   - 英文项目手动选了豆包时，不能显示「免费」。
2. **试听任务的失败和 uncertain 要能看到**
   - 在声线区，每个条目显示最近一次失败或 uncertain 的 tts 任务，带上原因。
   - uncertain 的显示「可能已扣费」和「释放」按钮，复用现有的释放接口和文案，写法参照 `CastingItemCard` 里出图任务的 uncertain 处理。
   - rejected 或 failed 的只显示原因，比如「语音 Key 无效」「参数错误」。
3. **定档失败时保留已填内容**：approve 请求失败后，「角色基调」输入框里的内容要保留，同时显示错误提示。
4. **允许修改已定档声线的角色基调**
   - 已定档的声线上加一个「改基调」入口。
   - 修改后用同一个 approve 接口重新提交：`asset_id` 不变，`baseline` 换成新值。提交前先确认后端允许对同一条试听重复 approve；如果不允许，就只在报告里写明，不改后端。
5. **修正 `docs/ARCHITECTURE.md` 里 TTS 额度的描述**：照 `04-review.md` 里写的那条改准确。

## 验证

- `cd backend && <py> -m pytest -q tests/ -k studio`
- `cd frontend && npx tsc --noEmit && npm run lint`，要求 0 error
