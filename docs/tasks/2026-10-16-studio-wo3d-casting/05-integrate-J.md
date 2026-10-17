# WO3d 集成任务 J：文档补齐 WO3c 并统一到 WO3d

工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`。Python：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。

## 背景
- `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example` 里的短片工作室章节标题还写着「WO1–WO3b」。
- 第 3c 期（拆解与分集，已合入 main）的内容在这四个文件里完全缺失。README 第 331 行附近还写着「本期不做自动拆解、分集」，这已经过时。
- 第 3d 期（定妆与声线）的段落已由块 C 追加在末尾。

## 只许改这 4 个文件
`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example`。同一工作区另有任务 I 正在改后端和前端代码，那些文件一律不碰。

## 要做的事
1. **补 WO3c 内容。** 依据是 `docs/tasks/2026-10-16-studio-wo3c-breakdown/02-spec.md` 与 `06-verify.md`，以及实际代码：`backend/studio/breakdown.py`、`breakdown_material.py`、`breakdown_plan.py`、`routers/studio.py` 里 breakdown/plan/episodes 相关路由、`frontend/components/studio/Breakdown*.tsx`、`EpisodePlan.tsx`、`SynopsisPanel.tsx`、`BibleTable.tsx`。
   - 内容要点：两条拆解路径（小说工坊结构化导入加按批补全；次要来源通读）、拆解前报价、断点续跑与 `retry_needed`、分集方案表与 G0 批准（`plan_revision` / `plan_approved_revision`、`expected_revision`）、导出 Markdown，以及相关环境变量。
   - 只写代码里确实存在的行为。用 grep 核实每个路由名、环境变量名和默认值，不确定就不写。
2. **统一标题和措辞。** 「WO1–WO3b」改为「WO1–WO3d」。删掉或改写已经过时的陈述，例如「本期不做自动拆解、分集」。
   - 先全库搜索：`grep -rn "WO3b\|WO1–WO3\|不做自动拆解\|不做拆解" --include=*.md --include=.env.example .`，排除 `docs/tasks/`、`node_modules`。
3. **核对块 C 追加的 WO3d 段落与实际代码一致。**
   - 环境变量名和默认值（`FIONA_STUDIO_PRICE_SEEDREAM_CNY=0.30`、`FIONA_STUDIO_PRICE_COSYVOICE_CNY_PER_10K_CHARS=2.0`，以及 `backend/studio/pricing.py` / `config.py` 里实际出现的在途上限变量），必须与 `backend/studio/*.py` 中的实际读取一致。
   - 依赖：`edge-tts==7.3.1`，系统需要 ffmpeg/ffprobe。
   - 不一致时以代码为准，改文档。
4. 保持各文件原有文风和密度，不大段重写无关章节。

## 验证
- `cd backend && <python> -m pytest -q tests/ -k "doc or env or readme or claude_md or architecture"`：全部通过，或注明与本任务无关的失败。
- 把每处修改按「文件:行 → 改了什么 → 依据（代码位置）」列进报告 `docs/tasks/2026-10-16-studio-wo3d-casting/05-report-J.md`。
- 不提交、不推送、不联网。
