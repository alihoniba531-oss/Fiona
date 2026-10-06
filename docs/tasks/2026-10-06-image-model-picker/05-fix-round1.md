# 返修单 第 1 轮：生图模型选择（2026-10-06）

- **依据**：`04-review.md`。Opus 5.5 第 1 次复核结论为通过：唯一一条「必须修复」已降为可优化。主会话从中选出下面几条，这一轮一起修。
- **硬规则**：同 `02-spec.md` 第 3 节，包括已有测试不得修改，默认模型的调用方式与基线逐字一致。
- **白名单**：同 `02-spec.md` 第 3 节，另加 `backend/routers/image_models.py`、`backend/tests/test_image_model_choice.py`。

## 改动

### 1. 修图尺寸（spec-tests MF1、ark O1）

- `_ark_size` 改为：先把比例当作**约束**，再按面积选。
  - 在「均匀缩放后刚好进入范围」的目标面积附近，取宽、高各自就近的 8 的倍数，组成候选（例如 `round(w*s/8)*8` 和 `ceil(w*s/8)*8` 两两组合）；
  - 只保留比例误差 ≤ 1% 且落在 [921600, 2048²] 内的候选；
  - 在剩下的候选里，选面积最接近目标面积的那个。只有找不到满足 1% 的候选时，才放宽到「比例误差最小」。
- **测试**（补进 `test_image_model_choice.py`）：
  - 959×961、1199×767、1001×919、1279×720 缩放后的面积 ≥ 921600，且 ≤ 921600 × 1.1；
  - 已在范围内的尺寸（如 960×960、1536×864）保持原样；
  - 需要缩小时，面积接近上限（≥ 上限 × 0.9）；
  - 输入面积单调增大时，输出面积不减小（抽样检查）。

### 2. 参考图像素上限（spec-tests O2、ark O3、routing O3）

- 删除 `_ark_reference_png_dimensions` 及与之相关的 4000 万像素放宽，方舟路径与 Qwen 路径一样用 `_reference_image_bytes` / `_png_dimensions`（上限 2048²）。
- 同步改正文档里关于这一点的说法。

### 3. 方舟单张图错误（ark O2）

- HTTP 200 但 `data[0]` 里没有 `b64_json`、却带 `error` 时，用 `_ark_error(status, data[0])` 映射。审核类 code 要给出审核文案。
- 补测试。

### 4. 排查日志（ark O5、routing O1）

- 方舟请求失败时，打印一行 `[image] provider=ark status=<HTTP 状态> code=<code>`。
  - code 只保留 `[A-Za-z0-9._-]` 字符，最多 80 字；
  - 不打印 message、请求 ID、提示词或密钥。
- 同时把这次失败的 `provider_status` 和 `provider_code`（同样经过清洗）写进 trace，例如通过 `ImageGenerationError` 携带的属性传出，让 `chat_service` 写入 `state.trace`。
- 补测试：日志和 trace 都有 status 与 code，而且不含原文 message。

### 5. 重试使用当前选择（frontend O3、routing O2）

- 「重新生成」改为用**当前界面选中的模型**（`imageModel`），不再固定用失败时记下的模型。
  - 重试请求里，描述、比例、参考图照旧沿用记下的值；
  - `ImageGenerationRetry.imageModel` 可以保留作记录，也可以删掉。
- 按钮的 `title` 改为「使用相同的描述和比例，以当前选择的模型重新生成」。
- 在报告里说明这一处对 `02-spec.md` §4.4 的修改，以及理由：失败提示让用户改选 Qwen，重试时应当尊重这个改选。

### 6. 不覆盖用户偏好（frontend O2）

- 服务端返回某模型 `available=false` 导致自动切回默认时，只改界面状态，不改写 localStorage。只有用户自己点按钮，才写入 localStorage。
- 之后管理员配好密钥、该模型重新可用时，界面恢复为用户原先保存的选择。

### 7. 小整理

- 两处模型按钮组抽成一个局部渲染片段（frontend O1）。
- `ImageGenerationRetry.imageModel` 的类型改用 `ImageModelId` 联合类型（frontend O5）。
- `/image-models` 路由加上 `user: str = Depends(get_current_user)`，作为第二道鉴权（routing O4）。
- 补一条测试：`ChatRequest.image_model` 的 Literal 取值与登记表的 id 集合一致（routing O5）。
- 退款测试加正控：断言成功路径确实扣了 10 颗，证明预扣发生过（spec-tests O1、routing O6）。
- 补聊天层多图修图的透传断言（spec-tests O1）。
- `PLAN.md` 的「2026-10-06：生图模型选择」小节挪到「2026-10-05：危机模型复核」之后（spec-tests O3）。

## 报告与验收

- 在 `03-report.md` 末尾追加「第 1 轮返修」，逐条写出改法与行号。
- 重跑规格 §7 的 A1–A3，贴原样尾部。
- 已有测试仍为 0 改动。
