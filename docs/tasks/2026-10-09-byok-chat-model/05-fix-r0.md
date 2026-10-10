# 规格修订 R0（回应 03-report.md 第 1 节的停止）

日期：2026-10-09。本修订与 `02-spec.md` 同等效力，冲突处以本修订为准。

## 1. 裁定

允许更新 `docs/CYBER_AVATAR_PLATFORM.md`。第 7.1 条可修改文档清单追加这一项，完整清单为：`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`docs/CYBER_AVATAR_PLATFORM.md` 中的任意几个。

该文件只改「实施状态」段里的当前事实陈述（报告列出的第 39、43 行附近：私聊计费规则、每日上限项数与清单），按第 6.8 节同步；第 2、9 节等已标为历史评估快照的内容不改。

已核对：除上述六份文档外，仓库内其他受版本控制的 Markdown 没有第 6.8 节所列事实的陈述；前端涉及草莓计费文案的 `frontend/app/page.tsx`、`frontend/components/Sidebar.tsx` 已在第 7.1 条清单内。

## 2. 继续执行

从停止处继续完成第 6.1–6.9 节全部任务，保留已写入的 `backend/byok/` 四个文件（可按需修改）。第 7 节验收命令全部重跑，并覆盖更新 `03-report.md`（报告按最终状态重写，不保留「按第 8 节停止」的结论；可在末尾附一句本轮因文档范围冲突停过一次、已由本修订裁定）。

第 8 节停下来的标准不变。
