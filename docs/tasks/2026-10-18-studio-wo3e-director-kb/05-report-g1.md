# WO3e 门禁返修 G1 报告：补 3 处存活变异的测试

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- 任务：只补测试，不改实现；补 M2、M6、M7 三处存活变异对应的测试缺口。
- 结果：三处变异均已能被新增测试杀死；实现文件恢复后 sha256 与返修前一致。

## 1. 拆分表

| 块 | 白名单 | 结果 |
|---|---|---|
| A：M2 预算兜底 | 只改 `backend/tests/test_studio_kb_core.py` | ✅ 新增 2 个测试（含 1 个参数化 600/5000 用例）；M2 变红 |
| B：M6/M7 审核路由与异常 | 只改 `backend/tests/test_studio_cross_review.py` | ✅ 新增 4 个测试 + 1 个试拆夹具；M6、M7 均变红 |

报告由主控汇总写入本文件；两个 agent 均未创建/修改报告。

## 2. 每条怎么补的

### G1-1（变异 M2 存活）

- **补的测试 1**：`test_tiny_budget_text_keeps_all_three_base_cards`，参数化 `budget_chars=600` 和 `5000`，用 `position="opening"` 取材料，断言：
  - `result["position"]["id"] == "scene-opening-hook"`；
  - `result["chars"] == len(result["text"]) <= budget_chars`；
  - `result["text"]` 同时含 template、position、model 三张卡的 `【id】` 渲染标识。
- **补的测试 2**：`test_tiny_budget_fallback_compose_keeps_three_base_card_groups`，monkeypatch `retrieval._compose` 记录每次调用的 blocks 组，调用 `budget_chars=600`，断言：
  - 倒数第二次调用是兜底调用，兜底有 3 个非空组，分别含 template、position、model 三张卡的 `【id】`；
  - 其余调用固定为 6 组；
  - 进入兜底时 `grammar`、`negatives`、`exemplars` 已全部为空。
- **为什么需要第 2 个测试**：`select_materials` 在循环结束后会用同一批 `blocks` 重新拼一次 `text`。只把兜底行改成 `text = _compose([model_blocks])` 时，循环内临时 `text` 变了，但最终返回值仍由 compact 的 template/position/model 三组重拼，公开返回值不变。因此单靠返回值 `text` 断言杀不掉 M2；必须用 `_compose` 调用记录观察兜底分支本身。实测兜底分支当前传 3 组（不是 6 组），测试按 3 组或 6 组兼容，但要求恰有 3 个非空组；M2 会产生 1 组，测试变红。

### G1-2（变异 M6 存活）

- **补的测试 1**：`test_review_qwen_uses_dashscope_with_real_run_brain`，直接调用 `cross_review.review(provider="qwen")`，不 monkeypatch `cross_review.run_brain`，走真实 `run_brain` → `brain.get_provider` → `QwenProvider` + `httpx.MockTransport`。断言：
  - 审核请求 host 为 `dashscope.aliyuncs.com`，path 为 `/compatible-mode/v1/chat/completions`；
  - 请求体 `model == "qwen3.8-max"`；
  - `result["status"] == "succeeded"`；
  - DeepSeek 假 provider 没有收到调用（`state["director_calls"] == 0`）。
- **补的测试 2**：`test_trial_sends_two_shot_plans_to_director_and_two_reviews_to_qwen`，跑完整试拆（deepseek 导演 + qwen 审核），断言 DeepSeek 只收到 2 次 `shot_plan`、0 次 `cross_review`；DashScope 收到 2 次审核请求且 model 均为 `qwen3.8-max`。
- **架构事实**：`kb_trial._run_trial` 的审核执行走 `brain_jobs._background` → `brain_jobs.run_brain`，不经过 `cross_review.review()`；因此完整试拆测试不能单独杀死 M6。直接调用 `review()` 的测试才是 M6 的杀手，完整试拆测试用于覆盖任务要求的场景。

### G1-3（变异 M7 存活）

- **补的测试 1**：`test_review_unclassified_exception_is_fixed_uncertain`，monkeypatch `cross_review.run_brain` 抛 `RuntimeError("含上游素材的正文")`，断言：
  - `status == "uncertain"`、`verdict is None`、`issues == []`；
  - `summary` 不含异常正文；
  - `model == "qwen3.8-max"`。
- **补的测试 2**：`test_trial_keeps_shot_results_when_review_raises`，完整试拆中让 qwen 审核 provider 在真实 `run_brain` 内抛未分类 `RuntimeError`；断言两种模式的 shots 都完整、主结果 succeeded、两份 review 均为 `uncertain`、summary 不含异常正文。
- **环境夹具**：B 在测试文件末尾追加了一个 autouse 的 `_strip_bracketed_no_proxy`，只移除本机 `NO_PROXY` 里带方括号的 IPv6 写法（如 `[::1]`），不改代理地址、不改既有测试的输入/断言/夹具；干净环境中为 no-op。该夹具不参与 M6/M7 的变异路径。

## 3. 三处变异自测结果

| 变异 | 手动改法 | 新增测试结果 | 还原后 sha256 |
|---|---|---|---|
| M2 | `text = _compose([template_blocks, position_blocks, model_blocks])` → `text = _compose([model_blocks])` | **变红**：`1 failed, 2 passed, 35 deselected`；失败点是兜底调用只有 1 组 | `040452f477e9752ea87bd63e579762c4b053dd0b70a700f25c4d50a80e2d42a4` |
| M6 | `run_brain("cross_review", …, provider=provider, …)` → `provider="deepseek"` | **变红**：`1 failed`；`result["status"]` 从 `succeeded` 变成 `uncertain`，DashScope 未收到请求 | `85862e4dd3a2347c46d1a125116be80afc1e18a2c635c63e2ac4992a10b53231` |
| M7 | `except Exception:` → `except ZeroDivisionError:` | **变红**：`1 failed`；`RuntimeError: 含上游素材的正文` 直接冒出 | 同上 |

- 三处变异均已手动打入并确认变红，随后逐一还原。
- `retrieval.py`、`cross_review.py`、`kb_trial.py`、`brain_jobs.py` 最终 sha256 与返修前完全一致；未修改任何实现文件。
- 两张样卡、其他既有测试、白名单外文件均未改动。

## 4. 门禁数字

- 完整门禁：`cd backend && <Python> -m pytest -q tests/ -k studio`
  → **1765 passed, 5550 deselected, 32 warnings in 74.92s**
  （0 failed / 0 skipped；比返修前 1758 增加 7 个新用例）。
- 两个改动文件单独跑：
  `pytest -q tests/test_studio_kb_core.py tests/test_studio_cross_review.py`
  → **48 passed, 32 warnings in 3.95s**（0 failed / 0 skipped）。
  - `test_studio_kb_core.py`：38 passed（新增 3 个用例，其中参数化算 2 个）。
  - `test_studio_cross_review.py`：10 passed（新增 4 个用例）。
- 本机 `NO_PROXY` 含非法条目 `[::1]`，会让 httpx 在 `main` 导入时抛 `InvalidURL`；门禁命令在把 `NO_PROXY` 设为合法值后运行，未改仓库配置。B 的测试文件内另有上文所述的环境夹具。

## 5. 未完成或需要人工确认

- **M2 是返回值等价变异**：只改兜底行的临时 `text`，最终返回值仍由 compact 三组重拼，所以公开 `text` 断言无法单独杀死它；新增的 `_compose` 调用记录测试是必要的，但它观察的是内部调用形状，后续若重构 `_compose` 需同步调整。
- **M6/M7 位于 `cross_review.review()`，而试拆执行路径不调用该函数**：因此新增了直接 `review()` 测试；完整试拆场景测试也已覆盖，但它本身不能杀死 M6/M7。若后续 WO4 让试拆改走 `review()`，这组测试会自然覆盖到。
- **试拆级 M7 测试的稳定性**依赖 `run_brain` 在 job running 后捕获异常并把 job 落为 `uncertain`；当前实现如此，测试已稳定通过。若未来 `brain_jobs` 的异常映射改变，需要同步复核该断言。
- **环境夹具**：`_strip_bracketed_no_proxy` 只为本机既有 `NO_PROXY` 问题服务，不改变实现行为；如作者不希望测试触碰环境变量，可在干净环境中删除该夹具，删除后新测试仍应通过。
- 前端 tsc/lint 未重跑：本轮未改任何前端文件。
- 白名单核对：本轮实际改动只有 `backend/tests/test_studio_kb_core.py`、`backend/tests/test_studio_cross_review.py` 与本报告；同目录的 `05-gate-fix-r1.md` 是主控派单原文（07:00 已存在），未修改。实现文件 sha256 与返修前一致。
