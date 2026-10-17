# 块 C 前端报告

## 文件与关键位置

| 文件 | 关键行 | 内容 |
|---|---|---|
| `frontend/lib/studio-casting.ts` | 13–16 | `casting_looks` 报价类型、`CastingLook`、`CastingLookSource` |
| `frontend/lib/studio-casting.ts` | 38–40 | `CastingItem.look` / `look_source` 与 PATCH `look` 字段 |
| `frontend/lib/studio-casting.ts` | 75–76 | `quoteCastingLooks` / `startCastingLooks` 请求封装 |
| `frontend/lib/studio-casting.ts` | 85–90 | `CASTING_LOOK_FIELDS` 字段与中文标签镜像、200 字上限 |
| `frontend/lib/studio-casting.ts` | 100–111 | 报价类型/来源标签、`casting_look` 在途判断 |
| `frontend/components/studio/CastingItemCard.tsx` | 23–56 | 造型草稿、来源、空状态、变更字段计算与保存 |
| `frontend/components/studio/CastingItemCard.tsx` | 73–93 | 造型说明展示、来源标签、编辑表单、在途提示 |
| `frontend/components/studio/CastingItems.tsx` | 17–18、35 | 风格状态与可补全条目筛选（排除场景、孤儿） |
| `frontend/components/studio/CastingItems.tsx` | 94–98 | 批量提示、风格未选提示、补全按钮 |
| `frontend/components/studio/CastingQuoteDialog.tsx` | 17–27 | 造型报价文案、按项计价、确认补全 |
| `frontend/components/studio/CastingStage.tsx` | 10、26、85–87 | 造型报价请求与 quote 状态扩展 |
| `frontend/components/studio/CastingStage.tsx` | 102、105 | 传递风格/补全回调，确认后启动 `casting_looks` 任务 |
| `backend/tests/test_studio_casting_frontend.py` | 350–410 | 新增 5 组块 C 离线测试及 mock 契约 |

## 逐项对应

- **类型与请求函数**：新增 `CastingLook = Record<string, string>`；`CastingItem` 增加 `look`、`look_source`；`CastingQuoteKind` 增加 `casting_looks`；请求路径与请求体按 §2.3 契约实现。
- **字段镜像**：`CASTING_LOOK_FIELDS` 按人物 8 项、道具 5 项的顺序和中文标签镜像 `LOOK_FIELDS`，上限为 200 字。
- **卡片展示**：仅人物和道具显示「造型说明」，按字段逐行显示标签和内容；来源为 `director`/`author` 时显示「导演补全」/「作者修改」。
- **卡片编辑**：提供「编辑」入口，逐字段输入框限制 200 字；保存时只 PATCH 发生变化的字段，符合后端合并规则。
- **空状态与在途**：空状态文案与规格一致；`casting_look` 的 `queued`/`running` 任务显示「导演正在补全造型…」。
- **批量栏**：新增「补全造型说明」，仅提交已勾选、非场景、非孤儿条目；风格未选时禁用并提示「先选定风格」；批量提示文案按规格落地。
- **报价框**：复用 `CastingQuoteDialog`，造型类型显示「导演模型补全造型说明」，确认按钮为「确认补全」；确认后调用 looks/start。
- **阶段编排**：报价与启动请求接入 `CastingStage`，导演模型名称用于造型报价；任务启动后正常刷新 `CastingState.jobs`。
- **样式约束**：未修改 `globals.css`，未新增依赖，沿用现有 `btn`、`tag`、`ceramic-card` 等类名。

## 测试结果

- `python -m pytest -q tests/test_studio_casting_frontend.py`：`28 passed`。
- `python -m pytest -q tests/ -k studio`：`1594 passed, 5550 deselected`（32 个既有依赖弃用警告）。
- `npx tsc --noEmit`：退出码 0。
- `npm run lint`：0 error、25 warning；警告均来自块 C 之外的既有文件（`app/page.tsx`、`app/plaza/page.tsx` 的未使用变量与 `<img>` 提示）。

## 未完成项

无。块 C 范围内的契约、交互与测试均已完成。
