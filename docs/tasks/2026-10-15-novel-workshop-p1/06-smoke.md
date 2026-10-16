# 小说工坊 P1 真实模型冒烟测试记录（2026-10-16）

作者批准，预算 ¥5。

## 环境

- **后端**：隔离启动在 127.0.0.1:8071。使用临时 SQLite 库，`DEV_MODE=0`（计费开启），`FIONA_NOVEL=1`，白名单只放测试账号 `tester01`（通过临时邀请码登录）。初始余额 3000 草莓。
- **配置**：
  - 推演模式为 critique；
  - 主编、情节架构师、审校、档案员：`dashscope:qwen3.8-max`；
  - 人物代言人：`ark:doubao-seed-2-1-pro-260915`；
  - 反转设计师、写手：`deepseek:deepseek-flash`；
  - 目标 2 章，每章 1000 字，预算 700 草莓。
- **测试思路**：拆迁楼存档摄影师，在空楼顶层撞见一间灯还亮、饭菜还温热的屋子。

## 过程

1. 建书 → setup（预扣 68，实扣 9）→ `awaiting_setup` → 插一条留言 → 确认立项 → `running`。
2. **第 1 章 finalize 以 `decision_invalid` 暂停**。千问主编的 `objection_responses` 没能覆盖全部 O*/A*，报错也只有一句笼统的话。→ 第 2 轮返修（05-fix-r2）：报错列出具体 ID，并给出按序的待回应清单。
3. 重启后端并 resume 之后，**再次暂停**。报错已经明确写出「缺少：A1、A2、A3」，但千问仍然只回应了 O1–O9。根因是替代走向混放在 `objection_responses` 里。→ 第 3 轮返修（05-fix-r3）：替代走向单独成字段 `alternative_responses`，同时兼容旧格式。
4. 再次重启并 resume：第 1 章和第 2 章的 finalize 都**一次通过**，进入 `awaiting_end` → 导出 Markdown → 确认完结 → `completed`。

## 核对结果

| 项目 | 结果 |
|---|---|
| 状态流转 | setup_running → awaiting_setup → running →（两次 paused/decision_invalid → resume）→ awaiting_end → completed，全部符合 §5 |
| 草莓总账 | 用户余额减少 392 = novels.spent 392 = 26 个步骤 strawberries_charged 之和 392；reserved = 0 |
| 价目折算 | catalog 返回每千 token 的草莓价：千问 1.8/5.4、DeepSeek flash 0.33/1.3、豆包 0.9/4.5，与 §13 D1 一致 |
| 逐步核对 | 每一步的实扣 = ceil(token × 价目)，误差在 1 颗以内。例外是第 1 章 finalize：两次暂停共 4 次失败尝试也照规格计费，累计 138，但该步只记录了最后一次的 token |
| 续跑不重复 | 两次 resume 后，spent 都从暂停时的数值接着累加，已完成的步骤没有被重复调用 |
| 留言 | N1 下发到第 1 章，主编采纳（在结尾钩子里落实了老照片），状态为 delivered |
| 圣经版本 | 1 setup → 2 user_edit（立项确认）→ 3 archive:1 → 4 archive:2 |
| 导出 | 200，Markdown 附件，约 9.8KB |
| 章节 | 第 1 章 1597 字，无标记；第 2 章 1643 字，带 `length_out_of_range`（上限 1600）和 `review_unresolved` 标记，按规则不暂停 |
| 花费 | 392 草莓，约合 ¥2.6（成本 × 1.5 定价），在预算内 |

## 遗留，需要作者决定或后续修复

1. **失败的校验重试也向用户计费**。第 1 章 finalize 失败的 4 次尝试约收 110 草莓（约 ¥0.7）。按 D2 拍板，平台主编没有 Claude；较弱的模型更容易失败，这部分代价实际落在用户身上。是否改成「因 `decision_invalid`/`step_failed` 暂停时，退还该步骤的全部扣费」，需要作者拍板。
2. **resume 重跑时步骤行的 token 被覆盖**。扣费累计是正确的，但 `input_tokens`/`output_tokens`/`attempts` 只保留最后一次运行的值，成本统计会偏低。建议改为累加。不影响收费。
3. **千问担任主编的写作质量没有评估**。这次冒烟只验证流程能走通，没有判断文笔和剧情。
