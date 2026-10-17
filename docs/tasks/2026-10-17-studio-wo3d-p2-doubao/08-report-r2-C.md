# R2 块 C（前端）报告

## 改动文件

- `frontend/components/studio/VoicePanel.tsx`
- `frontend/lib/studio-casting.ts`
- `backend/tests/test_studio_casting_frontend.py`
- `docs/tasks/2026-10-17-studio-wo3d-p2-doubao/08-report-r2-C.md`（本报告）

未改块 B 文件，未改其他前端文件，未移动或隐藏 `frontend/node_modules`。

## 逐项对应

1. 表演指示提示文字改为两行，文案与任务要求一致。
   - 测试：`test_voice_panel_card_defaults_validation_generate_and_approve` 检查两个独立 `<p>` 的完整文案及顺序。
2. 新增纯函数 `castingSpeechPace(text, duration_s)`：先去掉标点、符号和空白，再按字符数除以时长；空文本或非法/非正时长返回 `null`。
   - 语音列表每条展示 `x.x 字/秒`（保留 1 位小数），低于 3.5 字/秒追加「偏慢」标签，`title` 为「真人正常语速约 4–5 字/秒」。
   - 测试：`test_casting_lib_labels_costs_and_guards` 覆盖中英文、标点/空白、非法时长及保留精度；`test_voice_panel_shows_audition_speech_pace_and_slow_hint` 覆盖正常与偏慢试听的展示及标签。
3. 豆包新建方案的默认语速保持 1.0（界面值与提交值均为 `1`）。
   - 测试：`test_voice_panel_card_defaults_validation_generate_and_approve` 断言 `voice-rate-i1-0` 的值为 `'1'`，并继续覆盖提交时的数值契约。

## 测试结果

新测试先在旧实现上运行，按预期失败：3 failed，分别为缺少第二行提示、缺少「字/秒」展示、`castingSpeechPace is not a function`。

实现后：

- `pytest -q tests/test_studio_casting_frontend.py -k 'voice_panel_card_defaults_validation_generate_and_approve or audition_speech_pace or casting_lib_labels_costs_and_guards'`：3 passed
- `pytest -q tests/ -k studio`：1680 passed，5550 deselected，32 warnings
- `npx tsc --noEmit`：通过
- `npm run lint`：0 error，25 个既有 warning（均位于 `frontend/app/page.tsx`、`frontend/app/plaza/page.tsx`）

## 未完成项

无。
