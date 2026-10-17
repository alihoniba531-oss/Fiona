# WO3d 初查任务：按清单逐项核对，只读不改代码

工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`。Python 解释器：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。

- 基线是 `d11b60d`。本期改动用 `git diff d11b60d` 和 `git status --porcelain` 查看，未跟踪的新文件也算在内。
- 规格：`docs/tasks/2026-10-16-studio-wo3d-casting/02-spec.md`。
- **只许写一个文件**：`docs/tasks/2026-10-16-studio-wo3d-casting/06-precheck.md`。代码和测试一律不改。
- 需要临时脚本或临时库时，放在 `$TMPDIR` 里。
- 同一工作区正在跑全量测试，不要删除或移动任何文件，也不要动 `frontend/node_modules`。

## 清单

每项给出结论：**通过**、**不通过** 或 **存疑**。每项都要附证据，写成 `文件:行`，加一句说明。不通过和存疑的，要写出具体的失败场景：什么输入或状态，会得到什么错误结果。

1. **付费请求只发一次。**
   - Seedream、CosyVoice、edge-tts 的适配器在任何错误路径上都不重试。
   - `casting_jobs` 在任何分支都不会对同一任务调用两次适配器，包括异常处理、修正重请求、调度器重复 tick、并发确认这些分支。
   - Seedream 必须 `follow_redirects=False`。
2. **错误分类。**
   - 超时、断连、5xx、坏响应 → `uncertain`，预留保留。
   - 4xx、429 → `rejected`，释放预留，不结算。
   - 审核拦截 → `failed`。
   - 每类找出对应的代码和测试。
3. **报价。**
   - 同一报价只能确认一次，第二次返回 409。
   - 15 分钟过期在确认时检查，价格在确认时锁定。
   - 指纹包含 `quote_item_id`。
   - 单次报价上限 ¥100。日上限 ¥300，计入预留、已结算和 uncertain 三项。
   - 声线试听不弹报价，但照样预留并受日上限约束。
   - 风格提案的导演模型调用要预留额度。
4. **恢复。**
   - image/tts 任务处于 `submitting` 或 `running` 时，恢复为 `uncertain`。
   - `queued` 的任务由调度器补发。
   - 恢复过程中付费调用为 0 次。
   - i2v 和 brain 的恢复口径与基线一致。
5. **归属与准入。**
   - 每条 casting 路由都校验作者和项目。
   - 其他项目的 item、asset、job、参考图 id 一律拒绝。
   - 非作者访问返回 404。
   - G0 未批准时，所有 casting 写接口都拒绝。
   - 阶段前置条件（开工确认 → 风格 → 定妆）按规格 §4–§6 执行。
6. **存储。**
   - `save_audio` 和 `save_image` 写在项目目录内，无法路径穿越。
   - 先写临时文件再改名，有大小上限。
   - PIL 处理、写文件、哈希这类重 I/O 都走 `asyncio.to_thread`。
7. **ffmpeg。**
   - 用 `create_subprocess_exec` 传参数列表，不经 shell。
   - 超时后 kill 进程，临时目录清理干净。
   - 特效滤镜字符串与规格 §10 一致。
8. **删号。** `studio_items` 和其他新增数据，与工作室其他表在同一事务里删除。
9. **迁移。**
   - 先用 `git show d11b60d:backend/studio/store.py` 的建表语句造一个旧库，再跑当前的建表和迁移。
   - 新列要补上，迁移可以重复执行。
   - 旧库里能插入 image/tts 任务和 casting 资产。
   - 实际跑一遍，把结果写进报告。
10. **密钥与并发。**
    - 修改 dashscope 全局 api_key 时有锁保护，用完恢复原值。
    - 日志、错误信息、`meta_json`、测试快照里都没有密钥。
11. **原文注入。** `style_inputs` 不带原文摘录。提示词里把原文和来源数据标为不可信。
12. **前端。**
    - uncertain 只显示「可能已扣费」和「释放」，没有重试按钮。
    - 没有在途任务时停止轮询。
    - 报价框显示过期倒计时，绝不自动确认。
    - 出错时有错误态。
    - 390px 宽度下没有横向滚动，从类名和布局上判断。
13. **测试守卫。**
    - 依赖 node 的前端测试，在缺 `frontend/node_modules` 时 skip。
    - 依赖 ffmpeg 的测试，在缺 ffmpeg 时 skip。

## 报告格式

`06-precheck.md` 的结构：
1. 先放一张总表：清单项、结论、证据。
2. 再逐项展开不通过和存疑的条目。
3. 最后一节写「建议 Sonnet 复核重点关注」，列出 3–6 处具体的 `文件:行`。

不联网，不提交。
