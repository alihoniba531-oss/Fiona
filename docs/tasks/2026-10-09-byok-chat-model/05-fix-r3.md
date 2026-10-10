# 返修单 R3（回应 04-review-r2.md）

日期：2026-10-09。本单与此前所有规格、返修单同等效力，有冲突时以本单为准。K、C、F 编号对应 `04-review-r2.md`。约束沿用 `05-fix-r2.md` 第 0 节，不变：
- 先写会失败的测试，确认它变红；
- 本任务开始前已有的测试不改；
- 不装包，不发起真实网络请求。

这是小范围收尾，**直接自己做，不必派子代理**。

## R3-1 底栏切回可见时清掉了切换失败的提示（F0，必须修复）

`frontend/app/page.tsx` 的 `ChatModelFooter` 照 R2-5 的方式处理：错误由谁产生，就由谁清。

- 加 `refreshError` ref。
  - refresh 失败时：先置 true，再 `setError`。
  - refresh 成功时：先 `setSettings`；只有 `refreshError.current` 为真时，才复位并 `setError("")`。
- toggle 开始时复位 `refreshError`。
- toggle 自己写错误时（catch 分支），也先把 `refreshError` 复位。

验证（用 Playwright，route 拦截模拟 PATCH 失败，不发真实请求）：
- 底栏 toggle 失败后派发 `visibilitychange`，失败提示仍在。
- 在另一文档写入 `CHAT_MODEL_REV_KEY`，失败提示仍在。
- 初次加载失败后，切回可见时刷新成功，加载错误被清掉。

脚本放在本任务目录之外的临时位置。报告里写明步骤与结果。

## R3-2 发送前取消仍会把请求发出去（K0）

`backend/byok/client.py` 的 `_open`：两条分支都在 `resources.start()` 之后、调用 `endpoint.stream(...)` 或 `chat.completions.create(...)` 之前，各加一道检查：

```python
if resources.closed:
    raise ByokTimeoutError if resources.timed_out else ReplyInterruptedError
```

交给现有的 except 统一关闭。**中断线程里不得恢复任何 close。**

新测试：monkeypatch `_Resources.start`，在启动后立即调用 `control.abort()`；断言 SDK 的发送函数未被调用，并抛出 `ReplyInterruptedError`。看门狗情形同理，应抛出 `ByokTimeoutError`。

## R3-3 零余额 BYOK 在天气 pending 下说「换个话题」仍被卡住（C0，规格方裁定放开）

`services/chat_service.py` 的 `run_chat`，天气 pending 分支，在 `normalize_city` 判断之前加一道检查：

- 生效条件：`ctx.byok_unreserved` 为真，且消息匹配 `^(?:先聊|聊点|换个话题|先不)`。
- 命中后：清 pending，按普通路由继续，最终由 BYOK 回复。

余额充足的用户和平台路由保持不变，R2-3 的对照组断言继续成立。

新测试：
- 零余额 BYOK + 天气 pending + 「换个话题」：pending 被清，BYOK 调用 1 次，余额不变。
- 对照组：余额 10 的 BYOK 用户发同一句，与未配置 BYOK 的用户行为一致。

## R3-4 设置分区的残留竞态（F1）

`ChatModelSection.tsx` 中，save、test、toggle、remove 在自己写错误前（catch 分支，以及 `result.ok === false` 分支）先执行 `refreshError.current = false`。这样操作期间刷新失败、之后又刷新成功时，不会清掉该操作的失败原因。

## R3-5 文档更正（K1、F2、C1、F3）

1. **custom 的中断说明**改为：「custom 在 TLS 建立后立即中断；DNS 解析与 TCP/TLS 建连阶段分别最多等约 5 秒和 60 秒连接超时」。同步修改 `.env.example`、CLAUDE、README、PLAN、ARCHITECTURE、DEPLOYMENT 中所有相关表述。
2. **零余额 BYOK 的免费出口**：在 CLAUDE.md、ARCHITECTURE.md 写明以下规则，README 计费段与 DEPLOYMENT 相应位置同步一句。
   - **generate_image / weather 以外的 pending**：
     - 「算了/取消/不用了/不要了/不查了/没事了」→ 免费取消并清 pending；
     - 以「先聊/聊点/换个话题/先不」开头 → 清 pending，由用户模型回复；
     - 其他补参消息 → 仍报草莓不足，pending 保留。
   - **天气 pending**：「换个话题」类句子同样清 pending、由用户模型回复（R3-3）。
   - 不要再笼统写「照平台逻辑」。

## 验收

- 第 7 节第 1–6 条重跑。
- 全量 pytest 通过数不少于 2809 + 本轮新增数；回环与端口类测试由主控在沙箱外重跑。
- 前端：`npx tsc --noEmit` 退出码 0；`npx eslint .` 0 errors，warnings ≤ 25。
- `03-report.md` 新增「R3 返修」一节，逐条对应 R3-1 到 R3-5。
