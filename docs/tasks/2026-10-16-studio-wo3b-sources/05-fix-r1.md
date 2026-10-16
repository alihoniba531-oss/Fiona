# WO3b 返修单 R1

复核结论见 `docs/tasks/2026-10-16-studio-wo3b-sources/04-review.md`：通过，另有 1 项必须修复。

**本轮要做的**：按 04-review.md 末尾「给实现方的二次修改指令」第 1–9 条全部执行。
- 第 1 条是必须项：阻塞 I/O 改为 `asyncio.to_thread`。
- 第 2–8 条是作者同意一起做的小打磨。

**补充要求**
- 第 1 条：除复核点名的位置外，再检查一遍 `backend/studio/sources.py` 和 `backend/studio/novel_chat.py` 的 async 路径，看有没有其他会读写整本书文件或处理大文本的同步调用，比如 `read_snapshot` 读块文件并校验 sha256、`source_status` 读 manifest。有的话一并改为 `to_thread`，并写进报告。
- 第 3 条：只对 `source_kind` 非空的项目默认落在「①拆解」。空白项目保持「④镜头」。用户手动切换过页签后，不得再被自动切回。
- 所有新增的 node 驱动测试，缺少 `frontend/node_modules` 时必须 skip。

**完成后**
- 跑工作室和小说相关的专项测试。
- 跑一次后端全量（不带 deselect）；沙箱端口限制导致的失败如实列出即可。
- 跑前端 `npm run lint`、`npx tsc --noEmit`。
- 在 `03-report.md` 追加「二次修改」一节。

约束不变：不联网，不新增依赖，不提交，不改非工作室测试的固定值，派子代理时不要传 model 和 reasoning_effort。
