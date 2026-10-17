# 块 C 报告：前端与文档

## 结论

已完成 §3.4 与 §4 中块 C 的前端、测试和文档改动。只修改了块 C 允许的文件；未改动 P1 的后端、前端组件或提示词文件，未隐藏或移动 `frontend/node_modules`。

## 改动文件

- `frontend/lib/studio-casting.ts`
- `frontend/components/studio/VoicePanel.tsx`
- `backend/tests/test_studio_casting_frontend.py`
- `CLAUDE.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `backend/.env.example`

## 逐项对应

- `CastingVoiceEngine` 增加 `"doubao"`；`castingVoiceEngineLabel("doubao")` 返回「豆包语音 2.0」。
- `CastingAuditionVariant` 增加可选 `direction`；`CastingVoiceSpec` 增加 `direction`、`baseline`（均为 `string | null`）。
- `CastingPrices` 增加 `doubao_cny_per_10k_chars`，试听费用按豆包单价计算。
- `castingVoiceSpecLabel` 在有指示时追加「指示：…」。
- `VoicePanel` 中文项目新方案默认豆包语音 2.0，引擎下拉顺序为豆包语音 2.0（推荐）、CosyVoice、edge-tts。
- 豆包方案音高改为 `-12` 到 `12` 的整数步进输入，默认 `0`；语速仍为 `0.5–2.0`。
- 豆包方案显示「表演指示」多行输入框，最多 200 字、带计数和指定占位文字，并显示去除 AI 味的提示小字。
- 非豆包引擎隐藏表演指示输入框，提交时也不向非豆包方案传 `direction`。
- 试听列表显示该条试听使用的表演指示。
- 「选定这条」先弹出角色基调输入框，默认填入该条试听的指示；确认后以 `{ asset_id, baseline }` 调用 approve。
- 已定档声线显示角色基调。
- 音色下拉显示 label，并附上 note 的前 12 个字。
- 文档补充 `VOLC_SPEECH_API_KEY`、`VOLC_SPEECH_RESOURCE_ID`、`FIONA_STUDIO_PRICE_DOUBAO_TTS_CNY_PER_10K_CHARS`，以及火山引擎控制台开通「语音合成 2.0」后复制 API Key 的路径。
- 文档说明「表演指示」用于单条试听，「角色基调」用于定档并供后续逐句配音合并使用；中文默认引擎改为豆包语音 2.0。

## 测试结果

- `cd frontend && npx tsc --noEmit`：0 error。
- `cd frontend && npm run lint`：0 error，25 个既有 warning（均在 `app/page.tsx`、`app/plaza/page.tsx`，与本次改动无关）。
- `cd backend && <py> -m pytest -q tests/test_studio_casting_frontend.py`：30 passed。
- `cd backend && <py> -m pytest -q tests/ -k studio`：1659 passed，5550 deselected，32 warnings。
- 读取 `.env.example` 的既有文档测试：`test_claude_agent_docs.py`、`test_local_watch_docs.py`、`test_chat_image_tool_docs.py`、`test_local_watch_capture_docs_r3.py` 共 54 passed。

## 未完成项

- 无。`StudioAssetAudio.tsx` 不需要改动。
- 未做真实浏览器端到端试听；本次按任务约定使用离线组件探针和 Mock/假 API，不联网、不读取 `.env`、不打印任何 Key。
