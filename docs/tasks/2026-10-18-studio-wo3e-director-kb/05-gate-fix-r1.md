# 门禁返修 G1：补 3 处测不出的变异（接着你前面的工作做）

主控在沙箱外复跑了门禁，结果如下：
- 白名单检查通过，两张样卡没有变动。
- tsc、lint 通过，新文件没有粗体。
- 原文重合为 0。
- 老库升级通过。

变异测试共 9 处，6 处被测出来，**3 处存活**。也就是说，测试没有真正证明 §12 第 3 条和第 6a 条。下面这些都是测试缺口：**只补测试，不改实现**。如果补测试时发现实现确实有错，就停下来，在报告里写明，不要自行修改实现。

## 必须完成

用**工作流（workflow 工具）**并行，开 2 个 agent，按文件不重叠分工。每个 agent 的任务说明要自包含，并写明不得调用 subagent / subagent_fork / workflow。

### agent A：只改 `backend/tests/test_studio_kb_core.py`

**G1-1（变异 M2 存活）**
- 存活的变异：把 `retrieval.py` 里预算极小时的兜底分支改成只拼 model 卡，写法是 `text = _compose([model_blocks])`，现有测试照样全过。
- 原因：`test_tight_budget_keeps_template_position_and_model` 只检查了 `card_ids` 或字段，没有检查注入文本 `text` 本身。
- 要补：在 `budget_chars=600` 和 `5000` 两种情况下都断言 `text` 里含有三张卡的标识，即 template、position 卡（`position=opening`）和 model 卡，按 §5 的渲染格式「【卡片 id】」。
- 补完自测：把上面的变异手动打进去，测试必须变红；然后还原。

### agent B：只改 `backend/tests/test_studio_cross_review.py`

**G1-2（变异 M6 存活）**
- 存活的变异：在 `cross_review.py` 里把 `run_brain("cross_review", …, provider=provider, …)` 写死成 `provider="deepseek"`，现有测试照样全过。
- 原因：现有测试没有在传输层证明「审核请求发往 DashScope、model 为 qwen3.8-max」。
- 要补：
  - 用 httpx `MockTransport` 走真实的 `run_brain` 和 provider 路径，不 monkeypatch 掉 `run_brain` 本身。
  - 场景：导演为 deepseek、审核为 qwen，跑一次完整试拆。
  - 断言：
    - 审核请求的 host 是 `dashscope.aliyuncs.com`；
    - 请求体里 `model == "qwen3.8-max"`；
    - DeepSeek 端只收到 `shot_plan` 的请求，没有收到审核请求。
  - 需要的环境变量用 monkeypatch 设成假值，不读真实 Key。

**G1-3（变异 M7 存活）**
- 存活的变异：把 `cross_review.py` 里的 `except Exception:` 改成 `except ZeroDivisionError:`，现有测试照样全过。
- 原因：没有测试覆盖「审核调用抛出未分类异常」。
- 要补：审核的 `run_brain` 抛 `RuntimeError("含上游素材的正文")` 时，断言：
  - 试拆主结果完整，两种模式的 shots 都在；
  - 该模式 `review.status == "uncertain"`；
  - `review.summary` 里不含异常正文。

agent B 补完后同样要自测：把 M6、M7 两个变异逐一打进去，测试必须变红；然后还原。

## 规则

- 白名单只有上面两个测试文件，加上报告 `docs/tasks/2026-10-18-studio-wo3e-director-kb/05-report-g1.md`。
- 实现文件与其他测试一字不改。
- 禁止联网、读取 `.env`、读取或打印 Key、提交。
- 主代理最后跑 `cd backend && <Python> -m pytest -q tests/ -k studio`，给出 passed / failed / skipped 数。

## 最终回复

- 拆分表
- 每条怎么补的
- 三处变异的自测结果
- 门禁数字
