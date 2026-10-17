# R2-C 前端（先读 08-fix-r2-common.md）

只许改：`frontend/components/studio/{CastingStage,SetupCard,StyleCard,CastingItems,CastingItemCard,VoicePanel,StudioAssetAudio,CastingQuoteDialog}.tsx`、`frontend/lib/studio-casting.ts`；测试 `backend/tests/test_studio_casting_frontend.py`。不改 `globals.css`、不加依赖。

## 要改的
1. 「开工已确认：2026-10-16T20:14:52.032045+00:00」→ 用本地时区格式化为「2026-10-17 04:14」样式（找项目里已有的日期格式化函数复用，例如 `lib/studio.ts` 或分集表里用过的；没有就在 `lib/studio-casting.ts` 写一个纯函数）。所有显示 ISO 时间的地方（试听 created_at 等）同样处理。
2. `uncertain` 提示重复两遍（「可能已扣费，请勿直接重试，去控制台核对」+「可能已扣费，请勿直接重试。」）→ 只保留一句，保留「释放」按钮。
3. 定妆版本图与参考图 `<img>` 加 `loading="lazy" decoding="async"`。
4. 条目卡补充提示词文案改为「补充提示词（之后每次出图都会带上）」；批量栏的补充提示词旁注明「只对本批生效，追加在条目自己的补充提示词之后」。
5. 派生：条目没有已选定版本时，「从已选定版本派生」勾选框禁用并提示原因。
6. 孤儿条目（`orphaned: true`）：卡片显示「已不在当前总表」标签，禁用出图/试听/选定/勾选，且不计入页面上的 G1 进度显示（与后端 `g1` 一致，直接用后端返回值，不自行计算）。
7. 自定义风格：名称、视觉风格为空时「保存风格」禁用并提示。
8. 已定档的试听、已选定的版本：「归档」按钮禁用并 title 提示「先换选定」。skip/reopen 后后端会清空 `approved_asset_id`，界面以后端返回为准，不做乐观假设。

## 验证
- `cd backend && <py> -m pytest -q tests/test_studio_casting_frontend.py tests/test_studio_frontend_shell.py`
- `cd frontend && npx tsc --noEmit && npm run lint`（0 error）
