# 返修单 第 2 轮：收尾（2026-10-06）

依据：`04-review-round2.md` 的可优化项。只做下面三件事，其他一律不动；**提示词不得修改**。

1. **`PLAN.md`**：第 127 行一带把「只看本轮前 2000 字」改为「超过 2000 字时取首尾各 1000 字」，与代码一致。只改这一句。
2. **`backend/routers/chat.py`**：`final_crisis`（或等价函数）的 `except Exception` 分支里，打印一行 `[crisis-model] failed type=<异常类名> ms=<耗时>`，格式与 `crisis_model.py` 现有的失败日志一致，不打印原文。
   - 在 `backend/tests/test_crisis_model.py` 追加断言：上一轮新增的那条「classify 抛 RuntimeError」测试里，日志恰好多出这一行，且不含原文。
3. **`03-report.md`**：在第 6.2 节补一行：规格写的是「不带求死语境的中性问题（例如问桥有多高、楼有几层）」，提示词收窄为「中性高度/楼层问题」，并说明理由。末尾追加「第 2 轮返修」，贴全量测试结果。

**白名单**：`PLAN.md`、`backend/routers/chat.py`、`backend/tests/test_crisis_model.py`、`03-report.md`。硬规则同 `02-spec.md` 第 0 节。
