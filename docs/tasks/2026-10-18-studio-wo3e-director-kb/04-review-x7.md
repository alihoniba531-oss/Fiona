# 独立复核：WO3e 增补 X7（工作室 DeepSeek 默认改为 Flash，L2，涉及计费）

- 复核对象：`.review/x7.diff`（本轮增量）；规格 `07-deepseek-flash-spec.md`；实现方报告 `07-report-x7.md`（仅作线索，全部事实独立重测）。
- 复核环境：专用副本 = 基线 `4b45346`（git HEAD）+ 全部待审改动。开始时对 backend 全部 407 个源文件（`*.py` + `.env.example`，排除 `__pycache__`）建 sha256 清单；结束时复验 **407/407 一致**，`git status --porcelain` 33 条与开始时逐条一致。临时文件全部在 `/tmp/review-x7-work/`。
- 完整性前置验证：`git apply --check --reverse .review/x7.diff` → **clean**，即工作树与 x7.diff 后像逐字节一致，diff 没有隐藏未落盘的改动。
- 另注：x7.diff 含规格文档自身的修订（默认值由 Pro 改 Flash、白名单加两个测试文件），与规格首行所述作者 2026-10-18 新要求一致，属主控派单动作，不计为实现方越权。

## 1. 结论

**通过。**

- 规格第 1–4 节逐条达标；门禁 2747 passed / 0 failed / 0 skipped；3 处变异全部变红且已还原、字节级复原。
- 无必须修复项。
- 4 条可优化项，其中第 1 条（`backend/scripts/studio_brain_eval.py` 的报价模型与新默认脱节，涉及手动评测工具的花费授权口径）**建议主控另开跟进单**；该文件在本单白名单与搜索范围（`backend/studio/`）之外，规格明令非 studio 代码一律不动，故不构成 X7 的不合规。

## 2. 逐条核验（附证据）

### 2.1 配置项：默认 flash、Pro 可选、非法回落并告警（规格 §1.1）

| 项 | 证据 |
|---|---|
| `Settings.deepseek_model` 字段 | `backend/studio/config.py:89`；接线 `config.py:114` `deepseek_model=_deepseek_model()` |
| 默认 `deepseek-flash`，只允许两值 | `config.py:127-130`：`os.getenv("FIONA_STUDIO_DEEPSEEK_MODEL", "deepseek-flash")`，白名单集合 `{"deepseek-flash", "deepseek-v4-pro"}` |
| 非法值 `_warn` 后回落 flash | `config.py:131-132`，与 `_brain_default`（`config.py:119-124`）写法完全同款（含 `_warn` 每进程一次，`config.py:21-24`）；空串同样按非法回落 |
| 调用时读取 | `get_settings()` 无缓存，每次构造（`config.py:100-116`） |
| v4-pro 仍可选 | 配置白名单（上）+ `brain.py:468` `allowed_models = ("deepseek-flash", "deepseek-v4-pro")` + `pricing.py:145` Pro 价目保留 |
| 测试 | `tests/test_studio_deepseek_model.py::test_default_deepseek_model_is_flash`、`test_configured_model_is_used_by_provider_and_options[deepseek-flash]/[deepseek-v4-pro]`、`test_invalid_deepseek_model_warns_and_falls_back`（断言 `_warn` 恰收到 `FIONA_STUDIO_DEEPSEEK_MODEL` 且回落 flash）。单文件 **7 passed** |

**既有测试未因改默认而失败**（规格 §1.1 的「停下裁定」条款无需触发）：门禁 0 failed 即为独立证据；另抽查基线测试中全部 `deepseek-v4-pro` 出现处，均为假数据而非真实默认断言——`test_studio_brain_r1_provider.py:19/32/127`（假响应体自带 model）、`test_studio_brain_r2_provider.py:129`（假 `provider_options`）、`test_studio_breakdown_budget.py:24-27`（monkeypatch 假 options）、`test_studio_probe.py:466`（WO0 探针自有一张固定表）、`test_studio_brain_eval.py:43`（假 `DeepSeekProvider` lambda）、`test_studio_brain_frontend.py:10`（前端假 JSON）。实现方报告「没有测试需要主控裁定」属实。

### 2.2 写死点全部改读配置；请求体 / provider_options / 试拆与审核的报价、预留、结算跟随配置（规格 §1.2）

**改动点核验**（文件:行号为当前工作树）：

- `brain.py:465-470`：`DeepSeekProvider.model = "deepseek-flash"`（类默认）、`allowed_models` 两值；`brain.py:472-476`：实例 model = `get_settings().deepseek_model`（无显式入参时）；`brain.py:379-381`：`QwenProvider` 构造校验并入子类 `allowed_models`（`getattr(..., ())`，Qwen 自身无该属性、行为不变）。
- `brain.py:505-512`：`provider_options` 的 DeepSeek model = `get_settings().deepseek_model`（:506、:511）。
- `cross_review.py:7,10,13-16`：`DEFAULT_MODEL` 只留 qwen，`_default_model("deepseek")` 读配置；`:63-66` `_expected_model` 使用之（仅用于失败记录的展示 model；审核实际计费走 `run_brain`）。
- `kb_trial.py:19,38,41-44`：同款；`:445-448` `_require_option` 的 model 兜底走 `_default_model`。

**运行时链路追踪**（代码级）：

1. 实际请求体：`brain.py:416-421` `body = {"model": model, ...}`。无绑定 job 的 `run_brain`：`brain_jobs.py:272-274` `get_provider → DeepSeekProvider()`（构造即读配置）→ `_quote_item(provider, adapter.model, ...)`。有绑定 job（已报价确认）：`brain_jobs.py:301-303` `adapter.model = job["model"]`——锁定报价时配置，排队后改默认不影响已确认调用（与 WO3a 规则一致）。
2. 试拆报价：`kb_trial.py:451-494` `quote()` → `_options(owner)`（真 `provider_options`，:436）→ `director["model"]`/`reviewer["model"]`（:457-458，配置驱动）→ `_quote_item`/`_review_quote_item`（:475-480；`brain_jobs.py:53-63`、`kb_trial.py:382-388` 按该 model 调 `pricing.estimate_brain*` 计价）。
3. 预留：确认事务 `kb_trial.py:669-685` 用报价 item 调 `brain_jobs._insert_job`（`brain_jobs.py:105-124`）——job 行写 `item["model"]`，预留 `item["first_max"]`（按该 model 的价）。
4. 结算：`brain_jobs.py:325-327` `settle_brain_response(actual_model = reply.model or requested_model, ...)`；`pricing.py:243-251` 按实际响应 model 计价。修正轮 `brain_jobs.py:354-357` 亦按 `requested_model`。
5. 审核行：`kb_trial.py:477-480`（报价）、`:507-515` `_activate_review`（kb_review→brain，model 沿用报价 item）、`:628-639` 执行。导演=deepseek、审核=deepseek 时两行都来自同一配置。
6. 顺带核验同链路的其他工作室计费入口：WO3c 拆解 `breakdown.py:97,657`、WO3d 定妆 `casting.py:384,416,588` 均取 `provider_options` 的 `option['model']`，自动跟随配置；`store.py:207`、`brain_jobs.py:17` 等其余 "deepseek" 出现处均为 provider id，非 model。

**测试证据**：`test_run_brain_deepseek_posts_default_flash_model` 用 `httpx.MockTransport` 截获真实 `run_brain`（provider=deepseek，经 brain_jobs 计费编排）的请求体，断言 `requests[0]["model"] == "deepseek-flash"` 且 `result.model` 一致；`test_quote_prices_director_and_review_with_configured_model` 对 flash/pro 各报一次价，断言 4 个 item 的 model、导演行金额 == 按对应单价独立算出的 `estimate_brain + estimate_brain_repair` 且 flash ≠ pro、审核行 model 与金额随配置变化、公开报价 `est`/`total` 与 item 一致。两案在变异 1/2/3 下分别变红（见 §2.5），证明断言确实由配置驱动。

**全量搜索**（本审自查，命令 `grep -rn "deepseek-v4-pro" backend/studio/`，另查 `deepseek-flash`、`director_kb/`、`prompts/`）——`backend/studio/` 仅剩 3 处，逐处判断：

| 位置 | 内容 | 判断 |
|---|---|---|
| `studio/config.py:129` | 合法取值枚举 `{"deepseek-flash","deepseek-v4-pro"}` | 保留正确（枚举非默认；默认与回落均为 flash，:128/:132） |
| `studio/brain.py:468` | `allowed_models` 元组 | 保留正确（Pro 可选必须过构造校验） |
| `studio/pricing.py:145` | Pro 价目 `("CNY","2","3","2")` | 保留正确（选 Pro 时报价/结算需要） |

`director_kb/`（YAML 卡）与 `prompts/` 无任何 deepseek model 硬编码（`grep -rni deepseek` 零命中）。**无遗漏**，与实现方报告 §5 一致。

**非 studio 未动**：x7.diff 的 backend 文件清单 = `.env.example`（白名单）+ `studio/` 5 文件 + 新建测试文件，别无其他；`routers/studio.py`、`database.py`、`byok/providers.py:14`、`services/chat_service.py:312`、`novel/llm_router.py:38`、`exchange_models.py:28` 等聊天/BYOK/小说工坊/交换的 v4-pro 引用均不在 x7.diff 中（前四者属 WO3e 前期改动，见 wo3e.diff，非本轮）。✔

### 2.3 flash 单价与覆盖（规格 §1.3）

- `pricing.py:143-144`：注释「按官方高峰价取上界；空闲价为 1 / 4 / 0.02，高峰翻倍；待作者对账」+ `"deepseek-flash": ("CNY", "2", "8", "0.04")`——与规格要求的数值、注释要素逐项一致。
- 覆盖机制：`pricing.py:152-154` `brain_price_env("deepseek-flash")` → `FIONA_STUDIO_PRICE_DEEPSEEK_FLASH`；`brain_price`（:157-179）env 覆盖优先于内置价。测试 `test_flash_price_can_be_overridden` 断言覆盖值 `1/4/0.02` 生效（Decimal 精确比较）。`.env.example:231` 有注释示例。✔

### 2.4 文档（规格 §1.4）

- `backend/.env.example:217-218`：说明行（取值、默认 flash、非法回落）+ `FIONA_STUDIO_DEEPSEEK_MODEL=deepseek-flash`；`:231` 价格覆盖示例。
- `CLAUDE.md:192`：短片工作室段一行，含取值、默认、非法回落、「只作用于工作室，不影响聊天、BYOK 与小说工坊」。✔

### 2.5 既有测试一字未改；两个本期新建测试文件的处理

- 基线 `4b45346` 含 `backend/tests/` 文件 251 个（`git ls-tree -r HEAD --name-only backend/tests/ | wc -l`）。与 x7.diff 文件清单 `comm -12` 交集为**空**；与全量 wo3e.diff 交集亦为**空**——任何 diff 都未触碰基线测试。✔
- 本期新建的 `test_studio_kb_api.py`、`test_studio_cross_review.py`：x7.diff **零改动**（「改动只限默认 model 断言」平凡满足；规格措辞为「可改」，不改亦合规）。实地核对其中 4 处 v4-pro：`test_studio_kb_api.py:68-71`（monkeypatch 的假 `provider_options`）、`:130-133`（假 `get_provider` 返回自带 model 的假 Adapter）、`test_studio_cross_review.py:171-176`（假 options）、`:178-179`（假 Director 类属性）——均为「假 provider / 假选项列表、自带 model 字符串」，按规格 §1.1 不受默认值影响，不改是正确判断；实现方报告 §5 已逐处列出，与实测一致。✔
- 新测试文件与 x7.diff「+」侧逐字节一致（awk 抽取后 `diff` 为空，182 行）。✔

### 2.6 门禁（规格 §4）

```
cd backend && env -u NO_PROXY -u no_proxy /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python \
  -m pytest -q tests/ -k "studio or deepseek or byok or exchange"
→ 2747 passed, 4598 deselected, 32 warnings in 135.99s   （0 failed、0 skipped）
```

与实现方报告数字一致。新测试文件单独 `7 passed`（collect-only 名单与报告逐条相同）。

### 2.7 变异 3 处（每处变红后还原，sha256 复验 OK）

| # | 变异 | 结果（红） | 还原校验 |
|---|---|---|---|
| 1 | `config.py:128` getenv 默认值改回 `"deepseek-v4-pro"` | `2 failed, 5 passed`：`test_default_deepseek_model_is_flash`（`assert 'deepseek-v4-pro' == 'deepseek-flash'`）、`test_run_brain_deepseek_posts_default_flash_model` | `7a2e3ccf6c49…` OK |
| 2 | `pricing.py` 删除 `"deepseek-flash": ("CNY","2","8","0.04"),` 行 | `2 failed, 5 passed`：`test_run_brain_deepseek_posts_default_flash_model`、`test_quote_prices_director_and_review_with_configured_model`，均 `HTTPException 409: 模型 deepseek-flash 单价未配置或无效，请设置环境变量 FIONA_STUDIO_PRICE_DEEPSEEK_FLASH` | `c58a5a3984bb…` OK |
| 3 | `brain.py:511` `provider_options` 改回写死 `"deepseek-v4-pro"` | `3 failed, 36 passed`（与 kb_api/cross_review 两文件同跑）：`test_configured_model_is_used_by_provider_and_options[deepseek-flash]`、`test_default_deepseek_model_is_flash`、`test_quote_prices_director_and_review_with_configured_model`；既有 WO3e 测试因用假 options 不受牵连（符合预期） | `fb5113cf26c8…` OK |

备注：变异 2 下 `test_flash_price_can_be_overridden` 仍绿（env 覆盖路径不依赖内置价目行），但同变异被另两案可靠捕获，满足「每处都要让测试变红」。实现方报告自述的还原 sha256（brain.py `fb5113cf…`、pricing.py `c58a5a39…`）与本审实测**完全一致**。全部还原后 `7 passed` 复绿，最终 407/407 清单一致。

## 3. 必须修复项

**无。** 本单范围内（x7.diff 对照规格 §1–§4）未发现阻断性缺陷。

## 4. 可优化项

1. **（建议另开跟进单，涉及计费口径）`backend/scripts/studio_brain_eval.py:23` 与新默认脱节**：`MODELS = {"qwen": "qwen3.8-max", "deepseek": "deepseek-v4-pro"}` 仍写死 Pro，而 `:111` `brain.DeepSeekProvider(api_key=...)` 现在跟随配置（默认 flash）。离线实测：默认配置下 `DeepSeekProvider().model == "deepseek-flash"`，`MODELS['deepseek'] == "deepseek-v4-pro"`；同输入（10000 字 / max_tokens 8192）报价上界 pro ¥0.054576 vs flash ¥0.095536（flash 输出价 8/M 高于 pro 3/M）。失败场景：作者默认配置下跑手动评测，`--yes-spend` 授权上限（`main()`，:236-241）按 Pro 口径计算，不足以覆盖 flash 的最坏情况；生成的评测报告中 plan 行标 `deepseek-v4-pro`、attempt 行显示 `deepseek-flash`，自相矛盾。结算本身仍按实际响应 model 计价（`evaluate`，:161-163），不会错扣，但「先报价后授权」的安全属性失真。**不判为本单不合规**：该文件在 `backend/scripts/`（规格搜索范围是 `backend/studio/`），且规格 §1.2 明令非 studio 代码一律不动、§2 禁止自行扩大白名单。建议改法：`MODELS["deepseek"]` 改读 `get_settings().deepseek_model`，或 `_provider()` 显式传 `model=MODELS[provider]` 使调用与报价一致；`test_studio_brain_eval.py` 补一条「plan model == provider 实例 model」断言（现有测试 :43 用假 Provider，测不出此失配）。
2. **`backend/scripts/_studio_probe_brain.py:18,24`**（WO0 探针钉死 v4-pro 及其价目）：探针自成体系、内部一致，钉死型号属基准可比性的刻意设计，无缺陷；但已不代表工作室默认导演。建议跟进单里一并决定是否补 flash 探测项。
3. **实现方报告 §5「非 studio」小节枚举不全**：只列了聊天/BYOK/小说工坊，未提上述两个 `backend/scripts/` 工作室相关脚本。其「一律未动」的结论仍为真（本审已独立验证），属报告完备性瑕疵，建议补记。
4. **默认价目数值本身无守卫测试**：`test_flash_price_can_be_overridden` 只测覆盖路径，`test_quote_prices…` 的期望值与实现同源自 `pricing.estimate_brain*`；若有人把内置 `("CNY","2","8","0.04")` 的数值改错（而非删行），现有用例不会变红。可加一条 `pricing.brain_price("deepseek-flash") == {"currency":"CNY","input":Decimal("2"),"output":Decimal("8"),"cache_read":Decimal("0.04")}`（无 env 时）的字面断言。非本单规格要求，不阻断。
