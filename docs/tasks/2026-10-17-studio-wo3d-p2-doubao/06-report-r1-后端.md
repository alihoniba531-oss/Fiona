# WO3d-P2 小返修 R1 后端块报告

- 范围：`05-fix-r1.md` 后端块 1–3。
- 未联网、未读 `.env`、未提交。

## 改动文件

- `backend/studio/providers/tts_doubao.py`
- `backend/studio/casting_jobs.py`
- `backend/tests/test_studio_media_tts_doubao.py`
- `backend/tests/test_studio_casting_jobs.py`

## 逐项对应

### 1. error_code 不再原样存上游内容

- 新增 `_error_code()`：只接受 1–10 位纯数字，生成 `doubao_<数字>`；其他任何值（含非数字、超长数字、空值走 HTTP 语义码的路径）统一记 `doubao_unknown`。
- `_http_error()` 与 `_code_error()` 都改为通过 `_error_code()` 生成落库 code；45 开头的 8 位数字仍按 `rejected` 分类，分类判断使用原始 code，不受脱敏影响。
- `_redact()` 在原有 Key 脱敏之后统一截断到 200 字，`message` 继续脱敏。
- 对应测试：
  - `test_invalid_upstream_code_becomes_doubao_unknown`（4 组非数字/小数/11 位数字）
  - `test_rejected_message_is_redacted_and_truncated_to_200`
  - 既有数字 code 用例继续断言 `doubao_45000010`、`doubao_55001309` 等。

### 2. 发送前的错误记为 rejected

- `synthesize_doubao()` 在进入网络调用前完成 direction / pitch 校验和请求体构造；请求体构造失败（如 `rate=NaN`）现在直接抛 `ValueError`，不再被兜底异常吞成 `doubao_error`（uncertain）。
- `casting_jobs._run_tts()` 只把「合成调用本身」包在 `try` 里，捕获 `TypeError` / `ValueError` 并转成 `PreflightError("invalid_parameters", ...)`：
  - direction 超长、pitch 越界、rate 等脏数据在 POST 前失败；
  - `_process_voice()` 在付费调用之后执行的逻辑不在这个捕获范围内，仍保持原有分类。
- `PreflightError` 经 `_classify()` 记为 `rejected`，由状态转换释放预留。
- 对应测试：
  - `test_invalid_rate_is_a_pre_send_error`（适配器层：`ValueError`，0 次请求）
  - `test_doubao_pre_send_error_is_rejected_without_post`（任务层：direction 超长 / pitch 越界 / rate 非数字三组；断言 POST 次数为 0、`status=rejected`、`error_code=invalid_parameters`、`actual_amount=0`、`reserved_amount=0`）

### 3. uncertain 提示语统一

- `_code_error()` 与 `_http_error()` 的 uncertain 分支统一使用 `base.UNCERTAIN_MESSAGE`（即 `tts_cosy.py` 使用的既有常量），不再拼接上游 message，删除 `_redact(message) or UNCERTAIN_MESSAGE` 的永不生效兜底。
- 上游 message 只保留在 `rejected` 分支，并继续脱敏 + 截断。
- 对应测试：`test_uncertain_message_is_shared_constant`（HTTP 500 与响应体 55001309 两路，断言 message 等于常量而不是上游原文）。

## 测试结果

先写测试并在旧代码上运行，确认失败：

- 新增用例共 11 条失败（4 组 code 用例 + 脱敏截断 + 2 组 uncertain + 适配器预发送 + 3 组任务层预发送）。

修改后：

- `pytest -q tests/test_studio_media_tts_doubao.py tests/test_studio_casting_jobs.py` → `77 passed`
- `pytest -q tests/ -k studio` → `1670 passed, 5550 deselected, 32 warnings`（warnings 均为既有 slowapi/asyncio 弃用告警）

## 未完成项

无。
