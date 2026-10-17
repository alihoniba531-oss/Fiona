# WO3d 集成任务 K：定妆与声线演示数据脚本（截图用，不进仓库）

代码目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio/backend`。Python：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。
演示目录：`S=/private/tmp/claude-501/-Users-yangjing-Desktop-----/4cdfbac6-6c36-436b-b93e-8ad8fab63402/scratchpad/wo1e2e`。

## 只许写这一个文件
`$S/seed_casting_demo.py`。可以读、可以运行它；运行时写入 `$S/e2e.db` 和 `$S/studio/`。
- 仓库里任何文件都不许改。另有任务 I 正在改仓库代码，你只读不写。
- 绝不能连接或写入其他数据库，也不能访问 8010 端口。

## 参照
- 照 `$S/seed_breakdown_demo.py` 的写法：环境变量设置、`asyncio.run(database.init_db())`、假适配器、直接调服务函数。
- 环境变量与 `$S/ui_backend.sh` 完全一致：`FIONA_DB_PATH`、`FIONA_UPLOADS_DIR`、`FIONA_ENV_FILE`、`FIONA_STUDIO_DIR`、`FIONA_STUDIO_OWNERS=studio-e2e`、`DEV_MODE=1`，以及占位 `DASHSCOPE_API_KEY`。
  - 这些变量必须在 import 任何 backend 模块之前设置。
  - 用 `os.environ.pop` 去掉 `ARK_API_KEY`、`ANTHROPIC_*`、`OPENAI_BASE_URL`、`DASHSCOPE_WORKSPACE_ID`。
- 规格见 `docs/tasks/2026-10-16-studio-wo3d-casting/02-spec.md`，§3–§7 和 §8 的接口。

## 脚本要造出的状态（用户 `studio-e2e`）
1. **目标项目**：库里已有「海雾灯塔·返修后」项目（id 以 `3f904b4a` 开头，拆解已完成）。脚本按名字或前缀查到它。
   - 若 G0 未批准，用 `breakdown_plan` 的批准函数批准当前 revision。
   - 然后走 `backend/studio/casting.py` 的服务函数（与 REST 路由同一套）推进到下面的状态。
2. **开工确认**已确认：480P、万相、中文。
3. **风格**：
   - 风格提案任务用假 brain 返回 3 个方案，内容要像真的：名称、画风、色板、镜头、光线、理由，全部是自写的中文。
   - 选定第 2 个方案，写实度设为 photoreal。
4. **定妆**（假 Seedream：在最底层传输上返回 PIL 生成的 2560×1440 PNG）：
   - 每类（人物、场景、道具）至少各有 1 条有 2–3 个版本，画面颜色彼此不同，并写上「人物A v1」之类的大号文字。
   - 一条已批准，一条已跳过，其余待定。
   - 再造一条 `uncertain` 的出图任务（模拟超时），界面上应显示「可能已扣费」和「释放」。
   - 再造一条 `rejected` 的出图任务（模拟 429）。
   - **不要**留下 `queued`、`submitting`、`running` 状态的任务，否则 8061 后端的调度器会去调真实接口。
5. **声线**：
   - 一个人物有 2 条中文试听：假 CosyVoice 返回 2 秒正弦 WAV，一条无特效、一条带 `robot:B`。两条都必须走真实的 `process_voice`，也就是真实 ffmpeg。
   - 其中一条已选定。
   - 另一个人物有 1 条英文试听：假 edge-tts 返回音频，形状按 `backend/tests/test_studio_media_tts.py`。
6. 另一个演示项目（id 以 `95be0a55` 开头）保持 G0 未批准，用来展示门禁。

## 要求
- 脚本可以重复运行（幂等）。已有定妆数据时，先清掉该项目的 `studio_items`、casting 资产和 image/tts 任务再造，或者跳过已有项，二选一并写在注释里。
- 运行结束时打印项目 id、各条目的状态、资产数和任务状态分布。
- 服务函数签名对不上时，按实际代码调整脚本，不要改仓库代码。实在走不通的地方写进报告。
- 报告只写在脚本末尾的注释里，外加你的最终回复，不另建文件。
- 不联网，不提交。
