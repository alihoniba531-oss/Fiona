# 返修单 第 1 轮：模型判级的稳健性与延迟（2026-10-06）

- **依据**：`04-review.md`，即 Opus 5.5 第 1 次复核。结论为通过，没有必须修复项。主会话从可优化项中选出下面几条，本轮一起修。
- **硬规则**：同 `02-spec.md` 第 0 节。另外：
  - 已有测试以快照 `57d2056` 为准，不得修改；
  - `test_crisis_model.py` 是本单新建的，可以追加用例，但已有用例的断言不得放宽。
- **白名单**：
  - `backend/crisis_model.py`；
  - `backend/routers/chat.py`；
  - `backend/scripts/eval_crisis_model.py`；
  - `backend/tests/test_crisis_model.py`；
  - 新建 `backend/tests/test_eval_crisis_model.py`（可选）；
  - `README.md`、`CLAUDE.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`（只改相关句子）；
  - 本目录的 `03-report.md`。

## 改动

1. **连接复用**（分类器视角 O1、路由视角 O2）
   - **问题**：AsyncOpenAI 用默认连接池，空闲连接 5 秒就过期；`wait_for` 超时取消请求时，这条连接也会被关闭。线上两条消息之间往往隔几秒以上，结果几乎每次复核都要重新完成 TCP 和 TLS 握手，超时之后还容易接连超时。
   - **改法**：给 AsyncOpenAI 显式传入 `http_client=httpx.AsyncClient(...)`，并设置：
     - `limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=120)`；
     - `timeout` 沿用调用时读取的配置。
   - `httpx` 已经是 openai 的依赖，不算新增依赖。
   - 在报告里说明：超时取消后，被关闭的连接如何在下一次调用时重建。
   - 不做预热请求，不加后台任务。
2. **路由兜底**（路由视角 O1）
   - `routers/chat.py` 的 `final_crisis`（或等价函数）在 await 模型任务时，用 `try/except Exception` 兜住，异常时按 `model=None` 处理；`CancelledError` 照常传出。
   - 补测试：打桩 `classify` 直接抛 `RuntimeError`，消息被规则判为 possible，并触发参数校验错误；断言仍然「先发资源，再报错」。
3. **长消息送判方式**（分类器视角 O2）
   - 超过 2000 字时，改为取「前 1000 字 + 后 1000 字」，中间用「……」连接，总长不超过 2002 字。这是对 `02-spec.md` 2.1「截取前 2000 字」的有意修改，由主会话批准。
   - 补测试：危机句放在 8000 字消息的末尾时，送判文本里包含这句话。
4. **提示词**（规格视角 MF1 降级、O3、O4，分类器视角 O4）
   - 输出示例改为占位写法 `{"level":"high|possible|none"}`，不要出现具体值。
   - possible 口径回到规格原文：「想消失、不想醒来，或含糊但可能指向自杀的话」，并写明「拿不准时倾向 possible」。
     - 只在句中**明确给出日常目的**时才豁免为 none，例如「定个闹钟」「去旅行」「捆箱子」。
     - 「普通睡眠休息」改成这种写法：句中有明确的日常目的或语境时才算。
   - 消除 high 那段的歧义：「才判 high」改成并列写法，避免被理解成只有询问致死方法时才判 high。
   - 消除「不能凭危险词升档」与「备有危险物品未说明用途判 possible」之间的冲突：写明「只出现危险物品词、但本人没有表达处境或意图的，判 none；本人说明自己备有危险物品、却没有给出日常用途的，判 possible」。
   - 报告里逐条列出提示词与 `02-spec.md` 2.1 口径的每一处差异，以及理由。
5. **解析容错**（分类器视角 O6）
   - level 先做 `.strip().lower()` 再比对。
   - 补测试：`"HIGH"`、`" high "` 都能被识别。
6. **评测脚本**（评测视角 O2–O5，规格视角 O2、O7）
   - 规则已判 high 的句子不调用模型，与线上一致，单独计数为 `rule_high_skipped`。
   - 模型单独评分时，对期望 none / not_high 的句子，high 比 unavailable 更差。
   - 日志泄漏检查：
     - 原文的任意 6 字以上片段出现在日志里就算泄漏；短于 6 字的句子按整句判断；
     - 同时检查 stdout 和 stderr；
     - 打印实际捕获到的 `level=` 和 `failed` 行数，并断言二者之和等于调用次数。
   - C4 的分母按唯一句去重。
   - 计分的纯函数（`worst_level`、`meets_expected`、日常统计、p90）加单元测试，不出网。
7. **文档**（评测视角 O1、O6，规格视角 O6）
   - `docs/DEPLOYMENT.md` 写明以下几点：
     - 服务器到 DashScope 的网络延迟决定超时回落的比例；
     - 上线后用 `journalctl -u fiona | grep -c '\[crisis-model\] failed'` 和 `grep -c '\[crisis-model\] level='` 计算回落比例；
     - 回落比例超过 10% 时，考虑把 `FIONA_CRISIS_MODEL_TIMEOUT_SECONDS` 调到 3。
   - `docs/ARCHITECTURE.md` 的模型清单里注明：`qwen3.8-flash` 也用于危机复核，不回退、不重试。
   - 修正报告中与实际不符的自述。

## 报告与验收

在 `03-report.md` 末尾追加「第 1 轮返修」，内容包括：
- 逐条写出改法与行号；
- 全量测试结果；
- 一次小样本真实评测的原样输出，命令为 `--repeats 1`，覆盖全部语料。

主会话会在沙箱外独立重跑全量测试、真实模型评测和私藏盲测。
