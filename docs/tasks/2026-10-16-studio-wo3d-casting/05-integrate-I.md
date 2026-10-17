# WO3d 集成任务 I：接通块 A↔B↔C↔D，补集成测试

工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`。Python：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。
权威规格：`docs/tasks/2026-10-16-studio-wo3d-casting/02-spec.md`（§3 数据、§4–§7 流程、§8 接口、§10 规则）。四块已各自完成，报告在同目录 `03-report-{A,B,C,D}.md`，各块只用假实现自测过。**你的任务是让它们真正接通。**

同一工作区另有两个任务并行：任务 J 只改 `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example`；任务 K 只写工作区外的演示脚本。**这四个文件你不许碰。**

## 允许修改的文件
- 新建 `backend/tests/test_studio_casting_integration.py`（主产物）。
- 为修正跨块不一致，可以改：`backend/studio/casting.py`、`casting_jobs.py`、`routers/studio.py`、`store.py`、`providers/image_seedream.py`、`providers/tts_cosy.py`、`providers/tts_edge.py`、`audio.py`、`voices.py`、`casting_prompts.py`、`frontend/lib/studio-casting.ts`、`frontend/components/studio/Casting*.tsx` / `SetupCard.tsx` / `StyleCard.tsx` / `VoicePanel.tsx` / `StudioAssetAudio.tsx`，以及这些文件已有的测试文件。
- 判定标准：哪一侧与 §8 不一致就改哪一侧；§8 没写的，以后端实际返回为准、改前端去对齐。
- 写报告 `docs/tasks/2026-10-16-studio-wo3d-casting/05-report-I.md`：发现的不一致（文件:行、原因、怎么改的）、新增测试清单、测试结果。

## 必须做的集成测试（用真实块 B/C 函数，只在最底层注入假传输）
沿用 `tests/test_studio_casting_api.py` 的建库、准入（JWT 作者）和造 G0 已批准项目的夹具写法。最底层注入方式：
- Seedream：给 `generate_sheet` 的 `transport` 注入 `httpx.MockTransport`（返回真实 2560×1440 PNG 的 base64 或 url 形状，按块 B 测试里的响应夹具），**断言 POST 次数**。若 `casting_jobs._generate_sheet` 无法把 transport 传下去，就用 monkeypatch 替换 `image_seedream` 模块里的传输构造点，不要替换 `generate_sheet` 本身。
- CosyVoice：`synthesizer_factory` 注入，返回一段真实 WAV 字节（用 ffmpeg 或 `wave` 生成 1–2 秒正弦）。
- edge-tts：`communicate_factory` 注入，返回 mp3/音频块与词边界（形状按块 B 测试）。本机 venv 没装 edge-tts，测试不得依赖它真实存在。
- `process_voice` 用真实 ffmpeg。整个测试模块在 `shutil.which("ffmpeg")` 或 `shutil.which("ffprobe")` 为空时 `pytest.skip`（CI 可能没有 ffmpeg）。
- 导演模型（风格提案）照块 A 测试的假 brain 方式。

场景（每条一个或多个测试）：
1. **完整主流程**：开工确认 PUT → 风格报价 → 确认 → 提案落库 → 选定风格（含 realism）→ 对 2 个条目各出 2 版定妆图（报价→确认）→ 资产落库：`item_id`、`version_no` 递增、`role`、实际宽高 2560×1440、文件存在于 `FIONA_STUDIO_DIR` 临时目录 → 批准 1 个条目、跳过 1 个 → `GET /casting` 的 `g1` 进度正确，返回 JSON 形状逐字段符合 §8 `CastingState` / `CastingItem` / `CastingJob`。
2. **Seedream 超时/断连**：任务 `uncertain`，POST 恰好 1 次，预留保留；`POST /jobs/{jid}/release` 释放后预留归零。
3. **Seedream 429 / 400**：`rejected`，不结算费用，不重试（POST 1 次）。
4. **同一报价确认两次**：第二次 409；报价过期后确认被拒。
5. **中文试听**：`POST /casting/voices/audition`（cosy + `robot:B` 特效）→ 真 ffmpeg 处理 → 资产为 48000Hz 单声道 16bit WAV，`probe_audio` 结果与库里记录一致；按字数预留并结算。
6. **英文试听**：edge 路径，免费（不产生费用记录或金额为 0，按 §6 口径），输出 48k WAV。
7. **选定声线**：`POST /casting/items/{id}/voice/approve` 后 `voice_asset_id` 与 `spec_json` 中声线参数一致。
8. **声线目录**：`GET /casting/voice-catalog` 的 fx 键与档位必须与 `audio.FX_PRESETS` 完全一致，且 `frontend/lib/studio-casting.ts` 里用到的键名能在返回里找到（读 TS 源码做字符串断言即可）。
9. **参考图**：定妆报价带参考图 asset id（由 `POST /projects/{pid}/assets` 上传得到）时，Seedream 请求体里确实带上参考图，长边 ≤1536；他人项目的 asset id 被拒。
10. **重启恢复**：预置 `running` / `submitting` 的 image 与 tts 任务跑 recovery，变 `uncertain`，付费调用 0 次。
11. **门禁**：G0 未批准时所有 casting 写接口拒绝；非作者 404。

## 规则
- 付费调用一律不联网；`network_access` 关闭。不要读取 `.env`，不要设置真实 Key。
- 不要隐藏、改名或移动 `frontend/node_modules`。
- 修改前端后跑：`cd frontend && npx tsc --noEmit && npm run lint`（0 error）。
- 后端跑：`cd backend && <python> -m pytest -q tests/test_studio_casting_integration.py` 以及 `<python> -m pytest -q tests/ -k studio`。沙箱禁绑本地端口导致的 `PermissionError: bind` 与本任务无关，报告里注明即可。
- 可以自己拆子代理并行，但同一文件只能由一个代理改。
- 不提交、不推送。
