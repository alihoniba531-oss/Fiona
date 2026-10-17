# WO3d 独立复核 第 2 轮（Sonnet）

- 范围：只核验 04-review 的必须修复 1–5、可优化 a–k、m、存疑 1；只读，未改代码和测试。
- 回归：`pytest -k studio` = 1574 passed（0 failed）；`tsc --noEmit` 无错误。
- 复用上轮复现脚本（`wo3d_review/test_studio_review_repro.py`）重跑，输出与上轮逐项相反（见下）。
- 新写实测脚本：`$TMPDIR/wo3d_r2/test_r2_verify.py`（对真实适配器 + 假传输，不入库）。

## 结论：通过（5 项必须修复与 a–k、m、存疑 1 均已修复；有 1 条低风险新发现，不涉及扣费、越权、数据损坏）

## 必须修复
1. 派生重复参考图：**已修复**。`casting.py:440-469`（报价只存显式参考 + `derive_from_approved`，张数按合并后算）、`casting_jobs.py:453-472`（执行期单点合并，已选定排第一并去重）。实测：仅派生 → 1 张图，说明为 derived；派生 + 3 参考 → 4 张、succeeded；派生 + 显式里重复带已选定 + 3 → 4 张；显式 4 + 派生 → 报价 422；无已选定勾派生 → 409；报价存的 `reference_asset_ids` 只含显式。
2. 归档：**已修复**。`casting.py:633-646`。实测：已选定版本、已定档试听归档 409，`voice_asset_id` 与 `spec_json.voice` 保持；非选定版本 200；无 `item_id` 的素材、`item_id` 非空但 `role=first_frame` 的素材 409；他人 404。
3. 传输错误误判：**已修复**。`tts_cosy.py:88-111`、`tts_edge.py:31-44` 只认数值属性 / 键，`_failure_from_message`（`:123`）不再对 dict 做 `str()`。实测：`:443` 的 ConnectionError、`wss://…:443` 的 OSError、`task-failed` 说明带 `:443`/`429ms`、纯文本断连 → 全部 uncertain；`status=429`、`status_code=400`、`header.status_code=400` → rejected；`status=503` → uncertain。
4. 重新拆解后旧条目：**已修复**。`casting.py:121-125`。实测：旧条目 `orphaned=true`，`g1.total` 从 3 变 1，旧条目报价 409。
5. 条目级补充提示词 / 参考图：**已修复**。`casting.py:454-469`。实测：保存的补充提示词在批量栏留空时进入 prompt；批量栏内容追加在其后；常驻参考 + 批量参考合并去重（2 张）；批量不改写条目常驻值；常驻 4 + 批量再加 1 → 422。前端文案已改（`CastingItemCard.tsx:62`、`CastingItems.tsx:86`）。

## 可优化（本轮承诺项）
- a 单事务：**已修复**。`casting.py:535-568` 一个 `transaction=True`，`prepare_jobs`（`casting_jobs.py:272`）不自行提交。实测：事务中途抛 409（任务行已插入）→ 报价仍 open、0 任务，重试 200。
- b 预检：**已修复**。`casting.py:516-533` 起始前重校验，`casting_jobs.py:425-435` 转 `PreflightError`。实测：起始前归档参考图 → 404，报价 open；起始后、执行前归档 → rejected/reference_unavailable，预留 0，POST 0；文件被删 → rejected/reference_unreadable，POST 0。
- c ffmpeg：**已修复**。`casting.py:40,714-717`。实测 ffmpeg 或 ffprobe 任一缺失 → 503，0 任务，Cosy 调用 0 次。
- d 孤儿 / 派生前提：**已修复**。孤儿报价 409（`casting.py:449`），起始 520、试听 709 同样 409；无已选定的派生见必修 1。
- e skip / reopen：**已修复**。`casting.py:623-631`；实测两者后 `approved_asset_id=None`。
- f 空风格：**已修复**。`casting.py:395-397`；`{}`、空白名称、空视觉风格、缺字段、两者都不给 → 422；有效值 200。
- g 总超时 + running 不悬挂：**已修复**。`image_seedream.py:241-256`（`TOTAL_TIMEOUT_S`；实测改小后 uncertain/timeout，只发 1 次 POST）；`casting_jobs.py:358-398`（置 running 后 `get_job` 抛错 → 任务落 uncertain，不停在 running）。
- h Cosy 超时后不发请求：**已修复**。`tts_cosy.py:187`、`:223-233`。实测预占锁 + 超时 → uncertain，SDK 调用 0 次。
- i PNG：**已修复**。`casting_jobs.py:171-183`。RGB、RGBA、P、L、LA、CMYK 全部输出 PNG 字节，长边 ≤1536。
- j 唯一索引：**已修复**。`store.py:248`（带表存在守卫）；实测重复 `(item_id,role,version_no)` 抛 IntegrityError，不同 role 与 `item_id` 为空的行不受限；迁移测试覆盖新库与旧基线库。
- k 清理前查引用：**已修复**。`casting_jobs.py:512-547`。实测：提交失败时，文件被另一资产引用 → 保留；无人引用 → 删除。
- m 提示词 ≤1800：**已修复**。`casting_prompts.py:177-240`。600 字 locked + 超长风格 / 外形 / 说明 / 补充 → 恰好 1800，locked 完整；PATCH 600 → 200，601 → 422（`casting.py:35`、`routers/studio.py:236`）。

## 存疑 1：**已修复**
参考图字节与 `data:image/png` 标签一致（见 i）。真实 Ark 是否校验格式仍需带 Key 冒烟确认，沿用上轮处置。

## 顺带确认：`StudioAssetImage.tsx`
只新增可选 props `loading?` / `decoding?` 并原样转发到 `<img>`（`:8-16,43`）。其余调用方 `ShotCard.tsx:42`、`ClipComposer.tsx:113` 未传这两个 prop，值为 `undefined`，React 不输出该属性，行为不变；仅 `CastingItemCard.tsx:69,78,105` 使用。

## 新发现（供用户裁决）
1. `casting.py:598-607` `_single_item` 用 `studio_projects.breakdown_id`（活动拆解）判孤儿，而 GET 列表、报价、试听用 `get_episodes()["breakdown_id"]`（已发布拆解）。重新拆解进行中、尚未发布时，PATCH / 选定 / skip / reopen / 声线选定的响应会把条目标成 `orphaned=true`，GET 列表却是 `false`（实测）。前端每次变更后整体刷新，实际仅 API 响应不一致；不涉及多扣费、越权、数据损坏。
