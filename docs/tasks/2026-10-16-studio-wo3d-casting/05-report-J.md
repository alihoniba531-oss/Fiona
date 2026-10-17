# 任务 J 报告：文档补齐 WO3c 并统一到 WO3d

日期：2026-10-16　工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`

## 1. 改动清单（文件:行 → 改了什么 → 依据）

### CLAUDE.md
| 位置 | 改动 | 依据（代码/文档） |
|---|---|---|
| CLAUDE.md:165 | 标题 `## 短片工作室 WO1–WO3b` → `WO1–WO3d` | 任务要求；WO3c 已合入（main `d11b60d`） |
| CLAUDE.md:171 | 段末「后续拆解、分集以当前 `snapshot_no` 为依据，本期不新增拆解或付费调用。」改为「……（WO3c）。」（删掉过时的「本期不新增拆解」） | WO3c 已实现拆解与付费调用：`backend/studio/breakdown.py` |
| CLAUDE.md:173 | 新增 WO3c 第 1 段：表与补列、结构化导入 + `novel_complete` 补全、次要来源 `text_map`+`synopsis`、`episode_plan` 分集、`locate_scenes`、`merge_bible` | `studio/store.py:102-155,247-253`；`studio/breakdown_material.py:39-155`；`studio/breakdown.py:247,288-330`；`studio/breakdown_plan.py` |
| CLAUDE.md:174 | 新增 WO3c 第 2 段：按批报价、`FIONA_STUDIO_MAX_QUOTE_CNY`/当日额度/Claude 月额度、确认建批与预留、单批重跑、取消、重启恢复、重新拆解检查 | `studio/breakdown.py:82-165,222-287,638-695`；`studio/spend.py:111-124`；`studio/brain.py:420-423` |
| CLAUDE.md:175 | 新增 WO3c 第 3 段：`GET .../breakdown` 字段、`partial`、`plan_revision/plan_approved_revision/g0_approved`、`expected_revision`、outdated、总表编辑、Markdown 导出、无专属环境变量、前端 5 秒轮询 | `routers/studio.py:314-406`；`studio/breakdown.py:628-635`；`studio/breakdown_plan.py:60,115-137,204-215,311-355,600-658`；`frontend/components/studio/BreakdownPanel.tsx:46`、`BreakdownStage.tsx:50-59`、`EpisodePlan.tsx:70-71` |
| CLAUDE.md:186 | WO2 段「拆解页提供 WO3a 剧本试读预览，其他三个阶段显示后续开放。」改为「拆解页为 WO3c 拆解与分集、定妆页为 WO3d 定妆与声线，其余阶段显示后续开放。」 | `frontend/components/studio/StudioWorkbench.tsx:22,142-146` |

### README.md
| 位置 | 改动 | 依据 |
|---|---|---|
| README.md:325 | 标题 `（WO1–WO3b）` → `（WO1–WO3d）` | 任务要求 |
| README.md:327 | 段末「「①拆解」现提供剧本试读预览，其余三个阶段将在后续版本开放。」改为「「①拆解」已开放拆解与分集，「②定妆」开放到 G1 定妆与声线，③④将在后续版本开放。」 | `StudioWorkbench.tsx:22,142-146` |
| README.md:331 | 删掉过时的「本期不做自动拆解、分集。」，保留「建项目与同步不花钱。」 | WO3c 已实现 |
| README.md:360-362 | 新增 WO3c 两段面向作者的说明：报价与开跑、两条拆解路径、单批重跑换模型、费用口径；梗概/总表/分集方案可编辑、G0 批准与版本、Markdown 导出、快照 outdated 提示 | 同 CLAUDE.md 各项代码依据 |

### docs/ARCHITECTURE.md
| 位置 | 改动 | 依据 |
|---|---|---|
| ARCHITECTURE.md:334 | 表清单补 `breakdowns/chunks/units/bible/episodes/plan_revisions`；「WO3a/WO3b 通过 `migrate_schema`」改为「WO3a–WO3d」 | `studio/store.py:102-155,247-253` |
| ARCHITECTURE.md:399 | 「第一阶段提供剧本试读预览，其余三阶段保留真实空态。」改为「第一、第二阶段分别为拆解与分集（WO3c）与定妆与声线（WO3d），第三、第五阶段保留真实空态。」 | `StudioWorkbench.tsx:22,142-146` |
| ARCHITECTURE.md:423-431 | 新增 `### WO3c 拆解与分集（G0）` 一节（4 段）：模块分工与状态表/G0 定义；两条拆解路径与规则常量；报价-确认-执行-重跑-取消-恢复-重新拆解；只读接口与导出、前端轮询 | `studio/breakdown.py`、`breakdown_material.py:39-155`、`breakdown_plan.py:600-658`、`routers/studio.py:314-406`、`spend.py:111-124`、`brain.py:420-423`、`BreakdownPanel.tsx:46`、`EpisodePlan.tsx:70-71` |

### backend/.env.example
| 位置 | 改动 | 依据 |
|---|---|---|
| backend/.env.example:202-203 | 在 `FIONA_STUDIO_DAILY_CNY/MAX_QUOTE_CNY` 前新增两条注释：WO3c 无专属变量，整次拆解与单批重跑报价同受当日额度与单次报价上限约束（Claude 受月度美元额度），每集默认 180–240 秒（可 60–900），沿用 `FIONA_STUDIO_BRAIN_DEFAULT` | `studio/config.py:105-106,118`（`FIONA_STUDIO_DAILY_CNY` 默认 300、`FIONA_STUDIO_MAX_QUOTE_CNY` 默认 100、`FIONA_STUDIO_BRAIN_DEFAULT` 默认 claude）；`studio/spend.py:111-124`；`studio/breakdown.py:142-152`；代码里没有 `FIONA_STUDIO_BREAKDOWN_*` 变量 |

未改动但已核对：README.md:350 的 WO3a 试读说明（试读面板仍在「①拆解」内，描述依旧成立）、README.md:335 的「拆解等后续模型操作仍需单独报价确认」（拆解确实需单独报价）、ARCHITECTURE.md:336 的 WO3b 段落。

## 2. 块 C（WO3d）与代码一致性核对

| 文档声明 | 代码实际 | 结论 |
|---|---|---|
| `FIONA_STUDIO_PRICE_SEEDREAM_CNY=0.30` 元/张 | `studio/pricing.py:254,258,285`（`Decimal("0.30")`，`PRICE_SEEDREAM_ENV`） | 一致 |
| `FIONA_STUDIO_PRICE_COSYVOICE_CNY_PER_10K_CHARS=2.0` 元/万字符，最低 0.01 | `pricing.py:256-259,288-289,303-308` | 一致 |
| 出图在途上限 `FIONA_STUDIO_MAX_INFLIGHT_IMAGE` 默认 3，配音 `FIONA_STUDIO_MAX_INFLIGHT_TTS` 默认 2，合法 1–10，非法回落并只告警一次 | `casting_jobs.py:30-33,178-196`（`DEFAULT_INFLIGHT_IMAGE=3`、`DEFAULT_INFLIGHT_TTS=2`） | 一致 |
| 唯一新增依赖 `edge-tts==7.3.1`，另需系统 ffmpeg/ffprobe | `backend/requirements.txt:19` | 一致 |
| 其余 WO3d 段落的模块、接口、错误码描述 | `studio/casting*.py`、`providers/image_seedream.py`、`tts_cosy.py`、`tts_edge.py`、`audio.py`、`routers/studio.py` casting 路由 | 一致，无需改动 |

## 3. 验证

- 搜索残留过时措辞（排除 `docs/tasks/`、`node_modules`）：`grep -rn "WO3b\|WO1–WO3\|不做自动拆解\|不做拆解\|剧本试读预览" --include='*.md' --include='.env.example' .`
  - 结果为：标题已是 `WO1–WO3d`；仅剩 `WO3b 的 studio.sources...` 这类对第 3b 期功能本身的正确指代（保留）。
- `cd backend && /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/ -k "doc or env or readme or claude_md or architecture"`
  - **226 passed, 6851 deselected**，与本任务改动前基线相同（0 失败）。
- 未提交、未推送、未联网；只改了本任务允许的 4 个文件（`git status` 中其余改动来自任务 I 与块 C，未触碰）。
