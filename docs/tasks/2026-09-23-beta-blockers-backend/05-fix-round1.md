# 返修单 第 1 轮（后端内测阻断）

来源：`04-review.md`（独立复核，结论：不通过）。原规格仍是 `02-spec.md`，白名单、禁止事项与「何时停下来问」判据不变。

## 必须修复（逐条对应 04-review.md）

### R1 客户端断开时退款被级联取消吞掉

完整阅读 `04-review.md` 的 R1（含复核人的探针方法）。要求：
1. `services/chat_service.py` 的 `run_chat` 收尾退款，以及 `routers/chat.py` 的 `_refund_before_stream` 与 `_ReservedChatResponse.__call__` 中的退款/关闭逻辑，改为在 **anyio 屏蔽取消作用域**（`with anyio.CancelScope(shield=True): ...`）内完成，保证在 Starlette 以 task group 取消（ASGI `spec_version` 2.3，uvicorn 生产路径）时退款仍完整提交。
2. 新增测试：直接以 `scope={"type":"http", "asgi": {"spec_version": "2.3"}, ...}` 调用 `_ReservedChatResponse`，模型流打桩为「发出一块后阻塞」，`receive` 在首块之后返回 `{"type": "http.disconnect"}`；断言余额复原到预扣前、`tracker.started` 为真。参数化加入 `spec_version: "2.4"` 作为正控。**先在未修复的代码上确认该测试失败，再修复**，并在报告里写明失败与通过两次的输出摘要。

### R2 危机识别误报（亲昵/夸张口语）

以下句子必须**不命中**（加入 `test_crisis_detector_rejects_required_everyday_phrases`，与原 11 条反例并列）：
`我想死你了`、`宝贝我想死你了`、`我要死了，笑死`、`累得我要死`、`笑得我要死了`、`困得我要死`、`气得我想死`、`我快要死了好困`、`别让我去死记硬背`、`我不想活得太累`、`suicide squad 好看吗`、`跳楼价甩卖`、`跳楼机好刺激`。

### R3 危机识别漏报（直白自伤表达）

以下句子必须**命中**（加入 `test_crisis_detector_recognizes_required_phrases`，与原 11 条正例并列）：
`我想伤害自己`、`我在自残`、`我想自残`、`我只能自残了`、`我又割了自己`、`我要跳河`、`我打算今晚了结自己`、`我想把自己杀了`、`i want to die`、`i don't want to live anymore`、`i want to hurt myself`、`i'm going to cut myself`。

R2 与 R3 由同一个 subagent 一起改 `backend/safety.py`，**两组夹具（原 22 条 + 新 25 条）必须同时全部通过**。`04-review.md` 里给出的参考正则可以借鉴，但以夹具为准。注意撇号：`don't`/`i'm` 在规范化后仍保留撇号，也要兼容用户输入不带撇号（`dont`、`im`）的写法。

### R4 恢复「播报/朗读」强约束 system 消息的原有位置

1. 恢复 HEAD（`git show 54a9b57:backend/services/chat_service.py` 约 454–466 行）的设计：该强约束作为**独立的 `{"role": "system"}` 消息追加在当前 user 消息之后**，文本与 HEAD 完全一致；只在非危机轮追加。
2. 安全底线要求改为：一次请求中所有 system 内容合起来，`BASE_SAFETY_RULES` **恰好出现一次**，且位于**最后一条 system 消息的末尾**。存在尾随的朗读 system 消息时，底线追加在它的末尾，主 system 不再带底线；不存在时维持现状（主 system 末尾）。普通、镜子、看图（`vl_messages` 需要把尾随 system 放到多模态 user 之后）三条路径都要正确处理。
3. 更新 `test_non_crisis_chat_every_reply_prompt_ends_with_one_safety_block` 的朗读分支：断言底线在所有 system 拼接后恰好一次、最后一条 system 以底线结尾且包含「直接开口说话」、发送给模型的倒数第一条是 system、倒数第二条是 user；其余分支断言不变。

## 同轮顺带处理（来自 04-review.md 可优化项，改动小、风险低）

- **O1**：退款本身失败（如数据库锁超时）时，只打印异常类型名、在埋点里记 `refund_failed=True`，不得覆盖已发给客户端的事件，且 `log_event` 仍要写入。
- **O2**：`DEV_MODE=1` 时危机轮不做余额拦截（与 T1.6「DEV 模式完全跳过计费」一致），相应调整测试。
- **O6**：`manage_invites.py` 的 docstring 更新为带 `--env-file` 的用法；三个管理脚本的 `--help` 能看到 `--env-file` 与 `--init-db`。
- **O7**：`manage_strawberries.py list` 不得修改任何数据（不触发每日补给、不写补给日期），直接读出原始余额与补给日期。
- **O8**：`tests/test_beta_admin_scripts.py` 构造子进程环境时同时清除 `STRAWBERRY_DAILY_REFILL`，避免开发者本地配置影响断言。
- **O9**：`database.delete_account_data` 在同一事务里删除该用户的 `chat_slot_state` 行，避免用户名被重新发放后新账号继承旧的待补参数/模式；加测试。
- **O10**：`docs/DEPLOYMENT.md` 的管理脚本一节注明「脚本会执行与服务启动相同的兼容 DDL（只加列/索引），请先备份再运行」。

不处理（留给产品负责人）：O3 中新闻/剧情类提及（如「今天新闻说有人自杀了」）是否算危机、O4、O5。

## 交付

1. 在 `backend/` 下 `.venv/bin/python -m pytest -q` 全绿，并逐个测试文件单独运行也全绿；测试前后 `backend/uploads` 与 `backend/*.db` 快照一致。
2. 把本轮说明追加到 `03-report.md` 末尾「返修第 1 轮」小节：逐条对应 R1–R4、O1/O2/O6–O10，写明新增/修改的测试名，以及 R1 测试先失败后通过的证据。
