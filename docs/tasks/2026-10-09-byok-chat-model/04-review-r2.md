# 第 3 轮复核记录（Opus 5.5，只核 R2 返修项）

输入：全部规格与返修单、`04-review.md`、`04-review-r1.md`、本轮改动差异（第 2 轮复核版本 → 当前）、完整补丁、主控 R2 验收结果与截图。三组复核员只读；「必须修复」项派一名核实员尝试推翻。工作流 `wf_b77d20ad-ecb`，4 个代理。

## 结论

R2-1（中断/关闭分离）复核员沙箱外实测 2700 次中断 0 漏醒、fd 无泄漏，R1 正控同窗口漏 3–8 次；R2-2 gzip/deflate/br 等压缩响应全部被拒、炸弹不解压；R2-3、R2-4、R2-5、R2-6 第 1–3 条修好。**必须修复 1 条**：F0（底栏新增的切回可见刷新会清掉「改用平台/改用我的模型」失败文案，R2-6 第 4 条引入，与 R2-5 同类）。其余可优化项低成本一并在 R3 修。

## 返修项核验

- **byok-core**：修好 3
- **chat-billing**：修好 5
- **frontend-docs**：修好 5、部分修好 2；部分修好：R2-6 第 4 条：底栏 ChatModelFooter 初次加载失败时可重试，切回可见时自动刷新，不过量请求、不与设；部分修好：R2-4 文档：其他 pending 下零余额 BYOK 用户的免费出口（本组只核文档）

## 逐条结论

| 编号 | 问题 | 位置 | 原级别 | 核实 | 最终级别 | 处理 |
|---|---|---|---|---|---|---|
| K0 | 本轮去掉中断线程的 client.close 后，取消若落在 attach_client 与 SDK 发请求之间，请求照常发给厂商 | `backend/byok/client.py:301` | 可优化 | — | 可优化 | R3-2 |
| K1 | 文档称 custom 在响应头前挂起时「会立即中断」，但 TLS 握手停顿期间中断不生效，最多等 60 秒连接超时（既有行为，非本轮引入） | `backend/byok/url_safety.py:131` | 可优化 | — | 可优化 | R3-5（文档更正） |
| C0 | 零余额 BYOK 在天气 pending 下说「换个话题」仍被草莓不足卡住，最长 600 秒 | `backend/services/chat_service.py:1064` | 可优化 | — | 可优化 | R3-3（规格方裁定放开） |
| C1 | 文档仍写「免费取消照平台逻辑」，没有说明 R2-4 新增的 BYOK 专属出口 | `docs/ARCHITECTURE.md:87` | 可优化 | — | 可优化 | R3-5 |
| F0 | 底栏新增的 visibilitychange 刷新会清掉「改用平台/改用我的模型」的失败文案（R2-6 第 4 条引入的回归） | `frontend/app/page.tsx:298` | 必须修复 | CONFIRMED·必须修复 | 必须修复 | R3-1 |
| F1 | ChatModelForm 残留竞态：操作进行中刷新失败，操作自己的失败文案会被下一次成功刷新清掉 | `frontend/components/ChatModelSection.tsx:69` | 可优化 | — | 可优化 | R3-4 |
| F2 | 文档「上游在返回响应头之前挂起时……custom 会立即中断」在 TCP 建连阶段不成立 | `backend/byok/url_safety.py:164` | 可优化 | — | 可优化 | R3-5（同 K1） |
| F3 | R2-4 新增的零余额免费出口在 CLAUDE/ARCHITECTURE 中仍描述为「照平台逻辑」，README/DEPLOYMENT 未提 | `CLAUDE.md:61` | 可优化 | — | 可优化 | R3-5 |
