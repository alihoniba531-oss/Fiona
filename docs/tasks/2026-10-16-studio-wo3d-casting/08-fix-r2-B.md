# R2-B 适配器与提示词（先读 08-fix-r2-common.md）

## 只许改的文件
- `backend/studio/providers/tts_cosy.py`
- `backend/studio/providers/tts_edge.py`
- `backend/studio/providers/image_seedream.py`
- `backend/studio/casting_prompts.py`
- 测试：`backend/tests/test_studio_media_tts.py`、`test_studio_media_seedream.py`、`test_studio_casting_prompts.py`

## 要修的项

### 必须修复 3：错误分类只看结构化状态码
- 删掉 `_status_code` 等函数里用正则扫异常文本找 4xx 的逻辑，`_failure_from_message` 对 dict 整体 `str()` 的做法也一并去掉。
- 只采信结构化字段：异常对象上的数值属性 `status_code` / `status`，或上游响应里明确的数值状态码字段。
- 其余一律按 uncertain 处理（`MediaCallError` 对应的分类）。审核拦截的语义码维持现状。
- 测试至少覆盖以下几种情况，结果都必须是 uncertain：
  - `ConnectionError("Cannot connect to host x:443 ...")`
  - `OSError("... wss://dashscope.aliyuncs.com:443/ ...")`
  - edge-tts / aiohttp 风格的连接错误
  - 带有 `:443` 字样的 `task-failed` 文本
- 另加一组测试：带真实数值 `status=429` 和 `status=400` 的异常，结果仍是 rejected。

### 可优化 g（前半）：Seedream 加总超时
- 给 `generate_sheet` 加整体超时，常量 `TOTAL_TIMEOUT_S = 240`，测试可以改小。
- 超时视为 uncertain。

### 可优化 h：CosyVoice 超时后不能再发付费请求
- 现状：`wait_for` 超时只取消了等待，后台线程还在排队等锁，拿到锁后仍会发出付费请求。
- 改法：线程在拿到锁之后、调用 SDK 之前，检查取消标志（例如 `threading.Event`），已取消就直接返回，不调用 SDK。
- 测试：用假 factory 和一把预先占住的锁，构造超时场景，断言 SDK 调用次数为 0。

### 可优化 m（后半）：提示词总长永远不超过 1800
- `build_sheet_prompt` 在任何输入下返回的提示词都不超过 1800 字。
- 裁剪顺序：先裁 `extra_prompt`，再裁 `description` 尾部，再裁风格段尾部，最后裁 `appearance` 尾部。
- 版式、主体名称、`locked_features`（上限 600 字，由 R2-A 在 PATCH 处校验）、负向约束、原创声明这几部分绝不裁。
- 测试：用 600 字的 locked_features 加上超长的风格和外形，断言结果不超过 1800，且 locked_features 完整保留。

## 验证
```
cd backend && <py> -m pytest -q tests/test_studio_media_tts.py tests/test_studio_media_seedream.py tests/test_studio_casting_prompts.py
cd backend && <py> -m pytest -q tests/ -k studio
```
