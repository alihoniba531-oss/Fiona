# WO3e 增补 X7 报告：工作室 DeepSeek 导演可选 V4.1 Flash

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- 规格：`docs/tasks/2026-10-18-studio-wo3e-director-kb/07-deepseek-flash-spec.md`
- 结论：工作室 DeepSeek 默认模型改为 `deepseek-flash`，`deepseek-v4-pro` 保留为可选；配置、请求、provider 选项、试拆报价/预留/结算均读配置；flash 单价已补；文档已补。未改任何既有测试。

## 1. 改了哪些文件（附行号）

| 文件 | 行号 | 改动 |
|---|---|---|
| `backend/studio/config.py` | 89、114、127-132 | `Settings.deepseek_model`；`get_settings()` 读取 `_deepseek_model()`；默认 `deepseek-flash`，只允许 `deepseek-flash` / `deepseek-v4-pro`，非法值 `_warn` 后回落 `deepseek-flash` |
| `backend/studio/brain.py` | 379-381、467-468、475、506-511 | `QwenProvider` 校验允许子类 `allowed_models`；`DeepSeekProvider` 类默认改 `deepseek-flash`、允许两值；实例 `model` 读配置；`provider_options` 的 DeepSeek model 读配置 |
| `backend/studio/pricing.py` | 143-145 | 新增 flash 单价 `("CNY", "2", "8", "0.04")` 与高峰价注释；Pro 价目保留 |
| `backend/studio/cross_review.py` | 6、10-16、64 | `DEFAULT_MODEL` 只留 qwen；新增 `_default_model`，DeepSeek 读配置；`_expected_model` 使用它 |
| `backend/studio/kb_trial.py` | 19、38-44、447 | 引入 `get_settings`；`DEFAULT_MODEL` 只留 qwen；`_default_model` 的 DeepSeek 读配置；`_require_option` 的 model 回退使用它 |
| `backend/.env.example` | 218、231 | 新增 `FIONA_STUDIO_DEEPSEEK_MODEL=deepseek-flash` 说明；补 `FIONA_STUDIO_PRICE_DEEPSEEK_FLASH` 覆盖示例 |
| `CLAUDE.md` | 192 | 短片工作室段新增 DeepSeek 模型配置说明（取值、默认 flash、非法回落、只作用于工作室） |
| `backend/tests/test_studio_deepseek_model.py` | 新建，6 个测试函数（参数化后 7 项） | 默认/显式 flash、显式 Pro、非法回落告警、真实 `run_brain` 请求体、报价按模型计价、flash 价目覆盖 |
| `docs/tasks/2026-10-18-studio-wo3e-director-kb/07-report-x7.md` | 新建 | 本报告 |

未修改 `backend/tests/test_studio_kb_api.py`、`backend/tests/test_studio_cross_review.py`（原因见第 5 节）；未修改任何 `4b45346` 已有测试；未改 `backend/` 下非 studio 代码。

## 2. 实现了什么

- `FIONA_STUDIO_DEEPSEEK_MODEL` 新增为工作室配置，默认 `deepseek-flash`，可选 `deepseek-v4-pro`；每次 `get_settings()` 调用时读取，非法值只告警一次并回落默认。
- `DeepSeekProvider` 的实际请求 model 从配置读取；`provider_options` 对 DeepSeek 返回配置 model；`cross_review._expected_model` 与 `kb_trial._require_option` 的默认 DeepSeek model 也从配置读取。试拆报价、预留、结算都使用报价时锁定的 item model，模型来源即 `provider_options`。
- `BRAIN_PRICES` 新增 `deepseek-flash`，仍支持 `FIONA_STUDIO_PRICE_DEEPSEEK_FLASH` 覆盖。
- 文档补充取值与默认值；默认 flash 不会改变前端、数据库或非工作室 DeepSeek 配置。

## 3. 与第 1–4 节的逐条对应

1. **配置项**：`config.py:89,114,127-132`；默认 `deepseek-flash`；只允许两值；非法值 `_warn("FIONA_STUDIO_DEEPSEEK_MODEL")` 后回落默认。既有测试未因默认值改变而失败，因此没有测试需要主控裁定。
2. **所有写死点**：`grep -rn "deepseek-v4-pro" backend/studio --include='*.py'` 仅剩 3 处，逐处处理见第 5 节；`DeepSeekProvider` 实际请求、`provider_options`、`cross_review`/`kb_trial` 的默认 model 与报价/预留/结算链路都读配置。
3. **单价**：`pricing.py:143-145`；flash 单价 `("CNY", "2", "8", "0.04")`，注释写明高峰上界、空闲 1/4/0.02、高峰翻倍、待对账；覆盖变量可用（有测试）。
4. **文档**：`backend/.env.example:218,231`；`CLAUDE.md:192`。

## 4. 测试与变异结果

### 新测试（全离线，MockTransport / monkeypatch）

`backend/tests/test_studio_deepseek_model.py` → **7 passed, 0 failed, 0 skipped**（32 warnings，slowapi 既有弃用告警）：

- `test_configured_model_is_used_by_provider_and_options[deepseek-flash]`
- `test_configured_model_is_used_by_provider_and_options[deepseek-v4-pro]`
- `test_default_deepseek_model_is_flash`
- `test_invalid_deepseek_model_warns_and_falls_back`
- `test_flash_price_can_be_overridden`
- `test_run_brain_deepseek_posts_default_flash_model`
- `test_quote_prices_director_and_review_with_configured_model`

其中：
- 真实 `run_brain`（provider=deepseek）经 `DeepSeekProvider` + `httpx.MockTransport`，断言实际请求体 `model == "deepseek-flash"`，响应 model 也是它。
- 报价测试同时跑 flash 与 Pro：四个 item 的 model 分别为 `deepseek-flash` / `deepseek-v4-pro`；导演行 `amount` 等于对应单价的 `estimate_brain + estimate_brain_repair`，flash 金额不等于 Pro 金额；审核行 model 与金额也随配置变化；公开报价的 `est` 与合计一致。
- 非法值测试断言 `_warn` 只收到 `FIONA_STUDIO_DEEPSEEK_MODEL`，配置回落 flash。

### 变异自测（均已变红并还原）

| 变异 | 目标测试 | 结果 | 还原后 sha256 |
|---|---|---|---|
| `DeepSeekProvider` 改回 `model="deepseek-v4-pro"` | `test_default_deepseek_model_is_flash` | **红**：`assert 'deepseek-v4-pro' == 'deepseek-flash'` | `fb5113cf26c82abc435ed04510ebf0023d562a11fb8781eb7dc9e55f050086ab`（brain.py） |
| 删除 `"deepseek-flash": (...)` 单价行 | `test_quote_prices_director_and_review_with_configured_model` | **红**：`HTTPException 409: 模型 deepseek-flash 单价未配置` | `c58a5a3984bb17003dbdddde1cd3ec72be9336603d7f639ee0abfe95f37f5ff9`（pricing.py） |

两个变异均逐一打入、确认变红后还原；还原后 sha256 与变异前一致。

### 门禁

- `cd backend && env -u NO_PROXY -u no_proxy <Python> -m pytest -q tests/ -k "studio or deepseek or byok or exchange"`
  → **2747 passed, 4598 deselected, 32 warnings in 137.72s**（0 failed / 0 skipped）。
- 新测试文件单独：**7 passed**。
- 本机 `NO_PROXY` 含 `[::1]`，按本单要求用 `env -u NO_PROXY -u no_proxy` 运行；未改仓库配置。

## 5. 全量搜索 `deepseek-v4-pro` 的逐处处理表

### `backend/studio/`（Python；`__pycache__` 二进制忽略）

| 位置 | 当前用途 | 处理 |
|---|---|---|
| `studio/config.py:129` | `_deepseek_model()` 的允许值集合 `{"deepseek-flash", "deepseek-v4-pro"}` | **保留**：这是合法取值枚举，不是默认选择；默认与回落均为 flash |
| `studio/brain.py:468` | `DeepSeekProvider.allowed_models` | **保留**：允许 Pro 作为可选项；类默认 `model` 已改为 flash，实际实例 model 读配置 |
| `studio/pricing.py:145` | Pro 的价目 `("CNY","2","3","2")` | **保留**：Pro 仍可选，结算需要价目；不是默认 model |
| 其他 studio Python 文件 | 无 `deepseek-v4-pro` | 无需改 |

补充说明：`DeepSeekProvider.model` 类属性已改为 `deepseek-flash`；实际请求 model 来自 `get_settings().deepseek_model`，不是类属性。

### 本期 WO3e 新建测试中的硬编码（未改，原因如下）

| 位置 | 用途 | 处理 |
|---|---|---|
| `tests/test_studio_kb_api.py:71,132` | 假 `provider_options` / 假 Adapter 的 DeepSeek model | **未改**：这是测试自带的假 provider 选项，不是默认 model 断言；真实默认由 `test_studio_deepseek_model.py` 覆盖。门禁通过 |
| `tests/test_studio_cross_review.py:176,179` | 假 `provider_options` 与假 Director 的 model | **未改**：同上，假 provider 自带 model；不影响真实配置路径。门禁通过 |

`4b45346` 已有测试中的 `deepseek-v4-pro` 也都是假 options/假 provider 或 fixture 数据，不是默认值断言；按「既有测试一字不许改」全部未动，门禁通过。

### 非 studio

- `backend/` 下聊天、BYOK、小说工坊的 `deepseek-v4-pro` / `deepseek-flash` 引用一律未动（例如 BYOK 原生工具精确型号、`tests/test_novel_deepseek_flash.py`），符合本单「非 studio 不动」。
- `backend/.env.example` 中 BYOK/小说工坊的 Pro 示例未动；只新增工作室配置与 flash 覆盖示例。
- `CLAUDE.md` 中其他 DeepSeek 说明未动；只在短片工作室段新增一行。
