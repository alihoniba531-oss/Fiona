# 第 2 轮复核记录（Opus 5.5，只核 R1/R1b 返修项）

输入：`02-spec.md`、`05-fix-r0.md`、`04-review.md`、`05-fix-r1.md`、`05-fix-r1b.md`、本轮改动差异（首轮版本 → 当前）、相对基线完整补丁、主控 R1 验收结果与 16 张截图。三组复核员（byok 核心 / 聊天计费 / 前端文档）全新上下文、只读；「必须修复」项各派一名核实员尝试推翻。工作流 `wf_9efee840-15e`，8 个代理。复核模型按作者要求改用 Opus 5.5。

## 结论

返修项大多修好；**必须修复 4 条**：K0（看门狗/取消在中断线程里 shutdown 后立刻 close，有竞态，间歇退化为 60 秒）、K1（4 MiB 上限只计压缩后字节，gzip 可绕过）、C0（天气 pending 新加的关键词正则改变了有余额 BYOK 用户的路由，偏离平台）、F0（后台刷新清掉了用户正在看的失败文案）。C1（route/web_search 等 pending 下零余额 BYOK 仍被卡）核实降为可优化，但规格方决定在 R2 一并修。其余可优化项低成本一并修。

## 返修项核验

- **byok-core**：修好 5、部分修好 2；部分修好：R1-4 custom 每连接 4 MiB 字节上限、超限 abort、错误类别固定、预设不受影响；部分修好：R1-6 看门狗与取消对预设经 network_stream 取 socket 做 shutdown；只用公开 API；取不到 socket
- **chat-billing**：修好 10、未修好 1、部分修好 1；未修好：R1-2 ⑤ 对照组：余额 10、同样配置的用户行为与基线平台路径一致；部分修好：R1-2 总目标 B0「零余额 BYOK + 残留 pending 被卡死」
- **frontend-docs**：部分修好 1、修好 11；部分修好：R1-9 F0：ChatModelSection 监听 storage 版本号与 visibilitychange 刷新，只更新服务端状态、

## 逐条结论

| 编号 | 问题 | 位置 | 原级别 | 核实 | 最终级别 | 处理 |
|---|---|---|---|---|---|---|
| K0 | R1-6：中断线程 shutdown 后立即 close，看门狗和取消会间歇漏醒，回环验收测试不稳定 | `backend/byok/client.py:152` | 必须修复 | CONFIRMED·必须修复 | 必须修复 | R2-1 |
| K1 | R1-4：4 MiB 上限只计压缩后的线上字节，gzip 响应可绕过并打爆内存 | `backend/byok/url_safety.py:118` | 必须修复 | CONFIRMED·必须修复 | 必须修复 | R2-2 |
| K2 | 预设厂商在响应头到达前，看门狗和取消都无法中断，最长等 60 秒；文档「总时长即此配置」不准确 | `backend/byok/client.py:147` | 可优化 | — | 可优化 | R2-6（文档更正） |
| C0 | 天气 pending 新增关键词正则对所有启用 BYOK 的用户改路由，余额 10 的对照组偏离基线平台路径 | `backend/services/chat_service.py:1510` | 必须修复 | CONFIRMED·必须修复 | 必须修复 | R2-3 |
| C1 | route/web_search 等非生图、非天气 pending 下，零余额 BYOK 用户仍被卡死（B0 未全修） | `backend/services/chat_service.py:1061` | 必须修复 | CONFIRMED·可优化 | 可优化 | R2-4（规格方裁定后一并修） |
| C2 | 预设厂商在建流阶段（上游未回响应头）取消或到总时限时仍要等 60 秒读超时，文档写「总时长即 TOTAL_SECONDS」不成立 | `backend/byok/client.py:144` | 可优化 | — | 可优化 | R2-6（文档更正，同 K2） |
| C3 | 每次中途取消 BYOK 流，asyncio 都会打一条 ERROR 级「exception in shielded future」完整回溯 | `backend/services/chat_service.py:204` | 可优化 | — | 可优化 | R2-6 |
| F0 | 设置页后台刷新会清掉用户正在看的错误文案（本轮 F0 引入） | `frontend/components/ChatModelSection.tsx:62` | 必须修复 | CONFIRMED·必须修复 | 必须修复 | R2-5 |
| F1 | 文档「总时长即 FIONA_BYOK_TOTAL_SECONDS」在上游发响应头之前挂起时不成立 | `docs/ARCHITECTURE.md:143` | 可优化 | — | 可优化 | R2-6（同 K2） |
| F2 | 测试连接撞上平台 10 次/分钟限流时，文案把原因归给用户自己的模型 | `backend/main.py:146` | 可优化 | — | 可优化 | R2-6 |
| F3 | 底栏初次加载网络失败只显示「网络错误，请重试」，没有可点的重试入口 | `frontend/app/page.tsx:307` | 可优化 | — | 可优化 | R2-6 |
