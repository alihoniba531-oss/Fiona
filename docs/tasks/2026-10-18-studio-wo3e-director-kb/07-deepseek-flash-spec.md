# WO3e 增补 X7：工作室的 DeepSeek 导演可选 V4.1 Flash（L2，涉及计费）

- **作者要求**（2026-10-18）：阶段三验收试拆的导演用 DeepSeek Flash。作者另外指出，目前 Flash 的能力强过 Pro，所以**工作室的 DeepSeek 默认改为 Flash**，Pro 保留为可选。
- **现状事实**：
  - `backend/studio/brain.py` 的 `DeepSeekProvider.model` 写死为 `"deepseek-v4-pro"`，`provider_options` 里同样写死。
  - `backend/studio/cross_review.py:9` 和 `backend/studio/kb_trial.py:37` 的 `DEFAULT_MODEL` 也写死了它。
  - `backend/studio/pricing.py` 的 `BRAIN_PRICES` 没有 `deepseek-flash`。
  - DeepSeek 官方 `/models` 只列出两个模型：`deepseek-flash`（由 V4.1-Flash 提供服务）和 `deepseek-v4-pro`。

## 1. 要做的

1. **新增配置项**：在 `backend/studio/config.py` 的 `Settings` 里加 `deepseek_model`。
   - 来源是环境变量 `FIONA_STUDIO_DEEPSEEK_MODEL`。
   - 只允许 `deepseek-flash` 和 `deepseek-v4-pro` 两个值，**默认 `deepseek-flash`**。
   - 改默认后，如果 `4b45346` 里已有的测试因为断言旧默认值 `deepseek-v4-pro` 而失败，**不要改那些测试**，停下来在报告里列出测试名与断言原文，由主控裁定。只用假 provider 或假选项列表、自带 model 字符串的测试不受影响。
   - 遇到非法值，照 `_brain_default` 的写法调 `_warn`，并回落到默认值 `deepseek-flash`。
2. **所有写死 `deepseek-v4-pro` 的地方都改为读这个配置**：
   - `DeepSeekProvider` 的实际请求 model；
   - `provider_options` 返回的 model；
   - `cross_review` 与 `kb_trial` 的 `DEFAULT_MODEL`，以及报价、预留、结算用到的 model。
   - 不要只改这里列出的几处：在 `backend/studio/` 里全量搜索 `deepseek-v4-pro`，逐处判断是否应改为读配置，并在报告里列出每一处的处理结果。
   - `backend/` 下非 studio 的代码，例如聊天、BYOK、小说工坊，**一律不动**。
3. **单价**：在 `BRAIN_PRICES` 里加 `"deepseek-flash": ("CNY", "2", "8", "0.04")`。
   - 注释写明：按官方高峰价取上界，空闲价为 1 / 4 / 0.02，高峰翻倍；待作者对账。
   - 仍然可以用 `FIONA_STUDIO_PRICE_DEEPSEEK_FLASH` 覆盖。
4. **文档**：在 `backend/.env.example` 和 `CLAUDE.md` 的短片工作室段各加一行，说明 `FIONA_STUDIO_DEEPSEEK_MODEL` 的取值与默认值。

## 2. 白名单

- 改：
  - `backend/studio/config.py`、`backend/studio/brain.py`、`backend/studio/pricing.py`、`backend/studio/cross_review.py`、`backend/studio/kb_trial.py`
  - `backend/.env.example`、`CLAUDE.md`
- 新建：
  - `backend/tests/test_studio_deepseek_model.py`
- 可改（仅限上文所述的默认 model 断言）：`backend/tests/test_studio_kb_api.py`、`backend/tests/test_studio_cross_review.py`
  - 报告 `docs/tasks/2026-10-18-studio-wo3e-director-kb/07-report-x7.md`
- 如果第 1 节第 2 条的全量搜索发现 `backend/studio/` 里还有别的文件写死了这个 model，停下来在报告里说明，不要自行扩大白名单。

## 3. 测试（新文件，全离线，用 MockTransport 或 monkeypatch）

- 不设环境变量，或设为 `deepseek-flash`：
  - provider model 为 `deepseek-flash`；
  - 一次真实的 `run_brain`（provider 为 deepseek）发出的请求体里 `model == "deepseek-flash"`；
  - `provider_options` 显示 `deepseek-flash`；
  - 试拆报价中导演行按 flash 单价计。断言金额等于用 flash 单价算出的值，并且不等于 v4-pro 单价算出的值。
  - 导演为 deepseek、审核为 deepseek 时，审核行同样用 flash。
- 设为 `deepseek-v4-pro`：provider 与 `provider_options` 都是 v4-pro，报价按 v4-pro 单价计。
- 设为非法值 `deepseek-chat`：回落到 `deepseek-flash`，并且发出告警。
- **既有测试（`4b45346` 里已有的）一字不许改。**
- 本期 WO3e 新建的 `test_studio_kb_api.py`、`test_studio_cross_review.py` 里，凡是把 `deepseek-v4-pro` 当作「DeepSeek 默认 model」写死的断言，可以改为读配置或改成 `deepseek-flash`。这两个文件因此加入白名单，报告里要逐处列出。

## 4. 门禁

- `cd backend && env -u NO_PROXY -u no_proxy <Python> -m pytest -q tests/ -k "studio or deepseek or byok or exchange"`：0 failed、0 skipped。
- 自测变异 2 处，确认变红后还原：
  - 把 `DeepSeekProvider` 改回写死 `deepseek-v4-pro`，默认用例应当变红；
  - 删掉 `deepseek-flash` 的单价行。

## 5. 执行约定

- 本单只有一组文件，不必并行。直接自己完成，不得调用 subagent / subagent_fork / workflow。
- 遇到影响「实现什么」的矛盾才停下来问。你实测到的事实优先于本规格的断言，不符时停下来说明。
- 禁止联网、读 `.env`、读或打印 Key、提交。

## 6. 报告

写到 `07-report-x7.md`，五项：
1. 改了哪些文件，附行号；
2. 实现了什么；
3. 与第 1–4 节的逐条对应；
4. 测试与变异结果；
5. 全量搜索 `deepseek-v4-pro` 的逐处处理表。
